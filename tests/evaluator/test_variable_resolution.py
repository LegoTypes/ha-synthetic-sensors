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

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance with entity states."""
        hass = MagicMock()

        # Mock entity states for testing
        def mock_states_get(entity_id):
            state_values = {
                # SPAN Panel solar circuit entities
                "sensor.span_panel_circuit_30_power": MagicMock(state="1000"),
                "sensor.span_panel_circuit_32_power": MagicMock(state="500"),
                "sensor.span_panel_circuit_30_energy_produced": MagicMock(state="24000"),
                "sensor.span_panel_circuit_32_energy_produced": MagicMock(state="12000"),
                # Other test entities
                "sensor.power_meter": MagicMock(state="800"),
                "input_number.efficiency": MagicMock(state="1.2"),
                "sensor.unavailable_entity": None,  # Simulate unavailable entity
            }
            state_obj = state_values.get(entity_id)
            if state_obj:
                state_obj.entity_id = entity_id
            return state_obj

        hass.states.get.side_effect = mock_states_get
        return hass

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager with mock hass."""
        return ConfigManager(mock_hass)

    def test_formula_config_with_variables(self, mock_hass):
        """Test that FormulaConfig with variables can be evaluated correctly."""
        evaluator = Evaluator(mock_hass, allow_ha_lookups=True)

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

    def test_dynamic_sensor_variable_resolution(self, mock_hass, config_manager):
        """Test that DynamicSensor correctly resolves variables from formula config."""
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

        dynamic_sensor = DynamicSensor(
            mock_hass,
            sensor_config,
            evaluator,
            mock_sensor_manager,
            SensorManagerConfig(),
        )

        # Test the _build_variable_context method
        formula_config = sensor_config.formulas[0]
        context = dynamic_sensor._build_variable_context(formula_config)

        assert context is not None
        assert "leg1_power" in context
        assert "leg2_power" in context
        assert context["leg1_power"] == 1000.0
        assert context["leg2_power"] == 500.0

        # Test that the sensor can evaluate the formula correctly
        evaluator = Evaluator(mock_hass)
        main_context = dynamic_sensor._build_variable_context(formula_config)
        main_result = evaluator.evaluate_formula(formula_config, main_context)

        # Verify the evaluation worked
        assert main_result["success"] is True
        assert main_result["value"] == 1500.0

    def test_variable_resolution_with_unavailable_entity(self, mock_hass):
        """Test variable resolution when one entity is unavailable."""
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
        context = {}
        for var_name, entity_id in config.variables.items():
            state = mock_hass.states.get(entity_id)
            if state is not None:
                context[var_name] = float(state.state)
            else:
                context[var_name] = None

        # Should handle None values gracefully
        assert context["available_power"] == 1000.0
        assert context["unavailable_power"] is None

        # The evaluator should handle None values appropriately
        result = evaluator.evaluate_formula(config, context)
        # This might fail or return a specific error depending on how None is handled
        # The important thing is that it doesn't crash
        assert result is not None  # Should return some result, even if it's an error

    def test_multiple_formulas_with_different_variables(self, mock_hass, config_manager):
        """Test sensor with multiple formulas that have different variable sets."""
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

        dynamic_sensor = DynamicSensor(
            mock_hass,
            sensor_config,
            evaluator,
            mock_sensor_manager,
            SensorManagerConfig(),
        )

        # Test context building for both formulas
        main_context = dynamic_sensor._build_variable_context(main_formula)
        attr_context = dynamic_sensor._build_variable_context(attr_formula)

        assert main_context is not None
        assert attr_context is not None
        assert main_context["leg1_power"] == 1000.0
        assert main_context["leg2_power"] == 500.0

        assert attr_context["base_power"] == 800.0
        assert attr_context["efficiency_factor"] == 1.2

    def test_formula_without_variables(self, mock_hass):
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
