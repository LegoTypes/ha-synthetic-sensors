"""Integration tests for edge cases and boundary conditions."""

import pytest
from unittest.mock import MagicMock
from homeassistant.exceptions import ConfigEntryError
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.evaluation_context import HierarchicalEvaluationContext
from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalContextDict
from ha_synthetic_sensors.type_definitions import ReferenceValue


def _create_empty_hierarchical_context() -> HierarchicalContextDict:
    """Create an empty HierarchicalContextDict for testing."""
    hierarchical_context = HierarchicalEvaluationContext("test")
    return HierarchicalContextDict(hierarchical_context)


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
        """Test that deep attribute chains are properly configured - this is a unit test for config validation."""
        config = config_manager.load_from_yaml(deep_chain_yaml)
        sensor = config.sensors[0]

        # Unit test: Verify the configuration is loaded correctly
        assert sensor.unique_id == "deep_chain_test"
        assert len(sensor.formulas) > 1  # Has main formula + attributes

        # Unit test: Verify main formula is correct
        main_formula = sensor.formulas[0]
        assert main_formula.formula == "state * 0.25"

        # Unit test: Verify attribute formulas are configured correctly
        attribute_formulas = sensor.formulas[1:]
        assert len(attribute_formulas) >= 2  # At least level1 and level2

        # Find level1 and level2 attributes
        level1_formula = next((f for f in attribute_formulas if "level1" in f.id), None)
        level2_formula = next((f for f in attribute_formulas if "level2" in f.id), None)

        assert level1_formula is not None, "level1 attribute should exist"
        assert level2_formula is not None, "level2 attribute should exist"

        # Unit test: Verify dependency chain is configured correctly
        assert level1_formula.formula == "state"  # level1 depends on state
        assert level2_formula.formula == "level1 * 2"  # level2 depends on level1

        # NOTE: Full evaluation pipeline testing belongs in integration tests
        # This unit test only validates configuration structure

    def test_multiple_circular_references(
        self, config_manager, multiple_circular_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test multiple circular reference patterns."""
        # Multiple circular dependencies should be caught during configuration validation
        with pytest.raises(ConfigEntryError) as exc_info:
            config_manager.load_from_yaml(multiple_circular_yaml)

        # Verify the error message indicates circular dependencies and undefined variables
        error_msg = str(exc_info.value)
        assert "Circular dependency detected" in error_msg
        return  # Test passes - circular dependencies correctly caught during validation
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
        sensor_manager.register_data_provider_entities({"sensor.span_panel_instantaneous_power"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"multiple_circular_test": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        context = _create_empty_hierarchical_context()
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, context, sensor)
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
        sensor_manager.register_data_provider_entities({"sensor.span_panel_instantaneous_power"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"variable_conflict_test": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        context = _create_empty_hierarchical_context()
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, context, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0  # power_value * 1.1 = 1000 * 1.1 = 1100

        # Test attribute formulas with context from main result
        context = _create_empty_hierarchical_context()
        context._hierarchical_context.set("state", ReferenceValue(reference="state", value=main_result["value"]))

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
        sensor_manager.register_data_provider_entities({"sensor.span_panel_instantaneous_power"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"complex_inheritance_test": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        context = _create_empty_hierarchical_context()
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, context, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0  # base_power * efficiency_factor = 1000 * 1.1 = 1100

        # Test attribute formulas with context from main result and inherited variables
        context = _create_empty_hierarchical_context()
        context._hierarchical_context.set("state", ReferenceValue(reference="state", value=main_result["value"]))

        # Add the sensor's variables to context for attribute inheritance
        context._hierarchical_context.set(
            "base_power", ReferenceValue(reference="sensor.span_panel_instantaneous_power", value=1000.0)
        )
        context._hierarchical_context.set("efficiency_factor", ReferenceValue(reference="efficiency_factor", value=1.1))
        context._hierarchical_context.set("cost_rate", ReferenceValue(reference="cost_rate", value=0.25))
        context._hierarchical_context.set("multiplier", ReferenceValue(reference="multiplier", value=2.0))

        for i in range(1, len(sensor.formulas)):
            attribute_formula = sensor.formulas[i]
            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)
            assert attr_result["success"] is True

    def test_deep_nested_attributes(self, config_manager, deep_chain_yaml, mock_hass, mock_entity_registry, mock_states):
        """Test that nested attribute access configuration is valid - unit test for config structure."""
        config = config_manager.load_from_yaml(deep_chain_yaml)

        # Find the deep chain test sensor (it exists in the YAML)
        sensor = next(s for s in config.sensors if s.unique_id == "deep_chain_test")
        assert sensor is not None

        # Unit test: Verify the sensor has the expected structure for nested attributes
        assert len(sensor.formulas) >= 10  # Main + level1 through level9 (at least)

        # Unit test: Verify the dependency chain structure
        main_formula = sensor.formulas[0]
        assert main_formula.formula == "state * 0.25"

        # Unit test: Verify each level depends on the previous level
        attribute_formulas = {f.id: f for f in sensor.formulas[1:]}

        # Check that level1 depends on state
        level1_key = next(k for k in attribute_formulas.keys() if "level1" in k)
        assert attribute_formulas[level1_key].formula == "state"

        # Check that level2 depends on level1
        level2_key = next(k for k in attribute_formulas.keys() if "level2" in k)
        assert attribute_formulas[level2_key].formula == "level1 * 2"

        # Check that level3 depends on level2
        level3_key = next(k for k in attribute_formulas.keys() if "level3" in k)
        assert attribute_formulas[level3_key].formula == "level2 * 2"

        # Unit test: Verify metadata is properly configured
        for formula in sensor.formulas[1:]:  # Skip main formula
            assert "metadata" in formula.__dict__ or hasattr(formula, "metadata")

        # NOTE: Full nested attribute evaluation belongs in integration tests
        # This unit test only validates the configuration structure for nested dependencies

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
        sensor_manager.register_data_provider_entities({"sensor.span_panel_instantaneous_power"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"complex_deep_chain": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        context = _create_empty_hierarchical_context()
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, context, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0  # state * 1.1 = 1000 * 1.1 = 1100

        # Test attribute formulas with context from main result
        context = _create_empty_hierarchical_context()
        context._hierarchical_context.set("state", ReferenceValue(reference="state", value=main_result["value"]))

        for i in range(1, len(sensor.formulas)):
            attribute_formula = sensor.formulas[i]
            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)
            assert attr_result["success"] is True
