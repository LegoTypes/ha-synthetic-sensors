"""Variable resolution phase for synthetic sensor formulas."""

from dataclasses import dataclass
import logging
import re
from typing import Any, Callable

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.constants_formula import is_ha_state_value, is_reserved_word, normalize_ha_state_value
from ha_synthetic_sensors.exceptions import DataValidationError, MissingDependencyError
from ha_synthetic_sensors.shared_constants import get_ha_domains
from ha_synthetic_sensors.type_definitions import ContextValue, DataProviderResult
from ha_synthetic_sensors.utils_config import resolve_config_variables
from ha_synthetic_sensors.utils_resolvers import resolve_via_data_provider_attribute, resolve_via_hass_attribute

from .attribute_reference_resolver import AttributeReferenceResolver
from .resolver_factory import VariableResolverFactory

_LOGGER = logging.getLogger(__name__)


@dataclass
class VariableResolutionResult:
    """Result of variable resolution with HA state detection."""

    resolved_formula: str
    has_ha_state: bool = False
    ha_state_value: str | None = None
    unavailable_dependencies: list[str] | None = None


class VariableResolutionPhase:
    """Variable Resolution Engine - Phase 1 of compiler-like formula evaluation."""

    def __init__(
        self,
        sensor_to_backing_mapping: dict[str, str] | None = None,
        data_provider_callback: Callable[[str], DataProviderResult] | None = None,
    ) -> None:
        """Initialize the variable resolution phase."""
        self._resolver_factory = VariableResolverFactory(sensor_to_backing_mapping, data_provider_callback)
        self._sensor_registry_phase: Any = None
        self._formula_preprocessor: Any = None

    def set_formula_preprocessor(self, formula_preprocessor: Any) -> None:
        """Set the formula preprocessor for collection function resolution."""
        self._formula_preprocessor = formula_preprocessor

    @property
    def formula_preprocessor(self) -> Any:
        """Get the formula preprocessor."""
        return self._formula_preprocessor

    @property
    def resolve_collection_functions(self) -> Any:
        """Get the resolve_collection_functions method from the formula preprocessor."""
        if self.formula_preprocessor:
            return getattr(self.formula_preprocessor, "_resolve_collection_functions", None)
        return None

    def set_sensor_registry_phase(self, sensor_registry_phase: Any) -> None:
        """Set the sensor registry phase for cross-sensor reference resolution."""
        self._sensor_registry_phase = sensor_registry_phase
        # Update the cross-sensor resolver with the registry phase
        self._resolver_factory.set_sensor_registry_phase(sensor_registry_phase)

    def update_sensor_to_backing_mapping(
        self,
        sensor_to_backing_mapping: dict[str, str],
        data_provider_callback: Callable[[str], DataProviderResult] | None = None,
    ) -> None:
        """Update the sensor-to-backing entity mapping and data provider for state resolution."""
        # Update the existing resolver factory instead of recreating it
        self._resolver_factory.update_sensor_to_backing_mapping(sensor_to_backing_mapping, data_provider_callback)

    def set_dependency_handler(self, dependency_handler: Any) -> None:
        """Set the dependency handler to access current data provider callback."""
        self._dependency_handler = dependency_handler

        # Also set the dependency handler on the resolver factory for other resolvers
        self._resolver_factory.set_dependency_handler(dependency_handler)

        # Update the resolver factory with the current data provider callback for StateResolver
        if hasattr(dependency_handler, "data_provider_callback"):
            current_data_provider = dependency_handler.data_provider_callback
            # Update existing resolver factory with current data provider
            self._resolver_factory = VariableResolverFactory(
                self._resolver_factory.sensor_to_backing_mapping, current_data_provider
            )
            if self._sensor_registry_phase is not None:
                self._resolver_factory.set_sensor_registry_phase(self._sensor_registry_phase)
            # Re-set the dependency handler after recreating the factory
            self._resolver_factory.set_dependency_handler(dependency_handler)

    def update_data_provider_callback(self, data_provider_callback: Callable[[str], DataProviderResult] | None) -> None:
        """Update the data provider callback for the StateResolver."""
        # Recreate the resolver factory with the updated data provider
        self._resolver_factory = VariableResolverFactory(
            self._resolver_factory.sensor_to_backing_mapping, data_provider_callback
        )
        if self._sensor_registry_phase is not None:
            self._resolver_factory.set_sensor_registry_phase(self._sensor_registry_phase)
        if hasattr(self, "_dependency_handler"):
            self._resolver_factory.set_dependency_handler(self._dependency_handler)

    def resolve_all_references_with_ha_detection(
        self,
        formula: str,
        sensor_config: SensorConfig | None,
        eval_context: dict[str, ContextValue],
        formula_config: FormulaConfig | None = None,
    ) -> VariableResolutionResult:
        """
        Variable resolution with HA state detection.

        This method performs complete variable resolution and detects HA state values
        early to prevent invalid expressions from reaching the evaluator.
        """
        # Track entity mappings for enhanced dependency reporting
        entity_mappings: dict[str, str] = {}  # variable_name -> entity_id
        unavailable_dependencies: list[str] = []

        # Start with the original formula
        resolved_formula = formula

        # Resolve collection functions (always, regardless of sensor config)
        resolved_formula = self._resolve_collection_functions(resolved_formula, sensor_config, eval_context, formula_config)

        # STEP 1: Resolve state.attribute references FIRST (before entity references)
        if sensor_config:
            resolved_formula = self._resolve_state_attribute_references(resolved_formula, sensor_config)

        # STEP 2: Pre-scan for variable.attribute patterns to identify variables that need entity ID preservation
        variables_needing_entity_ids = self._identify_variables_for_attribute_access(resolved_formula, formula_config)

        # STEP 3: Resolve config variables with special handling for attribute access variables
        if formula_config:
            self._resolve_config_variables_with_attribute_preservation(
                eval_context, formula_config, variables_needing_entity_ids
            )

        # STEP 4: Resolve variable.attribute references (e.g., device.battery_level)
        # This must happen BEFORE simple variable resolution to catch attribute patterns
        resolved_formula = self._resolve_attribute_chains(resolved_formula, eval_context, formula_config)

        # STEP 5: Resolve entity references and track mappings and HA states
        resolved_formula, entity_mappings_from_entities, ha_deps_from_entities = self._resolve_entity_references_with_tracking(
            resolved_formula, eval_context
        )
        entity_mappings.update(entity_mappings_from_entities)
        unavailable_dependencies.extend(ha_deps_from_entities)

        # STEP 6: Resolve remaining config variables and track mappings
        if formula_config:
            var_mappings, ha_deps = self._resolve_config_variables_with_tracking(eval_context, formula_config, sensor_config)
            entity_mappings.update(var_mappings)
            unavailable_dependencies.extend(ha_deps)

        # STEP 7: Resolve simple variables from evaluation context and track mappings
        # Skip variables that are used in attribute chains (they were already handled in STEP 4)
        resolved_formula, simple_var_mappings, simple_ha_deps = self._resolve_simple_variables_with_tracking(
            resolved_formula, eval_context, entity_mappings
        )
        entity_mappings.update(simple_var_mappings)
        # Only add dependencies that aren't already in the list
        for dep in simple_ha_deps:
            if dep not in unavailable_dependencies:
                unavailable_dependencies.append(dep)

        # STEP 8: Check for HA state values in the resolved formula
        ha_state_result = self._detect_ha_state_in_formula(resolved_formula, unavailable_dependencies)
        if ha_state_result:
            return ha_state_result

        # STEP 9: Continue with remaining resolution steps
        resolved_formula = self._resolve_attribute_references(resolved_formula, eval_context)

        # Early return if no sensor config for the remaining steps
        if not sensor_config:
            _LOGGER.debug("Formula resolution (no sensor config): '%s' -> '%s'", formula, resolved_formula)
            return VariableResolutionResult(resolved_formula=resolved_formula)

        # Add sensor_config and formula_config to context for resolvers
        extended_context: dict[str, ContextValue] = eval_context.copy()
        extended_context["sensor_config"] = sensor_config  # type: ignore[assignment]
        if formula_config:
            extended_context["formula_config"] = formula_config  # type: ignore[assignment]

        # STEP 10: Resolve standalone 'state' references
        resolved_formula = self._resolve_state_references(resolved_formula, sensor_config, extended_context)

        # STEP 11: Resolve cross-sensor references
        resolved_formula = self._resolve_cross_sensor_references(resolved_formula, eval_context, sensor_config, formula_config)

        # Final check for HA state values
        final_ha_state_result = self._detect_ha_state_in_formula(resolved_formula, unavailable_dependencies)
        if final_ha_state_result:
            return final_ha_state_result

        _LOGGER.debug("Formula resolution: '%s' -> '%s'", formula, resolved_formula)
        return VariableResolutionResult(resolved_formula=resolved_formula)

    def resolve_all_references_in_formula(
        self,
        formula: str,
        sensor_config: SensorConfig | None,
        eval_context: dict[str, ContextValue],
        formula_config: FormulaConfig | None = None,
    ) -> str:
        """
        COMPILER-LIKE APPROACH: Resolve ALL references in formula to actual values.

        This method performs a complete resolution pass, handling:
        1. Collection functions (e.g., sum("device_class:power") -> sum(1000, 500, 200))
        2. state.attribute references (e.g., state.voltage -> 240.0)
        3. state references (e.g., state -> 1000.0)
        4. entity references (e.g., sensor.temperature -> 23.5)
        5. cross-sensor references (e.g., base_power_sensor -> 1000.0)

        After this method, the formula should contain only numeric values and operators.
        """
        # Use the enhanced version but return only the resolved formula for backward compatibility
        result = self.resolve_all_references_with_ha_detection(formula, sensor_config, eval_context, formula_config)
        return result.resolved_formula

    def _resolve_attribute_references(self, formula: str, eval_context: dict[str, ContextValue]) -> str:
        """Resolve attribute-to-attribute references in the formula."""
        # Get the attribute reference resolver
        attribute_resolver = None
        for resolver in self._resolver_factory.get_all_resolvers():
            if resolver.get_resolver_name() == "AttributeReferenceResolver":
                attribute_resolver = resolver
                break

        if attribute_resolver and hasattr(attribute_resolver, "resolve_references_in_formula"):
            try:
                # Cast to AttributeReferenceResolver since we've verified the method exists
                attr_resolver: AttributeReferenceResolver = attribute_resolver  # type: ignore[assignment]
                resolved_formula = attr_resolver.resolve_references_in_formula(formula, eval_context)
                return str(resolved_formula)
            except Exception as e:
                _LOGGER.warning("Error resolving attribute references in formula '%s': %s", formula, e)
                return formula
        else:
            # No attribute resolver available, return formula unchanged
            return formula

    def _resolve_collection_functions(
        self,
        formula: str,
        sensor_config: SensorConfig | None,
        eval_context: dict[str, ContextValue],
        formula_config: FormulaConfig | None = None,
    ) -> str:
        """Resolve collection functions using the formula preprocessor."""
        if not self.formula_preprocessor:
            return formula

        try:
            # Prepare exclusion set for automatic self-exclusion
            exclude_entity_ids = None
            if sensor_config and sensor_config.unique_id:
                # Convert sensor unique_id to entity_id format for exclusion
                current_entity_id = f"sensor.{sensor_config.unique_id}"
                exclude_entity_ids = {current_entity_id}
                _LOGGER.debug("Auto-excluding current sensor %s from collection functions", current_entity_id)

            # Use the formula preprocessor to resolve collection functions
            resolve_func = self.resolve_collection_functions
            if resolve_func and callable(resolve_func):
                # pylint: disable=not-callable
                resolved_formula = resolve_func(formula, exclude_entity_ids)
                _LOGGER.debug("Collection function resolution: '%s' -> '%s'", formula, resolved_formula)
                return str(resolved_formula)
            return formula
        except Exception as e:
            _LOGGER.warning("Error resolving collection functions in formula '%s': %s", formula, e)
            return formula

    def resolve_config_variables(
        self,
        eval_context: dict[str, ContextValue],
        config: FormulaConfig | None,
        sensor_config: SensorConfig | None = None,
    ) -> None:
        """Resolve config variables using the resolver factory."""

        def resolver_callback(var_name: str, var_value: Any, context: dict[str, ContextValue], _sensor_cfg: Any) -> Any:
            return self._resolver_factory.resolve_variable(var_name, var_value, context)

        resolve_config_variables(eval_context, config, resolver_callback, sensor_config)

    def _resolve_state_attribute_references(self, formula: str, sensor_config: SensorConfig) -> str:
        """Resolve state.attribute references including nested attributes."""
        attr_pattern = re.compile(r"\bstate\.([a-zA-Z_][a-zA-Z0-9_.]*)\b")

        def replace_attr_ref(match: re.Match[str]) -> str:
            attr_path = match.group(1)  # e.g., "voltage" or "device_info.manufacturer"
            attr_ref = f"state.{attr_path}"

            # Create extended context with sensor_config for the resolver
            extended_context = {"sensor_config": sensor_config}

            # Use the resolver factory to resolve the attribute reference
            resolved_value = self._resolver_factory.resolve_variable(attr_ref, attr_ref, extended_context)

            if resolved_value is not None:
                # Handle string concatenation properly
                if isinstance(resolved_value, str):
                    return f'"{resolved_value}"'  # Wrap strings in quotes for proper evaluation
                return str(resolved_value)
            _LOGGER.warning("Failed to resolve attribute reference '%s' in formula", attr_ref)
            # Return None instead of "unknown" to indicate resolution failure
            return "None"

        return attr_pattern.sub(replace_attr_ref, formula)

    def _resolve_state_references(
        self, formula: str, sensor_config: SensorConfig, eval_context: dict[str, ContextValue]
    ) -> str:
        """Resolve standalone 'state' references."""
        if "state" not in formula:
            return formula

        # Only resolve standalone 'state', not 'state.something' (which we already handled)
        state_pattern = re.compile(r"\bstate\b(?!\.)")

        def replace_state_ref(match: re.Match[str]) -> str:
            # Use the resolver factory to resolve the state reference
            # The StateResolver will handle backing entity validation and throw exceptions if needed
            resolved_value = self._resolver_factory.resolve_variable("state", "state", eval_context)

            if resolved_value is not None:
                return str(resolved_value)
            # This should not happen if StateResolver is working correctly
            _LOGGER.warning("State token resolution returned None unexpectedly")
            return "0.0"

        return state_pattern.sub(replace_state_ref, formula)

    def _resolve_entity_references(self, formula: str, eval_context: dict[str, ContextValue]) -> str:
        """Resolve entity references (e.g., sensor.temperature -> 23.5)."""
        # Pattern that explicitly prevents matching decimals by requiring word boundary at start and letter/underscore
        entity_pattern = re.compile(
            r"(?:^|(?<=\s)|(?<=\()|(?<=[+\-*/]))([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z0-9_.]+)(?=\s|$|[+\-*/)])"
        )

        def replace_entity_ref(match: re.Match[str]) -> str:
            entity_id = match.group(1)

            # First check if already resolved in context
            var_name = entity_id.replace(".", "_").replace("-", "_")
            if var_name in eval_context:
                return str(eval_context[var_name])
            if entity_id in eval_context:
                return str(eval_context[entity_id])

            # Use the resolver factory to resolve the entity reference
            resolved_value = self._resolver_factory.resolve_variable(entity_id, entity_id, eval_context)

            if resolved_value is not None:
                return str(resolved_value)

            _LOGGER.warning("Failed to resolve entity reference '%s' in formula", entity_id)
            raise MissingDependencyError(f"Failed to resolve entity reference '{entity_id}' in formula")

        return entity_pattern.sub(replace_entity_ref, formula)

    def _resolve_cross_sensor_references(
        self,
        formula: str,
        eval_context: dict[str, ContextValue],
        sensor_config: SensorConfig | None = None,
        formula_config: FormulaConfig | None = None,
    ) -> str:
        """Resolve cross-sensor references (e.g., base_power_sensor -> 1000.0)."""
        sensor_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")

        def replace_sensor_ref(match: re.Match[str]) -> str:
            sensor_name = match.group(1)

            # Skip if this looks like a number, operator, or function
            if is_reserved_word(sensor_name):
                return sensor_name

            # Check for self-reference in attribute context
            if (
                sensor_config
                and formula_config
                and sensor_name == sensor_config.unique_id
                and formula_config.id != "main"
                and formula_config.id != sensor_config.unique_id
            ):
                # Self-reference in attribute formula: replace with 'state' token
                # This ensures attribute formulas use the current evaluation cycle's main sensor result
                _LOGGER.debug(
                    "Cross-sensor resolver: detected self-reference '%s' in attribute formula '%s', replacing with 'state' token",
                    sensor_name,
                    formula_config.id,
                )
                return "state"

            # Use the resolver factory to resolve cross-sensor references
            resolved_value = self._resolver_factory.resolve_variable(sensor_name, sensor_name, eval_context)

            if resolved_value is not None:
                # Handle different data types appropriately
                if isinstance(resolved_value, str):
                    return f'"{resolved_value}"'  # Wrap strings in quotes
                return str(resolved_value)
            # Check if this is a cross-sensor reference
            if self._sensor_registry_phase and self._sensor_registry_phase.is_sensor_registered(sensor_name):
                sensor_value = self._sensor_registry_phase.get_sensor_value(sensor_name)
                if sensor_value is not None:
                    return str(sensor_value)
            # Not a cross-sensor reference, return as-is
            return sensor_name

        return sensor_pattern.sub(replace_sensor_ref, formula)

    def _resolve_simple_variables(self, formula: str, eval_context: dict[str, ContextValue]) -> str:
        """Resolve simple variable references from the evaluation context."""
        # Pattern to match simple variable names (letters, numbers, underscores)
        # Negative look-ahead `(?!\.)` ensures we do NOT match names that are immediately
        # followed by a dot (these are part of variable.attribute token chains)
        variable_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)(?!\.)\b")

        def replace_variable_ref(match: re.Match[str]) -> str:
            var_name = match.group(1)

            # Skip reserved words and function names
            if is_reserved_word(var_name):
                return var_name

            # Check if this variable exists in the evaluation context
            if var_name in eval_context:
                value = eval_context[var_name]
                if isinstance(value, str):
                    # For string values, return them quoted for proper evaluation
                    return f'"{value}"'
                return str(value)

            # Not a variable, return as-is
            return var_name

        return variable_pattern.sub(replace_variable_ref, formula)

    def _resolve_simple_variables_with_usage_tracking(
        self, formula: str, eval_context: dict[str, ContextValue]
    ) -> tuple[str, set[str]]:
        """Resolve simple variable references and track which variables were used."""
        # Pattern to match simple variable names (letters, numbers, underscores)
        # Negative look-ahead `(?!\.)` ensures we do NOT match names that are immediately
        # followed by a dot (these are part of variable.attribute token chains)
        variable_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)(?!\.)\b")

        used_variables: set[str] = set()

        def replace_variable(match: re.Match[str]) -> str:
            var_name = match.group(1)
            if var_name in eval_context:
                used_variables.add(var_name)
                value = eval_context[var_name]
                # Convert to string representation for formula substitution
                return str(value)
            return match.group(0)  # Keep original if not found

        resolved_formula = variable_pattern.sub(replace_variable, formula)
        return resolved_formula, used_variables

    def _resolve_attribute_chains(
        self, formula: str, eval_context: dict[str, ContextValue], formula_config: FormulaConfig | None
    ) -> str:
        """Resolve complete attribute chains including atributes like 'device.battery_level'."""
        if not formula_config:
            return formula

        # Pattern to match variable.attribute patterns
        # This matches: variable_name.attribute_name where variable_name is a valid variable name
        attribute_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b")

        def replace_attribute_chain(match: re.Match[str]) -> str:
            variable_name = match.group(1)
            attribute_name = match.group(2)

            # Get the original entity ID from the formula config (not the resolved value from context)
            if variable_name not in formula_config.variables:
                return match.group(0)  # Keep original if variable not found in config

            entity_id = formula_config.variables[variable_name]
            if not isinstance(entity_id, str):
                return match.group(0)  # Keep original if not a string entity ID

            _LOGGER.debug(
                "Resolving attribute chain %s.%s where %s = %s", variable_name, attribute_name, variable_name, entity_id
            )

            # Resolve the attribute using the attribute resolver
            try:
                attribute_value = self._resolve_entity_attribute(entity_id, attribute_name)
                _LOGGER.debug("Resolved attribute chain %s.%s to %s", variable_name, attribute_name, attribute_value)
                return str(attribute_value)
            except MissingDependencyError:
                raise  # Re-raise fatal errors per design guide
            except Exception as e:
                _LOGGER.debug("Failed to resolve attribute chain %s.%s: %s", variable_name, attribute_name, e)
                return match.group(0)  # Keep original on error

        return attribute_pattern.sub(replace_attribute_chain, formula)

    def _resolve_entity_attribute(self, entity_id: str, attribute_name: str) -> Any:
        """Resolve an entity attribute using the dependency handler."""
        if not self._dependency_handler:
            raise ValueError("Dependency handler not set")

        # Try data provider resolution first
        data_provider_result = resolve_via_data_provider_attribute(
            self._dependency_handler, entity_id, attribute_name, f"{entity_id}.{attribute_name}"
        )
        if data_provider_result is not None:
            return data_provider_result

        # Try HASS state lookup
        hass_result = resolve_via_hass_attribute(
            self._dependency_handler, entity_id, attribute_name, f"{entity_id}.{attribute_name}"
        )
        if hass_result is not None:
            return hass_result

        # Could not resolve entity attribute
        raise MissingDependencyError(f"Could not resolve attribute '{attribute_name}' of entity '{entity_id}'")

    def _resolve_variable_attribute_references(self, formula: str, eval_context: dict[str, ContextValue]) -> str:
        """Resolve variable.attribute references (e.g., device.battery_level where device is a variable)."""
        _LOGGER.debug("Resolving variable.attribute references in formula: '%s'", formula)
        _LOGGER.debug("Evaluation context keys: %s", list(eval_context.keys()))

        # Pattern to match variable.attribute where variable might be defined in context
        var_attr_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_.]*)\b")

        # Get hass from dependency handler if available
        hass = (
            getattr(self._dependency_handler, "hass", None)
            if hasattr(self, "_dependency_handler") and self._dependency_handler
            else None
        )

        def replace_var_attr_ref(match: re.Match[str]) -> str:
            variable_name = match.group(1)
            attribute_name = match.group(2)
            full_reference = f"{variable_name}.{attribute_name}"

            _LOGGER.debug(
                "Found potential variable.attribute match: %s (var=%s, attr=%s)", full_reference, variable_name, attribute_name
            )

            # Check if this is a variable.attribute pattern by seeing if variable_name is in context
            if variable_name in eval_context:
                entity_id = eval_context[variable_name]
                _LOGGER.debug(
                    "Variable '%s' found in context with value: %s (type: %s)", variable_name, entity_id, type(entity_id)
                )

                # Only process if it resolves to an entity ID (string starting with known domains)
                if isinstance(entity_id, str):
                    ha_domains = get_ha_domains(hass)
                    is_entity_id = any(entity_id.startswith(f"{domain}.") for domain in ha_domains)

                    if is_entity_id:
                        _LOGGER.debug(
                            "Resolving variable.attribute reference: %s -> %s.%s", full_reference, entity_id, attribute_name
                        )

                        # Use the resolver factory to resolve this as an entity attribute
                        resolved_value = self._resolver_factory.resolve_variable(full_reference, full_reference, eval_context)

                        if resolved_value is not None:
                            if isinstance(resolved_value, str):
                                _LOGGER.debug("Resolved %s to string: %s", full_reference, resolved_value)
                                return f'"{resolved_value}"'  # Wrap strings in quotes
                            _LOGGER.debug("Resolved %s to value: %s", full_reference, resolved_value)
                            return str(resolved_value)

                        _LOGGER.warning("Failed to resolve variable attribute reference '%s'", full_reference)
                        return full_reference  # Return original if resolution fails

                    _LOGGER.debug(
                        "Variable '%s' value '%s' is not an entity ID (wrong type or domain)", variable_name, entity_id
                    )
            else:
                _LOGGER.debug("Variable '%s' not found in context", variable_name)

            # Not a variable.attribute pattern we can handle, return original
            _LOGGER.debug("Returning original reference: %s", full_reference)
            return full_reference

        return var_attr_pattern.sub(replace_var_attr_ref, formula)

    def _resolve_entity_references_with_tracking(
        self, formula: str, eval_context: dict[str, ContextValue]
    ) -> tuple[str, dict[str, str], list[str]]:
        """Resolve entity references and track variable to entity mappings and HA states."""
        # Exclude state.attribute patterns and variable.attribute patterns where first part is not an entity domain
        # Only match domain.entity_name patterns (actual entity IDs)
        # Get hass from dependency handler if available
        hass = (
            getattr(self._dependency_handler, "hass", None)
            if hasattr(self, "_dependency_handler") and self._dependency_handler
            else None
        )

        # Validate domain availability for proper entity pattern construction
        if hass is not None:
            try:
                domains = get_ha_domains(hass)
                if not domains:
                    # This is a critical error - we have hass but no domains
                    # This indicates a configuration or initialization problem
                    raise DataValidationError(
                        "No entity domains available from Home Assistant registry. "
                        "This indicates a configuration or initialization problem. "
                        "Entity resolution cannot proceed safely without domain validation."
                    )

                entity_domains = "|".join(sorted(domains))
                # Pattern that requires a valid domain followed by dot and entity name
                # This avoids matching .1 or other invalid patterns
                entity_pattern = re.compile(rf"\b({entity_domains})\.([a-zA-Z0-9_]+)\b")
                _LOGGER.debug("Using hass-based entity pattern with %d domains: %s", len(domains), entity_pattern.pattern)
            except DataValidationError:
                # Re-raise DataValidationError as it's a critical configuration issue
                raise
            except Exception as e:
                _LOGGER.error("Critical error getting domains from HA: %s", e)
                raise DataValidationError(
                    f"Failed to get entity domains from Home Assistant: {e}. "
                    "Entity resolution cannot proceed safely without domain validation."
                ) from e
        else:
            # No hass available - only acceptable in testing scenarios
            # Use fallback pattern that explicitly prevents matching decimals
            _LOGGER.warning(
                "No Home Assistant instance available for domain validation. "
                "Using fallback entity pattern - this should only occur in testing scenarios."
            )
            entity_pattern = re.compile(
                r"(?:^|(?<=\s)|(?<=\()|(?<=[+\-*/]))([a-zA-Z_][a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)(?=\s|$|[+\-*/)])"
            )

        entity_mappings: dict[str, str] = {}
        ha_dependencies: list[str] = []

        def replace_entity_ref(match: re.Match[str]) -> str:
            domain = match.group(1)
            entity_name = match.group(2)
            entity_id = f"{domain}.{entity_name}"

            _LOGGER.debug(
                "Entity reference match: domain='%s', entity_name='%s', entity_id='%s'", domain, entity_name, entity_id
            )

            # First check if already resolved in context
            var_name = entity_id.replace(".", "_").replace("-", "_")
            if var_name in eval_context:
                value = eval_context[var_name]
                # Only return the value if it's already resolved (not a raw entity ID)
                if value != entity_id:
                    entity_mappings[var_name] = entity_id
                    # Check if value is an HA state
                    if isinstance(value, str) and is_ha_state_value(value):
                        ha_dependencies.append(f"{var_name} ({entity_id}) is {value}")
                    return str(value)
            if entity_id in eval_context:
                value = eval_context[entity_id]
                # Only return the value if it's already resolved (not a raw entity ID)
                if value != entity_id:
                    entity_mappings[entity_id] = entity_id
                    # Check if value is an HA state
                    if isinstance(value, str) and is_ha_state_value(value):
                        ha_dependencies.append(f"{entity_id} ({entity_id}) is {value}")
                    return str(value)

            # Use the resolver factory to resolve the entity reference
            resolved_value = self._resolver_factory.resolve_variable(entity_id, entity_id, eval_context)

            if resolved_value is not None:
                entity_mappings[entity_id] = entity_id

                # Check if resolved value is an HA state
                if isinstance(resolved_value, str) and is_ha_state_value(resolved_value):
                    ha_dependencies.append(f"{entity_id} ({entity_id}) is {resolved_value}")

                return str(resolved_value)

            _LOGGER.warning("Failed to resolve entity reference '%s' in formula", entity_id)
            raise MissingDependencyError(f"Failed to resolve entity reference '{entity_id}' in formula")

        _LOGGER.debug("Resolving entity references in formula: '%s'", formula)
        resolved_formula = entity_pattern.sub(replace_entity_ref, formula)
        return resolved_formula, entity_mappings, ha_dependencies

    def _resolve_config_variables_with_tracking(
        self, eval_context: dict[str, ContextValue], config: FormulaConfig, sensor_config: SensorConfig | None = None
    ) -> tuple[dict[str, str], list[str]]:
        """Resolve config variables and track entity mappings and HA states."""
        entity_mappings: dict[str, str] = {}
        ha_dependencies: list[str] = []

        # Get hass from dependency handler if available
        hass = (
            getattr(self._dependency_handler, "hass", None)
            if hasattr(self, "_dependency_handler") and self._dependency_handler
            else None
        )

        for var_name, var_value in config.variables.items():
            # Track entity mapping if var_value looks like an entity ID
            if isinstance(var_value, str) and any(var_value.startswith(f"{domain}.") for domain in get_ha_domains(hass)):
                entity_mappings[var_name] = var_value

            # Check if this variable is already resolved with an actual value
            if var_name in eval_context:
                existing_value = eval_context[var_name]
                # If the existing value is the same as var_value (raw entity ID), we need to resolve it
                if existing_value == var_value and isinstance(var_value, str):
                    _LOGGER.debug("Config variable %s has raw entity ID value %s, needs resolution", var_name, var_value)
                    # Continue to resolve it
                elif existing_value != var_value:
                    # Already resolved to a different value, check if it's an HA state
                    if isinstance(existing_value, str) and is_ha_state_value(existing_value):
                        entity_id = entity_mappings.get(var_name, var_value if isinstance(var_value, str) else "unknown")
                        ha_dependencies.append(f"{var_name} ({entity_id}) is {existing_value}")
                    _LOGGER.debug("Skipping config variable %s (already resolved to %s)", var_name, existing_value)
                    continue

            try:
                resolved_value = self._resolver_factory.resolve_variable(var_name, var_value, eval_context)
                if resolved_value is not None:
                    eval_context[var_name] = resolved_value
                    _LOGGER.debug("Added config variable %s=%s", var_name, resolved_value)

                    # Check if resolved value is an HA state
                    if isinstance(resolved_value, str) and is_ha_state_value(resolved_value):
                        entity_id = entity_mappings.get(var_name, var_value if isinstance(var_value, str) else "unknown")
                        ha_dependencies.append(f"{var_name} ({entity_id}) is {resolved_value}")
                else:
                    _LOGGER.warning(
                        "Config variable '%s' in formula '%s' resolved to None",
                        var_name,
                        config.name or config.id,
                    )
            except MissingDependencyError:
                # Propagate MissingDependencyError according to the reference guide's error propagation idiom
                raise
            except DataValidationError:
                # Propagate DataValidationError according to the reference guide's error propagation idiom
                raise
            except Exception as err:
                _LOGGER.warning("Error resolving config variable %s: %s", var_name, err)

        return entity_mappings, ha_dependencies

    def _resolve_simple_variables_with_tracking(
        self, formula: str, eval_context: dict[str, ContextValue], existing_mappings: dict[str, str]
    ) -> tuple[str, dict[str, str], list[str]]:
        """Resolve simple variable references and track HA states."""
        # Same negative look-ahead to avoid variable.attribute premature resolution
        variable_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)(?!\.)\b")
        entity_mappings: dict[str, str] = {}
        ha_dependencies: list[str] = []

        def replace_variable_ref(match: re.Match[str]) -> str:
            var_name = match.group(1)

            # Skip reserved words and function names
            if is_reserved_word(var_name):
                return var_name

            # Check if this variable exists in the evaluation context
            if var_name in eval_context:
                value = eval_context[var_name]

                # Check if value is an HA state
                if isinstance(value, str) and is_ha_state_value(value):
                    entity_id = existing_mappings.get(var_name, "unknown")
                    ha_dependencies.append(f"{var_name} ({entity_id}) is {value}")

                if isinstance(value, str):
                    # For string values, return them quoted for proper evaluation
                    return f'"{value}"'
                return str(value)

            # Not a variable, return as-is
            return var_name

        resolved_formula = variable_pattern.sub(replace_variable_ref, formula)
        return resolved_formula, entity_mappings, ha_dependencies

    def _identify_variables_for_attribute_access(self, formula: str, formula_config: FormulaConfig | None) -> set[str]:
        """Identify variables that are used in .attribute patterns and need entity ID preservation."""
        variables_needing_entity_ids: set[str] = set()

        if not formula_config:
            return variables_needing_entity_ids

        # Pattern to match variable.attribute where variable might be defined in config
        var_attr_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_.]*)\b")

        for match in var_attr_pattern.finditer(formula):
            variable_name = match.group(1)
            # Check if this variable is defined in the formula config
            if variable_name in formula_config.variables:
                var_value = formula_config.variables[variable_name]
                # Only preserve entity IDs (strings starting with known domains)
                if isinstance(var_value, str) and any(var_value.startswith(f"{domain}.") for domain in get_ha_domains()):
                    variables_needing_entity_ids.add(variable_name)
                    _LOGGER.debug(
                        "Identified variable '%s' for entity ID preservation (used in .attribute pattern)", variable_name
                    )

        return variables_needing_entity_ids

    def _resolve_config_variables_with_attribute_preservation(
        self, eval_context: dict[str, ContextValue], formula_config: FormulaConfig, variables_needing_entity_ids: set[str]
    ) -> None:
        """Resolve config variables with special handling for variables used in .attribute patterns."""
        for var_name, var_value in formula_config.variables.items():
            # If this variable is used in .attribute patterns, override with entity ID
            if var_name in variables_needing_entity_ids:
                _LOGGER.debug("Overriding variable '%s' with entity ID (used in .attribute pattern): %s", var_name, var_value)
                eval_context[var_name] = var_value
                continue

            # Skip if this variable is already set in context (context has higher priority)
            if var_name in eval_context:
                _LOGGER.debug("Skipping config variable %s (already set in context)", var_name)
                continue

            # Otherwise, resolve normally
            try:
                resolved_value = self._resolver_factory.resolve_variable(var_name, var_value, eval_context)
                if resolved_value is not None:
                    eval_context[var_name] = resolved_value
                    _LOGGER.debug("Added config variable %s=%s", var_name, resolved_value)
                else:
                    _LOGGER.warning(
                        "Config variable '%s' in formula '%s' resolved to None",
                        var_name,
                        formula_config.name or formula_config.id,
                    )
            except MissingDependencyError:
                # Propagate MissingDependencyError according to the reference guide's error propagation idiom
                raise
            except DataValidationError:
                # Propagate DataValidationError according to the reference guide's error propagation idiom
                raise
            except Exception as err:
                _LOGGER.warning("Error resolving config variable %s: %s", var_name, err)

    def _detect_ha_state_in_formula(self, formula: str, unavailable_dependencies: list[str]) -> VariableResolutionResult | None:
        """Detect HA state values in resolved formula and return appropriate result."""
        # If any unavailable dependencies exist, escalate the final state to 'unavailable'
        unavailable = [dep for dep in (unavailable_dependencies or []) if dep.endswith("is unavailable")]
        unknown = [dep for dep in (unavailable_dependencies or []) if dep.endswith("is unknown")]
        if unavailable:
            return VariableResolutionResult(
                resolved_formula=formula,
                has_ha_state=True,
                ha_state_value="unavailable",
                unavailable_dependencies=unavailable_dependencies or [],
            )
        if unknown:
            return VariableResolutionResult(
                resolved_formula=formula,
                has_ha_state=True,
                ha_state_value="unknown",
                unavailable_dependencies=unavailable_dependencies or [],
            )

        # Check for HA state values in the resolved formula - both quoted and unquoted
        for state_value in ["unknown", "unavailable"]:
            # Check for quoted HA state values in expressions (e.g., "unavailable" + 10)
            if f'"{state_value}"' in formula:
                _LOGGER.debug("Formula contains quoted HA state '%s', returning HA state", state_value)
                return VariableResolutionResult(
                    resolved_formula=formula,
                    has_ha_state=True,
                    ha_state_value=state_value,
                    unavailable_dependencies=unavailable_dependencies or [],
                )

            # Check for unquoted HA state values
            if state_value in formula:
                _LOGGER.debug("Formula contains unquoted HA state '%s', returning HA state", state_value)
                return VariableResolutionResult(
                    resolved_formula=formula,
                    has_ha_state=True,
                    ha_state_value=state_value,
                    unavailable_dependencies=unavailable_dependencies or [],
                )

        # Check for other HA state values that should result in corresponding sensor states
        stripped_formula = formula.strip()
        # Handle quoted strings by removing quotes
        if stripped_formula.startswith('"') and stripped_formula.endswith('"'):
            stripped_formula = stripped_formula[1:-1]

        if is_ha_state_value(stripped_formula):
            state_value = normalize_ha_state_value(stripped_formula)
            _LOGGER.debug("Formula resolved to HA state '%s'", state_value)
            return VariableResolutionResult(
                resolved_formula=formula,
                has_ha_state=True,
                ha_state_value=state_value,
                unavailable_dependencies=unavailable_dependencies or [],
            )

        return None
