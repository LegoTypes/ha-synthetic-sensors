"""
Sensor Set Operations Handler for Storage Manager.

This module handles sensor set creation, deletion, and metadata management
operations that were previously part of the main StorageManager class.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .config_manager import ConfigManager
from .config_types import GlobalSettingsDict
from .exceptions import SyntheticSensorsError

if TYPE_CHECKING:
    from .storage_manager import SensorSetMetadata, StorageManager

__all__ = ["SensorSetOpsHandler"]

_LOGGER = logging.getLogger(__name__)


class SensorSetOpsHandler:
    """Handles sensor set operations for storage manager."""

    def __init__(self, storage_manager: StorageManager) -> None:
        """Initialize sensor set operations handler."""
        self.storage_manager = storage_manager

    async def async_create_sensor_set(
        self,
        sensor_set_id: str,
        device_identifier: str | None = None,
        name: str | None = None,
        description: str | None = None,
        global_settings: GlobalSettingsDict | None = None,
    ) -> None:
        """Create a new sensor set.

        Args:
            sensor_set_id: Unique identifier for the sensor set
            device_identifier: Optional device identifier for all sensors in the set
            name: Optional human-readable name for the sensor set
            global_settings: Optional global settings for the sensor set
        """
        data = self.storage_manager.data

        if sensor_set_id in data["sensor_sets"]:
            raise SyntheticSensorsError(f"Sensor set already exists: {sensor_set_id}")

        # Create sensor set entry
        sensor_set_data = {
            "sensor_set_id": sensor_set_id,
            "device_identifier": device_identifier,
            "name": name or sensor_set_id,
            "description": description,
            "created_at": self.storage_manager.get_current_timestamp(),
            "updated_at": self.storage_manager.get_current_timestamp(),
            "sensor_count": 0,
            "global_settings": global_settings or {},
        }

        data["sensor_sets"][sensor_set_id] = sensor_set_data
        await self.storage_manager.async_save()

        _LOGGER.debug("Created sensor set: %s", sensor_set_id)

    async def async_delete_sensor_set(self, sensor_set_id: str) -> bool:
        """Delete a sensor set and all its sensors.

        Args:
            sensor_set_id: ID of the sensor set to delete

        Returns:
            True if deleted, False if not found
        """
        data = self.storage_manager.data

        if sensor_set_id not in data["sensor_sets"]:
            _LOGGER.warning("Sensor set not found for deletion: %s", sensor_set_id)
            return False

        # Delete all sensors in the sensor set
        sensors_to_delete = [
            unique_id
            for unique_id, stored_sensor in data["sensors"].items()
            if stored_sensor.get("sensor_set_id") == sensor_set_id
        ]

        for unique_id in sensors_to_delete:
            del data["sensors"][unique_id]
            _LOGGER.debug("Deleted sensor %s from sensor set %s", unique_id, sensor_set_id)

        # Delete the sensor set
        del data["sensor_sets"][sensor_set_id]
        await self.storage_manager.async_save()

        _LOGGER.debug("Deleted sensor set %s and %d sensors", sensor_set_id, len(sensors_to_delete))
        return True

    def get_sensor_set_metadata(self, sensor_set_id: str) -> SensorSetMetadata | None:
        """Get metadata for a sensor set.

        Args:
            sensor_set_id: ID of the sensor set

        Returns:
            SensorSetMetadata if found, None otherwise
        """
        from .storage_manager import SensorSetMetadata  # pylint: disable=import-outside-toplevel

        data = self.storage_manager.data

        if sensor_set_id not in data["sensor_sets"]:
            return None

        sensor_set_data = data["sensor_sets"][sensor_set_id]

        return SensorSetMetadata(
            sensor_set_id=sensor_set_data["sensor_set_id"],
            device_identifier=sensor_set_data.get("device_identifier"),
            name=sensor_set_data.get("name", sensor_set_id),
            description=sensor_set_data.get("description"),
            created_at=sensor_set_data.get("created_at", ""),
            updated_at=sensor_set_data.get("updated_at", ""),
            sensor_count=sensor_set_data.get("sensor_count", 0),
            global_settings=sensor_set_data.get("global_settings", {}),
        )

    def list_sensor_sets(self, device_identifier: str | None = None) -> list[SensorSetMetadata]:
        """List all sensor sets, optionally filtered by device identifier.

        Args:
            device_identifier: Optional device identifier to filter by

        Returns:
            List of sensor set metadata
        """
        from .storage_manager import SensorSetMetadata  # pylint: disable=import-outside-toplevel

        data = self.storage_manager.data
        sensor_sets = []

        for sensor_set_data in data["sensor_sets"].values():
            # Filter by device identifier if specified
            if device_identifier is not None and sensor_set_data.get("device_identifier") != device_identifier:
                continue

            metadata = SensorSetMetadata(
                sensor_set_id=sensor_set_data["sensor_set_id"],
                device_identifier=sensor_set_data.get("device_identifier"),
                name=sensor_set_data.get("name", sensor_set_data["sensor_set_id"]),
                description=sensor_set_data.get("description"),
                created_at=sensor_set_data.get("created_at", ""),
                updated_at=sensor_set_data.get("updated_at", ""),
                sensor_count=sensor_set_data.get("sensor_count", 0),
                global_settings=sensor_set_data.get("global_settings", {}),
            )
            sensor_sets.append(metadata)

        # Sort by creation time (newest first), handle None/empty values
        return sorted(sensor_sets, key=lambda x: x.created_at or "", reverse=True)

    def sensor_set_exists(self, sensor_set_id: str) -> bool:
        """Check if a sensor set exists.

        Args:
            sensor_set_id: ID of the sensor set to check

        Returns:
            True if the sensor set exists, False otherwise
        """
        data = self.storage_manager.data
        return sensor_set_id in data["sensor_sets"]

    def get_sensor_count(self, sensor_set_id: str | None = None) -> int:
        """Get the number of sensors in a sensor set or total.

        Args:
            sensor_set_id: Optional sensor set ID. If None, returns total count.

        Returns:
            Number of sensors
        """
        data = self.storage_manager.data

        if sensor_set_id is None:
            return len(data["sensors"])

        if sensor_set_id not in data["sensor_sets"]:
            return 0

        return sum(1 for stored_sensor in data["sensors"].values() if stored_sensor.get("sensor_set_id") == sensor_set_id)

    def get_sensor_set_header(self, sensor_set_id: str) -> dict[str, Any]:
        """Get sensor set header data for YAML export/validation.

        Args:
            sensor_set_id: ID of the sensor set

        Returns:
            Dictionary containing sensor set header data
        """
        data = self.storage_manager.data

        if sensor_set_id not in data["sensor_sets"]:
            return {}

        sensor_set_data = data["sensor_sets"][sensor_set_id]
        global_settings = sensor_set_data.get("global_settings", {})

        # Return a copy of global settings as the header
        return dict(global_settings)

    async def async_from_yaml(
        self,
        yaml_content: str,
        sensor_set_id: str,
        device_identifier: str | None = None,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        """Import YAML content into a sensor set.

        Args:
            yaml_content: YAML content to import
            sensor_set_id: Target sensor set ID
            device_identifier: Optional device identifier override
            replace_existing: Whether to replace existing sensor set

        Returns:
            Dictionary with import results
        """
        config_manager = ConfigManager(self.storage_manager.hass)
        config = config_manager.load_from_yaml(yaml_content)

        # Use the existing async_from_config method to avoid code duplication
        if replace_existing and self.sensor_set_exists(sensor_set_id):
            await self.async_delete_sensor_set(sensor_set_id)

        await self.storage_manager.async_from_config(config, sensor_set_id, device_identifier)
        stored_sensors = [sensor_config.unique_id for sensor_config in config.sensors]

        return {
            "sensor_set_id": sensor_set_id,
            "sensors_imported": len(stored_sensors),
            "sensor_unique_ids": stored_sensors,
            "global_settings": config.global_settings,
        }
