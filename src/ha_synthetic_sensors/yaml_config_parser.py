"""YAML configuration parser for synthetic sensors.

This module handles YAML parsing, validation, and conversion to configuration objects.
"""

import logging
from pathlib import Path
from typing import Any, cast

import aiofiles
import yaml

from .config_models import Config, FormulaConfig, SensorConfig
from .config_types import YAML_SYNTAX_ERROR_TEMPLATE, ConfigDict
from .formula_utils import add_optional_formula_fields
from .schema_validator import validate_yaml_config

_LOGGER = logging.getLogger(__name__)


def trim_yaml_keys(obj: Any) -> Any:
    """Recursively trim whitespace from dictionary keys in YAML data.

    Args:
        obj: The object to process (dict, list, or other)

    Returns:
        The processed object with trimmed keys
    """
    if isinstance(obj, dict):
        return {key.strip() if isinstance(key, str) else key: trim_yaml_keys(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [trim_yaml_keys(item) for item in obj]
    return obj


class YAMLConfigParser:
    """Handles YAML parsing and validation for synthetic sensor configurations."""

    def __init__(self) -> None:
        """Initialize the YAML parser."""
        self._logger = _LOGGER.getChild(self.__class__.__name__)

    def load_yaml_file(self, file_path: Path) -> ConfigDict:
        """Load and parse YAML file.

        Args:
            file_path: Path to YAML file

        Returns:
            Parsed YAML data as dictionary

        Raises:
            ValueError: If file cannot be loaded or parsed
        """
        try:
            with open(file_path, encoding="utf-8") as file:
                yaml_data_raw = yaml.safe_load(file)
                yaml_data = trim_yaml_keys(yaml_data_raw)

            if not yaml_data:
                self._logger.warning("Empty configuration file")
                return {}

            return cast(ConfigDict, yaml_data)

        except yaml.YAMLError as e:
            error_msg = YAML_SYNTAX_ERROR_TEMPLATE.format(error=str(e))
            self._logger.error("YAML syntax error: %s", error_msg)
            raise ValueError(f"YAML syntax error: {e}") from e
        except Exception as e:
            self._logger.error("Failed to load YAML file: %s", e)
            raise ValueError(f"Failed to load YAML file: {e}") from e

    async def async_load_yaml_file(self, file_path: Path) -> ConfigDict:
        """Load and parse YAML file asynchronously.

        Args:
            file_path: Path to YAML file

        Returns:
            Parsed YAML data as dictionary

        Raises:
            ValueError: If file cannot be loaded or parsed
        """
        try:
            async with aiofiles.open(file_path, encoding="utf-8") as file:
                content = await file.read()
                yaml_data_raw = yaml.safe_load(content)
                yaml_data = trim_yaml_keys(yaml_data_raw)

            if not yaml_data:
                self._logger.warning("Empty configuration file")
                return {}

            return cast(ConfigDict, yaml_data)

        except yaml.YAMLError as e:
            error_msg = YAML_SYNTAX_ERROR_TEMPLATE.format(error=str(e))
            self._logger.error("YAML syntax error: %s", error_msg)
            raise ValueError(f"YAML syntax error: {e}") from e
        except Exception as e:
            self._logger.error("Failed to load YAML file: %s", e)
            raise ValueError(f"Failed to load YAML file: {e}") from e

    def parse_yaml_content(self, yaml_content: str) -> ConfigDict:
        """Parse YAML content string.

        Args:
            yaml_content: YAML content as string

        Returns:
            Parsed YAML data as dictionary

        Raises:
            ValueError: If content cannot be parsed
        """
        try:
            yaml_data_raw = yaml.safe_load(yaml_content)
            yaml_data = trim_yaml_keys(yaml_data_raw)

            if not yaml_data:
                self._logger.warning("Empty YAML content")
                return {}

            return cast(ConfigDict, yaml_data)

        except yaml.YAMLError as e:
            error_msg = YAML_SYNTAX_ERROR_TEMPLATE.format(error=str(e))
            self._logger.error("YAML syntax error: %s", error_msg)
            raise ValueError(f"YAML syntax error: {e}") from e
        except Exception as e:
            self._logger.error("Failed to parse YAML content: %s", e)
            raise ValueError(f"Failed to parse YAML content: {e}") from e

    def validate_raw_yaml_structure(self, yaml_content: str) -> None:
        """Validate raw YAML structure before parsing.

        Args:
            yaml_content: YAML content to validate

        Raises:
            ValueError: If YAML structure is invalid
        """
        try:
            yaml_data = yaml.safe_load(yaml_content)
            if not yaml_data:
                return

            if not isinstance(yaml_data, dict):
                raise ValueError("YAML root must be a dictionary")

            # Check for required top-level keys
            required_keys = {"sensors"}
            missing_keys = required_keys - set(yaml_data.keys())
            if missing_keys:
                raise ValueError(f"Missing required top-level keys: {missing_keys}")

            # Validate sensors section
            sensors = yaml_data.get("sensors")
            if not isinstance(sensors, dict):
                raise ValueError("'sensors' must be a dictionary")

            # Validate each sensor
            for sensor_key, sensor_data in sensors.items():
                if not isinstance(sensor_data, dict):
                    raise ValueError(f"Sensor '{sensor_key}' must be a dictionary")

                # Check for required sensor fields
                if "formula" not in sensor_data:
                    raise ValueError(f"Sensor '{sensor_key}' missing required 'formula' field")

        except yaml.YAMLError as e:
            error_msg = YAML_SYNTAX_ERROR_TEMPLATE.format(error=str(e))
            self._logger.error("YAML validation error: %s", error_msg)
            raise ValueError(f"YAML validation error: {e}") from e

    def validate_yaml_data(self, yaml_data: dict[str, Any]) -> dict[str, Any]:
        """Validate YAML data structure and content.

        Args:
            yaml_data: YAML data to validate

        Returns:
            Validated YAML data

        Raises:
            ValueError: If validation fails
        """
        if not yaml_data:
            return {}

        if not isinstance(yaml_data, dict):
            raise ValueError("YAML root must be a dictionary")

        # Validate schema
        validate_yaml_config(yaml_data)

        return yaml_data

    def config_to_yaml(self, config: Config) -> dict[str, Any]:
        """Convert Config object to YAML dictionary.

        Args:
            config: Configuration object

        Returns:
            YAML dictionary representation
        """
        yaml_data: dict[str, Any] = {}

        # Add global settings if present
        if config.global_settings:
            yaml_data["global_settings"] = config.global_settings

        # Add sensors
        if config.sensors:
            yaml_data["sensors"] = {}
            for sensor in config.sensors:
                yaml_data["sensors"][sensor.unique_id] = self._sensor_to_yaml_dict(sensor)

        return yaml_data

    def _sensor_to_yaml_dict(self, sensor: SensorConfig) -> dict[str, Any]:
        """Convert SensorConfig to YAML dictionary.

        Args:
            sensor: Sensor configuration

        Returns:
            YAML dictionary representation
        """
        sensor_data: dict[str, Any] = {}

        # Add formulas (convert list to dict with formula IDs as keys)
        if sensor.formulas:
            sensor_data["formulas"] = {}
            for formula in sensor.formulas:
                sensor_data["formulas"][formula.id] = self._formula_to_yaml_dict(formula)

        # Add optional sensor-level fields
        self._add_optional_sensor_fields(sensor_data, sensor)

        # Add device association fields
        self._add_device_fields(sensor_data, sensor)

        return sensor_data

    def _add_optional_sensor_fields(self, sensor_data: dict[str, Any], sensor: SensorConfig) -> None:
        """Add optional sensor-level fields to YAML dictionary."""
        optional_fields = {
            "name": sensor.name,
            "description": sensor.description,
            "enabled": sensor.enabled,
            "update_interval": sensor.update_interval,
            "category": sensor.category,
            "entity_id": sensor.entity_id,
            "metadata": sensor.metadata,
        }

        for field_name, field_value in optional_fields.items():
            if field_value is not None:
                sensor_data[field_name] = field_value

    def _add_device_fields(self, sensor_data: dict[str, Any], sensor: SensorConfig) -> None:
        """Add device association fields to YAML dictionary."""
        device_fields = {
            "device_identifier": sensor.device_identifier,
            "device_name": sensor.device_name,
            "device_manufacturer": sensor.device_manufacturer,
            "device_model": sensor.device_model,
            "device_sw_version": sensor.device_sw_version,
            "device_hw_version": sensor.device_hw_version,
            "suggested_area": sensor.suggested_area,
        }

        for field_name, field_value in device_fields.items():
            if field_value is not None:
                sensor_data[field_name] = field_value

    def _formula_to_yaml_dict(self, formula: FormulaConfig) -> dict[str, Any]:
        """Convert FormulaConfig to YAML dictionary.

        Args:
            formula: Formula configuration

        Returns:
            YAML dictionary representation
        """
        formula_data: dict[str, Any] = {
            "formula": formula.formula,
        }

        # Add optional fields
        self._add_optional_formula_fields(formula_data, formula)

        return formula_data

    def _add_optional_formula_fields(self, formula_data: dict[str, Any], formula: FormulaConfig) -> None:
        """Add optional formula fields to YAML dictionary.

        Args:
            formula_data: Formula YAML data
            formula: Formula configuration
        """
        add_optional_formula_fields(formula_data, formula, include_variables=True)
