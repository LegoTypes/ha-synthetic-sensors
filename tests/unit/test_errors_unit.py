"""Integration tests for error scenarios and edge cases."""

import pytest
from unittest.mock import MagicMock
from homeassistant.exceptions import ConfigEntryError
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.exceptions import (
    BackingEntityResolutionError,
    CircularDependencyError,
    MissingDependencyError,
    DataValidationError,
    SensorMappingError,
)


class TestErrors:
    """Test error scenarios and edge cases."""

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
    def state_token_yaml(self):
        """Load the state token reference YAML file."""
        yaml_path = "examples/state_token_reference.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def invalid_data_yaml(self):
        """Load the invalid data YAML file."""
        yaml_path = "examples/error_invalid_data.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    def test_missing_entity_error(self, config_manager, missing_entity_yaml, mock_hass, mock_entity_registry, mock_states):
        """Test formula references non-existent entity."""
        config = config_manager.load_from_yaml(missing_entity_yaml)
        sensor = config.sensors[0]

        # Create sensor manager with data provider that uses common fixture
        def mock_data_provider(entity_id: str):
            if entity_id in mock_states:
                state = mock_states[entity_id]
                return {
                    "value": float(state.state) if state.state.replace(".", "").replace("-", "").isdigit() else state.state,
                    "exists": True,
                }
            # Don't return data for nonexistent_entity
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity from common fixture
        sensor_manager.register_data_provider_entities({"sensor.span_panel_instantaneous_power"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"missing_entity_main": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should raise MissingDependencyError because the referenced entity doesn't exist
        # According to the reference guide: "Fatal errors are never silently converted to error results"
        with pytest.raises(MissingDependencyError) as exc_info:
            evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        assert ".nonexistent_entity" in str(exc_info.value)

    def test_missing_entity_in_variables(
        self, config_manager, missing_entity_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test formula references non-existent entity through variables."""
        config = config_manager.load_from_yaml(missing_entity_yaml)
        sensor = config.sensors[0]

        # Create sensor manager with data provider that uses common fixture
        def mock_data_provider(entity_id: str):
            if entity_id in mock_states:
                state = mock_states[entity_id]
                return {
                    "value": float(state.state) if state.state.replace(".", "").replace("-", "").isdigit() else state.state,
                    "exists": True,
                }
            # Don't return data for nonexistent_entity
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            mock_hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should fail during entity resolution phase with MissingDependencyError
        with pytest.raises(MissingDependencyError) as exc_info:
            evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Check that the error message contains the missing entity reference (adjusted for actual format)
        error_msg = str(exc_info.value)
        assert "nonexistent_entity" in error_msg  # The actual error shows ".nonexistent_entity"

    def test_self_reference_detection(self, config_manager, self_reference_yaml, mock_hass, mock_entity_registry, mock_states):
        """Test self-reference detection in formulas."""
        # Self-references are circular dependencies and should be caught during configuration validation
        # The YAML contains formulas like: self_ref_attr: formula: "self_ref_attr * 1.1"
        with pytest.raises(ConfigEntryError) as exc_info:
            config_manager.load_from_yaml(self_reference_yaml)

        # Check that the error message indicates undefined variables (self-references)
        error_msg = str(exc_info.value)
        assert "self_ref_attr" in error_msg
        assert "undefined variable" in error_msg

    def test_self_reference_without_backing_entity(
        self, config_manager, state_token_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test that state token reference works without explicit backing entity registration."""
        config = config_manager.load_from_yaml(state_token_yaml)
        sensor = config.sensors[0]

        # Create sensor manager with data provider that uses common fixture
        def mock_data_provider(entity_id: str):
            if entity_id in mock_states:
                state = mock_states[entity_id]
                return {
                    "value": float(state.state) if state.state.replace(".", "").replace("-", "").isdigit() else state.state,
                    "exists": True,
                }
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            mock_hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Set up mock state for the sensor's own entity_id
        sensor_entity_id = sensor.entity_id  # Should be "sensor.span_panel_instantaneous_power"
        mock_states[sensor_entity_id] = type(
            "MockState",
            (),
            {
                "state": "1000",  # Initial state value
                "attributes": {"voltage": "240"},
            },
        )()

        # Test main formula evaluation without backing entity registration
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should succeed with state token self-reference behavior
        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Verify success and correct calculation (1000 * 0.25 = 250)
        assert result["success"] is True
        assert abs(result["value"] - 250.0) < 0.001  # Handle floating point precision

    def test_invalid_data_provider(self, config_manager, invalid_data_yaml, mock_hass, mock_entity_registry, mock_states):
        """Test data provider returns invalid data."""
        config = config_manager.load_from_yaml(invalid_data_yaml)
        # Use the correct sensor ID from the YAML
        sensor = next(s for s in config.sensors if s.unique_id == "invalid_backing_entity")

        # Create sensor manager with data provider that returns None
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.invalid_entity":
                return {"value": None, "exists": True}  # Entity exists but returns None
            if entity_id in mock_states:
                state = mock_states[entity_id]
                return {
                    "value": float(state.state) if state.state.replace(".", "").replace("-", "").isdigit() else state.state,
                    "exists": True,
                }
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity from common fixture
        sensor_manager.register_data_provider_entities({"sensor.invalid_entity"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"invalid_backing_entity": "sensor.invalid_entity"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should handle None values appropriately - the implementation determines exact behavior
        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        # The result should indicate the evaluation completed but with None/unknown state
        assert result["success"] is True
        # Current behavior: None values remain as None when no explicit alternate state handlers configured
        assert result["value"] is None

    def test_invalid_variable_reference(self, config_manager, invalid_data_yaml, mock_hass, mock_entity_registry, mock_states):
        """Test variable references entity that returns invalid data."""
        config = config_manager.load_from_yaml(invalid_data_yaml)

        # Find the sensor with invalid variable reference - use correct ID from YAML
        sensor = next(s for s in config.sensors if s.unique_id == "invalid_variable")
        assert sensor is not None

        # Create sensor manager with data provider that returns None for invalid entity
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.invalid_entity":
                return {"value": None, "exists": True}  # Entity exists but returns None
            if entity_id in mock_states:
                state = mock_states[entity_id]
                return {
                    "value": float(state.state) if state.state.replace(".", "").replace("-", "").isdigit() else state.state,
                    "exists": True,
                }
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity from common fixture
        sensor_manager.register_data_provider_entities({"sensor.span_panel_instantaneous_power", "sensor.invalid_entity"})

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"invalid_variable": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should handle None values appropriately - the implementation determines exact behavior
        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        # The result should indicate the evaluation completed but with None/unknown state
        assert result["success"] is True
        # Current behavior: None values remain as None when no explicit alternate state handlers configured
        assert result["value"] is None

    def test_complex_error_scenario(self, config_manager, invalid_data_yaml, mock_hass, mock_entity_registry, mock_states):
        """Test complex error scenario with state token self-reference."""
        config = config_manager.load_from_yaml(invalid_data_yaml)
        sensor = config.sensors[0]

        # Create sensor manager with data provider that uses common fixture
        def mock_data_provider(entity_id: str):
            if entity_id in mock_states:
                state = mock_states[entity_id]
                return {
                    "value": float(state.state) if state.state.replace(".", "").replace("-", "").isdigit() else state.state,
                    "exists": True,
                }
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            mock_hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Set up mock state for the sensor's own entity_id
        sensor_entity_id = sensor.entity_id  # Should be "sensor.invalid_entity"
        mock_states[sensor_entity_id] = type(
            "MockState",
            (),
            {
                "state": "500",  # Initial state value
                "attributes": {},
            },
        )()

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should succeed with state token self-reference behavior
        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Verify success and correct calculation (500 * 2 = 1000)
        assert result["success"] is True
        assert abs(result["value"] - 1000.0) < 0.001  # Handle floating point precision
