"""Enhanced integration tests for alternate_state_eval.py module.

These tests focus on integration scenarios and edge cases that complement
the existing unit tests, particularly testing the allow_unresolved_states
behavior and complex evaluation scenarios.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from ha_synthetic_sensors.alternate_state_eval import (
    evaluate_formula_alternate,
    evaluate_computed_alternate,
    _looks_like_formula,
    _strip_quotes,
    _try_convert_numeric,
)
from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.exceptions import AlternateStateDetected
from ha_synthetic_sensors.constants_alternate import STATE_NONE, STATE_UNKNOWN, STATE_UNAVAILABLE


class TestAlternateStateEvalEnhanced:
    """Enhanced integration tests for alternate state evaluation."""

    def test_looks_like_formula_edge_cases(self):
        """Test formula detection with edge cases and complex expressions."""
        # Complex mathematical expressions
        assert _looks_like_formula("sqrt(x**2 + y**2)") is True
        assert _looks_like_formula("sin(pi/4) * cos(pi/4)") is True
        assert _looks_like_formula("abs(value) > threshold") is True

        # Conditional expressions - "if" and "else" are not in the operator list
        # so these will be False with current implementation
        assert _looks_like_formula("value if condition else fallback") is False
        assert _looks_like_formula("x and y or z") is True  # Contains " and " and " or "
        assert _looks_like_formula("not (a or b)") is True  # Contains " not " and parentheses

        # String operations that look like formulas
        assert _looks_like_formula("'hello' + 'world'") is True
        assert _looks_like_formula("str(value) + '_suffix'") is True

        # Edge cases that should NOT be formulas
        assert _looks_like_formula("sensor.power_meter") is False
        assert _looks_like_formula("device_class:power") is False
        assert _looks_like_formula("area:kitchen") is False
        assert _looks_like_formula("unavailable") is False
        assert _looks_like_formula("unknown") is False

        # Empty and whitespace
        assert _looks_like_formula("") is False
        assert _looks_like_formula("   ") is False
        assert _looks_like_formula("\n\t") is False

    def test_strip_quotes_edge_cases(self):
        """Test quote stripping with edge cases."""
        # Nested quotes
        assert _strip_quotes("\"'nested'\"") == "'nested'"
        assert _strip_quotes("'\"nested\"'") == '"nested"'

        # Empty quoted strings
        assert _strip_quotes('""') == ""
        assert _strip_quotes("''") == ""

        # Quotes in middle (should not strip)
        assert _strip_quotes('hello"world') == 'hello"world'
        assert _strip_quotes("hello'world") == "hello'world"

        # Mismatched quotes
        assert _strip_quotes("\"hello'") == "\"hello'"
        assert _strip_quotes("'hello\"") == "'hello\""

        # Special characters
        assert _strip_quotes('"hello\nworld"') == "hello\nworld"
        assert _strip_quotes("'hello\tworld'") == "hello\tworld"

    def test_try_convert_numeric_edge_cases(self):
        """Test numeric conversion with edge cases."""
        # Scientific notation
        assert _try_convert_numeric("1.23e-4") == "1.23e-4"  # Not handled by current implementation
        assert _try_convert_numeric("1E+5") == "1E+5"  # Not handled by current implementation

        # Leading/trailing whitespace (should not convert)
        assert _try_convert_numeric(" 123 ") == " 123 "
        assert _try_convert_numeric("\t456\n") == "\t456\n"

        # Multiple decimal points
        assert _try_convert_numeric("1.2.3") == "1.2.3"

        # Negative floats
        assert _try_convert_numeric("-123.45") == -123.45
        assert _try_convert_numeric("-0.001") == -0.001

        # Zero variations
        assert _try_convert_numeric("0") == 0
        assert _try_convert_numeric("0.0") == 0.0
        assert _try_convert_numeric("-0") == 0
        assert _try_convert_numeric("-0.0") == -0.0

        # Very large numbers
        assert _try_convert_numeric("999999999999999999") == 999999999999999999
        assert _try_convert_numeric("999.999999999999999") == 999.999999999999999

    @patch("ha_synthetic_sensors.alternate_state_eval.EvaluatorHelpers")
    def test_evaluate_formula_alternate_error_handling(self, mock_evaluator_helpers):
        """Test formula alternate evaluation error handling."""
        mock_core_evaluator = Mock()
        mock_resolve_all_references = Mock()
        mock_sensor_config = Mock()
        mock_config = Mock()
        eval_context = {"x": 10}

        # Mock evaluation failure
        mock_resolve_all_references.return_value = "x / 0"
        mock_eval_result = Mock()
        mock_eval_result.value = None
        mock_eval_result.state = "error"
        mock_core_evaluator.evaluate_formula.side_effect = ZeroDivisionError("division by zero")

        # Test that exceptions are propagated
        with pytest.raises(ZeroDivisionError):
            evaluate_formula_alternate(
                "x / 0", eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
            )

    @patch("ha_synthetic_sensors.alternate_state_eval.EvaluatorHelpers")
    def test_evaluate_formula_alternate_complex_object_form(self, mock_evaluator_helpers):
        """Test formula alternate evaluation with complex object forms."""
        mock_core_evaluator = Mock()
        mock_resolve_all_references = Mock()
        mock_sensor_config = Mock()
        mock_config = Mock()
        eval_context = {"global_var": 100}

        # Mock the evaluation pipeline
        mock_resolve_all_references.return_value = "sqrt(base**2 + height**2)"
        mock_eval_result = Mock()
        mock_eval_result.value = 5.0
        mock_eval_result.state = "ok"
        mock_core_evaluator.evaluate_formula.return_value = mock_eval_result
        mock_evaluator_helpers.process_evaluation_result.return_value = 5.0

        # Test complex object form with mathematical functions
        handler_formula = {
            "formula": "sqrt(base**2 + height**2)",
            "variables": {
                "base": 3,
                "height": 4,
                "global_ref": "global_var",  # Reference to global context
            },
        }

        result = evaluate_formula_alternate(
            handler_formula, eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
        )
        assert result == 5.0

        # Verify variables were merged correctly
        expected_context = eval_context.copy()
        expected_context.update({"base": 3, "height": 4, "global_ref": "global_var"})
        mock_resolve_all_references.assert_called_once_with(
            "sqrt(base**2 + height**2)", mock_sensor_config, expected_context, mock_config
        )

    def test_evaluate_formula_alternate_none_variables(self):
        """Test formula alternate evaluation with None variables."""
        mock_core_evaluator = Mock()
        mock_resolve_all_references = Mock()
        mock_sensor_config = Mock()
        mock_config = Mock()
        eval_context = {}

        # Test object form with None variables (should be treated as empty dict)
        handler_formula = {"formula": "10 + 5", "variables": None}

        # Mock the evaluation pipeline
        mock_resolve_all_references.return_value = "10 + 5"
        mock_eval_result = Mock()
        mock_eval_result.value = 15
        mock_eval_result.state = "ok"
        mock_core_evaluator.evaluate_formula.return_value = mock_eval_result

        with patch("ha_synthetic_sensors.alternate_state_eval.EvaluatorHelpers") as mock_evaluator_helpers:
            mock_evaluator_helpers.process_evaluation_result.return_value = 15

            result = evaluate_formula_alternate(
                handler_formula, eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
            )
            assert result == 15

    def test_evaluate_computed_alternate_complex_formulas(self):
        """Test computed alternate evaluation with complex formulas."""
        mock_get_enhanced_helper = Mock()
        mock_extract_values = Mock()
        mock_enhanced_helper = Mock()
        eval_context = {"x": 10, "y": 20, "z": 30}

        # Mock the enhanced helper
        mock_get_enhanced_helper.return_value = mock_enhanced_helper
        mock_extract_values.return_value = {"x": 10, "y": 20, "z": 30}
        mock_enhanced_helper.try_enhanced_eval.return_value = (True, 60)

        # Test complex formula with multiple operations
        result = evaluate_computed_alternate("x + y + z", eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == 60

        # Verify the evaluation was called correctly
        mock_extract_values.assert_called_once_with(eval_context)
        mock_enhanced_helper.try_enhanced_eval.assert_called_once_with("x + y + z", {"x": 10, "y": 20, "z": 30})

    def test_evaluate_computed_alternate_nested_object_forms(self):
        """Test computed alternate evaluation with nested object forms."""
        mock_get_enhanced_helper = Mock()
        mock_extract_values = Mock()
        mock_enhanced_helper = Mock()
        eval_context = {"global_multiplier": 2}

        # Mock the enhanced helper
        mock_get_enhanced_helper.return_value = mock_enhanced_helper
        mock_extract_values.return_value = {"base": 10, "factor": 5, "global_multiplier": 2}
        mock_enhanced_helper.try_enhanced_eval.return_value = (True, 100)

        # Test object form with variables that reference global context
        handler_formula = {
            "formula": "base * factor * global_multiplier",
            "variables": {
                "base": 10,
                "factor": 5,
                # global_multiplier comes from eval_context
            },
        }

        result = evaluate_computed_alternate(handler_formula, eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == 100

        # Verify variables were merged correctly
        expected_context = eval_context.copy()
        expected_context.update({"base": 10, "factor": 5})
        mock_extract_values.assert_called_once_with(expected_context)

    def test_evaluate_computed_alternate_evaluation_exceptions(self):
        """Test computed alternate evaluation with various exception scenarios."""
        mock_get_enhanced_helper = Mock()
        mock_extract_values = Mock()
        mock_enhanced_helper = Mock()
        eval_context = {}

        # Mock the enhanced helper to raise exception
        mock_get_enhanced_helper.return_value = mock_enhanced_helper
        mock_extract_values.return_value = {}
        mock_enhanced_helper.try_enhanced_eval.side_effect = ValueError("Invalid expression")

        # Test that exceptions during evaluation are handled gracefully
        # "invalid_expr" doesn't look like a formula, so it returns the original string
        result = evaluate_computed_alternate("invalid_expr", eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == "invalid_expr"  # Returns original string since it's not formula-like

        # Test with a formula-like string that fails evaluation (not exception)
        mock_enhanced_helper.try_enhanced_eval.side_effect = None  # Reset side_effect
        mock_enhanced_helper.try_enhanced_eval.return_value = (False, None)  # Evaluation fails
        result = evaluate_computed_alternate("x + y", eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result is None  # Should return None when evaluation fails

    def test_evaluate_computed_alternate_partial_evaluation_success(self):
        """Test computed alternate evaluation with partial success scenarios."""
        mock_get_enhanced_helper = Mock()
        mock_extract_values = Mock()
        mock_enhanced_helper = Mock()
        eval_context = {"valid_var": 42}

        # Mock the enhanced helper for partial success
        mock_get_enhanced_helper.return_value = mock_enhanced_helper
        mock_extract_values.return_value = {"valid_var": 42}

        # "valid_var" doesn't look like a formula (no operators), so it returns the original string
        result = evaluate_computed_alternate("valid_var", eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == "valid_var"  # Returns original string since it's not formula-like

        # Test with a formula-like string that fails evaluation
        mock_enhanced_helper.try_enhanced_eval.return_value = (False, None)
        result = evaluate_computed_alternate("x + y", eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result is None  # Current implementation returns None when evaluation fails

    def test_evaluate_formula_alternate_state_constants(self):
        """Test formula alternate evaluation with HA state constants."""
        mock_core_evaluator = Mock()
        mock_resolve_all_references = Mock()
        mock_sensor_config = Mock()
        mock_config = Mock()
        eval_context = {}

        # Test with HA state constants
        test_cases = [
            (STATE_UNAVAILABLE, STATE_UNAVAILABLE),
            (STATE_UNKNOWN, STATE_UNKNOWN),
            (STATE_NONE, STATE_NONE),
            ("unavailable", "unavailable"),
            ("unknown", "unknown"),
        ]

        for input_value, expected_result in test_cases:
            result = evaluate_formula_alternate(
                input_value, eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
            )
            assert result == expected_result

    def test_evaluate_computed_alternate_boolean_edge_cases(self):
        """Test computed alternate evaluation with boolean edge cases."""
        mock_get_enhanced_helper = Mock()
        mock_extract_values = Mock()
        eval_context = {}

        # Test various boolean representations
        test_cases = [
            (True, True),
            (False, False),
            ("true", "true"),  # String, not boolean
            ("false", "false"),  # String, not boolean
            ("True", "True"),  # String, not boolean
            ("False", "False"),  # String, not boolean
        ]

        for input_value, expected_result in test_cases:
            result = evaluate_computed_alternate(input_value, eval_context, mock_get_enhanced_helper, mock_extract_values)
            assert result == expected_result

    def test_evaluate_formula_alternate_empty_formula_object(self):
        """Test formula alternate evaluation with empty or malformed formula objects."""
        mock_core_evaluator = Mock()
        mock_resolve_all_references = Mock()
        mock_sensor_config = Mock()
        mock_config = Mock()
        eval_context = {}

        # Test empty dict (no formula key)
        result = evaluate_formula_alternate(
            {}, eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
        )
        assert result is None

        # Test dict with empty formula
        handler_formula = {"formula": ""}
        mock_resolve_all_references.return_value = ""
        mock_eval_result = Mock()
        mock_eval_result.value = ""
        mock_eval_result.state = "ok"
        mock_core_evaluator.evaluate_formula.return_value = mock_eval_result

        with patch("ha_synthetic_sensors.alternate_state_eval.EvaluatorHelpers") as mock_evaluator_helpers:
            mock_evaluator_helpers.process_evaluation_result.return_value = ""

            result = evaluate_formula_alternate(
                handler_formula, eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
            )
            assert result == ""

    def test_evaluate_computed_alternate_empty_formula_object(self):
        """Test computed alternate evaluation with empty or malformed formula objects."""
        mock_get_enhanced_helper = Mock()
        mock_extract_values = Mock()
        eval_context = {}

        # Test empty dict (no formula key)
        result = evaluate_computed_alternate({}, eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result is None

        # Test dict with missing formula key but other keys
        result = evaluate_computed_alternate(
            {"variables": {"x": 10}}, eval_context, mock_get_enhanced_helper, mock_extract_values
        )
        assert result is None
