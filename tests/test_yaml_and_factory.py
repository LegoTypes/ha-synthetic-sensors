"""Tests for YAML-based configuration loading and EntityFactory functionality."""

from pathlib import Path
import tempfile
from unittest.mock import MagicMock

import pytest
import yaml

from ha_synthetic_sensors.entity_factory import EntityDescription, EntityFactory


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
        assert "global_settings" in config
        assert config["global_settings"]["domain_prefix"] == "syn2"
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
        assert variables["hvac_total"] == "sensor.syn2_hvac_total_power"
        assert variables["lighting_total"] == "sensor.syn2_lighting_total_power"

    def test_load_cost_analysis_yaml(self, cost_analysis_yaml):
        """Test loading cost analysis YAML configuration."""
        config = cost_analysis_yaml

        # Verify structure
        assert config["version"] == "1.0"
        assert len(config["sensors"]) == 1

        sensors = config["sensors"]
        assert "current_energy_cost_rate" in sensors
        sensor = sensors["current_energy_cost_rate"]
        assert sensor["device_class"] == "monetary"
        assert sensor["unit_of_measurement"] == "$/h"

    def test_load_simple_test_yaml(self, simple_test_yaml):
        """Test loading simple test YAML configuration."""
        config = simple_test_yaml

        # Verify structure (v2.0 format)
        assert config["version"] == "1.0"
        assert len(config["sensors"]) == 2

        # Test basic formula (v2.0 format with dict sensors)
        sensors = config["sensors"]
        assert "simple_test_sensor" in sensors
        basic_sensor = sensors["simple_test_sensor"]
        assert basic_sensor["formula"] == "var_a + var_b"

    def test_yaml_to_service_integration(self, mock_hass, solar_analytics_yaml):
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


class TestEntityFactory:
    """Test cases for EntityFactory functionality."""

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

    @pytest.fixture
    def entity_factory(self, mock_hass, mock_name_resolver):
        """Create an EntityFactory instance."""
        return EntityFactory(mock_hass, mock_name_resolver)

    def test_entity_factory_creation(self, entity_factory):
        """Test EntityFactory can be created."""
        assert entity_factory is not None
        assert hasattr(entity_factory, "_hass")
        assert hasattr(entity_factory, "_name_resolver")

    def test_generate_unique_id(self, entity_factory):
        """Test unique ID generation patterns."""
        # Test simple sensor ID
        unique_id = entity_factory.generate_unique_id("solar_sold_positive")
        assert unique_id == "syn2_solar_sold_positive"

        # Test sensor with formula ID
        unique_id = entity_factory.generate_unique_id("solar_sold_positive", "solar_sold")
        assert unique_id == "syn2_solar_sold_positive_solar_sold"

    def test_generate_entity_id(self, entity_factory):
        """Test entity ID generation patterns."""
        # Test simple sensor
        entity_id = entity_factory.generate_entity_id("solar_sold_positive")
        assert entity_id == "sensor.syn2_solar_sold_positive"

        # Test sensor with formula
        entity_id = entity_factory.generate_entity_id("solar_sold_positive", "solar_sold")
        assert entity_id == "sensor.syn2_solar_sold_positive_solar_sold"

    def test_create_entity_description(self, entity_factory):
        """Test creating entity descriptions from configuration."""
        sensor_config = {"unique_id": "test_sensor", "name": "Test Sensor"}

        formula_config = {
            "id": "test_formula",
            "name": "Test Formula",
            "unit_of_measurement": "W",
            "device_class": "power",
            "state_class": "measurement",
            "icon": "mdi:flash",
        }

        description = entity_factory.create_entity_description(sensor_config, formula_config)

        assert isinstance(description, EntityDescription)
        assert description.unique_id == "syn2_test_sensor_test_formula"
        assert description.entity_id == "sensor.syn2_test_sensor_test_formula"
        assert description.name == "Test Formula"  # Formula name takes priority
        assert description.unit_of_measurement == "W"
        assert description.device_class == "power"
        assert description.state_class == "measurement"
        assert description.icon == "mdi:flash"

    def test_create_entity_description_fallback_names(self, entity_factory):
        """Test entity description with fallback naming."""
        # Test with sensor name only (no formula name)
        sensor_config = {"unique_id": "test_sensor", "name": "Test Sensor"}

        formula_config = {"id": "test_formula", "unit_of_measurement": "W"}

        description = entity_factory.create_entity_description(sensor_config, formula_config)
        assert description.name == "Test Sensor"  # Falls back to sensor name

        # Test with unique_id only (no names)
        sensor_config = {"unique_id": "test_sensor"}

        description = entity_factory.create_entity_description(sensor_config, formula_config)
        assert description.name == "syn2_test_sensor_test_formula"  # Falls back to unique_id

    def test_create_sensor_entity(self, entity_factory):
        """Test creating sensor entities."""
        sensor_config = {
            "unique_id": "test_sensor",
            "name": "Test Sensor",
            "formula": "A + B",
        }

        result = entity_factory.create_sensor_entity(sensor_config)

        # Should return an EntityCreationResult with success and entity
        assert result is not None
        assert result["success"] is True
        assert result["entity"] is not None
        assert len(result["errors"]) == 0
        assert hasattr(result["entity"], "unique_id")
        assert result["entity"].unique_id == "test_sensor"

    def test_validate_entity_configuration(self, entity_factory):
        """Test entity configuration validation."""
        # Valid configuration (v2.0 format)
        valid_config = {
            "unique_id": "test_sensor",
            "formula": "A + B",
        }

        result = entity_factory.validate_entity_configuration(valid_config)
        assert result["is_valid"]
        assert len(result["errors"]) == 0

        # Invalid configuration (missing unique_id and formula)
        invalid_config = {}

        result = entity_factory.validate_entity_configuration(invalid_config)
        assert not result["is_valid"]
        assert len(result["errors"]) > 0
        assert any("unique_id" in error for error in result["errors"])
        assert any("formula" in error for error in result["errors"])

    def test_entity_factory_with_yaml_config(self, entity_factory, solar_analytics_yaml):
        """Test EntityFactory with real YAML configuration."""
        config = solar_analytics_yaml

        # Iterate over sensors dict (v2.0 format)
        for sensor_key, sensor_config in config["sensors"].items():
            # Test entity description creation (no formula config since it's inline)
            description = entity_factory.create_entity_description({"unique_id": sensor_key, **sensor_config})

            # Verify the generated IDs follow the simplified v2.0 pattern
            expected_unique_id = f"syn2_{sensor_key}"
            expected_entity_id = f"sensor.{expected_unique_id}"

            assert description.unique_id == expected_unique_id
            assert description.entity_id == expected_entity_id

            # Verify metadata is preserved
            if sensor_config.get("unit_of_measurement"):
                assert description.unit_of_measurement == sensor_config["unit_of_measurement"]
            if sensor_config.get("device_class"):
                assert description.device_class == sensor_config["device_class"]
