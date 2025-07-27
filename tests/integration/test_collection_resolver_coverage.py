"""Tests for collection_resolver.py with low coverage scenarios."""

from unittest.mock import MagicMock, patch

import pytest

from ha_synthetic_sensors.collection_resolver import CollectionResolver
from ha_synthetic_sensors.exceptions import MissingDependencyError, DataValidationError


class TestCollectionResolverCoverage:
    """Test the CollectionResolver class methods with low coverage."""

    def test_resolve_label_pattern_no_entity_registry(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _resolve_label_pattern when entity registry is not available."""
        resolver = CollectionResolver(mock_hass)

        # Mock entity registry as None
        resolver._entity_registry = None

        result = resolver._resolve_label_pattern("critical|important")

        assert result == []

    def test_resolve_area_pattern_no_area_registry(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _resolve_area_pattern when area registry is not available."""
        resolver = CollectionResolver(mock_hass)

        # Mock area registry as None
        resolver._area_registry = None

        result = resolver._resolve_area_pattern("living_room|kitchen")

        assert result == []

    def test_resolve_area_pattern_no_entity_registry(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _resolve_area_pattern when entity registry is not available."""
        resolver = CollectionResolver(mock_hass)

        # Mock entity registry as None
        resolver._entity_registry = None

        result = resolver._resolve_area_pattern("living_room|kitchen")

        assert result == []

    def test_entity_matches_device_class_filter_with_filter(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _entity_matches_device_class_filter with device class filter."""
        resolver = CollectionResolver(mock_hass)

        # Mock state with device class
        mock_state = MagicMock()
        mock_state.attributes = {"device_class": "temperature"}
        mock_hass.states.get.return_value = mock_state

        result = resolver._entity_matches_device_class_filter("sensor.test", "temperature")

        assert result is True

    def test_entity_matches_device_class_filter_no_match(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _entity_matches_device_class_filter when device class doesn't match."""
        resolver = CollectionResolver(mock_hass)

        # sensor.test has device_class: "temperature" in the common registry
        # Filtering for "nonexistent_device_class" should return False
        result = resolver._entity_matches_device_class_filter("sensor.test", "nonexistent_device_class")

        assert result is False

    def test_entity_matches_device_class_filter_no_state(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _entity_matches_device_class_filter when entity doesn't exist in registry."""
        resolver = CollectionResolver(mock_hass)

        # Test with entity that doesn't exist in the registry
        result = resolver._entity_matches_device_class_filter("sensor.nonexistent", "temperature")

        assert result is False

    def test_entity_matches_device_class_filter_no_attributes(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _entity_matches_device_class_filter when entity has no device_class."""
        resolver = CollectionResolver(mock_hass)

        # Test with entity that exists but has no device_class
        # We need to add an entity without device_class to the registry for this test
        mock_entity_registry.register_entity("sensor.no_device_class", "unique_id", "sensor")

        result = resolver._entity_matches_device_class_filter("sensor.no_device_class", "temperature")

        assert result is False

    def test_parse_attribute_condition_invalid_format(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _parse_attribute_condition with invalid condition format."""
        resolver = CollectionResolver(mock_hass)

        result = resolver._parse_attribute_condition("invalid_condition")

        assert result is None

    def test_parse_attribute_condition_unsupported_operator(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _parse_attribute_condition with unsupported operator."""
        resolver = CollectionResolver(mock_hass)

        result = resolver._parse_attribute_condition("battery_level%20")

        assert result is None

    def test_parse_state_condition_invalid_format(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _parse_state_condition with invalid condition format."""
        resolver = CollectionResolver(mock_hass)

        # Test operator without value
        with pytest.raises(DataValidationError):
            resolver._parse_state_condition(">=")

        # Test invalid operator characters
        with pytest.raises(DataValidationError):
            resolver._parse_state_condition("&50")

        # Test empty condition
        with pytest.raises(DataValidationError):
            resolver._parse_state_condition("")

    def test_parse_state_condition_unsupported_operator(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _parse_state_condition with unsupported operator."""
        resolver = CollectionResolver(mock_hass)

        # Test unsupported operator characters
        with pytest.raises(DataValidationError):
            resolver._parse_state_condition("state%20value")

        # Test malformed double operators
        with pytest.raises(DataValidationError):
            resolver._parse_state_condition(">>100")

    def test_clean_value_string_behavior(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _clean_value_string behavior (quote removal and whitespace)."""
        from ha_synthetic_sensors.condition_parser import ConditionParser

        # Test quote removal
        result = ConditionParser._clean_value_string('"quoted"')
        assert result == "quoted"

        result = ConditionParser._clean_value_string("'single'")
        assert result == "single"

        # Test whitespace trimming
        result = ConditionParser._clean_value_string("  spaced  ")
        assert result == "spaced"

        # Test combined quote removal and trimming
        result = ConditionParser._clean_value_string('  "quoted"  ')
        assert result == "quoted"

        # Test no change for simple strings
        result = ConditionParser._clean_value_string("hello")
        assert result == "hello"

    def test_condition_parser_with_comparison_factory(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test that ConditionParser delegates type handling to comparison factory."""
        from ha_synthetic_sensors.condition_parser import ConditionParser

        # Test that the factory handles type conversions correctly
        # Boolean comparisons
        assert ConditionParser.compare_values(True, "==", "true") is True
        assert ConditionParser.compare_values(False, "==", "false") is True

        # Numeric comparisons
        assert ConditionParser.compare_values(42, "==", "42") is True
        assert ConditionParser.compare_values(3.14, ">=", "3.0") is True

        # Scientific notation
        assert ConditionParser.compare_values(1.23e-4, "==", "0.000123") is True

    def test_get_entity_area_id_device_fallback(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _get_entity_area_id with device fallback."""
        resolver = CollectionResolver(mock_hass)

        # Mock entity entry without area_id but with device_id
        mock_entity_entry = MagicMock()
        mock_entity_entry.area_id = None
        mock_entity_entry.device_id = "device_123"

        # Mock device registry
        mock_device_entry = MagicMock()
        mock_device_entry.area_id = "area_456"
        resolver._device_registry = MagicMock()
        resolver._device_registry.async_get.return_value = mock_device_entry

        result = resolver._get_entity_area_id(mock_entity_entry)

        assert result == "area_456"

    def test_get_entity_area_id_no_device_registry(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _get_entity_area_id when device registry is not available."""
        resolver = CollectionResolver(mock_hass)

        # Mock entity entry without area_id but with device_id
        mock_entity_entry = MagicMock()
        mock_entity_entry.area_id = None
        mock_entity_entry.device_id = "device_123"

        # Mock device registry as None
        resolver._device_registry = None

        result = resolver._get_entity_area_id(mock_entity_entry)

        assert result is None

    def test_get_entity_area_id_device_not_found(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _get_entity_area_id when device is not found in registry."""
        resolver = CollectionResolver(mock_hass)

        # Mock entity entry without area_id but with device_id
        mock_entity_entry = MagicMock()
        mock_entity_entry.area_id = None
        mock_entity_entry.device_id = "device_123"

        # Mock device registry returning None
        resolver._device_registry = MagicMock()
        resolver._device_registry.async_get.return_value = None

        result = resolver._get_entity_area_id(mock_entity_entry)

        assert result is None

    def test_resolve_collection_pattern_unknown_type(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test resolve_collection_pattern with unknown pattern type."""
        resolver = CollectionResolver(mock_hass)

        # Test with unknown pattern type
        result = resolver.resolve_collection_pattern("unknown:pattern")

        assert result == set()

    def test_resolve_collection_pattern_empty_pattern(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test resolve_collection_pattern with empty pattern."""
        resolver = CollectionResolver(mock_hass)

        result = resolver.resolve_collection_pattern("")

        assert result == set()

    def test_resolve_collection_pattern_whitespace_only(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test resolve_collection_pattern with whitespace-only pattern."""
        resolver = CollectionResolver(mock_hass)

        result = resolver.resolve_collection_pattern("   ")

        assert result == set()

    def test_get_entities_matching_patterns_unknown_patterns(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test get_entities_matching_patterns with unknown pattern types."""
        resolver = CollectionResolver(mock_hass)

        dependencies = {"unknown:pattern1", "another:pattern2"}

        result = resolver.get_entities_matching_patterns(dependencies)

        assert result == set()

    def test_get_entities_matching_patterns_mixed_patterns(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test get_entities_matching_patterns with mixed valid and invalid patterns."""
        resolver = CollectionResolver(mock_hass)

        dependencies = {"regex:sensor.*", "unknown:pattern", "sensor.real"}

        result = resolver.get_entities_matching_patterns(dependencies)

        # regex:sensor.* should match multiple entities from the common registry
        # unknown:pattern should return empty (unknown query type)
        # sensor.real should return empty (invalid pattern format)
        # So result should contain entities matching the regex pattern
        assert len(result) > 0  # Should have entities matching regex:sensor.*
        # Verify some expected sensor entities are in the results
        sensor_entities = [entity for entity in result if entity.startswith("sensor.")]
        assert len(sensor_entities) > 0
