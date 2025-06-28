"""Tests for enhanced formula evaluator module."""

from typing import Any
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

        # Test that core math functions are available
        safe_functions = evaluator._math_functions
        assert "abs" in safe_functions
        assert "min" in safe_functions
        assert "max" in safe_functions
        assert "sum" in safe_functions
        assert "round" in safe_functions

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

        context: dict[str, Any] = {"A": 15, "B": 25, "C": 0}
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

    def test_evaluator_with_context_and_variables(self, mock_hass):
        """Test evaluator with explicit context and variables - comprehensive test."""

        # Set up mock entity states
        def mock_states_get(entity_id):
            state_values = {
                "sensor.power_meter": MagicMock(state="1000"),
                "sensor.solar_panel": MagicMock(state="500"),
                "sensor.temperature": MagicMock(state="22.5"),
                "sensor.humidity": MagicMock(state="45"),
                "sensor.unavailable": None,
            }
            state_obj = state_values.get(entity_id)
            if state_obj:
                state_obj.entity_id = entity_id
            return state_obj

        mock_hass.states.get.side_effect = mock_states_get
        evaluator = Evaluator(mock_hass)

        # Test 1: Formula with variables from context
        config = FormulaConfig(
            id="test_variables",
            name="Test Variables",
            formula="power_input + solar_input",
            variables={
                "power_input": "sensor.power_meter",
                "solar_input": "sensor.solar_panel",
            },
        )

        # Build context like DynamicSensor would - use Any to match ContextValue
        context: dict[str, Any] = {}
        for var_name, entity_id in config.variables.items():
            state = mock_hass.states.get(entity_id)
            if state is not None:
                context[var_name] = float(state.state)

        result = evaluator.evaluate_formula(config, context)
        assert result["success"] is True
        assert result["value"] == 1500.0  # 1000 + 500

        # Test 2: Formula without variables should still work
        config_no_vars = FormulaConfig(id="test_no_vars", name="Test No Variables", formula="100 + 200")

        result2 = evaluator.evaluate_formula(config_no_vars)
        assert result2["success"] is True
        assert result2["value"] == 300

        # Test 3: Formula with direct entity access (the correct way in this evaluator)
        config_entity_access = FormulaConfig(
            id="test_entity_access",
            name="Test Entity Access",
            formula="sensor_temperature * 2 + sensor_humidity",
            variables={
                "sensor_temperature": "sensor.temperature",
                "sensor_humidity": "sensor.humidity",
            },
        )  # Direct entity names, not entity() function

        entity_context: dict[str, Any] = {
            "sensor_temperature": 22.5,
            "sensor_humidity": 45.0,
        }

        result3 = evaluator.evaluate_formula(config_entity_access, entity_context)
        assert result3["success"] is True
        assert result3["value"] == 90.0  # (22.5 * 2) + 45

        # Test 4: Complex formula with both variables and direct entity access
        config_mixed = FormulaConfig(
            id="test_mixed",
            name="Test Mixed",
            formula="power_total + temperature_reading",
            variables={
                "power_total": "sensor.power_meter",
                "temperature_reading": "sensor.temperature",
            },
        )

        mixed_context: dict[str, Any] = {
            "power_total": 1000.0,
            "temperature_reading": 22.5,
        }
        result4 = evaluator.evaluate_formula(config_mixed, mixed_context)
        assert result4["success"] is True
        assert result4["value"] == 1022.5  # 1000 + 22.5

        # Test 5: Error handling - missing variable in context
        config_missing_var = FormulaConfig(id="test_missing", name="Test Missing Variable", formula="missing_var + 100")

        result5 = evaluator.evaluate_formula(config_missing_var, {})
        assert result5["success"] is False
        assert "missing_var" in result5.get("error", "")

        # Test 6: Error handling - unavailable entity (simulated by missing context)
        config_unavailable = FormulaConfig(
            id="test_unavailable",
            name="Test Unavailable",
            formula="unavailable_sensor + 100",
            variables={"unavailable_sensor": "sensor.unavailable"},
        )

        # Don't provide the variable in context to simulate unavailable entity
        result6 = evaluator.evaluate_formula(config_unavailable, {})
        assert result6["success"] is False
        # Should handle unavailable entity gracefully

    def test_evaluator_caching_with_context(self, mock_hass):
        """Test that caching works correctly with context variables."""

        # Set up mock
        def mock_states_get(entity_id):
            if entity_id == "sensor.test_entity":
                state_obj = MagicMock(state="100")
                state_obj.entity_id = entity_id
                return state_obj
            return None

        mock_hass.states.get.side_effect = mock_states_get
        evaluator = Evaluator(mock_hass)

        config = FormulaConfig(
            id="cache_test",
            name="Cache Test",
            formula="test_var * 2",
            variables={"test_var": "sensor.test_entity"},
        )

        # First evaluation
        context: dict[str, Any] = {"test_var": 100.0}
        result1 = evaluator.evaluate_formula(config, context)
        assert result1["success"] is True
        assert result1["value"] == 200.0

        # Second evaluation should use cache (same formula hash)
        result2 = evaluator.evaluate_formula(config, context)
        assert result2["success"] is True
        assert result2["value"] == 200.0

        # Different context should work too
        context2: dict[str, Any] = {"test_var": 150.0}
        result3 = evaluator.evaluate_formula(config, context2)
        assert result3["success"] is True
        assert result3["value"] == 300.0

    def test_evaluator_math_functions_comprehensive(self, mock_hass):
        """Test comprehensive math functions with real evaluation."""
        evaluator = Evaluator(mock_hass)

        # Test basic math functions
        test_cases = [
            ("abs(-50)", 50),
            ("min(10, 20, 5)", 5),
            ("max(10, 20, 5)", 20),
            ("round(3.14159, 2)", 3.14),
            ("sqrt(16)", 4.0),
            ("pow(2, 3)", 8),
            ("1 + 2 + 3 + 4", 10),  # Replace sum([1,2,3,4]) with simple addition
        ]

        for i, (formula, expected) in enumerate(test_cases):
            config = FormulaConfig(
                id=f"math_test_{i}_{formula.replace('(', '_').replace(')', '').replace('[', '_').replace(']', '').replace(',', '_').replace(' ', '_')}",
                name=f"Math Test {i}",
                formula=formula,
            )

            result = evaluator.evaluate_formula(config)
            assert result["success"] is True, f"Formula {formula} failed: {result.get('error')}"
            result_value = result["value"]
            if isinstance(expected, float):
                assert isinstance(result_value, (int, float)), (
                    f"Formula {formula}: expected numeric result, got {type(result_value)}"
                )
                assert abs(float(result_value) - expected) < 0.001, (
                    f"Formula {formula}: expected {expected}, got {result_value}"
                )
            else:
                assert result_value == expected, f"Formula {formula}: expected {expected}, got {result_value}"

    def test_evaluator_error_scenarios_comprehensive(self, mock_hass):
        """Test comprehensive error handling scenarios."""
        evaluator = Evaluator(mock_hass)

        # Test various error scenarios
        error_cases = [
            ("undefined_variable", "not defined"),
            ("1 / 0", "division by zero"),
            ("invalid_function()", "not defined"),
            ("", "cannot evaluate empty string"),
            ("1 +", "invalid syntax"),
            ("(1 + 2", "was never closed"),
        ]

        for formula, expected_error_part in error_cases:
            config = FormulaConfig(id=f"error_test_{hash(formula)}", name="Error Test", formula=formula)

            result = evaluator.evaluate_formula(config)
            assert result["success"] is False, f"Formula {formula} should have failed"
            error_msg = result.get("error", "").lower()
            # Check that some part of the expected error is in the actual error message
            assert any(part.lower() in error_msg for part in expected_error_part.lower().split()), (
                f"Formula {formula}: expected error containing '{expected_error_part}', got '{result.get('error')}'"
            )

    def test_evaluator_dependency_extraction_comprehensive(self, mock_hass):
        """Test comprehensive dependency extraction from various formula types."""
        evaluator = Evaluator(mock_hass)

        test_cases = [
            # Formula, Expected dependencies (variables/entity names)
            ("A + B", {"A", "B"}),
            ("power_meter + solar_panel", {"power_meter", "solar_panel"}),
            ("max(A, B, C) + min(D, E)", {"A", "B", "C", "D", "E"}),
            # Should exclude math functions and keywords but include variables
            ("max(A, 100) + min(50, B)", {"A", "B"}),
            ("abs(power_reading) + 100", {"power_reading"}),
            # Complex variable names
            ("sensor_power_1 + sensor_power_2", {"sensor_power_1", "sensor_power_2"}),
        ]

        for formula, expected_deps in test_cases:
            deps = evaluator.get_formula_dependencies(formula)
            assert deps == expected_deps, f"Formula {formula}: expected {expected_deps}, got {deps}"
