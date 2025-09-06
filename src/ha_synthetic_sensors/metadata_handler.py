"""Metadata handling for synthetic sensors."""

import logging
from typing import Any, TypeGuard

from .config_models import FormulaConfig, SensorConfig
from .constants_metadata import (
    ERROR_ASSUMED_STATE_MUST_BE_BOOL,
    ERROR_DEVICE_CLASS_MUST_BE_STRING,
    ERROR_ENTITY_CATEGORY_INVALID,
    ERROR_ENTITY_REGISTRY_ENABLED_DEFAULT_MUST_BE_BOOL,
    ERROR_ENTITY_REGISTRY_VISIBLE_DEFAULT_MUST_BE_BOOL,
    ERROR_ICON_MUST_BE_STRING,
    ERROR_METADATA_MUST_BE_DICT,
    ERROR_OPTIONS_MUST_BE_LIST,
    ERROR_STATE_CLASS_MUST_BE_STRING,
    ERROR_SUGGESTED_DISPLAY_PRECISION_MUST_BE_INT,
    ERROR_UNIT_MUST_BE_STRING,
    METADATA_BOOLEAN_PROPERTIES,
    METADATA_PROPERTY_ASSUMED_STATE,
    METADATA_PROPERTY_DEVICE_CLASS,
    METADATA_PROPERTY_ENTITY_CATEGORY,
    METADATA_PROPERTY_ENTITY_REGISTRY_ENABLED_DEFAULT,
    METADATA_PROPERTY_ENTITY_REGISTRY_VISIBLE_DEFAULT,
    METADATA_PROPERTY_ICON,
    METADATA_PROPERTY_OPTIONS,
    METADATA_PROPERTY_STATE_CLASS,
    METADATA_PROPERTY_SUGGESTED_DISPLAY_PRECISION,
    METADATA_PROPERTY_UNIT_OF_MEASUREMENT,
    METADATA_STRING_PROPERTIES,
    VALID_ENTITY_CATEGORIES,
    validate_attribute_metadata_properties,
)

_LOGGER = logging.getLogger(__name__)


