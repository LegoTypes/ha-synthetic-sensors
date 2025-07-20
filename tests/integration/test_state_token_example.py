"""Integration tests for state token example YAML configuration."""

import pytest
from unittest.mock import MagicMock
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.exceptions import BackingEntityResolutionError, SensorMappingError


class TestStateTokenExample:
    """Test the state token example YAML configuration."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()

        # Mock states.get to return None for backing entities (simulating not registered)
        def mock_states_get(entity_id):
            return None

        hass.states.get.side_effect = mock_states_get
        return hass

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager with mock HA."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def state_token_example_yaml(self):
        """Load the state token example YAML file."""
        yaml_path = "examples/state_token_example.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    def test_state_token_example_loads_correctly(self, config_manager, state_token_example_yaml):
        """Test that the state token example YAML loads without errors."""
        config = config_manager.load_from_yaml(state_token_example_yaml)

        # Verify all sensors are loaded
        assert len(config.sensors) == 4

        # Check that the new test_power_with_processing sensor is present
        sensor_names = [s.name for s in config.sensors]
        assert "Processed Power" in sensor_names

        # Find the test_power_with_processing sensor
        processed_sensor = next(s for s in config.sensors if s.name == "Processed Power")
        assert processed_sensor.unique_id == "test_power_with_processing"
        assert processed_sensor.entity_id == "sensor.raw_power"

    def test_state_token_in_main_formula_and_attributes(self, config_manager, state_token_example_yaml):
        """Test that state token works correctly in both main formula and attributes."""
        config = config_manager.load_from_yaml(state_token_example_yaml)

        # Find the test_power_with_processing sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_power_with_processing")

        # Create sensor manager with data provider that returns data
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.raw_power":
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
        sensor_manager.register_data_provider_entities({"sensor.raw_power"}, allow_ha_lookups=False, change_notifier=None)

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"test_power_with_processing": "sensor.raw_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"test_power_with_processing": "sensor.raw_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]  # First formula is the main formula

        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Main formula should succeed: state * 1.1 = 1000 * 1.1 = 1100
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0

        # Test attribute formula evaluation with context from main result
        attribute_formula = sensor.formulas[1]  # Second formula is the amperage attribute
        context = {"state": main_result["value"]}  # Provide main sensor result as context

        attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)

        # Attribute should succeed: state / 240 = 1100 / 240 = 4.583...
        assert attr_result["success"] is True
        assert abs(attr_result["value"] - 4.583) < 0.001  # Allow small floating point differences

        # Test efficiency attribute
        efficiency_formula = sensor.formulas[2]  # Third formula is the efficiency attribute

        efficiency_result = evaluator.evaluate_formula_with_sensor_config(efficiency_formula, context, sensor)

        # Efficiency should succeed: state / (state / 1.1) * 100 = 1100 / (1100 / 1.1) * 100 = 110
        assert efficiency_result["success"] is True
        assert abs(efficiency_result["value"] - 110.0) < 0.001

    def test_state_token_attribute_fails_without_context(self, config_manager, state_token_example_yaml):
        """Test that attribute state token fails when no context is provided."""
        config = config_manager.load_from_yaml(state_token_example_yaml)

        # Find the test_power_with_processing sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_power_with_processing")

        # Create sensor manager
        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(),
        )

        # Test attribute formula evaluation without context
        evaluator = sensor_manager._evaluator
        attribute_formula = sensor.formulas[1]  # Second formula is the amperage attribute

        result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, None, sensor)

        # Should fail with specific error about state not being defined
        assert result["success"] is False
        assert "state" in result["error"].lower()
        assert "cannot be resolved" in result["error"].lower()
        assert "no backing entity mapping" in result["error"].lower()

    def test_state_token_main_formula_fails_without_backing_entity(self, config_manager, state_token_example_yaml):
        """Test that main formula state token fails when backing entity is not registered."""
        config = config_manager.load_from_yaml(state_token_example_yaml)

        # Find the test_power_with_processing sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_power_with_processing")

        # Create sensor manager WITHOUT registering the backing entity
        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(),
        )

        # Test main formula evaluation without backing entity registration
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]  # First formula is the main formula

        # Should raise SensorMappingError for missing backing entity
        with pytest.raises(SensorMappingError) as exc_info:
            evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Check the error message
        error_msg = str(exc_info.value)
        assert "backing entity" in error_msg.lower()
        assert "test_power_with_processing" in error_msg  # Now uses sensor key instead of backing entity ID
        assert "not registered" in error_msg.lower()

    def test_state_token_example_all_sensors_have_correct_formulas(self, config_manager, state_token_example_yaml):
        """Test that all sensors in the example have the expected formulas."""
        config = config_manager.load_from_yaml(state_token_example_yaml)

        # Check each sensor has the expected formulas
        for sensor in config.sensors:
            if sensor.unique_id == "test_current_power":
                assert len(sensor.formulas) == 3  # 1 main + 1 static attribute + 1 formula attribute
                assert sensor.formulas[0].formula == "state"  # Main formula
                assert sensor.formulas[1].formula == "240"  # Static voltage attribute
                assert sensor.formulas[2].formula == "state / 240"  # Amperage attribute
            elif sensor.unique_id == "test_feed_through_power":
                assert len(sensor.formulas) == 3  # 1 main + 1 static attribute + 1 formula attribute
                assert sensor.formulas[0].formula == "state"  # Main formula
                assert sensor.formulas[1].formula == "240"  # Static voltage attribute
                assert sensor.formulas[2].formula == "state / 240"  # Amperage attribute
            elif sensor.unique_id == "test_energy_consumed":
                assert len(sensor.formulas) == 2  # 1 main + 1 static attribute
                assert sensor.formulas[0].formula == "state"  # Main formula
                assert sensor.formulas[1].formula == "240"  # Static voltage attribute
            elif sensor.unique_id == "test_power_with_processing":
                assert len(sensor.formulas) == 3  # 1 main + 2 attribute formulas
                assert sensor.formulas[0].formula == "state * 1.1"  # Main formula with processing
                assert sensor.formulas[1].formula == "state / 240"  # Amperage attribute
                assert sensor.formulas[2].formula == "state / (state / 1.1) * 100"  # Efficiency attribute

    def test_self_referencing_main_formula_state_and_entity_id_interchangeable(self, config_manager, state_token_example_yaml):
        """Test that state and entity_id are interchangeable in main formulas (both reference backing entity)."""
        # Create a modified version of the example with self-referencing formulas
        modified_yaml = state_token_example_yaml.replace(
            "formula: state",
            "formula: sensor.current_power",  # Use entity_id instead of state
        )

        config = config_manager.load_from_yaml(modified_yaml)

        # Find the test_current_power sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_current_power")

        # Create sensor manager with data provider
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.current_power":
                return {"value": 1200.0, "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities({"sensor.current_power"}, allow_ha_lookups=False, change_notifier=None)

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"test_current_power": "sensor.current_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation with entity_id reference
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Should succeed and return the backing entity value
        assert main_result["success"] is True
        assert main_result["value"] == 1200.0

    def test_self_referencing_attribute_uses_main_sensor_result(self, config_manager, state_token_example_yaml):
        """Test that attributes can reference the main sensor's result using state or entity_id."""
        config = config_manager.load_from_yaml(state_token_example_yaml)

        # Find the test_power_with_processing sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_power_with_processing")

        # Create sensor manager with data provider
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.raw_power":
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
        sensor_manager.register_data_provider_entities({"sensor.raw_power"}, allow_ha_lookups=False, change_notifier=None)

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"test_power_with_processing": "sensor.raw_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # First evaluate main formula to get the processed result
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0  # 1000 * 1.1

        # Test attribute using state (should use main sensor result, not backing entity)
        amperage_formula = sensor.formulas[1]  # state / 240
        context = {"state": main_result["value"]}

        attr_result = evaluator.evaluate_formula_with_sensor_config(amperage_formula, context, sensor)
        assert attr_result["success"] is True
        assert abs(attr_result["value"] - 4.583) < 0.001  # 1100 / 240

        # Test attribute using entity_id (should also use main sensor result)
        # Create a modified attribute formula that uses entity_id instead of state
        modified_attr_formula = sensor.formulas[1]
        modified_attr_formula.formula = "sensor.raw_power / 240"  # Use entity_id instead of state

        attr_result_entity_id = evaluator.evaluate_formula_with_sensor_config(modified_attr_formula, context, sensor)
        assert attr_result_entity_id["success"] is True
        assert abs(attr_result_entity_id["value"] - 4.583) < 0.001  # Should be same as state reference

    def test_self_referencing_fails_without_backing_entity_registration(self, config_manager, state_token_example_yaml):
        """Test that self-referencing in main formula fails with BackingEntityResolutionError when backing entity not registered."""
        config = config_manager.load_from_yaml(state_token_example_yaml)

        # Find the test_power_with_processing sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_power_with_processing")

        # Create sensor manager WITHOUT registering the backing entity
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
        assert "backing entity" in error_msg.lower()
        assert "test_power_with_processing" in error_msg  # Now uses sensor key instead of backing entity ID
        assert "not registered" in error_msg.lower()
