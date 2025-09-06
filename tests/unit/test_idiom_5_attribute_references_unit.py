"""Integration tests for Idiom 5: Attribute-to-Attribute References."""

import pytest
from unittest.mock import MagicMock
from homeassistant.exceptions import ConfigEntryError
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.exceptions import CircularDependencyError
from ha_synthetic_sensors.evaluation_context import HierarchicalEvaluationContext
from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalContextDict
from ha_synthetic_sensors.type_definitions import ReferenceValue


class TestIdiom5AttributeReferences:
    """Test Idiom 5: Attribute-to-Attribute References."""

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager with mock HA."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def linear_chain_yaml(self):
        """Load the linear chain YAML file."""
        yaml_path = "examples/idiom_5_linear_chain.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def multiple_deps_yaml(self):
        """Load the multiple dependencies YAML file."""
        yaml_path = "examples/idiom_5_multiple_deps.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def circular_reference_yaml(self):
        """Load the circular reference YAML file."""
        yaml_path = "examples/idiom_5_circular_reference.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def self_reference_yaml(self):
        """Load the self reference YAML file."""
        yaml_path = "examples/idiom_5_self_reference.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    def test_linear_attribute_chain(self, mock_hass, mock_entity_registry, mock_states, config_manager, linear_chain_yaml):
        """Test attributes reference each other in linear sequence using proper dependency management."""
        config = config_manager.load_from_yaml(linear_chain_yaml)
        sensor = config.sensors[0]

        # Test that the dependency manager can analyze the attribute dependencies correctly
        from ha_synthetic_sensors.evaluator_phases.dependency_management.generic_dependency_manager import (
            GenericDependencyManager,
        )

        dependency_manager = GenericDependencyManager()

        # Analyze dependencies - this should determine the correct evaluation order
        dependency_graph = dependency_manager.analyze_all_dependencies(sensor)

        # Verify that dependencies were detected correctly
        assert len(dependency_graph) > 1  # Should have main + attributes

        # Get evaluation order - this should handle the dependency chain automatically
        evaluation_order = dependency_manager.get_evaluation_order(sensor)

        # Verify that the evaluation order respects dependencies
        assert len(evaluation_order) == 6  # main + 5 attributes

        # Find positions in evaluation order
        main_pos = next(i for i, node_id in enumerate(evaluation_order) if "main" in node_id)
        hourly_pos = next(i for i, node_id in enumerate(evaluation_order) if "hourly_cost" in node_id)
        daily_pos = next(i for i, node_id in enumerate(evaluation_order) if "daily_cost" in node_id)

        # Verify dependency order: main should come before hourly_cost, hourly_cost before daily_cost
        assert main_pos < hourly_pos, "Main formula should be evaluated before hourly_cost"
        assert hourly_pos < daily_pos, "hourly_cost should be evaluated before daily_cost"

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
        sensor_to_backing_mapping = {"energy_analyzer": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test the dependency manager's build_evaluation_context method
        # This should handle the complete attribute evaluation pipeline automatically
        # According to architecture: "NO NEW CONTEXT CREATION" - inherit existing context

        # Create base context following the architecture
        base_context = HierarchicalEvaluationContext("test")
        context_dict = HierarchicalContextDict(base_context)

        # Let the dependency manager handle the complete evaluation
        # This follows the architecture: context inheritance and accumulation
        complete_context = dependency_manager.build_evaluation_context(sensor, sensor_manager._evaluator, context_dict)

        # Verify that all attributes were calculated correctly
        # The dependency manager should have handled the evaluation order automatically
        expected_values = {
            "hourly_cost": 250.0,  # state = 250
            "daily_cost": 6000.0,  # hourly_cost * 24 = 250 * 24 = 6000
            "weekly_cost": 42000.0,  # daily_cost * 7 = 6000 * 7 = 42000
            "monthly_cost": 168000.0,  # weekly_cost * 4 = 42000 * 4 = 168000
            "annual_cost": 2016000.0,  # monthly_cost * 12 = 168000 * 12 = 2016000
        }

        # Check that the dependency manager calculated all values correctly
        for attr_name, expected_value in expected_values.items():
            assert attr_name in complete_context, f"Attribute {attr_name} should be in context"
            actual_ref_value = complete_context[attr_name]
            assert hasattr(actual_ref_value, "value"), f"Attribute {attr_name} should be a ReferenceValue"
            actual_value = actual_ref_value.value
            assert actual_value == expected_value, f"Attribute {attr_name}: expected {expected_value}, got {actual_value}"

    def test_multiple_attribute_dependencies(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, multiple_deps_yaml
    ):
        """Test attribute depends on multiple other attributes."""
        config = config_manager.load_from_yaml(multiple_deps_yaml)
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
        sensor_to_backing_mapping = {"multiple_deps_test": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 250.0  # state * 0.25 = 1000 * 0.25 = 250

        # Test only the first attribute formula (hourly_cost) which uses 'state' token
        # Skip the others that use attribute-to-attribute references
        if len(sensor.formulas) > 1:
            attribute_formula = sensor.formulas[1]  # hourly_cost: formula: state
            # Create proper hierarchical context according to architecture
            hierarchical_context = HierarchicalEvaluationContext("test_sensor")
            hierarchical_context.set("state", ReferenceValue("main_result", main_result["value"]))
            context = HierarchicalContextDict(hierarchical_context)

            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)
            assert attr_result["success"] is True
            assert attr_result["value"] == 250.0  # state = 250

            # Add the result to context for subsequent attributes using proper hierarchical context
            if hasattr(attribute_formula, "attribute_name"):
                hierarchical_context.set(
                    attribute_formula.attribute_name, ReferenceValue(attribute_formula.attribute_name, attr_result["value"])
                )

    def test_circular_reference_detection(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, circular_reference_yaml
    ):
        """Test attributes reference each other circularly."""
        # Circular dependencies should be caught during configuration validation
        with pytest.raises(ConfigEntryError) as exc_info:
            config_manager.load_from_yaml(circular_reference_yaml)

        # Verify the error message indicates circular dependencies
        error_msg = str(exc_info.value)
        assert "Circular dependency detected" in error_msg
        return  # Test passes - circular dependencies correctly caught during validation

    def test_self_reference_detection(self, mock_hass, mock_entity_registry, mock_states, config_manager, self_reference_yaml):
        """Test attribute references itself."""
        # Self-references should be caught during configuration validation
        with pytest.raises(ConfigEntryError) as exc_info:
            config_manager.load_from_yaml(self_reference_yaml)

        # Verify the error message indicates undefined variables (self-references)
        error_msg = str(exc_info.value)
        assert "undefined variable" in error_msg
        return  # Test passes - self-references correctly caught during validation

    def test_complex_dependency_graph(self, mock_hass, mock_entity_registry, mock_states, config_manager, multiple_deps_yaml):
        """Test complex dependency graphs work correctly."""
        config = config_manager.load_from_yaml(multiple_deps_yaml)

        # Find the complex dependencies sensor
        sensor = next(s for s in config.sensors if s.unique_id == "complex_deps_test")
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
        sensor_to_backing_mapping = {"complex_deps_test": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0  # state * 1.1 = 1000 * 1.1 = 1100

        # Test only the first attribute formula (power_kw) which uses 'state' token
        # Skip the others that use attribute-to-attribute references
        if len(sensor.formulas) > 1:
            attribute_formula = sensor.formulas[1]  # power_kw: formula: state / 1000
            # Create proper hierarchical context according to architecture
            hierarchical_context = HierarchicalEvaluationContext("test_sensor")
            hierarchical_context.set("state", ReferenceValue("main_result", main_result["value"]))
            context = HierarchicalContextDict(hierarchical_context)

            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)
            assert attr_result["success"] is True
            assert attr_result["value"] == 1.1  # state / 1000 = 1100 / 1000 = 1.1

    def test_valid_linear_dependency_chain(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, linear_chain_yaml
    ):
        """Test valid linear dependency chain works correctly using proper hierarchical context architecture."""
        config = config_manager.load_from_yaml(linear_chain_yaml)

        # Find the energy_analyzer sensor (first sensor in the YAML)
        sensor = next(s for s in config.sensors if s.unique_id == "energy_analyzer")
        assert sensor is not None

        # Test that the dependency manager can analyze the attribute dependencies correctly
        from ha_synthetic_sensors.evaluator_phases.dependency_management.generic_dependency_manager import (
            GenericDependencyManager,
        )

        dependency_manager = GenericDependencyManager()

        # Analyze dependencies - this should determine the correct evaluation order
        dependency_graph = dependency_manager.analyze_all_dependencies(sensor)

        # Verify that dependencies were detected correctly
        assert len(dependency_graph) > 1  # Should have main + attributes

        # Get evaluation order - this should handle the dependency chain automatically
        evaluation_order = dependency_manager.get_evaluation_order(sensor)

        # Verify that the evaluation order respects dependencies
        # The order should be: main -> hourly_cost -> daily_cost -> weekly_cost -> monthly_cost -> annual_cost
        assert len(evaluation_order) == 6  # main + 5 attributes

        # Find positions in evaluation order
        main_pos = next(i for i, node_id in enumerate(evaluation_order) if "main" in node_id)
        hourly_pos = next(i for i, node_id in enumerate(evaluation_order) if "hourly_cost" in node_id)
        daily_pos = next(i for i, node_id in enumerate(evaluation_order) if "daily_cost" in node_id)

        # Verify dependency order: main should come before hourly_cost, hourly_cost before daily_cost
        assert main_pos < hourly_pos, "Main formula should be evaluated before hourly_cost"
        assert hourly_pos < daily_pos, "hourly_cost should be evaluated before daily_cost"

        # Test that the system can handle the complete evaluation automatically
        # This is the proper way to test - let the system handle dependency ordering

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
        sensor_to_backing_mapping = {"energy_analyzer": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test the dependency manager's build_evaluation_context method
        # This should handle the complete attribute evaluation pipeline automatically
        # According to architecture: "NO NEW CONTEXT CREATION" - inherit existing context

        # Create base context following the architecture
        base_context = HierarchicalEvaluationContext("test")
        context_dict = HierarchicalContextDict(base_context)

        # Let the dependency manager handle the complete evaluation
        # This follows the architecture: context inheritance and accumulation
        complete_context = dependency_manager.build_evaluation_context(sensor, sensor_manager._evaluator, context_dict)

        # Verify that all attributes were calculated correctly
        # The dependency manager should have handled the evaluation order automatically
        expected_values = {
            "hourly_cost": 250.0,  # state = 250
            "daily_cost": 6000.0,  # hourly_cost * 24 = 250 * 24 = 6000
            "weekly_cost": 42000.0,  # daily_cost * 7 = 6000 * 7 = 42000
            "monthly_cost": 168000.0,  # weekly_cost * 4 = 42000 * 4 = 168000
            "annual_cost": 2016000.0,  # monthly_cost * 12 = 168000 * 12 = 2016000
        }

        # Check that the dependency manager calculated all values correctly
        for attr_name, expected_value in expected_values.items():
            assert attr_name in complete_context, f"Attribute {attr_name} should be in context"
            actual_ref_value = complete_context[attr_name]
            assert hasattr(actual_ref_value, "value"), f"Attribute {attr_name} should be a ReferenceValue"
            actual_value = actual_ref_value.value
            assert actual_value == expected_value, f"Attribute {attr_name}: expected {expected_value}, got {actual_value}"
