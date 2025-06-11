"""Tests for enhanced formula evaluator module."""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import CircuitBreakerConfig, Evaluator, RetryConfig


class TestEvaluator:
    """Test cases for Evaluator."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()
        return hass

    def test_initialization(self, mock_hass):
        """Test evaluator initialization."""
        evaluator = Evaluator(mock_hass)
        assert evaluator._hass == mock_hass
        assert evaluator._cache is not None
        assert evaluator._dependency_parser is not None
        assert evaluator._math_functions is not None

    def test_extract_variables(self, mock_hass):
        """Test variable extraction from formulas."""
        evaluator = Evaluator(mock_hass)

        # Test simple formula
        dependencies = evaluator.get_formula_dependencies("A + B")
        assert "A" in dependencies
        assert "B" in dependencies

        # Test entity function format
        dependencies = evaluator.get_formula_dependencies('entity("sensor.temp") + entity("sensor.humidity")')
        assert "sensor.temp" in dependencies
        assert "sensor.humidity" in dependencies

        # Test mixed format
        dependencies = evaluator.get_formula_dependencies("A + entity('sensor.test')")
        assert "A" in dependencies
        assert "sensor.test" in dependencies

    def test_safe_functions(self, mock_hass):
        """Test that safe functions are available."""
        evaluator = Evaluator(mock_hass)

        # Test basic formula with safe functions
        config = FormulaConfig(id="safe_func", name="safe_func", formula="abs(-10) + max(5, 3) + min(1, 2)")

        result = evaluator.evaluate_formula(config, {})
        assert result["success"] is True
        assert result["value"] == 16  # abs(-10) + max(5,3) + min(1,2) = 10 + 5 + 1 = 16

    def test_formula_evaluation_basic(self, mock_hass):
        """Test basic formula evaluation."""
        evaluator = Evaluator(mock_hass)

        config = FormulaConfig(id="basic", name="basic", formula="10 + 20")

        result = evaluator.evaluate_formula(config, {})
        assert result["success"] is True
        assert result["value"] == 30

    def test_formula_evaluation_with_context(self, mock_hass):
        """Test formula evaluation with context variables."""
        evaluator = Evaluator(mock_hass)

        config = FormulaConfig(id="context", name="context", formula="A + B + C")

        context = {"A": 15, "B": 25, "C": 0}
        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 40

    def test_caching_mechanism(self, mock_hass):
        """Test result caching functionality."""
        evaluator = Evaluator(mock_hass)

        config = FormulaConfig(id="cache", name="cache", formula="100 + 200")

        # First evaluation
        result1 = evaluator.evaluate_formula(config, {})
        assert result1["success"] is True
        assert result1["value"] == 300
        assert result1.get("cached", False) is False

        # Second evaluation should use cache
        result2 = evaluator.evaluate_formula(config, {})
        assert result2["success"] is True
        assert result2["value"] == 300
        assert result2.get("cached", False) is True

    def test_dependency_tracking(self, mock_hass):
        """Test dependency tracking functionality."""
        evaluator = Evaluator(mock_hass)

        # Test simple variable dependencies
        deps = evaluator.get_formula_dependencies("temp + humidity")
        assert "temp" in deps
        assert "humidity" in deps

        # Test entity reference dependencies
        deps = evaluator.get_formula_dependencies('entity("sensor.temperature") + entity("sensor.humidity")')
        assert "sensor.temperature" in deps
        assert "sensor.humidity" in deps

    def test_cache_invalidation(self, mock_hass):
        """Test cache invalidation functionality."""
        evaluator = Evaluator(mock_hass)

        config = FormulaConfig(id="invalid", name="invalid", formula="50 + 75")

        # Evaluate to populate cache
        result = evaluator.evaluate_formula(config, {})
        assert result["success"] is True

        # Clear cache
        evaluator.clear_cache("invalid")

        # Next evaluation should not be cached
        result = evaluator.evaluate_formula(config, {})
        assert result["success"] is True
        assert result.get("cached", False) is False

    def test_error_handling(self, mock_hass):
        """Test error handling for invalid formulas."""
        evaluator = Evaluator(mock_hass)

        # Test syntax error
        config = FormulaConfig(id="error_handling", name="error_handling", formula="A / 0")

        result = evaluator.evaluate_formula(config, {})
        assert result["success"] is False
        assert "error" in result

    def test_clear_cache(self, mock_hass):
        """Test cache clearing functionality."""
        evaluator = Evaluator(mock_hass)

        config = FormulaConfig(id="clear_cache", name="clear_cache", formula="A + B")

        # Evaluate to populate cache
        evaluator.evaluate_formula(config, {})

        # Clear all caches
        evaluator.clear_cache()

        # Cache should be empty
        stats = evaluator.get_cache_stats()
        assert stats["total_cached_evaluations"] == 0
        assert stats["total_cached_formulas"] == 0

    def test_circuit_breaker_configuration(self, mock_hass):
        """Test that circuit breaker configuration is customizable."""
        # Test with custom configuration
        cb_config = CircuitBreakerConfig(
            max_fatal_errors=3,
            max_transitory_errors=10,
            track_transitory_errors=True,
            reset_on_success=True,
        )

        retry_config = RetryConfig(
            enabled=True,
            max_attempts=5,
            retry_on_unknown=True,
            retry_on_unavailable=False,
        )

        evaluator = Evaluator(mock_hass, circuit_breaker_config=cb_config, retry_config=retry_config)

        # Verify configuration was applied
        assert evaluator.get_circuit_breaker_config().max_fatal_errors == 3
        assert evaluator.get_circuit_breaker_config().max_transitory_errors == 10
        assert evaluator.get_retry_config().max_attempts == 5
        assert evaluator.get_retry_config().retry_on_unavailable is False

    def test_circuit_breaker_default_configuration(self, mock_hass):
        """Test that default configuration is applied when none provided."""
        evaluator = Evaluator(mock_hass)

        # Verify default configuration
        cb_config = evaluator.get_circuit_breaker_config()
        assert cb_config.max_fatal_errors == 5
        assert cb_config.max_transitory_errors == 20
        assert cb_config.track_transitory_errors is True
        assert cb_config.reset_on_success is True

        retry_config = evaluator.get_retry_config()
        assert retry_config.enabled is True
        assert retry_config.max_attempts == 3

    def test_configuration_updates(self, mock_hass):
        """Test that configuration can be updated after initialization."""
        evaluator = Evaluator(mock_hass)

        # Update circuit breaker config
        new_cb_config = CircuitBreakerConfig(max_fatal_errors=10)
        evaluator.update_circuit_breaker_config(new_cb_config)
        assert evaluator.get_circuit_breaker_config().max_fatal_errors == 10

        # Update retry config
        new_retry_config = RetryConfig(max_attempts=7)
        evaluator.update_retry_config(new_retry_config)
        assert evaluator.get_retry_config().max_attempts == 7

    def test_custom_fatal_error_threshold(self, mock_hass):
        """Test that custom fatal error threshold is respected."""
        # Set a low threshold for testing
        cb_config = CircuitBreakerConfig(max_fatal_errors=2)
        evaluator = Evaluator(mock_hass, circuit_breaker_config=cb_config)

        # Mock a missing entity to trigger fatal errors
        mock_hass.states.get.return_value = None

        config = FormulaConfig(id="test_formula", name="test", formula="missing_entity + 1")

        # First two evaluations should attempt and fail
        result1 = evaluator.evaluate_formula(config)
        assert result1["success"] is False
        assert "error" in result1
        assert "missing_entity" in result1["error"]

        result2 = evaluator.evaluate_formula(config)
        assert result2["success"] is False
        assert "error" in result2
        assert "missing_entity" in result2["error"]

        # Third evaluation should be skipped due to circuit breaker
        result3 = evaluator.evaluate_formula(config)
        assert result3["success"] is False
        assert "error" in result3
        assert "Skipping formula" in result3["error"]
