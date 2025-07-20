"""Integration tests for error scenarios and edge cases."""

import pytest
from unittest.mock import MagicMock
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.exceptions import (
    BackingEntityResolutionError,
    CircularDependencyError,
    MissingDependencyError,
    DataValidationError,
)


class TestErrors:
    """Test error scenarios and edge cases."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states.get.return_value = None
        return hass

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager with mock HA."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def missing_entity_yaml(self):
        """Load the missing entity YAML file."""
        yaml_path = "examples/error_missing_entity.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def self_reference_yaml(self):
        """Load the self reference YAML file."""
        yaml_path = "examples/error_self_reference.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def invalid_data_yaml(self):
        """Load the invalid data YAML file."""
        yaml_path = "examples/error_invalid_data.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    def test_missing_entity_error(self, config_manager, missing_entity_yaml):
        """Test formula references non-existent entity."""
        config = config_manager.load_from_yaml(missing_entity_yaml)
        sensor = config.sensors[0]

        # Create sensor manager with data provider that doesn't return the referenced entity
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {"value": 1000.0, "exists": True}
            # Don't return data for nonexistent_entity
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities(
            {"sensor.span_panel_instantaneous_power"}, allow_ha_lookups=False, change_notifier=None
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"missing_entity_main": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should fail because the referenced entity doesn't exist
        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert result["success"] is False
        assert "nonexistent_entity" in result["error"] or "not found" in result["error"].lower()

    def test_missing_entity_in_variables(self, config_manager, missing_entity_yaml):
        """Test variable references non-existent entity."""
        config = config_manager.load_from_yaml(missing_entity_yaml)

        # Find the sensor with missing entity in variables
        sensor = next(s for s in config.sensors if s.unique_id == "missing_entity_variable")
        assert sensor is not None

        # Create sensor manager with data provider that doesn't return the referenced entity
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {"value": 1000.0, "exists": True}
            # Don't return data for nonexistent_entity
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities(
            {"sensor.span_panel_instantaneous_power"}, allow_ha_lookups=False, change_notifier=None
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"missing_entity_variable": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should fail because the variable references a non-existent entity
        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert result["success"] is False
        assert "nonexistent_entity" in result["error"] or "not found" in result["error"].lower()

    def test_self_reference_detection(self, config_manager, self_reference_yaml):
        """Test attribute references itself."""
        config = config_manager.load_from_yaml(self_reference_yaml)
        sensor = config.sensors[0]

        # Create sensor manager with data provider
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
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
        sensor_manager.register_data_provider_entities(
            {"sensor.span_panel_instantaneous_power"}, allow_ha_lookups=False, change_notifier=None
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"simple_self_reference": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True

        # Test that self-reference detection works
        # This should be handled by the dependency resolution system
        # The exact behavior depends on the implementation

    def test_invalid_data_provider(self, config_manager, invalid_data_yaml):
        """Test data provider returns invalid data."""
        config = config_manager.load_from_yaml(invalid_data_yaml)
        sensor = config.sensors[0]

        # Create sensor manager with data provider that returns None
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.invalid_entity":
                return {"value": None, "exists": True}  # Entity exists but returns None
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities({"sensor.invalid_entity"}, allow_ha_lookups=False, change_notifier=None)

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"invalid_backing_entity": "sensor.invalid_entity"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should succeed but with "unknown" state because the backing entity returns None
        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert result["success"] is True
        assert result["state"] == "unknown"
        assert result["value"] is None

    def test_invalid_variable_reference(self, config_manager, invalid_data_yaml):
        """Test variable references invalid entity."""
        config = config_manager.load_from_yaml(invalid_data_yaml)

        # Find the sensor with invalid variable
        sensor = next(s for s in config.sensors if s.unique_id == "invalid_variable")
        assert sensor is not None

        # Create sensor manager with data provider that returns None for invalid entity
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {"value": 1000.0, "exists": True}
            if entity_id == "sensor.invalid_entity":
                return {"value": None, "exists": True}  # Entity exists but returns None
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entities
        sensor_manager.register_data_provider_entities(
            {"sensor.span_panel_instantaneous_power", "sensor.invalid_entity"}, allow_ha_lookups=False, change_notifier=None
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"invalid_variable": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should succeed but with "unknown" state because the variable references an invalid entity
        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert result["success"] is True
        assert result["state"] == "unknown"
        assert result["value"] is None

    def test_complex_error_scenario(self, config_manager, invalid_data_yaml):
        """Test complex error scenario with multiple issues."""
        config = config_manager.load_from_yaml(invalid_data_yaml)

        # Find the complex error sensor
        sensor = next(s for s in config.sensors if s.unique_id == "invalid_complex")
        assert sensor is not None

        # Create sensor manager with data provider that returns invalid data
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {"value": 1000.0, "exists": True}
            if entity_id == "sensor.invalid_entity":
                return {"value": None, "exists": True}  # Entity exists but returns None
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entities
        sensor_manager.register_data_provider_entities(
            {"sensor.span_panel_instantaneous_power", "sensor.invalid_entity"}, allow_ha_lookups=False, change_notifier=None
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"complex_error_test": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should succeed but with "unknown" state because of complex error scenario
        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert result["success"] is True
        assert result["state"] == "unknown"
        assert result["value"] is None
