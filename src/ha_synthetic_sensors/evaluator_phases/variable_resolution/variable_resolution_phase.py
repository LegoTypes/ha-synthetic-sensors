"""Variable resolution phase for synthetic sensor formulas."""

from collections.abc import Callable
import logging
import re
from typing import Any

from homeassistant.const import STATE_UNKNOWN

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.constants_alternate import identify_alternate_state_value
from ha_synthetic_sensors.constants_formula import is_reserved_word
from ha_synthetic_sensors.evaluator_handlers.metadata_handler import MetadataHandler
from ha_synthetic_sensors.exceptions import DataValidationError, MissingDependencyError
from ha_synthetic_sensors.shared_constants import get_ha_domains
from ha_synthetic_sensors.type_definitions import ContextValue, DataProviderResult, ReferenceValue
from ha_synthetic_sensors.utils_config import resolve_config_variables

from .attribute_reference_resolver import AttributeReferenceResolver
from .formula_helpers import FormulaHelpers
from .resolution_helpers import ResolutionHelpers
from .resolution_types import HADependency, VariableResolutionResult
from .resolver_factory import VariableResolverFactory
from .variable_inheritance import VariableInheritanceHandler
from .variable_processors import VariableProcessors

_LOGGER = logging.getLogger(__name__)


class VariableResolutionPhase:
    """Variable Resolution Engine - Phase 1: Variable Resolution (compiler-like evaluation)."""

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
        # Update the data provider callback on the existing factory instead of recreating it
        if hasattr(dependency_handler, "data_provider_callback"):
            current_data_provider = dependency_handler.data_provider_callback
            # Update the existing resolver factory's data provider callback
            self._resolver_factory.update_data_provider_callback(current_data_provider)

    def update_data_provider_callback(self, data_provider_callback: Callable[[str], DataProviderResult] | None) -> None:
        """Update the data provider callback for the StateResolver."""
        # Update the existing resolver factory instead of recreating it
        self._resolver_factory.update_data_provider_callback(data_provider_callback)

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
        # Initialize tracking variables and perform initial resolution
        entity_mappings, unavailable_dependencies, entity_to_value_mappings, resolved_formula = (
            self._initialize_resolution_tracking(formula, sensor_config, eval_context, formula_config)
        )
        # Perform main resolution steps
        resolved_formula = self._perform_main_resolution_steps(
            resolved_formula,
            sensor_config,
            eval_context,
            formula_config,
            entity_mappings,
            unavailable_dependencies,
            entity_to_value_mappings,
        )
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
        # Merge dependency hints without per-item duplication checks
        if simple_ha_deps:
            unavailable_dependencies = list({*unavailable_dependencies, *simple_ha_deps})
        # STEP 8: Continue with remaining resolution steps
        resolved_formula = VariableProcessors.resolve_variable_attribute_references(resolved_formula, eval_context)

        # STEP 8.5: Resolve entity references even without sensor config
        # This is needed for formulas like "switch.test + 1" to work in tests and simple evaluations
        resolved_formula, entity_mappings_from_entities, ha_deps_from_entities = self._resolve_entity_references_with_tracking(
            resolved_formula, eval_context, sensor_config
        )
        # Collect dependencies from entity resolution
        unavailable_dependencies.extend(ha_deps_from_entities)
        entity_to_value_mappings.update(entity_mappings_from_entities)

        # Early return if no sensor config for the remaining steps
        if not sensor_config:
            # NOTE: Most advanced resolution features are skipped for formulas without sensor config
            # to avoid breaking the cache mechanism. Entity reference resolution is now done above.
            _LOGGER.debug("Formula resolution (no sensor config): '%s' -> '%s'", formula, resolved_formula)
            # Still check for HA state values even without sensor config
            ha_state_result = FormulaHelpers.detect_ha_state_in_formula(
                resolved_formula, unavailable_dependencies, entity_to_value_mappings
            )
            if ha_state_result:
                return ha_state_result  # type: ignore[no-any-return]
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
        resolved_formula, ha_deps_from_state = self._resolve_state_references(resolved_formula, sensor_config, extended_context)
        # Collect dependencies from state resolution
        unavailable_dependencies.extend(ha_deps_from_state)

        # CRITICAL FIX: Copy resolved variables back to the original eval_context
        # The _resolve_state_references method adds resolved variables to extended_context,
        # but we need these in the original eval_context for the main evaluator
        for key, value in extended_context.items():
            if key not in eval_context and key not in ["sensor_config", "formula_config"]:
                eval_context[key] = value
        # STEP 11: Resolve cross-sensor references
        resolved_formula = self._resolve_cross_sensor_references(resolved_formula, eval_context, sensor_config, formula_config)

        # Phase 2: Metadata Processing is handled by CoreFormulaEvaluator
        # Metadata functions are detected and handled by MetadataHandler in CoreFormulaEvaluator.

        # Entity reference resolution has already been done in STEP 8.5 above
        # No need to do it again here

        # Note: Phase 3 (Value Resolution) now happens in CoreFormulaEvaluator
        # before enhanced SimpleEval to keep it common across all formula types

        # Check for HA state values in the fully resolved formula
        ha_state_result = FormulaHelpers.detect_ha_state_in_formula(
            resolved_formula, unavailable_dependencies, entity_to_value_mappings
        )
        if ha_state_result:
            return ha_state_result  # type: ignore[no-any-return]
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
        Resolve metadata() function calls using the shared MetadataHandler.
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
        # Use the shared metadata processing method
        try:
            # Ensure _hass is available in the context for MetadataHandler
            metadata_context = eval_context.copy()
            if self._hass and "_hass" not in metadata_context:
                metadata_context["_hass"] = self._hass

            # Use the shared MetadataHandler.process_metadata_functions method
            resolved_formula = MetadataHandler.process_metadata_functions(formula, metadata_context)
            if resolved_formula != formula:
                _LOGGER.debug("Metadata function resolution: '%s' -> '%s'", formula, resolved_formula)
            return resolved_formula
        except Exception as e:
            _LOGGER.debug("Metadata function resolution failed: %s", e)
            # Return original formula if resolution fails - let normal evaluation handle the error
            return formula

    def resolve_config_variables(
        self,
        eval_context: dict[str, ContextValue],
        config: FormulaConfig | None,
        sensor_config: SensorConfig | None = None,
    ) -> None:
        """Resolve config variables using the resolver factory."""

        def resolver_callback(var_name: str, var_value: Any, context: dict[str, ContextValue], _sensor_cfg: Any) -> Any:
            resolved_value = self._resolver_factory.resolve_variable(var_name, var_value, context)
            # ARCHITECTURE FIX: Always return ReferenceValue objects
            # This ensures consistency with the handler-based architecture
            if isinstance(resolved_value, ReferenceValue):
                return resolved_value

            if isinstance(var_value, str):
                # Wrap raw values in ReferenceValue objects using the entity ID as reference
                return ReferenceValue(reference=var_value, value=resolved_value)

            # For non-string values (literals), use the variable name as reference
            return ReferenceValue(reference=var_name, value=resolved_value)

        resolve_config_variables(eval_context, config, resolver_callback, sensor_config)

    def _resolve_state_attribute_references(self, formula: str, sensor_config: SensorConfig) -> str:
        """Resolve state.attribute references.

        For main formulas and attributes that reference backing entity attributes
        (state.xxx or state.attributes.xxx), resolve to concrete values using the
        current data provider and sensor_to_backing mapping.
        """
        try:
            mapping = getattr(self._resolver_factory, "sensor_to_backing_mapping", {}) or {}
            data_provider = getattr(self._resolver_factory, "data_provider_callback", None)
            backing_entity_id = mapping.get(sensor_config.unique_id)
            if not backing_entity_id or not callable(data_provider):
                return formula

            entity_data = data_provider(backing_entity_id)
            if not (entity_data and entity_data.get("exists")):
                return formula

            attributes = entity_data.get("attributes", {}) or {}

            # Replace state.attributes.some.path first (deep access)
            def replace_state_attributes(match: re.Match[str]) -> str:
                path = match.group(1)
                current: Any = attributes
                for part in path.split("."):
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        return match.group(0)
                return str(current)

            pattern_deep = re.compile(r"\bstate\.attributes\.([a-zA-Z0-9_.]+)\b")
            new_formula = pattern_deep.sub(replace_state_attributes, formula)

            # Replace simple state.attribute (single-level)
            def replace_state_simple(match: re.Match[str]) -> str:
                attr = match.group(1)
                if isinstance(attributes, dict) and attr in attributes:
                    return str(attributes[attr])
                return match.group(0)

            pattern_simple = re.compile(r"\bstate\.([a-zA-Z0-9_]+)\b")
            new_formula = pattern_simple.sub(replace_state_simple, new_formula)

            return new_formula
        except Exception:
            return formula

    def _resolve_state_references(
        self, formula: str, sensor_config: SensorConfig, eval_context: dict[str, ContextValue]
    ) -> tuple[str, list[HADependency]]:
        """Resolve standalone 'state' references - Phase 1: Variable Resolution builds ReferenceValue in context only."""
        ha_dependencies: list[HADependency] = []

        if "state" not in formula:
            return formula, ha_dependencies

        # Skip state resolution if state tokens are only inside metadata function parameters
        if self._state_tokens_only_in_metadata_functions(formula):
            return formula, ha_dependencies

        # Phase 1: Variable Resolution - Build ReferenceValue in context without formula substitution
        # Use the resolver factory to resolve the state reference and store in context
        resolved_value = self._resolver_factory.resolve_variable("state", "state", eval_context)
        if resolved_value is not None:
            # Store ReferenceValue in context for later phases
            eval_context["state"] = resolved_value

            # Check if the resolved state value is None (backing entity offline)
            actual_value = resolved_value.value if isinstance(resolved_value, ReferenceValue) else resolved_value
            if actual_value is None:
                # Get the backing entity ID for better dependency reporting
                backing_entity_id = "unknown"
                if isinstance(resolved_value, ReferenceValue):
                    backing_entity_id = resolved_value.reference
                ha_dependencies.append(HADependency(var="state", entity_id=backing_entity_id, state="unknown"))
                _LOGGER.debug("State resolver: detected None value for state, adding unknown dependency")
        else:
            # This should not happen if StateResolver is working correctly
            raise MissingDependencyError("State token resolution returned None unexpectedly")

        # Return formula unchanged - no substitution in Phase 1 (Variable Resolution)
        return formula, ha_dependencies

    def _state_tokens_only_in_metadata_functions(self, formula: str) -> bool:
        """Check if all 'state' tokens in the formula are inside metadata function parameters."""
        # Get all protected ranges for metadata function parameters
        protected_ranges = FormulaHelpers.find_metadata_function_parameter_ranges(formula)

        # Find all 'state' token positions in the formula using regex for proper word boundaries
        state_pattern = re.compile(r"\bstate\b")
        state_positions = [match.start() for match in state_pattern.finditer(formula)]

        # Check if all state positions are within protected ranges
        for state_pos in state_positions:
            is_protected = False
            for start_range, end_range in protected_ranges:
                if start_range <= state_pos < end_range:
                    is_protected = True
                    break
            if not is_protected:
                return False  # Found a state token outside metadata functions

        return True  # All state tokens are inside metadata functions

    def _resolve_entity_references(self, formula: str, eval_context: dict[str, ContextValue]) -> str:
        """Register entity references in context without modifying the formula (lazy resolution)."""
        # Pattern that explicitly prevents matching decimals by requiring word boundary at start and letter/underscore
        entity_pattern = re.compile(
            r"(?:^|(?<=\s)|(?<=\()|(?<=[+\-*/]))([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z0-9_.]+)(?=\s|$|[+\-*/)])"
        )

        def register_entity_ref(match: re.Match[str]) -> str:
            entity_id = match.group(1)
            var_name = entity_id.replace(".", "_").replace("-", "_")

            # Check if already resolved in context
            if var_name in eval_context or entity_id in eval_context:
                return match.group(0)  # Return original match unchanged

            # Use the resolver factory to resolve and register the entity reference
            try:
                resolved_value = self._resolver_factory.resolve_variable(entity_id, entity_id, eval_context)
                if resolved_value is not None:
                    # Store ReferenceValue in context for handlers (including None values)
                    eval_context[var_name] = resolved_value
                    eval_context[entity_id] = resolved_value
                    _LOGGER.debug("Registered entity reference '%s' in context for lazy resolution", entity_id)
            except MissingDependencyError:
                # Let the missing dependency be handled by later phases
                _LOGGER.debug("Entity reference '%s' could not be resolved, will be handled by later phases", entity_id)

            return match.group(0)  # Return original entity reference unchanged

        # Process matches but don't modify the formula string
        entity_pattern.sub(register_entity_ref, formula)

        # Return formula unchanged - let Phase 3 handle value extraction
        return formula

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
            # Phase 1: Variable Resolution - Only build ReferenceValues in context, do NOT substitute values into formula
            # Use the resolver factory to resolve cross-sensor references and add to context
            resolved_value = self._resolver_factory.resolve_variable(sensor_name, sensor_name, eval_context)
            if resolved_value is not None:
                # ReferenceValue is already in context - do NOT substitute into formula
                # Return the variable name unchanged for Phase 2 (metadata) processing
                return sensor_name
            # Check if this is a cross-sensor reference
            if self._sensor_registry_phase and self._sensor_registry_phase.is_sensor_registered(sensor_name):
                sensor_value = self._sensor_registry_phase.get_sensor_value(sensor_name)
                if sensor_value is not None:
                    # Phase 1: Variable Resolution - Do NOT substitute values; preserve names for metadata processing
                    return sensor_name
            # Not a cross-sensor reference, return as-is
            return sensor_name

        return sensor_pattern.sub(replace_sensor_ref, formula)

    def _resolve_simple_variables(self, formula: str, eval_context: dict[str, ContextValue]) -> str:
        """Resolve simple variable references from the evaluation context - Phase 1: Variable Resolution (only build context)."""
        # In Phase 1, we validate variables exist in context but don't substitute values
        # The actual substitution happens in Phase 3
        variable_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)(?!\.)\b")

        def validate_variable_ref(match: re.Match[str]) -> str:
            var_name = match.group(1)
            # Skip reserved words and function names
            if is_reserved_word(var_name):
                return var_name

            # Check if this variable exists in the evaluation context
            if var_name in eval_context:
                # Variable exists - keep the name in formula for lazy evaluation
                return var_name

            # Variable not found in context - this will be handled by the evaluator as a missing dependency
            return var_name

        # Validate variables exist but don't substitute - keep original formula structure
        return variable_pattern.sub(validate_variable_ref, formula)

    def _replace_variable_ref(self, match: re.Match[str], eval_context: dict[str, ContextValue]) -> str:
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
            # Convert Python None to "unknown" for HA state detection
            if value is None:
                return "unknown"
            return str(value)
        # Not a variable, return as-is
        return var_name

    def _process_resolved_entity_value(
        self, value: Any, var_name: str, entity_id: str, ha_dependencies: list[HADependency]
    ) -> str:
        """Process a resolved entity value and track HA state dependencies.

        Args:
            value: The resolved value (could be ReferenceValue or raw value)
            var_name: Variable name for dependency tracking
            entity_id: Entity ID for dependency tracking
            ha_dependencies: List to append dependencies to

        Returns:
            String representation of the value for formula substitution
        """
        # Extract value from ReferenceValue for formula substitution
        actual_value = value.value if isinstance(value, ReferenceValue) else value

        # Check for Python None values (backing entities offline)
        if actual_value is None:
            ha_dependencies.append(HADependency(var=var_name, entity_id=entity_id, state="unknown"))
            return "unknown"

        # Check if value is an HA state
        if isinstance(actual_value, str):
            alt_state = identify_alternate_state_value(actual_value)
            if isinstance(alt_state, str):
                ha_dependencies.append(HADependency(var=var_name, entity_id=entity_id, state=str(actual_value)))
                return str(actual_value)

        return str(actual_value)

    def _replace_entity_reference(
        self,
        match: re.Match[str],
        eval_context: dict[str, ContextValue],
        sensor_config: SensorConfig | None,
        entity_mappings: dict[str, str],
        ha_dependencies: list[HADependency],
    ) -> str:
        """Replace a single entity reference with its resolved value."""
        domain = match.group(1)
        entity_name = match.group(2)
        entity_id = f"{domain}.{entity_name}"
        _LOGGER.debug("Entity reference match: domain='%s', entity_name='%s', entity_id='%s'", domain, entity_name, entity_id)

        # Check if this entity reference is already defined as a variable in the formula config
        # If so, leave it as is to avoid conflicts with variable resolution
        if sensor_config and sensor_config.formulas:
            for formula_config in sensor_config.formulas:
                if formula_config.variables:
                    for var_value in formula_config.variables.items():
                        if isinstance(var_value, str) and var_value == entity_id:
                            return entity_id

        # First check if already resolved in context (try variable name)
        var_name = entity_id.replace(".", "_").replace("-", "_")
        if var_name in eval_context:
            value = eval_context[var_name]
            # Only return the variable name if it's already resolved (not a raw entity ID)
            if value != entity_id:
                entity_mappings[var_name] = entity_id
                # Process the value for dependency tracking but return the variable name for substitution
                self._process_resolved_entity_value(value, var_name, entity_id, ha_dependencies)
                return var_name

        # Check if already resolved in context (try entity ID directly)
        if entity_id in eval_context:
            value = eval_context[entity_id]
            # Only return the variable name if it's already resolved (not a raw entity ID)
            if value != entity_id:
                entity_mappings[entity_id] = entity_id
                # Process the value for dependency tracking but return the variable name for substitution
                self._process_resolved_entity_value(value, entity_id, entity_id, ha_dependencies)
                return var_name

        # Use the resolver factory to resolve the entity reference
        resolved_value = self._resolver_factory.resolve_variable(entity_id, entity_id, eval_context)
        if resolved_value is not None:
            entity_mappings[entity_id] = entity_id
            # Process the value for dependency tracking but return the variable name for substitution
            self._process_resolved_entity_value(resolved_value, entity_id, entity_id, ha_dependencies)
            return var_name

        raise MissingDependencyError(f"Failed to resolve entity reference '{entity_id}' in formula")

    def _resolve_entity_references_with_tracking(
        self, formula: str, eval_context: dict[str, ContextValue], sensor_config: SensorConfig | None = None
    ) -> tuple[str, dict[str, str], list[HADependency]]:
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
        if hass is None:
            # No hass available - this is a critical configuration error
            raise MissingDependencyError(
                "No Home Assistant instance available for domain validation. "
                "Entity resolution cannot proceed safely without domain validation."
            )
        entity_pattern = self._get_entity_pattern_from_hass(hass)
        entity_mappings: dict[str, str] = {}
        ha_dependencies: list[HADependency] = []

        def replace_entity_ref(match: re.Match[str]) -> str:
            return self._replace_entity_reference(match, eval_context, sensor_config, entity_mappings, ha_dependencies)

        _LOGGER.debug("Resolving entity references in formula: '%s'", formula)
        had_entity_tokens = entity_pattern.search(formula) is not None
        _LOGGER.debug("DEBUG: Before substitution, formula='%s'", formula)
        resolved_formula = entity_pattern.sub(replace_entity_ref, formula)
        _LOGGER.debug("DEBUG: After substitution, formula='%s'", resolved_formula)
        if had_entity_tokens and resolved_formula == formula:
            try:
                context_keys = list(eval_context.keys())
            except Exception:
                context_keys = []
            _LOGGER.debug(
                "ENTITY_SUBSTITUTION_NOOP: entity tokens detected but no substitution occurred. formula='%s' context_keys_sample=%s",
                formula,
                context_keys[:10],
            )
        return resolved_formula, entity_mappings, ha_dependencies

    def _has_entity_references(self, formula: str) -> bool:
        """Check if a formula contains entity references (e.g., sensor.test, binary_sensor.door)."""
        # Simple check for domain.entity_name pattern
        entity_pattern = re.compile(r"\b[a-z_]+\.[a-z0-9_]+\b")
        return entity_pattern.search(formula) is not None

    def _get_entity_pattern_from_hass(self, hass: Any) -> re.Pattern[str]:
        """Build an entity regex pattern from Home Assistant domains or raise clear errors."""
        try:
            domains = get_ha_domains(hass)
            if not domains:
                raise DataValidationError(
                    "No entity domains available from Home Assistant registry. "
                    "This indicates a configuration or initialization problem. "
                    "Entity resolution cannot proceed safely without domain validation."
                )
            entity_domains = "|".join(sorted(domains))
            entity_pattern = re.compile(rf"\b({entity_domains})\.([a-zA-Z0-9_]+)\b")
            _LOGGER.debug("Using hass-based entity pattern with %d domains: %s", len(domains), entity_pattern.pattern)
            return entity_pattern
        except DataValidationError:
            raise
        except Exception as e:  # pragma: no cover - defensive error mapping
            raise DataValidationError(
                f"Failed to get entity domains from Home Assistant: {e}. "
                "Entity resolution cannot proceed safely without domain validation."
            ) from e

    def _track_entities_and_register_context(
        self, resolved_formula: str, eval_context: dict[str, ContextValue]
    ) -> tuple[dict[str, str], list[HADependency]]:
        """Track entity references and pre-register dotted entities into context.

        Returns entity mappings and HA dependency messages.
        """
        entity_mappings_from_entities: dict[str, str] = {}
        ha_deps_from_entities: list[HADependency] = []
        # Perform tracking without substituting values into the formula
        _, entity_mappings_from_entities, ha_deps_from_entities = self._resolve_entity_references_with_tracking(
            resolved_formula, eval_context, None
        )

        # Additionally, pre-register dotted entity references found in the formula into context
        hass = self._get_hass_instance()
        if hass is None:
            return entity_mappings_from_entities, ha_deps_from_entities
        try:
            domains = get_ha_domains(hass)
            if not domains:
                return entity_mappings_from_entities, ha_deps_from_entities
            entity_domains = "|".join(sorted(domains))
            entity_pattern_ctx = re.compile(rf"\b({entity_domains})\.([a-zA-Z0-9_]+)\b")
            for match in entity_pattern_ctx.finditer(resolved_formula):
                entity_id = f"{match.group(1)}.{match.group(2)}"
                var_name = entity_id.replace(".", "_").replace("-", "_")
                if var_name in eval_context:
                    continue
                resolved_value = self._resolver_factory.resolve_variable(entity_id, entity_id, eval_context)
                if resolved_value is None:
                    continue
                ResolutionHelpers.log_and_set_resolved_variable(
                    eval_context, var_name, entity_id, resolved_value, "ENTITY_REFERENCE_CONTEXT"
                )
        except Exception as err:
            # Best effort; context pre-registration is optional
            _LOGGER.debug("ENTITY_CONTEXT_PREFILL_SKIP: %s", err)
        return entity_mappings_from_entities, ha_deps_from_entities

    def _resolve_config_variables_with_tracking(
        self, eval_context: dict[str, ContextValue], config: FormulaConfig, sensor_config: SensorConfig | None = None
    ) -> tuple[dict[str, str], list[HADependency]]:
        """Resolve config variables and track entity mappings and HA states."""
        entity_mappings: dict[str, str] = {}
        ha_dependencies: list[HADependency] = []
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
        ha_dependencies: list[HADependency],
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
        ha_dependencies: list[HADependency],
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
            if existing_value is None:
                entity_id = entity_mappings.get(var_name, var_value if isinstance(var_value, str) else "unknown")
                ha_dependencies.append(HADependency(var=var_name, entity_id=entity_id, state="unknown"))
            elif isinstance(existing_value, str):
                alt_state = identify_alternate_state_value(existing_value)
                if isinstance(alt_state, str):
                    entity_id = entity_mappings.get(var_name, var_value if isinstance(var_value, str) else "unknown")
                    ha_dependencies.append(HADependency(var=var_name, entity_id=entity_id, state=str(existing_value)))
            _LOGGER.debug("Skipping config variable %s (already resolved to %s)", var_name, existing_value)
            return True
        return False

    def _resolve_and_track_variable(
        self,
        var_name: str,
        var_value: Any,
        eval_context: dict[str, ContextValue],
        entity_mappings: dict[str, str],
        ha_dependencies: list[HADependency],
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
                # Check if resolved value is an HA state (extract from ReferenceValue if needed)
                actual_resolved_value = resolved_value.value if isinstance(resolved_value, ReferenceValue) else resolved_value
                if actual_resolved_value is None:
                    entity_id_for_tracking = entity_mappings.get(
                        var_name, var_value if isinstance(var_value, str) else STATE_UNKNOWN
                    )
                    ha_dependencies.append(HADependency(var=var_name, entity_id=entity_id_for_tracking, state="unknown"))
                elif isinstance(actual_resolved_value, str):
                    alt_state = identify_alternate_state_value(actual_resolved_value)
                    if isinstance(alt_state, str):
                        entity_id_for_tracking = entity_mappings.get(
                            var_name, var_value if isinstance(var_value, str) else STATE_UNKNOWN
                        )
                        ha_dependencies.append(
                            HADependency(var=var_name, entity_id=entity_id_for_tracking, state=str(actual_resolved_value))
                        )
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
    ) -> tuple[str, dict[str, str], list[HADependency], dict[str, str]]:
        """Resolve simple variable references with first-class EntityReference support."""
        # Don't extract values from ReferenceValue objects
        # Keep the original variable names in the formula and let handlers access ReferenceValue objects from context
        # Same negative look-ahead to avoid variable.attribute premature resolution
        variable_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)(?!\.)\b")
        entity_mappings: dict[str, str] = {}
        ha_dependencies: list[HADependency] = []

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
                    if value is None:
                        entity_id = reference if "." in reference else existing_mappings.get(var_name, reference)
                        ha_dependencies.append(HADependency(var=var_name, entity_id=entity_id, state="unknown"))
                        entity_mappings[var_name] = entity_id
                    elif isinstance(value, str):
                        alt_state = identify_alternate_state_value(value)
                        if isinstance(alt_state, str):
                            entity_id = reference if "." in reference else existing_mappings.get(var_name, reference)
                            ha_dependencies.append(HADependency(var=var_name, entity_id=entity_id, state=str(value)))
                            entity_mappings[var_name] = entity_id

                    # Keep the variable name in the formula
                    # Handlers will access the ReferenceValue objects from context
                    return var_name

                # Handle regular values (backward compatibility)
                value = context_value if isinstance(context_value, str | int | float | None) else str(context_value)
                # Check if value is an HA state
                if value is None:
                    entity_id = existing_mappings.get(var_name, "unknown")
                    ha_dependencies.append(HADependency(var=var_name, entity_id=entity_id, state="unknown"))
                    entity_mappings[var_name] = entity_id
                elif isinstance(value, str):
                    alt_state = identify_alternate_state_value(value)
                    if isinstance(alt_state, str):
                        entity_id = existing_mappings.get(var_name, "unknown")
                        ha_dependencies.append(HADependency(var=var_name, entity_id=entity_id, state=str(value)))
                        entity_mappings[var_name] = entity_id

                # Keep the variable name in the formula
                return var_name

            # Variable not found in context - this will be handled by the evaluator as a missing dependency
            return var_name

        # Don't modify the formula, just validate variables exist
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

    def _initialize_resolution_tracking(
        self,
        formula: str,
        sensor_config: SensorConfig | None,
        eval_context: dict[str, ContextValue],
        formula_config: FormulaConfig | None,
    ) -> tuple[dict[str, str], list[HADependency], dict[str, str], str]:
        """Initialize tracking variables and perform initial resolution steps."""
        # Track entity mappings for enhanced dependency reporting
        entity_mappings: dict[str, str] = {}  # variable_name -> entity_id
        unavailable_dependencies: list[HADependency] = []
        entity_to_value_mappings: dict[str, str] = {}  # entity_reference -> resolved_value
        # Start with the original formula
        resolved_formula = formula
        # Resolve collection functions (always, regardless of sensor config)
        resolved_formula = self._resolve_collection_functions(resolved_formula, sensor_config, eval_context, formula_config)
        return entity_mappings, unavailable_dependencies, entity_to_value_mappings, resolved_formula

    def _perform_main_resolution_steps(
        self,
        resolved_formula: str,
        sensor_config: SensorConfig | None,
        eval_context: dict[str, ContextValue],
        formula_config: FormulaConfig | None,
        entity_mappings: dict[str, str],
        unavailable_dependencies: list[HADependency],
        entity_to_value_mappings: dict[str, str],
    ) -> str:
        """Perform the main resolution steps for variables and entities."""
        # Phase 1: Variable Resolution - build ReferenceValues in context (no value extraction yet)
        # Phase 2: Metadata Processing - process metadata() functions with ReferenceValues
        # Phase 3: Value Resolution - extract values from ReferenceValues for formula evaluation
        # Phase 4: Formula Evaluation - handled by CoreFormulaEvaluator

        # STEP 1: Resolve state.attribute references FIRST (before entity references)
        if sensor_config:
            resolved_formula = self._resolve_state_attribute_references(resolved_formula, sensor_config)
        # STEP 2: Pre-scan for variable.attribute patterns to identify variables that need entity ID preservation
        variables_needing_entity_ids = FormulaHelpers.identify_variables_for_attribute_access(resolved_formula, formula_config)
        # STEP 3: Resolve config variables with special handling for attribute access variables
        if formula_config:
            # First do the attribute preservation (no tracking)
            self._resolve_config_variables_with_attribute_preservation(
                eval_context, formula_config, variables_needing_entity_ids, sensor_config
            )
            # Then do tracking for dependency collection
            entity_mappings_from_config, ha_deps_from_config = self._resolve_config_variables_with_tracking(
                eval_context, formula_config, sensor_config
            )
            # Collect dependencies from config variable resolution
            unavailable_dependencies.extend(ha_deps_from_config)
            entity_to_value_mappings.update(entity_mappings_from_config)
        # STEP 4: Resolve variable.attribute references (e.g., device.battery_level)
        # This must happen BEFORE simple variable resolution to catch attribute patterns
        resolved_formula = VariableProcessors.resolve_attribute_chains(
            resolved_formula, eval_context, formula_config, self._dependency_handler
        )
        # STEP 5: Resolve entity references and track mappings and HA states (context-only)
        # New behavior: register ReferenceValues for dotted entity references without substituting into formula.
        # This preserves lazy resolution and allows metadata() to access original references in Phase 2.
        try:
            entity_mappings_from_entities, ha_deps_from_entities = self._track_entities_and_register_context(
                resolved_formula, eval_context
            )
        except Exception:
            entity_mappings_from_entities = {}
            ha_deps_from_entities = []
        entity_mappings.update(entity_mappings_from_entities)
        unavailable_dependencies.extend(ha_deps_from_entities)
        return resolved_formula
