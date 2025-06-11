"""Integration tests for OR-style regex pattern support in collection functions.

This test suite validates that regex patterns with pipe (|) syntax work correctly
with actual YAML configurations and collection resolver execution. It covers:
- Basic OR regex patterns
- Multiple OR patterns (three-way)
- Variable-driven OR patterns
- Complex mathematical expressions with OR patterns
- Edge cases and error handling
"""

from unittest.mock import Mock, patch

import pytest
import yaml

from ha_synthetic_sensors.collection_resolver import CollectionResolver
from ha_synthetic_sensors.dependency_parser import DependencyParser, DynamicQuery
from ha_synthetic_sensors.evaluator import Evaluator


class TestOrRegexIntegration:
    """Integration tests for OR-style regex pattern functionality."""

    def setup_method(self):
        """Set up test fixtures for each test."""
        # Load the YAML test fixtures
        self.yaml_fixtures = self._load_yaml_fixtures()

        # Set up mock Home Assistant instance
        self.mock_hass = Mock()
        self.mock_hass.data = {}

        # Mock entities for regex testing
        self.mock_states = {
            "sensor.circuit_a_power": Mock(state="150.5", entity_id="sensor.circuit_a_power", attributes={"device_class": "power"}),
            "sensor.circuit_b_power": Mock(state="225.3", entity_id="sensor.circuit_b_power", attributes={"device_class": "power"}),
            "sensor.kitchen_main_power": Mock(state="75.2", entity_id="sensor.kitchen_main_power", attributes={"device_class": "power"}),
            "sensor.kitchen_outlet_power": Mock(state="45.8", entity_id="sensor.kitchen_outlet_power", attributes={"device_class": "power"}),
            "sensor.kitchen_main_temp": Mock(state="22.5", entity_id="sensor.kitchen_main_temp", attributes={"device_class": "temperature"}),
            "sensor.living_room_temp": Mock(state="21.8", entity_id="sensor.living_room_temp", attributes={"device_class": "temperature"}),
            "sensor.bedroom_main_temp": Mock(state="20.1", entity_id="sensor.bedroom_main_temp", attributes={"device_class": "temperature"}),
            "binary_sensor.motion_detector": Mock(state="on", entity_id="binary_sensor.motion_detector", attributes={}),
            "binary_sensor.door_sensor": Mock(state="off", entity_id="binary_sensor.door_sensor", attributes={}),
            "input_number.test_value": Mock(state="100", entity_id="input_number.test_value", attributes={}),
            # Variables for regex patterns
            "input_text.primary_regex_pattern": Mock(state=".*circuit_.*_power", entity_id="input_text.primary_regex_pattern", attributes={}),
            "input_text.secondary_regex_pattern": Mock(state=".*kitchen_.*_power", entity_id="input_text.secondary_regex_pattern", attributes={}),
            "input_text.circuit_power_regex": Mock(state=".*circuit_.*_power", entity_id="input_text.circuit_power_regex", attributes={}),
            "input_text.kitchen_power_regex": Mock(state=".*kitchen_.*_power", entity_id="input_text.kitchen_power_regex", attributes={}),
            "input_text.kitchen_temp_regex": Mock(state=".*kitchen_.*_temp", entity_id="input_text.kitchen_temp_regex", attributes={}),
            "input_text.living_temp_regex": Mock(state=".*living_.*_temp", entity_id="input_text.living_temp_regex", attributes={}),
            "input_text.bedroom_temp_regex": Mock(state=".*bedroom_.*_temp", entity_id="input_text.bedroom_temp_regex", attributes={}),
            "input_text.power_regex": Mock(state=".*_power", entity_id="input_text.power_regex", attributes={}),
        }

        # Configure mock states
        self.mock_hass.states.entity_ids.return_value = list(self.mock_states.keys())
        self.mock_hass.states.get.side_effect = lambda entity_id: self.mock_states.get(entity_id)

        # Create collection resolver and evaluator
        with patch("ha_synthetic_sensors.collection_resolver.er.async_get"), patch("ha_synthetic_sensors.collection_resolver.dr.async_get"), patch("ha_synthetic_sensors.collection_resolver.ar.async_get"):
            self.resolver = CollectionResolver(self.mock_hass)
            self.evaluator = Evaluator(self.mock_hass)
            self.parser = DependencyParser()

    def _load_yaml_fixtures(self):
        """Load the YAML test fixtures."""
        try:
            with open("/Users/bflood/projects/HA/ha-synthetic-sensors/tests/yaml_fixtures/dynamic_collection_variables.yaml") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            pytest.skip("YAML fixtures file not found")

    def test_yaml_or_regex_fixtures_loaded(self):
        """Test that YAML fixtures contain OR-style regex patterns."""
        assert self.yaml_fixtures is not None
        assert "sensors" in self.yaml_fixtures

        # Check for specific OR regex test cases
        sensors = self.yaml_fixtures["sensors"]
        assert "circuit_or_kitchen_power" in sensors
        assert "multi_room_temperature" in sensors
        assert "dynamic_or_regex_patterns" in sensors
        assert "comprehensive_regex_analysis" in sensors

    def test_parse_basic_or_regex_pattern(self):
        """Test parsing of basic OR regex patterns with pipe syntax."""
        formula = 'sum("regex:.*circuit_.*_power|.*kitchen_.*_power")'
        parsed = self.parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "sum"
        assert query.query_type == "regex"
        assert query.pattern == ".*circuit_.*_power|.*kitchen_.*_power"

    def test_parse_three_way_or_regex_pattern(self):
        """Test parsing of three-way OR regex patterns."""
        formula = 'avg("regex:.*kitchen_.*_temp|.*living_.*_temp|.*bedroom_.*_temp")'
        parsed = self.parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "avg"
        assert query.query_type == "regex"
        assert query.pattern == ".*kitchen_.*_temp|.*living_.*_temp|.*bedroom_.*_temp"

    def test_parse_complex_domain_or_regex(self):
        """Test parsing of complex domain OR patterns."""
        formula = 'count("regex:sensor\\.|binary_sensor\\.|input_.*\\.")'
        parsed = self.parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "count"
        assert query.query_type == "regex"
        assert query.pattern == "sensor\\.|binary_sensor\\.|input_.*\\."

    def test_resolve_or_regex_pattern_integration(self):
        """Test end-to-end resolution of OR regex patterns."""
        # Test basic OR pattern resolution with proper entity ID patterns
        query = DynamicQuery(query_type="regex", pattern=".*circuit_.*_power|.*kitchen_.*_power", function="sum")
        entities = self.resolver.resolve_collection(query)

        # Should match circuit and kitchen power sensors
        expected_entities = ["sensor.circuit_a_power", "sensor.circuit_b_power", "sensor.kitchen_main_power", "sensor.kitchen_outlet_power"]
        assert set(entities) == set(expected_entities)

    def test_resolve_three_way_or_regex_integration(self):
        """Test three-way OR regex pattern resolution."""
        query = DynamicQuery(query_type="regex", pattern=".*kitchen_.*_temp|.*living_.*_temp|.*bedroom_.*_temp", function="avg")
        entities = self.resolver.resolve_collection(query)

        # Should match temperature sensors from all three rooms
        expected_entities = ["sensor.kitchen_main_temp", "sensor.living_room_temp", "sensor.bedroom_main_temp"]
        assert set(entities) == set(expected_entities)

    def test_resolve_domain_or_regex_integration(self):
        """Test domain-based OR regex pattern resolution."""
        query = DynamicQuery(query_type="regex", pattern="sensor\\.|binary_sensor\\.", function="count")
        entities = self.resolver.resolve_collection(query)

        # Should match all sensor and binary_sensor entities
        expected_count = len([e for e in self.mock_states if e.startswith(("sensor.", "binary_sensor."))])
        assert len(entities) == expected_count

    def test_variable_driven_or_regex_integration(self):
        """Test variable-driven OR regex patterns."""
        # This would test resolution with variables, but requires full evaluator integration
        formula = 'sum("regex:primary_pattern|secondary_pattern")'
        variables = {"primary_pattern": "input_text.primary_regex_pattern", "secondary_pattern": "input_text.secondary_regex_pattern"}

        parsed = self.parser.parse_formula_dependencies(formula, variables)
        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.pattern == "primary_pattern|secondary_pattern"

    def test_yaml_circuit_or_kitchen_power_config(self):
        """Test YAML configuration for circuit or kitchen power."""
        config = self.yaml_fixtures["sensors"]["circuit_or_kitchen_power"]

        assert config["name"] == "Circuit or Kitchen Power Sum"
        assert config["formula"] == 'sum("regex:circuit_pattern|kitchen_pattern")'
        assert config["unit_of_measurement"] == "W"
        assert config["device_class"] == "power"
        assert config["state_class"] == "measurement"

    def test_yaml_multi_room_temperature_config(self):
        """Test YAML configuration for multi-room temperature."""
        config = self.yaml_fixtures["sensors"]["multi_room_temperature"]

        assert config["name"] == "Multi-Room Temperature Average"
        assert config["formula"] == 'avg("regex:kitchen_pattern|living_pattern|bedroom_pattern")'
        assert config["unit_of_measurement"] == "°C"
        assert config["device_class"] == "temperature"

    def test_yaml_comprehensive_regex_analysis_config(self):
        """Test YAML configuration for comprehensive regex analysis with OR patterns in attributes."""
        config = self.yaml_fixtures["sensors"]["comprehensive_regex_analysis"]

        assert config["name"] == "Comprehensive Regex Analysis"
        assert config["formula"] == 'sum("regex:power_pattern")'

        # Check OR patterns in attributes
        attributes = config["attributes"]
        assert attributes["circuit_status"]["formula"] == 'count("regex:circuit_pattern|breaker_pattern")'
        assert attributes["climate_data"]["formula"] == 'avg("regex:temperature_pattern|humidity_pattern|pressure_pattern")'
        assert attributes["motion_sensors"]["formula"] == 'count("regex:motion_pattern|occupancy_pattern|presence_pattern")'
        assert attributes["mixed_patterns"]["formula"] == 'sum("regex:sensor_power_pattern|binary_on_pattern")'

    def test_yaml_dynamic_or_regex_patterns_config(self):
        """Test YAML configuration for dynamic OR regex patterns."""
        config = self.yaml_fixtures["sensors"]["dynamic_or_regex_patterns"]

        assert config["name"] == "Dynamic OR Regex Patterns"
        assert config["formula"] == 'sum("regex:primary_pattern|secondary_pattern")'

        variables = config["variables"]
        assert variables["primary_pattern"] == "input_text.primary_regex_pattern"
        assert variables["secondary_pattern"] == "input_text.secondary_regex_pattern"

    def test_mathematical_expression_or_regex_integration(self):
        """Test OR regex patterns in mathematical expressions."""
        # Test the efficiency calculation formula from YAML
        formula = '(sum("regex:.*_power|.*_energy") / count("regex:.*_temp|.*_humidity")) * 100'
        parsed = self.parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 2

        # First query - power/energy OR pattern
        power_query = parsed.dynamic_queries[0]
        assert power_query.function == "sum"
        assert power_query.pattern == ".*_power|.*_energy"

        # Second query - temp/humidity OR pattern
        temp_query = parsed.dynamic_queries[1]
        assert temp_query.function == "count"
        assert temp_query.pattern == ".*_temp|.*_humidity"

    def test_edge_case_empty_or_pattern(self):
        """Test edge case with empty OR pattern."""
        query = DynamicQuery(query_type="regex", pattern="test_.*|", function="count")
        entities = self.resolver.resolve_collection(query)

        # Should handle gracefully and match only non-empty patterns
        assert isinstance(entities, list)

    def test_edge_case_trailing_pipe_pattern(self):
        """Test edge case with trailing pipe in pattern."""
        query = DynamicQuery(query_type="regex", pattern="sensor\\.|binary_sensor\\.|", function="count")
        entities = self.resolver.resolve_collection(query)

        # Should handle gracefully
        assert isinstance(entities, list)
        assert len(entities) > 0  # Should still match sensor and binary_sensor entities

    def test_escaped_characters_in_or_regex(self):
        """Test OR regex patterns with escaped characters."""
        query = DynamicQuery(query_type="regex", pattern="sensor\\.circuit_.*|sensor\\.power_.*", function="sum")
        entities = self.resolver.resolve_collection(query)

        # Should match escaped dot patterns correctly
        expected_entities = [e for e in self.mock_states if e.startswith("sensor.circuit_") or e.startswith("sensor.power_")]
        assert set(entities) == set(expected_entities)

    def test_direct_entity_id_or_patterns(self):
        """Test OR patterns with direct entity IDs (no variables)."""
        # Test direct entity ID OR pattern parsing
        formula = 'sum("regex:input_text.circuit_regex|input_text.kitchen_regex")'
        parsed = self.parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "sum"
        assert query.query_type == "regex"
        assert query.pattern == "input_text.circuit_regex|input_text.kitchen_regex"

    def test_mixed_direct_and_variable_or_patterns(self):
        """Test OR patterns mixing variables and direct entity IDs."""
        formula = 'sum("regex:variable_pattern|input_text.direct_regex_pattern")'
        variables = {"variable_pattern": "input_text.variable_regex_pattern"}
        parsed = self.parser.parse_formula_dependencies(formula, variables)

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "sum"
        assert query.query_type == "regex"
        assert query.pattern == "variable_pattern|input_text.direct_regex_pattern"

    def test_yaml_direct_regex_or_config(self):
        """Test YAML configuration for direct regex OR patterns."""
        config = self.yaml_fixtures["sensors"]["direct_regex_or"]

        assert config["name"] == "Direct Regex OR"
        assert config["formula"] == 'sum("regex:input_text.circuit_regex|input_text.kitchen_regex")'
        assert config["unit_of_measurement"] == "W"
        assert config["device_class"] == "power"
        # Should have no variables section since it uses direct entity IDs
        assert "variables" not in config

    def test_yaml_mixed_regex_or_config(self):
        """Test YAML configuration for mixed regex OR patterns."""
        config = self.yaml_fixtures["sensors"]["mixed_regex_or"]

        assert config["name"] == "Mixed Regex OR"
        assert config["formula"] == 'sum("regex:variable_pattern|input_text.direct_regex_pattern")'
        assert config["unit_of_measurement"] == "W"
        assert config["device_class"] == "power"

        # Should have variables for the variable part only
        variables = config["variables"]
        assert variables["variable_pattern"] == "input_text.variable_regex_pattern"
        assert len(variables) == 1  # Only one variable, not the direct entity ID

    def test_yaml_direct_three_way_regex_config(self):
        """Test YAML configuration for direct three-way regex OR patterns."""
        config = self.yaml_fixtures["sensors"]["direct_three_way_regex"]

        assert config["name"] == "Direct Three-Way Regex"
        assert config["formula"] == 'count("regex:input_text.pattern1|input_text.pattern2|input_text.pattern3")'
        assert config["unit_of_measurement"] == "entities"
        # Should have no variables section
        assert "variables" not in config
