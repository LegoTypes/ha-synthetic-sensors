"""Context building phase for compiler-like formula evaluation."""

import logging
from typing import Any

from ...config_models import FormulaConfig, SensorConfig
from ...type_definitions import ContextValue, DataProviderCallback
from ...utils_config import resolve_config_variables
from ...variable_resolver import (
    ContextResolutionStrategy,
    HomeAssistantResolutionStrategy,
    IntegrationResolutionStrategy,
    VariableResolutionStrategy,
    VariableResolver,
)
from .builder_factory import ContextBuilderFactory

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
        self._builder_factory = ContextBuilderFactory()
        # These will be set during integration
        self._hass: Any = None
        self._data_provider_callback: DataProviderCallback | None = None
        self._dependency_handler: Any = None
        self._sensor_to_backing_mapping: dict[str, str] = {}

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

    def build_evaluation_context(
        self,
        dependencies: set[str],
        context: dict[str, ContextValue] | None = None,
        config: FormulaConfig | None = None,
        sensor_config: SensorConfig | None = None,
        allow_ha_lookups: bool = False,
    ) -> dict[str, ContextValue]:
        """Build the complete evaluation context for formula evaluation."""
        eval_context: dict[str, ContextValue] = {}

        # Add Home Assistant constants to evaluation context (lowest priority)
        self._add_ha_constants_to_context(eval_context)

        # Create variable resolver with allow_ha_lookups setting
        resolver = self._create_variable_resolver(context, allow_ha_lookups)

        # Add context variables first (highest priority)
        self._add_context_variables(eval_context, context)

        # Resolve entity dependencies
        self._resolve_entity_dependencies(eval_context, dependencies, resolver)

        # Resolve config variables (can override entity values)
        # Create a new resolver with the current eval_context to include resolved entities
        resolver_with_context = self._create_variable_resolver(eval_context, allow_ha_lookups)
        self._resolve_config_variables(eval_context, config, resolver_with_context, sensor_config)

        _LOGGER.debug("Context building phase: built context with %d variables", len(eval_context))
        return eval_context

    def _create_variable_resolver(
        self, context: dict[str, ContextValue] | None, allow_ha_lookups: bool = False
    ) -> VariableResolver:
        """Create variable resolver with appropriate strategies."""
        strategies: list[VariableResolutionStrategy] = []

        # Context resolution (highest priority)
        if context:
            strategies.append(ContextResolutionStrategy(context))

        # Integration resolution (for data provider callback)
        if self._dependency_handler and self._dependency_handler.data_provider_callback:
            strategies.append(
                IntegrationResolutionStrategy(self._dependency_handler.data_provider_callback, self._dependency_handler)
            )

        # Home Assistant resolution (lowest priority, only if allowed)
        if allow_ha_lookups and self._hass:
            strategies.append(HomeAssistantResolutionStrategy(self._hass))

        return VariableResolver(strategies)

    def _add_context_variables(self, eval_context: dict[str, ContextValue], context: dict[str, ContextValue] | None) -> None:
        """Add context variables to evaluation context."""
        if context:
            eval_context.update(context)

    def _resolve_entity_dependencies(
        self, eval_context: dict[str, ContextValue], dependencies: set[str], resolver: VariableResolver
    ) -> None:
        """Resolve entity dependencies using variable resolver."""
        for entity_id in dependencies:
            resolved_value, exists, _ = resolver.resolve_variable(entity_id, entity_id)
            if exists and resolved_value is not None:
                self._add_entity_to_context(eval_context, entity_id, resolved_value, "entity_dependency")
            else:
                _LOGGER.warning("Failed to resolve entity dependency: %s", entity_id)

    def _add_entity_to_context(
        self, eval_context: dict[str, ContextValue], entity_id: str, value: ContextValue, source: str
    ) -> None:
        """Add entity to evaluation context."""
        eval_context[entity_id] = value
        _LOGGER.debug("Added entity %s to context from %s: %s", entity_id, source, value)

    def _resolve_config_variables(
        self,
        eval_context: dict[str, ContextValue],
        config: FormulaConfig | None,
        resolver: VariableResolver,
        sensor_config: SensorConfig | None = None,
    ) -> None:
        """Resolve config variables using variable resolver."""

        def resolver_callback(var_name: str, var_value: Any, context: dict[str, ContextValue], sensor_cfg: Any) -> Any:
            # For non-string values (numeric literals), add directly to context
            if not isinstance(var_value, str):
                return var_value

            # Use resolver to resolve entity references (strings only)
            resolved_value, exists, _ = resolver.resolve_variable(var_name, var_value)
            if exists and resolved_value is not None:
                return resolved_value

            # Fallback to adding as-is if resolution fails
            return var_value

        resolve_config_variables(eval_context, config, resolver_callback, sensor_config)

    def _handle_config_variable_none_value(self, var_name: str, config: FormulaConfig) -> None:
        """Handle config variable with None value."""
        _LOGGER.warning("Config variable '%s' in formula '%s' resolved to None", var_name, config.name or config.id)

    def _add_ha_constants_to_context(self, eval_context: dict[str, ContextValue]) -> None:
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
            # Skip entity IDs (they have dots but aren't attribute references)
            if var_value.startswith(("sensor.", "binary_sensor.", "input_number.", "input_text.", "input_boolean.")):
                return False

            # Check for state.attribute pattern
            if var_value.startswith("state."):
                return True

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
