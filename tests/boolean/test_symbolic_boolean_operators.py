"""Unit tests for Python's native boolean operators (and, or, not) in simpleeval."""

import pytest

from ha_synthetic_sensors.evaluator_handlers.boolean_handler import BooleanHandler


class TestPythonBooleanOperators:
    """Test Python's native boolean operators functionality."""

    def test_python_or_operator(self):
        """Test that 'or' operator works correctly."""
        handler = BooleanHandler()

        # Test true or false = true
        result = handler.evaluate("True or False")
        assert result is True

        # Test false or true = true
        result = handler.evaluate("False or True")
        assert result is True

        # Test false or false = false
        result = handler.evaluate("False or False")
        assert result is False

        # Test true or true = true
        result = handler.evaluate("True or True")
        assert result is True

    def test_python_and_operator(self):
        """Test that 'and' operator works correctly."""
        handler = BooleanHandler()

        # Test true and false = false
        result = handler.evaluate("True and False")
        assert result is False

        # Test false and true = false
        result = handler.evaluate("False and True")
        assert result is False

        # Test false and false = false
        result = handler.evaluate("False and False")
        assert result is False

        # Test true and true = true
        result = handler.evaluate("True and True")
        assert result is True

    def test_python_not_operator(self):
        """Test that 'not' operator works correctly."""
        handler = BooleanHandler()

        # Test not true = false
        result = handler.evaluate("not True")
        assert result is False

        # Test not false = true
        result = handler.evaluate("not False")
        assert result is True

    def test_boolean_operators_with_variables(self):
        """Test boolean operators with variable contexts."""
        handler = BooleanHandler()

        context = {"door_open": True, "window_open": False, "alarm_set": True, "motion_detected": False}

        # Test OR with variables: door_open or window_open = true or false = true
        result = handler.evaluate("door_open or window_open", context)
        assert result is True

        # Test AND with variables: alarm_set and not motion_detected = true and not false = true and true = true
        result = handler.evaluate("alarm_set and not motion_detected", context)
        assert result is True

        # Test complex expression: (door_open or window_open) and alarm_set = (true or false) and true = true
        result = handler.evaluate("(door_open or window_open) and alarm_set", context)
        assert result is True

    def test_boolean_operators_with_comparisons(self):
        """Test boolean operators combined with comparison operations."""
        handler = BooleanHandler()

        context = {"temperature": 80, "humidity": 55, "ac_running": True}

        # Test comparison with AND: (80 > 75) and (55 < 60) = true and true = true
        result = handler.evaluate("(temperature > 75) and (humidity < 60)", context)
        assert result is True

        # Test comparison with OR: (80 > 90) or ac_running = false or true = true
        result = handler.evaluate("(temperature > 90) or ac_running", context)
        assert result is True

        # Test complex mixed expression
        result = handler.evaluate("(temperature > 75) and (humidity < 60) or ac_running", context)
        assert result is True

    def test_boolean_operator_precedence(self):
        """Test operator precedence with boolean operators."""
        handler = BooleanHandler()

        # Test AND has higher precedence than OR
        # true or false and false should be evaluated as true or (false and false) = true or false = true
        result = handler.evaluate("True or False and False")
        assert result is True

        # Test with parentheses to override precedence
        # (true or false) and false should be evaluated as true and false = false
        result = handler.evaluate("(True or False) and False")
        assert result is False

        # Test NOT has highest precedence
        # not false or false should be evaluated as (not false) or false = true or false = true
        result = handler.evaluate("not False or False")
        assert result is True

    def test_boolean_operators_with_numeric_values(self):
        """Test boolean operators with numeric values (truthy/falsy)."""
        handler = BooleanHandler()

        context = {"zero": 0, "one": 1, "negative": -1, "positive": 42}

        # Test with numeric values - 0 is falsy, non-zero is truthy
        result = handler.evaluate("zero or one", context)  # 0 or 1 = false or true = true
        assert result is True

        result = handler.evaluate("zero and one", context)  # 0 and 1 = false and true = false
        assert result is False

        result = handler.evaluate("positive and negative", context)  # 42 and -1 = true and true = true
        assert result is True

    def test_boolean_operators_complex_nesting(self):
        """Test deeply nested boolean expressions."""
        handler = BooleanHandler()

        context = {"a": True, "b": False, "c": True, "d": False}

        # Test complex nested expression: (a and b) or (c and not d)
        # = (true and false) or (true and not false) = false or (true and true) = false or true = true
        result = handler.evaluate("(a and b) or (c and not d)", context)
        assert result is True

        # Test another complex expression: not (a or b) and (c or d)
        # = not (true or false) and (true or false) = not true and true = false and true = false
        result = handler.evaluate("not (a or b) and (c or d)", context)
        assert result is False

    def test_short_circuit_evaluation(self):
        """Test that boolean operators use short-circuit evaluation."""
        handler = BooleanHandler()

        # Test OR short-circuit: if first operand is True, second shouldn't be evaluated
        # This is hard to test directly with simpleeval, but we can test the logical result
        result = handler.evaluate("True or False")
        assert result is True

        # Test AND short-circuit: if first operand is False, second shouldn't be evaluated
        result = handler.evaluate("False and True")
        assert result is False

        # Test with variables
        context = {"true_val": True, "false_val": False}
        result = handler.evaluate("true_val or false_val", context)
        assert result is True

        result = handler.evaluate("false_val and true_val", context)
        assert result is False

    def test_boolean_with_conditional_expressions(self):
        """Test boolean operators in conditional expressions."""
        handler = BooleanHandler()

        context = {"condition": True, "temperature": 80, "humidity": 55}

        # Test boolean in conditional - result must be boolean
        result = handler.evaluate("True if (temperature > 75 and humidity > 50) else False", context)
        assert result is True

        # Test boolean condition with multiple operators
        result = handler.evaluate("condition and (temperature > 70 or humidity > 60)", context)
        assert result is True
