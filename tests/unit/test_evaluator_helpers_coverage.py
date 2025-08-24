"""Unit tests for EvaluatorHelpers coverage improvement."""

import pytest
from unittest.mock import Mock
from datetime import datetime

from src.ha_synthetic_sensors.evaluator_helpers import EvaluatorHelpers


class TestEvaluatorHelpersCoverage:
    """Test uncovered lines in EvaluatorHelpers."""

    def test_get_cache_key_id_with_context(self):
        """Test cache key generation with context."""
        mock_config = Mock()
        mock_config.id = "test_formula"

        context = {"var1": "value1", "var2": "value2"}

        cache_key = EvaluatorHelpers.get_cache_key_id(mock_config, context)

        # Should include the formula ID and a hash of the context
        assert cache_key.startswith("test_formula_")
        assert len(cache_key) > len("test_formula_")

    def test_get_cache_key_id_no_context(self):
        """Test cache key generation without context."""
        mock_config = Mock()
        mock_config.id = "test_formula"

        cache_key = EvaluatorHelpers.get_cache_key_id(mock_config, None)

        assert cache_key == "test_formula"

    def test_get_cache_key_id_empty_context(self):
        """Test cache key generation with empty context."""
        mock_config = Mock()
        mock_config.id = "test_formula"

        cache_key = EvaluatorHelpers.get_cache_key_id(mock_config, {})

        # Empty context should be treated same as None
        assert cache_key == "test_formula"

    def test_should_cache_result_int(self):
        """Test caching decision for integer results."""
        assert EvaluatorHelpers.should_cache_result(42) is True

    def test_should_cache_result_float(self):
        """Test caching decision for float results."""
        assert EvaluatorHelpers.should_cache_result(3.14) is True

    def test_should_cache_result_string(self):
        """Test caching decision for string results."""
        assert EvaluatorHelpers.should_cache_result("test") is False

    def test_should_cache_result_bool(self):
        """Test caching decision for boolean results."""
        # Note: In Python, bool is a subclass of int, so booleans are cached as numeric
        assert EvaluatorHelpers.should_cache_result(True) is True
        assert EvaluatorHelpers.should_cache_result(False) is True

    def test_should_cache_result_none(self):
        """Test caching decision for None results."""
        assert EvaluatorHelpers.should_cache_result(None) is False

    def test_should_cache_result_datetime(self):
        """Test caching decision for datetime results."""
        dt = datetime.now()
        assert EvaluatorHelpers.should_cache_result(dt) is False

    def test_should_cache_result_list(self):
        """Test caching decision for list results."""
        assert EvaluatorHelpers.should_cache_result([1, 2, 3]) is False

    def test_process_evaluation_result_datetime(self):
        """Test processing datetime evaluation results."""
        dt = datetime(2023, 1, 1, 12, 0, 0)
        result = EvaluatorHelpers.process_evaluation_result(dt)

        # Should convert datetime to string representation
        assert isinstance(result, str)
        assert "2023-01-01" in result
        assert "12:00:00" in result

    def test_process_evaluation_result_numeric(self):
        """Test processing numeric evaluation results."""
        # Test integer
        assert EvaluatorHelpers.process_evaluation_result(42) == 42

        # Test float
        assert EvaluatorHelpers.process_evaluation_result(3.14) == 3.14

    def test_process_evaluation_result_string(self):
        """Test processing string evaluation results."""
        result = EvaluatorHelpers.process_evaluation_result("test_string")
        assert result == "test_string"

    def test_process_evaluation_result_bool(self):
        """Test processing boolean evaluation results."""
        assert EvaluatorHelpers.process_evaluation_result(True) is True
        assert EvaluatorHelpers.process_evaluation_result(False) is False

    def test_process_evaluation_result_none(self):
        """Test processing None evaluation results."""
        # None should be preserved for Home Assistant to handle
        result = EvaluatorHelpers.process_evaluation_result(None)
        assert result is None
