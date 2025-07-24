"""State attribute resolver for handling state.attribute references."""

from contextlib import suppress
import logging
from typing import Any

from ...config_models import SensorConfig
from ...data_validation import validate_entity_state_value
from ...type_definitions import ContextValue
from .base_resolver import VariableResolver

_LOGGER = logging.getLogger(__name__)


class StateAttributeResolver(VariableResolver):
    """Resolver for state attribute references like 'state.voltage'."""

    def __init__(
        self, sensor_to_backing_mapping: dict[str, str] | None = None, data_provider_callback: Any | None = None
    ) -> None:
        """Initialize the state attribute resolver."""
        self._sensor_to_backing_mapping = sensor_to_backing_mapping or {}
        self._data_provider_callback = data_provider_callback

    def can_resolve(self, variable_name: str, variable_value: str | Any) -> bool:
        """Determine if this resolver can handle state attribute references."""
        if isinstance(variable_value, str):
            return variable_value.startswith("state.")
        return False

    def resolve(self, variable_name: str, variable_value: str | Any, context: dict[str, ContextValue]) -> Any | None:
        """Resolve a state attribute reference."""
        if not isinstance(variable_value, str) or not variable_value.startswith("state."):
            return None

        # Extract the attribute path (e.g., "voltage" or "device_info.manufacturer")
        attribute_path = variable_value.split(".", 1)[1]

        # Get sensor_config from context
        sensor_config_value = context.get("sensor_config")
        if not isinstance(sensor_config_value, SensorConfig):
            _LOGGER.debug("State attribute resolver: no valid sensor_config in context for '%s'", variable_value)
            return None

        sensor_config = sensor_config_value
        _LOGGER.debug("State attribute resolver: resolving '%s' for sensor '%s'", variable_value, sensor_config.unique_id)

        # Try to resolve the attribute
        if attribute_path.startswith("attributes."):
            # Special case: state.attributes.attribute_name -> access backing entity's attributes directly
            result = self._resolve_backing_entity_attribute(variable_value, sensor_config)
        elif "." in attribute_path:
            # Nested attribute (e.g., state.device_info.manufacturer)
            result = self._resolve_nested_state_attribute(variable_value, sensor_config)
        else:
            # Simple attribute (e.g., state.voltage)
            result = self._resolve_simple_state_attribute(variable_value, sensor_config)

        _LOGGER.debug("State attribute resolver: '%s' resolved to %s", variable_value, result)
        return result

    def _resolve_backing_entity_attribute(self, var_value: str, sensor_config: SensorConfig | None) -> Any | None:
        """Resolve state.attributes.attribute_name references to backing entity attributes."""
        if not (sensor_config and var_value.startswith("state.attributes.")):
            return None

        # Extract the attribute path
        attribute_path = self._extract_attribute_path(var_value)
        if not attribute_path:
            return None

        # Get the backing entity ID
        backing_entity_id = self._sensor_to_backing_mapping.get(sensor_config.unique_id)
        if not (backing_entity_id and self._data_provider_callback):
            return None

        try:
            # Get the backing entity data
            entity_data = self._data_provider_callback(backing_entity_id)
            if not (entity_data and entity_data.get("exists")):
                return None

            attributes = entity_data.get("attributes", {})
            result = self._resolve_nested_attribute_value(attributes, attribute_path, backing_entity_id)

            if result is not None:
                _LOGGER.debug(
                    "State attribute resolver: resolved '%s' to %s for entity '%s'",
                    var_value,
                    result,
                    backing_entity_id,
                )
                return result

            _LOGGER.debug(
                "State attribute resolver: attribute '%s' not found in entity '%s'",
                attribute_path,
                backing_entity_id,
            )
        except Exception as e:
            _LOGGER.warning(
                "State attribute resolver: error resolving '%s' for entity '%s': %s",
                var_value,
                backing_entity_id,
                e,
            )

        return None

    def _resolve_simple_state_attribute(self, var_value: str, sensor_config: SensorConfig | None) -> Any | None:
        """Resolve a simple state attribute reference like 'state.voltage'."""
        result = None

        if sensor_config and var_value.startswith("state."):
            # Extract the attribute name
            attribute_name = var_value.split(".", 1)[1]

            # Get the backing entity ID
            backing_entity_id = self._sensor_to_backing_mapping.get(sensor_config.unique_id)
            if backing_entity_id and self._data_provider_callback:
                data_result = self._data_provider_callback(backing_entity_id)
                if data_result and data_result.get("exists"):
                    attributes = data_result.get("attributes", {})
                    if isinstance(attributes, dict) and attribute_name in attributes:
                        attribute_value = attributes[attribute_name]
                        # Validate the attribute value
                        try:
                            result = validate_entity_state_value(attribute_value, f"{backing_entity_id}.{attribute_name}")
                            _LOGGER.debug("State attribute resolver: successfully resolved '%s' to %s", var_value, result)
                        except Exception as e:
                            _LOGGER.debug("State attribute resolver: validation failed for '%s': %s", var_value, e)
                    else:
                        _LOGGER.debug(
                            "State attribute resolver: attribute '%s' not found in attributes: %s",
                            attribute_name,
                            list(attributes.keys()) if isinstance(attributes, dict) else "no attributes",
                        )
                else:
                    _LOGGER.debug("State attribute resolver: data provider returned no result or entity doesn't exist")
            else:
                _LOGGER.debug(
                    "State attribute resolver: no backing entity mapping or data provider for sensor '%s'",
                    sensor_config.unique_id if sensor_config else "None",
                )

        return result

    def _resolve_nested_state_attribute(self, var_value: str, sensor_config: SensorConfig | None) -> Any | None:
        """Resolve nested state attribute references like 'state.device_info.manufacturer'."""
        result = None

        if sensor_config and var_value.startswith("state."):
            # Extract the attribute path (e.g., "device_info.manufacturer")
            attribute_path = var_value.split(".", 1)[1]
            path_parts = attribute_path.split(".")

            # Get the backing entity ID
            backing_entity_id = self._sensor_to_backing_mapping.get(sensor_config.unique_id)
            if backing_entity_id and self._data_provider_callback:
                data_result = self._data_provider_callback(backing_entity_id)
                if data_result and data_result.get("exists"):
                    # Navigate through the nested attributes
                    current_value = data_result.get("attributes", {})

                    for part in path_parts:
                        if not isinstance(current_value, dict) or part not in current_value:
                            # Path not found
                            _LOGGER.debug("Nested attribute path '%s' not found at part '%s'", attribute_path, part)
                            break
                        current_value = current_value[part]
                    else:
                        # All parts found, validate the final value
                        with suppress(Exception):
                            result = validate_entity_state_value(current_value, f"{backing_entity_id}.{attribute_path}")

        return result

    def _extract_attribute_path(self, var_value: str) -> str | None:
        """Extract attribute path from state.attributes.attribute_name."""
        if not var_value.startswith("state.attributes."):
            return None
        parts = var_value.split(".", 2)
        if len(parts) < 3:
            return None
        return parts[2]

    def _resolve_nested_attribute_value(self, attributes: dict[str, Any], attribute_path: str, entity_id: str) -> Any | None:
        """Resolve nested attribute value from attributes dictionary."""
        if "." in attribute_path:
            # Handle nested attribute paths (e.g., "device_info.manufacturer")
            path_parts = attribute_path.split(".")
            current_value = attributes

            for part in path_parts:
                if isinstance(current_value, dict) and part in current_value:
                    current_value = current_value[part]
                else:
                    _LOGGER.debug(
                        "State attribute resolver: nested attribute path '%s' not found in entity '%s'",
                        attribute_path,
                        entity_id,
                    )
                    return None

            return current_value

        # Simple attribute access
        return attributes.get(attribute_path)
