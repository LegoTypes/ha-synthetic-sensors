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

        # New structure should have these top-level keys (numeric_handler removed)
        expected_top_level_keys = {
            "enhanced_helper",
            "total_entries",
            "total_hits",
            "total_misses",
            "combined_hit_rate",
        }
        assert all(key in stats for key in expected_top_level_keys)

        # Enhanced helper section should have cache stats
        enhanced_stats = stats["enhanced_helper"]
        assert isinstance(enhanced_stats, dict)
        expected_handler_keys = {"total_entries", "hits", "misses", "hit_rate", "max_entries"}
        assert all(key in enhanced_stats for key in expected_handler_keys)

    def test_clear_compiled_formulas(self, evaluator):
        """Test clearing compiled formulas."""
        # Should not raise any errors
        evaluator.clear_compiled_formulas()

        # Verify cache is cleared
        stats = evaluator.get_compilation_cache_stats()
        assert stats["total_entries"] == 0

    def test_formula_evaluation_with_compilation_cache(self, evaluator, mock_hass, mock_entity_registry, mock_states):
        """Test that formula compilation cache works through EnhancedSimpleEvalHelper."""

        # Test the compilation cache functionality directly through EnhancedSimpleEvalHelper
        from ha_synthetic_sensors.enhanced_formula_evaluation import EnhancedSimpleEvalHelper

        # Create an EnhancedSimpleEvalHelper (uses compilation cache)
        helper = EnhancedSimpleEvalHelper()

        # Test the same formula multiple times to exercise caching
        formula = "1500.0 * 0.12 / 1000"
        context = {}

        success1, result1 = helper.try_enhanced_eval(formula, context)
        success2, result2 = helper.try_enhanced_eval(formula, context)
        success3, result3 = helper.try_enhanced_eval(formula, context)

        # All results should be the same
        expected_result = 1500.0 * 0.12 / 1000  # 0.18
        assert success1 and success2 and success3
        assert abs(result1 - expected_result) < 0.001
        assert abs(result2 - expected_result) < 0.001
        assert abs(result3 - expected_result) < 0.001

        # Get compilation cache statistics from the helper
        cache_stats = helper.get_compilation_cache_stats()

        # Should have at least one cached formula
        assert cache_stats["total_entries"] >= 1
        assert cache_stats["total_entries"] + cache_stats["hits"] + cache_stats["misses"] > 0

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
        # Compilation cache should not have been cleared
        assert final_stats["total_entries"] >= initial_stats["total_entries"]

        # Clear compilation cache specifically
        evaluator.clear_compiled_formulas()

        # Now compilation cache should be empty
        cleared_stats = evaluator.get_compilation_cache_stats()
        assert cleared_stats["total_entries"] == 0

    def test_different_formulas_cached_separately(self, evaluator, mock_hass):
        """Test that different formulas are cached as separate entries through EnhancedSimpleEvalHelper."""

        # Test different formulas through EnhancedSimpleEvalHelper to exercise compilation cache
        from ha_synthetic_sensors.enhanced_formula_evaluation import EnhancedSimpleEvalHelper

        # Create an EnhancedSimpleEvalHelper (uses compilation cache)
        helper = EnhancedSimpleEvalHelper()

        # Create different contexts
        context1 = {"value1": 5, "value2": 10}
        context2 = {"value3": 8, "value4": 3}

        # Evaluate different formulas
        formula1 = "value1 + value2"  # Should cache as first entry
        formula2 = "value3 * value4"  # Should cache as second entry

        success1, result1 = helper.try_enhanced_eval(formula1, context1)
        success2, result2 = helper.try_enhanced_eval(formula2, context2)

        # Both should succeed
        assert success1 and success2
        assert result1 == 15  # 5 + 10 = 15
        assert result2 == 24  # 8 * 3 = 24

        # Should have separate cache entries for different formulas
        cache_stats = helper.get_compilation_cache_stats()
        assert cache_stats["total_entries"] >= 2
