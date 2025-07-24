"""
Schema Validation - Comprehensive YAML configuration validation using JSON Schema.

This module provides schema-based validation for synthetic sensor YAML configurations,
with detailed error reporting and support for schema versioning.
"""

# pylint: disable=too-many-lines

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
import re
from typing import Any, TypedDict

from .ha_constants import HAConstantLoader

try:
    from jsonschema import Draft7Validator

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    Draft7Validator = None  # type: ignore[assignment,misc]

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
        self.schemas: dict[str, dict[str, Any]] = {}
        self._load_schemas()

    def _load_schemas(self) -> None:
        """Load all schema definitions."""
        # Schema for version 1.0 (modernized format)
        self.schemas["1.0"] = self._get_v1_schema()

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
        if version not in self.schemas:
            errors.append(
                ValidationError(
                    message=f"Unsupported schema version: {version}",
                    path="version",
                    severity=ValidationSeverity.ERROR,
                    suggested_fix=(f"Use supported version: {', '.join(self.schemas.keys())}"),
                )
            )
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        schema = self.schemas[version]

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
                # Validate device class using HA's built-in validation
                metadata = sensor_config.get("metadata", {})
                device_class = metadata.get("device_class")
                if device_class:
                    self._validate_device_class(sensor_key, device_class, warnings)

                self._validate_sensor_config(sensor_key, sensor_config, warnings)
                self._validate_state_class_compatibility(sensor_key, sensor_config, warnings)
                self._validate_unit_compatibility(sensor_key, sensor_config, errors)

        return errors, warnings

    def _validate_state_class_compatibility(
        self,
        sensor_key: str,
        sensor_config: dict[str, Any],
        warnings: list[ValidationError],
    ) -> None:
        """Validate state_class compatibility with device_class using HA's mappings."""
        metadata = sensor_config.get("metadata", {})
        state_class = metadata.get("state_class")
        device_class = metadata.get("device_class", "")

        if not state_class or not device_class:
            return

        # Import HA's official device class to state class mappings
        try:
            # Convert string values to enum instances for lookup
            try:
                sensor_device_class = HAConstantLoader.get_constant("SensorDeviceClass")
                sensor_state_class = HAConstantLoader.get_constant("SensorStateClass")
                device_class_enum = sensor_device_class(device_class)
                state_class_enum = sensor_state_class(state_class)
            except ValueError:
                # Check if the state class is valid using component constants
                try:
                    sensor_state_classes = HAConstantLoader.get_constant("STATE_CLASSES", "homeassistant.components.sensor")
                    if state_class not in sensor_state_classes:
                        warnings.append(
                            ValidationError(
                                message=f"Invalid state_class '{state_class}'. Valid options: {sensor_state_classes}",
                                path=f"sensors.{sensor_key}.state_class",
                                severity=ValidationSeverity.WARNING,
                            )
                        )
                except ValueError:
                    pass  # Skip validation if we can't get the constants
                return

            # Check if this combination is explicitly allowed by HA
            try:
                device_class_state_classes = HAConstantLoader.get_constant("DEVICE_CLASS_STATE_CLASSES")
                allowed_state_classes = device_class_state_classes.get(device_class_enum, set())

                if allowed_state_classes and state_class_enum not in allowed_state_classes:
                    warnings.append(
                        ValidationError(
                            message=(
                                f"Invalid state_class '{state_class}' for device_class '{device_class}'. "
                                f"Valid options: {[sc.value for sc in allowed_state_classes]}"
                            ),
                            path=f"sensors.{sensor_key}.state_class",
                            severity=ValidationSeverity.WARNING,
                        )
                    )
            except ValueError:
                pass  # Skip validation if we can't get the constants

        except ImportError:
            # HA not available - skip validation
            pass

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
                        message=(
                            f"Sensor '{sensor_key}' uses state_class 'total_increasing' with "
                            f"device_class '{device_class}' which typically doesn't increase monotonically."
                        ),
                        path=f"sensors.{sensor_key}.state_class",
                        severity=ValidationSeverity.WARNING,
                        suggested_fix="Consider using 'measurement' instead",
                    )
                )

    def _validate_sensor_config(
        self,
        sensor_key: str,
        sensor_config: dict[str, Any],
        warnings: list[ValidationError],
    ) -> None:
        """Validate a single sensor configuration."""
        # Single formula sensor validation
        if "formula" in sensor_config:
            formula_text = sensor_config.get("formula", "")
            variables = sensor_config.get("variables", {})

            # Skip validation if formula_text is not a string (schema validation will catch this)
            if isinstance(formula_text, str):
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
                # Skip validation if attr_config is not a dict (schema validation will catch this)
                if not isinstance(attr_config, dict):
                    continue
                attr_formula = attr_config.get("formula", "")

                # Allow 'state' variable in attribute formulas
                extended_variables = variables.copy()
                extended_variables["state"] = "main_sensor_state"

                # Skip validation if attr_formula is not a string (schema validation will catch this)
                if isinstance(attr_formula, str):
                    validation_result = self._validate_formula_variables(attr_formula, extended_variables)
                    for error_msg in validation_result:
                        warnings.append(
                            ValidationError(
                                message=error_msg,
                                path=f"sensors.{sensor_key}.attributes.{attr_name}.formula",
                                severity=ValidationSeverity.WARNING,
                                suggested_fix=(
                                    "Define all variables used in attribute formulas (or use 'state' for main sensor value)"
                                ),
                            )
                        )

    def _validate_formula_variables(self, formula: str, variables: dict[str, str]) -> list[str]:
        """Validate that formula variables are properly defined.

        Returns:
            List of validation warning messages
        """
        warnings = []

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

    def _validate_device_class(
        self,
        sensor_key: str,
        device_class: str,
        warnings: list[ValidationError],
    ) -> None:
        """Validate device class using Home Assistant's built-in validation.

        Args:
            sensor_key: The sensor key being validated
            device_class: The device class to validate
            warnings: List to append validation warnings to
        """
        try:
            # Try to validate against sensor device classes first
            try:
                # Check against the component's device class list
                sensor_device_classes = HAConstantLoader.get_constant("DEVICE_CLASSES", "homeassistant.components.sensor")
                if device_class in sensor_device_classes:
                    return  # Valid sensor device class
            except Exception as e:
                _LOGGER.debug("Could not check sensor device classes: %s", e)

            # Try to validate against binary sensor device classes
            try:
                # Check against the component's device class list
                binary_sensor_device_classes = HAConstantLoader.get_constant(
                    "DEVICE_CLASSES", "homeassistant.components.binary_sensor"
                )
                if device_class in binary_sensor_device_classes:
                    return  # Valid binary sensor device class
            except Exception as e:
                _LOGGER.debug("Could not check binary sensor device classes: %s", e)

            # If we get here, the device class is not valid
            warnings.append(
                ValidationError(
                    message=(
                        f"Sensor '{sensor_key}' uses invalid device_class '{device_class}'. "
                        f"This is not a recognized Home Assistant device class."
                    ),
                    path=f"sensors.{sensor_key}.metadata.device_class",
                    severity=ValidationSeverity.WARNING,
                    suggested_fix="Use a valid Home Assistant device class",
                )
            )
        except ImportError:
            # If HA imports fail, skip validation to avoid breaking the package
            return
        except Exception:
            # If validation fails for any other reason, skip to avoid breaking the package
            return

    def _validate_unit_compatibility(
        self,
        sensor_key: str,
        sensor_config: dict[str, Any],
        errors: list[ValidationError],
    ) -> None:
        """Validate unit_of_measurement compatibility with device_class (ERROR level)."""
        metadata = sensor_config.get("metadata", {})
        device_class = metadata.get("device_class")
        unit = metadata.get("unit_of_measurement")

        if not device_class or not unit:
            return  # No validation needed if either is missing

        try:
            # Check against both SensorDeviceClass and BinarySensorDeviceClass
            device_class_enum = None
            try:
                sensor_device_class = HAConstantLoader.get_constant("SensorDeviceClass")
                device_class_enum = sensor_device_class(device_class)
            except ValueError:
                # Try BinarySensorDeviceClass if SensorDeviceClass fails
                try:
                    binary_sensor_device_class = HAConstantLoader.get_constant("BinarySensorDeviceClass")
                    device_class_enum = binary_sensor_device_class(device_class)
                except ValueError:
                    # Invalid device_class - not found in either enum
                    errors.append(
                        ValidationError(
                            message=f"Sensor '{sensor_key}' uses invalid device_class '{device_class}'",
                            path=f"sensors.{sensor_key}.metadata.device_class",
                            severity=ValidationSeverity.ERROR,
                        )
                    )
                    return

            # Skip validation for device classes with open-ended unit requirements
            try:
                sensor_device_class = HAConstantLoader.get_constant("SensorDeviceClass")
                SKIP_UNIT_VALIDATION = {
                    sensor_device_class.MONETARY,  # ISO4217 currency codes (180+ options)
                    sensor_device_class.DATE,  # ISO8601 date formats (many variations)
                    sensor_device_class.TIMESTAMP,  # ISO8601 timestamp formats (many variations)
                    sensor_device_class.ENUM,  # User-defined enumeration values
                }
            except ValueError:
                SKIP_UNIT_VALIDATION = set()

            if device_class_enum in SKIP_UNIT_VALIDATION:
                return

            # Get allowed units for this device class
            try:
                device_class_units = HAConstantLoader.get_constant("DEVICE_CLASS_UNITS")
                allowed_units = device_class_units.get(device_class_enum, set())
            except ValueError:
                allowed_units = set()

            if not allowed_units:
                return  # No known restrictions

            # Convert allowed units to string representations for comparison
            allowed_unit_strings = {
                unit_obj.value if hasattr(unit_obj, "value") else str(unit_obj) for unit_obj in allowed_units
            }

            if unit not in allowed_unit_strings:
                errors.append(
                    ValidationError(
                        message=(
                            f"Sensor '{sensor_key}' uses invalid unit '{unit}' "
                            f"with device_class '{device_class}'. This combination is not valid."
                        ),
                        path=f"sensors.{sensor_key}.metadata.unit_of_measurement",
                        severity=ValidationSeverity.ERROR,
                        suggested_fix=f"Use one of: {', '.join(sorted(allowed_unit_strings))}",
                    )
                )
        except Exception as e:
            # If validation fails (e.g., HA constants not available), skip validation
            # This prevents breaking the package if HA changes its validation logic
            _LOGGER.debug("Unit validation failed, skipping: %s", e)

    def _get_v1_schema(self) -> dict[str, Any]:
        """Get the JSON schema for version 1.0 configurations (modernized format)."""
        # Define common patterns
        id_pattern = "^.+$"  # Allow any non-empty string for unique_id, matching HA's real-world requirements
        entity_pattern = "^[a-z_]+\\.[a-z0-9_]+$"
        # Allow entity IDs OR collection patterns (device_class:, area:, label:, regex:, attribute:)
        variable_value_pattern = (
            "^([a-z_]+\\.[a-z0-9_]+|device_class:[a-z0-9_]+|area:[a-z0-9_]+|label:[a-z0-9_]+|regex:.+|attribute:.+)$"
        )
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
                    "device_identifier": {
                        "type": "string",
                        "description": "Default device identifier for all sensors in this set",
                    },
                    "variables": {
                        "type": "object",
                        "description": "Global variable mappings available to all sensors",
                        "patternProperties": {
                            var_pattern: {
                                "oneOf": [
                                    {
                                        "type": "string",
                                        "pattern": entity_pattern,
                                        "description": "Home Assistant entity ID",
                                    },
                                    {
                                        "type": "number",
                                        "description": "Numeric literal value",
                                    },
                                ]
                            }
                        },
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
            "sensors": {
                "type": "object",
                "description": "Dictionary of synthetic sensor definitions",
                "patternProperties": {
                    "^[a-zA-Z_][a-zA-Z0-9_]*$": {"$ref": "#/definitions/sensor"},
                },
                "minProperties": 1,
                "additionalProperties": False,
            },
        }

    def _get_schema_definitions(
        self,
        id_pattern: str,
        variable_value_pattern: str,
        var_pattern: str,
        icon_pattern: str,
    ) -> dict[str, Any]:
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
                    "description": "Optional: Explicit entity ID for the sensor",
                    "pattern": "^[a-z_]+\\.[a-z0-9_]+$",
                },
                "formula": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate",
                    "minLength": 1,
                },
                "variables": {
                    "type": "object",
                    "description": "Variable mappings to Home Assistant entities or numeric literals",
                    "patternProperties": {
                        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                            "oneOf": [
                                {
                                    "type": "string",
                                    "pattern": "^([a-z_]+\\.[a-z0-9_]+|device_class:[a-z0-9_]+|area:[a-z0-9_]+|label:[a-z0-9_]+|regex:.+|attribute:.+)$",
                                    "description": "Home Assistant entity ID or collection pattern",
                                },
                                {
                                    "type": "number",
                                    "description": "Numeric literal value",
                                },
                            ]
                        }
                    },
                    "additionalProperties": False,
                },
                "metadata": {
                    "type": "object",
                    "description": "Sensor metadata including unit_of_measurement, device_class, etc.",
                    "additionalProperties": True,
                },
                "attributes": {
                    "type": "object",
                    "description": "Calculated attributes for the sensor",
                    "patternProperties": {
                        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                            "oneOf": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {
                                            "type": "string",
                                            "description": "Attribute formula",
                                            "minLength": 1,
                                        },
                                        "metadata": {
                                            "type": "object",
                                            "description": "Attribute metadata",
                                            "additionalProperties": True,
                                        },
                                        "variables": {
                                            "type": "object",
                                            "description": "Attribute-specific variables",
                                            "patternProperties": {
                                                "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                    "oneOf": [
                                                        {
                                                            "type": "string",
                                                            "pattern": "^([a-z_]+\\.[a-z0-9_]+|device_class:[a-z0-9_]+|area:[a-z0-9_]+|label:[a-z0-9_]+|regex:.+|attribute:.+)$",
                                                        },
                                                        {
                                                            "type": "number",
                                                        },
                                                    ]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "string",
                                    "description": "Literal string value",
                                },
                                {
                                    "type": "number",
                                    "description": "Literal numeric value",
                                },
                                {
                                    "type": "boolean",
                                    "description": "Literal boolean value",
                                },
                            ]
                        }
                    },
                    "additionalProperties": False,
                },
                "extra_attributes": {
                    "type": "object",
                    "description": "Additional attributes for the entity",
                    "additionalProperties": True,
                },
                "device_identifier": {
                    "type": "string",
                    "description": "Device identifier to associate with",
                },
                "device_name": {
                    "type": "string",
                    "description": "Optional device name override",
                },
                "device_manufacturer": {
                    "type": "string",
                    "description": "Device manufacturer",
                },
                "device_model": {
                    "type": "string",
                    "description": "Device model",
                },
                "device_sw_version": {
                    "type": "string",
                    "description": "Device software version",
                },
                "device_hw_version": {
                    "type": "string",
                    "description": "Device hardware version",
                },
                "suggested_area": {
                    "type": "string",
                    "description": "Suggested area for the sensor",
                },
            },
            "required": ["formula"],
            "additionalProperties": False,
        }

    def _get_formula_definition(
        self,
        id_pattern: str,
        variable_value_pattern: str,
        var_pattern: str,
        icon_pattern: str,
    ) -> dict[str, Any]:
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
                    "description": "Variable mappings to Home Assistant entities, collection patterns, or numeric literals",
                    "patternProperties": {
                        var_pattern: {
                            "oneOf": [
                                {
                                    "type": "string",
                                    "pattern": variable_value_pattern,
                                    "description": "Home Assistant entity ID or collection pattern (device_class:, area:, etc.)",
                                },
                                {
                                    "type": "number",
                                    "description": "Numeric literal value",
                                },
                            ]
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
                    "description": "Home Assistant device class (any string allowed)",
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
        # Return a list of common device classes for schema validation, but allow any string.
        try:
            sensor_device_class = HAConstantLoader.get_constant("SensorDeviceClass")
            return [device_class.value for device_class in sensor_device_class.__members__.values()]
        except Exception:
            # Fallback if enum access fails - return common device classes
            return [
                "apparent_power",
                "aqi",
                "atmospheric_pressure",
                "battery",
                "carbon_dioxide",
                "carbon_monoxide",
                "current",
                "data_rate",
                "data_size",
                "date",
                "distance",
                "duration",
                "energy",
                "frequency",
                "gas",
                "humidity",
                "illuminance",
                "irradiance",
                "moisture",
                "monetary",
                "nitrogen_dioxide",
                "nitrogen_monoxide",
                "nitrous_oxide",
                "ozone",
                "pm1",
                "pm10",
                "pm25",
                "power",
                "power_factor",
                "precipitation",
                "precipitation_intensity",
                "pressure",
                "reactive_power",
                "signal_strength",
                "sound_pressure",
                "speed",
                "sulphur_dioxide",
                "temperature",
                "timestamp",
                "volatile_organic_compounds",
                "voltage",
                "volume",
                "water",
                "weight",
                "wind_speed",
            ]

    def _get_state_class_enum(self) -> list[str]:
        """Get the list of valid state classes from Home Assistant constants."""
        try:
            state_classes = HAConstantLoader.get_constant("STATE_CLASSES", "homeassistant.components.sensor")
            return list(state_classes)
        except Exception:
            # Fallback if enum access fails - return common state classes
            return ["measurement", "total", "total_increasing"]

    def _get_v1_main_properties(
        self, id_pattern: str, entity_pattern: str, var_pattern: str, icon_pattern: str
    ) -> dict[str, Any]:
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
                    "device_identifier": {
                        "type": "string",
                        "description": "Default device identifier for all sensors in this set",
                    },
                    "variables": {
                        "type": "object",
                        "description": "Global variable mappings available to all sensors",
                        "patternProperties": {
                            var_pattern: {
                                "oneOf": [
                                    {
                                        "type": "string",
                                        "pattern": entity_pattern,
                                        "description": "Home Assistant entity ID",
                                    },
                                    {
                                        "type": "number",
                                        "description": "Numeric literal value",
                                    },
                                ]
                            }
                        },
                        "additionalProperties": False,
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Global metadata applied to all sensors",
                        "properties": {
                            "device_class": {
                                "type": "string",
                                "description": "Default device class for all sensors (any string allowed)",
                            },
                            "state_class": {
                                "type": "string",
                                "enum": self._get_state_class_enum(),
                                "description": "Default state class for all sensors",
                            },
                            "unit_of_measurement": {
                                "type": "string",
                                "description": "Default unit of measurement for all sensors",
                            },
                            "icon": {
                                "type": "string",
                                "pattern": icon_pattern,
                                "description": "Default icon for all sensors",
                            },
                        },
                        "additionalProperties": True,
                    },
                },
                "additionalProperties": False,
            },
            "sensors": {
                "type": "object",
                "description": "Dictionary of synthetic sensor definitions",
                "patternProperties": {id_pattern: {"$ref": "#/definitions/v1_sensor"}},
                "additionalProperties": False,
                "minProperties": 1,
            },
        }

    def _get_v1_schema_definitions(
        self, id_pattern: str, entity_pattern: str, var_pattern: str, icon_pattern: str
    ) -> dict[str, Any]:
        """Get the definitions section for the v2.0 schema."""
        return {
            "v1_sensor": self._get_v1_sensor_definition(id_pattern, entity_pattern, var_pattern, icon_pattern),
            "v1_attribute": self._get_v1_attribute_definition(var_pattern, icon_pattern),
        }

    def _get_v1_sensor_definition(
        self, id_pattern: str, entity_pattern: str, var_pattern: str, icon_pattern: str
    ) -> dict[str, Any]:
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
                    "description": "Variable mappings to Home Assistant entities or numeric literals",
                    "patternProperties": {
                        var_pattern: {
                            "oneOf": [
                                {
                                    "type": "string",
                                    "pattern": entity_pattern,
                                    "description": "Home Assistant entity ID",
                                },
                                {
                                    "type": "number",
                                    "description": "Numeric literal value",
                                },
                            ]
                        }
                    },
                    "additionalProperties": False,
                },
                "metadata": {
                    "type": "object",
                    "description": "Metadata dictionary for Home Assistant sensor properties",
                    "properties": {
                        "device_class": {
                            "type": "string",
                            "description": "Device class for the sensor (any string allowed)",
                        },
                        "state_class": {
                            "type": "string",
                            "enum": self._get_state_class_enum(),
                            "description": "State class for the sensor",
                        },
                        "unit_of_measurement": {
                            "type": "string",
                            "description": "Unit of measurement for the sensor",
                        },
                        "icon": {
                            "type": "string",
                            "pattern": icon_pattern,
                            "description": "Icon for the sensor",
                        },
                    },
                    "additionalProperties": True,
                },
                # Device association properties
                "device_identifier": {
                    "type": "string",
                    "description": "Unique identifier for the device this sensor belongs to",
                },
                "device_name": {
                    "type": "string",
                    "description": "Human-readable name for the device",
                },
                "device_manufacturer": {
                    "type": "string",
                    "description": "Manufacturer of the device",
                },
                "device_model": {
                    "type": "string",
                    "description": "Model of the device",
                },
                "device_sw_version": {
                    "type": "string",
                    "description": "Software version of the device",
                },
                "device_hw_version": {
                    "type": "string",
                    "description": "Hardware version of the device",
                },
                "suggested_area": {
                    "type": "string",
                    "description": "Suggested area for the device in Home Assistant",
                },
            },
            "required": ["formula"],
            "additionalProperties": False,
        }

    def _get_v1_attribute_definition(self, var_pattern: str, icon_pattern: str) -> dict[str, Any]:
        """Get the calculated attribute definition for the v2.0 schema."""
        entity_pattern = r"^[a-z_][a-z0-9_]*\.[a-z0-9_]+$"
        return {
            "oneOf": [
                {
                    "type": "object",
                    "description": "Calculated attribute definition with formula",
                    "properties": {
                        "formula": {
                            "type": "string",
                            "description": ("Mathematical expression to evaluate for this attribute"),
                            "minLength": 1,
                        },
                        "variables": {
                            "type": "object",
                            "description": "Variable mappings to Home Assistant entities or numeric literals",
                            "patternProperties": {
                                var_pattern: {
                                    "oneOf": [
                                        {
                                            "type": "string",
                                            "pattern": entity_pattern,
                                            "description": "Home Assistant entity ID",
                                        },
                                        {
                                            "type": "number",
                                            "description": "Numeric literal value",
                                        },
                                    ]
                                }
                            },
                            "additionalProperties": False,
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Metadata dictionary for Home Assistant attribute properties",
                            "properties": {
                                "device_class": {
                                    "type": "string",
                                    "description": "Device class for the attribute (any string allowed)",
                                },
                                "state_class": {
                                    "type": "string",
                                    "enum": self._get_state_class_enum(),
                                    "description": "State class for the attribute",
                                },
                                "unit_of_measurement": {
                                    "type": "string",
                                    "description": "Unit of measurement for the attribute",
                                },
                                "icon": {
                                    "type": "string",
                                    "pattern": icon_pattern,
                                    "description": "Icon for the attribute",
                                },
                            },
                            "additionalProperties": True,
                        },
                    },
                    "required": ["formula"],
                    "additionalProperties": False,
                },
                {
                    "type": "number",
                    "description": "Literal numeric value for the attribute",
                },
                {
                    "type": "string",
                    "description": "Literal string value for the attribute",
                },
                {
                    "type": "boolean",
                    "description": "Literal boolean value for the attribute (True/False)",
                },
            ]
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
    return validator.schemas.get(version)
