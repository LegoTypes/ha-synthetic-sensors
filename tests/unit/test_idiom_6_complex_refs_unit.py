"""Integration tests for Idiom 6: Complex Attribute References."""

import pytest
from unittest.mock import MagicMock
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig


class TestIdiom6ComplexRefs:
    """Test Idiom 6: Complex Attribute References."""

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager with mock HA."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def complex_refs_yaml(self):
        """Load the complex refs YAML file."""
        yaml_path = "examples/idiom_6_complex_refs.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def nested_attr_refs_yaml(self, load_yaml_fixture):
        """Load the nested attribute refs YAML fixture."""
        return load_yaml_fixture("nested_attr_refs")

    def test_complex_refs_main_formula(self, mock_hass, mock_entity_registry, mock_states, config_manager, complex_refs_yaml):
        """Test complex attribute references in main formula."""
        config = config_manager.load_from_yaml(complex_refs_yaml)
        sensor = config.sensors[0]

        # Create sensor manager with data provider that returns data with attributes
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {
                    "value": 1000.0,
                    "exists": True,
                    "attributes": {"voltage": 240.0, "current": 4.17, "power_factor": 0.95},
                }
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities({"sensor.span_panel_instantaneous_power"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"complex_refs_main": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Main formula should succeed: state.voltage * state.current * state.power_factor
        assert main_result["success"] is True
        expected_value = 240.0 * 4.17 * 0.95
        assert abs(main_result["value"] - expected_value) < 0.1

    def test_complex_refs_attributes(self, mock_hass, mock_entity_registry, mock_states, config_manager, complex_refs_yaml):
        """Test complex attribute references in attributes."""
        config = config_manager.load_from_yaml(complex_refs_yaml)

        # Find the complex refs attributes sensor
        sensor = next(s for s in config.sensors if s.unique_id == "complex_refs_attributes")
        assert sensor is not None

        # Create sensor manager with data provider that returns data with attributes
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {
                    "value": 1000.0,
                    "exists": True,
                    "attributes": {"voltage": 240.0, "current": 4.17, "power_factor": 0.95},
                }
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities({"sensor.span_panel_instantaneous_power"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"complex_refs_attributes": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0  # state * 1.1 = 1000 * 1.1 = 1100

        # Test attribute formulas with context from main result
        context = {"state": main_result["value"]}

        for i in range(1, len(sensor.formulas)):
            attribute_formula = sensor.formulas[i]
            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)
            assert attr_result["success"] is True

    def test_nested_attr_refs(self, mock_hass, mock_entity_registry, mock_states, config_manager, nested_attr_refs_yaml):
        """Test nested attribute references."""
        config = config_manager.load_from_dict(nested_attr_refs_yaml)

        # Find the nested attr refs sensor
        sensor = next(s for s in config.sensors if s.unique_id == "nested_attr_refs")
        assert sensor is not None

        # Create sensor manager with data provider that returns data with nested attributes
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {
                    "value": 1000.0,
                    "exists": True,
                    "attributes": {
                        "voltage": 240.0,
                        "current": 4.17,
                        "power_factor": {"value": 0.95, "unit": "ratio"},
                    },
                }
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities({"sensor.span_panel_instantaneous_power"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"nested_attr_refs": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 250.0  # state * 0.25 = 1000 * 0.25 = 250

        # Test attribute formulas with context from main result
        context = {"state": main_result["value"]}

        for i in range(1, len(sensor.formulas)):
            attribute_formula = sensor.formulas[i]
            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)
            assert attr_result["success"] is True

            # Verify specific attribute calculations
            if attribute_formula.name == "power_calculation":
                assert attr_result["value"] == 1000.8  # voltage * current = 240 * 4.17
            elif attribute_formula.name == "efficiency_calc":
                assert attr_result["value"] == 95.0  # power_factor.value * 100 = 0.95 * 100
            elif attribute_formula.name == "voltage_squared":
                assert attr_result["value"] == 57600.0  # voltage * voltage = 240 * 240

    def test_mixed_attr_patterns(self, mock_hass, mock_entity_registry, mock_states, config_manager, complex_refs_yaml):
        """Test mixed attribute reference patterns."""
        config = config_manager.load_from_yaml(complex_refs_yaml)

        # Find the mixed attr patterns sensor
        sensor = next(s for s in config.sensors if s.unique_id == "mixed_attr_patterns")
        assert sensor is not None

        # Create sensor manager with data provider that returns data with attributes
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {
                    "value": 1000.0,
                    "exists": True,
                    "attributes": {"voltage": 240.0, "current": 4.17, "power_factor": 0.95},
                }
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities({"sensor.span_panel_instantaneous_power"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"mixed_attr_patterns": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0  # state * 1.1 = 1000 * 1.1 = 1100

        # Test attribute formulas with context from main result
        context = {"state": main_result["value"]}

        for i in range(1, len(sensor.formulas)):
            attribute_formula = sensor.formulas[i]
            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)
            assert attr_result["success"] is True

    def test_complex_calculation_with_attributes(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, complex_refs_yaml
    ):
        """Test complex calculation using multiple attribute references."""
        config = config_manager.load_from_yaml(complex_refs_yaml)

        # Find the complex refs attributes sensor
        sensor = next(s for s in config.sensors if s.unique_id == "complex_refs_attributes")
        assert sensor is not None

        # Create sensor manager with data provider that returns data with attributes
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {
                    "value": 1000.0,
                    "exists": True,
                    "attributes": {"voltage": 240.0, "current": 4.17, "power_factor": 0.95},
                }
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities({"sensor.span_panel_instantaneous_power"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"complex_refs_attributes": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0  # state * 1.1 = 1000 * 1.1 = 1100

        # Test complex calculation attribute
        if len(sensor.formulas) > 4:  # Assuming complex_calculation is the 5th formula
            complex_formula = sensor.formulas[4]
            context = {"state": main_result["value"]}

            complex_result = evaluator.evaluate_formula_with_sensor_config(complex_formula, context, sensor)
            assert complex_result["success"] is True
            # Expected: (state.voltage * state.current * state.power_factor) / 1000
            expected_value = (240.0 * 4.17 * 0.95) / 1000
            assert abs(complex_result["value"] - expected_value) < 0.1
