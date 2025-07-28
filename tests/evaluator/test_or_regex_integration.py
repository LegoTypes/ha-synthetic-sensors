"""Tests for OR pattern integration with regex collection functions."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from ha_synthetic_sensors.collection_resolver import CollectionResolver
from ha_synthetic_sensors.dependency_parser import DependencyParser, DynamicQuery
from ha_synthetic_sensors.evaluator import Evaluator


@pytest.fixture
def collection_resolver(mock_hass, mock_entity_registry, mock_states):
    """Create a collection resolver instance with shared mocks."""
    from ha_synthetic_sensors.collection_resolver import CollectionResolver

    # Set up the mock hass with entity registry and states
    mock_hass.entity_registry = mock_entity_registry
    mock_hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)
    mock_hass.states.entity_ids.return_value = list(mock_states.keys())

    # Patch necessary modules
    with (
        patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
        patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
        patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
        patch("ha_synthetic_sensors.collection_resolver.ar.async_get"),
    ):
        return CollectionResolver(mock_hass)


class TestOrRegexIntegration:
    """Test OR pattern integration with regex-based entity resolution."""

    @pytest.fixture(autouse=True)
    def setup_method(self, mock_hass, mock_entity_registry, mock_states):
        """Set up test fixtures with shared mock entity registry."""
        self.mock_hass = mock_hass
        self.mock_hass.entity_registry = mock_entity_registry
        self.mock_hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)
        self.mock_hass.states.entity_ids.return_value = list(mock_states.keys())

        # Set up patchers for registry access
        self._patchers = [
            patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
            patch("ha_synthetic_sensors.collection_resolver.ar.async_get"),
        ]

        # Start all patchers
        for p in self._patchers:
            p.start()

        self.evaluator = Evaluator(self.mock_hass)
        self.resolver = CollectionResolver(self.mock_hass)

    def teardown_method(self):
        """Clean up patchers."""
        if hasattr(self, "_patchers"):
            for p in self._patchers:
                p.stop()

    def test_resolve_or_regex_pattern_integration(self, collection_resolver):
        """Test that OR regex pattern integration works correctly."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        # Test OR pattern with existing entities from shared registry
        # Pattern will match entities containing "circuit" OR "kitchen"
        query = DynamicQuery(query_type="regex", pattern="circuit.*|kitchen.*", function="count")

        # Resolve the collection using the resolver
        entities = collection_resolver.resolve_collection(query)

        # Expected entities from shared registry that match "circuit.*" or "kitchen.*"
        expected_patterns = ["circuit", "kitchen"]
        expected_entities = [
            "sensor.circuit_a_power",  # matches "circuit.*"
            "sensor.circuit_b_power",  # matches "circuit.*"
            "sensor.kitchen_temperature",  # matches "kitchen.*"
            "sensor.kitchen_temp",  # matches "kitchen.*"
            "sensor.kitchen_humidity",  # matches "kitchen.*"
        ]

        # Check that we found some entities matching the patterns
        found_entities = [entity for entity in expected_entities if entity in entities]
        assert len(entities) > 0, f"Should find entities matching circuit.* or kitchen.* patterns, got: {entities}"
        assert len(found_entities) > 0, f"Expected to find some of {expected_entities}, but found: {entities}"

    def test_resolve_three_way_or_regex_integration(self, collection_resolver):
        """Test OR pattern resolution with three regex patterns."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        # Test three-way OR pattern with existing entities from shared registry
        query = DynamicQuery(
            query_type="regex",
            pattern="bedroom.*|kitchen.*|living_room.*",
            function="count",
        )
        entities = collection_resolver.resolve_collection(query)

        # Expected entities from shared registry that match the patterns
        expected_entities = [
            "sensor.master_bedroom_temp",  # matches "bedroom.*"
            "sensor.guest_bedroom_temp",  # matches "bedroom.*"
            "sensor.kitchen_temperature",  # matches "kitchen.*"
            "sensor.kitchen_temp",  # matches "kitchen.*"
            "sensor.kitchen_humidity",  # matches "kitchen.*"
            "sensor.living_room_temp",  # matches "living_room.*"
            "sensor.living_room_humidity",  # matches "living_room.*"
            "light.living_room_main",  # matches "living_room.*"
        ]

        # Check that we found some entities matching the patterns
        found_entities = [entity for entity in expected_entities if entity in entities]
        assert len(entities) > 0, f"Should find entities matching bedroom.*|kitchen.*|living_room.* patterns, got: {entities}"
        assert len(found_entities) > 0, f"Expected to find some of {expected_entities}, but found: {entities}"

    def test_resolve_domain_or_regex_integration(self, collection_resolver):
        """Test OR pattern resolution with domain-specific regex patterns."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        # Test domain-specific OR pattern with existing entities from shared registry
        query = DynamicQuery(
            query_type="regex",
            pattern="sensor\\.circuit.*|binary_sensor\\.door.*",
            function="count",
        )
        entities = collection_resolver.resolve_collection(query)

        # Expected entities from shared registry that match the patterns
        expected_entities = [
            "sensor.circuit_a_power",  # matches "sensor\.circuit.*"
            "sensor.circuit_b_power",  # matches "sensor\.circuit.*"
            "binary_sensor.front_door",  # matches "binary_sensor\.door.*"
            "binary_sensor.back_door",  # matches "binary_sensor\.door.*"
        ]

        # Check that we found some entities matching the patterns
        found_entities = [entity for entity in expected_entities if entity in entities]
        assert len(entities) > 0, (
            f"Should find entities matching sensor\\.circuit.*|binary_sensor\\.door.* patterns, got: {entities}"
        )
        assert len(found_entities) > 0, f"Expected to find some of {expected_entities}, but found: {entities}"

    def test_edge_case_trailing_pipe_pattern(self, collection_resolver):
        """Test edge case with trailing pipe in regex pattern."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        # Test edge case with trailing pipe - should handle gracefully
        query = DynamicQuery(
            query_type="regex",
            pattern="circuit.*|kitchen.*|",
            function="count",
        )
        entities = collection_resolver.resolve_collection(query)

        # Should still find entities matching the valid patterns
        expected_entities = [
            "sensor.circuit_a_power",  # matches "circuit.*"
            "sensor.circuit_b_power",  # matches "circuit.*"
            "sensor.kitchen_temperature",  # matches "kitchen.*"
            "sensor.kitchen_temp",  # matches "kitchen.*"
            "sensor.kitchen_humidity",  # matches "kitchen.*"
        ]

        # Check that we found some entities matching the valid patterns
        found_entities = [entity for entity in expected_entities if entity in entities]
        assert len(entities) > 0, f"Should find entities matching valid patterns even with trailing pipe, got: {entities}"
        assert len(found_entities) > 0, f"Expected to find some of {expected_entities}, but found: {entities}"

    def test_escaped_characters_in_or_regex(self, collection_resolver):
        """Test escaped characters in OR regex patterns."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        # Test escaped characters in regex pattern
        query = DynamicQuery(
            query_type="regex", pattern="sensor\\.circuit_.*_power|sensor\\.circuit_.*_power", function="count"
        )
        entities = collection_resolver.resolve_collection(query)

        # Expected entities from shared registry that match the escaped pattern
        expected_entities = [
            "sensor.circuit_a_power",  # matches "sensor\.circuit_.*_power"
            "sensor.circuit_b_power",  # matches "sensor\.circuit_.*_power"
        ]

        # Check that we found the expected entities
        found_entities = [entity for entity in expected_entities if entity in entities]
        assert len(entities) > 0, f"Should find entities matching escaped regex pattern, got: {entities}"
        assert len(found_entities) > 0, f"Expected to find some of {expected_entities}, but found: {entities}"
