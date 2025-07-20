"""State resolver for handling standalone state token references."""

import logging
from typing import Any, Callable

from ...config_models import FormulaConfig, SensorConfig
from ...exceptions import BackingEntityResolutionError
from ...type_definitions import ContextValue, DataProviderResult
from .base_resolver import VariableResolver

_LOGGER = logging.getLogger(__name__)


class StateResolver(VariableResolver):
    """Resolver for standalone state token references like 'state'.

    According to the State and Entity Reference Guide:
    - Main Formula State Idiom: If a sensor has a resolvable backing entity,
      the 'state' token in the main formula resolves to the current state of the backing entity.
    - If there is no backing entity, 'state' refers to the sensor's own pre-evaluation state.
    - This resolver handles complete state token resolution including backing entity validation.
    """

    def __init__(
        self,
        sensor_to_backing_mapping: dict[str, str] | None = None,
        data_provider_callback: Callable[[str], DataProviderResult] | None = None,
    ) -> None:
        """Initialize the StateResolver with backing entity mapping and data provider."""
        self._sensor_to_backing_mapping = sensor_to_backing_mapping or {}
        self._data_provider_callback = data_provider_callback

    def can_resolve(self, variable_name: str, variable_value: str | Any) -> bool:
        """Determine if this resolver can handle standalone state token references."""
        # Check if this is a standalone 'state' reference
        return variable_name == "state" and variable_value == "state"

    def resolve(self, variable_name: str, variable_value: str | Any, context: dict[str, ContextValue]) -> Any | None:
        """Resolve a standalone state token reference.

        This is the complete state token resolution according to the guide:
        1. For main formulas with backing entities: resolve to backing entity state
        2. For main formulas without backing entities: resolve to previous calculated value
        3. For attribute formulas: resolve to main sensor calculated value (from context)
        4. Validate backing entity mapping exists when expected
        """
        if not isinstance(variable_value, str) or variable_value != "state":
            return None

        # First, check if state is already in context (e.g., for attribute formulas or previous value)
        if "state" in context:
            state_value = context["state"]
            _LOGGER.debug("State resolver: resolved 'state' from context to value '%s'", state_value)
            return state_value

        # If not in context, attempt backing entity resolution for main formulas
        sensor_config_raw = context.get("sensor_config")
        formula_config_raw = context.get("formula_config")

        # Type cast the context values to the expected types
        sensor_config = sensor_config_raw if isinstance(sensor_config_raw, SensorConfig) else None
        formula_config = formula_config_raw if isinstance(formula_config_raw, FormulaConfig) else None

        if self._should_resolve_backing_entity(sensor_config, formula_config):
            if sensor_config is not None:
                return self._resolve_backing_entity_state(sensor_config)
            # This should not happen if _should_resolve_backing_entity returned True
            _LOGGER.warning("State resolver: sensor_config is None but should_resolve_backing_entity returned True")
            raise BackingEntityResolutionError(
                entity_id="state",
                reason="State token cannot be resolved: invalid sensor configuration",
            )

        # State token cannot be resolved - this is a fatal error
        _LOGGER.debug("State resolver: 'state' token cannot be resolved - no context value and no backing entity")
        raise BackingEntityResolutionError(
            entity_id="state",
            reason="State token cannot be resolved: no backing entity mapping and no previous value available",
        )

    def _should_resolve_backing_entity(self, sensor_config: SensorConfig | None, formula_config: FormulaConfig | None) -> bool:
        """Determine if backing entity resolution should be attempted."""
        if not sensor_config or not formula_config:
            return False

        # Only resolve backing entity state for main formulas
        # Main formulas have either id="main" or id=sensor.unique_id (for implicit main formulas)
        is_main_formula = formula_config.id in ("main", sensor_config.unique_id)

        return is_main_formula and sensor_config.unique_id in self._sensor_to_backing_mapping

    def _resolve_backing_entity_state(self, sensor_config: SensorConfig) -> Any:
        """Resolve the backing entity state for the sensor."""
        backing_entity_id = self._sensor_to_backing_mapping[sensor_config.unique_id]

        _LOGGER.debug(
            "State resolver: Resolving backing entity state for sensor '%s' -> backing entity '%s'",
            sensor_config.unique_id,
            backing_entity_id,
        )

        # Use the data provider to get the backing entity state
        if self._data_provider_callback is None:
            raise BackingEntityResolutionError(
                entity_id=backing_entity_id,
                reason=f"Cannot resolve backing entity for sensor '{sensor_config.unique_id}': no data provider available",
            )

        result = self._data_provider_callback(backing_entity_id)
        if result is None or not result.get("exists", False):
            raise BackingEntityResolutionError(
                entity_id=backing_entity_id,
                reason=f"Cannot resolve backing entity for sensor '{sensor_config.unique_id}': entity does not exist or is not available",
            )

        # Get the state value from the result (using "value" field from data provider)
        state_value = result.get("value")
        if state_value is None:
            # None values are treated as Unknown to allow for integration initialization
            _LOGGER.debug(
                "State resolver: Backing entity '%s' has None state value, treating as Unknown",
                backing_entity_id,
            )
            return "Unknown"

        _LOGGER.debug(
            "State resolver: Successfully resolved backing entity '%s' state to '%s'",
            backing_entity_id,
            state_value,
        )
        return state_value
