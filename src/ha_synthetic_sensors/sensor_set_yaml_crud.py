"""
YAML-based CRUD operations for sensor sets.

This module provides methods for creating, updating, and managing sensors
using YAML string configurations.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import yaml as yaml_lib

from .config_manager import ConfigManager
from .config_models import SensorConfig
from .exceptions import SyntheticSensorsError

if TYPE_CHECKING:
    from .sensor_set import SensorSet

_LOGGER = logging.getLogger(__name__)


class SensorSetYamlCrud:
    """Handles YAML-based CRUD operations for sensor sets."""

    def __init__(self, sensor_set: SensorSet) -> None:
        """Initialize YAML CRUD handler.

        Args:
            sensor_set: SensorSet instance to operate on
        """
        self.sensor_set = sensor_set

    def _parse_sensor_yaml(self, sensor_yaml: str, sensor_set_id: str) -> SensorConfig:
        """
        Parse individual sensor YAML string into SensorConfig.

        Args:
            sensor_yaml: YAML string containing sensor configuration WITH sensor key
                        Example:
                        ```
                        sensor_key:
                          name: My Sensor
                          entity_id: sensor.my_sensor
                          formula: state * 1.1
                        ```
            sensor_set_id: Sensor set ID for context

        Returns:
            SensorConfig: Parsed sensor configuration

        Raises:
            SyntheticSensorsError: If YAML parsing or validation fails
        """
        try:
            # Parse the raw YAML
            sensor_data = yaml_lib.safe_load(sensor_yaml)

            if not sensor_data or not isinstance(sensor_data, dict):
                raise SyntheticSensorsError("Sensor YAML must be a dictionary")

            # The YAML should have exactly one top-level key (the sensor key)
            if len(sensor_data) != 1:
                raise SyntheticSensorsError("Sensor YAML must contain exactly one sensor definition")

            sensor_key = next(iter(sensor_data.keys()))
            sensor_config = sensor_data[sensor_key]

            # Create a minimal config with this sensor to leverage existing parsing
            minimal_config = {"version": "1.0", "sensors": {sensor_key: sensor_config}}

            # Get global settings from sensor set for parsing context
            global_settings = self.sensor_set.get_global_settings()
            if global_settings:
                minimal_config["global_settings"] = global_settings

            # Use ConfigManager to parse with full validation
            config_manager = ConfigManager(self.sensor_set.storage_manager.hass)
            config_yaml = yaml_lib.dump(minimal_config)
            parsed_config = config_manager.load_from_yaml(config_yaml)

            if not parsed_config.sensors:
                raise SyntheticSensorsError("Failed to parse sensor from YAML")

            return parsed_config.sensors[0]

        except Exception as exc:
            raise SyntheticSensorsError(f"Failed to parse sensor YAML: {exc}") from exc

    async def async_add_sensor_from_yaml(self, sensor_yaml: str) -> None:
        """
        Add a sensor to this sensor set from YAML string.

        Args:
            sensor_yaml: YAML string containing sensor configuration WITH sensor key
                        Example:
                        ```
                        my_power_sensor:
                          name: My Power Sensor
                          entity_id: sensor.test_device_power
                          formula: state * 1.1
                          attributes:
                            calculation_type: net_power
                          metadata:
                            unit_of_measurement: W
                            device_class: power
                        ```

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist, YAML is invalid, or sensor already exists
        """
        self.sensor_set.ensure_exists()

        sensor_config = self._parse_sensor_yaml(sensor_yaml, self.sensor_set.sensor_set_id)

        # Check if sensor already exists
        if self.sensor_set.has_sensor(sensor_config.unique_id):
            raise SyntheticSensorsError(
                f"Sensor {sensor_config.unique_id} already exists in sensor set {self.sensor_set.sensor_set_id}"
            )

        await self.sensor_set.async_add_sensor(sensor_config)

    async def async_update_sensor_from_yaml(self, sensor_yaml: str) -> bool:
        """
        Update a sensor in this sensor set from YAML string.

        Args:
            sensor_yaml: YAML string containing updated sensor configuration WITH sensor key
                        The sensor key must match an existing sensor.

        Returns:
            True if updated, False if sensor not found

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist or YAML is invalid
        """
        self.sensor_set.ensure_exists()

        sensor_config = self._parse_sensor_yaml(sensor_yaml, self.sensor_set.sensor_set_id)

        # Verify sensor exists
        if not self.sensor_set.has_sensor(sensor_config.unique_id):
            return False

        return await self.sensor_set.async_update_sensor(sensor_config)

    def add_sensor_from_yaml(self, sensor_yaml: str) -> None:
        """
        Add a sensor to this sensor set from YAML string (synchronous version).

        For async operations, use async_add_sensor_from_yaml().

        Args:
            sensor_yaml: YAML string containing sensor configuration WITH sensor key

        Raises:
            SyntheticSensorsError: If used in async context, sensor set doesn't exist,
                                  YAML is invalid, or sensor already exists
        """
        try:
            asyncio.get_running_loop()
            raise SyntheticSensorsError("Use async_add_sensor_from_yaml() in async context")
        except RuntimeError:
            # No running loop, safe to use run_until_complete
            asyncio.run(self.async_add_sensor_from_yaml(sensor_yaml))

    def update_sensor_from_yaml(self, sensor_yaml: str) -> bool:
        """
        Update a sensor in this sensor set from YAML string (synchronous version).

        For async operations, use async_update_sensor_from_yaml().

        Args:
            sensor_yaml: YAML string containing updated sensor configuration WITH sensor key

        Returns:
            True if sensor was updated, False if not found

        Raises:
            SyntheticSensorsError: If used in async context, sensor set doesn't exist, or YAML is invalid
        """
        try:
            asyncio.get_running_loop()
            raise SyntheticSensorsError("Use async_update_sensor_from_yaml() in async context")
        except RuntimeError:
            # No running loop, safe to use run_until_complete
            return asyncio.run(self.async_update_sensor_from_yaml(sensor_yaml))
