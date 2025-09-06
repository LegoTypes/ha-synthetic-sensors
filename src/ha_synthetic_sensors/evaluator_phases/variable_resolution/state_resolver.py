"""State resolver for handling standalone state token references."""

from collections.abc import Callable
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import STATE_UNKNOWN

from ...hierarchical_context_dict import HierarchicalContextDict

if TYPE_CHECKING:
    pass

from ...config_models import FormulaConfig, SensorConfig
from ...constants_boolean_states import get_current_core_false_states, get_current_core_true_states
from ...constants_evaluation_results import RESULT_KEY_VALUE
from ...exceptions import BackingEntityResolutionError, MissingDependencyError
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

    def resolve(self, variable_name: str, variable_value: str | Any, context: "HierarchicalContextDict") -> ContextValue:
        """Resolve a standalone state token reference.

        This is the complete state token resolution according to the guide:
        1. For main formulas with backing entities: resolve to backing entity state
        2. For main formulas without backing entities: resolve to previous calculated value
        3. For attribute formulas: resolve to main sensor calculated value (from context)
        4. Validate backing entity mapping exists when expected
        """

        if not isinstance(variable_value, str) or variable_value != "state":
            return None

        # First, check if state is already in context with a meaningful value (e.g., for attribute formulas or previous value)
        if "state" in context:
            state_value = context["state"]
            # Debug logging removed to reduce verbosity

            # If it's already a ReferenceValue, check if we need to resolve its value
            if isinstance(state_value, ReferenceValue):
                # If value is None, try to resolve it using existing resolution logic
                if state_value.value is None:
                    # Use the existing resolution logic below to get the resolved value
                    resolved_ref_value = self._resolve_state_from_context_or_backing_entity(context)
                    if isinstance(resolved_ref_value, ReferenceValue) and resolved_ref_value.value is not None:
                        # Update the shared ReferenceValue's value property
                        state_value._value = resolved_ref_value.value
                        _LOGGER.debug(
                            "State resolver: Updated shared ReferenceValue with resolved value: %s", state_value._value
                        )

                # Return the ReferenceValue (now potentially updated with resolved value)
                return state_value
            else:
                # Convert raw value to ReferenceValue for consistency, but only if not None
                # Use 'state' as the reference since that's what was requested
                if state_value is not None:
                    # Ensure the value is of the correct type for ReferenceValue
                    if isinstance(state_value, str | int | float | bool):
                        return ReferenceValue(reference="state", value=state_value)
                    # Convert complex types to string representation
                    return ReferenceValue(reference="state", value=str(state_value))
                # Fall through to backing entity resolution if value is None

        # If not in context, use the common resolution logic
        return self._resolve_state_from_context_or_backing_entity(context)

    def _resolve_state_from_context_or_backing_entity(self, context: HierarchicalContextDict) -> ContextValue:
        """Resolve state from context or backing entity."""
        # Get sensor and formula config from context
        sensor_config_raw = context.get("_sensor_config")
        formula_config_raw = context.get("_formula_config")
        sensor_config = sensor_config_raw if isinstance(sensor_config_raw, SensorConfig) else None
        formula_config = formula_config_raw if isinstance(formula_config_raw, FormulaConfig) else None

        should_resolve = self._should_resolve_backing_entity(sensor_config, formula_config)
        _LOGGER.debug(
            "State resolver: should_resolve_backing_entity = %s (sensor_config=%s, formula_config=%s)",
            should_resolve,
            sensor_config.unique_id if sensor_config else None,
            formula_config.id if formula_config else None,
        )

        if should_resolve:
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

        # For pure calculation sensors or when no backing entity/HA state is available,
        # state refers to the sensor's calculated value. During dependency resolution,
        # this will be None, but during evaluation it will be the calculated result.
        if sensor_config:
            # Return ReferenceValue that points to this sensor's calculated state
            # The reference should indicate this is the sensor's own calculated state
            sensor_entity_id = sensor_config.entity_id or f"sensor.{sensor_config.unique_id}"
            return ReferenceValue(reference=sensor_entity_id, value=None)

        # Fallback for dependency resolution phase when sensor context isn't fully set up yet
        # Return a generic state reference that will be properly resolved during evaluation
        return ReferenceValue(reference="state", value=None)

    def _should_resolve_backing_entity(self, sensor_config: SensorConfig | None, formula_config: FormulaConfig | None) -> bool:
        """Determine if backing entity resolution should be attempted."""
        if not sensor_config or not formula_config:
            _LOGGER.debug(
                "State resolver: should_resolve_backing_entity = False (missing config: sensor=%s, formula=%s)",
                sensor_config is not None,
                formula_config is not None,
            )
            return False

        # Only resolve backing entity state for main formulas
        # Main formulas have either id="main" or id=sensor.unique_id (for implicit main formulas)
        is_main_formula = formula_config.id in ("main", sensor_config.unique_id)
        has_backing_mapping = sensor_config.unique_id in self._sensor_to_backing_mapping

        _LOGGER.debug(
            "State resolver: should_resolve_backing_entity checks: is_main_formula=%s (formula.id='%s', sensor.unique_id='%s'), has_backing_mapping=%s",
            is_main_formula,
            formula_config.id,
            sensor_config.unique_id,
            has_backing_mapping,
        )

        return is_main_formula and has_backing_mapping

    def _resolve_backing_entity_state(self, sensor_config: SensorConfig) -> Any:
        """Resolve the backing entity state for the sensor."""
        backing_entity_id = self._sensor_to_backing_mapping[sensor_config.unique_id]

        # Use the data provider to get the backing entity state
        if self._data_provider_callback is None:
            # Return ReferenceValue with None value - let allow_unresolved_states logic handle this
            _LOGGER.debug(
                "State resolver: No data provider available for backing entity '%s', returning None", backing_entity_id
            )
            return ReferenceValue(reference=backing_entity_id, value=None)

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
            # Debug logging removed to reduce verbosity
            return ReferenceValue(reference=backing_entity_id, value=None)

        # Debug logging removed to reduce verbosity
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
            # If sensor doesn't exist in HA yet raise MissingDependencyError
            raise MissingDependencyError(f"Sensor '{entity_id}' not found in HA")
        # Extract numeric value from the state
        state_value = hass_state.state
        # Handle None separately to preserve it for alternate state handlers
        if state_value is None:
            _LOGGER.debug(
                "State resolver: Sensor '%s' has None state, preserving for alternate state handlers",
                entity_id,
            )
            # Preserve None values - let alternate state handlers decide what to do
            return ReferenceValue(reference=entity_id or "unknown", value=None)

        # Handle alternate states - preserve original values for proper alternate state classification
        if state_value in [STATE_UNKNOWN, STATE_UNAVAILABLE, "None"]:
            _LOGGER.debug(
                "State resolver: Sensor '%s' has alternate state '%s', preserving for alternate handler",
                entity_id,
                state_value,
            )
            return ReferenceValue(reference=entity_id or "unknown", value=state_value)

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
            # Handle boolean-like states using centralized constants
            true_states = get_current_core_true_states()
            false_states = get_current_core_false_states()

            if state_value in true_states:
                # Return ReferenceValue for boolean true state
                return ReferenceValue(reference=entity_id or "unknown", value=1.0)
            if state_value in false_states:
                # Return ReferenceValue for boolean false state
                return ReferenceValue(reference=entity_id or "unknown", value=0.0)

            _LOGGER.warning(
                "State resolver: Cannot convert sensor's own state '%s' (value: '%s') to numeric, defaulting to 0.0",
                entity_id,
                state_value,
            )
            # Return ReferenceValue for default fallback state
            return ReferenceValue(reference=entity_id or "unknown", value=0.0)

    def _is_attribute_formula(self, sensor_config: SensorConfig, formula_config: FormulaConfig) -> bool:
        """Determine if this is an attribute formula (not the main formula)."""
        if not sensor_config.formulas:
            return False
        # If this formula is not the first (main) formula, it's an attribute formula
        return formula_config.id != sensor_config.formulas[0].id
