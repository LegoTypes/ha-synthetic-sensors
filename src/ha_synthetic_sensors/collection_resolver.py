"""Collection function resolver for synthetic sensors.

This module provides runtime resolution of collection functions that query
Home Assistant's entity registry to find entities matching specific patterns.

Supported collection patterns:
- regex: Pattern matching against entity IDs
- device_class: Filter by device class
- tags: Filter by entity tags/labels
- area: Filter by area assignment
- attribute: Filter by attribute conditions

Each pattern can be combined with aggregation functions like sum(), avg(), count(), etc.
"""

from __future__ import annotations

import logging
import operator
import re

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)

from .dependency_parser import DynamicQuery

_LOGGER = logging.getLogger(__name__)


class CollectionResolver:
    """Resolves collection function patterns to actual entity values."""

    def __init__(self, hass: HomeAssistant):
        """Initialize collection resolver with Home Assistant instance.

        Args:
            hass: Home Assistant instance for entity registry access
        """
        self._hass = hass

        # Try to get registries, but handle cases where they might not be available (testing)
        try:
            self._entity_registry: er.EntityRegistry | None = er.async_get(hass)
            self._device_registry: dr.DeviceRegistry | None = dr.async_get(hass)
            self._area_registry: ar.AreaRegistry | None = ar.async_get(hass)
        except (AttributeError, KeyError):
            # For testing or when registries aren't fully initialized
            self._entity_registry = None
            self._device_registry = None
            self._area_registry = None

    def resolve_collection(self, query: DynamicQuery) -> list[str]:
        """Resolve a dynamic query to a list of matching entity IDs.

        Args:
            query: Dynamic query specification

        Returns:
            List of entity IDs that match the query criteria
        """
        _LOGGER.debug("Resolving collection query: %s:%s", query.query_type, query.pattern)

        if query.query_type == "regex":
            return self._resolve_regex_pattern(query.pattern)
        elif query.query_type == "device_class":
            return self._resolve_device_class_pattern(query.pattern)
        elif query.query_type == "tags":
            return self._resolve_tags_pattern(query.pattern)
        elif query.query_type == "area":
            return self._resolve_area_pattern(query.pattern)
        elif query.query_type == "attribute":
            return self._resolve_attribute_pattern(query.pattern)
        else:
            _LOGGER.warning("Unknown collection query type: %s", query.query_type)
            return []

    def _resolve_regex_pattern(self, pattern: str) -> list[str]:
        """Resolve regex pattern against entity IDs.

        Args:
            pattern: Regular expression pattern to match

        Returns:
            List of matching entity IDs
        """
        try:
            regex = re.compile(pattern)
            matching_entities: list[str] = []

            for entity_id in self._hass.states.entity_ids():
                if regex.match(entity_id):
                    matching_entities.append(entity_id)

            _LOGGER.debug("Regex pattern '%s' matched %d entities", pattern, len(matching_entities))
            return matching_entities

        except re.error as e:
            _LOGGER.error("Invalid regex pattern '%s': %s", pattern, e)
            return []

    def _resolve_device_class_pattern(self, pattern: str) -> list[str]:
        """Resolve device_class pattern.

        Args:
            pattern: Device class to match (e.g., "temperature", "power")

        Returns:
            List of matching entity IDs
        """
        matching_entities: list[str] = []
        device_classes = [cls.strip() for cls in pattern.split(",")]

        for entity_id in self._hass.states.entity_ids():
            state = self._hass.states.get(entity_id)
            if state and hasattr(state, "attributes"):
                entity_device_class = state.attributes.get("device_class")
                if entity_device_class in device_classes:
                    matching_entities.append(entity_id)

        _LOGGER.debug("Device class pattern '%s' matched %d entities", pattern, len(matching_entities))
        return matching_entities

    def _resolve_tags_pattern(self, pattern: str) -> list[str]:
        """Resolve tags/labels pattern.

        Args:
            pattern: Comma-separated list of tags to match

        Returns:
            List of matching entity IDs
        """
        matching_entities: list[str] = []

        if not self._entity_registry:
            _LOGGER.warning("Entity registry not available for tags pattern resolution")
            return matching_entities

        required_tags = {tag.strip() for tag in pattern.split(",")}

        for entity_entry in self._entity_registry.entities.values():
            entity_labels = set(entity_entry.labels) if entity_entry.labels else set()

            # Check if entity has all required tags
            if required_tags.issubset(entity_labels):
                matching_entities.append(entity_entry.entity_id)

        _LOGGER.debug("Tags pattern '%s' matched %d entities", pattern, len(matching_entities))
        return matching_entities

    def _resolve_area_pattern(self, pattern: str) -> list[str]:
        """Resolve area pattern with optional device class filter.

        Args:
            pattern: Area name or "area_name device_class:class_name"

        Returns:
            List of matching entity IDs
        """
        matching_entities: list[str] = []

        if not self._area_registry or not self._entity_registry:
            _LOGGER.warning("Area or entity registry not available for area pattern resolution")
            return matching_entities

        # Parse pattern for area and optional device class
        parts = pattern.split("device_class:")
        area_name = parts[0].strip()
        device_class_filter = parts[1].strip() if len(parts) > 1 else None

        # Find area by name
        target_area = None
        for area in self._area_registry.areas.values():
            if area.name.lower() == area_name.lower():
                target_area = area
                break

        if not target_area:
            _LOGGER.warning("Area '%s' not found", area_name)
            return []

        # Find entities in the area
        for entity_entry in self._entity_registry.entities.values():
            entity_area_id = entity_entry.area_id

            # Check device area if entity doesn't have direct area assignment
            if not entity_area_id and entity_entry.device_id and self._device_registry:
                device_entry = self._device_registry.devices.get(entity_entry.device_id)
                if device_entry:
                    entity_area_id = device_entry.area_id

            if entity_area_id == target_area.id:
                # Apply device class filter if specified
                if device_class_filter:
                    state = self._hass.states.get(entity_entry.entity_id)
                    if state and hasattr(state, "attributes"):
                        entity_device_class = state.attributes.get("device_class")
                        if entity_device_class == device_class_filter:
                            matching_entities.append(entity_entry.entity_id)
                else:
                    matching_entities.append(entity_entry.entity_id)

        _LOGGER.debug("Area pattern '%s' matched %d entities", pattern, len(matching_entities))
        return matching_entities

    def _resolve_attribute_pattern(self, pattern: str) -> list[str]:
        """Resolve attribute condition pattern.

        Args:
            pattern: Attribute condition like "battery_level<20" or "online=true"

        Returns:
            List of matching entity IDs
        """
        matching_entities: list[str] = []

        # Parse attribute condition
        for op in ["<=", ">=", "!=", "<", ">", "="]:
            if op in pattern:
                attribute_name, value_str = pattern.split(op, 1)
                attribute_name = attribute_name.strip()
                value_str = value_str.strip()

                # Convert value to appropriate type
                expected_value: bool | float | int | str
                try:
                    if value_str.lower() in ("true", "false"):
                        expected_value = value_str.lower() == "true"
                    elif "." in value_str:
                        expected_value = float(value_str)
                    else:
                        expected_value = int(value_str)
                except ValueError:
                    expected_value = value_str  # Keep as string

                # Check entities for matching attribute
                for entity_id in self._hass.states.entity_ids():
                    state = self._hass.states.get(entity_id)
                    if state and hasattr(state, "attributes"):
                        actual_value = state.attributes.get(attribute_name)

                        if actual_value is not None:
                            # Convert actual value to same type as expected
                            converted_value: bool | float | str
                            try:
                                if isinstance(expected_value, bool):
                                    converted_value = str(actual_value).lower() == "true"
                                elif isinstance(expected_value, (int, float)):
                                    converted_value = float(actual_value)
                                else:
                                    converted_value = str(actual_value)
                            except (ValueError, TypeError):
                                continue

                            # Apply comparison
                            if self._compare_values(converted_value, op, expected_value):
                                matching_entities.append(entity_id)
                break
        else:
            _LOGGER.warning("Invalid attribute pattern '%s'", pattern)

        _LOGGER.debug("Attribute pattern '%s' matched %d entities", pattern, len(matching_entities))
        return matching_entities

    def _compare_values(self, actual: bool | float | str, op: str, expected: bool | float | int | str) -> bool:
        """Compare two values using the specified operator.

        Args:
            actual: Actual value from entity
            op: Comparison operator (=, !=, <, >, <=, >=)
            expected: Expected value from pattern

        Returns:
            True if comparison matches, False otherwise
        """
        # Use operator module for type-safe comparisons
        operations = {
            "=": operator.eq,
            "!=": operator.ne,
            "<": operator.lt,
            ">": operator.gt,
            "<=": operator.le,
            ">=": operator.ge,
        }

        try:
            if op in operations:
                result = operations[op](actual, expected)
                return bool(result)
            return False
        except TypeError:
            # Type mismatch, try string comparison
            return str(actual) == str(expected) if op == "=" else False

    def get_entity_values(self, entity_ids: list[str]) -> list[float]:
        """Get numeric values for a list of entity IDs.

        Args:
            entity_ids: List of entity IDs to get values for

        Returns:
            List of numeric values, excluding unavailable/non-numeric states
        """
        values = []

        for entity_id in entity_ids:
            state = self._hass.states.get(entity_id)
            if state and state.state not in ("unknown", "unavailable", "none"):
                try:
                    value = float(state.state)
                    values.append(value)
                except (ValueError, TypeError):
                    _LOGGER.debug("Skipping non-numeric state for %s: %s", entity_id, state.state)

        _LOGGER.debug("Retrieved %d numeric values from %d entities", len(values), len(entity_ids))
        return values
