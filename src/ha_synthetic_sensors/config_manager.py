"""
Configuration Manager - Core configuration data structures and validation.

This module provides the foundational data structures and validation logic
for YAML-based synthetic sensor configuration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict, Union

import yaml  # type: ignore[import-untyped]
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

_LOGGER = logging.getLogger(__name__)

# Type alias for attribute values (allows complex types for formula metadata)
AttributeValue = Union[str, float, int, bool, list[str], dict[str, Any]]


# TypedDicts for YAML config structures
class FormulaConfigDict(TypedDict, total=False):
    id: str
    formula: str
    name: str
    variables: dict[str, str]
    unit_of_measurement: str
    device_class: str
    state_class: str
    icon: str
    attributes: dict[str, AttributeValue]


class SensorConfigDict(TypedDict, total=False):
    unique_id: str
    name: str
    formulas: list[FormulaConfigDict]
    enabled: bool
    update_interval: int
    category: str
    description: str


class ConfigDict(TypedDict, total=False):
    version: str
    global_settings: dict[str, AttributeValue]
    sensors: list[SensorConfigDict]


@dataclass
class FormulaConfig:
    """Configuration for a single formula within a synthetic sensor."""

    id: str  # REQUIRED: Formula identifier
    formula: str
    name: str | None = None  # OPTIONAL: Display name
    unit_of_measurement: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    icon: str | None = None
    attributes: dict[str, AttributeValue] = field(default_factory=dict)
    dependencies: set[str] = field(default_factory=set)

    def __post_init__(self):
        """Extract dependencies from formula after initialization."""
        if not self.dependencies:
            self.dependencies = self._extract_dependencies()

    def _extract_dependencies(self) -> set[str]:
        """Extract entity dependencies from the formula string."""
        # This will be enhanced to properly parse entity references
        # For now, simple regex-based extraction
        import re

        pattern = r'entity\(["\']([^"\']+)["\']\)'
        matches = re.findall(pattern, self.formula)
        return set(matches)


@dataclass
class SensorConfig:
    """Configuration for a complete synthetic sensor with multiple formulas."""

    unique_id: str  # REQUIRED: Unique identifier for HA entity creation
    formulas: list[FormulaConfig] = field(default_factory=list)
    name: str | None = None  # OPTIONAL: Display name
    enabled: bool = True
    update_interval: int | None = None
    category: str | None = None
    description: str | None = None

    def get_all_dependencies(self) -> set[str]:
        """Get all entity dependencies across all formulas."""
        deps = set()
        for formula in self.formulas:
            deps.update(formula.dependencies)
        return deps

    def validate(self) -> list[str]:
        """Validate sensor configuration and return list of errors."""
        errors = []

        if not self.unique_id:
            errors.append("Sensor unique_id is required")

        if not self.formulas:
            errors.append(f"Sensor '{self.unique_id}' must have at least one formula")

        formula_ids = [f.id for f in self.formulas]
        if len(formula_ids) != len(set(formula_ids)):
            errors.append(f"Sensor '{self.unique_id}' has duplicate formula IDs")

        return errors


@dataclass
class Config:
    """Complete configuration containing all synthetic sensors."""

    version: str = "1.0"
    sensors: list[SensorConfig] = field(default_factory=list)
    global_settings: dict[str, AttributeValue] = field(default_factory=dict)

    def get_sensor_by_unique_id(self, unique_id: str) -> SensorConfig | None:
        """Get a sensor configuration by unique_id."""
        for sensor in self.sensors:
            if sensor.unique_id == unique_id:
                return sensor
        return None

    def get_sensor_by_name(self, name: str) -> SensorConfig | None:
        """Get a sensor configuration by name (legacy method)."""
        for sensor in self.sensors:
            if sensor.name == name or sensor.unique_id == name:
                return sensor
        return None

    def get_all_dependencies(self) -> set[str]:
        """Get all entity dependencies across all sensors."""
        deps = set()
        for sensor in self.sensors:
            deps.update(sensor.get_all_dependencies())
        return deps

    def validate(self) -> list[str]:
        """Validate the entire configuration and return list of errors."""
        errors = []

        # Check for duplicate sensor unique_ids
        sensor_unique_ids = [s.unique_id for s in self.sensors]
        if len(sensor_unique_ids) != len(set(sensor_unique_ids)):
            errors.append("Duplicate sensor unique_ids found")

        # Validate each sensor
        for sensor in self.sensors:
            sensor_errors = sensor.validate()
            errors.extend(sensor_errors)

        return errors


class ConfigManager:
    """Manages loading, validation, and access to synthetic sensor configurations."""

    def __init__(
        self, hass: HomeAssistant, config_path: str | Path | None = None
    ) -> None:
        """Initialize the configuration manager.

        Args:
            hass: Home Assistant instance
            config_path: Optional path to YAML configuration file
        """
        self._hass = hass
        self._config_path = Path(config_path) if config_path else None
        self._config: Config | None = None
        self._logger = _LOGGER.getChild(self.__class__.__name__)

    @property
    def config(self) -> Config | None:
        """Get the current configuration."""
        return self._config

    def load_config(self, config_path: str | Path | None = None) -> Config:
        """Load configuration from YAML file.

        Args:
            config_path: Optional path to override the default config path

        Returns:
            Config: Loaded configuration object

        Raises:
            ConfigEntryError: If configuration loading or validation fails
        """
        path = Path(config_path) if config_path else self._config_path

        if not path or not path.exists():
            self._logger.warning("No configuration file found, using empty config")
            self._config = Config()
            return self._config

        try:
            with open(path, encoding="utf-8") as file:
                yaml_data = yaml.safe_load(file)

            if not yaml_data:
                self._logger.warning("Empty configuration file, using empty config")
                self._config = Config()
                return self._config

            self._config = self._parse_yaml_config(yaml_data)

            # Validate the loaded configuration
            errors = self._config.validate()
            if errors:
                error_msg = f"Configuration validation failed: {', '.join(errors)}"
                self._logger.error(error_msg)
                raise ConfigEntryError(error_msg)

            self._logger.info(
                "Loaded configuration with %d sensors from %s",
                len(self._config.sensors),
                path,
            )

            return self._config

        except Exception as exc:
            error_msg = f"Failed to load configuration from {path}: {exc}"
            self._logger.error(error_msg)
            raise ConfigEntryError(error_msg) from exc

    def _parse_yaml_config(self, yaml_data: ConfigDict) -> Config:
        """Parse YAML data into Config object.

        Args:
            yaml_data: Raw YAML data dictionary

        Returns:
            Config: Parsed configuration object
        """
        config = Config(
            version=yaml_data.get("version", "1.0"),
            global_settings=yaml_data.get("global_settings", {}),
        )

        # Parse sensors
        sensors_data = yaml_data.get("sensors", [])
        for sensor_data in sensors_data:
            sensor = self._parse_sensor_config(sensor_data)
            config.sensors.append(sensor)

        return config

    def _parse_sensor_config(self, sensor_data: SensorConfigDict) -> SensorConfig:
        """Parse a single sensor configuration.

        Args:
            sensor_data: Sensor configuration dictionary

        Returns:
            SensorConfig: Parsed sensor configuration
        """
        # Support both old 'name' and new 'unique_id' field for migration
        unique_id = sensor_data.get("unique_id") or sensor_data.get("name")
        if not unique_id:
            raise ValueError("Sensor must have either 'unique_id' or 'name' field")

        sensor = SensorConfig(
            unique_id=unique_id,
            name=str(sensor_data.get("name") or sensor_data.get("friendly_name") or ""),
            enabled=sensor_data.get("enabled", True),
            update_interval=sensor_data.get("update_interval"),
            category=sensor_data.get("category"),
            description=sensor_data.get("description"),
        )

        # Parse formulas
        formulas_data = sensor_data.get("formulas", [])
        for formula_data in formulas_data:
            formula = self._parse_formula_config(formula_data)
            sensor.formulas.append(formula)

        return sensor

    def _parse_formula_config(self, formula_data: FormulaConfigDict) -> FormulaConfig:
        """Parse a single formula configuration.

        Args:
            formula_data: Formula configuration dictionary

        Returns:
            FormulaConfig: Parsed formula configuration
        """
        # Support both old 'name' and new 'id' field for migration
        formula_id = formula_data.get("id") or formula_data.get("name")
        if not formula_id:
            raise ValueError("Formula must have either 'id' or 'name' field")

        formula_str = formula_data.get("formula")
        if formula_str is None:
            raise ValueError("Formula must have a 'formula' field")

        return FormulaConfig(
            id=formula_id,
            name=formula_data.get("name"),  # Use name as display name if provided
            formula=formula_str,
            unit_of_measurement=formula_data.get("unit_of_measurement"),
            device_class=formula_data.get("device_class"),
            state_class=formula_data.get("state_class"),
            icon=formula_data.get("icon"),
            attributes=formula_data.get("attributes", {}),
        )

    def reload_config(self) -> Config:
        """Reload configuration from the original path.

        Returns:
            Config: Reloaded configuration

        Raises:
            ConfigEntryError: If no path is set or reload fails
        """
        if not self._config_path:
            raise ConfigEntryError("No configuration path set for reload")

        return self.load_config(self._config_path)

    def get_sensor_configs(self, enabled_only: bool = True) -> list[SensorConfig]:
        """Get all sensor configurations.

        Args:
            enabled_only: If True, only return enabled sensors

        Returns:
            list: List of sensor configurations
        """
        if not self._config:
            return []

        if enabled_only:
            return [s for s in self._config.sensors if s.enabled]
        else:
            return self._config.sensors.copy()

    def get_sensor_config(self, name: str) -> SensorConfig | None:
        """Get a specific sensor configuration by name.

        Args:
            name: Sensor name

        Returns:
            SensorConfig or None if not found
        """
        if not self._config:
            return None

        return self._config.get_sensor_by_name(name)

    def validate_dependencies(self) -> dict[str, list[str]]:
        """Validate that all dependencies exist in Home Assistant.

        Returns:
            dict: Mapping of sensor names to lists of missing dependencies
        """
        if not self._config:
            return {}

        missing_deps = {}

        for sensor in self._config.sensors:
            if not sensor.enabled:
                continue

            missing = []
            for dep in sensor.get_all_dependencies():
                if not self._hass.states.get(dep):
                    missing.append(dep)

            if missing:
                missing_deps[sensor.unique_id] = missing

        return missing_deps

    def load_from_file(self, file_path: str | Path) -> Config:
        """Load configuration from a specific file path.

        This is an alias for load_config() for backward compatibility.

        Args:
            file_path: Path to the configuration file

        Returns:
            Config: Loaded configuration object
        """
        return self.load_config(file_path)

    def load_from_yaml(self, yaml_content: str) -> Config:
        """Load configuration from YAML string content.

        Args:
            yaml_content: YAML configuration as string

        Returns:
            Config: Parsed configuration object

        Raises:
            ConfigEntryError: If parsing or validation fails
        """
        try:
            yaml_data = yaml.safe_load(yaml_content)

            if not yaml_data:
                self._logger.warning("Empty YAML content, using empty config")
                self._config = Config()
                return self._config

            self._config = self._parse_yaml_config(yaml_data)

            # Validate the loaded configuration
            errors = self._config.validate()
            if errors:
                error_msg = f"Configuration validation failed: {', '.join(errors)}"
                self._logger.error(error_msg)
                raise ConfigEntryError(error_msg)

            self._logger.info(
                "Loaded configuration with %d sensors from YAML content",
                len(self._config.sensors),
            )

            return self._config

        except Exception as exc:
            error_msg = f"Failed to parse YAML content: {exc}"
            self._logger.error(error_msg)
            raise ConfigEntryError(error_msg) from exc

    def validate_config(self, config: Config | None = None) -> list[str]:
        """Validate a configuration object.

        Args:
            config: Configuration to validate, or current config if None

        Returns:
            list: List of validation error messages
        """
        config_to_validate = config or self._config
        if not config_to_validate:
            return ["No configuration loaded"]

        return config_to_validate.validate()

    def save_config(self, file_path: str | Path | None = None) -> None:
        """Save current configuration to YAML file.

        Args:
            file_path: Path to save to, or use current config path if None

        Raises:
            ConfigEntryError: If no configuration loaded or save fails
        """
        if not self._config:
            raise ConfigEntryError("No configuration loaded to save")

        path = Path(file_path) if file_path else self._config_path
        if not path:
            raise ConfigEntryError("No file path specified for saving")

        try:
            # Convert config back to YAML format
            yaml_data = self._config_to_yaml(self._config)

            with open(path, "w", encoding="utf-8") as file:
                yaml.dump(yaml_data, file, default_flow_style=False, allow_unicode=True)

            self._logger.info("Saved configuration to %s", path)

        except Exception as exc:
            error_msg = f"Failed to save configuration to {path}: {exc}"
            self._logger.error(error_msg)
            raise ConfigEntryError(error_msg) from exc

    def _config_to_yaml(self, config: Config) -> dict[str, Any]:
        """Convert Config object back to YAML-compatible dictionary.

        Args:
            config: Configuration object to convert

        Returns:
            dict: YAML-compatible dictionary
        """
        yaml_data: dict[str, Any] = {
            "version": config.version,
            "sensors": [],
        }

        if config.global_settings:
            yaml_data["global_settings"] = config.global_settings

        for sensor in config.sensors:
            sensor_data: dict[str, Any] = {
                "unique_id": sensor.unique_id,
                "enabled": sensor.enabled,
                "formulas": [],
            }

            if sensor.name:
                sensor_data["name"] = sensor.name
            if sensor.update_interval is not None:
                sensor_data["update_interval"] = sensor.update_interval
            if sensor.category:
                sensor_data["category"] = sensor.category
            if sensor.description:
                sensor_data["description"] = sensor.description

            for formula in sensor.formulas:
                formula_data: dict[str, Any] = {
                    "id": formula.id,
                    "formula": formula.formula,
                }

                if formula.name:
                    formula_data["name"] = formula.name
                if formula.unit_of_measurement:
                    formula_data["unit_of_measurement"] = formula.unit_of_measurement
                if formula.device_class:
                    formula_data["device_class"] = formula.device_class
                if formula.state_class:
                    formula_data["state_class"] = formula.state_class
                if formula.icon:
                    formula_data["icon"] = formula.icon
                if formula.attributes:
                    formula_data["attributes"] = formula.attributes

                sensor_data["formulas"].append(formula_data)

            yaml_data["sensors"].append(sensor_data)

        return yaml_data

    def add_variable(self, name: str, entity_id: str) -> bool:
        """Add a variable to the global settings.

        Args:
            name: Variable name
            entity_id: Entity ID that this variable maps to

        Returns:
            bool: True if variable was added successfully
        """
        if not self._config:
            self._config = Config()

        if "variables" not in self._config.global_settings:
            # Variables is a special case - it's a nested dict[str, str]
            self._config.global_settings["variables"] = dict()  # type: ignore[assignment]

        variables = self._config.global_settings["variables"]
        if isinstance(variables, dict):
            variables[name] = entity_id
            self._logger.info("Added variable: %s = %s", name, entity_id)
            return True

        return False

    def remove_variable(self, name: str) -> bool:
        """Remove a variable from the global settings.

        Args:
            name: Variable name to remove

        Returns:
            bool: True if variable was removed, False if not found
        """
        if not self._config or "variables" not in self._config.global_settings:
            return False

        variables = self._config.global_settings["variables"]
        if isinstance(variables, dict) and name in variables:
            del variables[name]
            self._logger.info("Removed variable: %s", name)
            return True

        return False

    def get_variables(self) -> dict[str, str]:
        """Get all variables from global settings.

        Returns:
            dict: Dictionary of variable name -> entity_id mappings
        """
        if not self._config or "variables" not in self._config.global_settings:
            return {}

        variables = self._config.global_settings["variables"]
        if isinstance(variables, dict):
            # Ensure all values are strings (entity IDs)
            return {k: str(v) for k, v in variables.items()}
        return {}

    def get_sensors(self) -> list[SensorConfig]:
        """Get all sensor configurations (alias for get_sensor_configs).

        Returns:
            list: List of all sensor configurations
        """
        return self.get_sensor_configs(enabled_only=False)

    def validate_configuration(self) -> dict[str, list[str]]:
        """Validate the current configuration and return structured results.

        Returns:
            dict: Dictionary with 'errors' and 'warnings' keys containing lists
        """
        errors = self.validate_config()
        # For now, we don't have separate warnings, but structure it properly
        return {"errors": errors, "warnings": []}

    def is_config_modified(self) -> bool:
        """Check if configuration file has been modified since last load.

        Returns:
            bool: True if file has been modified, False otherwise
        """
        if not self._config_path or not self._config_path.exists():
            return False

        try:
            # For now, always return False - file modification tracking
            # could be implemented with file timestamps if needed
            return False
        except Exception:
            return False
