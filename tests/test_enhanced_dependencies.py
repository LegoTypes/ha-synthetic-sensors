"""Tests for enhanced dependency parsing and variable inheritance.

This module tests the new features including:
- Variable inheritance in attribute formulas
- Dynamic query parsing (regex, tags, device_class, etc.)
- Dot notation attribute access
- Complex aggregation functions
"""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.dependency_parser import DependencyParser


class TestDependencyParser:
    """Test the enhanced dependency parser."""

    @pytest.fixture
    def parser(self):
        """Create a DependencyParser instance."""
        return DependencyParser()

    def test_extract_static_dependencies_with_variables(self, parser):
        """Test extraction of static dependencies including variables."""
        formula = "power_a + power_b * efficiency"
        variables = {"power_a": "sensor.power_meter_a", "power_b": "sensor.power_meter_b", "efficiency": "input_number.efficiency_factor"}

        deps = parser.extract_static_dependencies(formula, variables)

        expected = {"sensor.power_meter_a", "sensor.power_meter_b", "input_number.efficiency_factor"}
        assert deps == expected

    def test_extract_dynamic_queries_sum_regex(self, parser):
        """Test extraction of regex query patterns."""
        formula = "sum(regex:sensor\\.circuit_.*_power) + base_load"

        queries = parser.extract_dynamic_queries(formula)

        assert len(queries) == 1
        assert queries[0].query_type == "regex"
        assert queries[0].pattern == "sensor\\.circuit_.*_power"
        assert queries[0].function == "sum"

    def test_extract_dynamic_queries_sum_tags(self, parser):
        """Test extraction of tag query patterns."""
        formula = "avg(tags:heating,cooling) * factor"

        queries = parser.extract_dynamic_queries(formula)

        assert len(queries) == 1
        assert queries[0].query_type == "tags"
        assert queries[0].pattern == "heating,cooling"
        assert queries[0].function == "avg"

    def test_extract_dynamic_queries_device_class(self, parser):
        """Test extraction of device class query patterns."""
        formula = "count(device_class:door|window)"

        queries = parser.extract_dynamic_queries(formula)

        assert len(queries) == 1
        assert queries[0].query_type == "device_class"
        assert queries[0].pattern == "door|window"
        assert queries[0].function == "count"

    def test_extract_dynamic_queries_quoted(self, parser):
        """Test extraction of quoted query patterns."""
        formula = "sum(\"regex:sensor\\.span_.*_power\") + sum('tags:tag with spaces')"

        queries = parser.extract_dynamic_queries(formula)

        assert len(queries) == 2
        assert queries[0].query_type == "regex"
        assert queries[0].pattern == "sensor\\.span_.*_power"
        assert queries[1].query_type == "tags"
        assert queries[1].pattern == "tag with spaces"

    def test_dot_notation_extraction(self, parser):
        """Test extraction of dot notation references."""
        formula = "sensor1.battery_level + sensor2.attributes.battery_level"
        variables = {"sensor1": "sensor.phone", "sensor2": "sensor.tablet"}

        parsed = parser.parse_formula_dependencies(formula, variables)

        # Should include variables as static dependencies
        assert "sensor.phone" in parsed.static_dependencies
        assert "sensor.tablet" in parsed.static_dependencies

        # Should extract dot notation references
        expected_refs = {"sensor1.battery_level", "sensor2.attributes.battery_level"}
        assert parsed.dot_notation_refs == expected_refs


