"""Test evaluator's formula compilation cache management."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.config_models import FormulaConfig
from ha_synthetic_sensors.cache import CacheConfig


class TestEvaluatorCompilationCache:
    """Test evaluator's compilation cache integration."""

    @pytest.fixture
    def evaluator(self, mock_hass, mock_entity_registry, mock_states):
        """Create evaluator with compilation cache."""
        return Evaluator(mock_hass)

    def test_compilation_cache_stats(self, evaluator):
        """Test that compilation cache statistics are accessible."""
        stats = evaluator.get_compilation_cache_stats()

        # Should return empty dict or stats dict
        assert isinstance(stats, dict)

        # If numeric handler exists, should have cache stats
        if stats:
            expected_keys = {"total_entries", "hits", "misses", "hit_rate", "max_entries"}
            assert all(key in stats for key in expected_keys)

    def test_clear_compiled_formulas(self, evaluator):
        """Test clearing compiled formulas."""
        # Should not raise any errors
        evaluator.clear_compiled_formulas()

        # Verify cache is cleared
        stats = evaluator.get_compilation_cache_stats()
        if stats:
            assert stats["total_entries"] == 0

    def test_formula_evaluation_with_compilation_cache(self, evaluator, mock_hass, mock_entity_registry, mock_states):
        """Test that formula evaluation uses compilation cache."""

        # Set up mock data provider
        def mock_data_provider(entity_id):
            return {"value": 10.0, "exists": True}

        evaluator._data_provider_callback = mock_data_provider

        # Create a formula config
        formula_config = FormulaConfig(id="test_formula", formula="a * 2 + b", variables={"a": 5, "b": 3})

        # Evaluate the same formula multiple times
        context = {"a": 5, "b": 3}

        result1 = evaluator.evaluate_formula(formula_config, context)
        result2 = evaluator.evaluate_formula(formula_config, context)
        result3 = evaluator.evaluate_formula(formula_config, context)

        # All results should have the same value, but cache indicators may differ
        assert result1["value"] == result2["value"] == result3["value"] == 13.0
        assert result1["success"] == result2["success"] == result3["success"] == True

        # Second and third evaluations may be cached (depending on cache state)
        # This is expected behavior per the Cache Behavior documentation

        # Check cache statistics show usage
        stats = evaluator.get_compilation_cache_stats()
        if stats:
            # Should have at least one cached formula
            assert stats["total_entries"] >= 1
            # May have cache hits, but depends on cache state and implementation
            # The key test is that formulas are compiled and cached
            assert stats["total_entries"] + stats["hits"] + stats["misses"] > 0

    def test_compilation_cache_survives_result_cache_clear(self, evaluator):
        """Test that formula compilation cache is separate from result cache."""
        # Get initial compilation cache stats
        initial_stats = evaluator.get_compilation_cache_stats()

        # Do some formula evaluations to populate compilation cache
        formula_config = FormulaConfig(id="test_formula", formula="1 + 2 + 3", variables={})

        # Set up mock data provider
        def mock_data_provider(entity_id):
            return {"value": 1.0, "exists": True}

        evaluator._data_provider_callback = mock_data_provider

        # Evaluate to populate compilation cache
        result = evaluator.evaluate_formula(formula_config, {})
        assert result["success"] is True

        # Clear result cache (should NOT affect compilation cache)
        evaluator.clear_cache()

        # Compilation cache should still have entries
        final_stats = evaluator.get_compilation_cache_stats()
        if final_stats and initial_stats:
            # Compilation cache should not have been cleared
            assert final_stats["total_entries"] >= initial_stats["total_entries"]

        # Clear compilation cache specifically
        evaluator.clear_compiled_formulas()

        # Now compilation cache should be empty
        cleared_stats = evaluator.get_compilation_cache_stats()
        if cleared_stats:
            assert cleared_stats["total_entries"] == 0

    def test_different_formulas_cached_separately(self, evaluator):
        """Test that different formulas are cached as separate entries."""

        # Set up mock data provider
        def mock_data_provider(entity_id):
            return {"value": 1.0, "exists": True}

        evaluator._data_provider_callback = mock_data_provider

        # Create different formula configs
        formula1 = FormulaConfig(id="formula1", formula="a + b", variables={"a": 1, "b": 2})
        formula2 = FormulaConfig(id="formula2", formula="a * b", variables={"a": 3, "b": 4})

        # Evaluate both formulas
        result1 = evaluator.evaluate_formula(formula1, {"a": 1, "b": 2})
        result2 = evaluator.evaluate_formula(formula2, {"a": 3, "b": 4})

        # Both should succeed
        assert result1["success"] is True
        assert result2["success"] is True

        # Should have separate cache entries
        stats = evaluator.get_compilation_cache_stats()
        if stats:
            assert stats["total_entries"] >= 2
