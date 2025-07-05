"""Tests for evaluator cache methods."""

from unittest.mock import MagicMock

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator


class TestEvaluatorCache:
    """Test evaluator cache methods."""

    def test_clear_cache_all(self, mock_hass):
        """Test clearing all cache entries."""
        evaluator = Evaluator(mock_hass)

        # Mock the cache
        evaluator._cache = MagicMock()

        # Clear all cache
        evaluator.clear_cache()

        # Verify clear_all was called
        evaluator._cache.clear_all.assert_called_once()

    def test_clear_cache_specific_formula(self, mock_hass):
        """Test clearing cache for specific formula (currently clears all)."""
        evaluator = Evaluator(mock_hass)

        # Mock the cache
        evaluator._cache = MagicMock()

        # Clear cache for specific formula
        evaluator.clear_cache("test_formula")

        # Verify clear_all was called (current implementation)
        evaluator._cache.clear_all.assert_called_once()

    def test_get_cache_stats(self, mock_hass):
        """Test getting cache statistics."""
        evaluator = Evaluator(mock_hass)

        # Mock the cache statistics
        mock_stats = {"dependency_entries": 5, "total_entries": 10, "valid_entries": 8, "ttl_seconds": 300}
        evaluator._cache = MagicMock()
        evaluator._cache.get_statistics.return_value = mock_stats

        # Add some error counts
        evaluator._error_count = {"formula1": 2, "formula2": 1}

        # Get cache stats
        stats = evaluator.get_cache_stats()

        # Verify the structure and content
        assert stats["total_cached_formulas"] == 5
        assert stats["total_cached_evaluations"] == 10
        assert stats["valid_cached_evaluations"] == 8
        assert stats["error_counts"] == {"formula1": 2, "formula2": 1}
        assert stats["cache_ttl_seconds"] == 300

        # Verify cache.get_statistics was called
        evaluator._cache.get_statistics.assert_called_once()

    def test_get_cache_stats_no_errors(self, mock_hass):
        """Test getting cache statistics with no error counts."""
        evaluator = Evaluator(mock_hass)

        # Mock the cache statistics
        mock_stats = {"dependency_entries": 3, "total_entries": 7, "valid_entries": 7, "ttl_seconds": 600}
        evaluator._cache = MagicMock()
        evaluator._cache.get_statistics.return_value = mock_stats

        # No error counts (default empty dict)

        # Get cache stats
        stats = evaluator.get_cache_stats()

        # Verify the structure and content
        assert stats["total_cached_formulas"] == 3
        assert stats["total_cached_evaluations"] == 7
        assert stats["valid_cached_evaluations"] == 7
        assert stats["error_counts"] == {}
        assert stats["cache_ttl_seconds"] == 600

    def test_cache_integration_with_formula_dependencies(self, mock_hass):
        """Test cache integration with formula dependency extraction."""
        evaluator = Evaluator(mock_hass)

        # Mock the cache for dependencies
        evaluator._cache = MagicMock()
        evaluator._cache.get_dependencies.return_value = None  # Cache miss
        evaluator._cache.store_dependencies = MagicMock()

        # Mock the dependency parser
        evaluator._dependency_parser = MagicMock()
        test_dependencies = {"sensor.test1", "sensor.test2"}
        evaluator._dependency_parser.extract_dependencies.return_value = test_dependencies

        # Call get_formula_dependencies
        result = evaluator.get_formula_dependencies("test_formula")

        # Verify cache was checked first
        evaluator._cache.get_dependencies.assert_called_once_with("test_formula")

        # Verify dependency parser was called
        evaluator._dependency_parser.extract_dependencies.assert_called_once_with("test_formula")

        # Verify result was cached
        evaluator._cache.store_dependencies.assert_called_once_with("test_formula", test_dependencies)

        # Verify correct result returned
        assert result == test_dependencies

    def test_cache_hit_for_formula_dependencies(self, mock_hass):
        """Test cache hit for formula dependencies."""
        evaluator = Evaluator(mock_hass)

        # Mock the cache for dependencies
        cached_dependencies = {"sensor.cached1", "sensor.cached2"}
        evaluator._cache = MagicMock()
        evaluator._cache.get_dependencies.return_value = cached_dependencies

        # Mock the dependency parser (should not be called)
        evaluator._dependency_parser = MagicMock()

        # Call get_formula_dependencies
        result = evaluator.get_formula_dependencies("cached_formula")

        # Verify cache was checked
        evaluator._cache.get_dependencies.assert_called_once_with("cached_formula")

        # Verify dependency parser was NOT called (cache hit)
        evaluator._dependency_parser.extract_dependencies.assert_not_called()

        # Verify correct cached result returned
        assert result == cached_dependencies

    def test_cache_result_storage_on_successful_evaluation(self, mock_hass, mock_state):
        """Test that successful formula evaluation stores result in cache."""
        evaluator = Evaluator(mock_hass)

        # Setup mock entity
        mock_hass.states.get.return_value = mock_state("sensor.test", "42.5")

        # Mock the cache
        evaluator._cache = MagicMock()
        evaluator._cache.get_result.return_value = None  # Cache miss
        evaluator._cache.store_result = MagicMock()

        # Mock dependency parser
        evaluator._dependency_parser = MagicMock()
        evaluator._dependency_parser.extract_dependencies.return_value = {"sensor.test"}

        # Create formula config
        config = FormulaConfig(
            id="test_formula", formula="sensor_test", variables={"sensor_test": "sensor.test"}, dependencies={"sensor.test"}
        )

        # Evaluate formula
        result = evaluator.evaluate_formula(config)

        # Verify evaluation was successful
        assert result["success"] is True
        assert result["value"] == 42.5

        # Verify cache.store_result was called
        assert evaluator._cache.store_result.called

    def test_error_count_tracking_in_cache_stats(self, mock_hass):
        """Test that error counts are properly tracked and reported in cache stats."""
        evaluator = Evaluator(mock_hass)

        # Mock the cache statistics
        mock_stats = {"dependency_entries": 2, "total_entries": 4, "valid_entries": 3, "ttl_seconds": 300}
        evaluator._cache = MagicMock()
        evaluator._cache.get_statistics.return_value = mock_stats

        # Simulate some error counts
        evaluator._error_count = {"failing_formula": 3, "another_failing_formula": 1, "third_formula": 5}

        # Get cache stats
        stats = evaluator.get_cache_stats()

        # Verify error counts are included
        assert stats["error_counts"] == {"failing_formula": 3, "another_failing_formula": 1, "third_formula": 5}

        # Verify other stats are correct
        assert stats["total_cached_formulas"] == 2
        assert stats["total_cached_evaluations"] == 4
        assert stats["valid_cached_evaluations"] == 3
