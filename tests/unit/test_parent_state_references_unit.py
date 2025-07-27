"""Tests for valid parent state references in attribute formulas."""

import pytest
from unittest.mock import MagicMock
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig


class TestParentStateReferences:
    """Test valid parent state references in attribute formulas."""

    @pytest.fixture
    def config_manager(self, mock_hass, mock_entity_registry, mock_states):
        """Create a config manager with mock HA."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def parent_state_reference_yaml(self):
        """YAML with attribute that references parent sensor state (avoiding decimals)."""
        return """
sensors:
  simple_parent_reference:
    entity_id: sensor.span_panel_instantaneous_power
    formula: state * 2  # Main result = 2000 (assuming 1000W backing entity)
    attributes:
      # Reference to parent sensor state - should resolve to main sensor value
      doubled_state:
        formula: simple_parent_reference * 3  # Should be 2000 * 3 = 6000
        metadata:
          unit_of_measurement: W
          friendly_name: "Doubled State"
    metadata:
      unit_of_measurement: W
      device_class: power
      friendly_name: "Simple Parent Reference"
"""

    def test_attribute_references_parent_state(
        self, config_manager, parent_state_reference_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test that attribute can reference parent sensor's calculated state value."""
        config = config_manager.load_from_yaml(parent_state_reference_yaml)
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

        # Register the backing entity from common fixture
        sensor_manager.register_data_provider_entities(
            {"sensor.span_panel_instantaneous_power"}, allow_ha_lookups=False, change_notifier=None
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"simple_parent_reference": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Main formula should succeed: state * 2 = 1000 * 2 = 2000
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 2000.0

        # Test attribute formula that references parent state
        attribute_formula = sensor.formulas[1]  # doubled_state formula

        # Provide the main result as context for attribute evaluation
        # The self-reference should be replaced with 'state' which resolves to this context value
        context = {"state": main_result["value"]}

        # Attribute formula should succeed: simple_parent_reference -> state * 3 = 2000 * 3 = 6000
        # Bypass dependency management to test the cross-sensor reference replacement directly
        attr_result = evaluator.evaluate_formula_with_sensor_config(
            attribute_formula, context, sensor, bypass_dependency_management=True
        )
        assert attr_result["success"] is True
        assert attr_result["value"] == 6000.0

    def test_multiple_attributes_reference_parent(self, config_manager, mock_hass, mock_entity_registry, mock_states):
        """Test multiple attributes referencing parent sensor state."""
        from pathlib import Path

        yaml_fixture_path = (
            Path(__file__).parent.parent / "yaml_fixtures" / "unit_test_idioms_parent_state_multiple_attributes.yaml"
        )
        with open(yaml_fixture_path, "r") as f:
            yaml_content = f.read()

        config = config_manager.load_from_yaml(yaml_content)
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

        # Register the backing entity and mapping
        sensor_manager.register_data_provider_entities(
            {"sensor.span_panel_instantaneous_power"}, allow_ha_lookups=False, change_notifier=None
        )
        sensor_to_backing_mapping = {"multi_attribute_parent": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula: state * 5 = 1000 * 5 = 5000
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 5000.0

        # Test all attribute formulas with main result as context
        context = {"state": main_result["value"]}

        # doubled: multi_attribute_parent * 2 = 5000 * 2 = 10000
        doubled_formula = sensor.formulas[1]
        doubled_result = evaluator.evaluate_formula_with_sensor_config(
            doubled_formula, context, sensor, bypass_dependency_management=True
        )
        assert doubled_result["success"] is True
        assert doubled_result["value"] == 10000.0

        # tripled: multi_attribute_parent * 3 = 5000 * 3 = 15000
        tripled_formula = sensor.formulas[2]
        tripled_result = evaluator.evaluate_formula_with_sensor_config(
            tripled_formula, context, sensor, bypass_dependency_management=True
        )
        assert tripled_result["success"] is True
        assert tripled_result["value"] == 15000.0

        # halved: multi_attribute_parent / 2 = 5000 / 2 = 2500
        halved_formula = sensor.formulas[3]
        halved_result = evaluator.evaluate_formula_with_sensor_config(
            halved_formula, context, sensor, bypass_dependency_management=True
        )
        assert halved_result["success"] is True
        assert halved_result["value"] == 2500.0
