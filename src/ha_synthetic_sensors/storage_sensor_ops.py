"""
Sensor CRUD Operations Handler for Storage Manager.

This module handles sensor create, read, update, and delete operations
that were previously part of the main StorageManager class.
"""

from __future__ import annotations

from dataclasses import asdict
import logging
from typing import TYPE_CHECKING, Any

from .config_models import FormulaConfig, SensorConfig
from .exceptions import SyntheticSensorsError

if TYPE_CHECKING:
    from .storage_manager import StorageManager

__all__ = ["SensorOpsHandler"]

_LOGGER = logging.getLogger(__name__)


class SensorOpsHandler:
    """Handles sensor CRUD operations for storage manager."""

    def __init__(self, storage_manager: StorageManager) -> None:
        """Initialize sensor operations handler."""
        self.storage_manager = storage_manager

    async def async_store_sensor(
        self,
        sensor_config: SensorConfig,
        sensor_set_id: str,
        device_identifier: str | None = None,
    ) -> None:
        """Store a sensor configuration.

        Args:
            sensor_config: Sensor configuration to store
            sensor_set_id: ID of the sensor set to store the sensor in
            device_identifier: Optional device identifier override

        Raises:
            SyntheticSensorsError: If validation fails
        """
        data = self.storage_manager.data

        # Validate sensor set exists
        if sensor_set_id not in data["sensor_sets"]:
            raise SyntheticSensorsError(f"Sensor set not found: {sensor_set_id}")

        # Override device identifier if provided
        if device_identifier:
            sensor_config.device_identifier = device_identifier

        # Validate the sensor configuration
        errors = self.storage_manager.validator.validate_sensor_with_context(sensor_config, sensor_set_id)
        if errors:
            raise SyntheticSensorsError(f"Sensor validation failed: {'; '.join(errors)}")

        from .storage_manager import StoredSensorDict  # pylint: disable=import-outside-toplevel

        # Create stored sensor entry
        stored_sensor: StoredSensorDict = {
            "unique_id": sensor_config.unique_id,
            "sensor_set_id": sensor_set_id,
            "device_identifier": sensor_config.device_identifier,
            "created_at": self.storage_manager.get_current_timestamp(),
            "updated_at": self.storage_manager.get_current_timestamp(),
            "config_data": self.storage_manager.serialize_sensor_config(sensor_config),
        }

        # Store sensor
        data["sensors"][sensor_config.unique_id] = stored_sensor

        # Update sensor set metadata
        sensor_set_data = data["sensor_sets"][sensor_set_id]
        sensor_set_data["updated_at"] = self.storage_manager.get_current_timestamp()
        sensor_set_data["sensor_count"] = self.storage_manager.get_sensor_count(sensor_set_id)

        await self.storage_manager.async_save()
        _LOGGER.debug("Stored sensor: %s in sensor set: %s", sensor_config.unique_id, sensor_set_id)

    async def async_store_sensors_bulk(
        self,
        sensor_configs: list[SensorConfig],
        sensor_set_id: str,
        device_identifier: str | None = None,
    ) -> dict[str, Any]:
        """Store multiple sensor configurations in bulk.

        Args:
            sensor_configs: List of sensor configurations to store
            sensor_set_id: ID of the sensor set to store sensors in
            device_identifier: Optional device identifier override

        Returns:
            Dictionary with bulk operation results
        """
        from .storage_manager import StoredSensorDict  # pylint: disable=import-outside-toplevel

        data = self.storage_manager.data

        # Validate sensor set exists
        if sensor_set_id not in data["sensor_sets"]:
            raise SyntheticSensorsError(f"Sensor set not found: {sensor_set_id}")

        stored_sensors = []
        current_time = self.storage_manager.get_current_timestamp()

        for sensor_config in sensor_configs:
            # Override device identifier if provided
            if device_identifier:
                sensor_config.device_identifier = device_identifier

            # Validate the sensor configuration
            errors = self.storage_manager.validator.validate_sensor_with_context(sensor_config, sensor_set_id)
            if errors:
                raise SyntheticSensorsError(f"Sensor validation failed: {'; '.join(errors)}")

            # Create stored sensor entry
            stored_sensor: StoredSensorDict = {
                "unique_id": sensor_config.unique_id,
                "sensor_set_id": sensor_set_id,
                "device_identifier": sensor_config.device_identifier,
                "created_at": current_time,
                "updated_at": current_time,
                "config_data": self.storage_manager.serialize_sensor_config(sensor_config),
            }

            # Store sensor
            data["sensors"][sensor_config.unique_id] = stored_sensor
            stored_sensors.append(sensor_config.unique_id)

        # Update sensor set metadata
        sensor_set_data = data["sensor_sets"][sensor_set_id]
        sensor_set_data["updated_at"] = current_time
        sensor_set_data["sensor_count"] = self.storage_manager.get_sensor_count(sensor_set_id)

        await self.storage_manager.async_save()

        _LOGGER.debug("Stored %d sensors in sensor set: %s", len(stored_sensors), sensor_set_id)

        return {
            "sensor_set_id": sensor_set_id,
            "sensors_stored": len(stored_sensors),
            "sensor_unique_ids": stored_sensors,
        }

    def get_sensor(self, unique_id: str) -> SensorConfig | None:
        """Get a sensor configuration by unique ID.

        Args:
            unique_id: Unique identifier of the sensor

        Returns:
            SensorConfig if found, None otherwise
        """
        data = self.storage_manager.data

        if unique_id not in data["sensors"]:
            return None

        stored_sensor = data["sensors"][unique_id]
        return self.storage_manager.deserialize_sensor_config(stored_sensor["config_data"])

    def list_sensors(
        self,
        sensor_set_id: str | None = None,
        device_identifier: str | None = None,
        include_config: bool = False,
    ) -> list[SensorConfig]:
        """List sensors with optional filtering.

        Args:
            sensor_set_id: Optional sensor set ID to filter by
            device_identifier: Optional device identifier to filter by
            include_config: Whether to include full sensor configuration (deprecated, always True now)

        Returns:
            List of SensorConfig objects
        """
        data = self.storage_manager.data
        sensors = []

        for _, stored_sensor in data["sensors"].items():
            # Apply filters
            if sensor_set_id is not None and stored_sensor.get("sensor_set_id") != sensor_set_id:
                continue

            if device_identifier is not None and stored_sensor.get("device_identifier") != device_identifier:
                continue

            # Deserialize and add sensor config
            config_data = stored_sensor.get("config_data")
            if config_data:
                sensor_config = self.storage_manager.deserialize_sensor_config(config_data)
                sensors.append(sensor_config)

        # Sort by unique_id for consistent ordering
        return sorted(sensors, key=lambda x: x.unique_id)

    async def async_update_sensor(self, sensor_config: SensorConfig) -> bool:
        """Update an existing sensor configuration.

        Args:
            sensor_config: Updated sensor configuration

        Returns:
            True if updated, False if not found

        Raises:
            SyntheticSensorsError: If validation fails
        """
        data = self.storage_manager.data

        if sensor_config.unique_id not in data["sensors"]:
            _LOGGER.warning("Sensor not found for update: %s", sensor_config.unique_id)
            return False

        stored_sensor = data["sensors"][sensor_config.unique_id]
        sensor_set_id = stored_sensor["sensor_set_id"]

        # Validate the sensor configuration
        errors = self.storage_manager.validator.validate_sensor_with_context(sensor_config, sensor_set_id)
        if errors:
            raise SyntheticSensorsError(f"Sensor update validation failed: {'; '.join(errors)}")

        # Update stored sensor
        stored_sensor["updated_at"] = self.storage_manager.get_current_timestamp()
        stored_sensor["device_identifier"] = sensor_config.device_identifier
        stored_sensor["config_data"] = self.storage_manager.serialize_sensor_config(sensor_config)

        # Update sensor set metadata
        if sensor_set_id in data["sensor_sets"]:
            data["sensor_sets"][sensor_set_id]["updated_at"] = self.storage_manager.get_current_timestamp()

        await self.storage_manager.async_save()

        _LOGGER.debug("Updated sensor: %s", sensor_config.unique_id)
        return True

    async def async_delete_sensor(self, unique_id: str) -> bool:
        """Delete a sensor configuration.

        Args:
            unique_id: Unique identifier of the sensor to delete

        Returns:
            True if deleted, False if not found
        """
        data = self.storage_manager.data

        if unique_id not in data["sensors"]:
            _LOGGER.warning("Sensor not found for deletion: %s", unique_id)
            return False

        stored_sensor = data["sensors"][unique_id]
        sensor_set_id = stored_sensor.get("sensor_set_id")

        # Delete sensor
        del data["sensors"][unique_id]

        # Update sensor set metadata
        if sensor_set_id and sensor_set_id in data["sensor_sets"]:
            sensor_set_data = data["sensor_sets"][sensor_set_id]
            sensor_set_data["updated_at"] = self.storage_manager.get_current_timestamp()
            sensor_set_data["sensor_count"] = self.storage_manager.get_sensor_count(sensor_set_id)

        await self.storage_manager.async_save()

        _LOGGER.debug("Deleted sensor: %s", unique_id)
        return True

    def serialize_sensor_config(self, sensor_config: SensorConfig) -> Any:
        """Serialize sensor configuration for storage.

        Args:
            sensor_config: Sensor configuration to serialize

        Returns:
            Serialized sensor configuration
        """

        def set_to_list(obj: Any) -> Any:
            """Convert sets to lists for JSON serialization."""
            if isinstance(obj, set):
                return list(obj)
            if isinstance(obj, dict):
                return {k: set_to_list(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [set_to_list(item) for item in obj]
            return obj

        # Convert to dict and handle sets
        config_dict = asdict(sensor_config)
        return set_to_list(config_dict)

    def deserialize_sensor_config(self, config_data: dict[str, Any]) -> SensorConfig:
        """Deserialize sensor configuration from storage.

        Args:
            config_data: Serialized sensor configuration data

        Returns:
            Deserialized sensor configuration
        """

        def list_to_set(obj: Any) -> Any:
            """Convert lists back to sets where appropriate."""
            if isinstance(obj, dict):
                # Convert dependencies list back to set if present
                if "dependencies" in obj and isinstance(obj["dependencies"], list):
                    obj["dependencies"] = set(obj["dependencies"])
                return {k: list_to_set(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [list_to_set(item) for item in obj]
            return obj

        # Convert lists back to sets and create SensorConfig
        processed_data = list_to_set(config_data)

        # Convert formula dictionaries back to FormulaConfig objects
        if "formulas" in processed_data:
            formulas = []
            for formula_data in processed_data["formulas"]:
                formulas.append(FormulaConfig(**formula_data))
            processed_data["formulas"] = formulas

        return SensorConfig(**processed_data)
