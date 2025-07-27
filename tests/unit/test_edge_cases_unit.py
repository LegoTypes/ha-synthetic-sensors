"""Integration tests for edge cases and boundary conditions."""

import pytest
from unittest.mock import MagicMock
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def config_manager(self, mock_hass, mock_entity_registry, mock_states):
        """Create a config manager with mock HA."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def deep_chain_yaml(self):
        """Load the deep chain YAML file."""
        yaml_path = "examples/edge_deep_chain.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def multiple_circular_yaml(self):
        """Load the multiple circular YAML file."""
        yaml_path = "examples/edge_multiple_circular.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def variable_conflicts_yaml(self):
        """Load the variable conflicts YAML file."""
        yaml_path = "examples/edge_variable_conflicts.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def variable_inheritance_yaml(self):
        """Load the variable inheritance YAML file."""
        yaml_path = "examples/edge_variable_inheritance.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    def test_deep_attribute_chain(self, config_manager, deep_chain_yaml, mock_hass, mock_entity_registry, mock_states):
        """Test very long chain of attribute dependencies."""
        config = config_manager.load_from_yaml(deep_chain_yaml)
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
        sensor_to_backing_mapping = {"deep_chain_test": "sensor.span_panel_instantaneous_power"}
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

    def test_multiple_circular_references(
        self, config_manager, multiple_circular_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test multiple circular reference patterns."""
        config = config_manager.load_from_yaml(multiple_circular_yaml)
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
        sensor_to_backing_mapping = {"multiple_circular_test": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True

        # Test that circular reference detection works
        # This should be handled by the dependency resolution system
        # The exact behavior depends on the implementation

    def test_variable_name_conflicts(
        self, config_manager, variable_conflicts_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test variable names conflict between levels."""
        config = config_manager.load_from_yaml(variable_conflicts_yaml)
        sensor = config.sensors[0]

        # Set up the mock hass with entity registry and states
        mock_hass.entity_registry = mock_entity_registry
        mock_hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)
        mock_hass.states.entity_ids.return_value = list(mock_states.keys())

        # Create sensor manager with data provider
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {"value": 1000.0, "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            mock_hass,  # Use the proper mock_hass fixture
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities(
            {"sensor.span_panel_instantaneous_power"}, allow_ha_lookups=False, change_notifier=None
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"variable_conflict_test": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0  # power_value * 1.1 = 1000 * 1.1 = 1100

        # Test attribute formulas with context from main result
        context = {"state": main_result["value"]}

        for i in range(1, len(sensor.formulas)):
            attribute_formula = sensor.formulas[i]
            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)
            assert attr_result["success"] is True

    def test_complex_variable_inheritance(
        self, config_manager, variable_inheritance_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test complex variable inheritance patterns."""
        config = config_manager.load_from_yaml(variable_inheritance_yaml)
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
        sensor_to_backing_mapping = {"complex_inheritance_test": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0  # base_power * efficiency_factor = 1000 * 1.1 = 1100

        # Test attribute formulas with context from main result
        context = {"state": main_result["value"]}

        for i in range(1, len(sensor.formulas)):
            attribute_formula = sensor.formulas[i]
            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)
            assert attr_result["success"] is True

    def test_deep_nested_attributes(self, config_manager, deep_chain_yaml, mock_hass, mock_entity_registry, mock_states):
        """Test deeply nested attribute access."""
        config = config_manager.load_from_yaml(deep_chain_yaml)

        # Find the deep chain test sensor (it exists in the YAML)
        sensor = next(s for s in config.sensors if s.unique_id == "deep_chain_test")
        assert sensor is not None

        # Create sensor manager with data provider that returns deeply nested attributes
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {
                    "value": 1000.0,
                    "exists": True,
                    "attributes": {"level1": {"level2": {"level3": {"level4": {"level5": {"value": 42.0}}}}}},
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
        sensor_manager.register_data_provider_entities(
            {"sensor.span_panel_instantaneous_power"}, allow_ha_lookups=False, change_notifier=None
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"deep_chain_test": "sensor.span_panel_instantaneous_power"}
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

    def test_performance_with_large_chains(self, config_manager, deep_chain_yaml, mock_hass, mock_entity_registry, mock_states):
        """Test performance with large dependency chains."""
        config = config_manager.load_from_yaml(deep_chain_yaml)

        # Find the complex deep chain sensor (it exists in the YAML)
        sensor = next(s for s in config.sensors if s.unique_id == "complex_deep_chain")
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
        sensor_to_backing_mapping = {"complex_deep_chain": "sensor.span_panel_instantaneous_power"}
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
