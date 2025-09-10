"""
Configuration Manager - Main orchestration and public API.

This module provides the ConfigManager class as the main entry point for
configuration management, delegating to specialized components.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

import aiofiles
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
import yaml

from .alternate_state_circular_validator import validate_alternate_state_handler_circular_deps
from .config_helpers.yaml_helpers import check_duplicate_sensor_keys, extract_sensor_keys_from_yaml, trim_yaml_keys
from .config_models import AlternateStateHandler, ComputedVariable, Config, FormulaConfig, SensorConfig
from .config_types import AttributeConfig, AttributeValue, ConfigDict, GlobalSettingsDict, SensorConfigDict
from .config_yaml_converter import ConfigYamlConverter
from .constants_alternate import STATE_NONE_YAML
from .cross_sensor_reference_detector import CrossSensorReferenceDetector
from .schema_validator import validate_yaml_config
from .utils_config import validate_computed_variable_references
from .validation_utils import load_yaml_file
from .yaml_config_parser import YAMLConfigParser

_LOGGER = logging.getLogger(__name__)


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
        self._cross_sensor_detector = CrossSensorReferenceDetector()
        self._yaml_parser = YAMLConfigParser()

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

        if not path:
            error_msg = "No configuration path provided"
            self._logger.error(error_msg)
            raise ConfigEntryError(error_msg)

        if not path.exists():
            error_msg = f"Configuration file not found: {path}"
            self._logger.error(error_msg)
            raise ConfigEntryError(error_msg)

        try:
            with open(path, encoding="utf-8") as file:
                yaml_data_raw = yaml.safe_load(file)
                yaml_data = trim_yaml_keys(yaml_data_raw)

            # Check for empty YAML data early
            if not yaml_data:
                error_msg = "Empty configuration file"
                self._logger.error(error_msg)
                raise ConfigEntryError(error_msg)

            # Perform schema validation using shared method
            self._validate_yaml_data_with_schema(yaml_data)

            self._config = self._parse_yaml_config(yaml_data)

            # Validate the loaded configuration (additional semantic validation)
            errors = self._config.validate()
            if errors:
                error_msg = f"Configuration validation failed: {', '.join(errors)}"
                self._logger.error(error_msg)
                raise ConfigEntryError(error_msg)

            self._logger.debug(
                "Loaded configuration with %d sensors from %s",
                len(self._config.sensors),
                path,
            )

            return self._config

        except Exception as exc:
            error_msg = f"Failed to load configuration from {path}: {exc}"
            self._logger.error(error_msg)
            raise ConfigEntryError(error_msg) from exc

    async def async_load_config(self, config_path: str | Path | None = None) -> Config:
        """Load configuration from YAML file (async version).

        Args:
            config_path: Optional path to override the default config path

        Returns:
            Config: Loaded configuration object

        Raises:
            ConfigEntryError: If configuration loading or validation fails
        """
        path = Path(config_path) if config_path else self._config_path

        if not path:
            error_msg = "No configuration path provided"
            self._logger.error(error_msg)
            raise ConfigEntryError(error_msg)

        if not path.exists():
            error_msg = f"Configuration file not found: {path}"
            self._logger.error(error_msg)
            raise ConfigEntryError(error_msg)

        try:
            async with aiofiles.open(path, encoding="utf-8") as file:
                content = await file.read()
                yaml_data_raw = yaml.safe_load(content)
                yaml_data_trimmed = trim_yaml_keys(yaml_data_raw)
                if not isinstance(yaml_data_trimmed, dict):
                    yaml_data: dict[str, Any] = {}
                else:
                    yaml_data = cast(dict[str, Any], yaml_data_trimmed)

            # Check for empty YAML data early
            if not yaml_data:
                error_msg = "Empty configuration file"
                self._logger.error(error_msg)
                raise ConfigEntryError(error_msg)

            # Perform schema validation using shared method
            self._validate_yaml_data_with_schema(yaml_data)

            self._config = self._parse_yaml_config(cast(ConfigDict, yaml_data))

            # Validate the loaded configuration (additional semantic validation)
            errors = self._config.validate()
            if errors:
                error_msg = f"Configuration validation failed: {', '.join(errors)}"
                self._logger.error(error_msg)
                raise ConfigEntryError(error_msg)

            self._logger.debug(
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

        # Phase 1: Detect cross-sensor references before parsing sensors
        cross_sensor_references = self._cross_sensor_detector.scan_yaml_references(dict(yaml_data))
        config.cross_sensor_references = cross_sensor_references

        # Log detected references for debugging
        if cross_sensor_references:
            self._logger.debug("Detected cross-sensor references: %s", {k: list(v) for k, v in cross_sensor_references.items()})

            # Check for circular dependencies at parse time
            circular_refs = self._detect_circular_dependencies(cross_sensor_references)
            if circular_refs:
                self._logger.warning("Circular cross-sensor dependency detected among: %s", sorted(set(circular_refs)))

        # Parse sensors (v1.0 dict format)
        sensors_data = yaml_data.get("sensors", {})
        for sensor_key, sensor_data in sensors_data.items():
            sensor = self._parse_sensor_config(sensor_key, sensor_data, config.global_settings)
            config.sensors.append(sensor)

        return config

    def _detect_circular_dependencies(self, cross_sensor_references: dict[str, set[str]]) -> list[str]:
        """Detect circular dependencies in cross-sensor references.

        Args:
            cross_sensor_references: Dict mapping sensor names to their dependencies

        Returns:
            List of sensor names involved in circular dependencies
        """
        visited = set()
        rec_stack = set()
        circular_refs = []

        def has_cycle(sensor: str) -> bool:
            """Check if there's a cycle starting from the given sensor."""
            if sensor in rec_stack:
                return True
            if sensor in visited:
                return False

            visited.add(sensor)
            rec_stack.add(sensor)

            for dep in cross_sensor_references.get(sensor, set()):
                if has_cycle(dep):
                    if dep not in circular_refs:
                        circular_refs.append(dep)
                    return True

            rec_stack.remove(sensor)
            return False

        # Check for cycles starting from each sensor
        for sensor in cross_sensor_references:
            if sensor not in visited and has_cycle(sensor) and sensor not in circular_refs:
                circular_refs.append(sensor)

        return circular_refs

    def _validate_raw_yaml_structure(self, yaml_content: str) -> None:
        """Validate raw YAML structure for basic flaws in phase 0.

        Args:
            yaml_content: Raw YAML content string

        Raises:
            ConfigEntryError: If basic structural flaws are detected
        """
        sensor_keys = extract_sensor_keys_from_yaml(yaml_content)
        duplicates = check_duplicate_sensor_keys(sensor_keys)
        if duplicates:
            duplicate_list = ", ".join(duplicates)
            raise ConfigEntryError(f"Duplicate sensor keys found in YAML: {duplicate_list}")

        # Note: Duplicate attributes and variables within sensors will be checked
        # during the parsed config validation phase, not in raw YAML validation

    def _parse_sensor_config(
        self, sensor_key: str, sensor_data: SensorConfigDict, global_settings: GlobalSettingsDict | None = None
    ) -> SensorConfig:
        """Parse sensor configuration from v1.0 dict format.

        Args:
            sensor_key: Sensor key (serves as unique_id)
            sensor_data: Sensor configuration dictionary
            global_settings: Global settings to apply as defaults

        Returns:
            SensorConfig: Parsed sensor configuration
        """
        global_settings = global_settings or {}
        sensor = SensorConfig(unique_id=sensor_key)

        # Copy basic properties
        sensor.name = sensor_data.get("name")
        sensor.enabled = sensor_data.get("enabled", True)
        sensor.update_interval = sensor_data.get("update_interval")
        sensor.category = sensor_data.get("category")
        sensor.description = sensor_data.get("description")
        sensor.entity_id = sensor_data.get("entity_id")

        # Copy device association fields with global fallbacks
        # Sensor-specific values take precedence over global settings
        sensor.device_identifier = sensor_data.get("device_identifier") or global_settings.get("device_identifier")
        sensor.device_name = sensor_data.get("device_name")
        sensor.device_manufacturer = sensor_data.get("device_manufacturer")
        sensor.device_model = sensor_data.get("device_model")
        sensor.device_sw_version = sensor_data.get("device_sw_version")
        sensor.device_hw_version = sensor_data.get("device_hw_version")
        sensor.suggested_area = sensor_data.get("suggested_area")

        # Copy sensor-level metadata
        sensor.metadata = sensor_data.get("metadata", {})

        # Parse main formula (required)
        formula = self._parse_single_formula(sensor_key, sensor_data, global_settings)
        sensor.formulas.append(formula)

        # Parse calculated attributes if present - only create formula entries for attributes with explicit formula structure
        attributes_data = sensor_data.get("attributes", {})
        for attr_name, attr_config in attributes_data.items():
            # Only create separate formula entries for attributes that have an explicit formula structure
            if isinstance(attr_config, dict) and "formula" in attr_config:
                attr_formula = self._parse_attribute_formula(sensor_key, attr_name, attr_config, sensor_data, global_settings)
                sensor.formulas.append(attr_formula)
            # Literal values (str, int, float) are already handled in _parse_single_formula
            # and added to the main formula's attributes dict

        return sensor

    def _parse_alternate_state_handler(self, handler_data: dict[str, Any]) -> AlternateStateHandler | None:
        """Parse exception handler from YAML data.

        Args:
            handler_data: Dictionary containing either:
                - Direct UNAVAILABLE, UNKNOWN, NONE, and/or FALLBACK keys (old format)
                - alternate_states key containing the handlers (new format)

        Returns:
            AlternateStateHandler object or None if no handlers found
        """
        # Check for new alternate_states structure first
        if "alternate_states" in handler_data:
            alternate_states = handler_data["alternate_states"]
            unavailable_handler = self._convert_yaml_to_python_value(alternate_states.get("UNAVAILABLE"))
            unknown_handler = self._convert_yaml_to_python_value(alternate_states.get("UNKNOWN"))
            none_handler = self._convert_yaml_to_python_value(alternate_states.get("NONE"))
            fallback_handler = self._convert_yaml_to_python_value(alternate_states.get("FALLBACK"))
        else:
            # Fall back to old direct structure
            unavailable_handler = self._convert_yaml_to_python_value(handler_data.get("UNAVAILABLE"))
            unknown_handler = self._convert_yaml_to_python_value(handler_data.get("UNKNOWN"))
            none_handler = self._convert_yaml_to_python_value(handler_data.get("NONE"))
            fallback_handler = self._convert_yaml_to_python_value(handler_data.get("FALLBACK"))

        if unavailable_handler is None and unknown_handler is None and none_handler is None and fallback_handler is None:
            return None

        handler = AlternateStateHandler(
            unavailable=unavailable_handler, unknown=unknown_handler, none=none_handler, fallback=fallback_handler
        )

        # Validate for circular dependencies
        validate_alternate_state_handler_circular_deps(handler)

        return handler

    def _convert_yaml_to_python_value(self, value: Any) -> Any:
        """Convert YAML values to Python representation.

        Specifically handles STATE_NONE → Python None.
        """
        if isinstance(value, str) and value == STATE_NONE_YAML:
            return None
        return value

    def _parse_variables(self, variables_data: dict[str, Any]) -> dict[str, str | int | float | ComputedVariable]:
        """Parse variables dictionary, handling computed variables with formula key and exception handlers.

        Args:
            variables_data: Raw variables data from YAML

        Returns:
            Dictionary with parsed variables including ComputedVariable objects
        """

        parsed_variables: dict[str, str | int | float | ComputedVariable] = {}

        for var_name, var_value in variables_data.items():
            if isinstance(var_value, dict):
                if "formula" in var_value:
                    # This is a computed variable with formula key
                    formula_expr = var_value["formula"]
                    if not formula_expr or not str(formula_expr).strip():
                        raise ValueError(f"Variable '{var_name}' has empty formula expression")

                    # Parse exception handler if present (supports both old and new structure)
                    alternate_state_handler = self._parse_alternate_state_handler(var_value)

                    # Parse allow_unresolved_states if present
                    allow_unresolved_states = var_value.get("allow_unresolved_states", False)

                    # Create ComputedVariable object
                    # Note: Dependencies will be resolved during context building phase
                    parsed_variables[var_name] = ComputedVariable(
                        formula=str(formula_expr).strip(),
                        dependencies=set(),  # Will be populated during dependency resolution
                        alternate_state_handler=alternate_state_handler,
                        allow_unresolved_states=allow_unresolved_states,
                    )
                elif "UNAVAILABLE" in var_value or "UNKNOWN" in var_value or "NONE" in var_value or "FALLBACK" in var_value:
                    # This appears to be a simple variable with exception handlers
                    raise ValueError(
                        f"Variable '{var_name}' has exception handlers but no base value. "
                        f"Simple variables with exception handlers are not yet supported. "
                        f"Consider using a computed variable with formula."
                    )
                elif "alternate_states" in var_value:
                    # This appears to be a simple variable with alternate_states structure
                    raise ValueError(
                        f"Variable '{var_name}' has alternate_states but no base value. "
                        f"Simple variables with alternate_states are not yet supported. "
                        f"Consider using a computed variable with formula."
                    )
                else:
                    # Complex dict but not a computed variable - might be attribute config
                    # Cast to str since it's not a computed variable but a complex value
                    parsed_variables[var_name] = str(var_value)
            else:
                # Simple variable (entity_id, literal, etc.)
                parsed_variables[var_name] = var_value

        return parsed_variables

    def _parse_single_formula(
        self, sensor_key: str, sensor_data: SensorConfigDict, global_settings: GlobalSettingsDict | None = None
    ) -> FormulaConfig:
        """Parse a single formula sensor configuration (v1.0 format).

        Args:
            sensor_key: Sensor key (used as base for formula ID)
            sensor_data: Sensor configuration dictionary
            global_settings: Global settings containing variables

        Returns:
            FormulaConfig: Parsed formula configuration
        """
        formula_str = sensor_data.get("formula")
        if not formula_str:
            raise ValueError(f"Single formula sensor '{sensor_key}' must have 'formula' field")

        # Parse variables (including computed variables with "formula:" prefix)
        variables = self._parse_variables(sensor_data.get("variables", {}))

        # Validate computed variable references
        global_variables = (global_settings or {}).get("variables", {})
        validation_errors = validate_computed_variable_references(variables, sensor_key, global_variables)
        if validation_errors:
            error_msg = f"Computed variable validation failed: {'; '.join(validation_errors)}"
            self._logger.error(error_msg)
            raise ConfigEntryError(error_msg)

        # Variables are now optional aliases - no auto-detection needed
        # Entity IDs in formulas will be resolved directly during evaluation

        # Convert AttributeConfig to AttributeValue for FormulaConfig
        attributes: dict[str, AttributeValue] = {}
        for attr_name, attr_config in sensor_data.get("attributes", {}).items():
            if isinstance(attr_config, dict) and "formula" in attr_config:
                # Preserve the entire AttributeConfigDict structure instead of flattening
                attributes[attr_name] = cast(AttributeValue, attr_config)
            elif isinstance(attr_config, str | int | float):
                # Handle literal values (str, int, float) - these are compatible with AttributeValue
                attributes[attr_name] = attr_config
            else:
                # Handle other types by converting to string
                attributes[attr_name] = str(attr_config)

        # Parse formula-level alternate state handler if present
        formula_alternate_state_handler = self._parse_alternate_state_handler(cast(dict[str, Any], sensor_data))

        return FormulaConfig(
            id=sensor_key,  # Use sensor key as formula ID for single-formula sensors
            name=sensor_data.get("name"),
            formula=formula_str,
            attributes=attributes,
            variables=variables,
            metadata=sensor_data.get("metadata", {}),
            alternate_state_handler=formula_alternate_state_handler,
            allow_unresolved_states=bool(sensor_data.get("allow_unresolved_states", False)),
        )

    def _parse_attribute_formula(
        self,
        sensor_key: str,
        attr_name: str,
        attr_config: AttributeConfig,
        sensor_data: SensorConfigDict,
        global_settings: GlobalSettingsDict | None = None,
    ) -> FormulaConfig:
        """Parse a calculated attribute formula (v1.0 format).

        Args:
            sensor_key: Sensor key (used as base for formula ID)
            attr_name: Attribute name
            attr_config: Attribute configuration dictionary or literal value
            sensor_data: Parent sensor configuration dictionary
            global_settings: Global settings to inherit variables from

        Returns:
            FormulaConfig: Parsed attribute formula configuration
        """
        # Handle literal values (new feature)
        if isinstance(attr_config, int | float | str):
            # Create a formula that just returns the literal value
            return FormulaConfig(
                id=f"{sensor_key}_{attr_name}",
                name=f"{sensor_data.get('name', sensor_key)} - {attr_name}",
                formula=str(attr_config),  # Convert to string formula
                attributes={},
                variables={},
                metadata={},
                allow_unresolved_states=False,  # Literal values don't need this
            )

        # Handle formula objects (existing behavior)
        attr_formula = attr_config.get("formula")
        if not attr_formula:
            raise ValueError(f"Attribute '{attr_name}' in sensor '{sensor_key}' must have 'formula' field")

        # Parse attribute-specific variables only
        # Parent sensor variables are inherited at runtime, not stored in YAML
        attr_variables = attr_config.get("variables", {})
        formula_variables = self._parse_variables(attr_variables if isinstance(attr_variables, dict) else {})

        # Validate computed variable references in attribute variables
        global_variables = (global_settings or {}).get("variables", {})
        validation_errors = validate_computed_variable_references(
            formula_variables, f"{sensor_key}.{attr_name}", global_variables
        )
        if validation_errors:
            error_msg = f"Computed variable validation failed: {'; '.join(validation_errors)}"
            self._logger.error(error_msg)
            raise ConfigEntryError(error_msg)

        # Variables are now optional aliases - no auto-detection needed
        # Entity IDs in attribute formulas will be resolved directly during evaluation
        # Global and parent variables will be inherited during evaluation phase

        # Parse attribute-level alternate state handler if present
        attr_alternate_state_handler = self._parse_alternate_state_handler(cast(dict[str, Any], attr_config))

        return FormulaConfig(
            id=f"{sensor_key}_{attr_name}",  # Use sensor key + attribute name as ID
            name=f"{sensor_data.get('name', sensor_key)} - {attr_name}",
            formula=attr_formula,
            attributes={},
            variables=formula_variables,
            metadata=attr_config.get("metadata", {}),
            alternate_state_handler=attr_alternate_state_handler,
            allow_unresolved_states=bool(attr_config.get("allow_unresolved_states", False)),
        )

    async def async_reload_config(self) -> Config:
        """Reload configuration from the original path (async version).

        Returns:
            Config: Reloaded configuration

        Raises:
            ConfigEntryError: If no path is set or reload fails
        """
        if not self._config_path:
            raise ConfigEntryError("No configuration path set for reload")

        return await self.async_load_config(self._config_path)

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

        missing_deps: dict[str, list[str]] = {}

        for sensor in self._config.sensors:
            if not sensor.enabled:
                continue

            missing: list[str] = []
            for dep in sensor.get_all_dependencies():
                if not self._hass.states.get(dep):
                    missing.append(dep)

            if missing:
                missing_deps[sensor.unique_id] = missing

        return missing_deps

    def load_from_file(self, file_path: str | Path) -> Config:
        """Load configuration from a specific file path.

        Args:
            file_path: Path to the configuration file

        Returns:
            Config: Loaded configuration object
        """
        return self.load_config(file_path)

    async def async_load_from_file(self, file_path: str | Path) -> Config:
        """Load configuration from a specific file path (async version).

        Args:
            file_path: Path to the configuration file

        Returns:
            Config: Loaded configuration object
        """
        return await self.async_load_config(file_path)

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
            # Phase 0: Validate raw YAML structure for basic flaws BEFORE parsing
            self._validate_raw_yaml_structure(yaml_content)

            yaml_data = self._yaml_parser.parse_yaml_content(yaml_content)

            if not yaml_data:
                error_msg = "Empty YAML content"
                self._logger.error(error_msg)
                raise ConfigEntryError(error_msg)

            # Validate YAML data using the same validation logic as file-based loading
            self._validate_yaml_data_with_schema(yaml_data)

            self._config = self._parse_yaml_config(yaml_data)

            # Validate the loaded configuration
            errors = self._config.validate()
            if errors:
                error_msg = f"Configuration validation failed: {', '.join(errors)}"
                self._logger.error(error_msg)
                raise ConfigEntryError(error_msg)

            self._logger.debug(
                "Loaded configuration with %d sensors from YAML content",
                len(self._config.sensors),
            )

            return self._config

        except Exception as exc:
            error_msg = f"Failed to parse YAML content: {exc}"
            self._logger.error(error_msg)
            raise ConfigEntryError(error_msg) from exc

    def load_from_dict(self, config_dict: ConfigDict) -> Config:
        """Load configuration from dictionary (e.g., from JSON storage).

        Args:
            config_dict: Configuration as dictionary

        Returns:
            Config: Parsed configuration object

        Raises:
            ConfigEntryError: If parsing or validation fails
        """
        try:
            if not config_dict:
                self._config = Config()
                return self._config

            self._config = self._parse_yaml_config(config_dict)

            # Validate the loaded configuration
            errors = self._config.validate()
            if errors:
                error_msg = f"Configuration validation failed: {', '.join(errors)}"
                self._logger.error(error_msg)
                raise ConfigEntryError(error_msg)

            self._logger.debug(
                "Loaded configuration with %d sensors from dictionary",
                len(self._config.sensors),
            )

            return self._config

        except Exception as exc:
            error_msg = f"Failed to parse dictionary content: {exc}"
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

    async def async_save_config(self, file_path: str | Path | None = None) -> None:
        """Save current configuration to YAML file (async version).

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

            # Convert to YAML string first
            yaml_content = yaml.dump(yaml_data, default_flow_style=False, allow_unicode=True)

            async with aiofiles.open(path, "w", encoding="utf-8") as file:
                await file.write(yaml_content)

            self._logger.debug("Saved configuration to %s", path)

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
        converter = ConfigYamlConverter()
        return converter.config_to_yaml(config)

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
            self._logger.debug("Added variable: %s = %s", name, entity_id)
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
            self._logger.debug("Removed variable: %s", name)
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
        """Get all sensor configurations.

        Returns:
            list: List of all sensor configurations
        """
        return self.get_sensor_configs(enabled_only=False)

    def validate_configuration(self) -> dict[str, list[str]]:
        """Validate the current configuration and return structured results.

        Returns:
            dict: Dictionary with 'errors' key containing list of error messages
        """
        errors = self.validate_config()
        return {"errors": errors}

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
                "schema_version": str
            }
        """

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

        return {
            "valid": schema_result["valid"],
            "errors": errors,
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
        yaml_data, error_response = load_yaml_file(path)

        if error_response:
            return error_response

        if yaml_data is None:
            raise ValueError("yaml_data should not be None when error_response is None")

        result = self.validate_yaml_data(yaml_data)
        result["file_path"] = str(path)
        return result

    def _validate_yaml_data_with_schema(self, yaml_data: dict[str, Any] | ConfigDict) -> None:
        """Shared validation logic for both file-based and string-based loading.

        Args:
            yaml_data: YAML data to validate

        Raises:
            ConfigEntryError: If schema validation fails
        """
        schema_result = validate_yaml_config(cast(dict[str, Any], yaml_data))

        # Check for schema errors
        if not schema_result["valid"]:
            error_messages: list[str] = []

            # Add errors
            for error in schema_result["errors"]:
                msg = f"{error.path}: {error.message}"
                if error.suggested_fix:
                    msg += f" (Suggested fix: {error.suggested_fix})"
                error_messages.append(msg)

            error_msg = f"Configuration schema validation failed: {'; '.join(error_messages)}"
            self._logger.error(error_msg)
            raise ConfigEntryError(error_msg)
