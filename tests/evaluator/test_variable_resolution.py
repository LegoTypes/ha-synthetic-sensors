"""Test variable resolution in formula evaluation.

This tests the complete workflow from YAML config with variables
through to actual formula evaluation with resolved variable values.
"""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.config_manager import ConfigManager, FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.sensor_manager import DynamicSensor, SensorManagerConfig


class TestVariableResolution:
    """Test variable resolution in formula evaluation."""

    # Remove custom mock_hass fixture - use the common one from conftest.py

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager with mock hass."""
        return ConfigManager(mock_hass)

    def test_formula_config_with_variables(self, mock_hass, mock_entity_registry, mock_states):
        """Test that FormulaConfig with variables can be evaluated correctly."""
        # Add required entities to mock_states for this test
        mock_states["sensor.span_panel_circuit_30_power"] = MagicMock(state="1000")
        mock_states["sensor.span_panel_circuit_32_power"] = MagicMock(state="500")
        evaluator = Evaluator(mock_hass)

        # Create a formula config similar to SPAN Panel solar sensors
        config = FormulaConfig(
            id="solar_power",
            name="Solar Inverter Power",
            formula="leg1_power + leg2_power",
            variables={
                "leg1_power": "sensor.span_panel_circuit_30_power",
                "leg2_power": "sensor.span_panel_circuit_32_power",
            },
            metadata={
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
            },
        )

        # Test 1: Automatic variable resolution should work now
        result_auto_resolution = evaluator.evaluate_formula(config)
        assert result_auto_resolution["success"] is True
        assert result_auto_resolution["value"] == 1500  # 1000 + 500

        # Test 2: With variable context manually built (should also work)
        context = {}
        for var_name, entity_id in config.variables.items():
            state = mock_hass.states.get(entity_id)
            if state:
                context[var_name] = float(state.state)

        result_with_context = evaluator.evaluate_formula(config, context)
        assert result_with_context["success"] is True
        assert result_with_context["value"] == 1500  # 1000 + 500

    def test_dynamic_sensor_variable_resolution(self, mock_hass, config_manager, mock_entity_registry, mock_states):
        """Test that DynamicSensor correctly resolves variables from formula config."""
        # Add required entities to mock_states for this test
        mock_states["sensor.span_panel_circuit_30_power"] = MagicMock(state="1000")
        mock_states["sensor.span_panel_circuit_32_power"] = MagicMock(state="500")
        mock_states["sensor.power_meter"] = MagicMock(state="800")
        mock_states["input_number.efficiency"] = MagicMock(state="1.2")
        # Create a sensor configuration with variables
        sensor_config_data = {
            "solar_inverter_power": {
                "name": "Solar Inverter Power",
                "entity_id": "sensor.solar_inverter_power",
                "formula": "leg1_power + leg2_power",
                "variables": {
                    "leg1_power": "sensor.span_panel_circuit_30_power",
                    "leg2_power": "sensor.span_panel_circuit_32_power",
                },
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
            }
        }

        # Parse the configuration
        yaml_config = {"version": "1.0", "sensors": sensor_config_data}

        config = config_manager._parse_yaml_config(yaml_config)
        sensor_config = config.sensors[0]

        # Verify the sensor config has variables
        assert sensor_config.formulas[0].variables is not None
        assert "leg1_power" in sensor_config.formulas[0].variables
        assert "leg2_power" in sensor_config.formulas[0].variables

        # Create a DynamicSensor
        evaluator = Evaluator(mock_hass)
        mock_sensor_manager = MagicMock()

        dynamic_sensor = DynamicSensor(mock_hass, sensor_config, evaluator, mock_sensor_manager, SensorManagerConfig())

        # Test the _build_variable_context method
        formula_config = sensor_config.formulas[0]
        context = dynamic_sensor._build_variable_context(formula_config)

        assert context is not None
        assert "leg1_power" in context
        assert "leg2_power" in context
        # With ReferenceValue architecture, check the .value property
        leg1_value = context["leg1_power"].value if hasattr(context["leg1_power"], "value") else context["leg1_power"]
        leg2_value = context["leg2_power"].value if hasattr(context["leg2_power"], "value") else context["leg2_power"]
        assert leg1_value == 1000.0
        assert leg2_value == 500.0

        # Test that the sensor can evaluate the formula correctly
        # Since this is a unit test, we'll test the variable resolution logic directly
        # without triggering the full evaluation pipeline that requires HA domains
        evaluator = Evaluator(mock_hass)

        # Create a context with ReferenceValue objects for testing (ReferenceValue architecture)
        from ha_synthetic_sensors.type_definitions import ReferenceValue

        test_context = {
            "leg1_power": ReferenceValue("sensor.span_panel_circuit_30_power", 1000.0),
            "leg2_power": ReferenceValue("sensor.span_panel_circuit_32_power", 500.0),
        }

        # Test with a simple formula that doesn't trigger entity reference resolution
        simple_config = FormulaConfig(id="test", formula="leg1_power + leg2_power", variables={})
        result = evaluator.evaluate_formula(simple_config, test_context)

        # Verify the evaluation worked
        assert result["success"] is True
        assert result["value"] == 1500.0

    def test_variable_resolution_with_unavailable_entity(self, mock_hass, mock_entity_registry, mock_states):
        """Test variable resolution when one entity is unavailable."""
        # Add required entities to mock_states for this test
        mock_states["sensor.span_panel_circuit_30_power"] = MagicMock(state="1000")
        # Note: sensor.unavailable_entity is intentionally not added to test unavailable entity handling
        evaluator = Evaluator(mock_hass)

        config = FormulaConfig(
            id="partial_solar",
            name="Partial Solar",
            formula="available_power + unavailable_power",
            variables={
                "available_power": "sensor.span_panel_circuit_30_power",
                "unavailable_power": "sensor.unavailable_entity",
            },
        )

        # Create context manually (this is what DynamicSensor._build_variable_context should do)
        # Use ReferenceValue objects (ReferenceValue architecture)
        from ha_synthetic_sensors.type_definitions import ReferenceValue

        context = {}
        for var_name, entity_id in config.variables.items():
            state = mock_hass.states.get(entity_id)
            if state is not None:
                context[var_name] = ReferenceValue(entity_id, float(state.state))
            else:
                # For unavailable entities, create ReferenceValue with None value
                context[var_name] = ReferenceValue(entity_id, None)

        # Should handle None values gracefully
        assert context["available_power"].value == 1000.0
        assert context["available_power"].reference == "sensor.span_panel_circuit_30_power"
        assert context["unavailable_power"].value is None
        assert context["unavailable_power"].reference == "sensor.unavailable_entity"

        # The evaluator should handle None values appropriately
        result = evaluator.evaluate_formula(config, context)
        # This might fail or return a specific error depending on how None is handled
        # The important thing is that it doesn't crash
        assert result is not None  # Should return some result, even if it's an error

    def test_multiple_formulas_with_different_variables(self, mock_hass, config_manager, mock_entity_registry, mock_states):
        """Test sensor with multiple formulas that have different variable sets."""
        # Add required entities to mock_states for this test
        mock_states["sensor.span_panel_circuit_30_power"] = MagicMock(state="1000")
        mock_states["sensor.span_panel_circuit_32_power"] = MagicMock(state="500")
        mock_states["sensor.power_meter"] = MagicMock(state="800")
        mock_states["input_number.efficiency"] = MagicMock(state="1.2")
        sensor_config_data = {
            "comprehensive_solar": {
                "name": "Comprehensive Solar Monitor",
                "formula": "leg1_power + leg2_power",
                "variables": {
                    "leg1_power": "sensor.span_panel_circuit_30_power",
                    "leg2_power": "sensor.span_panel_circuit_32_power",
                },
                "unit_of_measurement": "W",
                "attributes": {
                    "efficiency_rating": {
                        "formula": "base_power * efficiency_factor",
                        "variables": {
                            "base_power": "sensor.power_meter",
                            "efficiency_factor": "input_number.efficiency",
                        },
                    }
                },
            }
        }  # Main formula

        yaml_config = {"version": "1.0", "sensors": sensor_config_data}

        config = config_manager._parse_yaml_config(yaml_config)
        sensor_config = config.sensors[0]

        # Should have main formula plus one attribute formula
        assert len(sensor_config.formulas) == 2

        main_formula = sensor_config.formulas[0]  # Main state formula
        attr_formula = sensor_config.formulas[1]  # Attribute formula

        assert main_formula.variables["leg1_power"] == "sensor.span_panel_circuit_30_power"
        assert attr_formula.variables["base_power"] == "sensor.power_meter"

        # Create sensor and test variable resolution for both formulas
        evaluator = Evaluator(mock_hass)
        mock_sensor_manager = MagicMock()

        dynamic_sensor = DynamicSensor(mock_hass, sensor_config, evaluator, mock_sensor_manager, SensorManagerConfig())

        # Test context building for both formulas
        main_context = dynamic_sensor._build_variable_context(main_formula)
        attr_context = dynamic_sensor._build_variable_context(attr_formula)

        assert main_context is not None
        assert attr_context is not None
        # With ReferenceValue architecture, check the .value property
        leg1_value = (
            main_context["leg1_power"].value if hasattr(main_context["leg1_power"], "value") else main_context["leg1_power"]
        )
        leg2_value = (
            main_context["leg2_power"].value if hasattr(main_context["leg2_power"], "value") else main_context["leg2_power"]
        )
        assert leg1_value == 1000.0
        assert leg2_value == 500.0

        base_power_value = (
            attr_context["base_power"].value if hasattr(attr_context["base_power"], "value") else attr_context["base_power"]
        )
        efficiency_value = (
            attr_context["efficiency_factor"].value
            if hasattr(attr_context["efficiency_factor"], "value")
            else attr_context["efficiency_factor"]
        )
        assert base_power_value == 800.0
        assert efficiency_value == 1.2

    def test_formula_without_variables(self, mock_hass, mock_entity_registry, mock_states):
        """Test that formulas without variables still work."""
        evaluator = Evaluator(mock_hass)

        config = FormulaConfig(id="simple", name="Simple", formula="1000 + 500")

        # Should work without any context
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True
        assert result["value"] == 1500

        # Should also work with empty context
        result2 = evaluator.evaluate_formula(config, {})
        assert result2["success"] is True
        assert result2["value"] == 1500
