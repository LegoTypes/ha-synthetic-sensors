"""Sensor registry management for the evaluator."""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class EvaluatorSensorRegistry:
    """Manages sensor registration and value tracking for the evaluator."""

    def __init__(self) -> None:
        """Initialize the sensor registry."""
        self._sensors: dict[str, float | str | bool] = {}
        self._sensor_entity_mapping: dict[str, str] = {}

    def register_sensor(self, sensor_name: str, entity_id: str, initial_value: float | str | bool = 0.0) -> None:
        """Register a synthetic sensor for value tracking.

        Args:
            sensor_name: Name of the sensor (from YAML key)
            entity_id: Home Assistant entity ID for the sensor
            initial_value: Initial value for the sensor
        """
        _LOGGER.debug("Registering sensor: %s -> %s with initial value: %s", sensor_name, entity_id, initial_value)
        self._sensors[sensor_name] = initial_value
        self._sensor_entity_mapping[sensor_name] = entity_id

    def update_sensor_value(self, sensor_name: str, value: float | str | bool) -> None:
        """Update the value of a registered sensor.

        Args:
            sensor_name: Name of the sensor
            value: New value for the sensor

        Raises:
            KeyError: If sensor is not registered
        """
        if sensor_name not in self._sensors:
            raise KeyError(f"Sensor '{sensor_name}' is not registered")

        _LOGGER.debug("Updating sensor %s from %s to %s", sensor_name, self._sensors[sensor_name], value)
        self._sensors[sensor_name] = value

    def get_sensor_value(self, sensor_name: str) -> float | str | bool | None:
        """Get the current value of a registered sensor.

        Args:
            sensor_name: Name of the sensor

        Returns:
            Current sensor value, or None if not registered
        """
        return self._sensors.get(sensor_name)

    def unregister_sensor(self, sensor_name: str) -> None:
        """Unregister a sensor and remove it from tracking.

        Args:
            sensor_name: Name of the sensor to unregister
        """
        _LOGGER.debug("Unregistering sensor: %s", sensor_name)
        self._sensors.pop(sensor_name, None)
        self._sensor_entity_mapping.pop(sensor_name, None)

    def get_registered_sensors(self) -> set[str]:
        """Get all registered sensor names.

        Returns:
            Set of registered sensor names
        """
        return set(self._sensors.keys())

    def get_sensor_entity_id(self, sensor_name: str) -> str | None:
        """Get the entity ID for a registered sensor.

        Args:
            sensor_name: Name of the sensor

        Returns:
            Entity ID or None if not registered
        """
        return self._sensor_entity_mapping.get(sensor_name)

    def get_all_sensors_data(self) -> dict[str, Any]:
        """Get all sensor data for debugging/monitoring.

        Returns:
            Dictionary with sensor values and mappings
        """
        return {
            "sensors": dict(self._sensors),
            "entity_mappings": dict(self._sensor_entity_mapping),
            "count": len(self._sensors),
        }
