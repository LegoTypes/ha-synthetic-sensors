"""Cache context validation tests for the evaluator.

These tests validate that the cache properly differentiates between:
1. Same formula text with different variable mappings
2. Same formula text with different context values
3. Different formulas that resolve to same text after variable substitution
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator


class TestCacheContextValidation:
    """Validate cache behavior with variables and context."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()
        return hass

    def test_same_formula_different_variable_mappings(self, mock_hass):
        """Test cache with same formula text but different variable->entity mappings."""
        evaluator = Evaluator(mock_hass)

        # Two sensors with identical formula text but different variable mappings
        config1 = FormulaConfig(id="sensor_1", name="Power Sensor A", formula="power_reading + 100", variables={"power_reading": "sensor.power_meter_a"})  # Same formula text  # Different entity

        config2 = FormulaConfig(id="sensor_2", name="Power Sensor B", formula="power_reading + 100", variables={"power_reading": "sensor.power_meter_b"})  # Same formula text  # Different entity

        # Evaluate with different contexts (simulating different entity values)
        context1: dict[str, Any] = {"power_reading": 200}  # From sensor.power_meter_a
        context2: dict[str, Any] = {"power_reading": 300}  # From sensor.power_meter_b

        result1 = evaluator.evaluate_formula(config1, context1)
        result2 = evaluator.evaluate_formula(config2, context2)

        assert result1["success"] is True
        assert result1["value"] == 300  # 200 + 100

        assert result2["success"] is True
        assert result2["value"] == 400  # Should be 400 (300 + 100), NOT 300 from cache

    def test_same_formula_same_variable_names_different_values(self, mock_hass):
        """Test cache with same formula and variable names but different context values."""
        evaluator = Evaluator(mock_hass)

        # Same sensor evaluated at different times with different values
        config = FormulaConfig(id="power_sensor", name="Power Sensor", formula="current_power * efficiency_factor", variables={"current_power": "sensor.power_meter", "efficiency_factor": "input_number.efficiency"})

        # First evaluation
        context1: dict[str, Any] = {"current_power": 1000, "efficiency_factor": 0.9}
        result1 = evaluator.evaluate_formula(config, context1)

        # Second evaluation with different values (simulating entity state changes)
        context2: dict[str, Any] = {"current_power": 1500, "efficiency_factor": 0.85}
        result2 = evaluator.evaluate_formula(config, context2)

        assert result1["success"] is True
        assert result1["value"] == 900  # 1000 * 0.9

        assert result2["success"] is True
        assert result2["value"] == 1275  # Should be 1275 (1500 * 0.85), not cached 900

    def test_cache_key_includes_context_hash(self, mock_hass):
        """Test that cache keys properly include context to avoid collisions."""
        evaluator = Evaluator(mock_hass)

        config = FormulaConfig(id="test_sensor", name="Test Sensor", formula="var_a + var_b")

        # Multiple evaluations with different contexts
        test_cases = [
            ({"var_a": 10, "var_b": 20}, 30),
            ({"var_a": 100, "var_b": 200}, 300),
            ({"var_a": 5, "var_b": 15}, 20),
            ({"var_a": 10, "var_b": 20}, 30),  # Repeat first case - should be cached
        ]

        results = []
        for i, (context, expected) in enumerate(test_cases):
            context_typed: dict[str, Any] = context
            result = evaluator.evaluate_formula(config, context_typed)
            results.append(result)

            assert result["success"] is True, f"Evaluation {i} failed"
            assert result["value"] == expected, f"Evaluation {i}: expected {expected}, got {result['value']}"

        # First three should not be cached, fourth should be cached
        assert results[0].get("cached", False) is False
        assert results[1].get("cached", False) is False
        assert results[2].get("cached", False) is False
        assert results[3].get("cached", False) is True  # Should be cached repeat of first

    def test_no_context_vs_with_context_caching(self, mock_hass):
        """Test cache behavior between formulas with and without context."""
        evaluator = Evaluator(mock_hass)

        config = FormulaConfig(id="math_formula", name="Math Formula", formula="10 + 20")  # No variables

        # First evaluation without context
        result1 = evaluator.evaluate_formula(config)

        # Second evaluation with empty context
        result2 = evaluator.evaluate_formula(config, {})

        # Third evaluation without context again
        result3 = evaluator.evaluate_formula(config)

        assert result1["success"] is True
        assert result1["value"] == 30
        assert result1.get("cached", False) is False

        assert result2["success"] is True
        assert result2["value"] == 30
        # This might or might not be cached depending on implementation

        assert result3["success"] is True
        assert result3["value"] == 30
        # This should be cached if cache keys treat None and {} as equivalent

    def test_formula_with_variables_vs_resolved_formula(self, mock_hass):
        """Test if cache distinguishes between formula with variables vs resolved formula."""
        evaluator = Evaluator(mock_hass)

        # Formula with variables
        config1 = FormulaConfig(id="with_variables", name="With Variables", formula="power_input + 50", variables={"power_input": "sensor.power_meter"})

        # Formula with same resolved content but no variables
        config2 = FormulaConfig(id="resolved_formula", name="Resolved Formula", formula="100 + 50")  # Equivalent to power_input=100 + 50

        # Evaluate first with context
        context: dict[str, Any] = {"power_input": 100}
        result1 = evaluator.evaluate_formula(config1, context)

        # Evaluate second without context (direct formula)
        result2 = evaluator.evaluate_formula(config2)

        assert result1["success"] is True
        assert result1["value"] == 150

        assert result2["success"] is True
        assert result2["value"] == 150

        # These should NOT share cache entries despite same mathematical result
        assert result2.get("cached", False) is False
