"""Constants for metadata validation and processing."""

from typing import Any

# Metadata property names
METADATA_PROPERTY_UNIT_OF_MEASUREMENT = "unit_of_measurement"
METADATA_PROPERTY_DEVICE_CLASS = "device_class"
METADATA_PROPERTY_STATE_CLASS = "state_class"
METADATA_PROPERTY_ICON = "icon"
METADATA_PROPERTY_SUGGESTED_DISPLAY_PRECISION = "suggested_display_precision"
METADATA_PROPERTY_ENTITY_REGISTRY_ENABLED_DEFAULT = "entity_registry_enabled_default"
METADATA_PROPERTY_ENTITY_REGISTRY_VISIBLE_DEFAULT = "entity_registry_visible_default"
METADATA_PROPERTY_ASSUMED_STATE = "assumed_state"
METADATA_PROPERTY_OPTIONS = "options"
METADATA_PROPERTY_ENTITY_CATEGORY = "entity_category"

# Metadata handler constants
METADATA_FUNCTION_NAME = "metadata"
METADATA_HANDLER_NAME = "metadata"

# Valid metadata keys that can be accessed via metadata() function
METADATA_FUNCTION_VALID_KEYS: frozenset[str] = frozenset(
    {
        "last_changed",
        "last_updated",
        "entity_id",
        "domain",
        "object_id",
        "friendly_name",
    }
)

# Metadata function error messages
ERROR_METADATA_FUNCTION_PARAMETER_COUNT = "metadata() function requires exactly 2 parameters, got {count}"
ERROR_METADATA_INVALID_KEY = "Invalid metadata key: {key}. Valid keys: {valid_keys}"
ERROR_METADATA_HASS_NOT_AVAILABLE = "Home Assistant instance not available for metadata lookup"
ERROR_METADATA_ENTITY_NOT_FOUND = "Entity '{entity_id}' not found in Home Assistant states"
ERROR_METADATA_KEY_NOT_FOUND = "Metadata key '{key}' not found for entity '{entity_id}'"

# Metadata property types
METADATA_STRING_PROPERTIES = [
    METADATA_PROPERTY_UNIT_OF_MEASUREMENT,
    METADATA_PROPERTY_DEVICE_CLASS,
    METADATA_PROPERTY_STATE_CLASS,
    METADATA_PROPERTY_ICON,
]

METADATA_BOOLEAN_PROPERTIES = [
    METADATA_PROPERTY_ENTITY_REGISTRY_ENABLED_DEFAULT,
    METADATA_PROPERTY_ENTITY_REGISTRY_VISIBLE_DEFAULT,
    METADATA_PROPERTY_ASSUMED_STATE,
]

# Entity category values
ENTITY_CATEGORY_CONFIG = "config"
ENTITY_CATEGORY_DIAGNOSTIC = "diagnostic"
ENTITY_CATEGORY_SYSTEM = "system"

VALID_ENTITY_CATEGORIES = [
    ENTITY_CATEGORY_CONFIG,
    ENTITY_CATEGORY_DIAGNOSTIC,
    ENTITY_CATEGORY_SYSTEM,
]

# Entity-only metadata properties
# These properties should only be used on entities, not on attributes
ENTITY_ONLY_METADATA_PROPERTIES: dict[str, str] = {
    METADATA_PROPERTY_DEVICE_CLASS: "device_class defines the entity type and should not be used on attributes",
    METADATA_PROPERTY_STATE_CLASS: "state_class controls statistics handling and should only be used on entities",
    METADATA_PROPERTY_ENTITY_CATEGORY: "entity_category groups entities in the UI and should not be used on attributes",
    METADATA_PROPERTY_ENTITY_REGISTRY_ENABLED_DEFAULT: "entity_registry_enabled_default controls entity defaults and should not be used on attributes",
    METADATA_PROPERTY_ENTITY_REGISTRY_VISIBLE_DEFAULT: "entity_registry_visible_default controls entity visibility and should not be used on attributes",
    METADATA_PROPERTY_ASSUMED_STATE: "assumed_state indicates entity state assumptions and should not be used on attributes",
    "available": "available indicates entity availability and should not be used on attributes",
    "last_reset": "last_reset is for accumulating sensors and should not be used on attributes",
    "force_update": "force_update controls state machine updates and should not be used on attributes",
}

# Attribute-allowed metadata properties
# These properties can be safely used on both entities and attributes
ATTRIBUTE_ALLOWED_METADATA_PROPERTIES: frozenset[str] = frozenset(
    {
        "unit_of_measurement",  # Unit of measurement for the value
        "suggested_display_precision",  # Number of decimal places to display
        "suggested_unit_of_measurement",  # Suggested unit for display
        "icon",  # Icon to display in the UI
        "attribution",  # Data source attribution text
        # Custom properties (any property not in entity-only list is allowed)
    }
)

# All known metadata properties (for reference and validation)
ALL_KNOWN_METADATA_PROPERTIES: frozenset[str] = frozenset(
    set(ENTITY_ONLY_METADATA_PROPERTIES.keys()) | ATTRIBUTE_ALLOWED_METADATA_PROPERTIES
)

# Registry-related metadata properties
# These properties control entity registry behavior
ENTITY_REGISTRY_METADATA_PROPERTIES: frozenset[str] = frozenset(
    {
        "entity_registry_enabled_default",
        "entity_registry_visible_default",
    }
)

