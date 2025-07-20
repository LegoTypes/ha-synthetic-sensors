"""Tests for cross-sensor reference functionality."""

import pytest
from unittest.mock import MagicMock

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig


class TestCrossSensorReferences:
    """Test cross-sensor reference functionality."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states.get.return_value = None
        return hass

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def simple_cross_sensor_yaml(self):
        """Load a simple cross-sensor YAML configuration."""
        return """
sensors:
  # Base sensor that others will reference
  base_sensor:
    entity_id: sensor.backing_entity
    formula: state * 1.0  # Pass through backing entity value
    metadata:
      unit_of_measurement: W
      device_class: power
      friendly_name: "Base Sensor"

  # Sensor that references base sensor
  derived_sensor:
    entity_id: sensor.backing_entity
    formula: base_sensor * 1.1  # References base_sensor
    metadata:
      unit_of_measurement: W
      device_class: power
      friendly_name: "Derived Sensor"
"""

    def test_simple_cross_sensor_reference(self, config_manager, simple_cross_sensor_yaml):
        """Test simple cross-sensor reference functionality."""
        config = config_manager.load_from_yaml(simple_cross_sensor_yaml)

        # Create sensor manager with data provider
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.backing_entity":
                return {"value": 1000.0, "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities({"sensor.backing_entity"}, allow_ha_lookups=False, change_notifier=None)

        # Register the sensor-to-backing mappings
        sensor_to_backing_mapping = {
            "base_sensor": "sensor.backing_entity",
            "derived_sensor": "sensor.backing_entity",
        }
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test evaluator
        evaluator = sensor_manager._evaluator

        # Test base sensor first
        base_sensor = next(s for s in config.sensors if s.unique_id == "base_sensor")
        base_formula = base_sensor.formulas[0]
        base_result = evaluator.evaluate_formula_with_sensor_config(base_formula, None, base_sensor)
        assert base_result["success"] is True
        assert base_result["value"] == 1000.0  # state * 1.0 = 1000 * 1.0 = 1000

        # Register the base sensor in the cross-sensor registry
        evaluator.register_sensor("base_sensor", "sensor.base_sensor", base_result["value"])

        # Test derived sensor (should reference base_sensor)
        derived_sensor = next(s for s in config.sensors if s.unique_id == "derived_sensor")
        derived_formula = derived_sensor.formulas[0]
        derived_result = evaluator.evaluate_formula_with_sensor_config(derived_formula, None, derived_sensor)
        assert derived_result["success"] is True
        assert derived_result["value"] == 1100.0  # base_sensor * 1.1 = 1000 * 1.1 = 1100

    def test_cross_sensor_reference_with_attributes(self, config_manager, simple_cross_sensor_yaml):
        """Test cross-sensor references in attribute formulas."""
        config = config_manager.load_from_yaml(simple_cross_sensor_yaml)

        # Create sensor manager with data provider
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.backing_entity":
                return {"value": 1000.0, "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities({"sensor.backing_entity"}, allow_ha_lookups=False, change_notifier=None)

        # Register the sensor-to-backing mappings
        sensor_to_backing_mapping = {
            "base_sensor": "sensor.backing_entity",
            "derived_sensor": "sensor.backing_entity",
        }
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test evaluator
        evaluator = sensor_manager._evaluator

        # Test base sensor first
        base_sensor = next(s for s in config.sensors if s.unique_id == "base_sensor")
        base_formula = base_sensor.formulas[0]
        base_result = evaluator.evaluate_formula_with_sensor_config(base_formula, None, base_sensor)
        assert base_result["success"] is True
        assert base_result["value"] == 1000.0

        # Register the base sensor in the cross-sensor registry
        evaluator.register_sensor("base_sensor", "sensor.base_sensor", base_result["value"])

        # Test derived sensor
        derived_sensor = next(s for s in config.sensors if s.unique_id == "derived_sensor")
        derived_formula = derived_sensor.formulas[0]
        derived_result = evaluator.evaluate_formula_with_sensor_config(derived_formula, None, derived_sensor)
        assert derived_result["success"] is True
        assert derived_result["value"] == 1100.0

        # Register the derived sensor in the cross-sensor registry
        evaluator.register_sensor("derived_sensor", "sensor.derived_sensor", derived_result["value"])

        # Test that both sensors are registered
        registered_sensors = evaluator.get_registered_sensors()
        assert "base_sensor" in registered_sensors
        assert "derived_sensor" in registered_sensors

        # Test that we can get their values
        assert evaluator.get_sensor_value("base_sensor") == 1000.0
        assert evaluator.get_sensor_value("derived_sensor") == 1100.0
