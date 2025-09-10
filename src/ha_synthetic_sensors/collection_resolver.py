"""Collection function resolver for synthetic sensors.

This module provides runtime resolution of collection functions that query
Home Assistant's entity registry to find entities matching specific patterns.

Supported collection patterns:
- regex: Pattern matching against entity IDs
- device_class: Filter by device class
- label: Filter by entity labels
- area: Filter by area assignment
- attribute: Filter by attribute conditions
- state: Filter by entity state values

Each pattern can be combined with aggregation functions like sum(), avg(), count(), etc.
All patterns support OR logic using pipe (|) syntax.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er, label_registry as lr

from .condition_parser import ConditionParser
from .dynamic_query import DynamicQuery
from .exceptions import InvalidCollectionPatternError, MissingDependencyError
from .regex_helper import create_entity_reference_pattern_from_domains, create_query_type_patterns, search_case_insensitive
from .shared_constants import get_ha_domains

_LOGGER = logging.getLogger(__name__)


class CollectionResolver:
    """Resolves collection function patterns to actual entity values."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the collection resolver.

        Args:
            hass: Home Assistant instance
        """
        if hass is None:
            raise ValueError("CollectionResolver requires a valid Home Assistant instance, got None")
        self._hass = hass

        # Get registry references
        try:
            self._area_registry: ar.AreaRegistry | None = ar.async_get(hass)
            self._device_registry: dr.DeviceRegistry | None = dr.async_get(hass)
            self._entity_registry: er.EntityRegistry | None = er.async_get(hass)
        except Exception:
            self._area_registry = None
            self._device_registry = None
            self._entity_registry = None

        # Pattern for detecting entity references within collection patterns
        # Uses centralized domain cache from constants_entities
        self._entity_reference_pattern: re.Pattern[str] | None = None

    @property
    def _entity_domains_pattern(self) -> str:
        """Get the entity domains pattern for regex compilation.

        Uses centralized domain cache from constants_entities.
        """
        return "|".join(sorted(get_ha_domains(self._hass)))

    @property
    def entity_reference_pattern(self) -> re.Pattern[str]:
        """Get the compiled entity reference pattern."""
        if self._entity_reference_pattern is None:
            # Use centralized entity reference pattern from regex helper

            self._entity_reference_pattern = create_entity_reference_pattern_from_domains(self._entity_domains_pattern)
        return self._entity_reference_pattern

    def invalidate_domain_cache(self) -> None:
        """Invalidate the cached domain pattern.

        This method is kept for backward compatibility but now delegates
        to the centralized cache invalidation system.
        """
        # Clear local pattern cache
        self._entity_reference_pattern = None

        # Note: The centralized domain cache is managed by constants_entities
        # and will be invalidated by the registry listener when needed

    def resolve_collection(self, query: DynamicQuery, exclude_entity_ids: set[str] | None = None) -> list[str]:
        """Resolve a collection query to a list of entity IDs.

        Args:
            query: Dynamic query object containing pattern and exclusions
            exclude_entity_ids: Additional entity IDs to exclude (for auto self-exclusion)

        Returns:
            List of entity IDs that match the query criteria (after exclusions)
        """
        _LOGGER.debug("Resolving collection query: %s:%s (function: %s)", query.query_type, query.pattern, query.function)

        # Resolve the main pattern first
        resolved_pattern = self._resolve_entity_references_in_pattern(query.pattern)
        _LOGGER.debug("Pattern after entity resolution: %s", resolved_pattern)

        # Use dispatch pattern to reduce complexity
        results = self._dispatch_query_resolution(query.query_type, resolved_pattern)

        # Process exclusions from the query
        query_exclusions = set()
        if query.exclusions:
            for exclusion_pattern in query.exclusions:
                excluded_entities = self._resolve_exclusion_pattern(exclusion_pattern)
                query_exclusions.update(excluded_entities)
                _LOGGER.debug("Exclusion pattern '%s' resolved to: %s", exclusion_pattern, excluded_entities)

        # Combine all exclusions
        all_exclusions = set()
        if exclude_entity_ids:
            all_exclusions.update(exclude_entity_ids)
        if query_exclusions:
            all_exclusions.update(query_exclusions)

        # Apply exclusions if specified, but only for entities that are actually in the results
        if all_exclusions:
            # Only exclude entities that are actually in the results
            entities_to_exclude = all_exclusions & set(results)
            if entities_to_exclude:
                results = [entity_id for entity_id in results if entity_id not in entities_to_exclude]
                _LOGGER.debug("Excluded %d entities from collection: %s", len(entities_to_exclude), entities_to_exclude)

        return results

    def _resolve_exclusion_pattern(self, exclusion_pattern: str) -> set[str]:
        """Resolve an exclusion pattern to a set of entity IDs.

        Args:
            exclusion_pattern: Pattern like 'area:kitchen' or 'sensor.specific_sensor'

        Returns:
            Set of entity IDs that match the exclusion pattern
        """
        # Check if it's a direct entity ID
        if "." in exclusion_pattern and ":" not in exclusion_pattern:
            # Direct entity ID reference
            return {exclusion_pattern}

        # Use centralized query type patterns from regex helper

        # Check if it's a query pattern (type:value)
        query_patterns = create_query_type_patterns()
        for query_type, pattern_regex in query_patterns.items():
            match = pattern_regex.match(exclusion_pattern)
            if match:
                resolved_pattern = self._resolve_entity_references_in_pattern(match.group(1).strip())
                excluded_entities = self._dispatch_query_resolution(query_type, resolved_pattern)
                return set(excluded_entities)

        # If no pattern matches, treat as direct entity reference
        return {exclusion_pattern}

    def _dispatch_query_resolution(self, query_type: str, resolved_pattern: str) -> list[str]:
        """Dispatch query resolution to appropriate handler.

        Args:
            query_type: Type of query to resolve
            resolved_pattern: Pattern with entity references resolved

        Returns:
            List of entity IDs that match the query criteria
        """
        # Dispatch table for query resolution
        resolvers = {
            "regex": self._resolve_regex_pattern,
            "device_class": self._resolve_device_class_pattern,
            "label": self._resolve_label_pattern,
            "area": self._resolve_area_pattern,
            "attribute": self._resolve_attribute_pattern,
            "state": self._resolve_state_pattern,
        }

        resolver = resolvers.get(query_type)
        if resolver:
            return resolver(resolved_pattern)

        # Unknown collection query type - this is a configuration error
        _LOGGER.error("Unknown collection query type: %s", query_type)
        return []

    def _resolve_entity_references_in_pattern(self, pattern: str) -> str:
        """Resolve entity references within a collection pattern.

        Args:
            pattern: Pattern that may contain entity references

        Returns:
            Pattern with entity references resolved to their current values
        """
        if not self._entity_registry:
            return pattern

        def replace_entity_ref(match: re.Match[str]) -> str:
            entity_id = match.group(0)
            try:
                if self._entity_registry is not None:
                    entity_entry = self._entity_registry.async_get(entity_id)
                    if entity_entry is not None and hasattr(entity_entry, "state") and entity_entry.state is not None:
                        return str(entity_entry.state.state)
            except Exception as e:
                raise MissingDependencyError(entity_id) from e
            return entity_id

        return self.entity_reference_pattern.sub(replace_entity_ref, pattern)

    def _resolve_regex_pattern(self, pattern: str) -> list[str]:
        """Resolve a regex pattern to matching entity IDs.

        Args:
            pattern: Regex pattern to match against entity IDs (supports OR logic with | separator)

        Returns:
            List of entity IDs that match the pattern
        """
        if not self._entity_registry:
            return []

        # Parse multiple regex patterns separated by '|'
        # Note: We need to be careful here since | is also regex OR syntax
        # We'll split on | but then treat each part as a separate complete regex
        regex_patterns = [regex_pattern.strip() for regex_pattern in pattern.split("|")]
        matching_entities = []

        # Use centralized case-insensitive pattern creation from regex helper

        for regex_pattern in regex_patterns:
            try:
                for entity_id in self._entity_registry.entities:
                    if (
                        search_case_insensitive(entity_id, regex_pattern) and entity_id not in matching_entities
                    ):  # Avoid duplicates
                        matching_entities.append(entity_id)

            except re.error as e:
                _LOGGER.error("Invalid regex pattern '%s': %s", regex_pattern, e)
                raise InvalidCollectionPatternError(regex_pattern, f"Invalid regex pattern: {e}") from e

        _LOGGER.debug("Regex pattern '%s' matched %d entities", pattern, len(matching_entities))
        return matching_entities

    def _resolve_device_class_pattern(self, pattern: str) -> list[str]:
        """Resolve a device class pattern to matching entity IDs.

        Supports:
        - Inclusion: "power", "energy", "temperature"
        - Exclusion: "!diagnostic", "!humidity"
        - OR logic: "power|energy", "!diagnostic|!humidity", "power|!humidity"
        - Shorthand: "power|energy" (second pattern without device_class: prefix)

        Args:
            pattern: Device class pattern to match (supports OR logic with | separator and ! negation)

        Returns:
            List of entity IDs that match the device class
        """
        if not self._entity_registry:
            return []

        # Parse multiple device class patterns separated by '|' (removed comma AND logic)
        device_class_patterns = [dc_pattern.strip() for dc_pattern in pattern.split("|")]
        matching_entities = []

        for device_class_pattern in device_class_patterns:
            device_class_pattern = device_class_pattern.strip()

            # Check for negation
            is_negation = device_class_pattern.startswith("!")
            target_device_class = device_class_pattern[1:].strip().lower() if is_negation else device_class_pattern.lower()

            for entity_id, _entity_entry in self._entity_registry.entities.items():
                entity_device_class = getattr(_entity_entry, "device_class", None)
                if entity_device_class:
                    entity_device_class = entity_device_class.lower()

                    # Include/exclude based on pattern
                    if is_negation:
                        # Exclude entities with this device class
                        if entity_device_class != target_device_class and entity_id not in matching_entities:
                            matching_entities.append(entity_id)
                    else:
                        # Include entities with this device class
                        if entity_device_class == target_device_class and entity_id not in matching_entities:
                            matching_entities.append(entity_id)

        _LOGGER.debug("Device class pattern '%s' matched %d entities", pattern, len(matching_entities))
        return matching_entities

    def _resolve_label_pattern(self, pattern: str) -> list[str]:
        """Resolve a label pattern to matching entity IDs.

        Supports:
        - Inclusion: "critical", "important"
        - Exclusion: "!deprecated", "!test"
        - OR logic: "critical|important", "!deprecated|!test", "critical|!test"

        Args:
            pattern: Label pattern to match (supports OR logic with | separator and ! negation)

        Returns:
            List of entity IDs that match the labels
        """
        if not self._entity_registry:
            return []

        # Get label registry for label name resolution
        label_registry = self._get_label_registry()

        # Parse multiple label patterns separated by '|'
        label_patterns = [label_pattern.strip() for label_pattern in pattern.split("|")]
        matching_entities: list[str] = []

        for label_pattern in label_patterns:
            self._process_label_pattern(label_pattern, label_registry, matching_entities)

        _LOGGER.debug("Label pattern '%s' matched %d entities", pattern, len(matching_entities))
        return matching_entities

    def _get_label_registry(self) -> Any:
        """Get label registry for label name resolution."""
        try:
            return lr.async_get(self._hass)
        except Exception:
            return None

    def _process_label_pattern(self, label_pattern: str, label_registry: Any, matching_entities: list[str]) -> None:
        """Process a single label pattern and add matching entities.

        Args:
            label_pattern: Single label pattern to process
            label_registry: Label registry for ID resolution
            matching_entities: List to append matching entities to
        """
        label_pattern = label_pattern.strip()

        # Check for negation
        is_negation = label_pattern.startswith("!")
        target_label = label_pattern[1:].strip().lower() if is_negation else label_pattern.lower()

        if self._entity_registry is None:
            return

        for entity_id, entity_entry in self._entity_registry.entities.items():
            entity_labels = self._extract_entity_labels(entity_entry, label_registry)

            if self._entity_matches_label_pattern(target_label, entity_labels, is_negation, entity_id, matching_entities):
                matching_entities.append(entity_id)

    def _extract_entity_labels(self, entity_entry: Any, label_registry: Any) -> set[str]:
        """Extract labels from an entity entry.

        Args:
            entity_entry: Entity registry entry
            label_registry: Label registry for ID resolution

        Returns:
            Set of lowercase label names
        """
        entity_labels: set[str] = set()

        # Check if entity has labels
        if not (hasattr(entity_entry, "labels") and entity_entry.labels):
            return entity_labels

        # Handle test fixtures where labels are already strings
        if isinstance(entity_entry.labels, list | tuple):
            entity_labels = {label.lower() for label in entity_entry.labels if isinstance(label, str)}
        # Handle real HA where labels are label IDs that need resolution
        elif label_registry and hasattr(entity_entry.labels, "__iter__") and not callable(entity_entry.labels):
            for label_id in entity_entry.labels:
                label_entry = label_registry.async_get_label(label_id)
                if label_entry and label_entry.name:
                    entity_labels.add(label_entry.name.lower())

        return entity_labels

    def _entity_matches_label_pattern(
        self, target_label: str, entity_labels: set[str], is_negation: bool, entity_id: str, matching_entities: list[str]
    ) -> bool:
        """Check if entity matches the label pattern.

        Args:
            target_label: Target label to match/exclude
            entity_labels: Set of entity's labels
            is_negation: Whether this is a negation pattern
            entity_id: Entity ID being checked
            matching_entities: List of already matched entities

        Returns:
            True if entity should be added to matching list
        """
        if entity_id in matching_entities:
            return False

        if is_negation:
            # Exclude entities with this label
            return target_label not in entity_labels

        # Include entities with this label
        return target_label in entity_labels

    def _resolve_area_pattern(self, pattern: str) -> list[str]:
        """Resolve an area pattern to matching entity IDs.

        Supports:
        - Inclusion: "kitchen", "living_room"
        - Exclusion: "!garage", "!basement"
        - OR logic: "kitchen|living_room", "!garage|!basement", "kitchen|!garage"

        Args:
            pattern: Area pattern to match (supports OR logic with | separator and ! negation)

        Returns:
            List of entity IDs that match the area
        """
        if not self._entity_registry or not self._area_registry:
            return []

        # Parse multiple area patterns separated by '|' (removed comma AND logic)
        area_patterns = [area.strip() for area in pattern.split("|")]
        matching_entities: list[str] = []

        for area_pattern in area_patterns:
            self._process_area_pattern(area_pattern.strip(), matching_entities)

        _LOGGER.debug("Area pattern '%s' matched %d entities", pattern, len(matching_entities))
        return matching_entities

    def _process_area_pattern(self, area_pattern: str, matching_entities: list[str]) -> None:
        """Process a single area pattern and add matching entities.

        Args:
            area_pattern: Single area pattern to process
            matching_entities: List to append matching entities to
        """
        # Check for negation
        is_negation = area_pattern.startswith("!")
        target_area = area_pattern[1:].strip() if is_negation else area_pattern

        # Find matching area IDs for this pattern
        area_ids = self._find_matching_area_ids([target_area])
        if not area_ids:
            return

        if is_negation:
            self._add_entities_excluding_areas(area_ids, matching_entities)
        else:
            self._add_entities_from_areas(area_ids, matching_entities)

    def _add_entities_excluding_areas(
        self, excluded_area_ids: set[tuple[str, str | None]], matching_entities: list[str]
    ) -> None:
        """Add entities that are NOT in the excluded areas.

        Args:
            excluded_area_ids: Set of area IDs to exclude
            matching_entities: List to append matching entities to
        """
        if self._entity_registry is None:
            return

        for entity_id, entity_entry in self._entity_registry.entities.items():
            entity_area_id = getattr(entity_entry, "area_id", None)
            if entity_area_id not in excluded_area_ids and entity_id not in matching_entities:
                matching_entities.append(entity_id)

    def _add_entities_from_areas(self, included_area_ids: set[tuple[str, str | None]], matching_entities: list[str]) -> None:
        """Add entities from the included areas.

        Args:
            included_area_ids: Set of area IDs to include
            matching_entities: List to append matching entities to
        """
        if self._entity_registry is None:
            return

        for entity_id, entity_entry in self._entity_registry.entities.items():
            entity_area_id = getattr(entity_entry, "area_id", None)
            if not entity_area_id or entity_id in matching_entities:
                continue

            for area_id, _ in included_area_ids:
                if entity_area_id == area_id:
                    matching_entities.append(entity_id)
                    break

    def _find_matching_area_ids(self, target_areas: list[str]) -> set[tuple[str, str | None]]:
        """Find area IDs that match the target area names.

        Args:
            target_areas: List of area names to match

        Returns:
            Set of (area_id, device_id) tuples
        """
        area_ids: set[tuple[str, str | None]] = set()

        if self._area_registry is None:
            return area_ids

        for area_name in target_areas:
            # First try to find area by ID (for test fixtures)
            if area_name in self._area_registry.areas:
                area_ids.add((area_name, None))
                continue

            # Find area by name
            for area_id, area_entry in self._area_registry.areas.items():
                if area_entry.name.lower() == area_name.lower():
                    area_ids.add((area_id, None))
                    break

        return area_ids

    def _find_entities_in_areas(self, area_ids: set[tuple[str, str | None]]) -> list[str]:
        """Find entities that belong to the specified areas.

        Args:
            area_ids: Set of (area_id, device_id) tuples

        Returns:
            List of entity IDs in the specified areas
        """
        matching_entities: list[str] = []

        if self._entity_registry is None:
            return matching_entities

        for entity_id, entity_entry in self._entity_registry.entities.items():
            entity_area_id = self._get_entity_area_id(entity_entry)
            if entity_area_id:
                for area_id, _ in area_ids:
                    if entity_area_id == area_id:
                        matching_entities.append(entity_id)
                        break

        return matching_entities

    def _get_entity_area_id(self, entity_entry: er.RegistryEntry) -> str | None:
        """Get the area ID for an entity.

        Args:
            entity_entry: Entity registry entry

        Returns:
            Area ID if the entity belongs to an area, None otherwise
        """
        if entity_entry.area_id:
            return entity_entry.area_id

        # Check if entity belongs to a device in an area
        if entity_entry.device_id and self._device_registry:
            device_entry = self._device_registry.async_get(entity_entry.device_id)
            if device_entry and device_entry.area_id:
                return device_entry.area_id

        return None

    def _entity_matches_device_class_filter(self, entity_id: str, device_class_filter: str | None) -> bool:
        """Check if an entity matches a device class filter.

        Args:
            entity_id: Entity ID to check
            device_class_filter: Device class to filter by

        Returns:
            True if entity matches the filter
        """
        if not device_class_filter:
            return True

        if self._entity_registry is None:
            return False

        entity_entry = self._entity_registry.async_get(entity_id)
        if not entity_entry:
            return False

        return bool(entity_entry.device_class and entity_entry.device_class.lower() == device_class_filter.lower())

    def _resolve_attribute_pattern(self, pattern: str) -> list[str]:
        """Resolve an attribute pattern to matching entity IDs.

        Args:
            pattern: Attribute pattern to match

        Returns:
            List of entity IDs that match the attribute conditions
        """
        if not self._entity_registry:
            return []

        # Parse multiple conditions separated by '|'
        conditions = [cond.strip() for cond in pattern.split("|")]
        matching_entities: list[str] = []

        for condition in conditions:
            condition_matches = self._resolve_single_attribute_condition(condition, matching_entities)
            matching_entities.extend(condition_matches)

        # Remove duplicates while preserving order
        seen = set()
        unique_matches = []
        for entity_id in matching_entities:
            if entity_id not in seen:
                seen.add(entity_id)
                unique_matches.append(entity_id)

        _LOGGER.debug("Attribute pattern '%s' matched %d entities", pattern, len(unique_matches))
        return unique_matches

    def _resolve_single_attribute_condition(self, condition: str, existing_matches: list[str]) -> list[str]:
        """Resolve a single attribute condition.

        Args:
            condition: Single attribute condition
            existing_matches: Existing matches to avoid duplicates

        Returns:
            List of entity IDs that match the condition
        """
        parsed = self._parse_attribute_condition(condition)
        if not parsed:
            raise ValueError(f"Invalid attribute condition: {condition}")

        attribute_name, op, expected_value = parsed
        matching_entities: list[str] = []

        if self._entity_registry is None:
            return matching_entities

        for entity_id, _entity_entry in self._entity_registry.entities.items():
            if entity_id in existing_matches:
                continue

            if self._entity_matches_attribute_condition(entity_id, attribute_name, op, expected_value):
                matching_entities.append(entity_id)

        return matching_entities

    def _parse_attribute_condition(self, condition: str) -> tuple[str, str, bool | float | int | str] | None:
        """Parse an attribute condition string.

        Args:
            condition: Attribute condition string (e.g., "friendly_name == 'Living Room'")

        Returns:
            Tuple of (attribute_name, operator, expected_value) or None if invalid
        """
        parsed_condition = ConditionParser.parse_attribute_condition(condition)
        if parsed_condition is None:
            return None
        return parsed_condition["attribute"], parsed_condition["operator"], parsed_condition["value"]

    def _entity_matches_attribute_condition(
        self,
        entity_id: str,
        attribute_name: str,
        op: str,
        expected_value: bool | float | int | str,
    ) -> bool:
        """Check if an entity matches an attribute condition.

        Args:
            entity_id: Entity ID to check
            attribute_name: Name of the attribute
            op: Comparison operator
            expected_value: Expected value to compare against

        Returns:
            True if entity matches the condition
        """
        try:
            # Get entity state from HA
            state = self._hass.states.get(entity_id)
            if not state:
                return False

            # Get attribute value
            actual_value = state.attributes.get(attribute_name)
            if actual_value is None:
                return False

            # Delegate to comparison handlers (supports user types and built-in types)
            return self._compare_values(actual_value, op, expected_value)

        except Exception as e:
            raise InvalidCollectionPatternError(entity_id, f"Error checking attribute condition: {e}") from e

    def _resolve_state_pattern(self, pattern: str) -> list[str]:
        """Resolve a state pattern to matching entity IDs.

        Args:
            pattern: State pattern to match

        Returns:
            List of entity IDs that match the state conditions
        """
        if not self._entity_registry:
            return []

        # Parse multiple conditions separated by '|'
        conditions = [cond.strip() for cond in pattern.split("|")]
        matching_entities: list[str] = []

        for condition in conditions:
            condition_matches = self._resolve_single_state_condition(condition, matching_entities)
            matching_entities.extend(condition_matches)

        # Remove duplicates while preserving order
        seen = set()
        unique_matches = []
        for entity_id in matching_entities:
            if entity_id not in seen:
                seen.add(entity_id)
                unique_matches.append(entity_id)

        _LOGGER.debug("State pattern '%s' matched %d entities", pattern, len(unique_matches))
        return unique_matches

    def _resolve_single_state_condition(self, condition: str, existing_matches: list[str]) -> list[str]:
        """Resolve a single state condition.

        Args:
            condition: Single state condition
            existing_matches: Existing matches to avoid duplicates

        Returns:
            List of entity IDs that match the condition

        Raises:
            DataValidationError: If condition format is invalid
        """
        # Let DataValidationError propagate - fatal errors should not be silently converted
        op, expected_value = self._parse_state_condition(condition)
        matching_entities: list[str] = []

        if self._entity_registry is None:
            return matching_entities

        for entity_id, _entity_entry in self._entity_registry.entities.items():
            if entity_id in existing_matches:
                continue

            if self._entity_matches_state_condition(entity_id, op, expected_value):
                matching_entities.append(entity_id)

        return matching_entities

    def _parse_state_condition(self, condition: str) -> tuple[str, bool | float | int | str]:
        """Parse a state condition string into operator and expected value.

        Args:
            condition: State condition string (e.g., "== on", ">= 50", "!off")

        Returns:
            Tuple of (operator, expected_value)

        Raises:
            DataValidationError: If condition format is invalid
        """
        parsed_condition = ConditionParser.parse_state_condition(condition)
        return parsed_condition["operator"], parsed_condition["value"]

    def _entity_matches_state_condition(self, entity_id: str, op: str, expected_value: bool | float | int | str) -> bool:
        """Check if an entity matches a state condition.

        Args:
            entity_id: Entity ID to check
            op: Comparison operator
            expected_value: Expected value to compare against

        Returns:
            True if entity matches the condition
        """
        try:
            # Get entity state from HA
            state = self._hass.states.get(entity_id)
            if not state:
                return False

            # Delegate to comparison handlers (supports user types and built-in types)
            return self._compare_values(state.state, op, expected_value)

        except Exception as e:
            raise InvalidCollectionPatternError(entity_id, f"Error checking state condition: {e}") from e

    def _compare_values(self, actual: Any, op: str, expected: Any) -> bool:
        """Compare two values using the specified operator.

        Delegates to the comparison handler system which supports built-in types
        (numeric, string, boolean, datetime, version) and user-defined types.

        Args:
            actual: Actual value (any supported type)
            op: Comparison operator
            expected: Expected value (any supported type)

        Returns:
            True if comparison is true
        """
        return ConditionParser.compare_values(actual, op, expected)

    def get_entity_values(self, entity_ids: list[str]) -> list[float]:
        """Get numeric values for a list of entity IDs.

        Args:
            entity_ids: List of entity IDs

        Returns:
            List of numeric values (0.0 for non-numeric or missing entities)
        """
        if self._hass is None:
            raise ValueError("CollectionResolver cannot get entity values: Home Assistant instance is None")
        values = []
        for entity_id in entity_ids:
            try:
                state = self._hass.states.get(entity_id)
                if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    try:
                        value = float(state.state)
                        values.append(value)
                    except (ValueError, TypeError):
                        # Non-numeric state, use 0.0
                        values.append(0.0)
                else:
                    # Missing or unavailable entity, use 0.0
                    values.append(0.0)
            except Exception as e:
                raise InvalidCollectionPatternError(entity_id, f"Error getting value for entity: {e}") from e

        return values

    def get_entities_matching_patterns(self, dependencies: set[str]) -> set[str]:
        """Get all entities that match collection patterns in dependencies.

        Args:
            dependencies: Set of dependency strings

        Returns:
            Set of entity IDs that match the patterns
        """
        matching_entities = set()

        for dependency in dependencies:
            try:
                entities = self.resolve_collection_pattern(dependency)
                matching_entities.update(entities)
            except InvalidCollectionPatternError:
                # Invalid patterns should be handled gracefully - skip and continue
                _LOGGER.debug("Skipping invalid collection pattern: %s", dependency)
                continue
        return matching_entities

    def resolve_collection_pattern(self, pattern: str) -> set[str]:
        """Resolve a collection pattern to entity IDs.

        Args:
            pattern: Collection pattern string (e.g., "device_class:power", "regex:sensor.*")

        Returns:
            Set of entity IDs that match the pattern
        """
        if not pattern or not pattern.strip():
            return set()

        pattern = pattern.strip()

        # Parse pattern to extract query type and value
        if ":" not in pattern:
            raise InvalidCollectionPatternError(pattern, "Invalid collection pattern format. Expected 'type:value'")

        query_type, query_pattern = pattern.split(":", 1)
        query_type = query_type.strip()
        query_pattern = query_pattern.strip()

        # Dispatch to appropriate resolver
        try:
            entities = self._dispatch_query_resolution(query_type, query_pattern)
            return set(entities)
        except Exception as e:
            raise InvalidCollectionPatternError(pattern, f"Error resolving collection pattern: {e}") from e