# Statistics-related metadata properties
# These properties control how HA handles statistics and long-term data
STATISTICS_METADATA_PROPERTIES: frozenset[str] = frozenset(
    {
        "state_class",
        "last_reset",
    }
)

# UI-related metadata properties
# These properties control how entities appear in the Home Assistant UI
UI_METADATA_PROPERTIES: frozenset[str] = frozenset(
    {
        "entity_category",
        "icon",
        "suggested_display_precision",
        "suggested_unit_of_measurement",
    }
)

# Sensor behavior metadata properties
# These properties control core sensor behavior and state handling
SENSOR_BEHAVIOR_METADATA_PROPERTIES: frozenset[str] = frozenset(
    {
        "device_class",
        "assumed_state",
        "available",
        "force_update",
    }
)

# Error messages
ERROR_METADATA_MUST_BE_DICT = "Metadata must be a dictionary"
ERROR_UNIT_MUST_BE_STRING = "unit_of_measurement must be a string"
ERROR_DEVICE_CLASS_MUST_BE_STRING = "device_class must be a string"
ERROR_STATE_CLASS_MUST_BE_STRING = "state_class must be a string"
ERROR_ICON_MUST_BE_STRING = "icon must be a string"
ERROR_SUGGESTED_DISPLAY_PRECISION_MUST_BE_INT = "suggested_display_precision must be an integer"
ERROR_ENTITY_REGISTRY_ENABLED_DEFAULT_MUST_BE_BOOL = "entity_registry_enabled_default must be a boolean"
ERROR_ENTITY_REGISTRY_VISIBLE_DEFAULT_MUST_BE_BOOL = "entity_registry_visible_default must be a boolean"
ERROR_ASSUMED_STATE_MUST_BE_BOOL = "assumed_state must be a boolean"
ERROR_OPTIONS_MUST_BE_LIST = "options must be a list"
ERROR_ENTITY_CATEGORY_INVALID = f"entity_category must be one of: {VALID_ENTITY_CATEGORIES}"

# Data structure keys
DATA_KEY_SENSOR_SETS = "sensor_sets"
DATA_KEY_GLOBAL_SETTINGS = "global_settings"

# Validation result keys
VALIDATION_RESULT_IS_VALID = "is_valid"
VALIDATION_RESULT_ERRORS = "errors"
VALIDATION_RESULT_MISSING_ENTITIES = "missing_entities"
VALIDATION_RESULT_VALID_VARIABLES = "valid_variables"
VALIDATION_RESULT_ENTITY_IDS = "entity_ids"


def is_entity_only_property(property_name: str) -> bool:
    """Check if a metadata property should only be used on entities.

    Args:
        property_name: The metadata property name to check

    Returns:
        True if the property should only be used on entities, False if it can be used on attributes
    """
    return property_name in ENTITY_ONLY_METADATA_PROPERTIES


def get_entity_only_property_reason(property_name: str) -> str | None:
    """Get the reason why a property should only be used on entities.

    Args:
        property_name: The metadata property name to check

    Returns:
        Reason string if the property is entity-only, None if it can be used on attributes
    """
    return ENTITY_ONLY_METADATA_PROPERTIES.get(property_name)


def is_attribute_allowed_property(property_name: str) -> bool:
    """Check if a metadata property can be used on attributes.

    Args:
        property_name: The metadata property name to check

    Returns:
        True if the property can be used on attributes, False if it's entity-only

    Note:
        Properties not in the entity-only list are generally allowed on attributes,
        following Home Assistant's permissive approach to state attributes.
    """
    return not is_entity_only_property(property_name)


def is_registry_property(property_name: str) -> bool:
    """Check if a metadata property affects entity registry behavior.

    Args:
        property_name: The metadata property name to check

    Returns:
        True if the property affects entity registry settings
    """
    return property_name in ENTITY_REGISTRY_METADATA_PROPERTIES


def is_statistics_property(property_name: str) -> bool:
    """Check if a metadata property affects statistics handling.

    Args:
        property_name: The metadata property name to check

    Returns:
        True if the property affects how HA handles statistics and long-term data
    """
    return property_name in STATISTICS_METADATA_PROPERTIES


def is_ui_property(property_name: str) -> bool:
    """Check if a metadata property affects UI display.

    Args:
        property_name: The metadata property name to check

    Returns:
        True if the property affects how the entity appears in the UI
    """
    return property_name in UI_METADATA_PROPERTIES


def is_sensor_behavior_property(property_name: str) -> bool:
    """Check if a metadata property affects core sensor behavior.

    Args:
        property_name: The metadata property name to check

    Returns:
        True if the property affects core sensor behavior and state handling
    """
    return property_name in SENSOR_BEHAVIOR_METADATA_PROPERTIES


def validate_attribute_metadata_properties(metadata: dict[str, Any]) -> list[str]:
    """Validate that attribute metadata doesn't contain entity-only properties.

    Args:
        metadata: Attribute metadata dictionary to validate

    Returns:
        List of validation errors for entity-only properties found in attributes
    """
    errors = []

    for property_name in metadata:
        if is_entity_only_property(property_name):
            reason = get_entity_only_property_reason(property_name)
            errors.append(f"Invalid attribute metadata property '{property_name}': {reason}")

    return errors
