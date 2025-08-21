"""Constants for metadata validation and processing."""

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    ATTR_ASSUMED_STATE,
    ATTR_DEVICE_CLASS,
    ATTR_ICON,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITY_CATEGORY,
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.helpers.entity import EntityCategory

from .shared_constants import ENGINE_BASE_RESERVED_ATTRIBUTES, LAST_VALID_CHANGED_KEY, LAST_VALID_STATE_KEY

# Metadata property names (pointing to HA constants where applicable)
METADATA_PROPERTY_UNIT_OF_MEASUREMENT = ATTR_UNIT_OF_MEASUREMENT  # HA entity attribute
METADATA_PROPERTY_DEVICE_CLASS = ATTR_DEVICE_CLASS  # HA entity property (SensorDeviceClass)
METADATA_PROPERTY_STATE_CLASS = "state_class"  # HA entity property (SensorStateClass) - no HA constant
METADATA_PROPERTY_ICON = ATTR_ICON  # HA entity property
METADATA_PROPERTY_SUGGESTED_DISPLAY_PRECISION = "suggested_display_precision"  # Custom property
METADATA_PROPERTY_ENTITY_REGISTRY_ENABLED_DEFAULT = "entity_registry_enabled_default"  # HA entity registry
METADATA_PROPERTY_ENTITY_REGISTRY_VISIBLE_DEFAULT = "entity_registry_visible_default"  # HA entity registry
METADATA_PROPERTY_ASSUMED_STATE = ATTR_ASSUMED_STATE  # HA entity property
METADATA_PROPERTY_OPTIONS = "options"  # Custom property
METADATA_PROPERTY_ENTITY_CATEGORY = CONF_ENTITY_CATEGORY  # HA entity property (EntityCategory)

# HA Constant Values (pointing to actual HA enum values)
# These ensure we're always using the correct HA values
HA_DEVICE_CLASS_POWER = SensorDeviceClass.POWER.value
HA_DEVICE_CLASS_ENERGY = SensorDeviceClass.ENERGY.value
HA_DEVICE_CLASS_TEMPERATURE = SensorDeviceClass.TEMPERATURE.value
HA_DEVICE_CLASS_HUMIDITY = SensorDeviceClass.HUMIDITY.value
HA_DEVICE_CLASS_BATTERY = SensorDeviceClass.BATTERY.value
HA_DEVICE_CLASS_MONETARY = SensorDeviceClass.MONETARY.value

HA_STATE_CLASS_MEASUREMENT = SensorStateClass.MEASUREMENT.value
HA_STATE_CLASS_TOTAL = SensorStateClass.TOTAL.value
HA_STATE_CLASS_TOTAL_INCREASING = SensorStateClass.TOTAL_INCREASING.value

HA_ENTITY_CATEGORY_CONFIG = EntityCategory.CONFIG.value
HA_ENTITY_CATEGORY_DIAGNOSTIC = EntityCategory.DIAGNOSTIC.value

# Common HA Unit Values
HA_UNIT_PERCENTAGE = PERCENTAGE
HA_UNIT_POWER_WATT = UnitOfPower.WATT
HA_UNIT_ENERGY_WATT_HOUR = UnitOfEnergy.WATT_HOUR

# HA Enum Aliases (for validation and type safety)
HA_DEVICE_CLASSES = SensorDeviceClass
HA_STATE_CLASSES = SensorStateClass
HA_ENTITY_CATEGORIES = EntityCategory

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

# Entity category values (pointing to HA EntityCategory enum values)
ENTITY_CATEGORY_CONFIG = HA_ENTITY_CATEGORY_CONFIG
ENTITY_CATEGORY_DIAGNOSTIC = HA_ENTITY_CATEGORY_DIAGNOSTIC

