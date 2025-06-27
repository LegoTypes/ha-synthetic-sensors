#!/usr/bin/env python3
"""Test script to verify README examples work correctly."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import yaml

from ha_synthetic_sensors.config_manager import ConfigManager


def load_yaml_fixture(fixture_name: str) -> dict[str, Any]:
    """Load a YAML fixture file from the readme_examples directory."""
    fixture_path = Path(__file__).parent / "yaml_fixtures" / "readme_examples" / fixture_name
    with open(fixture_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_basic_readme_examples():
    """Test basic README examples are valid YAML and can be parsed correctly."""

    # Mock hass object
    hass = MagicMock()
    hass.states.get = MagicMock()

    # Load basic examples fixture
    config_data = load_yaml_fixture("basic_examples.yaml")
    assert config_data is not None

    # Test config validation
    config_manager = ConfigManager(hass)
    validation_result = config_manager.validate_yaml_data(config_data)
    assert validation_result["valid"], f"Configuration validation failed: {validation_result.get('errors', 'Unknown error')}"

    # Check that we have the expected number of sensors
    sensors_count = len(config_data.get("sensors", {}))
    assert sensors_count == 4, f"Expected 4 sensors, got {sensors_count}"

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

    # Check temperature_converter sensor
    temp_sensor = sensors["temperature_converter"]
    freezing_f = temp_sensor["variables"]["freezing_f"]
    conversion_factor = temp_sensor["variables"]["conversion_factor"]
    celsius_factor = temp_sensor["variables"]["celsius_factor"]

    assert freezing_f == 32, f"Expected freezing_f=32, got {freezing_f}"
    assert conversion_factor == 5, f"Expected conversion_factor=5, got {conversion_factor}"
    assert celsius_factor == 9, f"Expected celsius_factor=9, got {celsius_factor}"

    # Check power_efficiency sensor
    power_sensor = sensors["power_efficiency"]
    rated_power = power_sensor["variables"]["rated_power"]
    percentage = power_sensor["variables"]["percentage"]

    assert rated_power == 1000, f"Expected rated_power=1000, got {rated_power}"
    assert percentage == 100, f"Expected percentage=100, got {percentage}"


def test_advanced_readme_examples():
    """Test advanced README examples with attributes and device association."""

    # Mock hass object
    hass = MagicMock()
    hass.states.get = MagicMock()

    # Load advanced examples fixture
    config_data = load_yaml_fixture("advanced_examples.yaml")
    assert config_data is not None

    # Test config validation
    config_manager = ConfigManager(hass)
    validation_result = config_manager.validate_yaml_data(config_data)
    assert validation_result["valid"], f"Configuration validation failed: {validation_result.get('errors', 'Unknown error')}"

    # Check sensor with attributes
    sensors = config_data["sensors"]
    energy_analysis = sensors["energy_cost_analysis"]

    # Verify main sensor has numeric literal
    assert energy_analysis["variables"]["conversion_factor"] == 1000

    # Verify sensor has attributes
    assert "attributes" in energy_analysis
    attributes = energy_analysis["attributes"]
    assert "daily_projected" in attributes
    assert "monthly_projected" in attributes
    assert "annual_projected" in attributes

    # Check device association sensor
    solar_sensor = sensors["solar_inverter_efficiency"]
    assert solar_sensor["variables"]["percentage_factor"] == 100
    assert solar_sensor["device_identifier"] == "solar_inverter_001"
    assert solar_sensor["device_name"] == "Solar Inverter"


def test_numeric_literals_readme_examples():
    """Test numeric literals focused README examples."""

    # Mock hass object
    hass = MagicMock()
    hass.states.get = MagicMock()

    # Load numeric literals examples fixture
    config_data = load_yaml_fixture("numeric_literals.yaml")
    assert config_data is not None

    # Test config validation
    config_manager = ConfigManager(hass)
    validation_result = config_manager.validate_yaml_data(config_data)
    assert validation_result["valid"], f"Configuration validation failed: {validation_result.get('errors', 'Unknown error')}"

    # Test various numeric literal types
    sensors = config_data["sensors"]

    # Check cost calculator with float literals
    cost_calc = sensors["cost_calculator"]
    assert cost_calc["variables"]["rate_per_kwh"] == 0.12
    assert cost_calc["variables"]["tax_rate"] == 0.085

    # Check mixed calculations with different number types
    mixed_calc = sensors["mixed_calculations"]
    variables = mixed_calc["variables"]
    assert variables["multiplier"] == 2.5  # float
    assert variables["offset"] == 10  # int
    assert variables["discount"] == -5.0  # negative float


if __name__ == "__main__":
    test_basic_readme_examples()
    test_advanced_readme_examples()
    test_numeric_literals_readme_examples()
