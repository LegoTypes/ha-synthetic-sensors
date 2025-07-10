"""Metadata property constants for Home Assistant entity classification.

This module centralizes metadata property definitions and validation rules,
making them easier to maintain and update when HA adds new metadata properties
or changes validation requirements.
"""

from typing import Any

# Entity-only metadata properties
# These properties should only be used on entities, not on attributes
ENTITY_ONLY_METADATA_PROPERTIES: dict[str, str] = {
    "device_class": "device_class defines the entity type and should not be used on attributes",
    "state_class": "state_class controls statistics handling and should only be used on entities",
    "entity_category": "entity_category groups entities in the UI and should not be used on attributes",
    "entity_registry_enabled_default": "entity_registry_enabled_default controls entity defaults and should not be used on attributes",
    "entity_registry_visible_default": "entity_registry_visible_default controls entity visibility and should not be used on attributes",
    "assumed_state": "assumed_state indicates entity state assumptions and should not be used on attributes",
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


def is_entity_only_property(property_name: str) -> bool:
    """Check if a metadata property should only be used on entities.

    Args:
        property_name: The metadata property name to check

    Returns:
        True if the property should only be used on entities, False if it can be used on attributes

    Note:
        This function helps validate metadata usage to ensure entity-specific
        properties are not incorrectly applied to attributes.
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
