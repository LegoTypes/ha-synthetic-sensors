"""
Schema Validation - YAML configuration validation using JSON Schema.

This module provides schema-based validation for synthetic sensor YAML configurations,
with detailed error reporting and support for schema versioning.
"""

# pylint: disable=too-many-lines

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
import logging
import re
from typing import Any, TypedDict

from homeassistant.exceptions import ConfigEntryError
import jsonschema

from .constants_formula import FORMULA_RESERVED_WORDS
from .constants_metadata import (
    METADATA_PROPERTY_DEVICE_CLASS,
    METADATA_PROPERTY_STATE_CLASS,
    METADATA_PROPERTY_UNIT_OF_MEASUREMENT,
)
from .formula_utils import tokenize_formula
from .ha_constants import HAConstantLoader
from .shared_constants import (
    DATETIME_FUNCTIONS,
    DURATION_FUNCTIONS,
    ENGINE_BASE_RESERVED_ATTRIBUTES,
    LAST_VALID_CHANGED_KEY,
    LAST_VALID_STATE_KEY,
    METADATA_FUNCTIONS,
)

HAS_JSONSCHEMA = True

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


class SchemaValidator:
    """Validates YAML configuration against JSON schema and additional semantic rules."""

    # Common regex patterns used across validation methods
    VARIABLE_VALUE_PATTERN = (
        "^([a-z_]+\\.[a-z0-9_.]+|[a-zA-Z_][a-zA-Z0-9_]*|device_class:[a-z0-9_]+|"
        "area:[a-z0-9_]+|label:[a-z0-9_]+|regex:.+|attribute:.+|(sum|avg|mean|count|min|max|std|var)\\(.+\\)|"
        "\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:Z|[+-]\\d{2}:?\\d{2})?|"
        "v\\d+(\\.\\d+){0,2}([-+][a-zA-Z0-9\\-.]+)?|\\d+\\.\\d+)$"
    )

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
            ValidationResult with validation status and any errors
        """
        if not JSONSCHEMA_AVAILABLE:
            raise ConfigEntryError("jsonschema not available, schema validation required")

        errors: list[ValidationError] = []

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
            return ValidationResult(valid=False, errors=errors)

        schema = self.schemas[version]

        try:
            # Create validator with custom error handling
            if Draft7Validator is None:
                raise ImportError("jsonschema not available")
            validator = Draft7Validator(schema)

            # Validate against schema
            for error in validator.iter_errors(config_data):
                validation_error = self._format_validation_error(error)
                errors.append(validation_error)

            # Additional semantic validations
            semantic_errors, semantic_warnings = self._perform_semantic_validation(config_data)
            errors.extend(semantic_errors)
            errors.extend(semantic_warnings)  # Treat all semantic issues as errors

        except Exception as exc:
            self._logger.exception("Schema validation failed")
            errors.append(
                ValidationError(
                    message=f"Schema validation error: {exc}",
                    path="",
                    severity=ValidationSeverity.ERROR,
                )
            )

        return ValidationResult(valid=len(errors) == 0, errors=errors)

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
        warnings: list[ValidationError] = []  # Empty list for compatibility

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

            # First validate sensor key references across the entire config
            self._validate_sensor_key_references(config_data, errors)

            for sensor_key, sensor_config in sensors.items():
                # Validate device class using HA's built-in validation
                metadata = sensor_config.get("metadata", {})
                device_class = metadata.get(METADATA_PROPERTY_DEVICE_CLASS)
                if device_class:
                    self._validate_device_class(sensor_key, device_class, errors)

                self._validate_sensor_config(sensor_key, sensor_config, errors, config_data)
                self._validate_state_class_compatibility(sensor_key, sensor_config, errors)
                self._validate_unit_compatibility(sensor_key, sensor_config, errors)

        return errors, warnings  # warnings will always be empty now

    def _validate_state_class_compatibility(
        self,
        sensor_key: str,
        sensor_config: dict[str, Any],
        errors: list[ValidationError],
    ) -> None:
        """Validate state_class compatibility with device_class using HA's mappings."""
        metadata = sensor_config.get("metadata", {})
        state_class = metadata.get(METADATA_PROPERTY_STATE_CLASS)
        device_class = metadata.get(METADATA_PROPERTY_DEVICE_CLASS, "")

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
                        errors.append(
                            ValidationError(
                                message=f"Invalid state_class '{state_class}'. Valid options: {sensor_state_classes}",
                                path=f"sensors.{sensor_key}.state_class",
                                severity=ValidationSeverity.ERROR,
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
                    errors.append(
                        ValidationError(
                            message=(
                                f"Invalid state_class '{state_class}' for device_class '{device_class}'. "
                                f"Valid options: {[sc.value for sc in allowed_state_classes]}"
                            ),
                            path=f"sensors.{sensor_key}.state_class",
                            severity=ValidationSeverity.ERROR,
                        )
                    )
            except ValueError:
                pass  # Skip validation if we can't get the constants

            # Additional validation for problematic combinations using HA's device class to state class mappings
            if state_class_enum == sensor_state_class.TOTAL_INCREASING:
                try:
                    device_class_state_classes = HAConstantLoader.get_constant("DEVICE_CLASS_STATE_CLASSES")
                    allowed_state_classes = device_class_state_classes.get(device_class_enum, set())

                    # Check if TOTAL_INCREASING is not in the allowed state classes for this device class
                    if sensor_state_class.TOTAL_INCREASING not in allowed_state_classes:
                        # Find a suitable alternative state class
                        suggested_state_class = sensor_state_class.MEASUREMENT
                        if sensor_state_class.MEASUREMENT in allowed_state_classes:
                            suggested_state_class = sensor_state_class.MEASUREMENT
                        elif sensor_state_class.TOTAL in allowed_state_classes:
                            suggested_state_class = sensor_state_class.TOTAL
                        else:
                            # If no suitable alternative found, just suggest measurement
                            suggested_state_class = sensor_state_class.MEASUREMENT

                        errors.append(
                            ValidationError(
                                message=(
                                    f"Sensor '{sensor_key}' uses state_class '{sensor_state_class.TOTAL_INCREASING.value}' with "
                                    f"device_class '{device_class}' which doesn't support this state class."
                                ),
                                path=f"sensors.{sensor_key}.state_class",
                                severity=ValidationSeverity.ERROR,
                                suggested_fix=f"Consider using '{suggested_state_class.value}' instead",
                            )
                        )
                except ValueError:
                    pass  # Skip validation if we can't get the constants

        except ImportError:
            # HA not available - skip validation
            pass

    def _validate_sensor_config(
        self,
        sensor_key: str,
        sensor_config: dict[str, Any],
        errors: list[ValidationError],
        config_data: dict[str, Any] | None = None,
    ) -> None:
        """Validate a single sensor configuration."""
        # Single formula sensor validation
        if "formula" in sensor_config:
            self._validate_sensor_formula(sensor_key, sensor_config, errors, config_data)

        # Validate calculated attributes (if present)
        attributes = sensor_config.get("attributes", {})
        if attributes:
            self._validate_sensor_attributes(sensor_key, sensor_config, attributes, errors, config_data)

    def _validate_sensor_formula(
        self,
        sensor_key: str,
        sensor_config: dict[str, Any],
        errors: list[ValidationError],
        config_data: dict[str, Any] | None = None,
    ) -> None:
        """Validate a sensor's main formula."""
        formula_text = sensor_config.get("formula", "")
        variables = sensor_config.get("variables", {})

        # Skip validation if formula_text is not a string (schema validation will catch this)
        if not isinstance(formula_text, str):
            return

        # Extract context from config_data for comprehensive validation
        global_vars, sensor_keys = self._extract_validation_context(config_data)
        sensor_vars = set(variables.keys())

        # Use _validate_formula_tokens for comprehensive validation
        self._validate_formula_tokens(
            formula_text,
            sensor_keys,
            f"sensors.{sensor_key}.formula",
            errors,
            global_vars=global_vars,
            sensor_vars=sensor_vars,
        )

        # Metadata function validation removed - 'state' token is valid for metadata functions

    def _validate_sensor_attributes(
        self,
        sensor_key: str,
        sensor_config: dict[str, Any],
        attributes: dict[str, Any],
        errors: list[ValidationError],
        config_data: dict[str, Any] | None = None,
    ) -> None:
        """Validate sensor attributes."""
        variables = sensor_config.get("variables", {})

        # Check for variable shadowing (scoping validation)
        self._validate_attribute_scoping(sensor_key, attributes, errors)

        # Check for attribute dependency cycles and build evaluation order
        self._validate_attribute_dependencies(sensor_key, attributes, errors)

        for attr_name, attr_config in attributes.items():
            # Disallow engine-reserved attribute names at YAML validation time
            # Use shared constants to detect collisions with engine-reserved attribute names
            if attr_name in (LAST_VALID_STATE_KEY, LAST_VALID_CHANGED_KEY) or attr_name in ENGINE_BASE_RESERVED_ATTRIBUTES:
                errors.append(
                    ValidationError(
                        message=f"Attribute name '{attr_name}' is reserved by the engine and cannot be used",
                        path=f"sensors.{sensor_key}.attributes.{attr_name}",
                        severity=ValidationSeverity.ERROR,
                        suggested_fix=f"Rename attribute '{attr_name}' to avoid collision with engine-reserved attributes",
                    )
                )
                continue

            self._validate_single_attribute(sensor_key, attr_name, attr_config, variables, attributes, errors, config_data)

    def _validate_single_attribute(
        self,
        sensor_key: str,
        attr_name: str,
        attr_config: dict[str, Any],
        variables: dict[str, Any],
        all_attributes: dict[str, Any],
        errors: list[ValidationError],
        config_data: dict[str, Any] | None = None,
    ) -> None:
        """Validate a single attribute."""
        # Skip validation if attr_config is not a dict (schema validation will catch this)
        if not isinstance(attr_config, dict):
            return

        attr_formula = attr_config.get("formula", "")

        # Allow 'state' variable in attribute formulas
        extended_variables = variables.copy()
        extended_variables["state"] = "main_sensor_state"

        # Include the current attribute's own variables
        attr_own_variables = attr_config.get("variables", {})
        extended_variables.update(attr_own_variables)

        # Skip validation if attr_formula is not a string (schema validation will catch this)
        if not isinstance(attr_formula, str):
            return

        # Extract context from config_data for comprehensive validation
        global_vars, sensor_keys = self._extract_validation_context(config_data)
        sensor_vars = set(variables.keys())
        attr_vars = set(extended_variables.keys())

        # Identify literal attributes and other formula attributes for cross-references
        literal_attrs, other_attr_names = self._categorize_attributes(all_attributes, attr_name)

        # Disallow attribute names that collide with engine-managed last-valid attribute keys
        if attr_name in (LAST_VALID_STATE_KEY, LAST_VALID_CHANGED_KEY):
            errors.append(
                ValidationError(
                    message=f"Attribute name '{attr_name}' is reserved by the engine and cannot be used",
                    path=f"sensors.{sensor_key}.attributes.{attr_name}",
                    severity=ValidationSeverity.ERROR,
                    suggested_fix=f"Rename attribute '{attr_name}' to avoid collision with engine-reserved attributes",
                )
            )
            return

        # Use _validate_formula_tokens for comprehensive validation
        self._validate_formula_tokens(
            attr_formula,
            sensor_keys,
            f"sensors.{sensor_key}.attributes.{attr_name}.formula",
            errors,
            global_vars=global_vars,
            sensor_vars=sensor_vars,
            attr_vars=attr_vars,
            literal_attrs=literal_attrs,
            other_attr_names=other_attr_names,
        )

        # Metadata function validation removed - 'state' token is valid for metadata functions

    def _extract_validation_context(self, config_data: dict[str, Any] | None) -> tuple[set[str], set[str]]:
        """Extract global variables and sensor keys from config data."""
        if config_data:
            # Get global variables
            global_settings = config_data.get("global_settings", {})
            global_variables = global_settings.get("variables", {})
            global_vars = set(global_variables.keys())

            # Get all sensor keys for cross-sensor references
            sensors = config_data.get("sensors", {})
            sensor_keys = set(sensors.keys())
        else:
            global_vars = set()
            sensor_keys = set()

        return global_vars, sensor_keys

    def _categorize_attributes(self, attributes: dict[str, Any], current_attr_name: str) -> tuple[set[str], set[str]]:
        """Categorize attributes into literal and formula attributes."""
        literal_attrs = set()
        other_attr_names = set()

        for other_attr_name, other_attr_config in attributes.items():
            if other_attr_name == current_attr_name:  # Don't include self
                continue

            if isinstance(other_attr_config, dict) and "formula" in other_attr_config:
                # This is another formula attribute
                other_attr_names.add(other_attr_name)
            else:
                # This is a literal attribute
                literal_attrs.add(other_attr_name)

        return literal_attrs, other_attr_names

    def _validate_attribute_scoping(
        self,
        sensor_key: str,
        attributes: dict[str, Any],
        errors: list[ValidationError],
    ) -> None:
        """Validate attribute scoping to detect variable shadowing.

        Checks for variables in formula attributes that shadow literal attributes,
        similar to Python variable shadowing in inner scopes.

        Args:
            sensor_key: The sensor key being validated
            attributes: The attributes dictionary for the sensor
            errors: List to append validation errors to
        """
        # First, identify literal attributes (non-dict values)
        literal_attributes: set[str] = set()
        formula_attributes: dict[str, dict[str, Any]] = {}

        for attr_name, attr_config in attributes.items():
            if isinstance(attr_config, dict) and "formula" in attr_config:
                # This is a formula attribute
                formula_attributes[attr_name] = attr_config
            else:
                # This is a literal attribute
                literal_attributes.add(attr_name)

        # Check each formula attribute for variable shadowing
        for attr_name, attr_config in formula_attributes.items():
            formula_variables = attr_config.get("variables", {})

            for var_name in formula_variables:
                if var_name in literal_attributes:
                    errors.append(
                        ValidationError(
                            message=f"Variable '{var_name}' in formula '{attr_name}' has a naming collision with literal attribute '{var_name}'",
                            path=f"sensors.{sensor_key}.attributes.{attr_name}.variables.{var_name}",
                            severity=ValidationSeverity.ERROR,
                        )
                    )

    def _validate_attribute_dependencies(
        self,
        sensor_key: str,
        attributes: dict[str, Any],
        errors: list[ValidationError],
    ) -> list[str]:
        """Validate attribute dependencies and return evaluation order.

        Uses topological sort to determine evaluation order and detect circular dependencies.

        Args:
            sensor_key: The sensor key being validated
            attributes: The attributes dictionary for the sensor
            errors: List to append validation errors to

        Returns:
            List of attribute names in evaluation order (dependencies first)
        """
        # Build dependency graph
        dependencies, _ = self._build_dependency_graph(attributes)

        # Perform topological sort to detect cycles and determine evaluation order
        all_attr_names = set(attributes.keys())
        evaluation_order = self._perform_topological_sort(dependencies, all_attr_names)

        # Check for circular dependencies
        if len(evaluation_order) != len(attributes):
            self._handle_circular_dependencies(sensor_key, evaluation_order, all_attr_names, errors)
            # Return partial order for continued validation
            return evaluation_order + sorted(set(attributes.keys()) - set(evaluation_order))

        return evaluation_order

    def _build_dependency_graph(self, attributes: dict[str, Any]) -> tuple[dict[str, set[str]], dict[str, str]]:
        """Build the dependency graph for attributes."""
        dependencies: dict[str, set[str]] = defaultdict(set)  # attr -> set of attrs it depends on
        formula_attrs: dict[str, str] = {}  # attr -> formula

        # First pass: identify all attributes and their types
        all_attr_names = set(attributes.keys())

        for attr_name, attr_config in attributes.items():
            if isinstance(attr_config, dict) and "formula" in attr_config:
                formula = attr_config.get("formula", "")
                if isinstance(formula, str):
                    formula_attrs[attr_name] = formula

        # Second pass: build dependency graph by analyzing formulas
        for attr_name, formula in formula_attrs.items():
            if self._is_formula_expression(formula):
                tokens = tokenize_formula(formula)
                for token in tokens:
                    # Check if token refers to another attribute
                    if token in all_attr_names and token != attr_name:
                        dependencies[attr_name].add(token)

        return dependencies, formula_attrs

    def _perform_topological_sort(self, dependencies: dict[str, set[str]], all_attr_names: set[str]) -> list[str]:
        """Perform topological sort using Kahn's algorithm."""
        evaluation_order = []
        in_degree = dict.fromkeys(all_attr_names, 0)

        # Calculate in-degrees
        for attr_name, deps in dependencies.items():
            for dep in deps:
                if dep in in_degree:  # Only count dependencies that are actual attributes
                    in_degree[attr_name] += 1

        # Kahn's algorithm for topological sort
        queue = deque([attr for attr, degree in in_degree.items() if degree == 0])

        while queue:
            current = queue.popleft()
            evaluation_order.append(current)

            # Remove edges from current node
            for attr_name, deps in dependencies.items():
                if current in deps:
                    deps.remove(current)
                    in_degree[attr_name] -= 1
                    if in_degree[attr_name] == 0:
                        queue.append(attr_name)

        return evaluation_order

    def _handle_circular_dependencies(
        self,
        sensor_key: str,
        evaluation_order: list[str],
        all_attr_names: set[str],
        errors: list[ValidationError],
    ) -> None:
        """Handle circular dependencies by adding validation errors."""
        remaining_attrs = all_attr_names - set(evaluation_order)
        cycle_attrs = sorted(remaining_attrs)

        errors.append(
            ValidationError(
                message=f"Circular dependency detected in attributes: {', '.join(cycle_attrs)}",
                path=f"sensors.{sensor_key}.attributes",
                severity=ValidationSeverity.ERROR,
            )
        )

    def _validate_device_class(
        self,
        sensor_key: str,
        device_class: str,
        errors: list[ValidationError],
    ) -> None:
        """Validate device class using Home Assistant's built-in validation.

        Args:
            sensor_key: The sensor key being validated
            device_class: The device class to validate
            errors: List to append validation errors to
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
            errors.append(
                ValidationError(
                    message=(
                        f"Sensor '{sensor_key}' uses invalid device_class '{device_class}'. "
                        f"This is not a recognized Home Assistant device class."
                    ),
                    path=f"sensors.{sensor_key}.metadata.device_class",
                    severity=ValidationSeverity.ERROR,
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
        device_class = metadata.get(METADATA_PROPERTY_DEVICE_CLASS)
        unit = metadata.get(METADATA_PROPERTY_UNIT_OF_MEASUREMENT)

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

    def _is_entity_id(self, value: str) -> bool:
        """Check if a string is an entity ID vs sensor key.

        Supports basic entity IDs (sensor.power_meter) and attribute references (sensor.power_meter.state)
        """
        return bool(re.match(r"^[a-z_]+\.[a-z0-9_.]+$", value))

    def _is_collection_pattern(self, value: str) -> bool:
        """Check if a string is a collection pattern."""
        return bool(re.match(r"^(device_class|area|label|regex|attribute):", value))

    def _is_collection_function(self, value: str) -> bool:
        """Check if a string is a collection function."""
        return bool(re.match(r"^(sum|avg|mean|count|min|max|std|var)\(", value))

    def _is_formula_expression(self, value: str) -> bool:
        """Check if a string is a formula expression.

        Formula expressions contain mathematical operators and variable references.
        """
        # Look for mathematical operators like +, -, *, /, ()
        # Allow decimal numbers (dots followed by digits) but exclude entity IDs (dots followed by letters)
        # Exclude collection patterns (containing colons)
        has_operators = bool(re.search(r"[+\-*/()]", value))
        is_entity_id = bool(re.search(r"\.[a-zA-Z]", value))  # dot followed by letter indicates entity ID
        has_colon = ":" in value
        return has_operators and not is_entity_id and not has_colon

    def _is_datetime_literal(self, value: str) -> bool:
        """Check if a string is a datetime literal (full datetime or date-only)."""
        # Accept full datetime: 2025-01-01T12:00:00Z
        datetime_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:?\d{2})?$"
        # Accept date-only: 2025-01-01
        date_pattern = r"^\d{4}-\d{2}-\d{2}$"
        return bool(re.match(datetime_pattern, value) or re.match(date_pattern, value))

    def _is_version_literal(self, value: str) -> bool:
        """Check if a string is a version literal (requires 'v' prefix)."""
        return bool(re.match(r"^v\d+(\.\d+){0,2}([-+][a-zA-Z0-9\-.]+)?$", value))

    def _validate_formula_tokens(
        self,
        formula: str,
        sensor_keys: set[str],
        path: str,
        errors: list[ValidationError],
        global_vars: set[str] | None = None,
        sensor_vars: set[str] | None = None,
        attr_vars: set[str] | None = None,
        literal_attrs: set[str] | None = None,
        other_attr_names: set[str] | None = None,
    ) -> None:
        """Validate that all tokens in a formula expression are valid references."""
        if not self._is_formula_expression(formula):
            return

        tokens = tokenize_formula(formula)
        for token in tokens:
            # Check if token is valid in any scope:
            # 1. Global variables (accessible from anywhere)
            # 2. Local sensor variables (accessible within same sensor)
            # 3. Local attribute variables (accessible within same attribute)
            # 4. Sensor keys (for cross-sensor references)
            # 5. Datetime function names (now, today, yesterday, etc.)
            # 6. Duration function names (days, hours, minutes, etc.)
            # 7. Entity references (domain.entity format)
            datetime_functions = DATETIME_FUNCTIONS
            duration_functions = DURATION_FUNCTIONS
            metadata_functions = METADATA_FUNCTIONS
            is_valid = (
                token in sensor_keys
                or (global_vars and token in global_vars)
                or (sensor_vars and token in sensor_vars)
                or (attr_vars and token in attr_vars)
                or (literal_attrs and token in literal_attrs)
                or (other_attr_names and token in other_attr_names)
                or token in datetime_functions
                or token in duration_functions
                or token in metadata_functions
                or token in FORMULA_RESERVED_WORDS
                or self._is_entity_id(token)
            )

            if not is_valid:
                available_refs: list[str] = []
                if global_vars:
                    available_refs.extend(f"global:{var}" for var in sorted(global_vars))
                if sensor_vars:
                    available_refs.extend(f"local:{var}" for var in sorted(sensor_vars))
                if attr_vars:
                    available_refs.extend(f"attr:{var}" for var in sorted(attr_vars))
                if literal_attrs:
                    available_refs.extend(f"literal:{attr}" for attr in sorted(literal_attrs))
                if other_attr_names:
                    available_refs.extend(f"attribute:{attr}" for attr in sorted(other_attr_names))
                available_refs.extend(f"sensor:{key}" for key in sorted(sensor_keys))

                errors.append(
                    ValidationError(
                        message=f"Potential undefined variable '{token}' in formula",
                        path=path,
                        severity=ValidationSeverity.ERROR,
                        suggested_fix="Define all variables used in the formula",
                    )
                )

    def _validate_variable_value(
        self,
        var_value: Any,
        sensor_keys: set[str],
        global_vars: set[str],
        sensor_vars: set[str] | None = None,
        attr_vars: set[str] | None = None,
    ) -> bool:
        """Validate a variable value is a recognized pattern.

        Variable values can only be:
        - References to sensor keys, global vars, or local vars
        - Entity IDs (domain.entity format)
        - Collection patterns (device_class:, area:, etc.)
        - Simple literals (numbers, dates, versions, plain strings)
        - Computed variables with 'formula:' prefix

        They CANNOT be formula expressions or collection functions.

        Returns True if valid, False otherwise.
        """
        # Handle non-string literals (numbers)
        if isinstance(var_value, int | float):
            return True

        # Check if it's a computed variable (dict with formula key)
        if isinstance(var_value, dict) and "formula" in var_value:
            formula_expr = var_value.get("formula", "")
            return bool(str(formula_expr).strip())  # Must have non-empty formula expression

        # Only process strings from this point on
        if not isinstance(var_value, str):
            return False

        # Consolidate all string validation checks into a single return
        return (
            self._is_variable_reference(var_value, sensor_keys, global_vars, sensor_vars, attr_vars)
            or self._is_entity_id(var_value)
            or self._is_collection_pattern(var_value)
            or self._is_datetime_literal(var_value)
            or self._is_version_literal(var_value)
            or self._is_datetime_function_call(var_value)
            or self._is_numeric_string(var_value)
            or self._is_simple_string_literal(var_value)
        )

    def _is_variable_reference(
        self,
        var_value: str,
        sensor_keys: set[str],
        global_vars: set[str],
        sensor_vars: set[str] | None = None,
        attr_vars: set[str] | None = None,
    ) -> bool:
        """Check if a value is a reference to an existing variable or sensor."""
        return (
            var_value in sensor_keys
            or var_value in global_vars
            or (sensor_vars is not None and var_value in sensor_vars)
            or (attr_vars is not None and var_value in attr_vars)
        )

    def _validate_attribute_variables(
        self,
        sensor_key: str,
        attr_name: str,
        attr_config: dict[str, Any],
        sensor_keys: set[str],
        global_var_keys: set[str],
        sensor_var_keys: set[str],
        errors: list[ValidationError],
    ) -> None:
        """Validate variables within an attribute configuration."""
        attr_variables = attr_config.get("variables", {})
        attr_var_keys = set(attr_variables.keys())

        for var_name, var_value in attr_variables.items():
            if isinstance(var_value, str):
                # First validate formula expressions by tokenizing them
                # Attribute variables can reference global vars, sensor vars, other attr vars, and sensor keys
                self._validate_formula_tokens(
                    var_value,
                    sensor_keys,
                    f"sensors.{sensor_key}.attributes.{attr_name}.variables.{var_name}",
                    errors,
                    global_vars=global_var_keys,
                    sensor_vars=sensor_var_keys,
                    attr_vars=attr_var_keys,
                )

                # Check what type of value this is by elimination
                if not self._validate_variable_value(var_value, sensor_keys, global_var_keys, sensor_var_keys, attr_var_keys):
                    errors.append(
                        ValidationError(
                            message=f"Invalid variable value '{var_value}' - must be a sensor key, entity ID, collection pattern, or simple literal",
                            path=f"sensors.{sensor_key}.attributes.{attr_name}.variables.{var_name}",
                            severity=ValidationSeverity.ERROR,
                            suggested_fix="Use a valid sensor key, entity ID (domain.entity), collection pattern (device_class:type), or simple literal value",
                        )
                    )

    def _validate_global_settings(
        self,
        global_settings: dict[str, Any],
        sensor_keys: set[str] | None,
        errors: list[ValidationError],
        warnings: list[ValidationError],
    ) -> None:
        """Validate global settings configuration.

        Args:
            global_settings: Global settings dictionary to validate
            sensor_keys: Set of available sensor keys (None for standalone validation)
            errors: List to append validation errors to
            warnings: List to append validation warnings to
        """
        if not global_settings:
            return

        global_variables = global_settings.get("variables", {})
        global_var_keys = set(global_variables.keys())

        # Use empty set if no sensor keys provided (for standalone validation)
        available_sensor_keys = sensor_keys or set()

        for var_name, var_value in global_variables.items():
            if isinstance(var_value, str):
                # First validate formula expressions by tokenizing them
                # Global variables can reference other global variables and sensor keys
                self._validate_formula_tokens(
                    var_value,
                    available_sensor_keys,
                    f"global_settings.variables.{var_name}",
                    errors,
                    global_vars=global_var_keys,
                )

                # Check what type of value this is by elimination
                if not self._validate_variable_value(var_value, available_sensor_keys, global_var_keys):
                    errors.append(
                        ValidationError(
                            message=f"Invalid variable value '{var_value}' - must be a sensor key, entity ID, collection pattern, or simple literal",
                            path=f"global_settings.variables.{var_name}",
                            severity=ValidationSeverity.ERROR,
                            suggested_fix="Use a valid sensor key, entity ID (domain.entity), collection pattern (device_class:type), or simple literal value",
                        )
                    )

    def validate_global_settings(
        self,
        global_settings: dict[str, Any],
        sensor_keys: set[str] | None,
        errors: list[ValidationError],
        warnings: list[ValidationError],
    ) -> None:
        """Public wrapper for global settings validation.

        Args:
            global_settings: Global settings dictionary to validate
            sensor_keys: Set of available sensor keys (None for standalone validation)
            errors: List to append validation errors to
            warnings: List to append validation warnings to
        """
        self._validate_global_settings(global_settings, sensor_keys, errors, warnings)

    def _validate_sensor_key_references(self, config_data: dict[str, Any], errors: list[ValidationError]) -> None:
        """Validate that all sensor key references point to actual sensors in the config."""
        sensors = config_data.get("sensors", {})
        sensor_keys = set(sensors.keys())
        warnings: list[ValidationError] = []

        # Validate global settings using the dedicated method
        global_settings = config_data.get("global_settings", {})
        self._validate_global_settings(global_settings, sensor_keys, errors, warnings)

        # Get global variable keys for sensor validation
        global_variables = global_settings.get("variables", {})
        global_var_keys = set(global_variables.keys())

        # Check sensor-level variables and attribute variables
        for sensor_key, sensor_config in sensors.items():
            # Check sensor-level variables
            sensor_variables = sensor_config.get("variables", {})
            sensor_var_keys = set(sensor_variables.keys())

            for var_name, var_value in sensor_variables.items():
                if isinstance(var_value, str):
                    # First validate formula expressions by tokenizing them
                    # Sensor variables can reference global vars, other sensor vars in same sensor, and sensor keys
                    self._validate_formula_tokens(
                        var_value,
                        sensor_keys,
                        f"sensors.{sensor_key}.variables.{var_name}",
                        errors,
                        global_vars=global_var_keys,
                        sensor_vars=sensor_var_keys,
                    )

                    # Check what type of value this is by elimination
                    if not self._validate_variable_value(var_value, sensor_keys, global_var_keys, sensor_var_keys):
                        errors.append(
                            ValidationError(
                                message=f"Invalid variable value '{var_value}' - must be a sensor key, entity ID, collection pattern, or simple literal",
                                path=f"sensors.{sensor_key}.variables.{var_name}",
                                severity=ValidationSeverity.ERROR,
                                suggested_fix="Use a valid sensor key, entity ID (domain.entity), collection pattern (device_class:type), or simple literal value",
                            )
                        )

            # Check attribute-level variables
            attributes = sensor_config.get("attributes", {})
            for attr_name, attr_config in attributes.items():
                if isinstance(attr_config, dict):
                    self._validate_attribute_variables(
                        sensor_key, attr_name, attr_config, sensor_keys, global_var_keys, sensor_var_keys, errors
                    )

    def _get_v1_schema(self) -> dict[str, Any]:
        """Get the JSON schema for version 1.0 configurations (modernized format)."""
        # Define common patterns
        id_pattern = "^.+$"  # Allow any non-empty string for unique_id, matching HA's real-world requirements
        var_pattern = "^[a-zA-Z_][a-zA-Z0-9_]*$"
        icon_pattern = "^mdi:[a-z0-9-]+$"

        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "HA Synthetic Sensors Configuration",
            "description": ("Schema for Home Assistant Synthetic Sensors YAML configuration"),
            "type": "object",
            "properties": self._get_v1_main_properties(id_pattern, self.VARIABLE_VALUE_PATTERN, var_pattern, icon_pattern),
            "required": ["sensors"],
            "additionalProperties": False,
            "definitions": self._get_v1_schema_definitions(id_pattern, self.VARIABLE_VALUE_PATTERN, var_pattern, icon_pattern),
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
                "alternate_states": {
                    "type": "object",
                    "description": "Alternative state handlers for UNAVAILABLE, UNKNOWN, NONE, and FALLBACK states",
                    "properties": {
                        "UNAVAILABLE": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "number"},
                                {"type": "boolean"},
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string", "minLength": 1},
                                        "variables": {
                                            "type": "object",
                                            "patternProperties": {
                                                "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                    "oneOf": [
                                                        {"type": "string"},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                    ]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                            ],
                            "description": "Alternate state handler for UNAVAILABLE (literal or {formula, variables}).",
                        },
                        "UNKNOWN": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "number"},
                                {"type": "boolean"},
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string", "minLength": 1},
                                        "variables": {
                                            "type": "object",
                                            "patternProperties": {
                                                "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                    "oneOf": [
                                                        {"type": "string"},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                    ]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                            ],
                            "description": "Alternate state handler for UNKNOWN (literal or {formula, variables}).",
                        },
                        "NONE": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "number"},
                                {"type": "boolean"},
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string", "minLength": 1},
                                        "variables": {
                                            "type": "object",
                                            "patternProperties": {
                                                "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                    "oneOf": [
                                                        {"type": "string"},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                    ]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                            ],
                            "description": "Alternate state handler for NONE (literal or {formula, variables}).",
                        },
                        "FALLBACK": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "number"},
                                {"type": "boolean"},
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string", "minLength": 1},
                                        "variables": {
                                            "type": "object",
                                            "patternProperties": {
                                                "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                    "oneOf": [
                                                        {"type": "string"},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                    ]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                            ],
                            "description": "Fallback alternate state handler (literal or {formula, variables}).",
                        },
                    },
                    "additionalProperties": False,
                },
                "variables": {
                    "type": "object",
                    "description": "Variable mappings to Home Assistant entities, numeric literals, boolean literals, datetime strings, or computed variables",
                    "patternProperties": {
                        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                            "oneOf": [
                                {
                                    "type": "string",
                                    "pattern": self.VARIABLE_VALUE_PATTERN,
                                    "description": "Home Assistant entity ID, sensor key, collection pattern, collection function, formula expression, datetime string, or version string",
                                },
                                {
                                    "type": "number",
                                    "description": "Numeric literal value",
                                },
                                {
                                    "type": "boolean",
                                    "description": "Boolean literal value",
                                },
                                {
                                    "type": "object",
                                    "description": "Computed variable with formula and optional alternate state handlers",
                                    "properties": {
                                        "formula": {
                                            "type": "string",
                                            "description": "Mathematical expression to evaluate for this variable",
                                            "minLength": 1,
                                        },
                                        "allow_unresolved_states": {
                                            "type": "boolean",
                                            "description": "Allow alternate states to proceed into formula evaluation (default: false)",
                                            "default": False,
                                        },
                                        "alternate_states": {
                                            "type": "object",
                                            "description": "Alternative state handlers for UNAVAILABLE, UNKNOWN, NONE, and FALLBACK states",
                                            "properties": {
                                                "UNAVAILABLE": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Alternate state handler for UNAVAILABLE (literal or {formula, variables}).",
                                                },
                                                "UNKNOWN": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Alternate state handler for UNKNOWN (literal or {formula, variables}).",
                                                },
                                                "NONE": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Alternate state handler for NONE (literal or {formula, variables}).",
                                                },
                                                "FALLBACK": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Fallback alternate state handler (literal or {formula, variables}).",
                                                },
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
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
                                        "alternate_states": {
                                            "type": "object",
                                            "description": "Alternative state handlers for UNAVAILABLE, UNKNOWN, NONE, and FALLBACK states",
                                            "properties": {
                                                "UNAVAILABLE": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Alternate state handler for UNAVAILABLE (literal or {formula, variables}).",
                                                },
                                                "UNKNOWN": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Alternate state handler for UNKNOWN (literal or {formula, variables}).",
                                                },
                                                "NONE": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Alternate state handler for NONE (literal or {formula, variables}).",
                                                },
                                                "FALLBACK": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Fallback alternate state handler (literal or {formula, variables}).",
                                                },
                                            },
                                            "additionalProperties": False,
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
                                                            "pattern": self.VARIABLE_VALUE_PATTERN,
                                                        },
                                                        {
                                                            "type": "number",
                                                        },
                                                        {
                                                            "type": "boolean",
                                                        },
                                                        {
                                                            "type": "object",
                                                            "description": "Computed variable with formula",
                                                            "properties": {
                                                                "formula": {
                                                                    "type": "string",
                                                                    "description": "Mathematical expression to evaluate for this variable",
                                                                    "minLength": 1,
                                                                },
                                                                "allow_unresolved_states": {
                                                                    "type": "boolean",
                                                                    "description": "Allow alternate states to proceed into formula evaluation (default: false)",
                                                                    "default": False,
                                                                },
                                                                "alternate_states": {
                                                                    "type": "object",
                                                                    "description": "Alternative state handlers for UNAVAILABLE, UNKNOWN, NONE, and FALLBACK states",
                                                                    "properties": {
                                                                        "UNAVAILABLE": {
                                                                            "oneOf": [
                                                                                {"type": "string", "minLength": 1},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                                {"type": "null"},
                                                                                {
                                                                                    "type": "object",
                                                                                    "properties": {
                                                                                        "formula": {
                                                                                            "type": "string",
                                                                                            "minLength": 1,
                                                                                        },
                                                                                        "variables": {
                                                                                            "type": "object",
                                                                                            "patternProperties": {
                                                                                                "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                                                                    "oneOf": [
                                                                                                        {"type": "string"},
                                                                                                        {"type": "number"},
                                                                                                        {"type": "boolean"},
                                                                                                    ]
                                                                                                }
                                                                                            },
                                                                                            "additionalProperties": False,
                                                                                        },
                                                                                    },
                                                                                    "required": ["formula"],
                                                                                    "additionalProperties": False,
                                                                                },
                                                                            ],
                                                                            "description": "Alternate state handler for UNAVAILABLE (literal or {formula, variables}).",
                                                                        },
                                                                        "UNKNOWN": {
                                                                            "oneOf": [
                                                                                {"type": "string", "minLength": 1},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                                {"type": "null"},
                                                                                {
                                                                                    "type": "object",
                                                                                    "properties": {
                                                                                        "formula": {
                                                                                            "type": "string",
                                                                                            "minLength": 1,
                                                                                        },
                                                                                        "variables": {
                                                                                            "type": "object",
                                                                                            "patternProperties": {
                                                                                                "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                                                                    "oneOf": [
                                                                                                        {"type": "string"},
                                                                                                        {"type": "number"},
                                                                                                        {"type": "boolean"},
                                                                                                    ]
                                                                                                }
                                                                                            },
                                                                                            "additionalProperties": False,
                                                                                        },
                                                                                    },
                                                                                    "required": ["formula"],
                                                                                    "additionalProperties": False,
                                                                                },
                                                                            ],
                                                                            "description": "Alternate state handler for UNKNOWN (literal or {formula, variables}).",
                                                                        },
                                                                        "NONE": {
                                                                            "oneOf": [
                                                                                {"type": "string", "minLength": 1},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                                {"type": "null"},
                                                                                {
                                                                                    "type": "object",
                                                                                    "properties": {
                                                                                        "formula": {
                                                                                            "type": "string",
                                                                                            "minLength": 1,
                                                                                        },
                                                                                        "variables": {
                                                                                            "type": "object",
                                                                                            "patternProperties": {
                                                                                                "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                                                                    "oneOf": [
                                                                                                        {"type": "string"},
                                                                                                        {"type": "number"},
                                                                                                        {"type": "boolean"},
                                                                                                    ]
                                                                                                }
                                                                                            },
                                                                                            "additionalProperties": False,
                                                                                        },
                                                                                    },
                                                                                    "required": ["formula"],
                                                                                    "additionalProperties": False,
                                                                                },
                                                                            ],
                                                                            "description": "Alternate state handler for NONE (literal or {formula, variables}).",
                                                                        },
                                                                        "FALLBACK": {
                                                                            "oneOf": [
                                                                                {"type": "string", "minLength": 1},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                                {"type": "null"},
                                                                                {
                                                                                    "type": "object",
                                                                                    "properties": {
                                                                                        "formula": {
                                                                                            "type": "string",
                                                                                            "minLength": 1,
                                                                                        },
                                                                                        "variables": {
                                                                                            "type": "object",
                                                                                            "patternProperties": {
                                                                                                "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                                                                                                    "oneOf": [
                                                                                                        {"type": "string"},
                                                                                                        {"type": "number"},
                                                                                                        {"type": "boolean"},
                                                                                                    ]
                                                                                                }
                                                                                            },
                                                                                            "additionalProperties": False,
                                                                                        },
                                                                                    },
                                                                                    "required": ["formula"],
                                                                                    "additionalProperties": False,
                                                                                },
                                                                            ],
                                                                            "description": "Fallback alternate state handler (literal or {formula, variables}).",
                                                                            "additionalProperties": False,
                                                                        },
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
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
                "alternate_states": {
                    "type": "object",
                    "description": "Alternative state handlers for UNAVAILABLE, UNKNOWN, NONE, and FALLBACK states",
                    "properties": {
                        "UNAVAILABLE": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "number"},
                                {"type": "boolean"},
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string", "minLength": 1},
                                        "variables": {
                                            "type": "object",
                                            "patternProperties": {
                                                var_pattern: {
                                                    "oneOf": [
                                                        {"type": "string"},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                    ]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                            ],
                            "description": "Alternate state handler for UNAVAILABLE (literal or {formula, variables}).",
                        },
                        "UNKNOWN": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "number"},
                                {"type": "boolean"},
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string", "minLength": 1},
                                        "variables": {
                                            "type": "object",
                                            "patternProperties": {
                                                var_pattern: {
                                                    "oneOf": [
                                                        {"type": "string"},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                    ]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                            ],
                            "description": "Alternate state handler for UNKNOWN (literal or {formula, variables}).",
                        },
                        "NONE": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "number"},
                                {"type": "boolean"},
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string", "minLength": 1},
                                        "variables": {
                                            "type": "object",
                                            "patternProperties": {
                                                var_pattern: {
                                                    "oneOf": [
                                                        {"type": "string"},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                    ]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                            ],
                            "description": "Alternate state handler for NONE (literal or {formula, variables}).",
                        },
                        "FALLBACK": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "number"},
                                {"type": "boolean"},
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string", "minLength": 1},
                                        "variables": {
                                            "type": "object",
                                            "patternProperties": {
                                                var_pattern: {
                                                    "oneOf": [
                                                        {"type": "string"},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                    ]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                            ],
                            "description": "Fallback alternate state handler (literal or {formula, variables}).",
                        },
                    },
                    "additionalProperties": False,
                },
                "variables": {
                    "type": "object",
                    "description": "Variable mappings to Home Assistant entities, collection patterns, numeric literals, or computed variables",
                    "patternProperties": {
                        var_pattern: {
                            "oneOf": [
                                {
                                    "type": "string",
                                    "description": "String literal value, entity ID, sensor key reference, or collection pattern",
                                },
                                {
                                    "type": "number",
                                    "description": "Numeric literal value",
                                },
                                {
                                    "type": "boolean",
                                    "description": "Boolean literal value",
                                },
                                {
                                    "type": "object",
                                    "description": "Computed variable with formula and optional alternate state handlers",
                                    "properties": {
                                        "formula": {
                                            "type": "string",
                                            "description": "Mathematical expression to evaluate for this variable",
                                            "minLength": 1,
                                        },
                                        "allow_unresolved_states": {
                                            "type": "boolean",
                                            "description": "Allow alternate states to proceed into formula evaluation (default: false)",
                                            "default": False,
                                        },
                                        "alternate_states": {
                                            "type": "object",
                                            "description": "Alternative state handlers for UNAVAILABLE, UNKNOWN, NONE, and FALLBACK states",
                                            "properties": {
                                                "UNAVAILABLE": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        var_pattern: {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Alternate state handler for UNAVAILABLE (literal or {formula, variables}).",
                                                },
                                                "UNKNOWN": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        var_pattern: {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Alternate state handler for UNKNOWN (literal or {formula, variables}).",
                                                },
                                                "NONE": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        var_pattern: {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Alternate state handler for NONE (literal or {formula, variables}).",
                                                },
                                                "FALLBACK": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        var_pattern: {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Fallback alternate state handler (literal or {formula, variables}).",
                                                },
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
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
        self, id_pattern: str, variable_value_pattern: str, var_pattern: str, icon_pattern: str
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
                    "device_name": {
                        "type": "string",
                        "description": "Default device name for all sensors in this set",
                    },
                    "device_manufacturer": {
                        "type": "string",
                        "description": "Default device manufacturer for all sensors in this set",
                    },
                    "device_model": {
                        "type": "string",
                        "description": "Default device model for all sensors in this set",
                    },
                    "device_sw_version": {
                        "type": "string",
                        "description": "Default device software version for all sensors in this set",
                    },
                    "device_hw_version": {
                        "type": "string",
                        "description": "Default device hardware version for all sensors in this set",
                    },
                    "suggested_area": {
                        "type": "string",
                        "description": "Default suggested area for all sensors in this set",
                    },
                    "variables": {
                        "type": "object",
                        "description": "Global variable mappings available to all sensors",
                        "patternProperties": {
                            var_pattern: {
                                "oneOf": [
                                    {
                                        "type": "string",
                                        "description": "String literal value, entity ID, sensor key reference, or collection pattern",
                                    },
                                    {
                                        "type": "number",
                                        "description": "Numeric literal value",
                                    },
                                    {
                                        "type": "boolean",
                                        "description": "Boolean literal value",
                                    },
                                    {
                                        "type": "object",
                                        "description": "Computed variable with formula and optional exception handlers",
                                        "properties": {
                                            "formula": {
                                                "type": "string",
                                                "description": "Mathematical expression to evaluate for this variable",
                                                "minLength": 1,
                                            },
                                            "allow_unresolved_states": {
                                                "type": "boolean",
                                                "description": "Allow alternate states to proceed into formula evaluation (default: false)",
                                                "default": False,
                                            },
                                            "UNAVAILABLE": {
                                                "type": "string",
                                                "description": "Exception handler for UNAVAILABLE state - formula or literal value to use when variable cannot be resolved",
                                                "minLength": 1,
                                            },
                                            "UNKNOWN": {
                                                "type": "string",
                                                "description": "Exception handler for UNKNOWN state - formula or literal value to use when variable is in unknown state",
                                                "minLength": 1,
                                            },
                                        },
                                        "required": ["formula"],
                                        "additionalProperties": False,
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
        self, id_pattern: str, variable_value_pattern: str, var_pattern: str, icon_pattern: str
    ) -> dict[str, Any]:
        """Get the definitions section for the v2.0 schema."""
        return {
            "v1_sensor": self._get_v1_sensor_definition(id_pattern, variable_value_pattern, var_pattern, icon_pattern),
            "v1_attribute": self._get_v1_attribute_definition(variable_value_pattern, var_pattern, icon_pattern),
        }

    def _get_v1_sensor_definition(
        self, id_pattern: str, variable_value_pattern: str, var_pattern: str, icon_pattern: str
    ) -> dict[str, Any]:
        """Get the sensor definition for the v2.0 schema."""
        entity_pattern = "^[a-z_]+\\.[a-z0-9_]+$"  # For entity_id field validation
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
                # Alternative state handlers grouped under alternate_states
                "alternate_states": {
                    "type": "object",
                    "description": "Alternative state handlers for UNAVAILABLE, UNKNOWN, NONE, and FALLBACK states",
                    "properties": {
                        "UNAVAILABLE": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "number"},
                                {"type": "boolean"},
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string", "minLength": 1},
                                        "variables": {
                                            "type": "object",
                                            "patternProperties": {
                                                var_pattern: {
                                                    "oneOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                            ],
                            "description": "Alternate state handler for UNAVAILABLE (literal or {formula, variables}).",
                        },
                        "UNKNOWN": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "number"},
                                {"type": "boolean"},
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string", "minLength": 1},
                                        "variables": {
                                            "type": "object",
                                            "patternProperties": {
                                                var_pattern: {
                                                    "oneOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                            ],
                            "description": "Alternate state handler for UNKNOWN (literal or {formula, variables}).",
                        },
                        "NONE": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "number"},
                                {"type": "boolean"},
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string", "minLength": 1},
                                        "variables": {
                                            "type": "object",
                                            "patternProperties": {
                                                var_pattern: {
                                                    "oneOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                            ],
                            "description": "Alternate state handler for NONE (literal or {formula, variables}).",
                        },
                        "FALLBACK": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "number"},
                                {"type": "boolean"},
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string", "minLength": 1},
                                        "variables": {
                                            "type": "object",
                                            "patternProperties": {
                                                var_pattern: {
                                                    "oneOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                            ],
                            "description": "Fallback alternate state handler (literal or {formula, variables}).",
                        },
                    },
                    "additionalProperties": False,
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
                    "description": "Variable mappings to Home Assistant entities, sensor keys, numeric literals, boolean literals, or computed variables",
                    "patternProperties": {
                        var_pattern: {
                            "oneOf": [
                                {
                                    "type": "string",
                                    "description": "String literal value, entity ID, sensor key reference, or collection pattern",
                                },
                                {
                                    "type": "number",
                                    "description": "Numeric literal value",
                                },
                                {
                                    "type": "boolean",
                                    "description": "Boolean literal value",
                                },
                                {
                                    "type": "object",
                                    "description": "Computed variable with formula and optional alternate state handlers",
                                    "properties": {
                                        "formula": {
                                            "type": "string",
                                            "description": "Mathematical expression to evaluate for this variable",
                                            "minLength": 1,
                                        },
                                        "allow_unresolved_states": {
                                            "type": "boolean",
                                            "description": "Allow alternate states to proceed into formula evaluation (default: false)",
                                            "default": False,
                                        },
                                        "alternate_states": {
                                            "type": "object",
                                            "description": "Alternative state handlers for UNAVAILABLE, UNKNOWN, NONE, and FALLBACK states",
                                            "properties": {
                                                "UNAVAILABLE": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        var_pattern: {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Alternate state handler for UNAVAILABLE (literal or {formula, variables}).",
                                                },
                                                "UNKNOWN": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        var_pattern: {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Alternate state handler for UNKNOWN (literal or {formula, variables}).",
                                                },
                                                "NONE": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        var_pattern: {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Alternate state handler for NONE (literal or {formula, variables}).",
                                                },
                                                "FALLBACK": {
                                                    "oneOf": [
                                                        {"type": "string", "minLength": 1},
                                                        {"type": "number"},
                                                        {"type": "boolean"},
                                                        {"type": "null"},
                                                        {
                                                            "type": "object",
                                                            "properties": {
                                                                "formula": {"type": "string", "minLength": 1},
                                                                "variables": {
                                                                    "type": "object",
                                                                    "patternProperties": {
                                                                        var_pattern: {
                                                                            "oneOf": [
                                                                                {"type": "string"},
                                                                                {"type": "number"},
                                                                                {"type": "boolean"},
                                                                            ]
                                                                        }
                                                                    },
                                                                    "additionalProperties": False,
                                                                },
                                                            },
                                                            "required": ["formula"],
                                                            "additionalProperties": False,
                                                        },
                                                    ],
                                                    "description": "Fallback alternate state handler (literal or {formula, variables}).",
                                                },
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
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

    def _get_v1_attribute_definition(self, variable_value_pattern: str, var_pattern: str, icon_pattern: str) -> dict[str, Any]:
        """Get the calculated attribute definition for the v2.0 schema."""
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
                        "alternate_states": {
                            "type": "object",
                            "description": "Alternative state handlers for UNAVAILABLE, UNKNOWN, NONE, and FALLBACK states",
                            "properties": {
                                "UNAVAILABLE": {
                                    "oneOf": [
                                        {"type": "string", "minLength": 1},
                                        {"type": "number"},
                                        {"type": "boolean"},
                                        {"type": "null"},
                                        {
                                            "type": "object",
                                            "properties": {
                                                "formula": {"type": "string", "minLength": 1},
                                                "variables": {
                                                    "type": "object",
                                                    "patternProperties": {
                                                        var_pattern: {
                                                            "oneOf": [
                                                                {"type": "string"},
                                                                {"type": "number"},
                                                                {"type": "boolean"},
                                                            ]
                                                        }
                                                    },
                                                    "additionalProperties": False,
                                                },
                                            },
                                            "required": ["formula"],
                                            "additionalProperties": False,
                                        },
                                    ],
                                    "description": "Alternate state handler for UNAVAILABLE (literal or {formula, variables}).",
                                },
                                "UNKNOWN": {
                                    "oneOf": [
                                        {"type": "string", "minLength": 1},
                                        {"type": "number"},
                                        {"type": "boolean"},
                                        {"type": "null"},
                                        {
                                            "type": "object",
                                            "properties": {
                                                "formula": {"type": "string", "minLength": 1},
                                                "variables": {
                                                    "type": "object",
                                                    "patternProperties": {
                                                        var_pattern: {
                                                            "oneOf": [
                                                                {"type": "string"},
                                                                {"type": "number"},
                                                                {"type": "boolean"},
                                                            ]
                                                        }
                                                    },
                                                    "additionalProperties": False,
                                                },
                                            },
                                            "required": ["formula"],
                                            "additionalProperties": False,
                                        },
                                    ],
                                    "description": "Alternate state handler for UNKNOWN (literal or {formula, variables}).",
                                },
                                "NONE": {
                                    "oneOf": [
                                        {"type": "string", "minLength": 1},
                                        {"type": "number"},
                                        {"type": "boolean"},
                                        {"type": "null"},
                                        {
                                            "type": "object",
                                            "properties": {
                                                "formula": {"type": "string", "minLength": 1},
                                                "variables": {
                                                    "type": "object",
                                                    "patternProperties": {
                                                        var_pattern: {
                                                            "oneOf": [
                                                                {"type": "string"},
                                                                {"type": "number"},
                                                                {"type": "boolean"},
                                                            ]
                                                        }
                                                    },
                                                    "additionalProperties": False,
                                                },
                                            },
                                            "required": ["formula"],
                                            "additionalProperties": False,
                                        },
                                    ],
                                    "description": "Alternate state handler for NONE (literal or {formula, variables}).",
                                },
                                "FALLBACK": {
                                    "oneOf": [
                                        {"type": "string", "minLength": 1},
                                        {"type": "number"},
                                        {"type": "boolean"},
                                        {"type": "null"},
                                        {
                                            "type": "object",
                                            "properties": {
                                                "formula": {"type": "string", "minLength": 1},
                                                "variables": {
                                                    "type": "object",
                                                    "patternProperties": {
                                                        var_pattern: {
                                                            "oneOf": [
                                                                {"type": "string"},
                                                                {"type": "number"},
                                                                {"type": "boolean"},
                                                            ]
                                                        }
                                                    },
                                                    "additionalProperties": False,
                                                },
                                            },
                                            "required": ["formula"],
                                            "additionalProperties": False,
                                        },
                                    ],
                                    "description": "Fallback alternate state handler (literal or {formula, variables}).",
                                },
                            },
                            "additionalProperties": False,
                        },
                        # Exception handlers for attribute formula
                        "UNAVAILABLE": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "number"},
                                {"type": "boolean"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string", "minLength": 1},
                                        "variables": {
                                            "type": "object",
                                            "patternProperties": {
                                                var_pattern: {
                                                    "oneOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                            ],
                            "description": "Alternate state handler for UNAVAILABLE (literal or {formula, variables}).",
                        },
                        "UNKNOWN": {
                            "oneOf": [
                                {"type": "string", "minLength": 1},
                                {"type": "number"},
                                {"type": "boolean"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "formula": {"type": "string", "minLength": 1},
                                        "variables": {
                                            "type": "object",
                                            "patternProperties": {
                                                var_pattern: {
                                                    "oneOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]
                                                }
                                            },
                                            "additionalProperties": False,
                                        },
                                    },
                                    "required": ["formula"],
                                    "additionalProperties": False,
                                },
                            ],
                            "description": "Alternate state handler for UNKNOWN (literal or {formula, variables}).",
                        },
                        "variables": {
                            "type": "object",
                            "description": "Variable mappings to Home Assistant entities, sensor keys, numeric literals, boolean literals, or computed variables",
                            "patternProperties": {
                                var_pattern: {
                                    "oneOf": [
                                        {
                                            "type": "string",
                                            "description": "String literal value, entity ID, sensor key reference, or collection pattern",
                                        },
                                        {
                                            "type": "number",
                                            "description": "Numeric literal value",
                                        },
                                        {
                                            "type": "boolean",
                                            "description": "Boolean literal value",
                                        },
                                        {
                                            "type": "object",
                                            "description": "Computed variable with formula and optional exception handlers",
                                            "properties": {
                                                "formula": {
                                                    "type": "string",
                                                    "description": "Mathematical expression to evaluate for this variable",
                                                    "minLength": 1,
                                                },
                                                "allow_unresolved_states": {
                                                    "type": "boolean",
                                                    "description": "Allow alternate states to proceed into formula evaluation (default: false)",
                                                    "default": False,
                                                },
                                                "UNAVAILABLE": {
                                                    "type": "string",
                                                    "description": "Exception handler for UNAVAILABLE state - formula or literal value to use when variable cannot be resolved",
                                                    "minLength": 1,
                                                },
                                                "UNKNOWN": {
                                                    "type": "string",
                                                    "description": "Exception handler for UNKNOWN state - formula or literal value to use when variable is in unknown state",
                                                    "minLength": 1,
                                                },
                                            },
                                            "required": ["formula"],
                                            "additionalProperties": False,
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

    def _is_datetime_function_call(self, var_value: str) -> bool:
        """Check if a variable value is a datetime function call.

        Args:
            var_value: Variable value to check

        Returns:
            True if the value is a datetime function call like now(), today(), etc.
        """
        # Import here to avoid circular imports

        # Strip whitespace
        var_value = var_value.strip()

        # Check if it matches the pattern: function_name()
        if not (var_value.endswith("()") and len(var_value) > 2):
            return False

        function_name = var_value[:-2]  # Remove the "()"

        # Check if it's one of our datetime functions
        return function_name in DATETIME_FUNCTIONS

    def _is_numeric_string(self, value: str) -> bool:
        """Check if a string represents a numeric value."""
        try:
            float(value)
            return True
        except ValueError:
            return False

    def _is_simple_string_literal(self, value: str) -> bool:
        """Check if a string is a simple literal without special characters."""
        return (
            value.isalpha()  # Pure alphabetic strings are OK
            or (value.replace("_", "").replace(" ", "").replace("-", "").isalpha())
        )  # Strings with basic separators


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
        ValidationResult with validation status and any errors
    """
    validator = SchemaValidator()
    return validator.validate_config(config_data)


def validate_global_settings_only(global_settings_data: dict[str, Any]) -> ValidationResult:
    """Validate only global settings without requiring sensors section.

    This is used by the global CRUD interface to validate global settings
    in isolation without requiring a complete sensor configuration.

    Args:
        global_settings_data: Global settings dictionary to validate

    Returns:
        ValidationResult with validation status and any errors
    """
    validator = SchemaValidator()

    if not JSONSCHEMA_AVAILABLE:
        return ValidationResult(valid=True, errors=[])

    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    # Get the schema for version 1.0
    schema = validator.schemas.get("1.0")
    if not schema:
        errors.append(
            ValidationError(message="Schema version 1.0 not found", path="version", severity=ValidationSeverity.ERROR)
        )
        return ValidationResult(valid=False, errors=errors)

    # Extract just the global_settings schema portion
    global_settings_schema = schema["properties"].get("global_settings", {})
    if not global_settings_schema:
        errors.append(
            ValidationError(
                message="Global settings schema not found", path="global_settings", severity=ValidationSeverity.ERROR
            )
        )
        return ValidationResult(valid=False, errors=errors)

    # Validate against JSON schema first
    if HAS_JSONSCHEMA:
        try:
            jsonschema.validate(global_settings_data, global_settings_schema)
        except jsonschema.ValidationError as e:
            errors.append(
                ValidationError(
                    message=str(e.message),
                    path=f"global_settings.{e.absolute_path[-1] if e.absolute_path else ''}",
                    severity=ValidationSeverity.ERROR,
                )
            )
        except Exception as e:
            errors.append(
                ValidationError(message=f"Validation error: {e!s}", path="global_settings", severity=ValidationSeverity.ERROR)
            )

    # Perform additional semantic validation using the public method
    # Pass None for sensor_keys since we're validating in isolation
    validator.validate_global_settings(global_settings_data, None, errors, warnings)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def get_schema_for_version(version: str) -> dict[str, Any] | None:
    """Get the JSON schema for a specific version.

    Args:
        version: Schema version string

    Returns:
        Schema dictionary or None if version not found
    """
    validator = SchemaValidator()
    return validator.schemas.get(version)
