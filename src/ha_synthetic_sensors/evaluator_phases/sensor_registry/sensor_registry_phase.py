"""Sensor registry phase for cross-sensor reference management."""

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class SensorRegistryPhase:
    """Sensor registry phase for cross-sensor reference management.

    This phase manages the registry of all sensors and their current values,
    enabling cross-sensor references by name (e.g., base_power_sensor).

    Responsibilities:
    - Register and unregister sensors in the cross-sensor reference registry
    - Update sensor values when they change
    - Provide access to sensor values for cross-sensor references
    - Maintain sensor name to entity ID mappings
    """

    def __init__(self) -> None:
        """Initialize the sensor registry phase."""
        # Registry of all sensors and their current values for cross-sensor references
        # This enables sensors to reference other sensors by name (e.g., base_power_sensor)
        self._sensor_registry: dict[str, float | str | bool] = {}
        self._sensor_entity_id_mapping: dict[str, str] = {}  # sensor_name -> entity_id

    def register_sensor(self, sensor_name: str, entity_id: str, initial_value: float | str | bool = 0.0) -> None:
        """
        Register a sensor in the cross-sensor reference registry.

        This method enables cross-sensor references by tracking all sensors and their values.
        Sensors can then reference each other by name (e.g., base_power_sensor).

        Args:
            sensor_name: The unique name of the sensor (e.g., "base_power_sensor")
            entity_id: The Home Assistant entity ID (e.g., "sensor.base_power_sensor")
            initial_value: The initial value for the sensor
        """
        self._sensor_registry[sensor_name] = initial_value
        self._sensor_entity_id_mapping[sensor_name] = entity_id
        _LOGGER.debug("Registered sensor '%s' (entity_id: %s) with initial value: %s", sensor_name, entity_id, initial_value)

    def update_sensor_value(self, sensor_name: str, value: float | str | bool) -> None:
        """
        Update a sensor's value in the cross-sensor reference registry.

        This method is called when a sensor's value changes, enabling other sensors
        to reference the updated value in their formulas.

        Args:
            sensor_name: The unique name of the sensor
            value: The new value for the sensor
        """
        if sensor_name in self._sensor_registry:
            self._sensor_registry[sensor_name] = value
            _LOGGER.debug("Updated sensor '%s' value to: %s", sensor_name, value)
        else:
            _LOGGER.warning("Attempted to update unregistered sensor '%s'", sensor_name)

    def get_sensor_value(self, sensor_name: str) -> float | str | bool | None:
        """
        Get a sensor's current value from the cross-sensor reference registry.

        This method is used during formula evaluation to resolve cross-sensor references.

        Args:
            sensor_name: The unique name of the sensor

        Returns:
            The current value of the sensor, or None if not found
        """
        return self._sensor_registry.get(sensor_name)

    def unregister_sensor(self, sensor_name: str) -> None:
        """
        Unregister a sensor from the cross-sensor reference registry.

        Args:
            sensor_name: The unique name of the sensor to unregister
        """
        if sensor_name in self._sensor_registry:
            del self._sensor_registry[sensor_name]
            del self._sensor_entity_id_mapping[sensor_name]
            _LOGGER.debug("Unregistered sensor '%s'", sensor_name)

    def get_registered_sensors(self) -> set[str]:
        """
        Get all registered sensor names.

        Returns:
            Set of all registered sensor names
        """
        return set(self._sensor_registry.keys())

    def get_sensor_entity_id(self, sensor_name: str) -> str | None:
        """
        Get the entity ID for a registered sensor.

        Args:
            sensor_name: The unique name of the sensor

        Returns:
            The entity ID of the sensor, or None if not found
        """
        return self._sensor_entity_id_mapping.get(sensor_name)

    def get_sensor_registry(self) -> dict[str, float | str | bool]:
        """
        Get the complete sensor registry.

        Returns:
            Dictionary mapping sensor names to their current values
        """
        return self._sensor_registry.copy()

    def get_sensor_entity_id_mapping(self) -> dict[str, str]:
        """
        Get the complete sensor name to entity ID mapping.

        Returns:
            Dictionary mapping sensor names to their entity IDs
        """
        return self._sensor_entity_id_mapping.copy()

    def clear_registry(self) -> None:
        """Clear all sensors from the registry."""
        self._sensor_registry.clear()
        self._sensor_entity_id_mapping.clear()
        _LOGGER.debug("Cleared sensor registry")

    def is_sensor_registered(self, sensor_name: str) -> bool:
        """
        Check if a sensor is registered in the registry.

        Args:
            sensor_name: The unique name of the sensor

        Returns:
            True if the sensor is registered, False otherwise
        """
        return sensor_name in self._sensor_registry

    def get_registry_stats(self) -> dict[str, Any]:
        """
        Get statistics about the sensor registry.

        Returns:
            Dictionary containing registry statistics
        """
        return {
            "total_sensors": len(self._sensor_registry),
            "registered_sensors": list(self._sensor_registry.keys()),
            "entity_id_mappings": len(self._sensor_entity_id_mapping),
        }
