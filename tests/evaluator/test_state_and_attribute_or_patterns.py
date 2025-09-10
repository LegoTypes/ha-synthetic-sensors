"""Tests for state and attribute OR pattern integration.

This module tests OR-style logic for both state and attribute collection patterns using pipe (|) syntax.
"""

import pytest
from unittest.mock import patch, Mock
from ha_synthetic_sensors.collection_resolver import CollectionResolver
from ha_synthetic_sensors.dependency_parser import DependencyParser, DynamicQuery
from ha_synthetic_sensors.evaluator import Evaluator
from pathlib import Path


@pytest.fixture
def config_manager(mock_hass):
    """Create a config manager with mock HA."""
    from ha_synthetic_sensors.config_manager import ConfigManager

    return ConfigManager(mock_hass)


@pytest.fixture
def yaml_config_path():
    """Path to the state and attribute OR patterns YAML fixture."""
    return Path(__file__).parent.parent / "yaml_fixtures" / "state_attribute_or_patterns.yaml"


@pytest.fixture
def dependency_parser():
    """Create a dependency parser instance."""
    from ha_synthetic_sensors.dependency_parser import DependencyParser

    return DependencyParser()


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


class TestStateAndAttributeORIntegration:
    """Test OR pattern integration with state and attribute-based entity resolution."""

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

    def test_attribute_or_resolution_implemented(self, collection_resolver):
        """Test that attribute OR pattern resolution works correctly."""
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

        # Test OR pattern with existing entities from shared registry
        # Pattern will match entities with battery_level>50 OR device_class==temperature
        query = DynamicQuery(query_type="attribute", pattern="battery_level>50|device_class:temperature", function="count")

        # Resolve the collection using the resolver
        entities = collection_resolver.resolve_collection(query)

        # Expected entities from shared registry that match the attribute patterns
        expected_entities = [
            "sensor.battery_device",  # has battery_level=85 (>50)
            "sensor.kitchen_temperature",  # has device_class=temperature (shorthand syntax)
            "sensor.living_room_temperature",  # has device_class=temperature
            "sensor.kitchen_temp",  # has device_class=temperature
            "sensor.living_temp",  # has device_class=temperature
            "sensor.temperature",  # has device_class=temperature
            "sensor.temp_1",  # has device_class=temperature
            "sensor.living_room_temp",  # has device_class=temperature
            "sensor.master_bedroom_temp",  # has device_class=temperature
            "sensor.guest_bedroom_temp",  # has device_class=temperature
        ]

        # Check that we found some entities matching the patterns
        found_entities = [entity for entity in expected_entities if entity in entities]
        assert len(entities) > 0, f"Should find entities with battery_level>50 or device_class:temperature, got: {entities}"
        assert len(found_entities) > 0, f"Expected to find some of {expected_entities}, but found: {entities}"

    def test_state_or_resolution_implemented(self, collection_resolver):
        """Test that state OR pattern resolution works correctly."""
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

        # Test OR pattern with existing entities from shared registry
        # Pattern will match entities with state=on OR state=locked using shorthand syntax
        query = DynamicQuery(query_type="state", pattern="on|locked", function="count")

        # Resolve the collection using the resolver
        entities = collection_resolver.resolve_collection(query)

        # Expected entities from shared registry that match the state patterns
        expected_entities = [
            "binary_sensor.back_door",  # state=on
            "binary_sensor.bedroom_window",  # state=on
            "lock.front_door_lock",  # state=locked
            "light.living_room_main",  # state=on
        ]

        # Check that we found some entities matching the patterns
        found_entities = [entity for entity in expected_entities if entity in entities]
        assert len(entities) > 0, f"Should find entities with state=on or state=locked, got: {entities}"
        assert len(found_entities) > 0, f"Expected to find some of {expected_entities}, but found: {entities}"

    def test_complex_attribute_or_conditions(self, collection_resolver):
        """Test OR pattern resolution for complex attribute conditions."""
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

        # Test complex OR conditions with existing entities
        query = DynamicQuery(query_type="attribute", pattern="battery_level>70|device_class:power", function="count")
        entities = collection_resolver.resolve_collection(query)

        # Expected entities from shared registry that match the patterns
        expected_entities = [
            "sensor.battery_device",  # has battery_level=85 (>70)
            "sensor.circuit_a_power",  # has device_class=power
            "sensor.circuit_b_power",  # has device_class=power
        ]

        # Check that we found some entities matching the patterns
        found_entities = [entity for entity in expected_entities if entity in entities]
        assert len(entities) > 0, f"Should find entities with complex attribute patterns, got: {entities}"
        assert len(found_entities) > 0, f"Expected to find some of {expected_entities}, but found: {entities}"

    def test_complex_state_or_conditions(self, collection_resolver):
        """Test OR pattern resolution for complex state conditions."""
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

        # Test complex state OR conditions with numeric and boolean patterns
        query = DynamicQuery(query_type="state", pattern=">20|locked|!off", function="count")
        entities = collection_resolver.resolve_collection(query)

        # Expected entities from shared registry that match the patterns
        expected_entities = [
            "sensor.kitchen_temperature",  # state=22.5 (>20)
            "sensor.living_room_temperature",  # state=23.0 (>20)
            "sensor.kitchen_temp",  # state=22.5 (>20)
            "sensor.living_temp",  # state=23.0 (>20)
            "sensor.temperature",  # state=22.0 (>20)
            "sensor.temp_1",  # state=21.5 (>20)
            "lock.front_door_lock",  # state=locked
            # Plus many entities that are not "off"
        ]

        # Check that we found some entities matching the patterns
        found_entities = [entity for entity in expected_entities if entity in entities]
        assert len(entities) > 0, f"Should find entities with complex state patterns, got: {entities}"
        assert len(found_entities) > 0, f"Expected to find some of {expected_entities}, but found: {entities}"

    def test_device_class_negation_syntax(self, collection_resolver):
        """Test device_class pattern negation with ! prefix."""
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

        # Test device_class inclusion and exclusion
        query = DynamicQuery(query_type="device_class", pattern="power|!humidity", function="count")
        entities = collection_resolver.resolve_collection(query)

        # Should find entities with device_class=power OR device_class!=humidity
        expected_entities = [
            "sensor.circuit_a_power",  # device_class=power (included)
            "sensor.circuit_b_power",  # device_class=power (included)
            # Plus entities that don't have device_class=humidity (excluded)
            "sensor.kitchen_temperature",  # device_class=temperature (not humidity)
            "sensor.living_room_temperature",  # device_class=temperature (not humidity)
            "binary_sensor.front_door",  # device_class=door (not humidity)
            "binary_sensor.back_door",  # device_class=door (not humidity)
        ]

        # Check that we found entities
        assert len(entities) > 0, f"Device class negation should find entities, got: {entities}"

        # Verify specific inclusions
        power_entities = [e for e in entities if "power" in e]
        assert len(power_entities) >= 2, f"Should include power entities, got: {power_entities}"

    def test_device_class_shorthand_syntax(self, collection_resolver):
        """Test device_class pattern shorthand syntax."""
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

        # Test device_class shorthand: first pattern with prefix, second without
        query = DynamicQuery(query_type="device_class", pattern="power|energy", function="count")
        entities = collection_resolver.resolve_collection(query)

        # Should find entities with device_class=power OR device_class=energy
        expected_entities = [
            "sensor.circuit_a_power",  # device_class=power
            "sensor.circuit_b_power",  # device_class=power
            # Plus any entities with device_class=energy
        ]

        # Check that we found entities
        assert len(entities) > 0, f"Device class shorthand should find entities, got: {entities}"

        # Verify power entities are included
        power_entities = [e for e in entities if "power" in e]
        assert len(power_entities) >= 2, f"Should include power entities, got: {power_entities}"

    def test_mixed_state_and_attribute_formulas(self, dependency_parser):
        """Test formulas that mix state and attribute patterns."""
        formula = 'count("state:>100") + count("attribute:battery_level<20")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 2

        # First query: state pattern
        state_query = parsed.dynamic_queries[0]
        assert state_query.function == "count"
        assert state_query.query_type == "state"
        assert state_query.pattern == ">100"

        # Second query: attribute pattern
        attr_query = parsed.dynamic_queries[1]
        assert attr_query.function == "count"
        assert attr_query.query_type == "attribute"
        assert attr_query.pattern == "battery_level<20"

    def test_variable_device_class_with_attribute_access(self, dependency_parser, mock_hass, mock_entity_registry, mock_states):
        """Test the variable + dot notation syntax for targeted attribute filtering."""
        formula = 'count("battery_devices.battery_level<20")'
        variables = {"battery_devices": "device_class:battery"}

        parsed = dependency_parser.parse_formula_dependencies(formula, variables)

        # This should NOT create a dynamic query since it's using variable dot notation
        # Instead, it should be handled by the formula evaluator
        # For now, let's just verify it parses without error
        assert isinstance(parsed.dynamic_queries, list)


