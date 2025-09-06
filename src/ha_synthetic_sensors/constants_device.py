"""Constants for device information and configuration."""

# Device info field names used in global settings and sensor configuration
DEVICE_INFO_FIELDS = [
    "device_identifier",
    "device_name",
    "device_manufacturer",
    "device_model",
    "device_sw_version",
    "device_hw_version",
    "suggested_area",
]

# Device info field descriptions for documentation and validation
DEVICE_INFO_FIELD_DESCRIPTIONS = {
    "device_identifier": "Unique identifier for the device",
    "device_name": "Human-readable name for the device",
    "device_manufacturer": "Manufacturer of the device",
    "device_model": "Model name/number of the device",
    "device_sw_version": "Software version running on the device",
    "device_hw_version": "Hardware version of the device",
    "suggested_area": "Suggested area for the device in Home Assistant",
}

# Device info field types for validation
DEVICE_INFO_FIELD_TYPES = {
    "device_identifier": str,
    "device_name": str,
    "device_manufacturer": str,
    "device_model": str,
    "device_sw_version": str,
    "device_hw_version": str,
    "suggested_area": str,
}

# Required device info fields (if any)
REQUIRED_DEVICE_INFO_FIELDS: set[str] = set()

# Optional device info fields
OPTIONAL_DEVICE_INFO_FIELDS: set[str] = set(DEVICE_INFO_FIELDS)

# Device info validation patterns
DEVICE_IDENTIFIER_PATTERN = r"^[a-zA-Z0-9_-]+$"
DEVICE_NAME_PATTERN = r"^[a-zA-Z0-9\s_-]+$"
DEVICE_MANUFACTURER_PATTERN = r"^[a-zA-Z0-9\s_-]+$"
DEVICE_MODEL_PATTERN = r"^[a-zA-Z0-9\s_-]+$"
DEVICE_VERSION_PATTERN = r"^[a-zA-Z0-9._-]+$"
SUGGESTED_AREA_PATTERN = r"^[a-zA-Z0-9\s_-]+$"

# Device info validation patterns mapping
DEVICE_INFO_VALIDATION_PATTERNS = {
    "device_identifier": DEVICE_IDENTIFIER_PATTERN,
    "device_name": DEVICE_NAME_PATTERN,
    "device_manufacturer": DEVICE_MANUFACTURER_PATTERN,
    "device_model": DEVICE_MODEL_PATTERN,
    "device_sw_version": DEVICE_VERSION_PATTERN,
    "device_hw_version": DEVICE_VERSION_PATTERN,
    "suggested_area": SUGGESTED_AREA_PATTERN,
}

# Error messages for device info validation
ERROR_DEVICE_INFO_INVALID_FIELD = "Invalid device info field: {field}"
ERROR_DEVICE_INFO_INVALID_VALUE = "Invalid value for device info field '{field}': {value}"
ERROR_DEVICE_INFO_MISSING_REQUIRED = "Missing required device info field: {field}"
ERROR_DEVICE_INFO_UNKNOWN_FIELD = "Unknown device info field: {field}"

# Data structure keys for device info
DATA_KEY_DEVICE_INFO = "device_info"
DATA_KEY_GLOBAL_SETTINGS = "global_settings"
DATA_KEY_SENSOR_SETS = "sensor_sets"

# Validation result keys for device info
VALIDATION_RESULT_IS_VALID = "is_valid"
VALIDATION_RESULT_ERRORS = "errors"
VALIDATION_RESULT_MISSING_FIELDS = "missing_fields"
VALIDATION_RESULT_INVALID_FIELDS = "invalid_fields"


def is_valid_device_info_field(field_name: str) -> bool:
    """Check if a field name is a valid device info field.

    Args:
        field_name: The field name to check

    Returns:
        True if the field is a valid device info field
    """
    return field_name in DEVICE_INFO_FIELDS


def is_required_device_info_field(field_name: str) -> bool:
    """Check if a device info field is required.

    Args:
        field_name: The field name to check

    Returns:
        True if the field is required
    """
    return field_name in REQUIRED_DEVICE_INFO_FIELDS


def is_optional_device_info_field(field_name: str) -> bool:
    """Check if a device info field is optional.

    Args:
        field_name: The field name to check

    Returns:
        True if the field is optional
    """
    return field_name in OPTIONAL_DEVICE_INFO_FIELDS


def get_device_info_field_type(field_name: str) -> type | None:
    """Get the expected type for a device info field.

    Args:
        field_name: The field name to check

    Returns:
        The expected type for the field, or None if field doesn't exist
    """
    return DEVICE_INFO_FIELD_TYPES.get(field_name)


def get_device_info_field_description(field_name: str) -> str | None:
    """Get the description for a device info field.

    Args:
        field_name: The field name to check

    Returns:
        The description for the field, or None if field doesn't exist
    """
    return DEVICE_INFO_FIELD_DESCRIPTIONS.get(field_name)


def get_device_info_validation_pattern(field_name: str) -> str | None:
    """Get the validation pattern for a device info field.

    Args:
        field_name: The field name to check

    Returns:
        The validation pattern for the field, or None if field doesn't exist
    """
    return DEVICE_INFO_VALIDATION_PATTERNS.get(field_name)


def validate_device_info(device_info: dict[str, str]) -> dict[str, list[str] | bool]:
    """Validate device info dictionary.

    Args:
        device_info: Device info dictionary to validate

    Returns:
        Dictionary with validation results containing errors and warnings
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Check for unknown fields
    for field_name in device_info:
        if not is_valid_device_info_field(field_name):
            errors.append(ERROR_DEVICE_INFO_UNKNOWN_FIELD.format(field=field_name))

    # Check for missing required fields
    for field_name in REQUIRED_DEVICE_INFO_FIELDS:
        if field_name not in device_info:
            errors.append(ERROR_DEVICE_INFO_MISSING_REQUIRED.format(field=field_name))

    # Validate field values
    for field_name, value in device_info.items():
        if not is_valid_device_info_field(field_name):
            continue

        # Check type
        expected_type = get_device_info_field_type(field_name)
        if expected_type and not isinstance(value, expected_type):
            errors.append(ERROR_DEVICE_INFO_INVALID_VALUE.format(field=field_name, value=value))

        # Use centralized device field validation from regex helper
        from .regex_helper import validate_device_field

        # Check pattern if available
        if not validate_device_field(field_name, str(value)):
            errors.append(ERROR_DEVICE_INFO_INVALID_VALUE.format(field=field_name, value=value))

    return {
        VALIDATION_RESULT_IS_VALID: len(errors) == 0,
        VALIDATION_RESULT_ERRORS: errors,
        "warnings": warnings,
    }
