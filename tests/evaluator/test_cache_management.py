"""Cache validation tests for the evaluator.

These tests ensure the evaluator's caching mechanism works correctly
and doesn't have issues with cache key collisions, variable context handling,
or other cache-related edge cases.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator


class TestCacheValidation:
    """Test cases to validate cache behavior and prevent regressions."""

    def test_unique_cache_keys_for_different_formulas(self, mock_hass, mock_entity_registry, mock_states):
        """Validate that different formulas get unique cache keys even with similar IDs."""
        evaluator = Evaluator(mock_hass)

        # Test case 1: Two formulas with IDs that might collide after transformation
        config1 = FormulaConfig(id="math_test_abs(-50)", name="Math Test", formula="abs(-50)")

        config2 = FormulaConfig(id="math_test_min(10, 20, 5)", name="Math Test", formula="min(10, 20, 5)")

        # Evaluate first formula
        result1 = evaluator.evaluate_formula(config1)
        assert result1["success"] is True
        assert result1["value"] == 50
        assert result1.get("cached", False) is False  # First evaluation should not be cached

        # Evaluate second formula - should NOT return cached result from first
        result2 = evaluator.evaluate_formula(config2)
        assert result2["success"] is True
        assert result2["value"] == 5  # Should be 5, NOT 50 from abs(-50)
        assert result2.get("cached", False) is False  # Should be fresh evaluation

        # Re-evaluate first formula - should now be cached
        result1_cached = evaluator.evaluate_formula(config1)
        assert result1_cached["success"] is True
        assert result1_cached["value"] == 50
        assert result1_cached.get("cached", False) is True

        # Re-evaluate second formula - should now be cached
        result2_cached = evaluator.evaluate_formula(config2)
        assert result2_cached["success"] is True
        assert result2_cached["value"] == 5
        assert result2_cached.get("cached", False) is True

    def test_cache_isolation_with_same_names(self, mock_hass, mock_entity_registry, mock_states):
        """Validate that formulas with the same name but different IDs are cached separately."""
        evaluator = Evaluator(mock_hass)

        # Two configs with same name but different formulas and IDs
        config1 = FormulaConfig(id="sensor_1", name="Test Sensor", formula="10 + 20")

        config2 = FormulaConfig(id="sensor_2", name="Test Sensor", formula="50 + 50")

        # Evaluate both
        result1 = evaluator.evaluate_formula(config1)
        result2 = evaluator.evaluate_formula(config2)

        assert result1["success"] is True
        assert result1["value"] == 30

        assert result2["success"] is True
        assert result2["value"] == 100

        # Re-evaluate to test caching
        result1_cached = evaluator.evaluate_formula(config1)
        result2_cached = evaluator.evaluate_formula(config2)

        assert result1_cached["value"] == 30
        assert result2_cached["value"] == 100

    def test_cache_with_edge_case_identifiers(self, mock_hass, mock_entity_registry, mock_states):
        """Validate caching behavior with empty, None, or special character IDs."""
        evaluator = Evaluator(mock_hass)

        # Test with IDs that might cause hash collisions
        test_cases = [
            ("id_1", "1 + 1", 2),
            ("id_2", "2 + 2", 4),
            ("", "3 + 3", 6),
            ("id_special_()[]", "4 + 4", 8),
            ("id_1", "1 + 1", 2),  # Repeat first case to test caching
        ]

        results = []
        for i, (id_val, formula, expected) in enumerate(test_cases):
            config = FormulaConfig(id=id_val, name=f"Test {i}", formula=formula)

            result = evaluator.evaluate_formula(config)
            results.append(result)

            assert result["success"] is True, f"Formula {formula} failed"
            assert result["value"] == expected, f"Formula {formula}: expected {expected}, got {result['value']}"

        # The last evaluation (repeat of first) should be cached
        assert results[-1].get("cached", False) is True

    def test_cache_key_uniqueness_validation(self, mock_hass, mock_entity_registry, mock_states):
        """Validate that different formulas generate different cache keys."""
        evaluator = Evaluator(mock_hass)

        # Create formulas that might accidentally have same cache key
        formulas = [
            ("abs(-50)", 50),
            ("min(10, 20, 5)", 5),
            ("max(10, 20, 5)", 20),
            ("round(3.14159, 2)", 3.14),
            ("sqrt(16)", 4.0),
            ("pow(2, 3)", 8),
            ("1 + 2 + 3 + 4", 10),
        ]

        # Track all results to verify no cross-contamination
        results = {}

        for i, (formula, expected) in enumerate(formulas):
            config = FormulaConfig(id=f"unique_test_{i}", name=f"Unique Test {i}", formula=formula)

            result = evaluator.evaluate_formula(config)
            results[formula] = result

            assert result["success"] is True, f"Formula {formula} failed: {result.get('error')}"

            # For floating point comparisons
            result_value = result["value"]
            if isinstance(expected, float):
                assert isinstance(result_value, (int, float)), f"Formula {formula}: expected numeric result"
                assert abs(float(result_value) - expected) < 0.001, (
                    f"Formula {formula}: expected {expected}, got {result_value}"
                )
            else:
                assert result_value == expected, f"Formula {formula}: expected {expected}, got {result_value}"

            assert result.get("cached", False) is False, f"First evaluation of {formula} should not be cached"

        # Now re-evaluate all formulas - they should all be cached and return correct values
        for i, (formula, expected) in enumerate(formulas):
            config = FormulaConfig(id=f"unique_test_{i}", name=f"Unique Test {i}", formula=formula)

            result = evaluator.evaluate_formula(config)

            assert result["success"] is True, f"Cached formula {formula} failed"
            assert result.get("cached", False) is True, f"Re-evaluation of {formula} should be cached"

            # Verify cached result is still correct
            result_value = result["value"]
            if isinstance(expected, float):
                assert isinstance(result_value, (int, float)), f"Cached formula {formula}: expected numeric result"
                assert abs(float(result_value) - expected) < 0.001, (
                    f"Cached formula {formula}: expected {expected}, got {result_value}"
                )
            else:
                assert result_value == expected, f"Cached formula {formula}: expected {expected}, got {result_value}"

    def test_cache_context_variable_handling(self, mock_hass, mock_entity_registry, mock_states):
        """Validate caching behavior when context variables are involved."""
        evaluator = Evaluator(mock_hass)

        # Test that different context values don't cause cache collisions
        config = FormulaConfig(id="context_test", name="Context Test", formula="var_a + var_b")

        # First evaluation with context
        context1: dict[str, Any] = {"var_a": 10, "var_b": 20}
        result1 = evaluator.evaluate_formula(config, context1)
        assert result1["success"] is True
        assert result1["value"] == 30
        assert result1.get("cached", False) is False

        # Second evaluation with different context - should not use cached result
        context2: dict[str, Any] = {"var_a": 100, "var_b": 200}
        result2 = evaluator.evaluate_formula(config, context2)
        assert result2["success"] is True
        assert result2["value"] == 300  # Should be 300, NOT 30 from cache
        # Note: Caching behavior with context may vary depending on implementation

        # Re-evaluate with first context - might be cached depending on implementation
        result1_repeat = evaluator.evaluate_formula(config, context1)
        assert result1_repeat["success"] is True
        assert result1_repeat["value"] == 30
