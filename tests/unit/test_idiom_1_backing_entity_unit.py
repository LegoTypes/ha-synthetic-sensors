"""Integration tests for Idiom 1: Backing Entity State Resolution."""

import pytest
from unittest.mock import MagicMock
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.exceptions import BackingEntityResolutionError, SensorMappingError


class TestIdiom1BackingEntity:
    """Test Idiom 1: Backing Entity State Resolution."""

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager with mock HA."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def backing_entity_yaml(self):
        """Load the backing entity YAML file."""
        yaml_path = "examples/idiom_1_backing_entity.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def no_backing_entity_yaml(self):
        """Load the no backing entity YAML file."""
        yaml_path = "examples/idiom_1_no_backing_entity.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def missing_backing_entity_yaml(self):
        """Load the missing backing entity YAML file."""
        yaml_path = "examples/idiom_1_missing_backing_entity.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    def test_backing_entity_loads_correctly(
        self, config_manager, backing_entity_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test that the backing entity YAML loads without errors."""
        config = config_manager.load_from_yaml(backing_entity_yaml)

        # Verify sensors are loaded
        assert len(config.sensors) == 3

        # Find the power_analyzer sensor
        sensor = next(s for s in config.sensors if s.unique_id == "power_analyzer")
        assert sensor is not None
        assert sensor.entity_id == "sensor.span_panel_instantaneous_power"

    def test_backing_entity_state_resolution(
        self, config_manager, backing_entity_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test that state token resolves to backing entity's current value."""
        config = config_manager.load_from_yaml(backing_entity_yaml)

        # Find the power_analyzer sensor
        sensor = next(s for s in config.sensors if s.unique_id == "power_analyzer")
        assert sensor is not None

        # Create sensor manager with data provider that returns data
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
        sensor_to_backing_mapping = {"power_analyzer": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Main formula should succeed: state * 1.1 = 1000 * 1.1 = 1100
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0

    def test_no_backing_entity_state_resolution(
        self, config_manager, no_backing_entity_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test that state token resolves to sensor's previous calculated value when no backing entity."""
        config = config_manager.load_from_yaml(no_backing_entity_yaml)

        # Find the recursive calculation sensor
        sensor = next(s for s in config.sensors if s.unique_id == "power_trend")
        assert sensor is not None

        # Create sensor manager without backing entity registration
        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(),
        )

        # Register the dependency entity so the test can focus on state token behavior
        sensor_manager.register_data_provider_entities(
            {"sensor.current_power_reading"}, allow_ha_lookups=False, change_notifier=None
        )

        # Provide data for the dependency
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.current_power_reading":
                return {"value": 1000.0, "exists": True}
            return {"value": None, "exists": False}

        sensor_manager.evaluator._dependency_handler.data_provider_callback = mock_data_provider

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should fail because no backing entity and no previous value
        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert result["success"] is False
        assert "state" in result["error"].lower()

    def test_missing_backing_entity_error(
        self, config_manager, missing_backing_entity_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test that BackingEntityResolutionError is raised when backing entity doesn't exist."""
        config = config_manager.load_from_yaml(missing_backing_entity_yaml)
        sensor = config.sensors[0]

        # Create sensor manager without registering the backing entity
        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(),
        )

        # Test main formula evaluation without backing entity registration
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should raise SensorMappingError for missing backing entity
        with pytest.raises(SensorMappingError) as exc_info:
            evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Check the error message
        error_msg = str(exc_info.value)
        assert "sensor key" in error_msg.lower()
        assert "problematic_sensor" in error_msg
        assert "not registered" in error_msg.lower()

    def test_backing_entity_with_attributes(
        self, config_manager, backing_entity_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test backing entity with attributes that reference main sensor state."""
        config = config_manager.load_from_yaml(backing_entity_yaml)

        # Find the power_analyzer sensor
        sensor = next(s for s in config.sensors if s.unique_id == "power_analyzer")
        assert sensor is not None

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
        sensor_to_backing_mapping = {"power_analyzer": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0

        # Test attribute formula evaluation with context from main result
        if len(sensor.formulas) > 1:
            attribute_formula = sensor.formulas[1]
            context = {"state": main_result["value"]}

            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)
            assert attr_result["success"] is True
