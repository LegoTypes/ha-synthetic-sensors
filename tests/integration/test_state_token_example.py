"""Integration tests for state token example YAML configuration and backing entity behavior."""

import pytest
from unittest.mock import MagicMock
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.exceptions import BackingEntityResolutionError, SensorMappingError


class TestStateTokenExample:
    """Test the state token example YAML configuration and backing entity behavior."""

    @pytest.fixture
    def config_manager(self, mock_hass, mock_entity_registry, mock_states):
        """Create a config manager with mock HA."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def state_token_example_yaml(self, load_yaml_fixture):
        """Load the state token example YAML fixture."""
        return load_yaml_fixture("state_token_example")

    def test_state_token_example_loads_correctly(self, config_manager, state_token_example_yaml):
        """Test that the state token example YAML loads without errors."""
        # Validate the YAML data
        validation_result = config_manager.validate_yaml_data(state_token_example_yaml)
        assert validation_result["valid"], (
            f"Configuration validation failed: {validation_result.get('errors', 'Unknown error')}"
        )

        # Load the config from the validated data
        config = config_manager.load_from_dict(state_token_example_yaml)

        # Verify all sensors are loaded
        assert len(config.sensors) == 4

        # Check that the test_power_with_processing sensor is present
        sensor_names = [s.name for s in config.sensors]
        assert "Processed Power" in sensor_names

        # Find the test_power_with_processing sensor
        processed_sensor = next(s for s in config.sensors if s.unique_id == "test_power_with_processing")
        assert processed_sensor.unique_id == "test_power_with_processing"
        assert processed_sensor.entity_id == "sensor.raw_power"

    def test_state_token_in_main_formula_and_attributes(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, state_token_example_yaml
    ):
        """Test that state token works correctly in both main formula and attributes."""
        # Validate and load the config
        validation_result = config_manager.validate_yaml_data(state_token_example_yaml)
        assert validation_result["valid"]
        config = config_manager.load_from_dict(state_token_example_yaml)

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
        sensor_manager.register_data_provider_entities({"sensor.raw_power"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"test_power_with_processing": "sensor.raw_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]  # First formula is the main formula

        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Main formula should succeed: state * 1.1 = 1000 * 1.1 = 1100
        # According to README: "state" in main formula refers to backing entity
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0

        # Test attribute formula evaluation with context from main result
        attribute_formula = sensor.formulas[1]  # Second formula is the amperage attribute
        context = {"state": main_result["value"]}  # Provide main sensor result as context

        attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)

        # Attribute should succeed: state / 240 = 1100 / 240 = 4.583...
        # According to README: "state" in attributes refers to main sensor's post-evaluation result
        assert attr_result["success"] is True
        assert abs(attr_result["value"] - 4.583) < 0.001  # Allow small floating point differences

        # Test efficiency attribute
        efficiency_formula = sensor.formulas[2]  # Third formula is the efficiency attribute

        efficiency_result = evaluator.evaluate_formula_with_sensor_config(efficiency_formula, context, sensor)

        # Efficiency should succeed: state / (state / 1.1) * 100 = 1100 / (1100 / 1.1) * 100 = 110
        assert efficiency_result["success"] is True
        assert abs(efficiency_result["value"] - 110.0) < 0.001

    def test_state_token_attribute_fails_without_context(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, state_token_example_yaml
    ):
        """Test that state token attribute formulas fail without proper context."""
        # Validate and load the config
        validation_result = config_manager.validate_yaml_data(state_token_example_yaml)
        assert validation_result["valid"]
        config = config_manager.load_from_dict(state_token_example_yaml)

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

        # Test attribute formula evaluation WITHOUT context
        evaluator = sensor_manager._evaluator
        attribute_formula = sensor.formulas[1]  # Second formula is the amperage attribute

        # Should fail without context
        attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, None, sensor)

        # Should fail because 'state' variable is not available
        assert attr_result["success"] is False
        assert "state" in str(attr_result["error"]).lower()

    def test_state_token_main_formula_with_self_reference(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, state_token_example_yaml
    ):
        """Test that state token main formula works with self-reference to sensor's own HA state."""
        # Validate and load the config
        validation_result = config_manager.validate_yaml_data(state_token_example_yaml)
        assert validation_result["valid"]
        config = config_manager.load_from_dict(state_token_example_yaml)

        # Find the test_power_with_processing sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_power_with_processing")

        # Setup mock HA state for the sensor's entity_id using the proper mock_states fixture
        sensor_entity_id = sensor.entity_id  # Should be "sensor.raw_power"
        mock_states[sensor_entity_id] = type(
            "MockState",
            (),
            {
                "state": "100",  # Initial state value
                "attributes": {},
            },
        )()

        # Create sensor manager WITHOUT registering backing entities
        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            mock_hass,  # Use mock_hass directly to ensure proper HA instance
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(),
        )

        # Test main formula evaluation without backing entity registration
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]  # First formula is the main formula

        # Should now succeed with state token self-reference
        # State token should resolve to sensor's own HA state (100) and multiply by 1.1 = 110
        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Should succeed with self-reference behavior
        assert result["success"] is True
        assert abs(result["value"] - 110.0) < 0.001  # 100 * 1.1 = ~110.0 (handle floating point precision)

        # Verify that the sensor's entity_id was accessed via the mock_states fixture
        # The mock_hass.states.get should have been called with the sensor's entity_id
        # This is handled by the mock_states fixture which provides the proper state lookup

    def test_state_token_example_all_sensors_have_correct_formulas(self, config_manager, state_token_example_yaml):
        """Test that all sensors in the example have the expected formulas."""
        # Validate and load the config
        validation_result = config_manager.validate_yaml_data(state_token_example_yaml)
        assert validation_result["valid"]
        config = config_manager.load_from_dict(state_token_example_yaml)

        # Check each sensor has the expected formulas
        for sensor in config.sensors:
            if sensor.unique_id == "test_current_power":
                assert len(sensor.formulas) == 2  # 1 main + 1 formula attribute (voltage is literal in main)
                main_formula = next(f for f in sensor.formulas if f.id == "test_current_power")
                amperage_formula = next(f for f in sensor.formulas if f.id == "test_current_power_amperage")
                assert main_formula.formula == "state"  # Main formula - references backing entity
                assert (
                    "voltage" in main_formula.attributes and main_formula.attributes["voltage"] == 240
                )  # Literal voltage in main formula
                assert amperage_formula.formula == "state / 240"  # Amperage attribute
            elif sensor.unique_id == "test_feed_through_power":
                assert len(sensor.formulas) == 2  # 1 main + 1 formula attribute (voltage is literal in main)
                main_formula = next(f for f in sensor.formulas if f.id == "test_feed_through_power")
                amperage_formula = next(f for f in sensor.formulas if f.id == "test_feed_through_power_amperage")
                assert main_formula.formula == "state"  # Main formula - references backing entity
                assert (
                    "voltage" in main_formula.attributes and main_formula.attributes["voltage"] == 240
                )  # Literal voltage in main formula
                assert amperage_formula.formula == "state / 240"  # Amperage attribute
            elif sensor.unique_id == "test_energy_consumed":
                assert len(sensor.formulas) == 1  # 1 main only (voltage is literal in main)
                main_formula = sensor.formulas[0]
                assert main_formula.formula == "state"  # Main formula - references backing entity
                assert (
                    "voltage" in main_formula.attributes and main_formula.attributes["voltage"] == 240
                )  # Literal voltage in main formula
            elif sensor.unique_id == "test_power_with_processing":
                assert len(sensor.formulas) == 3  # 1 main + 2 attribute formulas
                assert sensor.formulas[0].formula == "state * 1.1"  # Main formula with processing
                assert sensor.formulas[1].formula == "state / 240"  # Amperage attribute
                assert sensor.formulas[2].formula == "state / (state / 1.1) * 100"  # Efficiency attribute

    def test_backing_entity_state_token_behavior(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, state_token_example_yaml
    ):
        """Test that state token in main formula correctly references backing entity."""
        # Validate and load the config
        validation_result = config_manager.validate_yaml_data(state_token_example_yaml)
        assert validation_result["valid"]
        config = config_manager.load_from_dict(state_token_example_yaml)

        # Find the test_power_with_processing sensor (which uses state token)
        sensor = next(s for s in config.sensors if s.unique_id == "test_power_with_processing")

        # Create sensor manager with data provider
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.raw_power":
                return {"value": 500.0, "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities({"sensor.raw_power"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"test_power_with_processing": "sensor.raw_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Should succeed: state * 1.1 = 500 * 1.1 = 550
        # According to README: "state" in main formula refers to backing entity
        assert main_result["success"] is True
        assert main_result["value"] == 550.0

    def test_attribute_state_token_uses_main_sensor_result(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, state_token_example_yaml
    ):
        """Test that state token in attributes uses the main sensor's calculated result."""
        # Validate and load the config
        validation_result = config_manager.validate_yaml_data(state_token_example_yaml)
        assert validation_result["valid"]
        config = config_manager.load_from_dict(state_token_example_yaml)

        # Find the test_power_with_processing sensor (which uses state token)
        sensor = next(s for s in config.sensors if s.unique_id == "test_power_with_processing")

        # Create sensor manager with data provider
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.raw_power":
                return {"value": 500.0, "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities({"sensor.raw_power"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"test_power_with_processing": "sensor.raw_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Test attribute formula evaluation with context from main result
        attribute_formula = sensor.formulas[1]  # Second formula is the amperage attribute
        context = {"state": main_result["value"]}  # Provide main sensor result as context

        attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)

        # Should succeed: state / 240 = 550 / 240 = 2.291...
        # According to README: "state" in attributes refers to main sensor's post-evaluation result
        assert attr_result["success"] is True
        assert abs(attr_result["value"] - 2.291) < 0.001  # Allow small floating point differences

    def test_state_token_self_reference_succeeds(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, state_token_example_yaml
    ):
        """Test that state token succeeds with self-reference when no backing entity is registered."""
        # Validate and load the config
        validation_result = config_manager.validate_yaml_data(state_token_example_yaml)
        assert validation_result["valid"]
        config = config_manager.load_from_dict(state_token_example_yaml)

        # Find the test_power_with_processing sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_power_with_processing")

        # Setup mock HA state for the sensor's entity_id for self-reference
        sensor_entity_id = sensor.entity_id  # Should be "sensor.raw_power"
        mock_states[sensor_entity_id] = type(
            "MockState",
            (),
            {
                "state": "100",  # Initial state value
                "attributes": {},
            },
        )()

        # Create sensor manager WITHOUT registering the backing entity
        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            mock_hass,  # Use mock_hass directly to ensure proper HA instance
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(),
        )

        # Test main formula evaluation without backing entity registration
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should now succeed with state token self-reference
        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Should succeed with self-reference behavior
        assert result["success"] is True
        assert abs(result["value"] - 110.0) < 0.001  # 100 * 1.1 = ~110.0

    def test_self_reference_replacement_behavior(self, mock_hass, mock_entity_registry, mock_states, config_manager):
        """Test that self-references in YAML are replaced with state tokens according to design guide."""
        # This test verifies the behavior described in the design guide where:
        # - Self-references (sensor referring to itself) are replaced with 'state' token
        # - Cross-sensor references are replaced with HA entity IDs

        # Create a YAML with self-references (as described in design guide example)
        self_reference_yaml = {
            "version": "1.0",
            "sensors": {
                "base_power_sensor": {
                    "entity_id": "sensor.base_power",
                    "formula": "base_power_sensor * 1.1",  # Self-reference by sensor key
                    "attributes": {
                        "daily_power": {
                            "formula": "base_power_sensor * 24"  # Self-reference in attribute
                        }
                    },
                },
                "efficiency_calc": {
                    "formula": "base_power_sensor * 0.85",  # Cross-sensor reference
                    "attributes": {
                        "power_comparison": {
                            "formula": "efficiency_calc + base_power_sensor"  # Self + cross reference
                        }
                    },
                },
            },
        }

        # Load the configuration
        validation_result = config_manager.validate_yaml_data(self_reference_yaml)
        if not validation_result["valid"]:
            print(f"Validation failed: {validation_result.get('errors', 'Unknown error')}")
        assert validation_result["valid"]
        config = config_manager.load_from_dict(self_reference_yaml)

        # Verify that self-references are properly handled
        # Note: The actual replacement happens during cross-sensor reference resolution
        # This test verifies that the configuration loads correctly

        assert len(config.sensors) == 2

        # Check base_power_sensor
        base_sensor = next(s for s in config.sensors if s.unique_id == "base_power_sensor")
        assert base_sensor.formulas[0].formula == "base_power_sensor * 1.1"  # Original formula preserved

        # Check efficiency_calc
        efficiency_sensor = next(s for s in config.sensors if s.unique_id == "efficiency_calc")
        assert efficiency_sensor.formulas[0].formula == "base_power_sensor * 0.85"  # Cross-reference preserved

        # Note: The actual replacement of self-references with 'state' tokens
        # and cross-references with HA entity IDs happens during the cross-sensor
        # reference resolution phase, which is tested in the cross-sensor reference tests
