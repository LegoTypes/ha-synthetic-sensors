"""Context building phase for compiler-like formula evaluation."""

import logging
from typing import Any

from ...config_models import FormulaConfig, SensorConfig
from ...exceptions import DataValidationError, MissingDependencyError
from ...hierarchical_context_dict import HierarchicalContextDict
from ...reference_value_manager import ReferenceValueManager
from ...shared_constants import get_ha_domains
from ...type_definitions import ContextValue, DataProviderCallback, ReferenceValue
from ...utils_config import resolve_config_variables
from ..variable_resolution.resolver_factory import VariableResolverFactory

# ARCHITECTURE CLEANUP: Removed unused ContextBuilderFactory and all builder classes

_LOGGER = logging.getLogger(__name__)


class ContextBuildingPhase:
    """Context building phase for compiler-like formula evaluation.

    This phase handles the complete construction and management of evaluation contexts,
    following the compiler-like approach described in the state and entity reference guide.

    PHASE 3: Context Construction and Management
    - Build entity-based contexts
    - Build variable-based contexts
    - Build cross-sensor contexts
    - Handle context validation and error handling
    """

    def __init__(self) -> None:
        """Initialize the context building phase."""
        # ARCHITECTURE CLEANUP: Removed unused ContextBuilderFactory
        # These will be set during integration
        self._hass: Any = None
        self._data_provider_callback: DataProviderCallback | None = None
        self._dependency_handler: Any = None
        self._sensor_to_backing_mapping: dict[str, str] = {}
        self._global_settings: dict[str, Any] | None = None

    def _safe_context_set(self, context: HierarchicalContextDict, key: str, value: ContextValue) -> None:
        """Safely set a value in context, using unified setter if available."""
        if hasattr(context, "_hierarchical_context"):
            # This is our HierarchicalContextDict - use unified setter
            context._hierarchical_context.set(key, value)
            _LOGGER.debug("SAFE_CONTEXT_SET: Used unified setter for %s", key)
        else:
            # Regular dict - use direct assignment
            context[key] = value
            _LOGGER.debug("SAFE_CONTEXT_SET: Used direct assignment for %s", key)

    def set_evaluator_dependencies(
        self,
        hass: Any,
        data_provider_callback: DataProviderCallback | None,
        dependency_handler: Any,
        sensor_to_backing_mapping: dict[str, str],
    ) -> None:
        """Set dependencies from the evaluator for context building."""
        self._hass = hass
        self._data_provider_callback = data_provider_callback
        self._dependency_handler = dependency_handler
        self._sensor_to_backing_mapping = sensor_to_backing_mapping

    def set_global_settings(self, global_settings: dict[str, Any] | None) -> None:
        """Set global settings to make global variables available during context building.

        This ensures that global variables are available when computed variables are
        evaluated, fixing the empty context issue.
        """
        self._global_settings = global_settings
        _LOGGER.debug(
            "Context building phase: set global settings with %d variables",
            len(global_settings.get("variables", {})) if global_settings else 0,
        )

    def build_evaluation_context(
        self,
        dependencies: set[str],
        context: HierarchicalContextDict,
        config: FormulaConfig | None = None,
        sensor_config: SensorConfig | None = None,
    ) -> HierarchicalContextDict:
        """Build the complete evaluation context for formula evaluation."""
        # ARCHITECTURE FIX: Context is now required parameter - no None checks needed
        eval_context = context  # Preserve the hierarchical context
        _LOGGER.warning(
            "CONTEXT_BUILDING_PRESERVE: Using input context id=%d type=%s with %d items",
            id(eval_context),
            type(eval_context).__name__,
            len(eval_context),
        )

        # Add Home Assistant instance for metadata handler access
        if self._hass is not None:
            _LOGGER.warning("CONTEXT_BUILDING_HASS: Adding HASS instance to context: %s", type(self._hass).__name__)
            eval_context._hierarchical_context.set_system_object("_hass", self._hass)
        else:
            _LOGGER.warning("CONTEXT_BUILDING_NO_HASS: No HASS instance available in context building phase")

        # Add Home Assistant constants to evaluation context (lowest priority)
        self._add_ha_constants_to_context(eval_context)

        # Create modern resolver factory
        resolver_factory = self._create_resolver_factory(context)

        # Add context variables first (highest priority)
        self._add_context_variables(eval_context, context)

        # CRITICAL FIX: Add current sensor entity_id to context for metadata(state, ...) support
        # This ensures the metadata handler can resolve 'state' token to the current sensor's entity_id
        if sensor_config and sensor_config.entity_id:
            self._add_entity_to_context(
                eval_context,
                "current_sensor_entity_id",
                ReferenceValue(reference="sensor_config.entity_id", value=sensor_config.entity_id),
                "current_sensor",
            )
            _LOGGER.debug("Added current sensor entity_id to context: %s", sensor_config.entity_id)

        # Add global variables BEFORE resolving computed variables
        # This ensures global variables are available when computed variables are evaluated
        self._add_global_variables_to_context(eval_context)

        # CRITICAL FIX: Add sensor_config and formula_config to context BEFORE resolving entity dependencies
        # This ensures the StateResolver can access them when determining resolution strategy
        if sensor_config is not None:
            eval_context._hierarchical_context.set_system_object("_sensor_config", sensor_config)
        if config is not None:
            eval_context._hierarchical_context.set_system_object("_formula_config", config)

        # CRITICAL: Add state variable to context immediately after globals
        # The state is ALWAYS needed even if purely calculated (value would be None)
        self._add_state_to_context(eval_context, resolver_factory)

        # Resolve entity dependencies
        self._resolve_entity_dependencies(eval_context, dependencies, resolver_factory)

        # Resolve config variables (can override entity values)
        # Use the same resolver factory as context is managed within individual resolvers
        self._resolve_config_variables(eval_context, config, resolver_factory, sensor_config)

        _LOGGER.debug("Context building phase: built context with %d variables", len(eval_context))
        return eval_context

    def _add_state_to_context(self, eval_context: HierarchicalContextDict, resolver_factory: Any) -> None:
        """Ensure state variable is properly set in context using prior state resolution.

        This method sets up the initial state reference using prior/backing values,
        avoiding full evaluation that could trigger alternate state processing.
        """
        # Check if state is already properly set in context
        existing_state = eval_context.get("state")
        if (
            isinstance(existing_state, ReferenceValue) and existing_state.reference and existing_state.reference != "state"
        ):  # Has proper entity_id reference
            _LOGGER.debug("Context building: State already properly set with entity_id reference: %s", existing_state.reference)
            return

        _LOGGER.debug("Context building: State needs to be set using prior state resolution")

        # Try to get sensor config from context (should be set by build_evaluation_context)
        try:
            sensor_config_raw = eval_context._hierarchical_context.get("_sensor_config")
        except KeyError:
            # No sensor config available - this can happen for computed variables or cross-sensor references
            _LOGGER.debug("Context building: No _sensor_config in context - setting basic state reference")
            # Set a basic state reference for computed variables
            basic_state_ref = ReferenceValue(reference="state", value=None)
            self._safe_context_set(eval_context, "state", basic_state_ref)
            return

        if sensor_config_raw is not None and hasattr(sensor_config_raw, "unique_id"):
            sensor_config = sensor_config_raw

            # Get StateResolver from resolver factory and use prior state resolution
            try:
                # Get the StateResolver instance from the factory
                state_resolver = None
                if hasattr(resolver_factory, "_resolvers"):
                    for resolver in resolver_factory._resolvers:
                        if hasattr(resolver, "resolve_prior_state_reference"):
                            state_resolver = resolver
                            break

                if state_resolver:
                    # Use the new prior state resolution method
                    prior_state_ref = state_resolver.resolve_prior_state_reference(sensor_config, eval_context)
                    if prior_state_ref:
                        self._safe_context_set(eval_context, "state", prior_state_ref)
                        _LOGGER.debug(
                            "Context building: Set prior state reference for sensor %s: %s",
                            sensor_config.unique_id,
                            prior_state_ref.value,
                        )
                    else:
                        # No prior state available - set basic reference
                        basic_state_ref = ReferenceValue(
                            reference=sensor_config.entity_id if sensor_config.entity_id else "state", value=None
                        )
                        self._safe_context_set(eval_context, "state", basic_state_ref)
                        _LOGGER.debug(
                            "Context building: No prior state available for sensor %s - set basic reference",
                            sensor_config.unique_id,
                        )
                else:
                    _LOGGER.warning("Context building: No StateResolver found in resolver factory")
                    # Fallback to basic state reference
                    basic_state_ref = ReferenceValue(
                        reference=sensor_config.entity_id if sensor_config.entity_id else "state", value=None
                    )
                    self._safe_context_set(eval_context, "state", basic_state_ref)

            except Exception as e:
                _LOGGER.error("Context building: Failed to resolve prior state for sensor %s: %s", sensor_config.unique_id, e)
                # Fallback to basic state reference
                basic_state_ref = ReferenceValue(
                    reference=sensor_config.entity_id if sensor_config.entity_id else "state", value=None
                )
                self._safe_context_set(eval_context, "state", basic_state_ref)
        else:
            _LOGGER.debug("Context building: Invalid sensor_config - setting basic state reference")
            # Set a basic state reference
            basic_state_ref = ReferenceValue(reference="state", value=None)
            self._safe_context_set(eval_context, "state", basic_state_ref)

    def _create_resolver_factory(self, context: HierarchicalContextDict) -> VariableResolverFactory:
        """Create modern variable resolver factory for direct resolution."""

        resolver_factory = VariableResolverFactory(
            hass=self._hass,
            data_provider_callback=self._data_provider_callback,
            sensor_to_backing_mapping=self._sensor_to_backing_mapping,
        )

        # Configure the dependency handler for entity resolution
        if self._dependency_handler:
            resolver_factory.set_dependency_handler(self._dependency_handler)

        return resolver_factory

    def _add_context_variables(self, eval_context: HierarchicalContextDict, context: HierarchicalContextDict) -> None:
        """Add context variables to evaluation context."""
        # ARCHITECTURE FIX: Context is now required parameter - no None checks needed
        # ARCHITECTURE FIX: Ensure all context values are ReferenceValue objects
        # This prevents raw value injection during context merging
        for key, value in context.items():
            if key.startswith("_"):
                # Use system object method for internal registry keys
                eval_context._hierarchical_context.set_system_object(key, value)
            elif isinstance(value, ReferenceValue):
                # Already a ReferenceValue - use directly
                self._safe_context_set(eval_context, key, value)
            else:
                # Wrap intermediate raw values with ReferenceValue from computed variable results
                if isinstance(value, (int | float | str | bool)):
                    _LOGGER.debug(
                        "Converting raw value '%s'=%s (type: %s) to ReferenceValue for context",
                        key,
                        value,
                        type(value).__name__,
                    )
                    ReferenceValueManager.set_variable_with_reference_value(eval_context, key, key, value)
                else:
                    # ERROR: Other raw values should not exist at this point
                    _LOGGER.error(
                        "CONTEXT_BUG: Raw value '%s'=%s (type: %s) found in context - this indicates an upstream bug",
                        key,
                        value,
                        type(value).__name__,
                    )
                    # Fail fast to expose the problem
                    raise TypeError(
                        f"Raw value found in context: {key}={value}. Context should only contain ReferenceValue objects."
                    )

    def _add_global_variables_to_context(self, eval_context: HierarchicalContextDict) -> None:
        """Add global variables to the evaluation context before computed variable resolution.

        This is critical for fixing the empty context issue - global variables must be
        available BEFORE computed variables are evaluated.
        """
        if not self._global_settings:
            _LOGGER.debug("Context building: No global settings available")
            return

        global_vars = self._global_settings.get("variables", {})
        if not global_vars:
            _LOGGER.debug("Context building: No global variables to add")
            return

        for var_name, var_value in global_vars.items():
            # Store global variable as ReferenceValue with original value
            # Let the handler/type analyzer system handle conversion during evaluation
            ReferenceValueManager.set_variable_with_reference_value(eval_context, var_name, var_name, var_value)
            _LOGGER.debug("Context building: Added global variable '%s' = %s", var_name, var_value)

    def _resolve_entity_dependencies(
        self, eval_context: HierarchicalContextDict, dependencies: set[str], resolver_factory: VariableResolverFactory
    ) -> None:
        """Resolve entity dependencies using modern variable resolver factory."""
        for entity_id in dependencies:
            # ARCHITECTURE FIX: Skip dependencies that are already in context
            if entity_id in eval_context:
                _LOGGER.debug("Dependency '%s' already in context, skipping resolution", entity_id)
                continue

            try:
                resolved_value = resolver_factory.resolve_variable(
                    variable_name=entity_id, variable_value=entity_id, context=eval_context
                )
                if resolved_value is not None:
                    self._add_entity_to_context(eval_context, entity_id, resolved_value, "entity_dependency")
                else:
                    # Entity could not be resolved
                    raise MissingDependencyError(f"Failed to resolve entity dependency: {entity_id}")
            except Exception as e:
                # Log the specific error and re-raise as MissingDependencyError
                _LOGGER.debug("Entity dependency resolution failed for '%s': %s", entity_id, e)
                raise MissingDependencyError(f"Failed to resolve entity dependency: {entity_id}") from e

    def _add_entity_to_context(
        self, eval_context: HierarchicalContextDict, entity_id: str, value: ContextValue, source: str
    ) -> None:
        """Add entity to evaluation context."""
        # Use centralized ReferenceValueManager for type safety
        # If value is already a ReferenceValue, use it directly
        if isinstance(value, ReferenceValue):
            self._safe_context_set(eval_context, entity_id, value)
        else:
            # Create ReferenceValue for entity
            ReferenceValueManager.set_variable_with_reference_value(
                eval_context,
                entity_id,
                entity_id,
                value,  # entity_id is both name and reference
            )
        _LOGGER.debug("Added entity %s to context from %s: %s", entity_id, source, value)

    def _resolve_config_variables(
        self,
        eval_context: HierarchicalContextDict,
        config: FormulaConfig | None,
        resolver_factory: VariableResolverFactory,
        sensor_config: SensorConfig | None = None,
    ) -> None:
        """Resolve config variables using modern variable resolver factory."""

        def resolver_callback(var_name: str, var_value: Any, context: HierarchicalContextDict, sensor_cfg: Any) -> Any:
            # For non-string values (numeric literals), add directly to context
            if not isinstance(var_value, str):
                return var_value

            # Use modern resolver factory which returns ReferenceValue objects directly
            try:
                resolved_value = resolver_factory.resolve_variable(
                    variable_name=var_name, variable_value=var_value, context=context
                )
                if resolved_value is not None:
                    # Modern resolver returns ReferenceValue objects directly
                    return resolved_value
            except DataValidationError:
                # Re-raise fatal data validation errors - these should not be suppressed
                raise
            except Exception as e:
                _LOGGER.debug("Config variable resolution failed for '%s': %s", var_name, e)

            # Fallback to adding as-is if resolution fails
            return var_value

        # BULLETPROOF: Log what type we're passing to resolve_config_variables from context building phase
        _LOGGER.warning(
            "CONTEXT_BUILDING_CALLING: Passing context id=%d type=%s to resolve_config_variables",
            id(eval_context),
            type(eval_context).__name__,
        )
        resolve_config_variables(eval_context, config, resolver_callback, sensor_config)

    def _handle_config_variable_none_value(self, var_name: str, config: FormulaConfig) -> None:
        """Handle config variable with None value."""
        _LOGGER.warning("Config variable '%s' in formula '%s' resolved to None", var_name, config.name or config.id)

    def _add_ha_constants_to_context(self, eval_context: HierarchicalContextDict) -> None:
        """Add Home Assistant constants to the evaluation context.

        With lazy loading in place via formula_constants.__getattr__,
        HA constants are available on-demand without pre-loading.
        This method is kept for compatibility but no longer pre-loads constants.
        """
        # Note: HA constants are now available via lazy loading in formula_constants
        # No need to pre-load constants as they're resolved on-demand
        _LOGGER.debug("HA constants available via lazy loading - no pre-loading needed")

    def _is_attribute_reference(self, var_value: str) -> bool:
        """Check if a variable value is an attribute reference."""
        if not isinstance(var_value, str):
            return False

        # Check for attribute patterns
        if "." in var_value:
            # Check for state.attribute pattern first
            if var_value.startswith("state."):
                return True

            # Skip entity IDs (they have dots but aren't attribute references)
            # Use dynamic domain discovery instead of hardcoded list
            hass = getattr(self, "_hass", None)
            if hass:
                ha_domains = get_ha_domains(hass)
                if any(var_value.startswith(f"{domain}.") for domain in ha_domains):
                    return False

            # Check for other attribute patterns
            parts = var_value.split(".")
            if len(parts) == 2:
                # This could be an attribute reference
                return True

        return False

    def _resolve_state_attribute_reference(self, var_value: str, sensor_config: SensorConfig | None) -> Any:
        """Resolve a state attribute reference like 'state.voltage'."""
        if not sensor_config or not var_value.startswith("state."):
            return None

        # Extract the attribute name
        attribute_name = var_value.split(".", 1)[1]

        # Get the backing entity ID
        backing_entity_id = self._sensor_to_backing_mapping.get(sensor_config.unique_id)
        if not backing_entity_id:
            return None

        # Call the data provider to get the backing entity data
        if not self._data_provider_callback:
            return None

        result = self._data_provider_callback(backing_entity_id)
        if not result or not result.get("exists"):
            return None

        # Check if the result has attributes
        if "attributes" in result and isinstance(result["attributes"], dict):
            attributes = result["attributes"]
            if attribute_name in attributes:
                return attributes[attribute_name]

        return None
