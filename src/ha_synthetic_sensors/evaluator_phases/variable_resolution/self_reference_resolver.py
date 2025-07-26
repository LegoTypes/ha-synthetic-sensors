"""Self-reference resolver for handling entity ID self-references."""

import logging
from typing import Any

from ...constants_formula import is_ha_state_value, is_ha_unknown_equivalent, normalize_ha_state_value
from ...data_validation import validate_data_provider_result
from ...exceptions import DataValidationError, FormulaEvaluationError
from .base_resolver import VariableResolver

_LOGGER = logging.getLogger(__name__)


class SelfReferenceResolver(VariableResolver):
    """Resolver for entity ID self-references (sensor.sensor_key patterns)."""

    def __init__(self) -> None:
        """Initialize the self-reference resolver."""
        self._dependency_handler: Any = None
        self._sensor_to_backing_mapping: dict[str, str] = {}
        self._sensor_registry_phase: Any = None

    def set_dependency_handler(self, dependency_handler: Any) -> None:
        """Set the dependency handler for entity resolution."""
        self._dependency_handler = dependency_handler

    def set_sensor_to_backing_mapping(self, mapping: dict[str, str]) -> None:
        """Set the sensor to backing entity mapping."""
        self._sensor_to_backing_mapping = mapping

    def set_sensor_registry_phase(self, sensor_registry_phase: Any) -> None:
        """Set the sensor registry phase for cross-sensor references."""
        self._sensor_registry_phase = sensor_registry_phase

    def can_resolve(self, variable_name: str, variable_value: str | Any) -> bool:
        """Determine if this resolver can handle entity ID self-reference patterns."""
        if not isinstance(variable_value, str):
            return False

        # Only handle entity ID patterns (sensor.sensor_key)
        # Raw sensor keys are handled by auto-injection as variables
        if variable_value.startswith("sensor."):
            sensor_key = variable_value[7:]  # Remove "sensor." prefix
            if sensor_key in self._sensor_to_backing_mapping:
                return True

        return False

    def resolve(self, variable_name: str, variable_value: str | Any, context: dict[str, Any]) -> Any | None:
        """Resolve an entity ID self-reference to either backing entity value or sensor calculated result."""
        if not isinstance(variable_value, str):
            return None

        # Only handle entity ID references (sensor.sensor_key)
        if not variable_value.startswith("sensor."):
            return None

        sensor_key = variable_value[7:]  # Remove "sensor." prefix
        if sensor_key not in self._sensor_to_backing_mapping:
            return None

        _LOGGER.debug(
            "Self-reference resolver: detected entity ID self-reference '%s' (sensor key: '%s')", variable_value, sensor_key
        )

        # Check if we're in an attribute formula context
        # In attribute formulas, we should have access to previously calculated attributes
        # In main formulas, we shouldn't have any attributes in context
        state_value = context.get("state")

        # Look for any keys that could be attribute names (not 'state' or entity IDs)
        # Exclude HA constants from being considered as attribute indicators
        attribute_indicators = []
        for key in context:
            if self._is_attribute_indicator(key):
                attribute_indicators.append(key)

        _LOGGER.debug(
            "Self-reference resolver: context analysis - state=%s, attribute_indicators=%s", state_value, attribute_indicators
        )

        # If we have attribute indicators, we're likely in an attribute context
        if attribute_indicators:
            _LOGGER.debug(
                "Self-reference resolver: detected attribute context based on attribute indicators: %s", attribute_indicators
            )
            # In attribute context, use the state value which should be the main sensor's calculated result
            if state_value is not None and isinstance(state_value, (int, float)):
                return state_value
            raise FormulaEvaluationError(
                f"Self-reference resolver: in attribute context but state value is invalid: {state_value}"
            )

        # Default: resolve to backing entity value (main formula context)
        _LOGGER.debug("Self-reference resolver: detected main formula context, resolving to backing entity")
        backing_entity_id = self._sensor_to_backing_mapping[sensor_key]
        return self._resolve_backing_entity_value(backing_entity_id, variable_value)

    def _is_attribute_indicator(self, key: str) -> bool:
        """Check if a context key is an attribute indicator."""

        # Define exclusion rules in a data-driven way
        def is_state(k: str) -> bool:
            return k == "state"

        def is_sensor_entity(k: str) -> bool:
            return k.startswith("sensor.")

        def is_binary_sensor_entity(k: str) -> bool:
            return k.startswith("binary_sensor.")

        def is_config_key(k: str) -> bool:
            return k in ["sensor_config", "formula_config"]

        def is_state_constant(k: str) -> bool:
            return k.startswith("STATE_")

        def is_conf_constant(k: str) -> bool:
            return k.startswith("CONF_")

        def is_device_class_enum(k: str) -> bool:
            return k.endswith("DeviceClass")

        def is_state_enum(k: str) -> bool:
            return k.endswith("State")

        def is_state_class_enum(k: str) -> bool:
            return k.endswith("StateClass")

        exclusion_rules = [
            is_state,
            is_sensor_entity,
            is_binary_sensor_entity,
            is_config_key,
            is_state_constant,
            is_conf_constant,
            is_device_class_enum,
            is_state_enum,
            is_state_class_enum,
        ]

        # Check if any exclusion rule matches
        return not any(rule(key) for rule in exclusion_rules)

    def _resolve_calculated_result(self, sensor_key: str, original_reference: str) -> Any:
        """Resolve the main sensor's calculated result from the sensor registry."""
        # Use the sensor registry to get the calculated value
        if self._sensor_registry_phase and hasattr(self._sensor_registry_phase, "get_sensor_value"):
            try:
                calculated_value = self._sensor_registry_phase.get_sensor_value(sensor_key)
                if calculated_value is not None:
                    _LOGGER.debug(
                        "Self-reference resolver: resolved '%s' to calculated result: %s", original_reference, calculated_value
                    )
                    return calculated_value
                _LOGGER.debug(
                    "Self-reference resolver: calculated result for '%s' is None, sensor may not be evaluated yet",
                    sensor_key,
                )
                return None
            except Exception as e:
                raise FormulaEvaluationError(f"Error resolving calculated result for sensor '{sensor_key}': {e}") from e
        else:
            _LOGGER.debug(
                "Self-reference resolver: no sensor registry available to resolve calculated result for '%s'", sensor_key
            )
            return None

    def _resolve_backing_entity_value(self, backing_entity_id: str, original_reference: str) -> Any:
        """Resolve the backing entity value using data provider or HA lookups."""
        # Try data provider first
        data_provider_result = self._try_data_provider_resolution(backing_entity_id, original_reference)
        if data_provider_result is not None:
            return data_provider_result

        # Try HA state lookup
        ha_state_result = self._try_ha_state_resolution(backing_entity_id, original_reference)
        if ha_state_result is not None:
            return ha_state_result

        # Could not resolve backing entity
        _LOGGER.debug(
            "Self-reference resolver: could not resolve backing entity '%s' for '%s'", backing_entity_id, original_reference
        )
        return None

    def _try_data_provider_resolution(self, backing_entity_id: str, original_reference: str) -> Any:
        """Try resolving via data provider callback."""
        if not (
            self._dependency_handler
            and hasattr(self._dependency_handler, "should_use_data_provider")
            and self._dependency_handler.should_use_data_provider(backing_entity_id)
        ):
            return None

        data_provider_callback = self._dependency_handler.data_provider_callback
        if not (data_provider_callback and callable(data_provider_callback)):
            return None

        try:
            result = data_provider_callback(backing_entity_id)
            validated_result = validate_data_provider_result(result, f"data provider for '{backing_entity_id}'")

            if not validated_result.get("exists"):
                return None

            value = validated_result.get("value")
            return self._process_resolved_value(value, backing_entity_id, original_reference, "data provider")

        except DataValidationError:
            raise
        except Exception as e:
            _LOGGER.warning("Error resolving backing entity '%s' via data provider: %s", backing_entity_id, e)
            return None

    def _try_ha_state_resolution(self, backing_entity_id: str, original_reference: str) -> Any:
        """Try resolving via HA state lookup."""
        if not (
            self._dependency_handler
            and hasattr(self._dependency_handler, "hass")
            and hasattr(self._dependency_handler, "allow_ha_lookups")
            and self._dependency_handler.allow_ha_lookups
        ):
            return None

        try:
            hass = self._dependency_handler.hass
            if not (hass and hasattr(hass, "states")):
                return None

            hass_state = hass.states.get(backing_entity_id)
            if hass_state is None:
                return None

            state_value = hass_state.state
            return self._process_resolved_value(state_value, backing_entity_id, original_reference, "HASS")

        except Exception as e:
            _LOGGER.warning("Error resolving backing entity '%s' via HASS: %s", backing_entity_id, e)
            return None

    def _process_resolved_value(self, value: Any, backing_entity_id: str, original_reference: str, source: str) -> Any:
        """Process a resolved value from either data provider or HA state."""
        if value is None:
            _LOGGER.debug(
                "Self-reference resolver: backing entity '%s' has None value, returning unknown state",
                backing_entity_id,
            )
            return "unknown"

        # Handle special Home Assistant state values
        if isinstance(value, str) and (is_ha_state_value(value) or is_ha_unknown_equivalent(value)):
            _LOGGER.debug(
                "Self-reference resolver: backing entity '%s' has %s state via %s",
                backing_entity_id,
                value,
                source,
            )
            return normalize_ha_state_value(value)

        # For HA state, try to convert to numeric
        if source == "HASS" and isinstance(value, str):
            try:
                numeric_value = float(value) if "." in value else int(value)
                _LOGGER.debug(
                    "Self-reference resolver: resolved '%s' to %s via backing entity '%s' (%s)",
                    original_reference,
                    numeric_value,
                    backing_entity_id,
                    source,
                )
                return numeric_value
            except ValueError:
                _LOGGER.debug(
                    "Self-reference resolver: resolved '%s' to '%s' (non-numeric) via backing entity '%s' (%s)",
                    original_reference,
                    value,
                    backing_entity_id,
                    source,
                )
                return value

        # For data provider results, use value as-is
        _LOGGER.debug(
            "Self-reference resolver: resolved '%s' to %s via backing entity '%s' (%s)",
            original_reference,
            value,
            backing_entity_id,
            source,
        )
        return value
