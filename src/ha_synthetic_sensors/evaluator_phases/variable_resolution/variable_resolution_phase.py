"""Variable resolution phase for synthetic sensor formulas."""

from collections.abc import Callable
import logging
import re
from typing import Any

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.constants_formula import is_ha_state_value, is_reserved_word
from ha_synthetic_sensors.evaluator_handlers.metadata_handler import MetadataHandler
from ha_synthetic_sensors.exceptions import DataValidationError, MissingDependencyError
from ha_synthetic_sensors.shared_constants import get_ha_domains
from ha_synthetic_sensors.type_definitions import ContextValue, DataProviderResult, ReferenceValue
from ha_synthetic_sensors.utils_config import resolve_config_variables

from .attribute_reference_resolver import AttributeReferenceResolver
from .formula_helpers import FormulaHelpers
from .resolution_helpers import ResolutionHelpers
from .resolution_types import VariableResolutionResult
from .resolver_factory import VariableResolverFactory
from .variable_inheritance import VariableInheritanceHandler
from .variable_processors import VariableProcessors

_LOGGER = logging.getLogger(__name__)


class VariableResolutionPhase:
    """Variable Resolution Engine - Phase 1 of compiler-like formula evaluation."""

    def __init__(
        self,
        sensor_to_backing_mapping: dict[str, str] | None = None,
        data_provider_callback: Callable[[str], DataProviderResult] | None = None,
        hass: Any = None,
    ) -> None:
        """Initialize the variable resolution phase."""
        self._hass = hass  # Store HA instance for factory recreation
        self._resolver_factory = VariableResolverFactory(sensor_to_backing_mapping, data_provider_callback, hass)
        self._sensor_registry_phase: Any = None
        self._formula_preprocessor: Any = None
        self._global_settings: dict[str, Any] | None = None  # Store reference to current global settings
        # Initialize inheritance handler with no global settings by default
        # This ensures variable inheritance works even when set_global_settings is never called
        self._inheritance_handler: VariableInheritanceHandler = VariableInheritanceHandler(None)

    def set_formula_preprocessor(self, formula_preprocessor: Any) -> None:
        """Set the formula preprocessor for collection function resolution."""
        self._formula_preprocessor = formula_preprocessor

    def set_global_settings(self, global_settings: dict[str, Any] | None) -> None:
        """Set global settings for variable inheritance.
        This should be called after cross-reference resolution to ensure
        global variables reflect current entity IDs.
        """
        self._global_settings = global_settings
        self._inheritance_handler = VariableInheritanceHandler(global_settings)

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
            # Update existing resolver factory with current data provider (preserve HA instance)
            self._resolver_factory = VariableResolverFactory(
                self._resolver_factory.sensor_to_backing_mapping, current_data_provider, self._hass
            )
            if self._sensor_registry_phase is not None:
                self._resolver_factory.set_sensor_registry_phase(self._sensor_registry_phase)
            # Re-set the dependency handler after recreating the factory
            self._resolver_factory.set_dependency_handler(dependency_handler)

    def update_data_provider_callback(self, data_provider_callback: Callable[[str], DataProviderResult] | None) -> None:
        """Update the data provider callback for the StateResolver."""
        # Recreate the resolver factory with the updated data provider (preserve HA instance)
        self._resolver_factory = VariableResolverFactory(
            self._resolver_factory.sensor_to_backing_mapping, data_provider_callback, self._hass
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
        entity_to_value_mappings: dict[str, str] = {}  # entity_reference -> resolved_value
        # Start with the original formula
        resolved_formula = formula
        # Resolve collection functions (always, regardless of sensor config)
        resolved_formula = self._resolve_collection_functions(resolved_formula, sensor_config, eval_context, formula_config)
        # STEP 1: Resolve state.attribute references FIRST (before entity references)
        if sensor_config:
            resolved_formula = self._resolve_state_attribute_references(resolved_formula, sensor_config)
        # STEP 2: Pre-scan for variable.attribute patterns to identify variables that need entity ID preservation
        variables_needing_entity_ids = FormulaHelpers.identify_variables_for_attribute_access(resolved_formula, formula_config)
        # STEP 3: Resolve config variables with special handling for attribute access variables
        if formula_config:
            self._resolve_config_variables_with_attribute_preservation(
                eval_context, formula_config, variables_needing_entity_ids, sensor_config
            )
        # NOTE: Early metadata resolution disabled - timing issue with synthetic sensor creation
        # Metadata resolution needs to happen after synthetic sensors are created and available
        # STEP 4: Resolve variable.attribute references (e.g., device.battery_level)
        # This must happen BEFORE simple variable resolution to catch attribute patterns
        resolved_formula = VariableProcessors.resolve_attribute_chains(
            resolved_formula, eval_context, formula_config, self._dependency_handler
        )
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
        resolved_formula, simple_var_mappings, simple_ha_deps, simple_entity_mappings = (
            self._resolve_simple_variables_with_tracking(resolved_formula, eval_context, entity_mappings)
        )
        entity_to_value_mappings.update(simple_entity_mappings)
        entity_mappings.update(simple_var_mappings)
        # Only add dependencies that aren't already in the list
        for dep in simple_ha_deps:
            if dep not in unavailable_dependencies:
                unavailable_dependencies.append(dep)
        # STEP 8: Check for HA state values in the resolved formula
        ha_state_result = FormulaHelpers.detect_ha_state_in_formula(
            resolved_formula, unavailable_dependencies, entity_to_value_mappings
        )
        if ha_state_result:
            return ha_state_result  # type: ignore[no-any-return]
        # STEP 9: Continue with remaining resolution steps
        resolved_formula = VariableProcessors.resolve_variable_attribute_references(resolved_formula, eval_context)
        # Early return if no sensor config for the remaining steps
        if not sensor_config:
            _LOGGER.debug("Formula resolution (no sensor config): '%s' -> '%s'", formula, resolved_formula)
            return VariableResolutionResult(
                resolved_formula=resolved_formula,
                entity_to_value_mappings=entity_to_value_mappings if entity_to_value_mappings else None,
            )
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
        final_ha_state_result = FormulaHelpers.detect_ha_state_in_formula(
            resolved_formula, unavailable_dependencies, entity_to_value_mappings
        )
        if final_ha_state_result:
            return final_ha_state_result  # type: ignore[no-any-return]
        _LOGGER.debug("Formula resolution: '%s' -> '%s'", formula, resolved_formula)
        return VariableResolutionResult(
            resolved_formula=resolved_formula,
            entity_to_value_mappings=entity_to_value_mappings if entity_to_value_mappings else None,
        )

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
                raise MissingDependencyError(f"Error resolving attribute references in formula '{formula}': {e}") from e
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
            raise MissingDependencyError(f"Error resolving collection functions in formula '{formula}': {e}") from e

    def _resolve_metadata_functions(
        self,
        formula: str,
        sensor_config: SensorConfig | None,
        eval_context: dict[str, ContextValue],
        formula_config: FormulaConfig | None = None,
    ) -> str:
        """
        Resolve metadata() function calls early before variable resolution.
        This preserves entity references in metadata parameters while resolving
        the metadata calls to their actual values.
        Args:
            formula: Formula containing metadata() calls
            sensor_config: Current sensor configuration
            eval_context: Evaluation context
            formula_config: Formula-specific configuration
        Returns:
            Formula with metadata() calls resolved to actual values
        """
        # Pattern to match metadata function calls: metadata(param1, param2)
        metadata_pattern = re.compile(r"\bmetadata\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)")

        def resolve_metadata_call(match: re.Match[str]) -> str:
            entity_param = match.group(1).strip().strip("'\"")
            metadata_key = match.group(2).strip().strip("'\"")
            try:
                # Create metadata handler with proper HASS access
                metadata_handler = MetadataHandler(hass=self._hass)
                if not isinstance(metadata_handler, MetadataHandler):
                    raise ValueError("MetadataHandler not available")
                # Create minimal context for metadata resolution
                metadata_context: dict[str, ContextValue] = {}
                if sensor_config:
                    metadata_context["sensor_config"] = sensor_config  # type: ignore[assignment]
                if formula_config:
                    metadata_context["formula_config"] = formula_config  # type: ignore[assignment]
                if eval_context:
                    metadata_context["eval_context"] = eval_context
                # Reconstruct the metadata call formula and evaluate it
                metadata_formula = f"metadata({entity_param}, '{metadata_key}')"
                _LOGGER.debug(
                    "Early metadata: Calling handler.evaluate('%s') with context keys: %s",
                    metadata_formula,
                    list(eval_context.keys()) if eval_context else None,
                )
                result = metadata_handler.evaluate(metadata_formula, metadata_context)
                _LOGGER.debug("Early metadata resolution: metadata(%s, %s) -> %s", entity_param, metadata_key, result)
                return str(result)
            except Exception as e:
                _LOGGER.error("Error resolving metadata(%s, %s): %s", entity_param, metadata_key, e)
                _LOGGER.debug("eval_context contents: %s", eval_context)
                # Return original call if resolution fails - let normal evaluation handle the error
                return match.group(0)

        # Replace all metadata function calls with their resolved values
        resolved_formula = metadata_pattern.sub(resolve_metadata_call, formula)
        if resolved_formula != formula:
            _LOGGER.debug("Metadata function resolution: '%s' -> '%s'", formula, resolved_formula)
        return resolved_formula

    def resolve_config_variables(
        self,
        eval_context: dict[str, ContextValue],
        config: FormulaConfig | None,
        sensor_config: SensorConfig | None = None,
    ) -> None:
        """Resolve config variables using the resolver factory."""

        def resolver_callback(var_name: str, var_value: Any, context: dict[str, ContextValue], _sensor_cfg: Any) -> Any:
            resolved_value = self._resolver_factory.resolve_variable(var_name, var_value, context)
            # ARCHITECTURE FIX: Return ReferenceValue objects for entity references
            # This ensures consistency with the handler-based architecture
            if resolved_value is not None and isinstance(var_value, str):
                if isinstance(resolved_value, ReferenceValue):
                    return resolved_value
                # Wrap raw values in ReferenceValue objects using the entity ID as reference
                return ReferenceValue(reference=var_value, value=resolved_value)
            return resolved_value

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
                # Extract value from ReferenceValue if needed
                actual_value = resolved_value.value if isinstance(resolved_value, ReferenceValue) else resolved_value
                # Handle string concatenation properly
                if isinstance(actual_value, str):
                    return f'"{actual_value}"'  # Wrap strings in quotes for proper evaluation
                return str(actual_value)
            raise MissingDependencyError(f"Failed to resolve attribute reference '{attr_ref}' in formula")

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
                # Extract value from ReferenceValue for state resolution
                actual_value = resolved_value.value if isinstance(resolved_value, ReferenceValue) else resolved_value
                return str(actual_value)
            # This should not happen if StateResolver is working correctly
            raise MissingDependencyError("State token resolution returned None unexpectedly")

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
                value = eval_context[var_name]
                return str(value.value) if isinstance(value, ReferenceValue) else str(value)
            if entity_id in eval_context:
                value = eval_context[entity_id]
                return str(value.value) if isinstance(value, ReferenceValue) else str(value)
            # Use the resolver factory to resolve the entity reference
            resolved_value = self._resolver_factory.resolve_variable(entity_id, entity_id, eval_context)
            if resolved_value is not None:
                # Extract value from ReferenceValue for entity resolution
                actual_value = resolved_value.value if isinstance(resolved_value, ReferenceValue) else resolved_value
                return str(actual_value)
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
                # Extract value from ReferenceValue for cross-sensor resolution
                actual_value = resolved_value.value if isinstance(resolved_value, ReferenceValue) else resolved_value
                # Handle different data types appropriately
                if isinstance(actual_value, str):
                    return f'"{actual_value}"'  # Wrap strings in quotes
                return str(actual_value)
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
            # No hass available - this is a critical configuration error
            raise MissingDependencyError(
                "No Home Assistant instance available for domain validation. "
                "Entity resolution cannot proceed safely without domain validation."
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
                    # Extract value from ReferenceValue for formula substitution
                    actual_value = value.value if isinstance(value, ReferenceValue) else value
                    # Check if value is an HA state
                    if isinstance(actual_value, str) and is_ha_state_value(actual_value):
                        ha_dependencies.append(f"{var_name} ({entity_id}) is {actual_value}")
                    return str(actual_value)
            if entity_id in eval_context:
                value = eval_context[entity_id]
                # Only return the value if it's already resolved (not a raw entity ID)
                if value != entity_id:
                    entity_mappings[entity_id] = entity_id
                    # Extract value from ReferenceValue for formula substitution
                    actual_value = value.value if isinstance(value, ReferenceValue) else value
                    # Check if value is an HA state
                    if isinstance(actual_value, str) and is_ha_state_value(actual_value):
                        ha_dependencies.append(f"{entity_id} ({entity_id}) is {actual_value}")
                    return str(actual_value)
            # Use the resolver factory to resolve the entity reference
            resolved_value = self._resolver_factory.resolve_variable(entity_id, entity_id, eval_context)
            if resolved_value is not None:
                entity_mappings[entity_id] = entity_id
                # Extract value from ReferenceValue and check if it's an HA state
                actual_value = resolved_value.value if isinstance(resolved_value, ReferenceValue) else resolved_value
                if isinstance(actual_value, str) and is_ha_state_value(actual_value):
                    ha_dependencies.append(f"{entity_id} ({entity_id}) is {actual_value}")
                return str(actual_value)
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
        self._initialize_entity_registry(eval_context)
        hass = self._get_hass_instance()
        for var_name, var_value in config.variables.items():
            self._process_config_variable(var_name, var_value, eval_context, entity_mappings, ha_dependencies, config, hass)
        return entity_mappings, ha_dependencies

    def _initialize_entity_registry(self, eval_context: dict[str, ContextValue]) -> None:
        """Initialize entity registry in evaluation context."""
        entity_registry_key = "_entity_reference_registry"
        if entity_registry_key not in eval_context:
            eval_context[entity_registry_key] = {}
        _LOGGER.debug(
            "Config variable resolution starting. Context contents: %s", {k: str(v)[:100] for k, v in eval_context.items()}
        )

    def _get_hass_instance(self) -> Any:
        """Get Home Assistant instance from dependency handler."""
        return (
            getattr(self._dependency_handler, "hass", None)
            if hasattr(self, "_dependency_handler") and self._dependency_handler
            else None
        )

    def _process_config_variable(
        self,
        var_name: str,
        var_value: Any,
        eval_context: dict[str, ContextValue],
        entity_mappings: dict[str, str],
        ha_dependencies: list[str],
        config: FormulaConfig,
        hass: Any,
    ) -> None:
        """Process a single config variable."""
        # Track entity mapping if var_value looks like an entity ID
        if isinstance(var_value, str) and any(var_value.startswith(f"{domain}.") for domain in get_ha_domains(hass)):
            entity_mappings[var_name] = var_value
        # Check if this variable is already resolved
        if self._should_skip_variable(var_name, var_value, eval_context, entity_mappings, ha_dependencies):
            return
        # Resolve the variable
        self._resolve_and_track_variable(var_name, var_value, eval_context, entity_mappings, ha_dependencies, config)

    def _should_skip_variable(
        self,
        var_name: str,
        var_value: Any,
        eval_context: dict[str, ContextValue],
        entity_mappings: dict[str, str],
        ha_dependencies: list[str],
    ) -> bool:
        """Check if variable should be skipped because it's already resolved."""
        entity_registry_key = "_entity_reference_registry"
        if var_name not in eval_context or var_name == entity_registry_key:
            return False
        existing_value = eval_context[var_name]
        # If the existing value is the same as var_value (raw entity ID), we need to resolve it
        if existing_value == var_value and isinstance(var_value, str):
            _LOGGER.debug("Config variable %s has raw entity ID value %s, needs resolution", var_name, var_value)
            return False
        if existing_value != var_value:
            # Already resolved to a different value, check if it's an HA state
            if isinstance(existing_value, str) and is_ha_state_value(existing_value):
                entity_id = entity_mappings.get(var_name, var_value if isinstance(var_value, str) else "unknown")
                ha_dependencies.append(f"{var_name} ({entity_id}) is {existing_value}")
            _LOGGER.debug("Skipping config variable %s (already resolved to %s)", var_name, existing_value)
            return True
        return False

    def _resolve_and_track_variable(
        self,
        var_name: str,
        var_value: Any,
        eval_context: dict[str, ContextValue],
        entity_mappings: dict[str, str],
        ha_dependencies: list[str],
        config: FormulaConfig,
    ) -> None:
        """Resolve variable and track its state."""
        try:
            resolved_value = self._resolver_factory.resolve_variable(var_name, var_value, eval_context)
            if resolved_value is not None:
                # Use centralized ReferenceValueManager for type safety
                ResolutionHelpers.log_and_set_resolved_variable(
                    eval_context, var_name, var_value, resolved_value, "VARIABLE_RESOLUTION"
                )
                # Check if resolved value is an HA state
                if isinstance(resolved_value, str) and is_ha_state_value(resolved_value):
                    entity_id_for_tracking = entity_mappings.get(
                        var_name, var_value if isinstance(var_value, str) else "unknown"
                    )
                    ha_dependencies.append(f"{var_name} ({entity_id_for_tracking}) is {resolved_value}")
            else:
                _LOGGER.debug(
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
            raise MissingDependencyError(f"Error resolving config variable {var_name}: {err}") from err

    def _resolve_simple_variables_with_tracking(
        self, formula: str, eval_context: dict[str, ContextValue], existing_mappings: dict[str, str]
    ) -> tuple[str, dict[str, str], list[str], dict[str, str]]:
        """Resolve simple variable references with first-class EntityReference support."""
        # NEW APPROACH: Don't extract values from ReferenceValue objects
        # Keep the original variable names in the formula and let handlers access ReferenceValue objects from context
        # Same negative look-ahead to avoid variable.attribute premature resolution
        variable_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)(?!\.)\b")
        entity_mappings: dict[str, str] = {}
        ha_dependencies: list[str] = []

        def validate_variable_ref(match: re.Match[str]) -> str:
            var_name = match.group(1)
            # Skip reserved words and function names
            if is_reserved_word(var_name):
                return var_name

            # Check if this variable exists in the evaluation context
            if var_name in eval_context:
                context_value = eval_context[var_name]
                # Handle ReferenceValue objects (universal reference/value pairs)
                if isinstance(context_value, ReferenceValue):
                    ref_value: ReferenceValue = context_value
                    value = ref_value.value
                    reference = ref_value.reference
                    _LOGGER.debug(
                        "Validated ReferenceValue %s: reference=%s, value=%s (keeping variable name in formula)",
                        var_name,
                        reference,
                        value,
                    )
                    # Track dependencies for HA states
                    if isinstance(value, str) and is_ha_state_value(value):
                        entity_id = reference if "." in reference else existing_mappings.get(var_name, reference)
                        ha_dependencies.append(f"{var_name} ({entity_id}) is {value}")
                        entity_mappings[var_name] = entity_id

                    # NEW APPROACH: Keep the variable name in the formula
                    # Handlers will access the ReferenceValue objects from context
                    return var_name

                # Handle regular values (backward compatibility)
                value = context_value if isinstance(context_value, str | int | float | None) else str(context_value)
                # Check if value is an HA state
                if isinstance(value, str) and is_ha_state_value(value):
                    entity_id = existing_mappings.get(var_name, "unknown")
                    ha_dependencies.append(f"{var_name} ({entity_id}) is {value}")
                    entity_mappings[var_name] = entity_id

                # NEW APPROACH: Keep the variable name in the formula
                return var_name

            # Variable not found in context - this will be handled by the evaluator as a missing dependency
            return var_name

        # NEW APPROACH: Don't modify the formula, just validate variables exist
        # The original formula is returned unchanged, handlers get values from context
        validated_formula = variable_pattern.sub(validate_variable_ref, formula)

        # Return empty entity_to_value_mappings since we're not doing substitution anymore
        return validated_formula, entity_mappings, ha_dependencies, {}

    def _resolve_config_variables_with_attribute_preservation(
        self,
        eval_context: dict[str, ContextValue],
        formula_config: FormulaConfig,
        variables_needing_entity_ids: set[str],
        sensor_config: SensorConfig | None = None,
    ) -> None:
        """Resolve config variables with special handling for variables used in .attribute patterns.
        Also implements variable inheritance for attribute formulas:
        - Global variables (if available)
        - Parent sensor variables (from main sensor formula)
        - Attribute-specific variables (highest precedence)
        """
        # Inheritance handler is now always initialized, no need to check for None
        # Get all variables to process (inherited + formula-specific)
        inherited_variables = self._inheritance_handler.build_inherited_variables(formula_config, sensor_config)
        # Process each variable
        for var_name, var_value in inherited_variables.items():
            self._inheritance_handler.process_single_variable(
                var_name, var_value, eval_context, formula_config, variables_needing_entity_ids, self._resolver_factory
            )
