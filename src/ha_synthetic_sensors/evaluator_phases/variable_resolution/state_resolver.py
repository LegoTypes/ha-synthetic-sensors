"""State resolver for handling standalone state token references."""

from collections.abc import Callable
import logging
from typing import Any

from ...config_models import FormulaConfig, SensorConfig
from ...constants_evaluation_results import RESULT_KEY_VALUE
from ...exceptions import BackingEntityResolutionError
from ...type_definitions import ContextValue, DataProviderResult, ReferenceValue
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
        hass: Any = None,
    ) -> None:
        """Initialize the StateResolver with backing entity mapping, data provider, and HA instance."""
        self._sensor_to_backing_mapping = sensor_to_backing_mapping or {}
        self._data_provider_callback = data_provider_callback
        self._hass = hass

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

            # If it's already a ReferenceValue, return it directly
            if isinstance(state_value, ReferenceValue):
                return state_value

            # Convert raw value to ReferenceValue for consistency
            # Use 'state' as the reference since that's what was requested
            # Ensure the value is of the correct type for ReferenceValue
            if isinstance(state_value, str | int | float | bool) or state_value is None:
                return ReferenceValue(reference="state", value=state_value)

            # Convert complex types to string representation
            return ReferenceValue(reference="state", value=str(state_value))

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

        # No backing entity mapping - try to fall back to sensor's own HA state
        if sensor_config and sensor_config.entity_id and self._should_resolve_sensor_own_state(sensor_config, formula_config):
            return self._resolve_sensor_own_state(sensor_config)

        # State token cannot be resolved - this is a fatal error
        _LOGGER.debug(
            "State resolver: 'state' token cannot be resolved - no context value, no backing entity, and no sensor entity_id"
        )
        raise BackingEntityResolutionError(
            entity_id="state",
            reason="State token cannot be resolved: no backing entity mapping, no sensor entity_id, and no previous value available",
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
        state_value = result.get(RESULT_KEY_VALUE)
        if state_value is None:
            # Preserve None values - let alternate state handlers decide what to do
            _LOGGER.debug(
                "STATE_RESOLVER_DEBUG: Backing entity '%s' has None state value, preserving None",
                backing_entity_id,
            )
            return ReferenceValue(reference=backing_entity_id, value=None)

        _LOGGER.debug(
            "State resolver: Successfully resolved backing entity '%s' state to '%s'",
            backing_entity_id,
            state_value,
        )
        # Return ReferenceValue for backing entity state
        return ReferenceValue(reference=backing_entity_id, value=state_value)

    def _should_resolve_sensor_own_state(
        self, sensor_config: SensorConfig | None, formula_config: FormulaConfig | None
    ) -> bool:
        """Determine if sensor's own HA state resolution should be attempted."""
        if not sensor_config or not formula_config:
            return False

        # Only resolve sensor's own state for main formulas
        # Main formulas have either id="main" or id=sensor.unique_id (for implicit main formulas)
        is_main_formula = formula_config.id in ("main", sensor_config.unique_id)

        # Only resolve if this is a main formula and sensor has entity_id
        return is_main_formula and sensor_config.entity_id is not None

    def _resolve_sensor_own_state(self, sensor_config: SensorConfig) -> Any:
        """Resolve the sensor's own HA state for recursive/self-reference calculations."""
        entity_id = sensor_config.entity_id

        _LOGGER.debug(
            "State resolver: Resolving sensor's own HA state for sensor '%s' -> entity_id '%s'",
            sensor_config.unique_id,
            entity_id,
        )

        if not self._hass or not hasattr(self._hass, "states"):
            raise BackingEntityResolutionError(
                entity_id=entity_id or "unknown",
                reason=f"Cannot resolve sensor's own state for '{sensor_config.unique_id}': Home Assistant instance not available",
            )

        # Get the current HA state for the sensor's entity_id
        hass_state = self._hass.states.get(entity_id)
        if hass_state is None:
            # If sensor doesn't exist in HA yet, treat as initial state
            _LOGGER.debug(
                "State resolver: Sensor '%s' not found in HA, treating as initial state (value: 0)",
                entity_id,
            )
            # Return ReferenceValue for initial state
            return ReferenceValue(reference=entity_id or "unknown", value=0)

        # Extract numeric value from the state
        state_value = hass_state.state
        if state_value in ["unknown", "unavailable", "None", None]:
            _LOGGER.debug(
                "State resolver: Sensor '%s' has unknown/unavailable state, treating as 0",
                entity_id,
            )
            # Return ReferenceValue for unknown/unavailable state
            return ReferenceValue(reference=entity_id or "unknown", value=0)

        # Try to convert to numeric value
        try:
            numeric_value = float(state_value)
            _LOGGER.debug(
                "State resolver: Successfully resolved sensor's own HA state '%s' -> %s",
                entity_id,
                numeric_value,
            )
            # Return ReferenceValue for numeric state
            return ReferenceValue(reference=entity_id or "unknown", value=numeric_value)
        except (ValueError, TypeError):
            # Handle boolean-like states (on/off, true/false, etc.)
            if isinstance(state_value, str):
                state_lower = state_value.lower()
                if state_lower in ("on", "true", "open", "locked", "home", "detected"):
                    # Return ReferenceValue for boolean true state
                    return ReferenceValue(reference=entity_id or "unknown", value=1.0)
                if state_lower in ("off", "false", "closed", "unlocked", "away", "clear"):
                    # Return ReferenceValue for boolean false state
                    return ReferenceValue(reference=entity_id or "unknown", value=0.0)

            _LOGGER.warning(
                "State resolver: Cannot convert sensor's own state '%s' (value: '%s') to numeric, defaulting to 0",
                entity_id,
                state_value,
            )
            # Return ReferenceValue for default fallback state
            return ReferenceValue(reference=entity_id or "unknown", value=0)
