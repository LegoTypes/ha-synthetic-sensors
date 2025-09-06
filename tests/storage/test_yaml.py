"""Tests for YAML-based configuration loading and EntityFactory functionality."""

from pathlib import Path
import tempfile
from unittest.mock import MagicMock

import pytest
import yaml


class TestYamlConfigurationLoading:
    """Test cases for loading YAML configurations from actual files."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()
        hass.config = MagicMock()
        hass.config.config_dir = "/config"
        return hass

    @pytest.fixture
    def mock_name_resolver(self):
        """Create a mock name resolver."""
        name_resolver = MagicMock()
        name_resolver.resolve_entity_id = MagicMock(return_value="sensor.resolved_entity")
        name_resolver.normalize_name = MagicMock(side_effect=lambda x: x.lower().replace(" ", "_"))
        return name_resolver

    def test_load_solar_analytics_yaml(self, solar_analytics_yaml):
        """Test loading solar analytics YAML configuration."""
        config = solar_analytics_yaml

        # Verify basic structure
        assert config["version"] == "1.0"
        assert "sensors" in config
        assert len(config["sensors"]) == 2

        # Verify first sensor (solar_sold_positive) - now using dict format
        sensors = config["sensors"]
        assert "solar_sold_positive" in sensors
        first_sensor = sensors["solar_sold_positive"]
        assert first_sensor["name"] == "Solar Sold (Positive Value)"
        assert first_sensor["formula"] == "abs(min(grid_power, 0))"
        assert "grid_power" in first_sensor["variables"]
        assert first_sensor["variables"]["grid_power"] == "sensor.span_panel_current_power"

    def test_load_hierarchical_calculations_yaml(self, hierarchical_calculations_yaml):
        """Test loading hierarchical calculations YAML configuration."""
        config = hierarchical_calculations_yaml

        # Verify structure
        assert config["version"] == "1.0"
        assert len(config["sensors"]) == 3

        # Find the parent sensor that references other synthetic sensors
        sensors = config["sensors"]
        assert "total_home_consumption" in sensors
        parent_sensor = sensors["total_home_consumption"]
        assert parent_sensor is not None

        variables = parent_sensor["variables"]

        # Verify it references other synthetic sensors by entity ID (simplified v2.0
        # format)
        assert variables["hvac_total"] == "sensor.hvac_total_power"
        assert variables["lighting_total"] == "sensor.lighting_total_power"

    def test_load_cost_analysis_yaml(self, cost_analysis_yaml):
        """Test loading cost analysis YAML configuration."""
        config = cost_analysis_yaml

        # Verify structure
        assert config["version"] == "1.0"
        assert len(config["sensors"]) == 1

        sensors = config["sensors"]
        assert "current_energy_cost_rate" in sensors
        sensor = sensors["current_energy_cost_rate"]
        assert sensor["metadata"]["device_class"] == "monetary"
        assert sensor["metadata"]["unit_of_measurement"] == "$/h"

    def test_load_simple_test_yaml(self, simple_test_yaml):
        """Test loading simple test YAML configuration."""
        config = simple_test_yaml

        assert config["version"] == "1.0"
        assert len(config["sensors"]) == 2

        # Test basic formula (v2.0 format with dict sensors)
        sensors = config["sensors"]
        assert "simple_test_sensor" in sensors
        basic_sensor = sensors["simple_test_sensor"]
        assert basic_sensor["formula"] == "var_a + var_b"

    def test_yaml_to_service_integration(self, mock_hass, mock_entity_registry, mock_states, solar_analytics_yaml):
        """Test that YAML configuration can be used with service layer."""
        from ha_synthetic_sensors.config_manager import ConfigManager

        # Create a temporary YAML file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(solar_analytics_yaml, f)
            temp_path = f.name

        try:
            # Load configuration using ConfigManager
            config_manager = ConfigManager(mock_hass)
            config = config_manager.load_config(temp_path)

            # Verify the configuration was loaded correctly
            assert config is not None
            assert len(config.sensors) == 2

            # Verify sensor IDs match the entity_id focused approach (order may vary)
            sensor_unique_ids = {sensor.unique_id for sensor in config.sensors}
            assert "solar_sold_positive" in sensor_unique_ids
            assert "solar_self_consumption_rate" in sensor_unique_ids

        finally:
            Path(temp_path).unlink()

    def test_yaml_configuration_with_service_call_simulation(self, simple_test_yaml):
        """Test simulating a service call with YAML content."""
        # Simulate the service call data structure
        service_call_data = {"config": yaml.dump(simple_test_yaml)}

        # Verify the YAML can be parsed back
        parsed_config = yaml.safe_load(service_call_data["config"])
        assert parsed_config["version"] == "1.0"
        assert len(parsed_config["sensors"]) == 2
