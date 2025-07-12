"""
Storage Manager - HA Storage-based configuration management for synthetic sensors.

This module provides storage-based configuration management using Home Assistant's
built-in storage system, replacing file-based YAML configuration for fresh installations
while maintaining compatibility with existing config structures.

Phase 1 Implementation: Basic storage infrastructure for fresh installations.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any, Callable, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .config_models import Config, SensorConfig
from .config_types import GlobalSettingsDict
from .entity_change_handler import EntityChangeHandler
from .entity_registry_listener import EntityRegistryListener
from .exceptions import SyntheticSensorsError
from .sensor_set_factory import create_sensor_set

if TYPE_CHECKING:
    from .evaluator import Evaluator
    from .sensor_manager import SensorManager
    from .sensor_set import SensorSet
    from .storage_validator import ValidationHandler

_LOGGER = logging.getLogger(__name__)

# Storage version for HA storage system
STORAGE_VERSION = 1
STORAGE_KEY = "synthetic_sensors"


# Type definitions for storage data structures
class StoredSensorDict(TypedDict, total=False):
    """Storage representation of a sensor configuration."""

    unique_id: str
    sensor_set_id: str  # Bulk management identifier
    device_identifier: str | None  # Device association
    config_data: dict[str, Any]  # Serialized sensor configuration
    created_at: str  # ISO timestamp
    updated_at: str  # ISO timestamp


class StorageData(TypedDict):
    """Root storage data structure."""

    version: str
    sensors: dict[str, StoredSensorDict]  # unique_id -> sensor data
    sensor_sets: dict[str, dict[str, Any]]  # sensor_set_id -> metadata


def _default_sensors() -> dict[str, StoredSensorDict]:
    """Default factory for sensors dictionary."""
    return {}


def _default_sensor_sets() -> dict[str, dict[str, Any]]:
    """Default factory for sensor sets dictionary."""
    return {}


@dataclass
class SensorSetMetadata:
    """Metadata for a sensor set (bulk management group)."""

    sensor_set_id: str
    device_identifier: str | None = None
    name: str | None = None
    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    sensor_count: int = 0
    global_settings: dict[str, Any] | None = None


class StorageManager:
    """
    HA Storage-based configuration manager for synthetic sensors.

    Provides storage-based configuration management using Home Assistant's
    built-in storage system. Supports device association and bulk operations
    while maintaining compatibility with existing config structures.
    """

    def __init__(self, hass: HomeAssistant, storage_key: str = STORAGE_KEY, enable_entity_listener: bool = True) -> None:
        """Initialize storage manager.

        Args:
            hass: Home Assistant instance
            storage_key: Storage key for Home Assistant storage
            enable_entity_listener: Whether to enable entity registry listener
        """
        self.hass = hass
        self._storage_key = storage_key
        self._store: Store[StorageData] = Store(hass, STORAGE_VERSION, storage_key)
        self._data: StorageData | None = None
        self._lock = asyncio.Lock()

        # Entity change handling components
        self._entity_change_handler = EntityChangeHandler()
        self._entity_registry_listener: EntityRegistryListener | None = None
        self._enable_entity_listener = enable_entity_listener
        self._logger = _LOGGER.getChild(self.__class__.__name__)

        # Cache for SensorSet instances to ensure consistency
        self._sensor_set_cache: dict[str, SensorSet] = {}

        # Initialize handler modules
        from .storage_sensor_ops import SensorOpsHandler  # pylint: disable=import-outside-toplevel
        from .storage_sensor_set_ops import SensorSetOpsHandler  # pylint: disable=import-outside-toplevel
        from .storage_validator import ValidationHandler  # pylint: disable=import-outside-toplevel
        from .storage_yaml_handler import YamlHandler  # pylint: disable=import-outside-toplevel

        self._yaml_handler = YamlHandler(self)
        self._validation_handler = ValidationHandler(self)
        self._sensor_set_ops_handler = SensorSetOpsHandler(self)
        self._sensor_ops_handler = SensorOpsHandler(self)

    @property
    def validator(self) -> ValidationHandler:
        """Get the validation handler."""
        return self._validation_handler

    async def async_load(self) -> None:
        """Load configuration from HA storage."""
        async with self._lock:
            try:
                stored_data = await self._store.async_load()
                if stored_data is None:
                    # Initialize empty storage
                    self._data = StorageData(
                        version="1.0",
                        sensors=_default_sensors(),
                        sensor_sets=_default_sensor_sets(),
                    )
                    _LOGGER.info("Initialized empty synthetic sensor storage")
                else:
                    self._data = stored_data
                    _LOGGER.info(
                        "Loaded synthetic sensor storage: %d sensors, %d sensor sets",
                        len(stored_data.get("sensors", {})),
                        len(stored_data.get("sensor_sets", {})),
                    )

                # Start entity registry listener after loading (if enabled)
                if self._enable_entity_listener:
                    await self._start_entity_registry_listener()

            except Exception as err:
                _LOGGER.error("Failed to load synthetic sensor storage: %s", err)
                # Initialize empty storage on error
                self._data = StorageData(
                    version="1.0",
                    sensors=_default_sensors(),
                    sensor_sets=_default_sensor_sets(),
                )
                raise SyntheticSensorsError(f"Failed to load storage: {err}") from err

    async def async_unload(self) -> None:
        """Unload storage manager and cleanup entity change components."""
        await self._stop_entity_registry_listener()
        self._logger.debug("Storage manager unloaded")

    async def _start_entity_registry_listener(self) -> None:
        """Start the entity registry listener for tracking external entity ID changes."""
        if self._entity_registry_listener is not None:
            self._logger.warning("Entity registry listener already started")
            return

        self._entity_registry_listener = EntityRegistryListener(
            self.hass,
            self,  # StorageManager instance
            self._entity_change_handler,
        )

        await self._entity_registry_listener.async_start()
        self._logger.debug("Started entity registry listener")

    async def _stop_entity_registry_listener(self) -> None:
        """Stop the entity registry listener."""
        if self._entity_registry_listener is not None:
            await self._entity_registry_listener.async_stop()
            self._entity_registry_listener = None
            self._logger.debug("Stopped entity registry listener")

    def register_evaluator(self, evaluator: Evaluator) -> None:
        """Register an evaluator for entity change notifications."""
        self._entity_change_handler.register_evaluator(evaluator)

    def unregister_evaluator(self, evaluator: Evaluator) -> None:
        """Unregister an evaluator from entity change notifications."""
        self._entity_change_handler.unregister_evaluator(evaluator)

    def register_sensor_manager(self, sensor_manager: SensorManager) -> None:
        """Register a sensor manager for entity change notifications."""
        self._entity_change_handler.register_sensor_manager(sensor_manager)

    def unregister_sensor_manager(self, sensor_manager: SensorManager) -> None:
        """Unregister a sensor manager from entity change notifications."""
        self._entity_change_handler.unregister_sensor_manager(sensor_manager)

    def add_entity_change_callback(self, callback: Callable[[str, str], None]) -> None:
        """Add a callback for entity change notifications."""
        self._entity_change_handler.register_integration_callback(callback)

    def remove_entity_change_callback(self, callback: Callable[[str, str], None]) -> None:
        """Remove a callback from entity change notifications."""
        self._entity_change_handler.unregister_integration_callback(callback)

    @property
    def entity_change_handler(self) -> EntityChangeHandler:
        """Get the entity change handler."""
        return self._entity_change_handler

    def is_entity_tracked(self, entity_id: str) -> bool:
        """Check if an entity is being tracked for changes."""
        data = self._ensure_loaded()

        # Check if any sensor references this entity
        for stored_sensor in data["sensors"].values():
            config_data = stored_sensor.get("config_data")
            if config_data:
                sensor_config = self.deserialize_sensor_config(config_data)
                if entity_id in sensor_config.get_all_dependencies():
                    return True

        return False

    async def async_save(self) -> None:
        """Save configuration to HA storage."""
        if self._data is None:
            raise SyntheticSensorsError("No data to save")

        async with self._lock:
            try:
                # Ensure all sets are converted to lists for JSON serialization
                json_safe_data = self._convert_sets_to_lists(self._data)
                await self._store.async_save(json_safe_data)
                self._logger.debug("Saved synthetic sensor storage")
            except Exception as err:
                _LOGGER.error("Failed to save synthetic sensor storage: %s", err)
                raise SyntheticSensorsError(f"Failed to save storage: {err}") from err

    def _convert_sets_to_lists(self, obj: Any) -> Any:
        """Recursively convert all sets to lists for JSON serialization."""
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, dict):
            return {k: self._convert_sets_to_lists(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._convert_sets_to_lists(item) for item in obj]
        return obj

    def _ensure_loaded(self) -> StorageData:
        """Ensure storage data is loaded."""
        if self._data is None:
            raise SyntheticSensorsError("Storage not loaded")
        return self._data

    @property
    def data(self) -> StorageData:
        """Get storage data."""
        return self._ensure_loaded()

    # YAML Import/Export Methods (delegated to YamlHandler)
    async def async_from_yaml(
        self,
        yaml_content: str,
        sensor_set_id: str,
        device_identifier: str | None = None,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        """Import YAML content into a sensor set."""
        return await self._sensor_set_ops_handler.async_from_yaml(
            yaml_content, sensor_set_id, device_identifier, replace_existing
        )

    def export_yaml(self, sensor_set_id: str) -> str:
        """Export sensor set to YAML format."""
        return self._yaml_handler.export_yaml(sensor_set_id)

    # Sensor Set Operations (delegated to SensorSetOpsHandler)
    async def async_create_sensor_set(
        self,
        sensor_set_id: str,
        device_identifier: str | None = None,
        name: str | None = None,
        description: str | None = None,
        global_settings: GlobalSettingsDict | None = None,
    ) -> SensorSetMetadata:
        """Create a new sensor set."""
        await self._sensor_set_ops_handler.async_create_sensor_set(
            sensor_set_id, device_identifier, name, description, global_settings
        )
        # Return the created metadata
        metadata = self.get_sensor_set_metadata(sensor_set_id)
        if metadata is None:
            raise SyntheticSensorsError(f"Failed to create sensor set: {sensor_set_id}")
        return metadata

    async def async_delete_sensor_set(self, sensor_set_id: str) -> bool:
        """Delete a sensor set and all its sensors."""
        return await self._sensor_set_ops_handler.async_delete_sensor_set(sensor_set_id)

    def get_sensor_set_metadata(self, sensor_set_id: str) -> SensorSetMetadata | None:
        """Get metadata for a sensor set."""
        return self._sensor_set_ops_handler.get_sensor_set_metadata(sensor_set_id)

    def list_sensor_sets(self, device_identifier: str | None = None) -> list[SensorSetMetadata]:
        """List all sensor sets, optionally filtered by device identifier."""
        return self._sensor_set_ops_handler.list_sensor_sets(device_identifier)

    def sensor_set_exists(self, sensor_set_id: str) -> bool:
        """Check if a sensor set exists."""
        return self._sensor_set_ops_handler.sensor_set_exists(sensor_set_id)

    def get_sensor_count(self, sensor_set_id: str | None = None) -> int:
        """Get the number of sensors in a sensor set or total."""
        return self._sensor_set_ops_handler.get_sensor_count(sensor_set_id)

    def _get_sensor_set_header(self, sensor_set_id: str) -> dict[str, Any]:
        """Get sensor set header data for YAML export/validation."""
        return self._sensor_set_ops_handler.get_sensor_set_header(sensor_set_id)

    # Sensor CRUD Operations (delegated to SensorOpsHandler)
    async def async_store_sensor(
        self,
        sensor_config: SensorConfig,
        sensor_set_id: str,
        device_identifier: str | None = None,
    ) -> None:
        """Store a sensor configuration."""
        await self._sensor_ops_handler.async_store_sensor(sensor_config, sensor_set_id, device_identifier)

    async def async_store_sensors_bulk(
        self,
        sensor_configs: list[SensorConfig],
        sensor_set_id: str,
        device_identifier: str | None = None,
    ) -> dict[str, Any]:
        """Store multiple sensor configurations in bulk."""
        return await self._sensor_ops_handler.async_store_sensors_bulk(sensor_configs, sensor_set_id, device_identifier)

    def get_sensor(self, unique_id: str) -> SensorConfig | None:
        """Get a sensor configuration by unique ID."""
        return self._sensor_ops_handler.get_sensor(unique_id)

    def list_sensors(
        self,
        sensor_set_id: str | None = None,
        device_identifier: str | None = None,
        include_config: bool = False,
    ) -> list[SensorConfig]:
        """List sensors with optional filtering."""
        return self._sensor_ops_handler.list_sensors(sensor_set_id, device_identifier, include_config)

    async def async_update_sensor(self, sensor_config: SensorConfig) -> bool:
        """Update an existing sensor configuration."""
        return await self._sensor_ops_handler.async_update_sensor(sensor_config)

    async def async_delete_sensor(self, unique_id: str) -> bool:
        """Delete a sensor configuration."""
        return await self._sensor_ops_handler.async_delete_sensor(unique_id)

    def serialize_sensor_config(self, sensor_config: SensorConfig) -> Any:
        """Serialize sensor configuration for storage."""
        return self._sensor_ops_handler.serialize_sensor_config(sensor_config)

    def deserialize_sensor_config(self, config_data: dict[str, Any]) -> SensorConfig:
        """Deserialize sensor configuration from storage."""
        return self._sensor_ops_handler.deserialize_sensor_config(config_data)

    # Validation Methods (delegated to ValidationHandler)
    def validate_no_global_conflicts(self, sensors: list[SensorConfig], global_settings: GlobalSettingsDict) -> None:
        """Validate that global variables don't conflict with sensor formulas."""
        self._validation_handler.validate_no_global_conflicts(sensors, global_settings)

    def validate_no_attribute_variable_conflicts(self, sensors: list[SensorConfig]) -> None:
        """Validate that attribute formulas don't conflict with each other."""
        self._validation_handler.validate_no_attribute_variable_conflicts(sensors)

    def _validate_sensor_with_context(self, sensor_config: SensorConfig, sensor_set_id: str) -> list[str]:
        """Validate a sensor configuration within its sensor set context."""
        return self._validation_handler.validate_sensor_with_context(sensor_config, sensor_set_id)

    # Configuration conversion methods
    def to_config(
        self,
        device_identifier: str | None = None,
        sensor_set_id: str | None = None,
    ) -> Config:
        """Convert storage data to Config object."""
        data = self._ensure_loaded()

        # Filter sensors by criteria
        sensors = []
        global_settings: GlobalSettingsDict = {}

        for stored_sensor in data["sensors"].values():
            # Apply device identifier filter
            if device_identifier is not None and stored_sensor.get("device_identifier") != device_identifier:
                continue

            # Apply sensor set filter
            if sensor_set_id is not None:
                if stored_sensor.get("sensor_set_id") != sensor_set_id:
                    continue

                # Get global settings from sensor set
                if sensor_set_id in data["sensor_sets"]:
                    global_settings = data["sensor_sets"][sensor_set_id].get("global_settings", {})

            # Deserialize and add sensor
            config_data = stored_sensor.get("config_data")
            if config_data:
                sensor_config = self.deserialize_sensor_config(config_data)
                sensors.append(sensor_config)

        return Config(sensors=sensors, global_settings=global_settings)

    async def async_from_config(
        self,
        config: Config,
        sensor_set_id: str,
        device_identifier: str | None = None,
    ) -> None:
        """Store a Config object in storage."""
        # Create or update sensor set
        if not self.sensor_set_exists(sensor_set_id):
            final_device_id, final_name, global_settings = self.prepare_sensor_set_creation_params(
                config, sensor_set_id, device_identifier
            )
            await self.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier=final_device_id,
                name=final_name,
                global_settings=global_settings,
            )
        else:
            # Update global settings for existing sensor set
            if config.global_settings:
                sensor_set = self.get_sensor_set(sensor_set_id)
                await sensor_set.async_set_global_settings(config.global_settings)

        # Store sensors
        for sensor_config in config.sensors:
            # Override device identifier if specified
            if device_identifier:
                sensor_config.device_identifier = device_identifier

            await self.async_store_sensor(
                sensor_config=sensor_config,
                sensor_set_id=sensor_set_id,
                device_identifier=device_identifier,
            )

    def prepare_sensor_set_creation_params(
        self, config: Config, sensor_set_id: str, device_identifier: str | None = None
    ) -> tuple[str | None, str, GlobalSettingsDict]:
        """Prepare parameters for sensor set creation from config.

        Args:
            config: Configuration object
            sensor_set_id: Target sensor set ID
            device_identifier: Optional device identifier override

        Returns:
            Tuple of (final_device_id, final_name, global_settings)
        """
        global_device_id = config.global_settings.get("device_identifier")
        global_name = config.global_settings.get("name", sensor_set_id)

        final_device_id = device_identifier or (global_device_id if isinstance(global_device_id, str) else None)
        final_name = global_name if isinstance(global_name, str) else sensor_set_id

        return final_device_id, final_name, config.global_settings

    def _prepare_sensor_set_creation_params(
        self, config: Config, sensor_set_id: str, device_identifier: str | None = None
    ) -> tuple[str | None, str, GlobalSettingsDict]:
        """Prepare parameters for sensor set creation from config (deprecated).

        Args:
            config: Configuration object
            sensor_set_id: Target sensor set ID
            device_identifier: Optional device identifier override

        Returns:
            Tuple of (final_device_id, final_name, global_settings)
        """
        return self.prepare_sensor_set_creation_params(config, sensor_set_id, device_identifier)

    # Utility methods
    def get_current_timestamp(self) -> str:
        """Get current timestamp as ISO string."""
        return datetime.now().isoformat()

    def get_sensor_set(self, sensor_set_id: str) -> SensorSet:
        """Get or create a SensorSet instance."""
        if sensor_set_id not in self._sensor_set_cache:
            self._sensor_set_cache[sensor_set_id] = create_sensor_set(self, sensor_set_id)

        return self._sensor_set_cache[sensor_set_id]

    async def async_clear_all_data(self) -> None:
        """Clear all storage data."""
        self._data = StorageData(
            version="1.0",
            sensors=_default_sensors(),
            sensor_sets=_default_sensor_sets(),
        )
        await self.async_save()
        self._sensor_set_cache.clear()
        _LOGGER.info("Cleared all synthetic sensor storage data")

    def get_storage_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        data = self._ensure_loaded()

        return {
            "version": data.get("version", "unknown"),
            "total_sensors": len(data["sensors"]),
            "total_sensor_sets": len(data["sensor_sets"]),
            "sensor_sets": [
                {
                    "sensor_set_id": sensor_set_id,
                    "sensor_count": sum(1 for s in data["sensors"].values() if s.get("sensor_set_id") == sensor_set_id),
                    "device_identifier": sensor_set_data.get("device_identifier"),
                    "name": sensor_set_data.get("name"),
                }
                for sensor_set_id, sensor_set_data in data["sensor_sets"].items()
            ],
        }

    def has_data(self) -> bool:
        """Check if storage has any data."""
        if self._data is None:
            return False

        return bool(self._data["sensors"] or self._data["sensor_sets"])