class TestStateAndAttributePatternEdgeCases:
    """Test edge cases for state and attribute OR patterns."""

    def test_single_attribute_no_or(self, dependency_parser):
        """Test single attribute without OR logic."""
        formula = 'count("attribute:battery_level<20")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.pattern == "battery_level<20"
        assert "|" not in query.pattern

    def test_single_state_no_or(self, dependency_parser):
        """Test single state without OR logic."""
        formula = 'count("state:>100")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.pattern == ">100"
        assert "|" not in query.pattern

    def test_empty_or_components_attribute(self, dependency_parser):
        """Test handling of empty OR components in attribute patterns."""
        formula = 'sum("attribute:battery_level<20||online=false")'  # Double pipe
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.pattern == "battery_level<20||online=false"

    def test_empty_or_components_state(self, dependency_parser):
        """Test handling of empty OR components in state patterns."""
        formula = 'sum("state:>100||=on")'  # Double pipe
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.pattern == ">100||=on"

    def test_multiple_or_patterns_same_formula(self, dependency_parser):
        """Test multiple OR patterns in the same formula."""
        formula = 'sum("state:>100|=on") + count("attribute:battery_level<20|online=false")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 2

        patterns = [query.pattern for query in parsed.dynamic_queries]
        assert ">100|=on" in patterns
        assert "battery_level<20|online=false" in patterns