class TestVariableInheritance:
    """Test variable inheritance in attribute formulas."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        return MagicMock()

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a ConfigManager instance."""
        return ConfigManager(mock_hass)

    def test_attribute_inherits_parent_variables(self, config_manager):
        """Test that attribute formulas inherit parent sensor variables."""
        sensor_data = {"name": "Test Sensor", "formula": "power_a + power_b", "variables": {"power_a": "sensor.meter_a", "power_b": "sensor.meter_b"}, "attributes": {"daily_total": {"formula": "power_a * 24"}}}

        # Parse the attribute formula
        attr_config = sensor_data["attributes"]["daily_total"]
        formula_config = config_manager._parse_attribute_formula("test_sensor", "daily_total", attr_config, sensor_data)

        # Should inherit parent variables
        assert "power_a" in formula_config.variables
        assert "power_b" in formula_config.variables
        assert formula_config.variables["power_a"] == "sensor.meter_a"
        assert formula_config.variables["power_b"] == "sensor.meter_b"

        # Should auto-inject the referenced entity_id as a variable
        assert formula_config.variables["test_sensor"] == "sensor.test_sensor"

    def test_attribute_variable_override(self, config_manager):
        """Test that attribute-specific variables override parent variables."""
        sensor_data = {"name": "Test Sensor", "formula": "power_a + power_b", "variables": {"power_a": "sensor.meter_a", "power_b": "sensor.meter_b"}, "attributes": {"custom_calc": {"formula": "power_a * factor", "variables": {"power_a": "sensor.custom_meter", "factor": "input_number.factor"}}}}  # Override parent  # New variable

        attr_config = sensor_data["attributes"]["custom_calc"]
        formula_config = config_manager._parse_attribute_formula("test_sensor", "custom_calc", attr_config, sensor_data)

        # Should use overridden value
        assert formula_config.variables["power_a"] == "sensor.custom_meter"
        # Should keep non-overridden parent variable
        assert formula_config.variables["power_b"] == "sensor.meter_b"
        # Should include new attribute-specific variable
        assert formula_config.variables["factor"] == "input_number.factor"

    def test_attribute_references_main_sensor(self, config_manager):
        """Test that attributes can reference the main sensor by key."""
        sensor_data = {"name": "Power Analysis", "formula": "meter_a + meter_b", "variables": {"meter_a": "sensor.meter_a", "meter_b": "sensor.meter_b"}, "attributes": {"daily_projection": {"formula": "power_analysis * 24"}}}  # Reference main sensor by key

        attr_config = sensor_data["attributes"]["daily_projection"]
        formula_config = config_manager._parse_attribute_formula("power_analysis", "daily_projection", attr_config, sensor_data)

        # Should include main sensor as variable
        assert "power_analysis" in formula_config.variables
        assert formula_config.variables["power_analysis"] == "sensor.power_analysis"


class TestComplexFormulaParsing:
    """Test parsing of complex formulas with multiple feature types."""

    @pytest.fixture
    def parser(self):
        """Create a DependencyParser instance."""
        return DependencyParser()

    def test_mixed_dependency_types(self, parser):
        """Test formula with static deps, dynamic queries, and dot notation."""
        formula = "sum(regex:sensor\\.circuit_.*) + " "avg(tags:heating) + " "base_load + " "sensor1.battery_level"
        variables = {"base_load": "sensor.base_power", "sensor1": "sensor.phone"}

        parsed = parser.parse_formula_dependencies(formula, variables)

        # Static dependencies
        assert "sensor.base_power" in parsed.static_dependencies
        assert "sensor.phone" in parsed.static_dependencies

        # Dynamic queries
        query_types = {q.query_type for q in parsed.dynamic_queries}
        assert "regex" in query_types
        assert "tags" in query_types

        # Dot notation
        assert "sensor1.battery_level" in parsed.dot_notation_refs


@pytest.fixture
def sample_config_with_attributes():
    """Sample configuration for testing."""
    return {"version": "1.0", "sensors": {"energy_analysis": {"name": "Energy Analysis", "formula": "grid_power + solar_power", "variables": {"grid_power": "sensor.grid_meter", "solar_power": "sensor.solar_inverter"}, "unit_of_measurement": "W", "device_class": "power", "state_class": "measurement", "attributes": {"daily_projection": {"formula": "energy_analysis * 24", "unit_of_measurement": "Wh"}, "efficiency": {"formula": "solar_power / (grid_power + solar_power) * 100", "unit_of_measurement": "%"}, "custom_calc": {"formula": "power_total * efficiency_factor", "variables": {"power_total": "sensor.total_power", "efficiency_factor": "input_number.factor"}, "unit_of_measurement": "W"}}}}}  # New variable


class TestIntegrationScenarios:
    """Integration tests for complete scenarios."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        return MagicMock()

    def test_config_parsing_with_enhanced_features(self, mock_hass, sample_config_with_attributes):
        """Test full config parsing with all enhanced features."""
        config_manager = ConfigManager(mock_hass)

        # This should parse without errors
        config = config_manager._parse_yaml_config(sample_config_with_attributes)

        # Should have one sensor
        assert len(config.sensors) == 1
        sensor = config.sensors[0]

        # Should have multiple formulas (main + attributes)
        assert len(sensor.formulas) == 4  # Main + 3 attributes

        # Check main formula
        main_formula = sensor.formulas[0]
        assert main_formula.id == "energy_analysis"
        assert "grid_power" in main_formula.variables
        assert "solar_power" in main_formula.variables

        # Check attribute formulas inherit variables
        daily_proj = next(f for f in sensor.formulas if f.id == "energy_analysis_daily_projection")
        assert "grid_power" in daily_proj.variables  # Inherited
        assert "solar_power" in daily_proj.variables  # Inherited
        assert "energy_analysis" in daily_proj.variables  # Main sensor reference

        # Check attribute with custom variables
        custom_calc = next(f for f in sensor.formulas if f.id == "energy_analysis_custom_calc")
        assert "power_total" in custom_calc.variables  # Attribute-specific
        assert "efficiency_factor" in custom_calc.variables  # Attribute-specific
        assert "grid_power" in custom_calc.variables  # Still inherited
