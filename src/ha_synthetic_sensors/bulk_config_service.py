"""
Bulk Config Service - High-level bulk configuration management for synthetic sensors.

This module provides a high-level service interface for bulk configuration management,
including sensor set operations, device association, and batch processing capabilities.
Used by integrations to manage large numbers of synthetic sensors efficiently.

Phase 1 Implementation: Basic bulk operations for fresh installations.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .config_converter import ConfigConverter
from .config_manager import SensorConfig
from .exceptions import SyntheticSensorsError
from .storage_manager import SensorSetMetadata, StorageManager

_LOGGER = logging.getLogger(__name__)


class BulkConfigService:
    """
    High-level service for bulk configuration management.

    Provides a simplified interface for integrations to manage large numbers
    of synthetic sensors through sensor sets, device association, and batch
    operations while abstracting away storage implementation details.
    """

    def __init__(self, hass: HomeAssistant, storage_key: str = "synthetic_sensors") -> None:
        """
        Initialize the BulkConfigService.

        Args:
            hass: Home Assistant instance
            storage_key: Storage key for HA storage system
        """
        self.hass = hass
        self.storage_manager = StorageManager(hass, storage_key)
        self.config_converter = ConfigConverter(self.storage_manager)
        self._loaded = False

    async def async_initialize(self) -> None:
        """Initialize the service and load storage."""
        if not self._loaded:
            await self.storage_manager.async_load()
            self._loaded = True
            _LOGGER.info("BulkConfigService initialized")

    def _ensure_initialized(self) -> None:
        """Ensure service is initialized."""
        if not self._loaded:
            raise SyntheticSensorsError("Service not initialized. Call async_initialize() first.")

    # Device-based Sensor Set Management

    async def async_create_device_sensor_set(
        self,
        device_identifier: str,
        device_name: str | None = None,
        description: str | None = None,
    ) -> str:
        """
        Create a sensor set associated with a specific device.

        Args:
            device_identifier: Unique device identifier
            device_name: Human-readable device name
            description: Description of the sensor set

        Returns:
            Generated sensor_set_id
        """
        self._ensure_initialized()

        name = device_name or f"Device {device_identifier}"
        desc = description or f"Synthetic sensors for device {device_identifier}"

        # Generate sensor_set_id based on device_identifier
        import uuid

        sensor_set_id = f"device_{device_identifier}_{uuid.uuid4().hex[:8]}"

        await self.storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier=device_identifier,
            name=name,
            description=desc,
        )

        _LOGGER.info(
            "Created device sensor set: %s for device %s",
            sensor_set_id,
            device_identifier,
        )
        return sensor_set_id

    async def async_get_or_create_device_sensor_set(
        self,
        device_identifier: str,
        device_name: str | None = None,
        description: str | None = None,
    ) -> str:
        """
        Get existing sensor set for device or create new one.

        Args:
            device_identifier: Unique device identifier
            device_name: Human-readable device name
            description: Description of the sensor set

        Returns:
            Sensor set ID (existing or newly created)
        """
        self._ensure_initialized()

        # Check for existing sensor set for this device
        existing_sets = self.storage_manager.list_sensor_sets(device_identifier)

        if existing_sets:
            # Return the first existing set for this device
            sensor_set_id = existing_sets[0].sensor_set_id
            _LOGGER.debug(
                "Found existing sensor set %s for device %s",
                sensor_set_id,
                device_identifier,
            )
            return sensor_set_id
        else:
            # Create new sensor set
            return await self.async_create_device_sensor_set(
                device_identifier,
                device_name,
                description,
            )

    async def async_delete_device_sensors(self, device_identifier: str) -> int:
        """
        Delete all sensor sets and sensors for a device.

        Args:
            device_identifier: Device identifier

        Returns:
            Number of sensor sets deleted
        """
        self._ensure_initialized()

        device_sets = self.storage_manager.list_sensor_sets(device_identifier)
        deleted_count = 0

        for sensor_set in device_sets:
            await self.storage_manager.async_delete_sensor_set(sensor_set.sensor_set_id)
            deleted_count += 1

        _LOGGER.info(
            "Deleted %d sensor sets for device %s",
            deleted_count,
            device_identifier,
        )
        return deleted_count

    # Bulk Sensor Configuration

    async def async_add_sensors_to_device(
        self,
        device_identifier: str,
        sensor_configs: list[SensorConfig],
        device_name: str | None = None,
    ) -> str:
        """
        Add multiple sensors to a device in bulk.

        Args:
            device_identifier: Device to associate sensors with
            sensor_configs: List of sensor configurations to add
            device_name: Human-readable device name

        Returns:
            Sensor set ID where sensors were stored
        """
        self._ensure_initialized()

        # Get or create sensor set for device
        sensor_set_id = await self.async_get_or_create_device_sensor_set(
            device_identifier,
            device_name,
        )

        # Store sensors in bulk
        await self.storage_manager.async_store_sensors_bulk(
            sensor_configs,
            sensor_set_id,
            device_identifier,
        )

        _LOGGER.info(
            "Added %d sensors to device %s (sensor_set: %s)",
            len(sensor_configs),
            device_identifier,
            sensor_set_id,
        )
        return sensor_set_id

    async def async_replace_device_sensors(
        self,
        device_identifier: str,
        sensor_configs: list[SensorConfig],
        device_name: str | None = None,
    ) -> str:
        """
        Replace all sensors for a device with new configurations.

        Args:
            device_identifier: Device identifier
            sensor_configs: New sensor configurations
            device_name: Human-readable device name

        Returns:
            Sensor set ID where sensors were stored
        """
        self._ensure_initialized()

        # Delete existing sensors for device
        await self.async_delete_device_sensors(device_identifier)

        # Add new sensors
        sensor_set_id = await self.async_add_sensors_to_device(
            device_identifier,
            sensor_configs,
            device_name,
        )

        _LOGGER.info(
            "Replaced sensors for device %s with %d new sensors",
            device_identifier,
            len(sensor_configs),
        )
        return sensor_set_id

    # YAML Integration Support

    async def async_import_yaml_for_device(
        self,
        device_identifier: str,
        yaml_content: str,
        device_name: str | None = None,
        replace_existing: bool = False,
    ) -> str:
        """
        Import YAML configuration for a specific device.

        Args:
            device_identifier: Device to associate imported sensors with
            yaml_content: YAML configuration content
            device_name: Human-readable device name
            replace_existing: Whether to replace existing sensors

        Returns:
            Sensor set ID where sensors were stored
        """
        self._ensure_initialized()

        # If replacing, delete existing sensors first
        if replace_existing:
            await self.async_delete_device_sensors(device_identifier)

        # Convert YAML to storage format
        sensor_set_name = device_name or f"Device {device_identifier}"
        description = f"Imported YAML configuration for device {device_identifier}"

        sensor_set_id = await self.config_converter.convert_yaml_content_to_storage(
            yaml_content,
            sensor_set_name,
            device_identifier,
            description,
        )

        _LOGGER.info(
            "Imported YAML configuration for device %s (sensor_set: %s)",
            device_identifier,
            sensor_set_id,
        )
        return sensor_set_id

    async def async_export_device_yaml(
        self,
        device_identifier: str,
        output_file_path: str | None = None,
    ) -> str:
        """
        Export device sensors to YAML format.

        Args:
            device_identifier: Device identifier
            output_file_path: Optional file path to save YAML

        Returns:
            YAML content as string
        """
        self._ensure_initialized()

        # Get config for device
        config = self.storage_manager.to_config(device_identifier=device_identifier)

        # Convert to YAML
        from .config_manager import ConfigManager

        config_manager = ConfigManager(self.hass)
        yaml_content = config_manager._config_to_yaml(config)

        # Save to file if requested
        if output_file_path:
            await self.config_converter.export_storage_to_yaml(
                output_file_path,
                device_identifier=device_identifier,
            )

        _LOGGER.info(
            "Exported YAML for device %s (%d sensors)",
            device_identifier,
            len(config.sensors),
        )

        import yaml

        return yaml.dump(yaml_content, default_flow_style=False, sort_keys=False)

    # Query and Management

    def get_device_sensors(self, device_identifier: str) -> list[SensorConfig]:
        """
        Get all sensors for a device.

        Args:
            device_identifier: Device identifier

        Returns:
            List of sensor configurations
        """
        self._ensure_initialized()
        return self.storage_manager.list_sensors(device_identifier=device_identifier)

    def get_device_sensor_sets(self, device_identifier: str) -> list[SensorSetMetadata]:
        """
        Get all sensor sets for a device.

        Args:
            device_identifier: Device identifier

        Returns:
            List of sensor set metadata
        """
        self._ensure_initialized()
        return self.storage_manager.list_sensor_sets(device_identifier)

    def get_all_devices(self) -> list[str]:
        """
        Get list of all device identifiers that have sensors.

        Returns:
            List of device identifiers
        """
        self._ensure_initialized()

        device_identifiers = set()
        sensor_sets = self.storage_manager.list_sensor_sets()

        for sensor_set in sensor_sets:
            if sensor_set.device_identifier:
                device_identifiers.add(sensor_set.device_identifier)

        return list(device_identifiers)

    def get_device_summary(self, device_identifier: str) -> dict[str, Any]:
        """
        Get summary information for a device.

        Args:
            device_identifier: Device identifier

        Returns:
            Dictionary with device summary information
        """
        self._ensure_initialized()

        sensors = self.get_device_sensors(device_identifier)
        sensor_sets = self.get_device_sensor_sets(device_identifier)

        return {
            "device_identifier": device_identifier,
            "sensor_count": len(sensors),
            "sensor_set_count": len(sensor_sets),
            "sensor_sets": [
                {
                    "sensor_set_id": s.sensor_set_id,
                    "name": s.name,
                    "description": s.description,
                    "sensor_count": s.sensor_count,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                }
                for s in sensor_sets
            ],
            "sensor_unique_ids": [s.unique_id for s in sensors],
        }

    # Batch Operations

    async def async_batch_update_sensors(
        self,
        updates: list[dict[str, Any]],
    ) -> dict[str, bool]:
        """
        Perform batch updates on multiple sensors.

        Args:
            updates: List of update dictionaries with keys:
                    - unique_id: Sensor unique ID
                    - sensor_config: New SensorConfig (optional)
                    - device_identifier: New device association (optional)
                    - operation: 'update' or 'delete'

        Returns:
            Dictionary mapping unique_ids to success status
        """
        self._ensure_initialized()

        results: dict[str, bool] = {}

        for update in updates:
            unique_id = update.get("unique_id")
            operation = update.get("operation", "update")

            # Ensure unique_id is a string for the results dict
            unique_id_str = str(unique_id) if unique_id is not None else "unknown"

            try:
                if operation == "delete":
                    if unique_id is None or not isinstance(unique_id, str):
                        results[unique_id_str] = False
                        continue
                    success = await self.storage_manager.async_delete_sensor(unique_id)
                    results[unique_id_str] = success
                elif operation == "update":
                    sensor_config = update.get("sensor_config")
                    device_identifier = update.get("device_identifier")

                    if sensor_config:
                        # Get or create sensor set for device
                        sensor_set_id = await self.async_get_or_create_device_sensor_set(device_identifier or "unknown")

                        await self.storage_manager.async_store_sensor(
                            sensor_config,
                            sensor_set_id,
                            device_identifier,
                        )
                        results[unique_id_str] = True
                    else:
                        results[unique_id_str] = False
                else:
                    results[unique_id_str] = False

            except Exception as err:
                _LOGGER.error("Batch update failed for %s: %s", unique_id, err)
                results[unique_id_str] = False

        successful_updates = sum(1 for success in results.values() if success)
        _LOGGER.info(
            "Batch update completed: %d/%d successful",
            successful_updates,
            len(updates),
        )

        return results

    # Validation and Health Checks

    def validate_device_configuration(self, device_identifier: str) -> dict[str, Any]:
        """
        Validate configuration for a device.

        Args:
            device_identifier: Device identifier

        Returns:
            Dictionary with validation results
        """
        self._ensure_initialized()

        sensors = self.get_device_sensors(device_identifier)
        config = self.storage_manager.to_config(device_identifier=device_identifier)

        # Validate using existing config validation
        validation_errors = config.validate()

        # Additional device-specific validation
        device_errors = []
        unique_ids = [s.unique_id for s in sensors]
        if len(unique_ids) != len(set(unique_ids)):
            device_errors.append("Duplicate sensor unique_ids found")

        return {
            "device_identifier": device_identifier,
            "sensor_count": len(sensors),
            "validation_errors": validation_errors,
            "device_errors": device_errors,
            "is_valid": len(validation_errors) == 0 and len(device_errors) == 0,
        }

    async def async_cleanup_orphaned_sensors(self) -> dict[str, int]:
        """
        Clean up sensors that are not associated with any sensor set.

        Returns:
            Dictionary with cleanup statistics
        """
        self._ensure_initialized()

        # This is a placeholder for Phase 1 - in practice, the storage manager
        # design prevents orphaned sensors since all sensors must belong to a set

        return {
            "orphaned_sensors_found": 0,
            "orphaned_sensors_deleted": 0,
            "sensor_sets_cleaned": 0,
        }
