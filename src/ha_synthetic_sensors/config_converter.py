"""
Config Converter - YAML to Storage conversion utilities for synthetic sensors.

This module provides utilities to convert YAML-based sensor configurations
to storage-compatible JSON format, enabling seamless transition from file-based
configuration to HA storage-based configuration management.

Phase 1 Implementation: Basic conversion support for fresh installations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .config_manager import Config, ConfigManager
from .exceptions import SyntheticSensorsError
from .storage_manager import StorageManager

_LOGGER = logging.getLogger(__name__)


class ConfigConverter:
    """
    Utility class for converting YAML configurations to storage format.

    Provides methods to convert existing YAML-based sensor configurations
    to the new storage-based format while maintaining compatibility and
    preserving all configuration data.
    """

    def __init__(self, storage_manager: StorageManager) -> None:
        """
        Initialize the ConfigConverter.

        Args:
            storage_manager: StorageManager instance for storing converted data
        """
        self.storage_manager = storage_manager

    async def convert_yaml_file_to_storage(
        self,
        yaml_file_path: str | Path,
        sensor_set_name: str,
        device_identifier: str | None = None,
        description: str | None = None,
    ) -> str:
        """
        Convert a YAML configuration file to storage format.

        Args:
            yaml_file_path: Path to the YAML configuration file
            sensor_set_name: Name for the sensor set (for bulk management)
            device_identifier: Device to associate sensors with
            description: Description for the sensor set

        Returns:
            Generated sensor_set_id

        Raises:
            SyntheticSensorsError: If conversion fails
        """
        try:
            # Load and parse YAML configuration
            config_manager = ConfigManager(self.storage_manager.hass)
            config = await config_manager.async_load_from_file(yaml_file_path)

            # Convert to storage format
            sensor_set_id = await self.convert_config_to_storage(
                config,
                sensor_set_name,
                device_identifier,
                description,
            )

            _LOGGER.info(
                "Successfully converted YAML file %s to storage (sensor_set_id: %s)",
                yaml_file_path,
                sensor_set_id,
            )
            return sensor_set_id

        except Exception as err:
            _LOGGER.error("Failed to convert YAML file %s: %s", yaml_file_path, err)
            raise SyntheticSensorsError(f"YAML conversion failed: {err}") from err

    async def convert_yaml_content_to_storage(
        self,
        yaml_content: str,
        sensor_set_name: str,
        device_identifier: str | None = None,
        description: str | None = None,
    ) -> str:
        """
        Convert YAML content string to storage format.

        Args:
            yaml_content: YAML configuration content as string
            sensor_set_name: Name for the sensor set (for bulk management)
            device_identifier: Device to associate sensors with
            description: Description for the sensor set

        Returns:
            Generated sensor_set_id

        Raises:
            SyntheticSensorsError: If conversion fails
        """
        try:
            # Parse YAML content
            config_manager = ConfigManager(self.storage_manager.hass)
            config = config_manager.load_from_yaml(yaml_content)

            # Convert to storage format
            sensor_set_id = await self.convert_config_to_storage(
                config,
                sensor_set_name,
                device_identifier,
                description,
            )

            _LOGGER.info(
                "Successfully converted YAML content to storage (sensor_set_id: %s)",
                sensor_set_id,
            )
            return sensor_set_id

        except Exception as err:
            _LOGGER.error("Failed to convert YAML content: %s", err)
            raise SyntheticSensorsError(f"YAML conversion failed: {err}") from err

    async def convert_config_to_storage(
        self,
        config: Config,
        sensor_set_name: str,
        device_identifier: str | None = None,
        description: str | None = None,
    ) -> str:
        """
        Convert a Config object to storage format.

        Args:
            config: Config object to convert
            sensor_set_name: Name for the sensor set (for bulk management)
            device_identifier: Device to associate sensors with
            description: Description for the sensor set

        Returns:
            Generated sensor_set_id
        """
        # Create sensor set
        import uuid

        sensor_set_id = f"config_converter_{uuid.uuid4().hex[:8]}"
        await self.storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier=device_identifier,
            name=sensor_set_name,
            description=description,
        )

        # Store the config in the sensor set
        await self.storage_manager.async_from_config(
            config,
            sensor_set_id,
            device_identifier,
        )

        _LOGGER.info(
            "Converted config to storage: %d sensors (sensor_set_id: %s)",
            len(config.sensors),
            sensor_set_id,
        )
        return sensor_set_id

    def config_to_yaml(self, config: Config) -> dict[str, Any]:
        """
        Convert a Config object to YAML-compatible dict.

        Args:
            config: Config object to convert

        Returns:
            YAML-compatible dictionary representation of the config
        """
        try:
            config_manager = ConfigManager(self.storage_manager.hass)
            return config_manager._config_to_yaml(config)
        except Exception as err:
            _LOGGER.error("Failed to convert config to YAML dict: %s", err)
            raise SyntheticSensorsError(f"YAML conversion failed: {err}") from err

    def config_to_json(self, config: Config) -> str:
        """
        Convert a Config object to JSON string.

        Args:
            config: Config object to convert

        Returns:
            JSON string representation of the config
        """
        try:
            import json

            # Convert config to dict format suitable for JSON serialization
            config_dict = self._config_to_dict(config)
            return json.dumps(config_dict, indent=2, ensure_ascii=False)
        except Exception as err:
            _LOGGER.error("Failed to convert config to JSON: %s", err)
            raise SyntheticSensorsError(f"JSON conversion failed: {err}") from err

    async def yaml_to_config(self, yaml_data: dict[str, Any]) -> Config:
        """
        Convert YAML data dict to Config object.

        Args:
            yaml_data: YAML configuration data as dict

        Returns:
            Config object
        """
        try:
            # Validate basic structure first
            if yaml_data is None:
                raise SyntheticSensorsError("YAML data cannot be None")
            if not isinstance(yaml_data, dict):
                raise SyntheticSensorsError("YAML data must be a dictionary")
            if "version" not in yaml_data:
                raise SyntheticSensorsError("YAML data must contain 'version' field")
            if "sensors" not in yaml_data:
                raise SyntheticSensorsError("YAML data must contain 'sensors' field")
            if not isinstance(yaml_data["sensors"], dict):
                raise SyntheticSensorsError("YAML 'sensors' field must be a dictionary")

            config_manager = ConfigManager(self.storage_manager.hass)
            return config_manager.load_from_dict(yaml_data)  # type: ignore[arg-type]
        except SyntheticSensorsError:
            raise  # Re-raise our own exceptions
        except Exception as err:
            _LOGGER.error("Failed to convert YAML data to config: %s", err)
            raise SyntheticSensorsError(f"YAML to config conversion failed: {err}") from err

    def json_to_config(self, json_string: str) -> Config:
        """
        Convert JSON string to Config object.

        Args:
            json_string: JSON configuration data as string

        Returns:
            Config object

        Raises:
            SyntheticSensorsError: If conversion fails
        """
        try:
            import json

            config_dict = json.loads(json_string)
            return self._dict_to_config(config_dict)
        except Exception as err:
            _LOGGER.error("Failed to convert JSON to config: %s", err)
            raise SyntheticSensorsError(f"JSON conversion failed: {err}") from err

    def dict_to_config(self, config_dict: dict[str, Any]) -> Config:
        """
        Convert dictionary to Config object.

        Args:
            config_dict: Configuration data as dictionary

        Returns:
            Config object

        Raises:
            SyntheticSensorsError: If conversion fails
        """
        try:
            return self._dict_to_config(config_dict)
        except Exception as err:
            _LOGGER.error("Failed to convert dict to config: %s", err)
            raise SyntheticSensorsError(f"Dict conversion failed: {err}") from err

    async def export_storage_to_yaml(
        self,
        output_file_path: str | Path,
        device_identifier: str | None = None,
        sensor_set_id: str | None = None,
    ) -> None:
        """
        Export storage configuration to YAML file.

        Args:
            output_file_path: Path for the output YAML file
            device_identifier: Filter by device identifier
            sensor_set_id: Filter by sensor set identifier
        """
        try:
            # Use storage manager's export method to reconstruct YAML from current state
            if sensor_set_id:
                yaml_content_str = self.storage_manager.export_yaml(sensor_set_id)
            else:
                # For device filtering without sensor_set_id, we need to reconstruct
                # This is a less common case - typically exports are done by sensor_set_id
                config = self.storage_manager.to_config(device_identifier, sensor_set_id)
                config_manager = ConfigManager(self.storage_manager.hass)
                yaml_content = config_manager._config_to_yaml(config)
                yaml_content_str = yaml.dump(yaml_content, default_flow_style=False, sort_keys=False)

            # Write to file
            output_path = Path(output_file_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(yaml_content_str)

            _LOGGER.info(
                "Exported storage to YAML file: %s",
                output_file_path,
            )

        except Exception as err:
            _LOGGER.error("Failed to export storage to YAML: %s", err)
            raise SyntheticSensorsError(f"YAML export failed: {err}") from err

    async def export_storage_to_json(
        self,
        output_file_path: str | Path,
        device_identifier: str | None = None,
        sensor_set_id: str | None = None,
    ) -> None:
        """
        Export storage configuration to JSON file.

        Args:
            output_file_path: Path for the output JSON file
            device_identifier: Filter by device identifier
            sensor_set_id: Filter by sensor set identifier
        """
        try:
            # Get config from storage
            config = self.storage_manager.to_config(device_identifier, sensor_set_id)

            # Convert to JSON
            json_content = self.config_to_json(config)

            # Write to file
            output_path = Path(output_file_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(json_content)

            _LOGGER.info(
                "Exported storage to JSON file: %s (%d sensors)",
                output_file_path,
                len(config.sensors),
            )

        except Exception as err:
            _LOGGER.error("Failed to export storage to JSON: %s", err)
            raise SyntheticSensorsError(f"JSON export failed: {err}") from err

    def validate_yaml_compatibility(self, config: Config) -> list[str]:
        """
        Validate that a config is compatible with YAML format.

        Args:
            config: Config to validate

        Returns:
            List of compatibility issues (empty if compatible)
        """
        issues = []

        # Check for storage-specific features that don't translate to YAML
        for sensor in config.sensors:
            # Check for device association fields that YAML format doesn't support
            if sensor.device_identifier:
                issues.append(f"Sensor '{sensor.unique_id}' has device_identifier which is not supported in YAML format")

        return issues

    def _config_to_dict(self, config: Config) -> dict[str, Any]:
        """Convert Config object to dictionary for JSON serialization."""
        from dataclasses import asdict

        # Convert using dataclass asdict, then clean up for JSON
        config_dict = asdict(config)

        # Clean up any non-JSON serializable items
        cleaned_dict = self._clean_dict_for_json(config_dict)
        if not isinstance(cleaned_dict, dict):
            raise ValueError("Config conversion did not result in dictionary")
        return cleaned_dict

    def _dict_to_config(self, config_dict: dict[str, Any]) -> Config:
        """Convert dictionary to Config object."""
        from .config_manager import FormulaConfig, SensorConfig

        # Reconstruct sensors list
        sensors = []
        for sensor_data in config_dict.get("sensors", []):
            # Reconstruct formulas
            formulas = []
            for formula_data in sensor_data.get("formulas", []):
                formula = FormulaConfig(**formula_data)
                formulas.append(formula)

            # Create sensor config
            sensor_data_copy = sensor_data.copy()
            sensor_data_copy["formulas"] = formulas
            sensor = SensorConfig(**sensor_data_copy)
            sensors.append(sensor)

        return Config(
            version=config_dict.get("version", "1.0"),
            sensors=sensors,
            global_settings=config_dict.get("global_settings", {}),
        )

    def _clean_dict_for_json(self, obj: Any) -> Any:
        """Recursively clean dictionary for JSON serialization."""
        if isinstance(obj, dict):
            return {key: self._clean_dict_for_json(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._clean_dict_for_json(item) for item in obj]
        elif isinstance(obj, set):
            return list(obj)  # Convert sets to lists for JSON
        elif hasattr(obj, "__dict__"):
            # Convert objects to dicts
            return self._clean_dict_for_json(obj.__dict__)
        else:
            return obj

    # Utility methods

    def generate_conversion_summary(self, config: Config) -> dict[str, Any]:
        """Generate conversion summary - alias for get_conversion_summary."""
        return self.get_conversion_summary(config)

    def get_conversion_summary(self, config: Config) -> dict[str, Any]:
        """
        Get a summary of what will be converted from a config.

        Args:
            config: Config to analyze

        Returns:
            Dictionary with conversion summary information
        """
        summary: dict[str, Any] = {
            "version": config.version,
            "sensor_count": len(config.sensors),
            "global_settings_count": len(config.global_settings),
            "sensors_by_type": {},
            "device_associations": set(),
            "compatibility_issues": self.validate_yaml_compatibility(config),
        }

        # Analyze sensors
        for sensor in config.sensors:
            # Count formulas per sensor
            formula_count = len(sensor.formulas)
            sensor_type = f"{formula_count}_formula{'s' if formula_count != 1 else ''}"
            summary["sensors_by_type"][sensor_type] = summary["sensors_by_type"].get(sensor_type, 0) + 1

            # Track device associations
            if sensor.device_identifier:
                summary["device_associations"].add(sensor.device_identifier)

        # Convert set to list for JSON serialization
        summary["device_associations"] = list(summary["device_associations"])

        return summary
