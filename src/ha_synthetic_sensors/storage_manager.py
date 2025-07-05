"""
Storage Manager - HA Storage-based configuration management for synthetic sensors.

This module provides storage-based configuration management using Home Assistant's
built-in storage system, replacing file-based YAML configuration for fresh installations
while maintaining compatibility with existing config structures.

Phase 1 Implementation: Basic storage infrastructure for fresh installations.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import logging
from typing import TYPE_CHECKING, Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
import yaml

from .config_manager import Config, FormulaConfig, SensorConfig
from .exceptions import SyntheticSensorsError

if TYPE_CHECKING:
    from .sensor_set import SensorSet

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


class StorageManager:
    """
    HA Storage-based configuration manager for synthetic sensors.

    Provides storage-based configuration management using Home Assistant's
    built-in storage system. Supports device association and bulk operations
    while maintaining compatibility with existing config structures.
    """

    def __init__(self, hass: HomeAssistant, storage_key: str = STORAGE_KEY) -> None:
        """
        Initialize the StorageManager.

        Args:
            hass: Home Assistant instance
            storage_key: Storage key for HA storage system
        """
        self.hass = hass
        self._store: Store[StorageData] = Store(hass, STORAGE_VERSION, storage_key)
        self._data: StorageData | None = None
        self._lock = asyncio.Lock()

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
            except Exception as err:
                _LOGGER.error("Failed to load synthetic sensor storage: %s", err)
                # Initialize empty storage on error
                self._data = StorageData(
                    version="1.0",
                    sensors=_default_sensors(),
                    sensor_sets=_default_sensor_sets(),
                )
                raise SyntheticSensorsError(f"Failed to load storage: {err}") from err

    async def async_save(self) -> None:
        """Save configuration to HA storage."""
        if self._data is None:
            _LOGGER.warning("No data to save")
            return

        async with self._lock:
            try:
                await self._store.async_save(self._data)
                _LOGGER.debug("Saved synthetic sensor storage")
            except Exception as err:
                _LOGGER.error("Failed to save synthetic sensor storage: %s", err)
                raise SyntheticSensorsError(f"Failed to save storage: {err}") from err

    def _ensure_loaded(self) -> StorageData:
        """Ensure storage data is loaded and return it."""
        if self._data is None:
            raise SyntheticSensorsError("Storage not loaded. Call async_load() first.")
        return self._data

    @property
    def data(self) -> StorageData:
        """Get the storage data, ensuring it's loaded."""
        return self._ensure_loaded()

    # YAML-JSON storage methods (simple conversion, no parsing)

    async def async_from_yaml(
        self,
        yaml_content: str,
        sensor_set_id: str,
        device_identifier: str | None = None,
    ) -> str:
        """
        Store YAML content directly as JSON without parsing.

        Args:
            yaml_content: Raw YAML content string
            sensor_set_id: Sensor set identifier for bulk management
            device_identifier: Device to associate with

        Returns:
            The sensor_set_id used for storage
        """
        try:
            # Convert YAML to JSON (no parsing, just format conversion)
            yaml_data = yaml.safe_load(yaml_content)
            if not yaml_data:
                raise SyntheticSensorsError("Empty YAML content")

            # Store the raw YAML structure as JSON
            data = self._ensure_loaded()

            # Create sensor set if it doesn't exist
            if sensor_set_id not in data["sensor_sets"]:
                # Create the sensor set directly instead of using async_create_sensor_set
                # which generates a UUID instead of using our provided sensor_set_id
                timestamp = self._get_timestamp()
                data["sensor_sets"][sensor_set_id] = {
                    "device_identifier": device_identifier,
                    "name": f"YAML Import {sensor_set_id}",
                    "description": "Imported from YAML content",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "sensor_count": 0,
                }

            timestamp = self._get_timestamp()
            data["sensor_sets"][sensor_set_id]["updated_at"] = timestamp

            # Parse YAML and create individual sensor records
            from .config_manager import ConfigManager

            config_manager = ConfigManager(self.hass)
            config = config_manager.load_from_dict(yaml_data)

            # Store global settings per sensor set
            yaml_global_settings = {}
            if "global_settings" in yaml_data:
                yaml_global_settings = yaml_data["global_settings"]
                # Store global settings in the sensor set metadata
                data["sensor_sets"][sensor_set_id]["global_settings"] = yaml_global_settings

            # Validate that local settings don't conflict with global settings
            self._validate_no_global_conflicts(config.sensors, yaml_global_settings)

            # Remove any existing sensors from this sensor set first
            sensors_to_remove = [
                unique_id
                for unique_id, sensor_data in data["sensors"].items()
                if sensor_data.get("sensor_set_id") == sensor_set_id
            ]
            for unique_id in sensors_to_remove:
                del data["sensors"][unique_id]

            # Store all sensors from the YAML with sensor_set_id association
            # Store original sensor configs - global settings will be applied during retrieval
            for sensor_config in config.sensors:
                stored_sensor = StoredSensorDict(
                    unique_id=sensor_config.unique_id,
                    sensor_set_id=sensor_set_id,
                    device_identifier=device_identifier,
                    config_data=self._serialize_sensor_config(sensor_config),
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                data["sensors"][sensor_config.unique_id] = stored_sensor

            # Update sensor set metadata
            data["sensor_sets"][sensor_set_id]["sensor_count"] = len(config.sensors)

            await self.async_save()

            _LOGGER.info("Stored YAML content and %d sensors for sensor set: %s", len(config.sensors), sensor_set_id)
            return sensor_set_id

        except Exception as exc:
            raise SyntheticSensorsError(f"Failed to store YAML content: {exc}") from exc

    def export_yaml(self, sensor_set_id: str) -> str:
        """
        Export sensor set data as YAML string reconstructed from current sensor state.

        Args:
            sensor_set_id: Sensor set identifier

        Returns:
            YAML content string
        """
        data = self._ensure_loaded()

        if sensor_set_id not in data["sensor_sets"]:
            raise SyntheticSensorsError(f"Sensor set not found: {sensor_set_id}")

        # Always reconstruct YAML from current sensor state
        sensor_configs = self.list_sensors(sensor_set_id=sensor_set_id)

        if not sensor_configs:
            raise SyntheticSensorsError(f"No sensors found for sensor set: {sensor_set_id}")

        # Reconstruct YAML structure with sensors as dict (not list)
        yaml_data: dict[str, Any] = {"version": "1.0", "sensors": {}}

        # Add global settings from this specific sensor set
        sensor_set_metadata = data["sensor_sets"].get(sensor_set_id, {})
        global_settings = sensor_set_metadata.get("global_settings", {})
        if global_settings:
            yaml_data["global_settings"] = global_settings

        # Convert sensors to YAML format (sensors as dict with unique_id as keys)
        for sensor_config in sensor_configs:
            sensor_dict: dict[str, Any] = {
                "name": sensor_config.name,
                "enabled": sensor_config.enabled,
            }

            # Add device_identifier if not covered by global settings
            global_device_identifier = global_settings.get("device_identifier")
            if sensor_config.device_identifier and sensor_config.device_identifier != global_device_identifier:
                sensor_dict["device_identifier"] = sensor_config.device_identifier

            # Add optional sensor fields
            if sensor_config.update_interval is not None:
                sensor_dict["update_interval"] = sensor_config.update_interval
            if sensor_config.category:
                sensor_dict["category"] = sensor_config.category
            if sensor_config.description:
                sensor_dict["description"] = sensor_config.description

            # Handle formulas - main formula and attributes
            main_formula = None
            attributes: dict[str, Any] = {}

            for formula in sensor_config.formulas:
                if formula.id == sensor_config.unique_id:
                    # This is the main formula
                    main_formula = formula
                else:
                    # This is an attribute formula
                    attr_name = formula.id.replace(f"{sensor_config.unique_id}_", "")
                    attr_dict: dict[str, Any] = {"formula": formula.formula}
                    if formula.unit_of_measurement:
                        attr_dict["unit_of_measurement"] = formula.unit_of_measurement
                    if formula.device_class:
                        attr_dict["device_class"] = formula.device_class
                    if formula.state_class:
                        attr_dict["state_class"] = formula.state_class
                    if formula.icon:
                        attr_dict["icon"] = formula.icon
                    attributes[attr_name] = attr_dict

            # Add main formula details
            if main_formula:
                sensor_dict["formula"] = main_formula.formula

                # Add variables, excluding global ones (only include locals that were originally there)
                if main_formula.variables:
                    global_variables = global_settings.get("variables", {})
                    local_variables = {}
                    for var_name, var_value in main_formula.variables.items():
                        # Only include variables that are not in globals, or are local overrides with same value
                        if var_name not in global_variables:
                            local_variables[var_name] = var_value
                        elif var_name in global_variables and var_value == global_variables[var_name]:
                            # This was a local override with same value as global - preserve it in export
                            local_variables[var_name] = var_value

                    if local_variables:
                        sensor_dict["variables"] = local_variables

                if main_formula.unit_of_measurement:
                    sensor_dict["unit_of_measurement"] = main_formula.unit_of_measurement
                if main_formula.device_class:
                    sensor_dict["device_class"] = main_formula.device_class
                if main_formula.state_class:
                    sensor_dict["state_class"] = main_formula.state_class
                if main_formula.icon:
                    sensor_dict["icon"] = main_formula.icon

            # Add attributes if any
            if attributes:
                sensor_dict["attributes"] = attributes

            yaml_data["sensors"][sensor_config.unique_id] = sensor_dict

        # Convert to YAML string
        return yaml.dump(yaml_data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Sensor Set Management (Bulk Operations)

    async def async_create_sensor_set(
        self,
        sensor_set_id: str,
        device_identifier: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> SensorSet:
        """
        Create a new sensor set for bulk management.

        Args:
            sensor_set_id: Integration-provided sensor set identifier
            device_identifier: Device to associate sensors with
            name: Human-readable name for the sensor set
            description: Description of the sensor set

        Returns:
            SensorSet handle for the created sensor set
        """
        self._ensure_loaded()
        data = self._ensure_loaded()

        # Use the provided sensor_set_id instead of generating UUID
        timestamp = self._get_timestamp()

        metadata = {
            "device_identifier": device_identifier,
            "name": name,
            "description": description,
            "created_at": timestamp,
            "updated_at": timestamp,
            "sensor_count": 0,
        }

        data["sensor_sets"][sensor_set_id] = metadata
        await self.async_save()

        _LOGGER.info(
            "Created sensor set: %s (device: %s, name: %s)",
            sensor_set_id,
            device_identifier,
            name,
        )

        return self.get_sensor_set(sensor_set_id)

    async def async_delete_sensor_set(self, sensor_set_id: str) -> bool:
        """
        Delete a sensor set and all associated sensors.

        Args:
            sensor_set_id: Sensor set identifier

        Returns:
            True if deleted, False if not found
        """
        self._ensure_loaded()
        data = self._ensure_loaded()

        if sensor_set_id not in data["sensor_sets"]:
            return False

        # Delete all sensors in the set
        sensors_to_delete = [
            unique_id for unique_id, sensor_data in data["sensors"].items() if sensor_data.get("sensor_set_id") == sensor_set_id
        ]

        for unique_id in sensors_to_delete:
            del data["sensors"][unique_id]

        # Delete the sensor set metadata
        del data["sensor_sets"][sensor_set_id]
        await self.async_save()

        _LOGGER.info(
            "Deleted sensor set %s and %d associated sensors",
            sensor_set_id,
            len(sensors_to_delete),
        )
        return True

    def get_sensor_set_metadata(self, sensor_set_id: str) -> SensorSetMetadata | None:
        """
        Get metadata for a sensor set.

        Args:
            sensor_set_id: Sensor set identifier

        Returns:
            Sensor set metadata or None if not found
        """
        data = self._ensure_loaded()

        metadata = data["sensor_sets"].get(sensor_set_id)
        if not metadata:
            return None

        return SensorSetMetadata(
            sensor_set_id=sensor_set_id,
            device_identifier=metadata.get("device_identifier"),
            name=metadata.get("name"),
            description=metadata.get("description"),
            created_at=metadata.get("created_at"),
            updated_at=metadata.get("updated_at"),
            sensor_count=metadata.get("sensor_count", 0),
        )

    def list_sensor_sets(self, device_identifier: str | None = None) -> list[SensorSetMetadata]:
        """
        List all sensor sets, optionally filtered by device.

        Args:
            device_identifier: Filter by device identifier

        Returns:
            List of sensor set metadata
        """
        data = self._ensure_loaded()

        result = []
        for sensor_set_id, metadata in data["sensor_sets"].items():
            if device_identifier is None or metadata.get("device_identifier") == device_identifier:
                result.append(
                    SensorSetMetadata(
                        sensor_set_id=sensor_set_id,
                        device_identifier=metadata.get("device_identifier"),
                        name=metadata.get("name"),
                        description=metadata.get("description"),
                        created_at=metadata.get("created_at"),
                        updated_at=metadata.get("updated_at"),
                        sensor_count=metadata.get("sensor_count", 0),
                    )
                )

        return result

    # Sensor Configuration Management

    async def async_store_sensor(
        self,
        sensor_config: SensorConfig,
        sensor_set_id: str,
        device_identifier: str | None = None,
    ) -> None:
        """
        Store a sensor configuration.

        Args:
            sensor_config: Sensor configuration to store
            sensor_set_id: Sensor set identifier for bulk management
            device_identifier: Device to associate with

        Raises:
            SyntheticSensorsError: If sensor validation fails or conflicts with global settings
        """
        data = self._ensure_loaded()

        # Validate sensor set exists
        if sensor_set_id not in data["sensor_sets"]:
            raise SyntheticSensorsError(f"Sensor set not found: {sensor_set_id}")

        # Perform comprehensive validation with context
        validation_errors = self._validate_sensor_with_context(sensor_config, sensor_set_id)
        if validation_errors:
            error_msg = f"Sensor validation failed: {'; '.join(validation_errors)}"
            _LOGGER.error(error_msg)
            raise SyntheticSensorsError(error_msg)

        timestamp = self._get_timestamp()

        # Convert sensor config to storage format
        stored_sensor = StoredSensorDict(
            unique_id=sensor_config.unique_id,
            sensor_set_id=sensor_set_id,
            device_identifier=device_identifier,
            config_data=self._serialize_sensor_config(sensor_config),
            created_at=timestamp,
            updated_at=timestamp,
        )

        # Store the sensor
        data["sensors"][sensor_config.unique_id] = stored_sensor

        # Update sensor set metadata
        if sensor_set_id in data["sensor_sets"]:
            data["sensor_sets"][sensor_set_id]["updated_at"] = timestamp
            data["sensor_sets"][sensor_set_id]["sensor_count"] = len(
                [s for s in data["sensors"].values() if s.get("sensor_set_id") == sensor_set_id]
            )

        await self.async_save()

        _LOGGER.debug(
            "Stored sensor: %s (set: %s, device: %s)",
            sensor_config.unique_id,
            sensor_set_id,
            device_identifier,
        )

    async def async_store_sensors_bulk(
        self,
        sensor_configs: list[SensorConfig],
        sensor_set_id: str,
        device_identifier: str | None = None,
    ) -> None:
        """
        Store multiple sensor configurations in bulk.

        Args:
            sensor_configs: List of sensor configurations to store
            sensor_set_id: Sensor set identifier for bulk management
            device_identifier: Device to associate with
        """
        data = self._ensure_loaded()

        timestamp = self._get_timestamp()

        # Store all sensors
        for sensor_config in sensor_configs:
            stored_sensor = StoredSensorDict(
                unique_id=sensor_config.unique_id,
                sensor_set_id=sensor_set_id,
                device_identifier=device_identifier,
                config_data=self._serialize_sensor_config(sensor_config),
                created_at=timestamp,
                updated_at=timestamp,
            )
            data["sensors"][sensor_config.unique_id] = stored_sensor

        # Update sensor set metadata
        if sensor_set_id in data["sensor_sets"]:
            data["sensor_sets"][sensor_set_id]["updated_at"] = timestamp
            data["sensor_sets"][sensor_set_id]["sensor_count"] = len(
                [s for s in data["sensors"].values() if s.get("sensor_set_id") == sensor_set_id]
            )

        await self.async_save()

        _LOGGER.info(
            "Stored %d sensors in bulk (set: %s, device: %s)",
            len(sensor_configs),
            sensor_set_id,
            device_identifier,
        )

    def get_sensor(self, unique_id: str) -> SensorConfig | None:
        """
        Get a sensor configuration by unique ID.

        Applies global_settings from sensor set to individual sensor during retrieval.
        This ensures CRUD operations get sensors with global settings applied at runtime.

        Args:
            unique_id: Sensor unique identifier

        Returns:
            Sensor configuration or None if not found
        """
        data = self._ensure_loaded()

        stored_sensor = data["sensors"].get(unique_id)
        if not stored_sensor:
            return None

        config_data = stored_sensor.get("config_data")
        if not config_data:
            raise SyntheticSensorsError(f"No config data found for sensor: {unique_id}")

        sensor_config = self._deserialize_sensor_config(config_data)

        # Apply global settings from this sensor's sensor set
        sensor_set_id = stored_sensor.get("sensor_set_id")
        if sensor_set_id:
            sensor_set_metadata = data["sensor_sets"].get(sensor_set_id, {})
            global_settings = sensor_set_metadata.get("global_settings", {})

            if global_settings:
                normalized_sensors = self._apply_global_settings_to_sensors(
                    [sensor_config], global_settings, stored_sensor.get("device_identifier")
                )
                return normalized_sensors[0] if normalized_sensors else sensor_config

        return sensor_config

    def list_sensors(
        self,
        device_identifier: str | None = None,
        sensor_set_id: str | None = None,
    ) -> list[SensorConfig]:
        """
        List sensor configurations with optional filtering.

        Applies global_settings from sensor set to individual sensors during retrieval.
        This ensures CRUD operations get sensors with global settings applied at runtime.

        Args:
            device_identifier: Filter by device identifier
            sensor_set_id: Filter by sensor set identifier

        Returns:
            List of sensor configurations
        """
        data = self._ensure_loaded()

        # Group sensors by sensor_set_id for efficient global settings application
        sensors_by_set: dict[str, list[tuple[SensorConfig, StoredSensorDict]]] = {}

        for stored_sensor in data["sensors"].values():
            # Apply filters
            if device_identifier is not None and stored_sensor.get("device_identifier") != device_identifier:
                continue
            if sensor_set_id is not None and stored_sensor.get("sensor_set_id") != sensor_set_id:
                continue

            config_data = stored_sensor.get("config_data")
            if not config_data:
                continue  # Skip sensors without config data

            sensor_config = self._deserialize_sensor_config(config_data)
            set_id = stored_sensor.get("sensor_set_id", "")

            if set_id not in sensors_by_set:
                sensors_by_set[set_id] = []
            sensors_by_set[set_id].append((sensor_config, stored_sensor))

        # Apply global settings per sensor set and collect results
        result = []
        for set_id, sensor_data_list in sensors_by_set.items():
            sensors = [sensor for sensor, _ in sensor_data_list]

            # Apply global settings from this specific sensor set
            sensor_set_metadata = data["sensor_sets"].get(set_id, {})
            global_settings = sensor_set_metadata.get("global_settings", {})

            if global_settings:
                # Use device_identifier from the first sensor (they should all be the same in a set)
                device_id = sensor_data_list[0][1].get("device_identifier") if sensor_data_list else None
                normalized_sensors = self._apply_global_settings_to_sensors(sensors, global_settings, device_id)
                result.extend(normalized_sensors)
            else:
                result.extend(sensors)

        return result

    async def async_update_sensor(self, sensor_config: SensorConfig) -> bool:
        """
        Update existing sensor configuration with full validation.

        Args:
            sensor_config: Updated sensor configuration

        Returns:
            True if updated, False if sensor not found

        Raises:
            SyntheticSensorsError: If validation fails
        """
        data = self._ensure_loaded()

        if sensor_config.unique_id not in data["sensors"]:
            _LOGGER.warning("Sensor %s not found for update", sensor_config.unique_id)
            return False

        stored_sensor = data["sensors"][sensor_config.unique_id]
        sensor_set_id = stored_sensor.get("sensor_set_id")

        if not sensor_set_id:
            raise SyntheticSensorsError(f"Sensor {sensor_config.unique_id} has no sensor set ID")

        # Perform comprehensive validation with context
        validation_errors = self._validate_sensor_with_context(sensor_config, sensor_set_id)
        if validation_errors:
            error_msg = f"Sensor update validation failed: {'; '.join(validation_errors)}"
            _LOGGER.error(error_msg)
            raise SyntheticSensorsError(error_msg)

        # Update the sensor config data and timestamp
        stored_sensor["config_data"] = self._serialize_sensor_config(sensor_config)
        stored_sensor["updated_at"] = self._get_timestamp()

        # Update sensor set metadata
        if sensor_set_id and sensor_set_id in data["sensor_sets"]:
            data["sensor_sets"][sensor_set_id]["updated_at"] = self._get_timestamp()

        await self.async_save()
        _LOGGER.debug("Updated sensor: %s", sensor_config.unique_id)
        return True

    async def async_delete_sensor(self, unique_id: str) -> bool:
        """
        Delete a sensor configuration.

        Args:
            unique_id: Sensor unique identifier

        Returns:
            True if deleted, False if not found
        """
        data = self._ensure_loaded()

        if unique_id not in data["sensors"]:
            return False

        # Get sensor set ID for metadata update
        sensor_set_id = data["sensors"][unique_id].get("sensor_set_id")

        # Delete the sensor
        del data["sensors"][unique_id]

        # Update sensor set metadata
        if sensor_set_id and sensor_set_id in data["sensor_sets"]:
            data["sensor_sets"][sensor_set_id]["updated_at"] = self._get_timestamp()
            data["sensor_sets"][sensor_set_id]["sensor_count"] = len(
                [s for s in data["sensors"].values() if s.get("sensor_set_id") == sensor_set_id]
            )

        await self.async_save()

        _LOGGER.debug("Deleted sensor: %s", unique_id)
        return True

    # Compatibility with existing Config structures

    def to_config(
        self,
        device_identifier: str | None = None,
        sensor_set_id: str | None = None,
    ) -> Config:
        """
        Convert stored data to Config object for compatibility.

        This method reconstructs the original YAML structure and uses
        the same parsing logic as YAML files to ensure consistency.

        Args:
            device_identifier: Filter by device identifier
            sensor_set_id: Filter by sensor set identifier

        Returns:
            Config object compatible with existing code
        """
        data = self._ensure_loaded()

        # Always construct Config from current sensor state
        sensors = self.list_sensors(device_identifier, sensor_set_id)

        # Get global settings from the specific sensor set if provided
        global_settings = {}
        if sensor_set_id and sensor_set_id in data["sensor_sets"]:
            global_settings = data["sensor_sets"][sensor_set_id].get("global_settings", {})

        return Config(
            version=data.get("version", "1.0"),
            sensors=sensors,
            global_settings=global_settings,
        )

    async def async_from_config(
        self,
        config: Config,
        sensor_set_id: str,
        device_identifier: str | None = None,
    ) -> None:
        """
        Store a Config object (for migration from YAML).

        Args:
            config: Config object to store
            sensor_set_id: Sensor set identifier for bulk management
            device_identifier: Device to associate with
        """
        data = self._ensure_loaded()

        # Store global settings in the sensor set metadata
        if sensor_set_id in data["sensor_sets"]:
            data["sensor_sets"][sensor_set_id]["global_settings"] = config.global_settings

        # Store all sensors in bulk
        await self.async_store_sensors_bulk(
            config.sensors,
            sensor_set_id,
            device_identifier,
        )

    # Utility methods

    def _serialize_sensor_config(self, sensor_config: SensorConfig) -> dict[str, Any]:
        """Serialize a SensorConfig to JSON-compatible dict."""
        import json

        def set_to_list(obj: Any) -> list[Any]:
            """Convert sets to lists for JSON serialization."""
            if isinstance(obj, set):
                return list(obj)
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        # Convert to dict first
        config_dict = asdict(sensor_config)

        # Convert to JSON string and back to handle sets
        json_str = json.dumps(config_dict, default=set_to_list)
        result: dict[str, Any] = json.loads(json_str)
        return result

    def _deserialize_sensor_config(self, config_data: dict[str, Any]) -> SensorConfig:
        """Deserialize a dict to SensorConfig."""
        # Handle formulas list
        formulas = []
        for formula_data in config_data.get("formulas", []):
            # Convert dependencies list back to set
            if "dependencies" in formula_data and isinstance(formula_data["dependencies"], list):
                formula_data = formula_data.copy()
                formula_data["dependencies"] = set(formula_data["dependencies"])

            formula = FormulaConfig(**formula_data)
            formulas.append(formula)

        # Create sensor config
        config_data_copy = config_data.copy()
        config_data_copy["formulas"] = formulas

        return SensorConfig(**config_data_copy)

    def _apply_global_settings_to_sensors(
        self, sensors: list[SensorConfig], global_settings: dict[str, Any], device_identifier: str | None = None
    ) -> list[SensorConfig]:
        """
        Apply global settings to sensors, creating normalized sensor configs.

        Validates that local overrides don't conflict with global settings.
        Local overrides with different values are fatal errors.
        Local overrides with same values are acceptable.

        Args:
            sensors: List of sensor configurations
            global_settings: Global settings from YAML
            device_identifier: Device identifier override

        Returns:
            List of sensor configurations with global settings applied

        Raises:
            SyntheticSensorsError: If local overrides conflict with global settings
        """
        normalized_sensors = []
        global_variables = global_settings.get("variables", {})
        global_device_identifier = global_settings.get("device_identifier")

        for sensor in sensors:
            # Create a copy of the sensor to avoid modifying the original
            from copy import deepcopy

            normalized_sensor = deepcopy(sensor)

            # Validate and apply global device_identifier
            if global_device_identifier:
                if normalized_sensor.device_identifier and normalized_sensor.device_identifier != global_device_identifier:
                    raise SyntheticSensorsError(
                        f"Sensor '{sensor.unique_id}' has conflicting device_identifier. "
                        f"Local: '{normalized_sensor.device_identifier}', Global: '{global_device_identifier}'. "
                        f"Local overrides with different values are not allowed."
                    )
                normalized_sensor.device_identifier = global_device_identifier
            elif not normalized_sensor.device_identifier:
                # Use provided device_identifier if no global or local device_identifier
                normalized_sensor.device_identifier = device_identifier

            # Validate and apply global variables to all formulas
            if global_variables:
                for formula in normalized_sensor.formulas:
                    if formula.variables is None:
                        formula.variables = {}

                    # Check for conflicting local variables - locals MUST NOT override globals
                    for var_name, global_value in global_variables.items():
                        if var_name in formula.variables:
                            local_value = formula.variables[var_name]
                            if local_value != global_value:
                                raise SyntheticSensorsError(
                                    f"Sensor '{sensor.unique_id}' formula '{formula.id}' has conflicting variable '{var_name}'. "
                                    f"Local: '{local_value}', Global: '{global_value}'. "
                                    f"Local overrides with different values are not allowed."
                                )

                    # Apply global variables - they are mandatory for all sensors in the set
                    # Local variables are added on top of globals (no conflicts allowed)
                    merged_variables = global_variables.copy()
                    merged_variables.update(formula.variables)
                    formula.variables = merged_variables

            normalized_sensors.append(normalized_sensor)

        return normalized_sensors

    def _validate_no_global_conflicts(self, sensors: list[SensorConfig], global_settings: dict[str, Any]) -> None:
        """
        Validate that local settings don't conflict with global settings during import.

        Args:
            sensors: List of sensor configurations from YAML
            global_settings: Global settings from YAML

        Raises:
            SyntheticSensorsError: If local settings conflict with global settings
        """
        global_device_identifier = global_settings.get("device_identifier")
        global_variables = global_settings.get("variables", {})

        for sensor in sensors:
            # Check device_identifier conflicts
            if global_device_identifier and sensor.device_identifier and sensor.device_identifier != global_device_identifier:
                raise SyntheticSensorsError(
                    f"Sensor '{sensor.unique_id}' has conflicting device_identifier. "
                    f"Local: '{sensor.device_identifier}', Global: '{global_device_identifier}'. "
                    f"Local device_identifier must match global device_identifier or be omitted."
                )

            # Check variable conflicts in all formulas
            for formula in sensor.formulas:
                if formula.variables:
                    for var_name, local_value in formula.variables.items():
                        if var_name in global_variables:
                            global_value = global_variables[var_name]
                            if local_value != global_value:
                                raise SyntheticSensorsError(
                                    f"Sensor '{sensor.unique_id}' formula '{formula.id}' has conflicting variable '{var_name}'. "
                                    f"Local: '{local_value}', Global: '{global_value}'. "
                                    f"Local variables must match global variables or be omitted."
                                )

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime

        return datetime.now().isoformat()

    def _get_sensor_set_header(self, sensor_set_id: str) -> dict[str, Any]:
        """
        Extract sensor set header information (version and global settings).

        Args:
            sensor_set_id: Sensor set identifier

        Returns:
            Dictionary with version and global_settings (if any)
        """
        data = self._ensure_loaded()

        header = {"version": "1.0"}

        # Add global settings if they exist for this sensor set
        if sensor_set_id in data["sensor_sets"]:
            sensor_set_metadata = data["sensor_sets"][sensor_set_id]
            global_settings = sensor_set_metadata.get("global_settings", {})
            if global_settings:
                header["global_settings"] = global_settings

        return header

    def _validate_sensor_with_context(self, sensor_config: SensorConfig, sensor_set_id: str) -> list[str]:
        """
        Validate a sensor configuration within the context of its sensor set.

        This creates a minimal YAML structure with the sensor set header (version/globals)
        plus the sensor being validated, then performs full validation including:
        - Standard sensor validation
        - Global settings conflict validation
        - Schema validation

        Args:
            sensor_config: Sensor configuration to validate
            sensor_set_id: Sensor set identifier for context

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        try:
            # Get sensor set header (version and global settings)
            header = self._get_sensor_set_header(sensor_set_id)

            # Create minimal YAML structure for validation
            test_yaml_data = header.copy()
            test_yaml_data["sensors"] = {sensor_config.unique_id: {}}

            # Convert sensor to YAML-like dict format for validation
            sensor_dict: dict[str, Any] = {
                "name": sensor_config.name,
                "enabled": sensor_config.enabled,
            }

            # Add device_identifier if present
            if sensor_config.device_identifier:
                sensor_dict["device_identifier"] = sensor_config.device_identifier

            # Add optional fields
            if sensor_config.update_interval is not None:
                sensor_dict["update_interval"] = sensor_config.update_interval
            if sensor_config.category:
                sensor_dict["category"] = sensor_config.category
            if sensor_config.description:
                sensor_dict["description"] = sensor_config.description

            # Handle formulas - for validation, we need at least the main formula
            if sensor_config.formulas:
                # Find main formula (id matches sensor unique_id or legacy "main")
                main_formula = None
                for formula in sensor_config.formulas:
                    if formula.id == sensor_config.unique_id or formula.id == "main":
                        main_formula = formula
                        break

                if main_formula:
                    sensor_dict["formula"] = main_formula.formula

                    # Add variables if present
                    if main_formula.variables:
                        sensor_dict["variables"] = main_formula.variables

                    # Add other formula properties
                    if main_formula.unit_of_measurement:
                        sensor_dict["unit_of_measurement"] = main_formula.unit_of_measurement
                    if main_formula.device_class:
                        sensor_dict["device_class"] = main_formula.device_class
                    if main_formula.state_class:
                        sensor_dict["state_class"] = main_formula.state_class
                    if main_formula.icon:
                        sensor_dict["icon"] = main_formula.icon

            test_yaml_data["sensors"][sensor_config.unique_id] = sensor_dict

            # Perform schema validation
            from .schema_validator import validate_yaml_config

            schema_result = validate_yaml_config(test_yaml_data)

            if not schema_result["valid"]:
                for error in schema_result["errors"]:
                    errors.append(f"Schema validation: {error.message}")

            # Perform configuration validation using ConfigManager
            from typing import cast

            from .config_manager import ConfigDict, ConfigManager

            config_manager = ConfigManager(self.hass)

            try:
                config = config_manager.load_from_dict(cast(ConfigDict, test_yaml_data))

                # Validate the config
                config_errors = config.validate()
                errors.extend(config_errors)

                # Additional validation: check for global settings conflicts
                if len(config.sensors) > 0:
                    sensor = config.sensors[0]
                    global_settings = config.global_settings

                    if global_settings:
                        # Use the existing validation method
                        try:
                            self._validate_no_global_conflicts([sensor], global_settings)
                        except Exception as e:
                            errors.append(str(e))

            except Exception as e:
                errors.append(f"Configuration validation failed: {e}")

        except Exception as e:
            errors.append(f"Validation setup failed: {e}")

        return errors

    def get_sensor_set(self, sensor_set_id: str) -> SensorSet:
        """
        Get a SensorSet handle for individual sensor set operations.

        Args:
            sensor_set_id: Sensor set identifier

        Returns:
            SensorSet handle for the specified sensor set
        """
        from .sensor_set import SensorSet

        return SensorSet(self, sensor_set_id)

    # Convenience methods for integration support

    def sensor_set_exists(self, sensor_set_id: str) -> bool:
        """
        Check if a sensor set exists.

        Args:
            sensor_set_id: Sensor set identifier

        Returns:
            True if sensor set exists, False otherwise
        """
        return self.get_sensor_set_metadata(sensor_set_id) is not None

    def get_sensor_count(self, sensor_set_id: str | None = None) -> int:
        """
        Get count of sensors in storage.

        Args:
            sensor_set_id: Optional sensor set to filter by

        Returns:
            Number of sensors
        """
        data = self._ensure_loaded()

        if sensor_set_id:
            # Count sensors in specific sensor set
            count = 0
            for sensor_data in data["sensors"].values():
                if sensor_data.get("sensor_set_id") == sensor_set_id:
                    count += 1
            return count
        else:
            # Count all sensors
            return len(data["sensors"])

    async def async_clear_all_data(self) -> None:
        """
        Clear all data from storage.

        This is useful for testing or complete resets.
        """
        data = self._ensure_loaded()
        data["sensors"].clear()
        data["sensor_sets"].clear()
        await self.async_save()
        _LOGGER.info("Cleared all synthetic sensor storage data")

    def get_storage_stats(self) -> dict[str, Any]:
        """
        Get storage statistics.

        Returns:
            Dictionary with storage statistics
        """
        data = self._ensure_loaded()

        # Count sensors by sensor set
        sensor_set_counts: dict[str, int] = {}
        for sensor_data in data["sensors"].values():
            sensor_set_id = sensor_data.get("sensor_set_id", "unknown")
            sensor_set_counts[sensor_set_id] = sensor_set_counts.get(sensor_set_id, 0) + 1

        return {
            "total_sensors": len(data["sensors"]),
            "total_sensor_sets": len(data["sensor_sets"]),
            "sensor_sets": sensor_set_counts,
        }

    def has_data(self) -> bool:
        """
        Check if storage has any data.

        Returns:
            True if storage has sensors or sensor sets, False otherwise
        """
        data = self._ensure_loaded()
        return len(data["sensors"]) > 0 or len(data["sensor_sets"]) > 0
