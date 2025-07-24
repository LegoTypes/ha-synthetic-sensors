"""Tests for evaluator cache methods."""

from unittest.mock import MagicMock

from ha_synthetic_sensors.config_models import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator


class TestEvaluatorCache:
    """Test evaluator cache methods."""

    def test_clear_cache_all(self, mock_hass, mock_entity_registry, mock_states):
        """Test clearing all cache entries."""
        evaluator = Evaluator(mock_hass)

        # Mock the cache handler
        evaluator._cache_handler = MagicMock()

        # Clear all cache
        evaluator.clear_cache()

        # Verify clear_cache was called
        evaluator._cache_handler.clear_cache.assert_called_once_with(None)

    def test_clear_cache_specific_formula(self, mock_hass, mock_entity_registry, mock_states):
        """Test clearing cache for specific formula."""
        evaluator = Evaluator(mock_hass)

        # Mock the cache handler
        evaluator._cache_handler = MagicMock()

        # Clear cache for specific formula
        evaluator.clear_cache("test_formula")

        # Verify clear_cache was called with formula name
        evaluator._cache_handler.clear_cache.assert_called_once_with("test_formula")

    def test_get_cache_stats(self, mock_hass, mock_entity_registry, mock_states):
        """Test getting cache statistics."""
        evaluator = Evaluator(mock_hass)

        # Mock the cache handler statistics
        mock_stats = {"total_cached_formulas": 5, "total_cached_evaluations": 10, "cache_hit_rate": 0.8, "cache_size": 8}
        evaluator._cache_handler = MagicMock()
        evaluator._cache_handler.get_cache_stats.return_value = mock_stats

        # Add some error counts using the error handler
        evaluator._error_handler._error_count = {"formula1": 2, "formula2": 1}

        # Get cache stats
        stats = evaluator.get_cache_stats()

        # Verify the structure and content
        assert stats["total_cached_formulas"] == 5
        assert stats["total_cached_evaluations"] == 10
        assert stats["cache_hit_rate"] == 0.8
        assert stats["cache_size"] == 8
        assert stats["error_counts"] == {"formula1": 2, "formula2": 1}

        # Verify cache handler was called
        evaluator._cache_handler.get_cache_stats.assert_called_once()

    def test_get_cache_stats_no_errors(self, mock_hass, mock_entity_registry, mock_states):
        """Test getting cache statistics with no error counts."""
        evaluator = Evaluator(mock_hass)

        # Mock the cache handler statistics
        mock_stats = {"total_cached_formulas": 3, "total_cached_evaluations": 7, "cache_hit_rate": 1.0, "cache_size": 7}
        evaluator._cache_handler = MagicMock()
        evaluator._cache_handler.get_cache_stats.return_value = mock_stats

        # No error counts (default empty dict)

        # Get cache stats
        stats = evaluator.get_cache_stats()

        # Verify the structure and content
        assert stats["total_cached_formulas"] == 3
        assert stats["total_cached_evaluations"] == 7
        assert stats["cache_hit_rate"] == 1.0
        assert stats["cache_size"] == 7
        assert stats["error_counts"] == {}

    def test_cache_integration_with_formula_dependencies(self, mock_hass, mock_entity_registry, mock_states):
        """Test cache integration with formula dependency extraction."""
        evaluator = Evaluator(mock_hass)

        # Mock the dependency handler
        evaluator._dependency_handler = MagicMock()
        test_dependencies = {"sensor.test1", "sensor.test2"}
        evaluator._dependency_handler.get_formula_dependencies.return_value = test_dependencies

        # Call get_formula_dependencies
        result = evaluator.get_formula_dependencies("test_formula")

        # Verify dependency handler was called
        evaluator._dependency_handler.get_formula_dependencies.assert_called_once_with("test_formula")

        # Verify correct result returned
        assert result == test_dependencies

    def test_cache_hit_for_formula_dependencies(self, mock_hass, mock_entity_registry, mock_states):
        """Test cache hit for formula dependencies."""
        evaluator = Evaluator(mock_hass)

        # Mock the dependency handler
        cached_dependencies = {"sensor.cached1", "sensor.cached2"}
        evaluator._dependency_handler = MagicMock()
        evaluator._dependency_handler.get_formula_dependencies.return_value = cached_dependencies

        # Call get_formula_dependencies
        result = evaluator.get_formula_dependencies("cached_formula")

        # Verify dependency handler was called
        evaluator._dependency_handler.get_formula_dependencies.assert_called_once_with("cached_formula")

        # Verify correct cached result returned
        assert result == cached_dependencies

    def test_cache_result_storage_on_successful_evaluation(self, mock_hass, mock_entity_registry, mock_states):
        """Test that successful formula evaluation stores result in cache."""
        evaluator = Evaluator(mock_hass)

        # Setup mock entity state
        mock_state = MagicMock()
        mock_state.state = "42.5"
        mock_hass.states.get.return_value = mock_state

        # Mock the cache handler
        evaluator._cache_handler = MagicMock()
        evaluator._cache_handler.check_cache.return_value = None  # Cache miss
        evaluator._cache_handler.cache_result = MagicMock()

        # Mock dependency handler
        evaluator._dependency_handler = MagicMock()
        evaluator._dependency_handler.extract_and_prepare_dependencies.return_value = ({"sensor.test"}, set())
        evaluator._dependency_handler.check_dependencies.return_value = (set(), set(), set())  # No missing/unavailable/unknown

        # Create formula config
        config = FormulaConfig(id="test_formula", formula="sensor_test", variables={"sensor_test": "sensor.test"})

        # Create context with the variable value
        context = {"sensor_test": 42.5}

        # Evaluate formula with context
        result = evaluator.evaluate_formula(config, context)

        # Verify evaluation was successful
        assert result["success"] is True

        # Verify cache_result was called
        assert evaluator._cache_handler.cache_result.called

    def test_error_count_tracking_in_cache_stats(self, mock_hass, mock_entity_registry, mock_states):
        """Test that error counts are properly tracked and reported in cache stats."""
        evaluator = Evaluator(mock_hass)

        # Mock the cache handler statistics
        mock_stats = {"total_cached_formulas": 2, "total_cached_evaluations": 4, "cache_hit_rate": 0.75, "cache_size": 3}
        evaluator._cache_handler = MagicMock()
        evaluator._cache_handler.get_cache_stats.return_value = mock_stats

        # Simulate some error counts
        evaluator._error_handler._error_count = {"failing_formula": 3, "another_failing_formula": 1, "third_formula": 5}

        # Get cache stats
        stats = evaluator.get_cache_stats()

        # Verify error counts are included
        assert stats["error_counts"] == {"failing_formula": 3, "another_failing_formula": 1, "third_formula": 5}

        # Verify other stats are correct
        assert stats["total_cached_formulas"] == 2
        assert stats["total_cached_evaluations"] == 4
        assert stats["cache_hit_rate"] == 0.75
        assert stats["cache_size"] == 3