VALID_ENTITY_CATEGORIES = [
    ENTITY_CATEGORY_CONFIG,
    ENTITY_CATEGORY_DIAGNOSTIC,
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
        METADATA_PROPERTY_UNIT_OF_MEASUREMENT,  # Unit of measurement for the value
        METADATA_PROPERTY_SUGGESTED_DISPLAY_PRECISION,  # Number of decimal places to display
        "suggested_unit_of_measurement",  # Suggested unit for display
        METADATA_PROPERTY_ICON,  # Icon to display in the UI
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
        METADATA_PROPERTY_ENTITY_REGISTRY_ENABLED_DEFAULT,
        METADATA_PROPERTY_ENTITY_REGISTRY_VISIBLE_DEFAULT,
    }
)

# Statistics-related metadata properties
# These properties control how HA handles statistics and long-term data
STATISTICS_METADATA_PROPERTIES: frozenset[str] = frozenset(
    {
        METADATA_PROPERTY_STATE_CLASS,
        "last_reset",
    }
)

# UI-related metadata properties
# These properties control how entities appear in the Home Assistant UI
UI_METADATA_PROPERTIES: frozenset[str] = frozenset(
    {
        METADATA_PROPERTY_ENTITY_CATEGORY,
        METADATA_PROPERTY_ICON,
        METADATA_PROPERTY_SUGGESTED_DISPLAY_PRECISION,
        "suggested_unit_of_measurement",
    }
)

# Sensor behavior metadata properties
# These properties control core sensor behavior and state handling
SENSOR_BEHAVIOR_METADATA_PROPERTIES: frozenset[str] = frozenset(
    {
        METADATA_PROPERTY_DEVICE_CLASS,
        METADATA_PROPERTY_ASSUMED_STATE,
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

    # Disallow attribute names that collide with engine-managed last-valid keys
    for engine_key in (LAST_VALID_STATE_KEY, LAST_VALID_CHANGED_KEY):
        if engine_key in metadata:
            errors.append(f"Attribute name '{engine_key}' is reserved by the engine and cannot be used")

    # Disallow HA-managed extra state attribute collisions (engine reserves some base attribute names)
    for reserved in ENGINE_BASE_RESERVED_ATTRIBUTES:
        if reserved in metadata:
            errors.append(f"Attribute name '{reserved}' is reserved by the engine and cannot be used as an attribute name")

    return errors


def get_ha_device_class_value(device_class: str) -> str | None:
    """Get the HA device class enum value for a string device class.

    Args:
        device_class: Device class string to validate

    Returns:
        The validated device class string or None if invalid
    """
    try:
        return HA_DEVICE_CLASSES(device_class).value
    except ValueError:
        return None


def get_ha_state_class_value(state_class: str) -> str | None:
    """Get the HA state class enum value for a string state class.

    Args:
        state_class: State class string to validate

    Returns:
        The validated state class string or None if invalid
    """
    try:
        return HA_STATE_CLASSES(state_class).value
    except ValueError:
        return None


def get_ha_entity_category_value(entity_category: str) -> str | None:
    """Get the HA entity category enum value for a string entity category.

    Args:
        entity_category: Entity category string to validate

    Returns:
        The validated entity category string or None if invalid
    """
    try:
        return HA_ENTITY_CATEGORIES(entity_category).value
    except ValueError:
        return None


def is_valid_ha_device_class(device_class: str) -> bool:
    """Check if a device class string is a valid HA device class.

    Args:
        device_class: Device class string to validate

    Returns:
        True if the device class is valid
    """
    return get_ha_device_class_value(device_class) is not None


def is_valid_ha_state_class(state_class: str) -> bool:
    """Check if a state class string is a valid HA state class.

    Args:
        state_class: State class string to validate

    Returns:
        True if the state class is valid
    """
    return get_ha_state_class_value(state_class) is not None


def is_valid_ha_entity_category(entity_category: str) -> bool:
    """Check if an entity category string is a valid HA entity category.

    Args:
        entity_category: Entity category string to validate

    Returns:
        True if the entity category is valid
    """
    return get_ha_entity_category_value(entity_category) is not None
