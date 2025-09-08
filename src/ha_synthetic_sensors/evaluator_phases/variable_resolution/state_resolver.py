"""State resolver for handling standalone state token references."""

from collections.abc import Callable
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import STATE_UNKNOWN

from ...hierarchical_context_dict import HierarchicalContextDict

if TYPE_CHECKING:
    pass

from datetime import UTC

from ...config_models import FormulaConfig, SensorConfig
from ...constants_boolean_states import get_current_core_false_states, get_current_core_true_states
from ...constants_evaluation_results import RESULT_KEY_VALUE
from ...exceptions import BackingEntityResolutionError, MissingDependencyError
from ...reference_value_manager import ReferenceValueManager
from ...shared_constants import LAST_VALID_CHANGED_KEY, LAST_VALID_STATE_KEY
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

    def resolve_prior_state_reference(
        self, sensor_config: SensorConfig | None, context: HierarchicalContextDict
    ) -> ReferenceValue | None:
        """Resolve prior state reference for context building without triggering evaluation.

        This method gets the backing entity value or prior state for context initialization,
        avoiding the full evaluation pipeline that could trigger alternate state processing.

        Args:
            sensor_config: The sensor configuration (required for backing entity mapping)
            context: The evaluation context

        Returns:
            ReferenceValue with prior state or None if no prior state available
        """
        if not sensor_config:
            _LOGGER.debug("StateResolver: No sensor_config provided for prior state resolution")
            return None

        # Try to get backing entity value first
        backing_entity_id = self._sensor_to_backing_mapping.get(sensor_config.unique_id)
        if backing_entity_id and self._data_provider_callback:
            try:
                result = self._data_provider_callback(backing_entity_id)
                if result and result.get("exists") and result.get("value") is not None:
                    _LOGGER.debug(
                        "StateResolver: Found prior state from backing entity %s: %s", backing_entity_id, result["value"]
                    )
                    # Use the existing unified state reference method
                    state_ref = self._set_unified_state_reference(context, sensor_config, result["value"])

                    _LOGGER.debug("StateResolver: Set up prior state reference using unified method: %s", result["value"])
                    return state_ref
            except Exception as e:
                _LOGGER.debug("StateResolver: Failed to get backing entity value: %s", e)

        # Try to get previous state from HA state registry
        if self._hass and sensor_config.entity_id:
            try:
                state_obj = self._hass.states.get(sensor_config.entity_id)
                if state_obj and state_obj.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE, "unknown", "unavailable"):
                    _LOGGER.debug(
                        "StateResolver: Found prior state from HA registry %s: %s", sensor_config.entity_id, state_obj.state
                    )
                    # Use the existing unified state reference method
                    state_ref = self._set_unified_state_reference(context, sensor_config, state_obj.state)

                    _LOGGER.debug("StateResolver: Set up prior state reference using unified method: %s", state_obj.state)
                    return state_ref
            except Exception as e:
                _LOGGER.debug("StateResolver: Failed to get HA state: %s", e)

        # No prior state available - return None reference for calculated sensors
        _LOGGER.debug("StateResolver: No prior state available for sensor %s", sensor_config.unique_id)
        return ReferenceValue(reference=sensor_config.entity_id if sensor_config.entity_id else "state", value=None)

    def update_state_with_main_result(
        self, context: HierarchicalContextDict, sensor_config: SensorConfig, main_result_value: Any
    ) -> ReferenceValue:
        """Update the state reference in context with the main formula result.

        This method should be called after main formula evaluation to ensure that
        attribute formulas can access the main sensor result via the 'state' token.

        Args:
            context: The evaluation context
            sensor_config: Sensor configuration
            main_result_value: The result value from main formula evaluation

        Returns:
            The updated ReferenceValue for the state
        """
        # Set flag to indicate we're updating with main result (force update of cached ReferenceValue)
        context._updating_main_result = True
        try:
            return self._set_unified_state_reference(context, sensor_config, main_result_value)
        finally:
            # Clean up the flag
            if hasattr(context, "_updating_main_result"):
                delattr(context, "_updating_main_result")

    @classmethod
    def update_context_with_main_result(
        cls,
        context: HierarchicalContextDict,
        sensor_config: SensorConfig,
        main_result_value: Any,
        sensor_to_backing_mapping: dict[str, str],
        data_provider_callback: Callable[[str], dict[str, Any]] | None,
        hass: Any,
    ) -> ReferenceValue:
        """Convenience method to create StateResolver and update context with main result.

        This is a one-call method that creates a StateResolver instance and updates
        the state reference with the main formula result.

        Args:
            context: The evaluation context
            sensor_config: Sensor configuration
            main_result_value: The result value from main formula evaluation
            sensor_to_backing_mapping: Mapping of sensor unique_id to backing entity_id
            data_provider_callback: Optional callback for data provider
            hass: Home Assistant instance

        Returns:
            The updated ReferenceValue for the state
        """
        resolver = cls(
            sensor_to_backing_mapping=sensor_to_backing_mapping, data_provider_callback=data_provider_callback, hass=hass
        )
        return resolver.update_state_with_main_result(context, sensor_config, main_result_value)

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

            # If it's already a ReferenceValue, return it directly
            # Don't try to re-resolve None values as this can cause recursive loops
            # and interfere with alternate state handling
            if isinstance(state_value, ReferenceValue):
                _LOGGER.debug(
                    "State resolver: Found existing ReferenceValue for 'state' with value=%s, returning as-is",
                    state_value.value,
                )
                return state_value
            else:
                # Convert raw value to ReferenceValue for consistency, but only if not None
                if state_value is not None:
                    # Get sensor_config from context to use unified method for proper sharing
                    sensor_config_raw = context.get("_sensor_config")
                    if isinstance(sensor_config_raw, SensorConfig):
                        # Use unified method to ensure proper sharing and context variable setting
                        final_value = state_value if isinstance(state_value, str | int | float | bool) else str(state_value)
                        return self._set_unified_state_reference(context, sensor_config_raw, final_value)
                    else:
                        # Missing sensor_config in context indicates improper setup
                        raise RuntimeError(
                            "StateResolver requires _sensor_config in context for proper state reference sharing. "
                            "This indicates improper context initialization or direct resolver usage without proper setup."
                        )
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
            return self._resolve_sensor_own_state(sensor_config, context)

        # For pure calculation sensors or when no backing entity/HA state is available,
        # state refers to the sensor's calculated value. During dependency resolution,
        # this will be None, but during evaluation it will be the calculated result.
        if sensor_config:
            # Use unified state setting method to ensure single ReferenceValue instance
            return self._set_unified_state_reference(context, sensor_config, None)

        # Check if sensor_config is available in context to use unified method
        sensor_config_raw = context.get("_sensor_config")
        if isinstance(sensor_config_raw, SensorConfig):
            # Use unified method even when sensor_config parameter is None
            return self._set_unified_state_reference(context, sensor_config_raw, None)

        # No sensor_config available - this indicates improper context setup
        raise RuntimeError(
            "StateResolver requires either sensor_config parameter or _sensor_config in context "
            "for proper state reference sharing. This indicates improper context initialization."
        )

    def _set_unified_state_reference(
        self, context: HierarchicalContextDict, sensor_config: SensorConfig, state_value: Any
    ) -> ReferenceValue:
        """Set a unified state ReferenceValue that ensures single instance sharing.

        This method ensures that:
        1. Only one ReferenceValue exists for the state
        2. Both 'state' and the sensor's entity_id reference the same ReferenceValue
        3. Last valid context variables are properly set
        4. The ReferenceValue is cached for reuse

        Args:
            context: The evaluation context
            sensor_config: Sensor configuration
            state_value: The resolved state value (can be None)

        Returns:
            The single ReferenceValue instance for the state
        """
        sensor_entity_id = sensor_config.entity_id or f"sensor.{sensor_config.unique_id}"

        # Use ReferenceValueManager to create/reuse ReferenceValue for this entity
        # This ensures that both 'state' and the sensor's entity_id share the same ReferenceValue
        # Force update when this is called from update_state_with_main_result to ensure main result overwrites backing entity value
        force_update = hasattr(context, "_updating_main_result") and context._updating_main_result
        ReferenceValueManager.set_variable_with_reference_value(
            context, "state", sensor_entity_id, state_value, force_update=force_update
        )

        # Also add _last_valid_changed and _last_valid_state context variables
        self._add_last_valid_context_variables(context, sensor_config)

        # Return the ReferenceValue that was set in context
        state_ref_value = context.get("state")
        if not isinstance(state_ref_value, ReferenceValue):
            # This should not happen if ReferenceValueManager is working correctly
            raise RuntimeError(f"Expected ReferenceValue for state, got {type(state_ref_value)}")

        _LOGGER.debug(
            "State resolver: Set unified state reference for sensor %s -> entity_id %s, value=%s",
            sensor_config.unique_id,
            sensor_entity_id,
            state_value,
        )

        return state_ref_value

    def _add_last_valid_context_variables(self, context: HierarchicalContextDict, sensor_config: SensorConfig) -> None:
        """Add _last_valid_changed and _last_valid_state context variables.

        These variables provide access to the sensor's last valid state and timestamp
        for use in formulas and attribute calculations.
        """
        # Create context variable names with underscore prefix
        last_valid_state_var = f"_{LAST_VALID_STATE_KEY}"
        last_valid_changed_var = f"_{LAST_VALID_CHANGED_KEY}"

        # Use ReferenceValueManager to create context variables that reference the sensor's attributes
        sensor_entity_id = sensor_config.entity_id or f"sensor.{sensor_config.unique_id}"

        # Create references to the sensor's last_valid_state and last_valid_changed attributes
        last_valid_state_ref = f"{sensor_entity_id}.{LAST_VALID_STATE_KEY}"
        last_valid_changed_ref = f"{sensor_entity_id}.{LAST_VALID_CHANGED_KEY}"

        # Try to get actual values for last_valid_* from backing entity or HA state
        last_valid_state_value = None
        last_valid_changed_value = None

        # Try to get values from backing entity first
        backing_entity_id = (
            self._sensor_to_backing_mapping.get(sensor_config.unique_id) if self._sensor_to_backing_mapping else None
        )
        if backing_entity_id and self._data_provider_callback:
            try:
                result = self._data_provider_callback(backing_entity_id)
                if result and result.get("exists"):
                    # For backing entities, use the current state as last_valid_state
                    last_valid_state_value = result.get("value")
                    # Use current time as last_valid_changed (since we don't have historical data)
                    from datetime import datetime

                    last_valid_changed_value = datetime.now(UTC).isoformat()
            except Exception as e:
                _LOGGER.debug("StateResolver: Failed to get last_valid values from backing entity: %s", e)

        # Fallback to HA state if available
        if last_valid_state_value is None and self._hass and sensor_config.entity_id:
            try:
                state_obj = self._hass.states.get(sensor_config.entity_id)
                if state_obj:
                    last_valid_state_value = state_obj.state
                    last_valid_changed_value = state_obj.last_changed.isoformat() if state_obj.last_changed else None
            except Exception as e:
                _LOGGER.debug("StateResolver: Failed to get last_valid values from HA state: %s", e)

        # Set context variables using ReferenceValueManager for consistency
        ReferenceValueManager.set_variable_with_reference_value(
            context, last_valid_state_var, last_valid_state_ref, last_valid_state_value
        )
        ReferenceValueManager.set_variable_with_reference_value(
            context, last_valid_changed_var, last_valid_changed_ref, last_valid_changed_value
        )

        _LOGGER.debug(
            "State resolver: Added last valid context variables %s and %s for sensor %s",
            last_valid_state_var,
            last_valid_changed_var,
            sensor_config.unique_id,
        )

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
            # Use ReferenceValueManager to ensure consistent ReferenceValue handling
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

    def _resolve_sensor_own_state(self, sensor_config: SensorConfig, context: HierarchicalContextDict | None = None) -> Any:
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
            # Use unified state setting method if context is available
            if context is not None:
                return self._set_unified_state_reference(context, sensor_config, None)
            return ReferenceValue(reference=entity_id or "unknown", value=None)

        # Handle alternate states - preserve original values for proper alternate state classification
        if state_value in [STATE_UNKNOWN, STATE_UNAVAILABLE, "None"]:
            _LOGGER.debug(
                "State resolver: Sensor '%s' has alternate state '%s', preserving for alternate handler",
                entity_id,
                state_value,
            )
            # Use unified state setting method if context is available
            if context is not None:
                return self._set_unified_state_reference(context, sensor_config, state_value)
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
            # Use unified state setting method if context is available
            if context is not None:
                return self._set_unified_state_reference(context, sensor_config, numeric_value)
            return ReferenceValue(reference=entity_id or "unknown", value=numeric_value)
        except (ValueError, TypeError):
            # Handle boolean-like states using centralized constants
            true_states = get_current_core_true_states()
            false_states = get_current_core_false_states()

            if state_value in true_states:
                # Return ReferenceValue for boolean true state
                # Use unified state setting method if context is available
                if context is not None:
                    return self._set_unified_state_reference(context, sensor_config, 1.0)
                return ReferenceValue(reference=entity_id or "unknown", value=1.0)
            if state_value in false_states:
                # Return ReferenceValue for boolean false state
                # Use unified state setting method if context is available
                if context is not None:
                    return self._set_unified_state_reference(context, sensor_config, 0.0)
                return ReferenceValue(reference=entity_id or "unknown", value=0.0)

            _LOGGER.warning(
                "State resolver: Cannot convert sensor's own state '%s' (value: '%s') to numeric, defaulting to 0.0",
                entity_id,
                state_value,
            )
            # Return ReferenceValue for default fallback state
            # Use unified state setting method if context is available
            if context is not None:
                return self._set_unified_state_reference(context, sensor_config, 0.0)
            return ReferenceValue(reference=entity_id or "unknown", value=0.0)

    def _is_attribute_formula(self, sensor_config: SensorConfig, formula_config: FormulaConfig) -> bool:
        """Determine if this is an attribute formula (not the main formula)."""
        if not sensor_config.formulas:
            return False
        # If this formula is not the first (main) formula, it's an attribute formula
        return formula_config.id != sensor_config.formulas[0].id
