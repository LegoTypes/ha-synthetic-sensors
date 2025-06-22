"""
Configuration Manager - Core configuration data structures and validation.

This module provides the foundational data structures and validation logic
for YAML-based synthetic sensor configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Any, TypeAlias, TypedDict

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
import yaml

from .dependency_parser import DependencyParser
from .schema_validator import validate_yaml_config

_LOGGER = logging.getLogger(__name__)

# Type alias for attribute values (allows complex types for formula metadata)
AttributeValue = str | float | int | bool | list[str] | dict[str, Any]

# Type aliases for Home Assistant constants - use the actual enum types
DeviceClassType: TypeAlias = SensorDeviceClass | str  # str for YAML parsing, enum for runtime
StateClassType: TypeAlias = SensorStateClass | str  # str for YAML parsing, enum for runtime


# TypedDicts for v2.0 YAML config structures
class AttributeConfigDict(TypedDict, total=False):
    formula: str
    unit_of_measurement: str
    device_class: DeviceClassType
    state_class: StateClassType
    icon: str
    variables: dict[str, str]  # Allow attributes to define additional variables


class SensorConfigDict(TypedDict, total=False):
    name: str
    description: str
    enabled: bool
    update_interval: int
    category: str
    entity_id: str  # Optional: Explicit entity ID for the sensor
    # Main formula syntax
    formula: str
    attributes: dict[str, AttributeConfigDict]
    # Common properties
    variables: dict[str, str]
    unit_of_measurement: str
    device_class: DeviceClassType
    state_class: StateClassType
    icon: str
    extra_attributes: dict[str, AttributeValue]


class ConfigDict(TypedDict, total=False):
    version: str
    global_settings: dict[str, AttributeValue]
    sensors: dict[str, SensorConfigDict]


@dataclass
class FormulaConfig:
    """Configuration for a single formula within a synthetic sensor."""

    id: str  # REQUIRED: Formula identifier
    formula: str
    name: str | None = None  # OPTIONAL: Display name
    unit_of_measurement: str | None = None
    device_class: DeviceClassType | None = None
    state_class: StateClassType | None = None
    icon: str | None = None
    attributes: dict[str, AttributeValue] = field(default_factory=dict)
    dependencies: set[str] = field(default_factory=set)
    variables: dict[str, str] = field(default_factory=dict)  # Variable name -> entity_id mappings

    def __post_init__(self) -> None:
        """Extract dependencies from formula after initialization."""
        if not self.dependencies:
            self.dependencies = self._extract_dependencies()

    def _extract_dependencies(self) -> set[str]:
        """Extract entity dependencies from the formula string and variables."""
        # Use enhanced dependency parser that handles:
        # - Variable references
        # - Direct entity_ids
        # - Dot notation (sensor1.battery_level)
        # - Dynamic queries (regex:, tags:, device_class:, etc.)
        parser = DependencyParser()

        # Extract static dependencies (direct entity references and variables)
        static_deps = parser.extract_static_dependencies(self.formula, self.variables)

        # Note: Dynamic query patterns are extracted but resolved at runtime by evaluator
        # Dynamic dependencies cannot be pre-computed as they depend on HA state
        return static_deps


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
    entity_id: str | None = None  # OPTIONAL: Explicit entity ID

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

    def __init__(self, hass: HomeAssistant, config_path: str | Path | None = None) -> None:
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

            # Perform schema validation first
            schema_result = validate_yaml_config(yaml_data)

            # Log warnings
            for warning in schema_result["warnings"]:
                self._logger.warning("Config warning at %s: %s", warning.path, warning.message)
                if warning.suggested_fix:
                    self._logger.warning("Suggested fix: %s", warning.suggested_fix)

            # Check for schema errors
            if not schema_result["valid"]:
                error_messages = []
                for error in schema_result["errors"]:
                    msg = f"{error.path}: {error.message}"
                    if error.suggested_fix:
                        msg += f" (Suggested fix: {error.suggested_fix})"
                    error_messages.append(msg)

                error_msg = f"Configuration schema validation failed: " f"{'; '.join(error_messages)}"
                self._logger.error(error_msg)
                raise ConfigEntryError(error_msg)

            self._config = self._parse_yaml_config(yaml_data)

            # Validate the loaded configuration (additional semantic validation)
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

        # Parse sensors (v2.0 dict format)
        sensors_data = yaml_data.get("sensors", {})
        for sensor_key, sensor_data in sensors_data.items():
            sensor = self._parse_sensor_config(sensor_key, sensor_data)
            config.sensors.append(sensor)

        return config

    def _parse_sensor_config(self, sensor_key: str, sensor_data: SensorConfigDict) -> SensorConfig:
        """Parse sensor configuration from v2.0 dict format.

        Args:
            sensor_key: Sensor key (serves as unique_id)
            sensor_data: Sensor configuration dictionary

        Returns:
            SensorConfig: Parsed sensor configuration
        """
        sensor = SensorConfig(unique_id=sensor_key)

        # Copy basic properties
        sensor.name = sensor_data.get("name")
        sensor.enabled = sensor_data.get("enabled", True)
        sensor.update_interval = sensor_data.get("update_interval")
        sensor.category = sensor_data.get("category")
        sensor.description = sensor_data.get("description")
        sensor.entity_id = sensor_data.get("entity_id")

        # Parse main formula (required)
        formula = self._parse_single_formula(sensor_key, sensor_data)
        sensor.formulas.append(formula)

        # Parse calculated attributes if present
        attributes_data = sensor_data.get("attributes", {})
        for attr_name, attr_config in attributes_data.items():
            attr_formula = self._parse_attribute_formula(sensor_key, attr_name, attr_config, sensor_data)
            sensor.formulas.append(attr_formula)

        return sensor

    def _parse_single_formula(self, sensor_key: str, sensor_data: SensorConfigDict) -> FormulaConfig:
        """Parse a single formula sensor configuration (v2.0 format).

        Args:
            sensor_key: Sensor key (used as base for formula ID)
            sensor_data: Sensor configuration dictionary

        Returns:
            FormulaConfig: Parsed formula configuration
        """
        formula_str = sensor_data.get("formula")
        if not formula_str:
            raise ValueError(f"Single formula sensor '{sensor_key}' must have 'formula' field")

        # Get explicit variables from config
        variables = sensor_data.get("variables", {}).copy()

        # AUTO-INJECT MISSING ENTITY REFERENCES AS VARIABLES
        # Parse formula to find entity references that aren't explicitly defined as variables
        variables = self._auto_inject_entity_variables(formula_str, variables)

        return FormulaConfig(
            id=sensor_key,  # Use sensor key as formula ID for single-formula sensors
            name=sensor_data.get("name"),
            formula=formula_str,
            unit_of_measurement=sensor_data.get("unit_of_measurement"),
            device_class=sensor_data.get("device_class"),
            state_class=sensor_data.get("state_class"),
            icon=sensor_data.get("icon"),
            attributes=sensor_data.get("extra_attributes", {}),
            variables=variables,
        )

    def _parse_attribute_formula(
        self,
        sensor_key: str,
        attr_name: str,
        attr_config: AttributeConfigDict,
        sensor_data: SensorConfigDict,
    ) -> FormulaConfig:
        """Parse a calculated attribute formula (v2.0 format).

        Args:
            sensor_key: Sensor key (used as base for formula ID)
            attr_name: Attribute name
            attr_config: Attribute configuration dictionary
            sensor_data: Parent sensor configuration dictionary

        Returns:
            FormulaConfig: Parsed attribute formula configuration
        """
        attr_formula = attr_config.get("formula")
        if not attr_formula:
            raise ValueError(f"Attribute '{attr_name}' in sensor '{sensor_key}' must have " f"'formula' field")

        # Merge parent sensor variables with attribute-specific variables
        # Attribute variables take precedence for overrides
        merged_variables = sensor_data.get("variables", {}).copy()
        attr_variables = attr_config.get("variables", {})
        merged_variables.update(attr_variables)

        # Add the parent sensor's main state as a variable reference
        # This allows attributes to reference the main sensor by key
        parent_entity_id = f"sensor.{sensor_key}"
        merged_variables[sensor_key] = parent_entity_id

        # AUTO-INJECT MISSING ENTITY REFERENCES AS VARIABLES
        # Parse formula to find entity references that aren't explicitly defined as variables
        merged_variables = self._auto_inject_entity_variables(attr_formula, merged_variables)

        return FormulaConfig(
            id=f"{sensor_key}_{attr_name}",  # Use sensor key + attribute name as ID
            name=f"{sensor_data.get('name', sensor_key)} - {attr_name}",
            formula=attr_formula,
            unit_of_measurement=attr_config.get("unit_of_measurement"),
            device_class=None,  # Attributes don't typically have device classes
            state_class=None,  # Attributes don't typically have state classes
            icon=attr_config.get("icon"),
            attributes={},
            variables=merged_variables,
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
            self._config.global_settings["variables"] = {}

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

    def validate_yaml_data(self, yaml_data: dict[str, Any]) -> dict[str, Any]:
        """Validate raw YAML configuration data and return detailed results.

        Args:
            yaml_data: Raw configuration dictionary from YAML

        Returns:
            Dictionary with validation results:
            {
                "valid": bool,
                "errors": list of error dictionaries,
                "warnings": list of warning dictionaries,
                "schema_version": str
            }
        """
        from .schema_validator import validate_yaml_config

        schema_result = validate_yaml_config(yaml_data)

        # Convert ValidationError objects to dictionaries for JSON serialization
        errors = [
            {
                "message": error.message,
                "path": error.path,
                "severity": error.severity.value,
                "schema_path": error.schema_path,
                "suggested_fix": error.suggested_fix,
            }
            for error in schema_result["errors"]
        ]

        warnings = [
            {
                "message": warning.message,
                "path": warning.path,
                "severity": warning.severity.value,
                "schema_path": warning.schema_path,
                "suggested_fix": warning.suggested_fix,
            }
            for warning in schema_result["warnings"]
        ]

        return {
            "valid": schema_result["valid"],
            "errors": errors,
            "warnings": warnings,
            "schema_version": yaml_data.get("version", "1.0"),
        }

    def validate_config_file(self, config_path: str | Path) -> dict[str, Any]:
        """Validate a YAML configuration file and return detailed results.

        Args:
            config_path: Path to YAML configuration file

        Returns:
            Dictionary with validation results and file info
        """
        path = Path(config_path)

        if not path.exists():
            return {
                "valid": False,
                "errors": [
                    {
                        "message": f"Configuration file not found: {path}",
                        "path": "file",
                        "severity": "error",
                        "schema_path": "",
                        "suggested_fix": "Check file path and ensure file exists",
                    }
                ],
                "warnings": [],
                "schema_version": "unknown",
                "file_path": str(path),
            }

        try:
            with open(path, encoding="utf-8") as file:
                yaml_data = yaml.safe_load(file)

            if not yaml_data:
                return {
                    "valid": False,
                    "errors": [
                        {
                            "message": "Configuration file is empty",
                            "path": "file",
                            "severity": "error",
                            "schema_path": "",
                            "suggested_fix": "Add configuration content to the file",
                        }
                    ],
                    "warnings": [],
                    "schema_version": "unknown",
                    "file_path": str(path),
                }

            result = self.validate_yaml_data(yaml_data)
            result["file_path"] = str(path)
            return result

        except yaml.YAMLError as exc:
            return {
                "valid": False,
                "errors": [
                    {
                        "message": f"YAML parsing error: {exc}",
                        "path": "file",
                        "severity": "error",
                        "schema_path": "",
                        "suggested_fix": "Check YAML syntax and formatting",
                    }
                ],
                "warnings": [],
                "schema_version": "unknown",
                "file_path": str(path),
            }
        except Exception as exc:
            return {
                "valid": False,
                "errors": [
                    {
                        "message": f"File reading error: {exc}",
                        "path": "file",
                        "severity": "error",
                        "schema_path": "",
                        "suggested_fix": "Check file permissions and encoding",
                    }
                ],
                "warnings": [],
                "schema_version": "unknown",
                "file_path": str(path),
            }

    def _auto_inject_entity_variables(self, formula: str, variables: dict[str, str]) -> dict[str, str]:
        """Auto-inject missing entity references as variables.

        Args:
            formula: Formula string to analyze
            variables: Existing variables dict

        Returns:
            Updated variables dict with auto-injected entity references
        """
        parser = DependencyParser()
        static_deps = parser.extract_static_dependencies(formula, variables)

        # Add missing entity_ids as self-referencing variables
        for entity_id in static_deps:
            if entity_id not in variables:
                variables[entity_id] = entity_id

        return variables
