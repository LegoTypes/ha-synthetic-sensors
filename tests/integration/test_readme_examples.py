#!/usr/bin/env python3
"""Test script to verify README examples work correctly."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import yaml

from ha_synthetic_sensors.config_manager import ConfigManager


def load_yaml_fixture(fixture_name: str) -> dict[str, Any]:
    """Load a YAML fixture file from the readme_examples directory."""
    fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "readme_examples" / fixture_name
    with open(fixture_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_basic_readme_examples(mock_hass, mock_entity_registry, mock_states):
    """Test basic README examples are valid YAML and can be parsed correctly."""

    # Load basic examples fixture
    config_data = load_yaml_fixture("basic_examples.yaml")
    assert config_data is not None

    # Test config validation
    config_manager = ConfigManager(mock_hass)
    validation_result = config_manager.validate_yaml_data(config_data)
    assert validation_result["valid"], f"Configuration validation failed: {validation_result.get('errors', 'Unknown error')}"

    # Check that we have the expected number of sensors (based on README basic examples)
    sensors_count = len(config_data.get("sensors", {}))
    assert sensors_count == 2, f"Expected 2 sensors, got {sensors_count}"

    # Test that variables contain numeric literals
    sensors = config_data["sensors"]

    # Check energy_cost_current sensor
    energy_sensor = sensors["energy_cost_current"]
    conversion_factor = energy_sensor["variables"]["conversion_factor"]
    assert conversion_factor == 1000, f"Expected conversion_factor=1000, got {conversion_factor}"

    # Check solar_sold_power sensor
    solar_sensor = sensors["solar_sold_power"]
    zero_threshold = solar_sensor["variables"]["zero_threshold"]
    assert zero_threshold == 0, f"Expected zero_threshold=0, got {zero_threshold}"

    # Verify the basic sensors match README examples
    assert "energy_cost_current" in sensors, "energy_cost_current sensor should exist"
    assert "solar_sold_power" in sensors, "solar_sold_power sensor should exist"

    # Check that energy_cost_current has the expected formula structure
    assert energy_sensor["formula"] == "current_power * electricity_rate / conversion_factor"
    assert "current_power" in energy_sensor["variables"]
    assert "electricity_rate" in energy_sensor["variables"]

    # Check that solar_sold_power has the expected formula structure
    assert solar_sensor["formula"] == "abs(min(grid_power, zero_threshold))"
    assert "grid_power" in solar_sensor["variables"]


def test_advanced_readme_examples(mock_hass, mock_entity_registry, mock_states):
    """Test advanced README examples with attributes and device association."""

    # Load advanced examples fixture
    config_data = load_yaml_fixture("advanced_examples.yaml")
    assert config_data is not None

    # Test config validation
    config_manager = ConfigManager(mock_hass)
    validation_result = config_manager.validate_yaml_data(config_data)
    assert validation_result["valid"], f"Configuration validation failed: {validation_result.get('errors', 'Unknown error')}"

    # Check sensor with attributes
    sensors = config_data["sensors"]
    energy_analysis = sensors["energy_cost_analysis"]

    # Verify main sensor formula uses direct numeric literal division
    assert energy_analysis["formula"] == "current_power * electricity_rate / 1000"

    # Verify main sensor variables (should not include conversion_factor)
    variables = energy_analysis.get("variables", {})
    assert "current_power" in variables
    assert "electricity_rate" in variables
    # conversion_factor should NOT be a variable since 1000 is used directly in formula

    # Verify sensor has attributes
    assert "attributes" in energy_analysis
    attributes = energy_analysis["attributes"]
    assert "daily_projected" in attributes
    assert "monthly_projected" in attributes
    assert "annual_projected" in attributes

    # Verify solar inverter efficiency sensor structure
    solar_sensor = sensors["solar_inverter_efficiency"]
    assert solar_sensor["formula"] == "solar_output / solar_capacity * 100"
    assert "solar_output" in solar_sensor["variables"]
    assert "solar_capacity" in solar_sensor["variables"]

    # Check metadata
    assert solar_sensor["metadata"]["unit_of_measurement"] == "%"
    assert solar_sensor["metadata"]["device_class"] == "power_factor"


def test_numeric_literals_readme_examples(mock_hass, mock_entity_registry, mock_states):
    """Test numeric literals focused README examples."""

    # Load numeric literals examples fixture
    config_data = load_yaml_fixture("numeric_literals.yaml")
    assert config_data is not None

    # Test config validation
    config_manager = ConfigManager(mock_hass)
    validation_result = config_manager.validate_yaml_data(config_data)
    assert validation_result["valid"], f"Configuration validation failed: {validation_result.get('errors', 'Unknown error')}"

    # Test various numeric literal types
    sensors = config_data["sensors"]

    # Check temperature converter with numeric literals
    temp_converter = sensors["temperature_converter"]
    assert temp_converter["variables"]["freezing_f"] == 32
    assert temp_converter["variables"]["conversion_factor"] == 5
    assert temp_converter["variables"]["celsius_factor"] == 9

    # Check device activity score with numeric literals
    activity_score = sensors["device_activity_score"]
    assert activity_score["formula"] == "motion_sensor * 10 + door_sensor * 5 + switch_state * 2"

    # Check device info sensor with float efficiency factor
    device_info = sensors["device_info_sensor"]
    assert device_info["variables"]["efficiency_factor"] == 0.95

    # Check literal attribute values
    attributes = device_info["attributes"]
    assert attributes["voltage"] == 240
    assert attributes["manufacturer"] == "TestCorp"
    assert attributes["max_capacity"] == 5000
    assert attributes["warranty_years"] == 5
    assert attributes["is_active"] == True


if __name__ == "__main__":
    test_basic_readme_examples()
    test_advanced_readme_examples()
    test_numeric_literals_readme_examples()
