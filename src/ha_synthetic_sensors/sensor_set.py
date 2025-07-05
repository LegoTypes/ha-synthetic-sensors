"""
SensorSet - Handle for individual sensor set operations.

This module provides a focused interface for working with individual sensor sets,
including CRUD operations on sensors within the set and metadata management.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .config_manager import SensorConfig
from .exceptions import SyntheticSensorsError

if TYPE_CHECKING:
    from .storage_manager import SensorSetMetadata, StorageManager

_LOGGER = logging.getLogger(__name__)


class SensorSet:
    """
    Handle for individual sensor set operations.

    Provides a focused interface for working with a specific sensor set,
    including CRUD operations on sensors within the set.
    """

    def __init__(self, storage_manager: StorageManager, sensor_set_id: str) -> None:
        """
        Initialize SensorSet handle.

        Args:
            storage_manager: StorageManager instance
            sensor_set_id: Sensor set identifier
        """
        self.storage_manager = storage_manager
        self.sensor_set_id = sensor_set_id

    @property
    def metadata(self) -> SensorSetMetadata | None:
        """Get sensor set metadata."""
        return self.storage_manager.get_sensor_set_metadata(self.sensor_set_id)

    @property
    def exists(self) -> bool:
        """Check if sensor set exists."""
        return self.metadata is not None

    def _ensure_exists(self) -> None:
        """Ensure sensor set exists."""
        if not self.exists:
            raise SyntheticSensorsError(f"Sensor set not found: {self.sensor_set_id}")

    # Sensor CRUD Operations

    async def async_add_sensor(self, sensor_config: SensorConfig) -> None:
        """
        Add a sensor to this sensor set.

        Args:
            sensor_config: Sensor configuration to add
        """
        self._ensure_exists()

        metadata = self.metadata
        device_identifier = metadata.device_identifier if metadata else None

        await self.storage_manager.async_store_sensor(
            sensor_config=sensor_config,
            sensor_set_id=self.sensor_set_id,
            device_identifier=device_identifier,
        )

        _LOGGER.info("Added sensor %s to set %s", sensor_config.unique_id, self.sensor_set_id)

    async def async_update_sensor(self, sensor_config: SensorConfig) -> bool:
        """
        Update a sensor in this sensor set.

        Args:
            sensor_config: Updated sensor configuration

        Returns:
            True if updated, False if sensor not found
        """
        self._ensure_exists()

        # Verify sensor belongs to this set
        if not self.has_sensor(sensor_config.unique_id):
            raise SyntheticSensorsError(f"Sensor {sensor_config.unique_id} not found in sensor set {self.sensor_set_id}")

        success = await self.storage_manager.async_update_sensor(sensor_config)
        if success:
            _LOGGER.info("Updated sensor %s in set %s", sensor_config.unique_id, self.sensor_set_id)

        return success

    async def async_remove_sensor(self, unique_id: str) -> bool:
        """
        Remove a sensor from this sensor set.

        Args:
            unique_id: Sensor unique identifier

        Returns:
            True if removed, False if not found
        """
        self._ensure_exists()

        # Verify sensor belongs to this set
        if not self.has_sensor(unique_id):
            _LOGGER.warning("Sensor %s not found in sensor set %s for removal", unique_id, self.sensor_set_id)
            return False

        success = await self.storage_manager.async_delete_sensor(unique_id)
        if success:
            _LOGGER.info("Removed sensor %s from set %s", unique_id, self.sensor_set_id)

        return success

    def get_sensor(self, unique_id: str) -> SensorConfig | None:
        """
        Get a sensor from this sensor set.

        Args:
            unique_id: Sensor unique identifier

        Returns:
            SensorConfig if found and belongs to this set, None otherwise
        """
        self._ensure_exists()

        sensor_config = self.storage_manager.get_sensor(unique_id)

        # Verify it belongs to this sensor set
        if sensor_config and self.has_sensor(unique_id):
            return sensor_config

        return None

    def list_sensors(self) -> list[SensorConfig]:
        """
        List all sensors in this sensor set.

        Returns:
            List of sensor configurations
        """
        self._ensure_exists()

        return self.storage_manager.list_sensors(sensor_set_id=self.sensor_set_id)

    def has_sensor(self, unique_id: str) -> bool:
        """
        Check if sensor belongs to this sensor set.

        Args:
            unique_id: Sensor unique identifier

        Returns:
            True if sensor belongs to this set, False otherwise
        """
        sensors = self.list_sensors()
        return unique_id in [s.unique_id for s in sensors]

    # Bulk Operations

    async def async_replace_sensors(self, sensor_configs: list[SensorConfig]) -> None:
        """
        Replace all sensors in this sensor set.

        Args:
            sensor_configs: New sensor configurations
        """
        self._ensure_exists()

        metadata = self.metadata
        device_identifier = metadata.device_identifier if metadata else None

        # Store new sensors (this replaces existing ones)
        await self.storage_manager.async_store_sensors_bulk(
            sensor_configs=sensor_configs,
            sensor_set_id=self.sensor_set_id,
            device_identifier=device_identifier,
        )

        _LOGGER.info("Replaced %d sensors in set %s", len(sensor_configs), self.sensor_set_id)

    # YAML Operations

    async def async_import_yaml(self, yaml_content: str) -> None:
        """
        Import YAML content to this sensor set, replacing existing sensors.

        Args:
            yaml_content: YAML content to import
        """
        metadata = self.metadata
        device_identifier = metadata.device_identifier if metadata else None

        await self.storage_manager.async_from_yaml(
            yaml_content=yaml_content,
            sensor_set_id=self.sensor_set_id,
            device_identifier=device_identifier,
        )

        _LOGGER.info("Imported YAML to sensor set: %s", self.sensor_set_id)

    def export_yaml(self) -> str:
        """
        Export this sensor set to YAML format.

        Returns:
            YAML content as string
        """
        self._ensure_exists()

        return self.storage_manager.export_yaml(self.sensor_set_id)

    # Sensor Set Management

    async def async_delete(self) -> bool:
        """
        Delete this entire sensor set.

        Returns:
            True if deleted, False if not found
        """
        success = await self.storage_manager.async_delete_sensor_set(self.sensor_set_id)
        if success:
            _LOGGER.info("Deleted sensor set: %s", self.sensor_set_id)

        return success

    # Statistics and Info

    @property
    def sensor_count(self) -> int:
        """Get number of sensors in this set."""
        if not self.exists:
            return 0
        return len(self.list_sensors())

    def get_summary(self) -> dict[str, Any]:
        """
        Get summary information for this sensor set.

        Returns:
            Dictionary with sensor set summary
        """
        if not self.exists:
            return {
                "sensor_set_id": self.sensor_set_id,
                "exists": False,
            }

        metadata = self.metadata
        sensors = self.list_sensors()

        return {
            "sensor_set_id": self.sensor_set_id,
            "exists": True,
            "device_identifier": metadata.device_identifier if metadata else None,
            "name": metadata.name if metadata else None,
            "description": metadata.description if metadata else None,
            "sensor_count": len(sensors),
            "created_at": metadata.created_at if metadata else None,
            "updated_at": metadata.updated_at if metadata else None,
            "sensor_unique_ids": [s.unique_id for s in sensors],
        }

    # Enhanced error handling and validation methods

    def validate_sensor_config(self, sensor_config: SensorConfig) -> list[str]:
        """
        Validate a sensor configuration before adding/updating.

        Args:
            sensor_config: Sensor configuration to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Basic validation
        if not sensor_config.unique_id:
            errors.append("Sensor unique_id is required")

        if not sensor_config.formulas:
            errors.append("Sensor must have at least one formula")

        # Check for formula ID uniqueness within sensor
        formula_ids = [f.id for f in sensor_config.formulas]
        if len(formula_ids) != len(set(formula_ids)):
            errors.append("Sensor has duplicate formula IDs")

        # Validate each formula has required fields
        for formula in sensor_config.formulas:
            if not formula.formula:
                errors.append(f"Formula '{formula.id}' missing formula expression")

        return errors

    def get_sensor_errors(self) -> dict[str, list[str]]:
        """
        Get validation errors for all sensors in this sensor set.

        Returns:
            Dictionary mapping sensor unique_id to list of errors
        """
        self._ensure_exists()

        errors = {}
        sensors = self.list_sensors()

        for sensor in sensors:
            sensor_errors = self.validate_sensor_config(sensor)
            if sensor_errors:
                errors[sensor.unique_id] = sensor_errors

        return errors

    async def async_validate_import(self, yaml_content: str) -> dict[str, Any]:
        """
        Validate YAML content before importing without actually importing.

        Args:
            yaml_content: YAML content to validate

        Returns:
            Dictionary with validation results:
            - "yaml_errors": YAML parsing errors
            - "config_errors": Configuration validation errors
            - "sensor_errors": Per-sensor validation errors
        """
        import yaml as yaml_lib

        from .config_manager import ConfigManager

        validation_results: dict[str, Any] = {
            "yaml_errors": [],
            "config_errors": [],
            "sensor_errors": {},
        }

        try:
            # Parse YAML
            yaml_data = yaml_lib.safe_load(yaml_content)
            if not yaml_data:
                validation_results["yaml_errors"].append("Empty YAML content")
                return validation_results

        except yaml_lib.YAMLError as e:
            validation_results["yaml_errors"].append(f"YAML parsing error: {e}")
            return validation_results

        try:
            # Validate configuration structure
            config_manager = ConfigManager(self.storage_manager.hass)
            config = config_manager.load_from_dict(yaml_data)

            # Validate overall config
            config_errors = config.validate()
            validation_results["config_errors"] = config_errors

            # Validate individual sensors
            for sensor in config.sensors:
                sensor_errors = self.validate_sensor_config(sensor)
                if sensor_errors:
                    validation_results["sensor_errors"][sensor.unique_id] = sensor_errors

        except Exception as e:
            validation_results["config_errors"].append(f"Configuration validation error: {e}")

        return validation_results

    def is_valid(self) -> bool:
        """
        Check if this sensor set and all its sensors are valid.

        Returns:
            True if all sensors are valid, False otherwise
        """
        if not self.exists:
            return False

        errors = self.get_sensor_errors()
        return len(errors) == 0
