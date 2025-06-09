"""
Schema Validation - Comprehensive YAML configuration validation using JSON Schema.

This module provides schema-based validation for synthetic sensor YAML configurations,
with detailed error reporting and support for schema versioning.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypedDict

try:
    import jsonschema
    from jsonschema import Draft7Validator, validators

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    jsonschema = None
    Draft7Validator = None
    validators = None

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
        # Schema for version 1.0
        self._schemas["1.0"] = self._get_v1_schema()

        # Add future schema versions here
        # self._schemas["1.1"] = self._get_v1_1_schema()

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
                    suggested_fix=(
                        f"Use supported version: {', '.join(self._schemas.keys())}"
                    ),
                )
            )
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        schema = self._schemas[version]

        try:
            # Create validator with custom error handling
            validator = Draft7Validator(schema)

            # Validate against schema
            for error in validator.iter_errors(config_data):
                validation_error = self._format_validation_error(error)
                if validation_error.severity == ValidationSeverity.ERROR:
                    errors.append(validation_error)
                else:
                    warnings.append(validation_error)

            # Additional semantic validations
            semantic_errors, semantic_warnings = self._perform_semantic_validation(
                config_data
            )
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

        return ValidationResult(
            valid=len(errors) == 0, errors=errors, warnings=warnings
        )

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

    def _perform_semantic_validation(
        self, config_data: dict[str, Any]
    ) -> tuple[list[ValidationError], list[ValidationError]]:
        """Perform additional semantic validation beyond schema structure.

        Returns:
            Tuple of (errors, warnings)
        """
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []

        sensors = config_data.get("sensors", [])

        # Check for duplicate unique_ids
        unique_ids = []
        for i, sensor in enumerate(sensors):
            unique_id = sensor.get("unique_id")
            if unique_id in unique_ids:
                errors.append(
                    ValidationError(
                        message=f"Duplicate unique_id '{unique_id}' found",
                        path=f"sensors[{i}].unique_id",
                        severity=ValidationSeverity.ERROR,
                        suggested_fix=(
                            "Use unique values for unique_id across all sensors"
                        ),
                    )
                )
            else:
                unique_ids.append(unique_id)

        # Check for duplicate formula IDs within sensors
        for i, sensor in enumerate(sensors):
            formulas = sensor.get("formulas", [])
            formula_ids = []
            for j, formula in enumerate(formulas):
                formula_id = formula.get("id")
                if formula_id in formula_ids:
                    errors.append(
                        ValidationError(
                            message=(
                                f"Duplicate formula id '{formula_id}' in sensor "
                                f"'{sensor.get('unique_id')}'"
                            ),
                            path=f"sensors[{i}].formulas[{j}].id",
                            severity=ValidationSeverity.ERROR,
                            suggested_fix=("Use unique formula IDs within each sensor"),
                        )
                    )
                else:
                    formula_ids.append(formula_id)

        # Validate entity references in formulas
        for i, sensor in enumerate(sensors):
            formulas = sensor.get("formulas", [])
            for j, formula in enumerate(formulas):
                formula_text = formula.get("formula", "")
                variables = formula.get("variables", {})

                # Check if all variables used in formula are defined
                validation_result = self._validate_formula_variables(
                    formula_text, variables
                )
                for error_msg in validation_result:
                    warnings.append(
                        ValidationError(
                            message=error_msg,
                            path=f"sensors[{i}].formulas[{j}]",
                            severity=ValidationSeverity.WARNING,
                            suggested_fix=("Define all variables used in the formula"),
                        )
                    )

        return errors, warnings

    def _validate_formula_variables(
        self, formula: str, variables: dict[str, str]
    ) -> list[str]:
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
            if var not in variables and var not in known_functions:
                # Check if it looks like it could be a variable
                if not var.isdigit() and var not in ["True", "False"]:
                    warnings.append(f"Potential undefined variable '{var}' in formula")

        return warnings

    def _get_v1_schema(self) -> dict[str, Any]:
        """Get the JSON schema for version 1.0 configurations."""
        # Define common patterns to reduce repetition
        id_pattern = "^[a-z][a-z0-9_]*$"
        entity_pattern = "^[a-z_]+\\.[a-z0-9_]+$"
        var_pattern = "^[a-zA-Z_][a-zA-Z0-9_]*$"
        icon_pattern = "^mdi:[a-z0-9-]+$"

        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "HA Synthetic Sensors Configuration",
            "description": (
                "Schema for Home Assistant Synthetic Sensors YAML configuration"
            ),
            "type": "object",
            "properties": self._get_main_properties(
                id_pattern, entity_pattern, var_pattern, icon_pattern
            ),
            "required": ["sensors"],
            "additionalProperties": False,
            "definitions": self._get_schema_definitions(
                id_pattern, entity_pattern, var_pattern, icon_pattern
            ),
        }

    def _get_main_properties(
        self, id_pattern: str, entity_pattern: str, var_pattern: str, icon_pattern: str
    ) -> dict[str, Any]:
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
                        "description": (
                            "Whether synthetic sensors are globally enabled"
                        ),
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

    def _get_schema_definitions(
        self, id_pattern: str, entity_pattern: str, var_pattern: str, icon_pattern: str
    ) -> dict[str, Any]:
        """Get the definitions section for the schema."""
        return {
            "sensor": self._get_sensor_definition(id_pattern),
            "formula": self._get_formula_definition(
                id_pattern, entity_pattern, var_pattern, icon_pattern
            ),
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

    def _get_formula_definition(
        self, id_pattern: str, entity_pattern: str, var_pattern: str, icon_pattern: str
    ) -> dict[str, Any]:
        """Get the formula definition for the schema."""
        return {
            "type": "object",
            "description": "Formula calculation definition",
            "properties": {
                "id": {
                    "type": "string",
                    "description": (
                        "Unique identifier for the formula within the sensor"
                    ),
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
        """Get the list of valid device classes."""
        return [
            "energy",
            "power",
            "voltage",
            "current",
            "temperature",
            "humidity",
            "pressure",
            "illuminance",
            "battery",
            "timestamp",
            "duration",
            "distance",
            "speed",
            "weight",
            "volume",
            "monetary",
            "signal_strength",
            "data_rate",
            "data_size",
            "frequency",
            "reactive_power",
            "apparent_power",
            "power_factor",
            "carbon_monoxide",
            "carbon_dioxide",
            "nitrogen_dioxide",
            "nitrogen_monoxide",
            "nitrous_oxide",
            "ozone",
            "pm1",
            "pm25",
            "pm10",
            "sulphur_dioxide",
            "volatile_organic_compounds",
        ]


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
