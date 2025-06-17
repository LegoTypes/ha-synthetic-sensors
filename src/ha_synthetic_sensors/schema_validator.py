"""
Schema Validation - Comprehensive YAML configuration validation using JSON Schema.

This module provides schema-based validation for synthetic sensor YAML configurations,
with detailed error reporting and support for schema versioning.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
from typing import Any, TypedDict

try:
    import jsonschema
    from jsonschema import Draft7Validator, validators

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    jsonschema = None  # type: ignore[assignment]
    Draft7Validator = None  # type: ignore[assignment,misc]
    validators = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Validation error severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ValidationError:
    """Represents a validation error with context."""

    message: str
    path: str
    severity: ValidationSeverity
    schema_path: str = ""
    suggested_fix: str = ""


class ValidationResult(TypedDict):
    """Result of schema validation."""

    valid: bool
    errors: list[ValidationError]
    warnings: list[ValidationError]


class SchemaValidator:
    """Validates synthetic sensor YAML configurations against JSON Schema."""

    def __init__(self) -> None:
        """Initialize the schema validator."""
        self._logger = _LOGGER.getChild(self.__class__.__name__)
        self._schemas: dict[str, dict[str, Any]] = {}
        self._load_schemas()

    def _load_schemas(self) -> None:
        """Load all schema definitions."""
        # Schema for version 1.0 (modernized format)
        self._schemas["1.0"] = self._get_v2_schema()

    def validate_config(self, config_data: dict[str, Any]) -> ValidationResult:
        """Validate configuration data against appropriate schema.

        Args:
            config_data: Raw configuration dictionary from YAML

        Returns:
            ValidationResult with validation status and any errors/warnings
        """
        if not JSONSCHEMA_AVAILABLE:
            self._logger.warning("jsonschema not available, skipping schema validation")
            return ValidationResult(valid=True, errors=[], warnings=[])

        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        # Determine schema version
        version = config_data.get("version", "1.0")
        if version not in self._schemas:
            errors.append(
                ValidationError(
                    message=f"Unsupported schema version: {version}",
                    path="version",
                    severity=ValidationSeverity.ERROR,
                    suggested_fix=(f"Use supported version: {', '.join(self._schemas.keys())}"),
                )
            )
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        schema = self._schemas[version]

        try:
            # Create validator with custom error handling
            if Draft7Validator is None:
                raise ImportError("jsonschema not available")
            validator = Draft7Validator(schema)

            # Validate against schema
            for error in validator.iter_errors(config_data):
                validation_error = self._format_validation_error(error)
                if validation_error.severity == ValidationSeverity.ERROR:
                    errors.append(validation_error)
                else:
                    warnings.append(validation_error)

            # Additional semantic validations
            semantic_errors, semantic_warnings = self._perform_semantic_validation(config_data)
            errors.extend(semantic_errors)
            warnings.extend(semantic_warnings)

        except Exception as exc:
            self._logger.exception("Schema validation failed")
            errors.append(
                ValidationError(
                    message=f"Schema validation error: {exc}",
                    path="",
                    severity=ValidationSeverity.ERROR,
                )
            )

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def _format_validation_error(self, error: Any) -> ValidationError:
        """Format a jsonschema validation error into our ValidationError format."""
        path = ".".join(str(p) for p in error.absolute_path)
        schema_path = ".".join(str(p) for p in error.schema_path)

        # Generate helpful error messages and suggestions
        message = error.message
        suggested_fix = ""

        # Custom error messages for common issues
        if "'unique_id' is a required property" in message:
            suggested_fix = "Add 'unique_id' field to sensor configuration"
        elif "'formula' is a required property" in message:
            suggested_fix = "Add 'formula' field to formula configuration"
        elif "is not of type" in message:
            suggested_fix = f"Check the data type for field at path: {path}"
        elif "Additional properties are not allowed" in message:
            suggested_fix = "Remove unknown fields or check field names for typos"

        return ValidationError(
            message=message,
            path=path or "root",
            severity=ValidationSeverity.ERROR,
            schema_path=schema_path,
            suggested_fix=suggested_fix,
        )

    def _perform_semantic_validation(self, config_data: dict[str, Any]) -> tuple[list[ValidationError], list[ValidationError]]:
        """Perform additional semantic validation beyond JSON schema."""
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        # Validate version compatibility
        version = config_data.get("version", "1.0")
        if version not in ["1.0"]:
            errors.append(
                ValidationError(
                    message=f"Unsupported configuration version: {version}",
                    path="version",
                    severity=ValidationSeverity.ERROR,
                )
            )

        # Validate sensors based on version
        if version == "1.0":
            sensors = config_data.get("sensors", {})
            for sensor_key, sensor_config in sensors.items():
                self._validate_sensor_config(sensor_key, sensor_config, warnings)
                self._validate_state_class_compatibility(sensor_key, sensor_config, warnings)
                self._validate_unit_compatibility(sensor_key, sensor_config, errors)

        return errors, warnings

    def _validate_state_class_compatibility(self, sensor_key: str, sensor_config: dict[str, Any], warnings: list[ValidationError]) -> None:
        """Validate state_class compatibility with device_class using HA's mappings."""
        state_class = sensor_config.get("state_class")
        device_class = sensor_config.get("device_class", "")

        if not state_class or not device_class:
            return

        # Import HA's official device class to state class mappings
        try:
            from homeassistant.components.sensor import (
                SensorDeviceClass,
                SensorStateClass,
            )
            from homeassistant.components.sensor.const import DEVICE_CLASS_STATE_CLASSES

            # Convert string values to enum instances for lookup
            try:
                device_class_enum = SensorDeviceClass(device_class)
                state_class_enum = SensorStateClass(state_class)
            except ValueError:
                # Invalid enum values - will be caught by schema validation
                return

            # Check if this combination is explicitly allowed by HA
            allowed_state_classes = DEVICE_CLASS_STATE_CLASSES.get(device_class_enum, set())

            if allowed_state_classes and state_class_enum not in allowed_state_classes:
                allowed_values = [sc.value for sc in allowed_state_classes]
                warnings.append(
                    ValidationError(
                        message=(f"Sensor '{sensor_key}' uses state_class '{state_class}' with " f"device_class '{device_class}'. Home Assistant recommends " f"state_class values: {', '.join(allowed_values)} for this " "device class."),
                        path=f"sensors.{sensor_key}.state_class",
                        severity=ValidationSeverity.WARNING,
                        suggested_fix=f"Consider using one of: {', '.join(allowed_values)}",
                    )
                )

        except ImportError:
            # Fall back to basic validation if HA constants not available
            self._validate_state_class_fallback(sensor_key, sensor_config, device_class, state_class, warnings)

    def _validate_state_class_fallback(
        self,
        sensor_key: str,
        sensor_config: dict[str, Any],
        device_class: str,
        state_class: str,
        warnings: list[ValidationError],
    ) -> None:
        """Fallback validation when HA constants are not available."""
        # Basic validation for obvious mismatches
        if state_class == "total_increasing":
            problematic_classes = [
                "battery",
                "temperature",
                "humidity",
                "signal_strength",
            ]
            if any(pattern in device_class for pattern in problematic_classes):
                warnings.append(
                    ValidationError(
                        message=(f"Sensor '{sensor_key}' uses state_class 'total_increasing' with " f"device_class '{device_class}' which typically doesn't increase monotonically."),
                        path=f"sensors.{sensor_key}.state_class",
                        severity=ValidationSeverity.WARNING,
                        suggested_fix="Consider using 'measurement' instead",
                    )
                )

    def _validate_sensor_config(self, sensor_key: str, sensor_config: dict[str, Any], warnings: list[ValidationError]) -> None:
        """Validate a single sensor configuration."""
        # Single formula sensor validation
        if "formula" in sensor_config:
            formula_text = sensor_config.get("formula", "")
            variables = sensor_config.get("variables", {})

            validation_result = self._validate_formula_variables(formula_text, variables)
            for error_msg in validation_result:
                warnings.append(
                    ValidationError(
                        message=error_msg,
                        path=f"sensors.{sensor_key}.formula",
                        severity=ValidationSeverity.WARNING,
                        suggested_fix="Define all variables used in the formula",
                    )
                )

        # Validate calculated attributes (if present)
        attributes = sensor_config.get("attributes", {})
        if attributes:
            variables = sensor_config.get("variables", {})
            for attr_name, attr_config in attributes.items():
                attr_formula = attr_config.get("formula", "")

                # Allow 'state' variable in attribute formulas
                extended_variables = variables.copy()
                extended_variables["state"] = "main_sensor_state"

                validation_result = self._validate_formula_variables(attr_formula, extended_variables)
                for error_msg in validation_result:
                    warnings.append(
                        ValidationError(
                            message=error_msg,
                            path=f"sensors.{sensor_key}.attributes.{attr_name}.formula",
                            severity=ValidationSeverity.WARNING,
                            suggested_fix=("Define all variables used in attribute formulas " "(or use 'state' for main sensor value)"),
                        )
                    )

    def _validate_formula_variables(self, formula: str, variables: dict[str, str]) -> list[str]:
        """Validate that formula variables are properly defined.

        Returns:
            List of validation warning messages
        """
        warnings = []

        # Basic check - this could be enhanced with proper parsing
        import re

        # Find potential variable references (simple heuristic)
        potential_vars = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", formula)

        # Filter out known functions and operators
        known_functions = {
            "abs",
            "min",
            "max",
            "round",
            "sum",
            "float",
            "int",
            "sqrt",
            "pow",
            "clamp",
            "map",
            "percent",
            "avg",
            "mean",
            "floor",
            "ceil",
            "if",
            "and",
            "or",
            "not",
        }

        for var in potential_vars:
            if var not in variables and var not in known_functions and not var.isdigit() and var not in ["True", "False"]:
                # Check if it looks like it could be a variable
                warnings.append(f"Potential undefined variable '{var}' in formula")

        return warnings

    def _validate_unit_compatibility(self, sensor_key: str, sensor_config: dict[str, Any], errors: list[ValidationError]) -> None:
        """Validate unit_of_measurement compatibility with device_class (ERROR level)."""
        device_class = sensor_config.get("device_class")
        unit = sensor_config.get("unit_of_measurement")

        if not device_class or not unit:
            return

        # Import HA's official device class to unit mappings
        try:
            from homeassistant.components.sensor import SensorDeviceClass
            from homeassistant.components.sensor.const import DEVICE_CLASS_UNITS

            # Convert string to enum for lookup
            try:
                device_class_enum = SensorDeviceClass(device_class)
            except ValueError:
                # Invalid device_class - will be caught by schema validation
                return

            # Skip validation for device classes with open-ended unit requirements
            SKIP_UNIT_VALIDATION = {
                SensorDeviceClass.MONETARY,  # ISO4217 currency codes (180+ options)
                SensorDeviceClass.DATE,  # ISO8601 date formats (many variations)
                SensorDeviceClass.TIMESTAMP,  # ISO8601 timestamp formats (many variations)
                SensorDeviceClass.ENUM,  # User-defined enumeration values
            }

            if device_class_enum in SKIP_UNIT_VALIDATION:
                return  # Punt - too many valid options to validate reasonably

            # Get allowed units for this device class
            allowed_units_raw = DEVICE_CLASS_UNITS.get(device_class_enum, set())

            # If HA doesn't define units for this device class, punt
            if not allowed_units_raw:
                return

            # Convert enum units to string values for comparison
            allowed_units: set[str | None] = set()
            for unit_spec in allowed_units_raw:
                if unit_spec is None:
                    # None is allowed (unitless)
                    allowed_units.add(None)
                elif isinstance(unit_spec, str):
                    # It's a string constant
                    allowed_units.add(unit_spec)
                else:
                    # It's likely an enum like UnitOfPower.WATT
                    try:
                        allowed_units.add(str(unit_spec.value))
                    except AttributeError:
                        # If it doesn't have .value, add as string
                        allowed_units.add(str(unit_spec))

            # Check if current unit is allowed
            if allowed_units and unit not in allowed_units:
                # Format allowed units for display (handle None separately for sorting)
                str_units = [u for u in allowed_units if u is not None and isinstance(u, str)]
                has_none = None in allowed_units

                unit_list = sorted(str_units)
                if has_none:
                    unit_list.append("None")
                errors.append(
                    ValidationError(
                        message=(f"Sensor '{sensor_key}' uses invalid unit '{unit}' for " f"device_class '{device_class}'. Home Assistant will log this " f"as an error. Allowed units: {', '.join(unit_list)}"),
                        path=f"sensors.{sensor_key}.unit_of_measurement",
                        severity=ValidationSeverity.ERROR,
                        suggested_fix=f"Use one of the allowed units: {', '.join(unit_list)}",
                    )
                )

        except ImportError:
            # Fall back if HA constants not available - no validation
            pass

    def _get_v2_schema(self) -> dict[str, Any]:
        """Get the JSON schema for version 1.0 configurations (modernized format)."""
        # Define common patterns
        id_pattern = "^[a-z][a-z0-9_]*$"
        entity_pattern = "^[a-z_]+\\.[a-z0-9_]+$"
        # Allow entity IDs OR collection patterns (device_class:, area:, tags:, regex:, attribute:)
        variable_value_pattern = "^([a-z_]+\\.[a-z0-9_]+|device_class:[a-z0-9_]+|area:[a-z0-9_]+|tags:[a-z0-9_]+|regex:.+|attribute:.+)$"
        var_pattern = "^[a-zA-Z_][a-zA-Z0-9_]*$"
        icon_pattern = "^mdi:[a-z0-9-]+$"

        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "HA Synthetic Sensors Configuration",
            "description": ("Schema for Home Assistant Synthetic Sensors YAML configuration"),
            "type": "object",
            "properties": self._get_v1_main_properties(id_pattern, entity_pattern, var_pattern, icon_pattern),
            "required": ["sensors"],
            "additionalProperties": False,
            "definitions": self._get_v1_schema_definitions(id_pattern, variable_value_pattern, var_pattern, icon_pattern),
        }

    def _get_main_properties(self, id_pattern: str, entity_pattern: str, var_pattern: str, icon_pattern: str) -> dict[str, Any]:
        """Get the main properties for the schema."""
        return {
            "version": {
                "type": "string",
                "enum": ["1.0"],
                "description": "Configuration schema version",
            },
            "global_settings": {
                "type": "object",
                "description": "Global settings for all sensors",
                "properties": {
                    "domain_prefix": {
                        "type": "string",
                        "description": "Prefix for sensor entity IDs",
                        "pattern": id_pattern,
                    },
                    "enabled": {
                        "type": "boolean",
                        "description": ("Whether synthetic sensors are globally enabled"),
                    },
                    "update_interval": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Default update interval in seconds",
                    },
                },
                "additionalProperties": True,
            },
            "sensors": {
                "type": "array",
                "description": "List of synthetic sensor definitions",
                "items": {"$ref": "#/definitions/sensor"},
                "minItems": 1,
            },
        }

    def _get_schema_definitions(self, id_pattern: str, variable_value_pattern: str, var_pattern: str, icon_pattern: str) -> dict[str, Any]:
        """Get the definitions section for the schema."""
        return {
            "sensor": self._get_sensor_definition(id_pattern),
            "formula": self._get_formula_definition(id_pattern, variable_value_pattern, var_pattern, icon_pattern),
        }

    def _get_sensor_definition(self, id_pattern: str) -> dict[str, Any]:
        """Get the sensor definition for the schema."""
        return {
            "type": "object",
            "description": "Synthetic sensor definition",
            "properties": {
                "unique_id": {
                    "type": "string",
                    "description": "Unique identifier for the sensor",
                    "pattern": id_pattern,
                    "minLength": 1,
                },
                "name": {
                    "type": "string",
                    "description": "Human-readable name for the sensor",
                    "minLength": 1,
                },
                "description": {
                    "type": "string",
                    "description": "Description of what the sensor calculates",
                },
                "enabled": {
                    "type": "boolean",
                    "description": "Whether this sensor is enabled",
                    "default": True,
                },
                "update_interval": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Update interval in seconds for this sensor",
                },
                "category": {
                    "type": "string",
                    "description": "Category for grouping sensors",
                },
                "formulas": {
                    "type": "array",
                    "description": ("List of formula calculations for this sensor"),
                    "items": {"$ref": "#/definitions/formula"},
                    "minItems": 1,
                },
            },
            "required": ["unique_id", "formulas"],
            "additionalProperties": False,
        }

    def _get_formula_definition(self, id_pattern: str, variable_value_pattern: str, var_pattern: str, icon_pattern: str) -> dict[str, Any]:
        """Get the formula definition for the schema."""
        return {
            "type": "object",
            "description": "Formula calculation definition",
            "properties": {
                "id": {
                    "type": "string",
                    "description": ("Unique identifier for the formula within the sensor"),
                    "pattern": id_pattern,
                    "minLength": 1,
                },
                "name": {
                    "type": "string",
                    "description": "Human-readable name for the formula",
                    "minLength": 1,
                },
                "formula": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate",
                    "minLength": 1,
                },
                "variables": {
                    "type": "object",
                    "description": "Variable mappings to Home Assistant entities or collection patterns",
                    "patternProperties": {
                        var_pattern: {
                            "type": "string",
                            "pattern": variable_value_pattern,
                            "description": "Home Assistant entity ID or collection pattern (device_class:, area:, etc.)",
                        }
                    },
                    "additionalProperties": False,
                },
                "unit_of_measurement": {
                    "type": "string",
                    "description": ("Unit of measurement for the calculated value"),
                },
                "device_class": {
                    "type": "string",
                    "description": "Home Assistant device class",
                    "enum": self._get_device_class_enum(),
                },
                "state_class": {
                    "type": "string",
                    "description": "Home Assistant state class",
                    "enum": ["measurement", "total", "total_increasing"],
                },
                "icon": {
                    "type": "string",
                    "description": "Material Design icon identifier",
                    "pattern": icon_pattern,
                },
                "attributes": {
                    "type": "object",
                    "description": "Additional attributes for the entity",
                    "additionalProperties": True,
                },
            },
            "required": ["id", "formula"],
            "additionalProperties": False,
        }

    def _get_device_class_enum(self) -> list[str]:
        """Get the list of valid device classes from Home Assistant constants."""
        from homeassistant.components.sensor import SensorDeviceClass

        return [device_class.value for device_class in SensorDeviceClass.__members__.values()]

    def _get_state_class_enum(self) -> list[str]:
        """Get the list of valid state classes from Home Assistant constants."""
        from homeassistant.components.sensor import SensorStateClass

        return [state_class.value for state_class in SensorStateClass.__members__.values()]

    def _get_v1_main_properties(self, id_pattern: str, entity_pattern: str, var_pattern: str, icon_pattern: str) -> dict[str, Any]:
        """Get the main properties for the v1.0 schema."""
        return {
            "version": {
                "type": "string",
                "enum": ["1.0"],
                "description": "Configuration schema version",
            },
            "global_settings": {
                "type": "object",
                "description": "Global settings for all sensors",
                "properties": {
                    "domain_prefix": {
                        "type": "string",
                        "description": "Prefix for sensor entity IDs",
                        "pattern": id_pattern,
                    },
                    "enabled": {
                        "type": "boolean",
                        "description": ("Whether synthetic sensors are globally enabled"),
                    },
                    "update_interval": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Default update interval in seconds",
                    },
                },
                "additionalProperties": True,
            },
            "global": {
                "type": "object",
                "description": ("Global settings for all sensors (alias for global_settings)"),
                "properties": {
                    "domain_prefix": {
                        "type": "string",
                        "description": "Prefix for sensor entity IDs",
                        "pattern": id_pattern,
                    },
                    "enabled": {
                        "type": "boolean",
                        "description": ("Whether synthetic sensors are globally enabled"),
                    },
                    "update_interval": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Default update interval in seconds",
                    },
                    "restore_state": {
                        "type": "boolean",
                        "description": "Whether to restore state on startup",
                    },
                },
                "additionalProperties": True,
            },
            "sensors": {
                "type": "object",
                "description": "Dictionary of synthetic sensor definitions",
                "patternProperties": {id_pattern: {"$ref": "#/definitions/v1_sensor"}},
                "additionalProperties": False,
                "minProperties": 1,
            },
        }

    def _get_v1_schema_definitions(self, id_pattern: str, entity_pattern: str, var_pattern: str, icon_pattern: str) -> dict[str, Any]:
        """Get the definitions section for the v2.0 schema."""
        return {
            "v1_sensor": self._get_v1_sensor_definition(id_pattern, entity_pattern, var_pattern, icon_pattern),
            "v1_attribute": self._get_v1_attribute_definition(var_pattern, icon_pattern),
        }

    def _get_v1_sensor_definition(self, id_pattern: str, entity_pattern: str, var_pattern: str, icon_pattern: str) -> dict[str, Any]:
        """Get the sensor definition for the v2.0 schema."""
        return {
            "type": "object",
            "description": "Synthetic sensor definition (v2.0 syntax)",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable name for the sensor",
                    "minLength": 1,
                },
                "description": {
                    "type": "string",
                    "description": "Description of what the sensor calculates",
                },
                "enabled": {
                    "type": "boolean",
                    "description": "Whether this sensor is enabled",
                    "default": True,
                },
                "update_interval": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Update interval in seconds for this sensor",
                },
                "category": {
                    "type": "string",
                    "description": "Category for grouping sensors",
                },
                "entity_id": {
                    "type": "string",
                    "description": "Explicit entity ID for the sensor (optional)",
                    "pattern": entity_pattern,
                },
                # Main formula for sensor calculation
                "formula": {
                    "type": "string",
                    "description": "Mathematical expression for sensor calculation",
                    "minLength": 1,
                },
                "attributes": {
                    "type": "object",
                    "description": "Calculated attributes for rich sensor data",
                    "patternProperties": {var_pattern: {"$ref": "#/definitions/v1_attribute"}},
                    "additionalProperties": False,
                },
                # Common properties for both syntax patterns
                "variables": {
                    "type": "object",
                    "description": "Variable mappings to Home Assistant entities",
                    "patternProperties": {
                        var_pattern: {
                            "type": "string",
                            "pattern": entity_pattern,
                            "description": "Home Assistant entity ID",
                        }
                    },
                    "additionalProperties": False,
                },
                "unit_of_measurement": {
                    "type": "string",
                    "description": "Unit of measurement for the calculated value",
                },
                "device_class": {
                    "type": "string",
                    "description": "Home Assistant device class",
                    "enum": self._get_device_class_enum(),
                },
                "state_class": {
                    "type": "string",
                    "description": "Home Assistant state class",
                    "enum": self._get_state_class_enum(),
                },
                "icon": {
                    "type": "string",
                    "description": "Material Design icon identifier",
                    "pattern": icon_pattern,
                },
                "extra_attributes": {
                    "type": "object",
                    "description": "Additional static attributes for the entity",
                    "additionalProperties": True,
                },
            },
            "required": ["formula"],
            "additionalProperties": False,
        }

    def _get_v1_attribute_definition(self, var_pattern: str, icon_pattern: str) -> dict[str, Any]:
        """Get the calculated attribute definition for the v2.0 schema."""
        return {
            "type": "object",
            "description": "Calculated attribute definition",
            "properties": {
                "formula": {
                    "type": "string",
                    "description": ("Mathematical expression to evaluate for this attribute"),
                    "minLength": 1,
                },
                "unit_of_measurement": {
                    "type": "string",
                    "description": "Unit of measurement for this attribute",
                },
                "device_class": {
                    "type": "string",
                    "description": "Home Assistant device class",
                    "enum": self._get_device_class_enum(),
                },
                "state_class": {
                    "type": "string",
                    "description": "Home Assistant state class",
                    "enum": self._get_state_class_enum(),
                },
                "icon": {
                    "type": "string",
                    "description": "Material Design icon identifier",
                    "pattern": icon_pattern,
                },
            },
            "required": ["formula"],
            "additionalProperties": False,
        }


class SchemaValidationError(Exception):
    """Exception raised when schema validation fails."""

    def __init__(self, message: str, errors: list[ValidationError]) -> None:
        """Initialize with validation errors."""
        super().__init__(message)
        self.errors = errors


def validate_yaml_config(config_data: dict[str, Any]) -> ValidationResult:
    """Convenience function to validate configuration data.

    Args:
        config_data: Raw configuration dictionary from YAML

    Returns:
        ValidationResult with validation status and any errors/warnings
    """
    validator = SchemaValidator()
    return validator.validate_config(config_data)


def get_schema_for_version(version: str) -> dict[str, Any] | None:
    """Get the JSON schema for a specific version.

    Args:
        version: Schema version string

    Returns:
        Schema dictionary or None if version not found
    """
    validator = SchemaValidator()
    return validator._schemas.get(version)
