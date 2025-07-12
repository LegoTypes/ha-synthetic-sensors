"""
Metadata handling module for synthetic sensors.

This module provides functionality for merging and managing metadata from global settings,
sensor configurations, and attribute configurations following the inheritance rules.
"""

from __future__ import annotations

import logging
from typing import Any

from .config_models import FormulaConfig, SensorConfig
from .constants_metadata import validate_attribute_metadata_properties

_LOGGER = logging.getLogger(__name__)


class MetadataHandler:
    """
    Handler for metadata merging and validation.

    Handles metadata inheritance with the following precedence:
    1. Global metadata (lowest precedence)
    2. Sensor-level metadata (overrides global)
    3. Attribute-level metadata (overrides both global and sensor)
    """

    def __init__(self) -> None:
        """Initialize the metadata handler."""
        _LOGGER.debug("Initializing MetadataHandler")

    def merge_metadata(self, global_metadata: dict[str, Any], local_metadata: dict[str, Any]) -> dict[str, Any]:
        """
        Merge global and local metadata with local taking precedence.

        Args:
            global_metadata: Metadata from global settings
            local_metadata: Metadata from sensor or attribute level

        Returns:
            Merged metadata dictionary with local overriding global
        """
        # Start with global metadata as base
        merged = global_metadata.copy()

        # Override with local metadata
        merged.update(local_metadata)

        _LOGGER.debug("Merged metadata: global=%s, local=%s, result=%s", global_metadata, local_metadata, merged)

        return merged

    def merge_sensor_metadata(self, global_metadata: dict[str, Any], sensor_config: SensorConfig) -> dict[str, Any]:
        """
        Merge global metadata with sensor-level metadata.

        Args:
            global_metadata: Metadata from global settings
            sensor_config: Sensor configuration containing metadata

        Returns:
            Merged metadata for the sensor
        """
        sensor_metadata = getattr(sensor_config, "metadata", {})
        return self.merge_metadata(global_metadata, sensor_metadata)

    def get_attribute_metadata(self, attribute_config: FormulaConfig) -> dict[str, Any]:
        """
        Get metadata for an individual attribute.

        Attributes have their own metadata and do not inherit from sensor or global metadata.

        Args:
            attribute_config: Attribute configuration containing metadata

        Returns:
            Metadata dictionary for the attribute
        """
        # Attributes get only their own metadata - no inheritance
        attribute_metadata = getattr(attribute_config, "metadata", {})
        return attribute_metadata.copy()

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
            errors.append("Metadata must be a dictionary")
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
        # Use the centralized validation function from constants_metadata
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

        # String properties
        string_properties = ["unit_of_measurement", "device_class", "state_class", "icon"]
        for prop in string_properties:
            if prop in metadata and not isinstance(metadata[prop], str):
                errors.append(f"{prop} must be a string")

        # Integer properties
        if "suggested_display_precision" in metadata and not isinstance(metadata["suggested_display_precision"], int):
            errors.append("suggested_display_precision must be an integer")

        # Boolean properties
        boolean_properties = ["entity_registry_enabled_default", "entity_registry_visible_default", "assumed_state"]
        for prop in boolean_properties:
            if prop in metadata and not isinstance(metadata[prop], bool):
                errors.append(f"{prop} must be a boolean")

        # List properties
        if "options" in metadata and not isinstance(metadata["options"], list):
            errors.append("options must be a list")

        # Enumerated properties
        if "entity_category" in metadata:
            valid_categories = ["config", "diagnostic", "system"]
            if metadata["entity_category"] not in valid_categories:
                errors.append(f"entity_category must be one of: {valid_categories}")

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
