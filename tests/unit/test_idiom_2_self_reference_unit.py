"""Integration tests for Idiom 2: Self-Reference Patterns."""

import pytest
from unittest.mock import MagicMock
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig


class TestIdiom2SelfReference:
    """Test Idiom 2: Self-Reference Patterns."""

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager with mock HA."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def state_token_yaml(self):
        """Load the state token YAML file."""
        yaml_path = "examples/idiom_2_state_token.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def sensor_key_yaml(self):
        """Load the main formula state YAML file."""
        yaml_path = "examples/idiom_2_main_formula_state.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def entity_id_yaml(self):
        """Load the entity ID YAML file."""
        yaml_path = "examples/idiom_2_entity_id.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    def test_state_token_reference(self, config_manager, state_token_yaml, mock_hass, mock_entity_registry, mock_states):
        """Test that state token resolves to backing entity value."""
        config = config_manager.load_from_yaml(state_token_yaml)
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
        sensor_to_backing_mapping = {"power_calculator": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Main formula should succeed: state * 2 = 1000 * 2 = 2000
        assert main_result["success"] is True
        assert main_result["value"] == 2000.0

    def test_sensor_key_reference(self, config_manager, sensor_key_yaml, mock_hass, mock_entity_registry, mock_states):
        """Test that sensor key name resolves to backing entity value."""
        config = config_manager.load_from_yaml(sensor_key_yaml)
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
        sensor_to_backing_mapping = {"power_calculator": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Main formula should succeed: power_calculator * 2 = 1000 * 2 = 2000
        assert main_result["success"] is True
        assert main_result["value"] == 2000.0

    # @pytest.mark.skip(reason="Entity ID self-reference not yet supported by evaluator")
    def test_entity_id_reference(self, config_manager, entity_id_yaml, mock_hass, mock_entity_registry, mock_states):
        """Test that full entity ID resolves to backing entity value."""
        config = config_manager.load_from_yaml(entity_id_yaml)
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
        sensor_to_backing_mapping = {"power_calculator": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Main formula should succeed: sensor.power_calculator * 2 = 1000 * 2 = 2000
        assert main_result["success"] is True
        assert main_result["value"] == 2000.0

    def test_self_reference_without_backing_entity(self, config_manager, mock_hass, mock_entity_registry, mock_states):
        """Test self-reference behavior when no backing entity is configured."""
        # Load YAML for sensor without backing entity
        from pathlib import Path

        yaml_fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "unit_test_idioms_self_reference_no_backing.yaml"
        with open(yaml_fixture_path, "r") as f:
            yaml_content = f.read()
        config = config_manager.load_from_yaml(yaml_content)
        sensor = config.sensors[0]

        # Create sensor manager
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.current_power":
                return {"value": 1000.0, "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the external entity
        sensor_manager.register_data_provider_entities({"sensor.current_power"})

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should fail because no previous value and no backing entity
        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert result["success"] is False
        assert "state" in result["error"].lower()

    def test_self_reference_in_attributes(self, config_manager, mock_hass, mock_entity_registry, mock_states):
        """Test self-reference patterns in attribute formulas."""
        from pathlib import Path

        yaml_fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "unit_test_idioms_self_reference_attributes.yaml"
        with open(yaml_fixture_path, "r") as f:
            yaml_content = f.read()
        config = config_manager.load_from_yaml(yaml_content)
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
        sensor_to_backing_mapping = {"power_analyzer": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0

        # Test attribute formulas with context from main result
        context = {"state": main_result["value"]}

        # Test daily_power attribute (state token)
        if len(sensor.formulas) > 1:
            daily_formula = sensor.formulas[1]
            daily_result = evaluator.evaluate_formula_with_sensor_config(daily_formula, context, sensor)
            assert daily_result["success"] is True
            assert daily_result["value"] == 26400.0  # 1100 * 24

        # Note: Sensor key and entity ID references in attributes are not yet supported
        # These would need to be tested once the evaluator supports them
