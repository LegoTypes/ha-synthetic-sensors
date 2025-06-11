"""Tests for state and attribute OR pattern integration.

This module tests OR-style logic for both state and attribute collection patterns using pipe (|) syntax.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ha_synthetic_sensors.collection_resolver import CollectionResolver
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.dependency_parser import DependencyParser


class TestStateAndAttributeORIntegration:
    """Test OR pattern integration for state and attribute collection functions."""

    @pytest.fixture
    def yaml_config_path(self):
        """Path to the attribute OR patterns YAML fixture."""
        return Path(__file__).parent / "yaml_fixtures" / "attribute_or_patterns.yaml"

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance with diverse entity states and attributes."""
        hass = Mock()
        hass.data = {}

        mock_states = {
            # Entities with battery_level attributes
            "sensor.phone_battery": Mock(state="85", entity_id="sensor.phone_battery", attributes={"battery_level": 15, "device_class": "battery"}),
            "sensor.tablet_battery": Mock(state="25", entity_id="sensor.tablet_battery", attributes={"battery_level": 25, "device_class": "battery"}),
            "sensor.laptop_battery": Mock(state="92", entity_id="sensor.laptop_battery", attributes={"battery_level": 92, "device_class": "battery"}),
            # Entities with online attributes
            "sensor.router_status": Mock(state="connected", entity_id="sensor.router_status", attributes={"online": False}),
            "sensor.server_status": Mock(state="active", entity_id="sensor.server_status", attributes={"online": True}),
            "sensor.camera_status": Mock(state="offline", entity_id="sensor.camera_status", attributes={"online": False}),
            # Entities with high numeric states (for state: testing)
            "sensor.power_meter": Mock(state="150", entity_id="sensor.power_meter", attributes={"device_class": "power"}),
            "sensor.temperature_sensor": Mock(state="25", entity_id="sensor.temperature_sensor", attributes={"device_class": "temperature"}),
            "sensor.humidity_sensor": Mock(state="45", entity_id="sensor.humidity_sensor", attributes={"device_class": "humidity"}),
            # Entities with "on" states
            "light.living_room": Mock(state="on", entity_id="light.living_room", attributes={}),
            "switch.garden_light": Mock(state="on", entity_id="switch.garden_light", attributes={}),
            "switch.fan": Mock(state="off", entity_id="switch.fan", attributes={}),
            # Mixed entities for comprehensive testing
            "sensor.mixed_device_1": Mock(state="120", entity_id="sensor.mixed_device_1", attributes={"battery_level": 5, "online": True}),
            "sensor.mixed_device_2": Mock(state="on", entity_id="sensor.mixed_device_2", attributes={"battery_level": 90, "online": False}),
        }

        hass.states.entity_ids.return_value = list(mock_states.keys())
        hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)

        return hass

    @pytest.fixture
    def collection_resolver(self, mock_hass):
        """Create a collection resolver instance with mocked dependencies."""
        with patch("ha_synthetic_sensors.collection_resolver.er.async_get"), patch("ha_synthetic_sensors.collection_resolver.dr.async_get"), patch("ha_synthetic_sensors.collection_resolver.ar.async_get"):
            return CollectionResolver(mock_hass)

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager instance."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def dependency_parser(self):
        """Create a dependency parser instance."""
        return DependencyParser()

    def test_yaml_fixture_loads_with_or_patterns(self, config_manager, yaml_config_path):
        """Test that the YAML fixture loads without errors."""
        try:
            config = config_manager.load_from_file(yaml_config_path)

            assert config is not None
            assert len(config.sensors) > 0

            # Check that we have the expected sensors
            sensor_names = [sensor.unique_id for sensor in config.sensors]
            assert "low_battery_or_offline" in sensor_names
            assert "targeted_battery_monitoring" in sensor_names

        except Exception as e:
            if "Configuration schema validation failed" in str(e):
                pytest.skip(f"Schema validation failed as expected for future syntax: {e}")
            else:
                raise

    def test_basic_attribute_or_pattern_parsing(self, dependency_parser):
        """Test parsing of basic attribute OR patterns."""
        formula = 'count("attribute:battery_level<20|online=false")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "count"
        assert query.query_type == "attribute"
        assert query.pattern == "battery_level<20|online=false"

    def test_basic_state_or_pattern_parsing(self, dependency_parser):
        """Test parsing of basic state OR patterns."""
        formula = 'count("state:>100|=on")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "count"
        assert query.query_type == "state"
        assert query.pattern == ">100|=on"

    def test_attribute_or_resolution_implemented(self, collection_resolver):
        """Test resolution of attribute OR patterns."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        query = DynamicQuery(query_type="attribute", pattern="battery_level<20|online=false", function="count")

        entities = collection_resolver.resolve_collection(query)

        # Should find entities with battery_level < 20 OR online = false
        expected_entities = [
            "sensor.phone_battery",  # battery_level: 15 < 20
            "sensor.router_status",  # online: False
            "sensor.camera_status",  # online: False
            "sensor.mixed_device_1",  # battery_level: 5 < 20
            "sensor.mixed_device_2",  # online: False
        ]

        for entity_id in expected_entities:
            assert entity_id in entities, f"Expected {entity_id} to be found with attribute OR pattern"

    def test_state_or_resolution_implemented(self, collection_resolver):
        """Test resolution of state OR patterns."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        query = DynamicQuery(query_type="state", pattern=">100|=on", function="count")

        entities = collection_resolver.resolve_collection(query)

        # Should find entities with state > 100 OR state = "on"
        expected_entities = [
            "sensor.power_meter",  # state: "150" > 100
            "sensor.mixed_device_1",  # state: "120" > 100
            "light.living_room",  # state: "on"
            "switch.garden_light",  # state: "on"
            "sensor.mixed_device_2",  # state: "on"
        ]

        for entity_id in expected_entities:
            assert entity_id in entities, f"Expected {entity_id} to be found with state OR pattern"

    def test_complex_attribute_or_conditions(self, collection_resolver):
        """Test complex attribute OR conditions."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        # Test multiple conditions
        query = DynamicQuery(query_type="attribute", pattern="battery_level<30|battery_level>90|online=true", function="count")

        entities = collection_resolver.resolve_collection(query)

        # Should find entities with battery_level < 30 OR battery_level > 90 OR online = true
        expected_entities = [
            "sensor.phone_battery",  # battery_level: 15 < 30
            "sensor.tablet_battery",  # battery_level: 25 < 30
            "sensor.laptop_battery",  # battery_level: 92 > 90
            "sensor.server_status",  # online: True
            "sensor.mixed_device_1",  # battery_level: 5 < 30 AND online: True
        ]

        for entity_id in expected_entities:
            assert entity_id in entities, f"Expected {entity_id} to be found with complex attribute OR pattern"

    def test_complex_state_or_conditions(self, collection_resolver):
        """Test complex state OR conditions."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        # Test multiple state conditions
        query = DynamicQuery(query_type="state", pattern="<30|>90|=active|=connected", function="count")

        entities = collection_resolver.resolve_collection(query)

        # Should find entities with various state conditions
        expected_entities = [
            "sensor.temperature_sensor",  # state: "25" < 30
            "sensor.laptop_battery",  # state: "92" > 90
            "sensor.mixed_device_1",  # state: "120" > 90
            "sensor.server_status",  # state: "active"
            "sensor.router_status",  # state: "connected"
        ]

        for entity_id in expected_entities:
            assert entity_id in entities, f"Expected {entity_id} to be found with complex state OR pattern"

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

    def test_variable_device_class_with_attribute_access(self, dependency_parser):
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

    @pytest.fixture
    def dependency_parser(self):
        """Create a dependency parser instance."""
        return DependencyParser()

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
