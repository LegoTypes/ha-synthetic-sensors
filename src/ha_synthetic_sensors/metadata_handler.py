"""Metadata handling for synthetic sensors."""

import logging
from typing import Any

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
        sensor_metadata = getattr(sensor_config, "metadata", {})
        return self.merge_metadata(global_metadata, sensor_metadata)

    def get_attribute_metadata(self, attribute_config: FormulaConfig) -> dict[str, Any]:
        """
        Get metadata for an attribute.

        Args:
            attribute_config: Attribute configuration

        Returns:
            Attribute metadata dictionary
        """
        attribute_metadata = getattr(attribute_config, "metadata", {})
        return attribute_metadata

    def validate_metadata(self, metadata: dict[str, Any], is_attribute: bool = False) -> list[str]:
        """
        Validate metadata properties.

        Args:
            metadata: Metadata dictionary to validate
            is_attribute: Whether this metadata is for an attribute (vs entity)

        Returns:
            List of validation errors (empty if valid)
        """
        errors: list[str] = []

        # Basic validation - ensure metadata is a dictionary
        if not isinstance(metadata, dict):
            errors.append(ERROR_METADATA_MUST_BE_DICT)
            return errors

        # Check for entity-only properties in attribute metadata
        if is_attribute:
            errors.extend(self._validate_attribute_metadata_restrictions(metadata))

        # Validate metadata property types
        errors.extend(self._validate_metadata_types(metadata))

        _LOGGER.debug("Validated metadata: %s, errors: %s", metadata, errors)

        return errors

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
        string_property_errors = {
            METADATA_PROPERTY_UNIT_OF_MEASUREMENT: ERROR_UNIT_MUST_BE_STRING,
            METADATA_PROPERTY_DEVICE_CLASS: ERROR_DEVICE_CLASS_MUST_BE_STRING,
            METADATA_PROPERTY_STATE_CLASS: ERROR_STATE_CLASS_MUST_BE_STRING,
            METADATA_PROPERTY_ICON: ERROR_ICON_MUST_BE_STRING,
        }

        for prop in METADATA_STRING_PROPERTIES:
            if prop in metadata and not isinstance(metadata[prop], str):
                errors.append(string_property_errors.get(prop, f"Property {prop} must be a string"))

        return errors

    def _validate_integer_properties(self, metadata: dict[str, Any]) -> list[str]:
        """Validate integer properties in metadata."""
        errors: list[str] = []
        if METADATA_PROPERTY_SUGGESTED_DISPLAY_PRECISION in metadata and not isinstance(
            metadata[METADATA_PROPERTY_SUGGESTED_DISPLAY_PRECISION], int
        ):
            errors.append(ERROR_SUGGESTED_DISPLAY_PRECISION_MUST_BE_INT)
        return errors

    def _validate_boolean_properties(self, metadata: dict[str, Any]) -> list[str]:
        """Validate boolean properties in metadata."""
        errors: list[str] = []
        boolean_property_errors = {
            METADATA_PROPERTY_ENTITY_REGISTRY_ENABLED_DEFAULT: ERROR_ENTITY_REGISTRY_ENABLED_DEFAULT_MUST_BE_BOOL,
            METADATA_PROPERTY_ENTITY_REGISTRY_VISIBLE_DEFAULT: ERROR_ENTITY_REGISTRY_VISIBLE_DEFAULT_MUST_BE_BOOL,
            METADATA_PROPERTY_ASSUMED_STATE: ERROR_ASSUMED_STATE_MUST_BE_BOOL,
        }

        for prop in METADATA_BOOLEAN_PROPERTIES:
            if prop in metadata and not isinstance(metadata[prop], bool):
                errors.append(boolean_property_errors.get(prop, f"Property {prop} must be a boolean"))

        return errors

    def _validate_list_properties(self, metadata: dict[str, Any]) -> list[str]:
        """Validate list properties in metadata."""
        errors: list[str] = []
        if METADATA_PROPERTY_OPTIONS in metadata and not isinstance(metadata[METADATA_PROPERTY_OPTIONS], list):
            errors.append(ERROR_OPTIONS_MUST_BE_LIST)
        return errors

    def _validate_enumerated_properties(self, metadata: dict[str, Any]) -> list[str]:
        """Validate enumerated properties in metadata."""
        errors: list[str] = []
        if (
            METADATA_PROPERTY_ENTITY_CATEGORY in metadata
            and metadata[METADATA_PROPERTY_ENTITY_CATEGORY] not in VALID_ENTITY_CATEGORIES
        ):
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

        _LOGGER.debug("Extracted HA sensor properties: %s", ha_properties)

        return ha_properties
