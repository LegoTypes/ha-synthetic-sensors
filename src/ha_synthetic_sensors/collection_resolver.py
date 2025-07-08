"""Collection function resolver for synthetic sensors.

This module provides runtime resolution of collection functions that query
Home Assistant's entity registry to find entities matching specific patterns.

Supported collection patterns:
- regex: Pattern matching against entity IDs
- device_class: Filter by device class
- tags: Filter by entity tags/labels
- area: Filter by area assignment
- attribute: Filter by attribute conditions
- state: Filter by entity state values

Each pattern can be combined with aggregation functions like sum(), avg(), count(), etc.
All patterns support OR logic using pipe (|) syntax.
"""

from __future__ import annotations

import logging
import operator
import re

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from .dependency_parser import DynamicQuery
from .exceptions import InvalidCollectionPatternError, MissingDependencyError

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

        # Pattern for detecting entity references within collection patterns
        entity_domains = (
            r"sensor|binary_sensor|input_number|input_boolean|input_select|input_text|switch|light|climate|"
            r"cover|fan|lock|alarm_control_panel|vacuum|media_player|camera|weather|device_tracker|person|"
            r"zone|automation|script|scene|group|timer|counter|sun"
        )
        self.entity_reference_pattern = re.compile(rf"\b(?:{entity_domains})\.[a-zA-Z0-9_.]+\b")

    def resolve_collection(self, query: DynamicQuery) -> list[str]:
        """Resolve a dynamic query to a list of matching entity IDs.

        Args:
            query: Dynamic query specification

        Returns:
            List of entity IDs that match the query criteria
        """
        _LOGGER.debug("Resolving collection query: %s:%s", query.query_type, query.pattern)

        # First, resolve any entity references within the pattern
        resolved_pattern = self._resolve_entity_references_in_pattern(query.pattern)

        _LOGGER.debug("Pattern after entity resolution: %s", resolved_pattern)

        if query.query_type == "regex":
            return self._resolve_regex_pattern(resolved_pattern)
        if query.query_type == "device_class":
            return self._resolve_device_class_pattern(resolved_pattern)
        if query.query_type == "tags":
            return self._resolve_tags_pattern(resolved_pattern)
        if query.query_type == "area":
            return self._resolve_area_pattern(resolved_pattern)
        if query.query_type == "attribute":
            return self._resolve_attribute_pattern(resolved_pattern)
        if query.query_type == "state":
            return self._resolve_state_pattern(resolved_pattern)

        # Unknown collection query type - this is a configuration error
        _LOGGER.error("Unknown collection query type: %s", query.query_type)

        raise InvalidCollectionPatternError(
            query.query_type,
            f"Query type '{query.query_type}' is not supported. Supported types are: regex, device_class, area, tags",
        )

    def _resolve_entity_references_in_pattern(self, pattern: str) -> str:
        """Resolve entity references within a collection pattern.

        This method detects entity references like 'input_select.device_type' within
        collection patterns and replaces them with their current state values.

        Args:
            pattern: Collection pattern that may contain entity references

        Returns:
            Pattern with entity references resolved to their current values
        """

        def replace_entity_ref(match: re.Match[str]) -> str:
            """Replace an entity reference with its current state value."""
            entity_id = match.group(0)
            state = self._hass.states.get(entity_id)
            if state is not None:
                _LOGGER.debug(
                    "Resolving entity reference '%s' to value '%s'",
                    entity_id,
                    state.state,
                )
                return str(state.state)

            # Entity reference not found - this is a configuration error
            _LOGGER.error("Entity reference '%s' not found - entity does not exist", entity_id)

            raise MissingDependencyError(f"Entity reference '{entity_id}' not found in collection pattern")

        # Replace all entity references in the pattern
        resolved_pattern = self.entity_reference_pattern.sub(replace_entity_ref, pattern)

        return resolved_pattern

    def _resolve_regex_pattern(self, pattern: str) -> list[str]:
        """Resolve regex pattern against entity IDs.

        Args:
            pattern: Regular expression pattern to match (supports OR with pipe |)

        Returns:
            List of matching entity IDs
        """
        matching_entities: list[str] = []

        # Split by pipe (|) for OR logic
        regex_patterns = [p.strip() for p in pattern.split("|")]

        for regex_pattern in regex_patterns:
            try:
                regex = re.compile(regex_pattern)

                for entity_id in self._hass.states.entity_ids():
                    if regex.match(entity_id) and entity_id not in matching_entities:
                        matching_entities.append(entity_id)

            except re.error as e:
                _LOGGER.error("Invalid regex pattern '%s': %s", regex_pattern, e)
                continue

        _LOGGER.debug("Regex pattern '%s' matched %d entities", pattern, len(matching_entities))
        return matching_entities

    def _resolve_device_class_pattern(self, pattern: str) -> list[str]:
        """Resolve device_class pattern.

        Args:
            pattern: Device class to match (e.g., "temperature", "power", "door|window")

        Returns:
            List of matching entity IDs
        """
        matching_entities: list[str] = []

        # Split by pipe (|) for OR logic
        device_classes = [cls.strip() for cls in pattern.split("|")]

        for entity_id in self._hass.states.entity_ids():
            state = self._hass.states.get(entity_id)
            if state and hasattr(state, "attributes"):
                entity_device_class = state.attributes.get("device_class")
                if entity_device_class in device_classes:
                    matching_entities.append(entity_id)

        _LOGGER.debug(
            "Device class pattern '%s' matched %d entities",
            pattern,
            len(matching_entities),
        )
        return matching_entities

    def _resolve_tags_pattern(self, pattern: str) -> list[str]:
        """Resolve tags/labels pattern.

        Args:
            pattern: Tags to match using OR logic (e.g., "critical|important|warning")

        Returns:
            List of matching entity IDs
        """
        matching_entities: list[str] = []

        if not self._entity_registry:
            # Entity registry not available - this is a configuration/initialization error
            _LOGGER.error("Entity registry not available for tags pattern resolution - collection will be empty")
            return matching_entities

        # Split by pipe (|) for OR logic
        target_tags = [tag.strip() for tag in pattern.split("|")]

        for entity_entry in self._entity_registry.entities.values():
            entity_labels = set(entity_entry.labels) if entity_entry.labels else set()

            # Check if entity has any of the target tags (OR logic)
            if any(tag in entity_labels for tag in target_tags):
                matching_entities.append(entity_entry.entity_id)

        _LOGGER.debug("Tags pattern '%s' matched %d entities", pattern, len(matching_entities))
        return matching_entities

    def _resolve_area_pattern(self, pattern: str) -> list[str]:
        """Resolve area pattern with OR logic support.

        Args:
            pattern: Area names using OR logic (e.g., "living_room|kitchen|dining_room")

        Returns:
            List of matching entity IDs
        """
        matching_entities: list[str] = []

        if not self._area_registry or not self._entity_registry:
            # Area or entity registry not available - this is a configuration/initialization error
            _LOGGER.error("Area or entity registry not available for area pattern resolution - collection will be empty")
            return matching_entities

        # Split by pipe (|) for OR logic
        target_areas = [area_name.strip() for area_name in pattern.split("|")]
        area_ids = self._find_matching_area_ids(target_areas)
        matching_entities = self._find_entities_in_areas(area_ids)

        _LOGGER.debug("Area pattern '%s' matched %d entities", pattern, len(matching_entities))
        return matching_entities

    def _find_matching_area_ids(self, target_areas: list[str]) -> set[tuple[str, str | None]]:
        """Find area IDs matching the target area names.

        Args:
            target_areas: List of area names to match

        Returns:
            Set of (area_id, device_class_filter) tuples
        """
        area_ids = set()
        for target_area_name in target_areas:
            # Handle device_class filter if present
            parts = target_area_name.split("device_class:")
            area_name = parts[0].strip()
            device_class_filter = parts[1].strip() if len(parts) > 1 else None

            # Find area by name
            if self._area_registry:
                for area in self._area_registry.areas.values():
                    if area.name.lower() == area_name.lower():
                        area_ids.add((area.id, device_class_filter))
                        break

        return area_ids

    def _find_entities_in_areas(self, area_ids: set[tuple[str, str | None]]) -> list[str]:
        """Find entities in the specified areas.

        Args:
            area_ids: Set of (area_id, device_class_filter) tuples

        Returns:
            List of matching entity IDs
        """
        matching_entities = []

        if self._entity_registry:
            for entity_entry in self._entity_registry.entities.values():
                entity_area_id = self._get_entity_area_id(entity_entry)

                # Check if entity is in any of the target areas
                for area_id, device_class_filter in area_ids:
                    if entity_area_id == area_id:
                        if self._entity_matches_device_class_filter(entity_entry.entity_id, device_class_filter):
                            matching_entities.append(entity_entry.entity_id)
                        break  # Avoid adding the same entity multiple times

        return matching_entities

    def _get_entity_area_id(self, entity_entry: er.RegistryEntry) -> str | None:
        """Get the area ID for an entity, checking device if needed.

        Args:
            entity_entry: Entity registry entry

        Returns:
            Area ID or None
        """
        entity_area_id: str | None = getattr(entity_entry, "area_id", None)

        # Check device area if entity doesn't have direct area assignment
        if not entity_area_id and hasattr(entity_entry, "device_id") and entity_entry.device_id and self._device_registry:
            device_entry = self._device_registry.devices.get(entity_entry.device_id)
            if device_entry:
                entity_area_id = getattr(device_entry, "area_id", None)

        return entity_area_id

    def _entity_matches_device_class_filter(self, entity_id: str, device_class_filter: str | None) -> bool:
        """Check if entity matches device class filter.

        Args:
            entity_id: Entity ID to check
            device_class_filter: Device class filter or None

        Returns:
            True if entity matches filter (or no filter specified)
        """
        if not device_class_filter:
            return True

        state = self._hass.states.get(entity_id)
        if state and hasattr(state, "attributes"):
            entity_device_class = state.attributes.get("device_class")
            return bool(entity_device_class == device_class_filter)

        return False

    def _resolve_attribute_pattern(self, pattern: str) -> list[str]:
        """Resolve attribute condition pattern with OR logic support.

        Args:
            pattern: Attribute conditions using OR logic (e.g., "battery_level<20|online=false")

        Returns:
            List of matching entity IDs
        """
        matching_entities: list[str] = []
        attribute_conditions = [condition.strip() for condition in pattern.split("|")]

        for condition in attribute_conditions:
            condition_matches = self._resolve_single_attribute_condition(condition, matching_entities)
            matching_entities.extend(condition_matches)

        _LOGGER.debug(
            "Attribute pattern '%s' matched %d entities",
            pattern,
            len(matching_entities),
        )
        return matching_entities

    def _resolve_single_attribute_condition(self, condition: str, existing_matches: list[str]) -> list[str]:
        """Resolve a single attribute condition.

        Args:
            condition: Single attribute condition (e.g., "battery_level<20")
            existing_matches: Entities already matched to avoid duplicates

        Returns:
            List of newly matching entity IDs
        """
        matches: list[str] = []

        # Parse the condition
        parsed = self._parse_attribute_condition(condition)
        if not parsed:
            # Invalid attribute condition - this is a configuration error
            _LOGGER.error("Invalid attribute condition '%s' - check syntax", condition)
            return matches

        attribute_name, op, expected_value = parsed

        # Check entities for matching attribute
        for entity_id in self._hass.states.entity_ids():
            if entity_id in existing_matches:
                continue  # Already matched by previous condition

            if self._entity_matches_attribute_condition(entity_id, attribute_name, op, expected_value):
                matches.append(entity_id)

        return matches

    def _parse_attribute_condition(self, condition: str) -> tuple[str, str, bool | float | int | str] | None:
        """Parse a single attribute condition into components.

        Args:
            condition: Attribute condition string

        Returns:
            Tuple of (attribute_name, operator, expected_value) or None if invalid
        """
        for op in ["<=", ">=", "!=", "<", ">", "="]:
            if op in condition:
                attribute_name, value_str = condition.split(op, 1)
                attribute_name = attribute_name.strip()
                value_str = value_str.strip()
                expected_value = self._convert_value_string(value_str)
                return attribute_name, op, expected_value
        return None

    def _entity_matches_attribute_condition(
        self,
        entity_id: str,
        attribute_name: str,
        op: str,
        expected_value: bool | float | int | str,
    ) -> bool:
        """Check if an entity matches an attribute condition.

        Args:
            entity_id: Entity to check
            attribute_name: Name of attribute to check
            op: Comparison operator
            expected_value: Expected value to compare against

        Returns:
            True if entity matches condition
        """
        state = self._hass.states.get(entity_id)
        if not state or not hasattr(state, "attributes"):
            return False

        actual_value = state.attributes.get(attribute_name)
        if actual_value is None:
            return False

        # Convert actual value to same type as expected
        try:
            if isinstance(expected_value, bool):
                converted_value: bool | float | str = str(actual_value).lower() == "true"
            elif isinstance(expected_value, (int, float)):
                converted_value = float(actual_value)
            else:
                converted_value = str(actual_value)
        except (ValueError, TypeError):
            return False

        return self._compare_values(converted_value, op, expected_value)

    def _convert_value_string(self, value_str: str) -> bool | float | int | str:
        """Convert a string value to appropriate type.

        Args:
            value_str: String to convert

        Returns:
            Converted value (bool, float, int, or str)
        """
        try:
            if value_str.lower() in ("true", "false"):
                return value_str.lower() == "true"
            if "." in value_str:
                return float(value_str)

            return int(value_str)
        except ValueError:
            return value_str  # Keep as string

    def _resolve_state_pattern(self, pattern: str) -> list[str]:
        """Resolve state condition pattern with OR logic support.

        Args:
            pattern: State conditions using OR logic (e.g., ">100|=on|<50")

        Returns:
            List of matching entity IDs
        """
        matching_entities: list[str] = []
        state_conditions = [condition.strip() for condition in pattern.split("|")]

        for condition in state_conditions:
            condition_matches = self._resolve_single_state_condition(condition, matching_entities)
            matching_entities.extend(condition_matches)

        _LOGGER.debug("State pattern '%s' matched %d entities", pattern, len(matching_entities))
        return matching_entities

    def _resolve_single_state_condition(self, condition: str, existing_matches: list[str]) -> list[str]:
        """Resolve a single state condition.

        Args:
            condition: Single state condition (e.g., ">100")
            existing_matches: Entities already matched to avoid duplicates

        Returns:
            List of newly matching entity IDs
        """
        matches: list[str] = []

        # Parse the condition
        parsed = self._parse_state_condition(condition)
        if not parsed:
            # Invalid state condition - this is a configuration error
            _LOGGER.error("Invalid state condition '%s' - check syntax", condition)
            return matches

        op, expected_value = parsed

        # Check entities for matching state
        for entity_id in self._hass.states.entity_ids():
            if entity_id in existing_matches:
                continue  # Already matched by previous condition

            if self._entity_matches_state_condition(entity_id, op, expected_value):
                matches.append(entity_id)

        return matches

    def _parse_state_condition(self, condition: str) -> tuple[str, bool | float | int | str] | None:
        """Parse a single state condition into components.

        Args:
            condition: State condition string

        Returns:
            Tuple of (operator, expected_value) or None if invalid
        """
        for op in ["<=", ">=", "!=", "<", ">", "="]:
            if op in condition:
                value_str = condition.replace(op, "", 1).strip()
                expected_value = self._convert_value_string(value_str)
                return op, expected_value
        return None

    def _entity_matches_state_condition(self, entity_id: str, op: str, expected_value: bool | float | int | str) -> bool:
        """Check if an entity matches a state condition.

        Args:
            entity_id: Entity to check
            op: Comparison operator
            expected_value: Expected value to compare against

        Returns:
            True if entity matches condition
        """
        state = self._hass.states.get(entity_id)
        if not state or state.state in ("unknown", "unavailable", "none"):
            return False

        # Convert actual state to same type as expected
        try:
            if isinstance(expected_value, bool):
                converted_state: bool | float | str = str(state.state).lower() == "true"
            elif isinstance(expected_value, (int, float)):
                converted_state = float(state.state)
            else:
                converted_state = str(state.state)
        except (ValueError, TypeError):
            return False

        return self._compare_values(converted_state, op, expected_value)

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
            List of numeric values (non-numeric entities are skipped)
        """
        values: list[float] = []

        for entity_id in entity_ids:
            state = self._hass.states.get(entity_id)
            if state is not None:
                try:
                    # Try to convert state to float
                    value = float(state.state)
                    values.append(value)
                except (ValueError, TypeError):
                    # Skip non-numeric entities
                    _LOGGER.debug("Skipping non-numeric entity %s with state '%s'", entity_id, state.state)
                    continue

        return values

    def get_entities_matching_patterns(self, dependencies: set[str]) -> set[str]:
        """Get entities that match collection patterns from a set of dependencies.

        Args:
            dependencies: Set of entity IDs and potential collection patterns

        Returns:
            Set of entity IDs that are collection patterns (not actual entities)
        """
        collection_patterns = set()

        for dep in dependencies:
            # Check if this looks like a collection pattern
            # Collection patterns typically don't exist as actual entities
            if not self._hass.states.get(dep) and any(
                pattern in dep for pattern in [":", "*", "regex", "device_class", "area", "tags", "attribute", "state"]
            ):
                collection_patterns.add(dep)

        return collection_patterns

    def resolve_collection_pattern(self, pattern: str) -> set[str]:
        """Resolve a collection pattern to actual entity IDs.

        Args:
            pattern: Collection pattern string

        Returns:
            Set of entity IDs that match the pattern
        """
        # This is a simplified version - in a full implementation,
        # this would parse the pattern and resolve it properly
        try:
            # For now, return empty set for patterns we can't resolve
            _LOGGER.debug("Resolving collection pattern: %s", pattern)
            return set()
        except Exception as err:
            _LOGGER.warning("Error resolving collection pattern '%s': %s", pattern, err)
            return set()
