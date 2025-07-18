"""Tests for collection_resolver.py with low coverage scenarios."""

from unittest.mock import MagicMock, patch

import pytest

from ha_synthetic_sensors.collection_resolver import CollectionResolver
from ha_synthetic_sensors.exceptions import MissingDependencyError


class TestCollectionResolverCoverage:
    """Test the CollectionResolver class methods with low coverage."""

    def test_resolve_tags_pattern_no_entity_registry(self) -> None:
        """Test _resolve_tags_pattern when entity registry is not available."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Mock entity registry as None
        resolver._entity_registry = None

        result = resolver._resolve_tags_pattern("critical|important")

        assert result == []

    def test_resolve_area_pattern_no_area_registry(self) -> None:
        """Test _resolve_area_pattern when area registry is not available."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Mock area registry as None
        resolver._area_registry = None

        result = resolver._resolve_area_pattern("living_room|kitchen")

        assert result == []

    def test_resolve_area_pattern_no_entity_registry(self) -> None:
        """Test _resolve_area_pattern when entity registry is not available."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Mock entity registry as None
        resolver._entity_registry = None

        result = resolver._resolve_area_pattern("living_room|kitchen")

        assert result == []

    def test_entity_matches_device_class_filter_with_filter(self) -> None:
        """Test _entity_matches_device_class_filter with device class filter."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Mock state with device class
        mock_state = MagicMock()
        mock_state.attributes = {"device_class": "temperature"}
        hass.states.get.return_value = mock_state

        result = resolver._entity_matches_device_class_filter("sensor.test", "temperature")

        assert result is True

    def test_entity_matches_device_class_filter_no_match(self) -> None:
        """Test _entity_matches_device_class_filter when device class doesn't match."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Mock state with different device class
        mock_state = MagicMock()
        mock_state.attributes = {"device_class": "humidity"}
        hass.states.get.return_value = mock_state

        result = resolver._entity_matches_device_class_filter("sensor.test", "temperature")

        assert result is False

    def test_entity_matches_device_class_filter_no_state(self) -> None:
        """Test _entity_matches_device_class_filter when entity state doesn't exist."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Mock state as None
        hass.states.get.return_value = None

        result = resolver._entity_matches_device_class_filter("sensor.test", "temperature")

        assert result is False

    def test_entity_matches_device_class_filter_no_attributes(self) -> None:
        """Test _entity_matches_device_class_filter when state has no attributes."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Mock state without attributes
        mock_state = MagicMock()
        mock_state.attributes = {}
        hass.states.get.return_value = mock_state

        result = resolver._entity_matches_device_class_filter("sensor.test", "temperature")

        assert result is False

    def test_parse_attribute_condition_invalid_format(self) -> None:
        """Test _parse_attribute_condition with invalid condition format."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        result = resolver._parse_attribute_condition("invalid_condition")

        assert result is None

    def test_parse_attribute_condition_unsupported_operator(self) -> None:
        """Test _parse_attribute_condition with unsupported operator."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        result = resolver._parse_attribute_condition("battery_level%20")

        assert result is None

    def test_parse_state_condition_invalid_format(self) -> None:
        """Test _parse_state_condition with invalid condition format."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        result = resolver._parse_state_condition("invalid_condition")

        assert result is None

    def test_parse_state_condition_unsupported_operator(self) -> None:
        """Test _parse_state_condition with unsupported operator."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        result = resolver._parse_state_condition("state%20value")

        assert result is None

    def test_convert_value_string_complex_types(self) -> None:
        """Test _convert_value_string with complex value types."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Test boolean conversion
        result = resolver._convert_value_string("true")
        assert result is True

        result = resolver._convert_value_string("false")
        assert result is False

        # Test integer conversion
        result = resolver._convert_value_string("42")
        assert result == 42

        # Test float conversion
        result = resolver._convert_value_string("3.14")
        assert result == 3.14

        # Test string (unchanged)
        result = resolver._convert_value_string("hello")
        assert result == "hello"

    def test_convert_value_string_scientific_notation(self) -> None:
        """Test _convert_value_string with scientific notation."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        result = resolver._convert_value_string("1.23e-4")
        assert result == 1.23e-4

    def test_get_entity_area_id_device_fallback(self) -> None:
        """Test _get_entity_area_id with device fallback."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Mock entity entry without area_id but with device_id
        mock_entity_entry = MagicMock()
        mock_entity_entry.area_id = None
        mock_entity_entry.device_id = "device_123"

        # Mock device registry
        mock_device_entry = MagicMock()
        mock_device_entry.area_id = "area_456"
        resolver._device_registry = MagicMock()
        resolver._device_registry.devices.get.return_value = mock_device_entry

        result = resolver._get_entity_area_id(mock_entity_entry)

        assert result == "area_456"

    def test_get_entity_area_id_no_device_registry(self) -> None:
        """Test _get_entity_area_id when device registry is not available."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Mock entity entry without area_id but with device_id
        mock_entity_entry = MagicMock()
        mock_entity_entry.area_id = None
        mock_entity_entry.device_id = "device_123"

        # Mock device registry as None
        resolver._device_registry = None

        result = resolver._get_entity_area_id(mock_entity_entry)

        assert result is None

    def test_get_entity_area_id_device_not_found(self) -> None:
        """Test _get_entity_area_id when device is not found in registry."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Mock entity entry without area_id but with device_id
        mock_entity_entry = MagicMock()
        mock_entity_entry.area_id = None
        mock_entity_entry.device_id = "device_123"

        # Mock device registry returning None
        resolver._device_registry = MagicMock()
        resolver._device_registry.devices.get.return_value = None

        result = resolver._get_entity_area_id(mock_entity_entry)

        assert result is None

    def test_resolve_collection_pattern_unknown_type(self) -> None:
        """Test resolve_collection_pattern with unknown pattern type."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Test with unknown pattern type
        result = resolver.resolve_collection_pattern("unknown:pattern")

        assert result == set()

    def test_resolve_collection_pattern_empty_pattern(self) -> None:
        """Test resolve_collection_pattern with empty pattern."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        result = resolver.resolve_collection_pattern("")

        assert result == set()

    def test_resolve_collection_pattern_whitespace_only(self) -> None:
        """Test resolve_collection_pattern with whitespace-only pattern."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        result = resolver.resolve_collection_pattern("   ")

        assert result == set()

    def test_get_entities_matching_patterns_unknown_patterns(self) -> None:
        """Test get_entities_matching_patterns with unknown pattern types."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        dependencies = {"unknown:pattern1", "another:pattern2"}

        result = resolver.get_entities_matching_patterns(dependencies)

        assert result == set()

    def test_get_entities_matching_patterns_mixed_patterns(self) -> None:
        """Test get_entities_matching_patterns with mixed valid and invalid patterns."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Mock hass.states.get to return None for collection patterns
        def mock_states_get(entity_id: str):
            if entity_id in ["regex:sensor.*", "unknown:pattern"]:
                return None  # These don't exist as actual entities
            return MagicMock()  # Return a mock state for real entities

        hass.states.get.side_effect = mock_states_get

        dependencies = {"regex:sensor.*", "unknown:pattern", "sensor.real"}

        result = resolver.get_entities_matching_patterns(dependencies)

        # Should return the collection patterns, not the real entity
        assert result == {"regex:sensor.*", "unknown:pattern"}

    def test_resolve_entity_references_in_pattern_missing_entity(self) -> None:
        """Test _resolve_entity_references_in_pattern with missing entity."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Mock state as None (entity doesn't exist)
        hass.states.get.return_value = None

        pattern = "sensor.nonexistent + 10"

        with pytest.raises(MissingDependencyError, match="Entity reference 'sensor.nonexistent' not found"):
            resolver._resolve_entity_references_in_pattern(pattern)

    def test_resolve_regex_pattern_invalid_regex(self) -> None:
        """Test _resolve_regex_pattern with invalid regex pattern."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Mock entity_ids to return some entities
        hass.states.entity_ids.return_value = ["sensor.test1", "sensor.test2"]

        # Test with invalid regex pattern
        result = resolver._resolve_regex_pattern("[invalid")

        assert result == []

    def test_resolve_regex_pattern_mixed_valid_invalid(self) -> None:
        """Test _resolve_regex_pattern with mixed valid and invalid patterns."""
        hass = MagicMock()
        resolver = CollectionResolver(hass)

        # Mock entity_ids to return some entities
        hass.states.entity_ids.return_value = ["sensor.test1", "sensor.test2"]

        # Test with OR pattern where one is invalid
        result = resolver._resolve_regex_pattern("sensor.*|[invalid")

        # Should still match valid patterns even if one is invalid
        assert "sensor.test1" in result
        assert "sensor.test2" in result
