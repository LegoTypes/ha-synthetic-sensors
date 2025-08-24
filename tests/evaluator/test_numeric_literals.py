"""Tests for numeric literal variables in synthetic sensors.

This module tests the new feature where variables can be defined as numeric literals
instead of only entity references, enabling constants and scaling factors in formulas.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
import pytest

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.evaluator import Evaluator


@pytest.fixture
def numeric_literals_config_manager(mock_hass: HomeAssistant):
    """Fixture that loads the numeric literals test configuration."""
    config_manager = ConfigManager(mock_hass)
    config_path = Path(__file__).parent.parent / "yaml_fixtures" / "numeric_literals.yaml"
    config = config_manager.load_config(config_path)
    return config_manager, config


class TestNumericLiterals:
    """Test numeric literal variables in formulas."""

    def test_basic_numeric_literals(
        self, mock_hass: HomeAssistant, mock_entity_registry, mock_states, numeric_literals_config_manager
    ):
        """Test basic integer and float literals in variables."""
        config_manager, config = numeric_literals_config_manager
        evaluator = Evaluator(mock_hass)

        # Set the state for the entity
        mock_states.register_state("sensor.test_value", state_value="100", attributes={"device_class": "power"})

        # Register the entity with the evaluator
        evaluator.update_integration_entities({"sensor.test_value"})

        # Get the basic literals sensor config
        sensor_config = next(s for s in config.sensors if s.name == "Basic Literals Test")
        formula_config = sensor_config.formulas[0]  # Get the main formula

        # Test the formula: base_value + offset * multiplier
        # Where base_value = 100 (from entity), offset = 10, multiplier = 1.5
        # Expected: 100 + (10 * 1.5) = 100 + 15 = 115
        result = evaluator.evaluate_formula(formula_config)

        assert result["success"] is True
        assert result["value"] == 115.0

    def test_all_numeric_types(
        self, mock_hass: HomeAssistant, mock_entity_registry, mock_states, numeric_literals_config_manager
    ):
        """Test various numeric literal types (int, float, negative, zero)."""
        config_manager, config = numeric_literals_config_manager
        evaluator = Evaluator(mock_hass)

        # Get the all numeric types sensor config
        sensor_config = next(s for s in config.sensors if s.name == "All Numeric Types")
        formula_config = sensor_config.formulas[0]  # Get the main formula

        # Test the formula: int_val + float_val + negative_val + zero_val
        # Expected: 42 + 3.14159 + (-5) + 0 = 40.14159
        result = evaluator.evaluate_formula(formula_config)

        assert result["success"] is True
        assert abs(result["value"] - 40.14159) < 0.00001  # Float precision check

    def test_mixed_entity_and_literal_variables(
        self, mock_hass: HomeAssistant, mock_entity_registry, mock_states, numeric_literals_config_manager
    ):
        """Test mixing entity references with numeric literals."""
        config_manager, config = numeric_literals_config_manager
        evaluator = Evaluator(mock_hass)

        # Mock the entity references
        def mock_get_state(entity_id):
            if entity_id == "sensor.temperature":
                return MagicMock(state="25.0")
            elif entity_id == "sensor.humidity":
                return MagicMock(state="60.0")
            return None

        mock_hass.states.get.side_effect = mock_get_state

        # Get the mixed references sensor config
        sensor_config = next(s for s in config.sensors if s.name == "Mixed References")
        formula_config = sensor_config.formulas[0]  # Get the main formula

        # Test the formula: (sensor_a + sensor_b) * scale_factor + offset
        # Where sensor_a = 25.0, sensor_b = 60.0, scale_factor = 2.0, offset = 100
        # Expected: (25.0 + 60.0) * 2.0 + 100 = 85.0 * 2.0 + 100 = 170.0 + 100 = 270.0
        result = evaluator.evaluate_formula(formula_config)

        assert result["success"] is True
        assert result["value"] == 270.0

    def test_literals_in_attribute_formulas(
        self, mock_hass: HomeAssistant, mock_entity_registry, mock_states, numeric_literals_config_manager
    ):
        """Test numeric literals in attribute formulas."""
        config_manager, config = numeric_literals_config_manager
        evaluator = Evaluator(mock_hass)

        # Set the state for the entity
        mock_states.register_state("sensor.power_meter", state_value="500", attributes={"device_class": "power"})

        # Register the entity with the evaluator
        evaluator.update_integration_entities({"sensor.power_meter"})

        # Get the literals in attributes sensor config
        sensor_config = next(s for s in config.sensors if s.name == "Literals in Attributes")

        # Test the main formula
        main_formula = sensor_config.formulas[0]  # Main formula (base_power)
        result = evaluator.evaluate_formula(main_formula)
        assert result["success"] is True
        assert result["value"] == 500.0

        # Test attribute formulas with literals - they should be in the formulas list after the main formula
        attribute_formulas = sensor_config.formulas[1:]  # Skip the main formula

        # Find the efficiency_percent attribute formula
        efficiency_formula = next((f for f in attribute_formulas if f.name == "efficiency_percent"), None)
        if efficiency_formula:
            efficiency_result = evaluator.evaluate_formula(efficiency_formula)
            assert efficiency_result["success"] is True
            assert efficiency_result["value"] == 50.0  # (500 / 1000) * 100 = 50%

        # Find the cost_per_hour attribute formula
        cost_formula = next((f for f in attribute_formulas if f.name == "cost_per_hour"), None)
        if cost_formula:
            cost_result = evaluator.evaluate_formula(cost_formula)
            assert cost_result["success"] is True
            assert cost_result["value"] == 0.06  # 500 * 0.12 / 1000 = 0.06

    def test_edge_case_numbers(
        self, mock_hass: HomeAssistant, mock_entity_registry, mock_states, numeric_literals_config_manager
    ):
        """Test edge cases with very small, large, and scientific notation numbers."""
        config_manager, config = numeric_literals_config_manager
        evaluator = Evaluator(mock_hass)

        # Get the edge case numbers sensor config
        sensor_config = next(s for s in config.sensors if s.name == "Edge Case Numbers")
        formula_config = sensor_config.formulas[0]  # Get the main formula

        # Test the formula: very_small + very_large + scientific_notation
        # Expected: 0.000001 + 1000000 + 0.000123 = 1000000.000124
        result = evaluator.evaluate_formula(formula_config)

        assert result["success"] is True
        assert abs(result["value"] - 1000000.000124) < 0.0000001

    def test_boolean_numeric_literals(
        self, mock_hass: HomeAssistant, mock_entity_registry, mock_states, numeric_literals_config_manager
    ):
        """Test boolean-like numeric literals (0 and 1)."""
        config_manager, config = numeric_literals_config_manager
        evaluator = Evaluator(mock_hass)

        # Set the state for the entity
        mock_states.register_state("sensor.some_value", state_value="100", attributes={"device_class": "power"})

        # Register the entity with the evaluator
        evaluator.update_integration_entities({"sensor.some_value"})

        # Get the boolean numerics sensor config
        sensor_config = next(s for s in config.sensors if s.name == "Boolean Numerics")
        formula_config = sensor_config.formulas[0]  # Get the main formula

        # Test the formula: base_value * enabled_flag + disabled_value * disabled_flag
        # Where base_value = 100, enabled_flag = 1, disabled_value = 42, disabled_flag = 0
        # Expected: 100 * 1 + 42 * 0 = 100 + 0 = 100
        result = evaluator.evaluate_formula(formula_config)

        assert result["success"] is True
        assert result["value"] == 100.0

    def test_complex_math_with_literals(
        self, mock_hass: HomeAssistant, mock_entity_registry, mock_states, numeric_literals_config_manager
    ):
        """Test complex mathematical expressions with literals."""
        config_manager, config = numeric_literals_config_manager
        evaluator = Evaluator(mock_hass)

        # Mock the entity references
        def mock_get_state(entity_id):
            if entity_id == "sensor.x_coordinate":
                return MagicMock(state="60.0")
            elif entity_id == "sensor.y_coordinate":
                return MagicMock(state="35.0")
            return None

        mock_hass.states.get.side_effect = mock_get_state

        # Get the complex math sensor config
        sensor_config = next(s for s in config.sensors if s.name == "Complex Math with Literals")
        formula_config = sensor_config.formulas[0]  # Get the main formula

        # Test the formula: sqrt((x_val - x_offset)**2 + (y_val - y_offset)**2) * scale
        # Where x_val = 60.0, y_val = 35.0, x_offset = 50.5, y_offset = 25.0, scale = 2.5
        # Distance = sqrt((60.0 - 50.5)^2 + (35.0 - 25.0)^2) = sqrt(9.5^2 + 10^2) = sqrt(90.25 + 100) = sqrt(190.25) ≈ 13.794
        # Expected: 13.794 * 2.5 ≈ 34.485
        result = evaluator.evaluate_formula(formula_config)

        assert result["success"] is True
        assert abs(result["value"] - 34.485) < 0.01  # Allow for floating point precision

    def test_literal_variable_types_validation(self, mock_hass: HomeAssistant, mock_entity_registry, mock_states):
        """Test that literal variables are properly validated as numeric."""
        from ha_synthetic_sensors.config_manager import FormulaConfig

        evaluator = Evaluator(mock_hass)

        # Test with valid numeric context
        config = FormulaConfig(id="test_numeric", formula="a + b + c", variables={"a": 10, "b": 20.5, "c": -5})

        # Test evaluation
        result = evaluator.evaluate_formula(config)

        assert result["success"] is True
        assert result["value"] == 25.5

    def test_error_handling_for_invalid_literals(self, mock_hass: HomeAssistant, mock_entity_registry, mock_states):
        """Test error handling for invalid literal values."""
        from ha_synthetic_sensors.config_manager import FormulaConfig

        # Set up the mock_hass to use the shared entity registry
        mock_hass.entity_registry = mock_entity_registry

        evaluator = Evaluator(mock_hass)

        # Test with missing entity
        config = FormulaConfig(
            id="test_invalid",
            formula="a + b",
            variables={"a": "sensor.invalid", "b": 10},  # sensor.invalid doesn't exist in shared registry
        )

        # Mock the invalid entity to return None (entity doesn't exist)
        def mock_states_get(entity_id):
            if entity_id == "sensor.invalid":
                return None  # Entity doesn't exist
            return None

        mock_hass.states.get.side_effect = mock_states_get

        # Missing entities are now treated as non-fatal and result in unknown state
        result = evaluator.evaluate_formula(config)
        assert result["success"] is True  # Non-fatal - reflects dependency state
        # Prefer the HA constant for alternate-state assertions
        from homeassistant.const import STATE_UNKNOWN

        assert result.get("state") == STATE_UNKNOWN  # Reflects missing dependency as unknown

    def test_zero_and_negative_literals(
        self, mock_hass: HomeAssistant, mock_entity_registry, mock_states, numeric_literals_config_manager
    ):
        """Test handling of zero and negative literal values."""
        config_manager, config = numeric_literals_config_manager
        evaluator = Evaluator(mock_hass)

        # Get the all numeric types sensor config (includes zero and negative)
        sensor_config = next(s for s in config.sensors if s.name == "All Numeric Types")

        # Test that zero and negative values work correctly
        formula_config = sensor_config.formulas[0]  # Get the main formula
        result = evaluator.evaluate_formula(formula_config)

        assert result["success"] is True
        # Verify negative values and zero are handled correctly
        # int_val (42) + float_val (3.14159) + negative_val (-5) + zero_val (0) = 40.14159
        assert abs(result["value"] - 40.14159) < 0.00001

    def test_large_number_precision(self, mock_hass: HomeAssistant, mock_entity_registry, mock_states):
        """Test that large numbers maintain precision."""
        from ha_synthetic_sensors.config_manager import FormulaConfig

        evaluator = Evaluator(mock_hass)

        config = FormulaConfig(
            id="large_numbers_test",
            formula="large_int + very_large_float",
            variables={"large_int": 9999999999, "very_large_float": 1.23456789e10},
        )

        result = evaluator.evaluate_formula(config)

        assert result["success"] is True
        # Check that precision is maintained for large numbers
        expected = 9999999999 + 1.23456789e10
        assert abs(result["value"] - expected) < 1e6  # Allow for some precision loss with very large numbers
