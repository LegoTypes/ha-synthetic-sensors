"""Tests for synthetic sensors formula evaluation and dependency resolution."""

from typing import cast
from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.type_definitions import ContextValue


class TestFormulaEvaluation:
    """Test cases for formula evaluation functionality."""

    def test_enhanced_evaluator_basic_functionality(self, mock_hass, mock_entity_registry, mock_states):
        """Test basic formula evaluation functionality."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test simple arithmetic
        config = FormulaConfig(id="test", name="test", formula="10 + 20")
        result = evaluator.evaluate_formula(config, {})
        assert result["success"] is True
        assert result["value"] == 30

        # Test with variables
        config = FormulaConfig(id="test_vars", name="test_vars", formula="A + B")
        context = cast(dict[str, ContextValue], {"A": 100, "B": 50})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 150

    def test_enhanced_evaluator_with_entity_data(
        self, mock_hass, mock_entity_registry, mock_states, mock_entities_with_dependencies
    ):
        """Test formula evaluation with real entity data."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Create variables from entity data
        variables = {}
        for entity_id, entity_data in mock_entities_with_dependencies.items():
            # Simple normalization for testing
            normalized_name = entity_id.replace("sensor.", "").replace("_", "")
            variables[normalized_name] = float(entity_data["state"])

        # Test HVAC total calculation
        config = FormulaConfig(
            id="hvac_total",
            name="hvac_total",
            formula="hvacupstairs + hvacdownstairs",
            dependencies={"hvacupstairs", "hvacdownstairs"},
        )
        result = evaluator.evaluate_formula(config, variables)
        assert result["success"] is True
        assert result["value"] == 2000.0  # 1200 + 800

    def test_dependency_resolution(self, mock_hass, mock_entity_registry, mock_states):
        """Test dependency resolution in enhanced evaluator."""
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test simple formula dependencies
        dependencies = evaluator.get_formula_dependencies("A + B + C")
        assert dependencies == {"A", "B", "C"}

        # Test complex formula dependencies
        dependencies = evaluator.get_formula_dependencies("(HVAC_Upstairs + HVAC_Downstairs) / Total_Power")
        assert dependencies == {"HVAC_Upstairs", "HVAC_Downstairs", "Total_Power"}

    def test_caching_mechanism(self, mock_hass, mock_entity_registry, mock_states):
        """Test caching mechanism in enhanced evaluator."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        variables = cast(dict[str, ContextValue], {"A": 10, "B": 20})
        config = FormulaConfig(id="cache_test", name="cache_test", formula="A + B + 5")

        # First evaluation should compute result
        result1 = evaluator.evaluate_formula(config, variables)
        assert result1["success"] is True
        assert result1["value"] == 35

        # Second evaluation with same inputs should use cache
        result2 = evaluator.evaluate_formula(config, variables)
        assert result2["success"] is True
        assert result2["value"] == 35
        # Note: Caching behavior may not be explicitly indicated in result dict

    def test_formula_syntax_validation(self, mock_hass, mock_entity_registry, mock_states):
        """Test formula syntax validation."""
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test valid formulas
        errors = evaluator.validate_formula_syntax("A + B")
        assert len(errors) == 0  # Simple formulas with variables are valid

        # Test invalid formulas
        errors = evaluator.validate_formula_syntax("A + B + )")
        assert len(errors) > 0
        assert any("syntax" in error.lower() for error in errors)

        # Test balanced parentheses
        errors = evaluator.validate_formula_syntax("((A + B)")
        assert any("never closed" in error.lower() or "unmatched" in error.lower() for error in errors)

    def test_error_handling(self, mock_hass, mock_entity_registry, mock_states):
        """Test error handling in formula evaluation."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test division by zero - current behavior treats as alternate state
        config = FormulaConfig(id="division_test", name="division_test", formula="A / B")
        context = cast(dict[str, ContextValue], {"A": 10, "B": 0})
        result = evaluator.evaluate_formula(config, context)
        # Current implementation: runtime errors treated as alternate states
        assert result["success"] is True
        # Accept either STATE_UNKNOWN or 'unknown' depending on API surface
        # `STATE_UNKNOWN` equals the string 'unknown' — compare to the constant only for clarity
        from homeassistant.const import STATE_UNKNOWN

        assert result.get("state") == STATE_UNKNOWN
        assert result["value"] is None

        # Test missing dependencies - current behavior treats as alternate state
        config = FormulaConfig(id="missing_deps", name="missing_deps", formula="A + B")
        # Only A is present in context, B is missing
        mock_hass.states.get.side_effect = lambda entity_id: (None if entity_id == "B" else MagicMock(state=10))
        context = cast(dict[str, ContextValue], {"A": 10})  # Missing B
        result = evaluator.evaluate_formula(config, context)
        # Current implementation: undefined variables treated as alternate states
        assert result["success"] is True
        assert result.get("state") == STATE_UNKNOWN
        assert result["value"] is None

    def test_complex_formulas(self, mock_hass, mock_entity_registry, mock_states):
        """Test complex mathematical formulas."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator
        from ha_synthetic_sensors.type_definitions import ReferenceValue

        evaluator = Evaluator(mock_hass)

        # Clear any cached formulas to ensure fresh evaluation
        evaluator.clear_compiled_formulas()

        # Test min function in isolation first
        config = FormulaConfig(id="min_test", name="min_test", formula="min(C, D)")
        variables = cast(
            dict[str, ContextValue],
            {
                "C": 30,
                "D": 5,
            },
        )
        result = evaluator.evaluate_formula(config, variables)
        assert result["success"] is True
        assert result["value"] == 5  # min(30, 5) = 5

        # Test max function in isolation
        config = FormulaConfig(id="max_test", name="max_test", formula="max(A, B)")
        variables = cast(
            dict[str, ContextValue],
            {
                "A": 10,
                "B": 20,
            },
        )
        result = evaluator.evaluate_formula(config, variables)
        assert result["success"] is True
        assert result["value"] == 20  # max(10, 20) = 20

        # Test mathematical functions
        config = FormulaConfig(id="math_test", name="math_test", formula="max(A, B) + min(C, D)")
        variables = cast(
            dict[str, ContextValue],
            {
                "A": 10,
                "B": 20,
                "C": 30,
                "D": 5,
            },
        )
        result = evaluator.evaluate_formula(config, variables)
        assert result["success"] is True
        assert result["value"] == 25  # max(10, 20) + min(30, 5) = 20 + 5 = 25

        # Test absolute value
        config = FormulaConfig(id="abs_test", name="abs_test", formula="abs(A) + abs(B)")
        variables = cast(dict[str, ContextValue], {"A": -10, "B": 15})
        result = evaluator.evaluate_formula(config, variables)
        assert result["success"] is True
        assert result["value"] == 25  # abs(-10) + abs(15) = 10 + 15 = 25

    def test_cache_management(self, mock_hass, mock_entity_registry, mock_states):
        """Test cache management functionality."""
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test cache clearing - with new cache system, we don't manipulate directly
        # Instead test that clear_cache() method works without errors
        evaluator.clear_cache()

        # Test cache statistics
        stats = evaluator.get_cache_stats()
        assert isinstance(stats, dict)
        assert "total_cached_formulas" in stats
        assert "total_cached_evaluations" in stats

    def test_phase1_mathematical_functions(self, mock_hass, mock_entity_registry, mock_states):
        """Test Phase 1 advanced mathematical functions."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test sqrt function
        config = FormulaConfig(id="sqrt_test", name="sqrt_test", formula="sqrt(A)")
        context = cast(dict[str, ContextValue], {"A": 25})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 5.0

        # Test pow function
        config = FormulaConfig(id="pow_test", name="pow_test", formula="pow(A, B)")
        context = cast(dict[str, ContextValue], {"A": 2, "B": 3})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 8.0

        # Test floor and ceil functions
        config = FormulaConfig(id="floor_test", name="floor_test", formula="floor(A) + ceil(B)")
        context = cast(dict[str, ContextValue], {"A": 3.7, "B": 2.3})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 6.0  # floor(3.7) + ceil(2.3) = 3 + 3 = 6

        # Test clamp function
        config = FormulaConfig(id="clamp_test", name="clamp_test", formula="clamp(A, 10, 50)")
        context = cast(dict[str, ContextValue], {"A": 75})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 50  # Clamped to max value

        context = cast(dict[str, ContextValue], {"A": 5})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 10  # Clamped to min value

        context = cast(dict[str, ContextValue], {"A": 30})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 30  # Within range, unchanged

    def test_map_function(self, mock_hass, mock_entity_registry, mock_states):
        """Test the map range function."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test mapping 0-100 to 0-255 (common use case)
        config = FormulaConfig(id="map_test", name="map_test", formula="map(A, 0, 100, 0, 255)")
        context = cast(dict[str, ContextValue], {"A": 50})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 127.5  # 50% of 255

        # Test mapping with different ranges
        config = FormulaConfig(id="map_test2", name="map_test2", formula="map(A, 20, 80, 0, 10)")
        context = cast(dict[str, ContextValue], {"A": 50})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 5.0  # Middle of range maps to middle

        # Test edge case: identical input range
        config = FormulaConfig(id="map_edge", name="map_edge", formula="map(A, 10, 10, 0, 100)")
        context = cast(dict[str, ContextValue], {"A": 10})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 0  # Should return out_min when in_min == in_max

    def test_percent_function(self, mock_hass, mock_entity_registry, mock_states):
        """Test the percentage calculation function."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test basic percentage
        config = FormulaConfig(id="percent_test", name="percent_test", formula="percent(A, B)")
        context = cast(dict[str, ContextValue], {"A": 25, "B": 100})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 25.0

        # Test percentage with decimals
        context = cast(dict[str, ContextValue], {"A": 33, "B": 100})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 33.0

        # Test division by zero protection
        context = cast(dict[str, ContextValue], {"A": 50, "B": 0})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 0  # Should return 0 when dividing by zero

    def test_average_functions(self, mock_hass, mock_entity_registry, mock_states):
        """Test average/mean functions."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator
        from ha_synthetic_sensors.type_definitions import ReferenceValue

        evaluator = Evaluator(mock_hass)

        # Test avg function with individual arguments - use ReferenceValue objects
        config = FormulaConfig(id="avg_test", name="avg_test", formula="avg(A, B, C)")
        context = cast(
            dict[str, ContextValue],
            {
                "A": ReferenceValue(reference="A", value=10),
                "B": ReferenceValue(reference="B", value=20),
                "C": ReferenceValue(reference="C", value=30),
            },
        )
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 20.0

        # Test mean function (should be identical to avg) - use ReferenceValue objects
        config = FormulaConfig(id="mean_test", name="mean_test", formula="mean(A, B, C, D)")
        context = cast(
            dict[str, ContextValue],
            {
                "A": ReferenceValue(reference="A", value=5),
                "B": ReferenceValue(reference="B", value=10),
                "C": ReferenceValue(reference="C", value=15),
                "D": ReferenceValue(reference="D", value=20),
            },
        )
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 12.5

    def test_complex_phase1_formulas(self, mock_hass, mock_entity_registry, mock_states):
        """Test complex formulas using multiple Phase 1 functions."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)

        # Test complex formula: Energy efficiency calculation
        config = FormulaConfig(id="efficiency", name="efficiency", formula="clamp(percent(output, input), 0, 100)")
        context = cast(dict[str, ContextValue], {"output": 850, "input": 1000})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 85.0

        # Test complex formula: Temperature comfort index
        config = FormulaConfig(id="comfort", name="comfort", formula="floor(map(clamp(temp, 18, 26), 18, 26, 0, 100))")
        context = cast(dict[str, ContextValue], {"temp": 22})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 50.0  # 22°C maps to 50% comfort

        # Test complex formula: Power analysis with square root
        config = FormulaConfig(id="power_analysis", name="power_analysis", formula="sqrt(pow(voltage, 2) + pow(current, 2))")
        context = cast(dict[str, ContextValue], {"voltage": 3, "current": 4})
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 5.0  # Pythagorean theorem: sqrt(9 + 16) = 5