class MetadataHandler:
    """Handles metadata validation and processing for synthetic sensors."""

    def __init__(self) -> None:
        """Initialize the metadata handler."""

    def is_valid_metadata_dict(self, metadata: Any) -> TypeGuard[dict[str, Any]]:
        """Type guard to check if value is a valid metadata dictionary."""
        return isinstance(metadata, dict)

    def merge_metadata(self, global_metadata: dict[str, Any], local_metadata: dict[str, Any]) -> dict[str, Any]:
        """
        Merge global and local metadata, with local metadata taking precedence.

        Args:
            global_metadata: Global metadata dictionary
            local_metadata: Local metadata dictionary

        Returns:
            Merged metadata dictionary
        """
        merged = global_metadata.copy()
        merged.update(local_metadata)
        return merged

    def merge_sensor_metadata(self, global_metadata: dict[str, Any], sensor_config: SensorConfig) -> dict[str, Any]:
        """
        Merge global metadata with sensor-specific metadata.

        Args:
            global_metadata: Global metadata dictionary
            sensor_config: Sensor configuration

        Returns:
            Merged metadata dictionary
        """
        return self.merge_metadata(global_metadata, sensor_config.metadata)

    def get_attribute_metadata(self, attribute_config: FormulaConfig) -> dict[str, Any]:
        """
        Get metadata for an attribute.

        Args:
            attribute_config: Attribute configuration

        Returns:
            Attribute metadata dictionary
        """
        return attribute_config.metadata

    def merge_attribute_metadata(self, sensor_metadata: dict[str, Any], attribute_config: FormulaConfig) -> dict[str, Any]:
        """
        Merge sensor metadata with attribute-specific metadata.

        Args:
            sensor_metadata: Sensor metadata dictionary (already merged with global)
            attribute_config: Attribute configuration

        Returns:
            Merged metadata dictionary for the attribute
        """
        return self.merge_metadata(sensor_metadata, attribute_config.metadata)

    def validate_metadata(self, metadata: Any, is_attribute: bool = False) -> list[str]:
        """
        Validate metadata properties.

        Args:
            metadata: Metadata to validate (should be a dictionary)
            is_attribute: Whether this metadata is for an attribute (vs entity)

        Returns:
            List of validation errors (empty if valid)
        """
        errors: list[str] = []

        # Basic validation - ensure metadata is a dictionary
        if not self.is_valid_metadata_dict(metadata):
            errors.append(ERROR_METADATA_MUST_BE_DICT)
            return errors

        # Check for entity-only properties in attribute metadata
        if is_attribute:
            errors.extend(self._validate_attribute_metadata_restrictions(metadata))

        # Validate metadata property types
        errors.extend(self._validate_metadata_types(metadata))

        # Debug logging removed to reduce verbosity

        return errors

    def validate_entity_metadata(self, metadata: dict[str, Any]) -> list[str]:
        """
        Validate entity metadata properties.

        Args:
            metadata: Entity metadata dictionary to validate

        Returns:
            List of validation errors (empty if valid)
        """
        return self.validate_metadata(metadata, is_attribute=False)

    def validate_attribute_metadata(self, metadata: dict[str, Any]) -> list[str]:
        """
        Validate attribute metadata properties.

        Args:
            metadata: Attribute metadata dictionary to validate

        Returns:
            List of validation errors (empty if valid)
        """
        return self.validate_metadata(metadata, is_attribute=True)

    def _validate_attribute_metadata_restrictions(self, metadata: dict[str, Any]) -> list[str]:
        """
        Validate that attribute metadata doesn't contain entity-only properties.

        Args:
            metadata: Attribute metadata to validate

        Returns:
            List of validation errors for entity-only properties found in attributes
        """
        return validate_attribute_metadata_properties(metadata)

    def _validate_metadata_types(self, metadata: dict[str, Any]) -> list[str]:
        """
        Validate metadata property types.

        Args:
            metadata: Metadata dictionary to validate

        Returns:
            List of type validation errors
        """
        errors: list[str] = []

        # Validate different property types
        errors.extend(self._validate_string_properties(metadata))
        errors.extend(self._validate_integer_properties(metadata))
        errors.extend(self._validate_boolean_properties(metadata))
        errors.extend(self._validate_list_properties(metadata))
        errors.extend(self._validate_enumerated_properties(metadata))

        return errors

    def _validate_string_properties(self, metadata: dict[str, Any]) -> list[str]:
        """Validate string properties in metadata."""
        errors: list[str] = []
        string_property_errors: dict[str, str] = {
            METADATA_PROPERTY_UNIT_OF_MEASUREMENT: ERROR_UNIT_MUST_BE_STRING,
            METADATA_PROPERTY_DEVICE_CLASS: ERROR_DEVICE_CLASS_MUST_BE_STRING,
            METADATA_PROPERTY_STATE_CLASS: ERROR_STATE_CLASS_MUST_BE_STRING,
            METADATA_PROPERTY_ICON: ERROR_ICON_MUST_BE_STRING,
        }

        for prop in METADATA_STRING_PROPERTIES:
            if prop in metadata:
                value = metadata[prop]
                if not isinstance(value, str):
                    error_message = string_property_errors.get(prop, f"Property {prop} must be a string")
                    errors.append(error_message)

        return errors

    def _validate_integer_properties(self, metadata: dict[str, Any]) -> list[str]:
        """Validate integer properties in metadata."""
        errors: list[str] = []
        if METADATA_PROPERTY_SUGGESTED_DISPLAY_PRECISION in metadata:
            value = metadata[METADATA_PROPERTY_SUGGESTED_DISPLAY_PRECISION]
            if not isinstance(value, int):
                errors.append(ERROR_SUGGESTED_DISPLAY_PRECISION_MUST_BE_INT)
        return errors

    def _validate_boolean_properties(self, metadata: dict[str, Any]) -> list[str]:
        """Validate boolean properties in metadata."""
        errors: list[str] = []
        boolean_property_errors: dict[str, str] = {
            METADATA_PROPERTY_ENTITY_REGISTRY_ENABLED_DEFAULT: ERROR_ENTITY_REGISTRY_ENABLED_DEFAULT_MUST_BE_BOOL,
            METADATA_PROPERTY_ENTITY_REGISTRY_VISIBLE_DEFAULT: ERROR_ENTITY_REGISTRY_VISIBLE_DEFAULT_MUST_BE_BOOL,
            METADATA_PROPERTY_ASSUMED_STATE: ERROR_ASSUMED_STATE_MUST_BE_BOOL,
        }

        for prop in METADATA_BOOLEAN_PROPERTIES:
            if prop in metadata:
                value = metadata[prop]
                if not isinstance(value, bool):
                    error_message = boolean_property_errors.get(prop, f"Property {prop} must be a boolean")
                    errors.append(error_message)

        return errors

    def _validate_list_properties(self, metadata: dict[str, Any]) -> list[str]:
        """Validate list properties in metadata."""
        errors: list[str] = []
        if METADATA_PROPERTY_OPTIONS in metadata:
            value = metadata[METADATA_PROPERTY_OPTIONS]
            if not isinstance(value, list):
                errors.append(ERROR_OPTIONS_MUST_BE_LIST)
            elif value:  # If list is not empty, validate all items are strings
                for item in value:
                    if not isinstance(item, str):
                        errors.append(f"All items in {METADATA_PROPERTY_OPTIONS} must be strings")
                        break
        return errors

    def _validate_enumerated_properties(self, metadata: dict[str, Any]) -> list[str]:
        """Validate enumerated properties in metadata."""
        errors: list[str] = []
        if METADATA_PROPERTY_ENTITY_CATEGORY in metadata:
            value = metadata[METADATA_PROPERTY_ENTITY_CATEGORY]
            if value not in VALID_ENTITY_CATEGORIES:
                errors.append(ERROR_ENTITY_CATEGORY_INVALID)
        return errors

    def extract_ha_sensor_properties(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """
        Extract properties that should be passed to Home Assistant sensor creation.

        Args:
            metadata: Merged metadata dictionary

        Returns:
            Dictionary of properties for HA sensor creation
        """
        # All metadata properties are passed through to HA sensors
        # This allows for extensibility without code changes
        ha_properties = metadata.copy()

        # Debug logging removed to reduce verbosity

        return ha_properties

    def filter_entity_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """
        Filter metadata to only include properties valid for entities.

        Args:
            metadata: Raw metadata dictionary

        Returns:
            Filtered metadata dictionary with only entity-valid properties
        """
        # For now, pass through all properties since we validate them elsewhere
        # This method provides a hook for future filtering if needed
        return metadata.copy()

    def filter_attribute_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """
        Filter metadata to only include properties valid for attributes.

        Args:
            metadata: Raw metadata dictionary

        Returns:
            Filtered metadata dictionary with only attribute-valid properties
        """
        filtered: dict[str, Any] = {}

        # Only include properties that are valid for attributes
        for key, value in metadata.items():
            if key in [
                METADATA_PROPERTY_UNIT_OF_MEASUREMENT,
                METADATA_PROPERTY_ICON,
                METADATA_PROPERTY_SUGGESTED_DISPLAY_PRECISION,
            ] or not key.startswith("_"):  # Allow custom properties that don't start with underscore
                filtered[key] = value

        return filtered

    def get_metadata_type_info(self, property_name: str) -> dict[str, Any]:
        """
        Get type information for a metadata property.

        Args:
            property_name: The metadata property name

        Returns:
            Dictionary with type information including expected type and validation rules
        """
        type_info: dict[str, Any] = {"property": property_name, "required": False, "description": None}

        if property_name in METADATA_STRING_PROPERTIES:
            type_info["type"] = "string"
            type_info["python_type"] = str
        elif property_name == METADATA_PROPERTY_SUGGESTED_DISPLAY_PRECISION:
            type_info["type"] = "integer"
            type_info["python_type"] = int
        elif property_name in METADATA_BOOLEAN_PROPERTIES:
            type_info["type"] = "boolean"
            type_info["python_type"] = bool
        elif property_name == METADATA_PROPERTY_OPTIONS:
            type_info["type"] = "list"
            type_info["python_type"] = list
            type_info["item_type"] = str
        elif property_name == METADATA_PROPERTY_ENTITY_CATEGORY:
            type_info["type"] = "enum"
            type_info["python_type"] = str
            type_info["valid_values"] = VALID_ENTITY_CATEGORIES
        else:
            type_info["type"] = "custom"
            type_info["python_type"] = Any

        return type_info
