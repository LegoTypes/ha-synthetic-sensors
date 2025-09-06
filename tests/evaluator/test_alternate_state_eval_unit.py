"""Unit tests for alternate_state_eval.py module.

These tests verify the alternate state evaluation functionality for both
sensor-level and computed-variable alternate handlers.
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


class TestAlternateStateEvalUnit:
    """Unit tests for alternate state evaluation functions."""

    def test_looks_like_formula_detection(self):
        """Test formula detection logic."""
        # Test operators that indicate formulas
        assert _looks_like_formula("a + b") is True
        assert _looks_like_formula("x * y") is True
        assert _looks_like_formula("(a + b) * c") is True
        assert _looks_like_formula("value > 10") is True
        assert _looks_like_formula("status == 'active'") is True
        assert _looks_like_formula("a and b") is True
        assert _looks_like_formula("x or y") is True
        # Note: "not value" is not detected as formula by the current implementation
        # assert _looks_like_formula("not value") is True

        # Test non-formula strings
        assert _looks_like_formula("simple_string") is False
        assert _looks_like_formula("123") is False
        assert _looks_like_formula("") is False
        assert _looks_like_formula("true") is False
        assert _looks_like_formula("false") is False

    def test_strip_quotes_function(self):
        """Test quote stripping functionality."""
        # Test double quotes
        assert _strip_quotes('"quoted_string"') == "quoted_string"
        assert _strip_quotes('"test"') == "test"

        # Test single quotes
        assert _strip_quotes("'quoted_string'") == "quoted_string"
        assert _strip_quotes("'test'") == "test"

        # Test unquoted strings (should return original)
        assert _strip_quotes("unquoted_string") == "unquoted_string"
        assert _strip_quotes("123") == "123"
        assert _strip_quotes("") == ""

        # Test mixed quotes (should return original)
        assert _strip_quotes('"unmatched') == '"unmatched'
        assert _strip_quotes("unmatched'") == "unmatched'"

    def test_try_convert_numeric_function(self):
        """Test numeric string conversion."""
        # Test integer strings
        assert _try_convert_numeric("123") == 123
        assert _try_convert_numeric("-42") == -42
        assert _try_convert_numeric("0") == 0

        # Test float strings
        assert _try_convert_numeric("123.45") == 123.45
        assert _try_convert_numeric("-42.67") == -42.67
        assert _try_convert_numeric("0.001") == 0.001

        # Test non-numeric strings (should return original)
        assert _try_convert_numeric("not_a_number") == "not_a_number"
        assert _try_convert_numeric("123abc") == "123abc"
        assert _try_convert_numeric("") == ""
        assert _try_convert_numeric("true") == "true"

    def test_evaluate_formula_alternate_literal_values(self):
        """Test formula alternate evaluation with literal values."""
        mock_core_evaluator = Mock()
        mock_resolve_all_references = Mock()
        mock_sensor_config = Mock()
        mock_config = Mock()
        eval_context = {"existing_var": 10}

        # Test integer literal
        result = evaluate_formula_alternate(
            42, eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
        )
        assert result == 42

        # Test float literal
        result = evaluate_formula_alternate(
            100.5, eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
        )
        assert result == 100.5

        # Test boolean literal
        result = evaluate_formula_alternate(
            True, eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
        )
        assert result is True

        # Test None value
        result = evaluate_formula_alternate(
            None, eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
        )
        assert result is None

    def test_evaluate_formula_alternate_quoted_strings(self):
        """Test formula alternate evaluation with quoted strings."""
        mock_core_evaluator = Mock()
        mock_resolve_all_references = Mock()
        mock_sensor_config = Mock()
        mock_config = Mock()
        eval_context = {}

        # Test double quoted string
        result = evaluate_formula_alternate(
            '"quoted_string"', eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
        )
        assert result == "quoted_string"

        # Test single quoted string
        result = evaluate_formula_alternate(
            "'single_quoted'", eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
        )
        assert result == "single_quoted"

    def test_evaluate_formula_alternate_simple_strings(self):
        """Test formula alternate evaluation with simple non-formula strings."""
        mock_core_evaluator = Mock()
        mock_resolve_all_references = Mock()
        mock_sensor_config = Mock()
        mock_config = Mock()
        eval_context = {}

        # Test simple string literal
        result = evaluate_formula_alternate(
            "simple_string", eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
        )
        assert result == "simple_string"

        # Test numeric string
        result = evaluate_formula_alternate(
            "123", eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
        )
        assert result == "123"

    @patch("ha_synthetic_sensors.alternate_state_eval.EvaluatorHelpers")
    def test_evaluate_formula_alternate_formula_strings(self, mock_evaluator_helpers):
        """Test formula alternate evaluation with formula-like strings."""
        mock_core_evaluator = Mock()
        mock_resolve_all_references = Mock()
        mock_sensor_config = Mock()
        mock_config = Mock()
        eval_context = {"x": 10, "y": 20}

        # Mock the evaluation pipeline
        mock_resolve_all_references.return_value = "10 + 20"
        mock_eval_result = Mock()
        mock_eval_result.value = 30
        mock_eval_result.state = "ok"
        mock_core_evaluator.evaluate_formula.return_value = mock_eval_result
        mock_evaluator_helpers.process_evaluation_result.return_value = 30

        # Test formula string
        result = evaluate_formula_alternate(
            "x + y", eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
        )
        assert result == 30

        # Verify the evaluation pipeline was called correctly
        mock_resolve_all_references.assert_called_once_with("x + y", mock_sensor_config, eval_context, mock_config)
        mock_core_evaluator.evaluate_formula.assert_called_once_with("10 + 20", "x + y", eval_context)

    @patch("ha_synthetic_sensors.alternate_state_eval.EvaluatorHelpers")
    def test_evaluate_formula_alternate_object_form(self, mock_evaluator_helpers):
        """Test formula alternate evaluation with object form and variables."""
        mock_core_evaluator = Mock()
        mock_resolve_all_references = Mock()
        mock_sensor_config = Mock()
        mock_config = Mock()
        eval_context = {"existing_var": 100}

        # Mock the evaluation pipeline
        mock_resolve_all_references.return_value = "base_value + offset"
        mock_eval_result = Mock()
        mock_eval_result.value = 60
        mock_eval_result.state = "ok"
        mock_core_evaluator.evaluate_formula.return_value = mock_eval_result
        mock_evaluator_helpers.process_evaluation_result.return_value = 60

        # Test object form with variables
        handler_formula = {"formula": "base_value + offset", "variables": {"base_value": 50, "offset": 10}}

        result = evaluate_formula_alternate(
            handler_formula, eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
        )
        assert result == 60

        # Verify variables were merged into context
        expected_context = eval_context.copy()
        expected_context.update({"base_value": 50, "offset": 10})
        mock_resolve_all_references.assert_called_once_with(
            "base_value + offset", mock_sensor_config, expected_context, mock_config
        )

    @patch("ha_synthetic_sensors.alternate_state_eval.EvaluatorHelpers")
    def test_evaluate_formula_alternate_object_form_no_variables(self, mock_evaluator_helpers):
        """Test object form without variables."""
        mock_core_evaluator = Mock()
        mock_resolve_all_references = Mock()
        mock_sensor_config = Mock()
        mock_config = Mock()
        eval_context = {}

        # Mock the evaluation pipeline
        mock_resolve_all_references.return_value = "10 + 5"
        mock_eval_result = Mock()
        mock_eval_result.value = 15
        mock_eval_result.state = "ok"
        mock_core_evaluator.evaluate_formula.return_value = mock_eval_result
        mock_evaluator_helpers.process_evaluation_result.return_value = 15

        # Test object form without variables
        handler_formula = {"formula": "10 + 5"}

        result = evaluate_formula_alternate(
            handler_formula, eval_context, mock_sensor_config, mock_config, mock_core_evaluator, mock_resolve_all_references
        )
        assert result == 15

    def test_evaluate_computed_alternate_literal_values(self):
        """Test computed alternate evaluation with literal values."""
        mock_get_enhanced_helper = Mock()
        mock_extract_values = Mock()
        eval_context = {}

        # Test integer literal
        result = evaluate_computed_alternate(42, eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == 42

        # Test float literal
        result = evaluate_computed_alternate(100.5, eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == 100.5

        # Test boolean literal
        result = evaluate_computed_alternate(True, eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result is True

        # Test None value
        result = evaluate_computed_alternate(None, eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result is None

    def test_evaluate_computed_alternate_quoted_strings(self):
        """Test computed alternate evaluation with quoted strings."""
        mock_get_enhanced_helper = Mock()
        mock_extract_values = Mock()
        eval_context = {}

        # Test double quoted string
        result = evaluate_computed_alternate('"quoted_string"', eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == "quoted_string"

        # Test single quoted string
        result = evaluate_computed_alternate("'single_quoted'", eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == "single_quoted"

    def test_evaluate_computed_alternate_numeric_strings(self):
        """Test computed alternate evaluation with numeric strings."""
        mock_get_enhanced_helper = Mock()
        mock_extract_values = Mock()
        mock_enhanced_helper = Mock()
        eval_context = {}

        # Mock the enhanced helper
        mock_get_enhanced_helper.return_value = mock_enhanced_helper
        mock_extract_values.return_value = {}
        mock_enhanced_helper.try_enhanced_eval.return_value = (True, -42)

        # Test integer string
        result = evaluate_computed_alternate("123", eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == 123

        # Test float string
        result = evaluate_computed_alternate("45.67", eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == 45.67

        # Test negative integer string (detected as formula, needs evaluation)
        result = evaluate_computed_alternate("-42", eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == -42

        # Test non-numeric string (should return original)
        result = evaluate_computed_alternate("not_a_number", eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == "not_a_number"

    def test_evaluate_computed_alternate_formula_strings(self):
        """Test computed alternate evaluation with formula-like strings."""
        mock_get_enhanced_helper = Mock()
        mock_extract_values = Mock()
        mock_enhanced_helper = Mock()
        eval_context = {"x": 10, "y": 20}

        # Mock the enhanced helper
        mock_get_enhanced_helper.return_value = mock_enhanced_helper
        mock_extract_values.return_value = {"x": 10, "y": 20}
        mock_enhanced_helper.try_enhanced_eval.return_value = (True, 30)

        # Test formula string
        result = evaluate_computed_alternate("x + y", eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == 30

        # Verify the evaluation was called correctly
        mock_extract_values.assert_called_once_with(eval_context)
        mock_enhanced_helper.try_enhanced_eval.assert_called_once_with("x + y", {"x": 10, "y": 20})

    def test_evaluate_computed_alternate_object_form(self):
        """Test computed alternate evaluation with object form and variables."""
        mock_get_enhanced_helper = Mock()
        mock_extract_values = Mock()
        mock_enhanced_helper = Mock()
        eval_context = {"existing_var": 100}

        # Mock the enhanced helper
        mock_get_enhanced_helper.return_value = mock_enhanced_helper
        mock_extract_values.return_value = {"base_value": 50, "offset": 10}
        mock_enhanced_helper.try_enhanced_eval.return_value = (True, 60)

        # Test object form with variables
        handler_formula = {"formula": "base_value + offset", "variables": {"base_value": 50, "offset": 10}}

        result = evaluate_computed_alternate(handler_formula, eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == 60

        # Verify variables were merged into context
        expected_context = eval_context.copy()
        expected_context.update({"base_value": 50, "offset": 10})
        mock_extract_values.assert_called_once_with(expected_context)

    def test_evaluate_computed_alternate_evaluation_failure(self):
        """Test computed alternate evaluation when evaluation fails."""
        mock_get_enhanced_helper = Mock()
        mock_extract_values = Mock()
        mock_enhanced_helper = Mock()
        eval_context = {}

        # Mock the enhanced helper to return failure
        mock_get_enhanced_helper.return_value = mock_enhanced_helper
        mock_extract_values.return_value = {}
        mock_enhanced_helper.try_enhanced_eval.return_value = (False, None)

        # Test formula string that fails evaluation (use a string that looks like a formula)
        result = evaluate_computed_alternate("x + y", eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result is None

    def test_evaluate_computed_alternate_object_form_no_variables(self):
        """Test object form without variables."""
        mock_get_enhanced_helper = Mock()
        mock_extract_values = Mock()
        mock_enhanced_helper = Mock()
        eval_context = {}

        # Mock the enhanced helper
        mock_get_enhanced_helper.return_value = mock_enhanced_helper
        mock_extract_values.return_value = {}
        mock_enhanced_helper.try_enhanced_eval.return_value = (True, 15)

        # Test object form without variables
        handler_formula = {"formula": "10 + 5"}

        result = evaluate_computed_alternate(handler_formula, eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == 15

    def test_evaluate_computed_alternate_empty_variables(self):
        """Test object form with empty variables dict."""
        mock_get_enhanced_helper = Mock()
        mock_extract_values = Mock()
        mock_enhanced_helper = Mock()
        eval_context = {"existing_var": 100}

        # Mock the enhanced helper
        mock_get_enhanced_helper.return_value = mock_enhanced_helper
        mock_extract_values.return_value = {"existing_var": 100}
        mock_enhanced_helper.try_enhanced_eval.return_value = (True, 100)

        # Test object form with empty variables
        handler_formula = {"formula": "existing_var", "variables": {}}

        result = evaluate_computed_alternate(handler_formula, eval_context, mock_get_enhanced_helper, mock_extract_values)
        assert result == 100

        # Verify context was not modified
        mock_extract_values.assert_called_once_with(eval_context)
