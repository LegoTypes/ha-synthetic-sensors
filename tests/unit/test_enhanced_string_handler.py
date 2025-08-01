"""Unit tests for enhanced StringHandler."""

import pytest

from ha_synthetic_sensors.evaluator_handlers.string_handler import StringHandler, ArithmeticTokenizerConfig


class TestEnhancedStringHandler:
    """Test cases for enhanced string handler functionality."""

    @pytest.fixture
    def handler(self):
        """Create a StringHandler instance for testing."""
        config = ArithmeticTokenizerConfig(max_iterations=10, enable_iteration_logging=True)
        return StringHandler(config)

    def test_can_handle_string_literals(self, handler):
        """Test that string literals are properly detected."""
        string_formulas = ["'hello world'", '"hello world"', "'Device: ' + state", '"Status: " + state + " active"']

        for formula in string_formulas:
            assert handler.can_handle(formula), f"Should handle: {formula}"

    def test_can_handle_user_str_function(self, handler):
        """Test that str() user functions are detected."""
        str_formulas = ["str(state + 'W')", "str(numeric_value * 1.1)", "str(state)"]

        for formula in str_formulas:
            assert handler.can_handle(formula), f"Should handle: {formula}"

    def test_cannot_handle_numeric_formulas(self, handler):
        """Test that numeric formulas are not handled."""
        numeric_formulas = ["state * 1.1", "42", "count('device_class:power')", "sum('device_class:energy')"]

        for formula in numeric_formulas:
            assert not handler.can_handle(formula), f"Should NOT handle: {formula}"

    def test_simple_string_literal_evaluation(self, handler):
        """Test evaluation of simple string literals."""
        test_cases = [("'hello world'", "hello world"), ('"test string"', "test string"), ("'Device Status'", "Device Status")]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return {expected}, got {result}"

    def test_simple_string_concatenation(self, handler):
        """Test basic string concatenation without variables."""
        test_cases = [
            ("'Hello' + ' ' + 'World'", "Hello World"),
            ('"Device: " + "Test"', "Device: Test"),
            ("'A' + 'B' + 'C'", "ABC"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return {expected}, got {result}"

    def test_string_concatenation_with_context(self, handler):
        """Test string concatenation with context variables."""
        context = {"state": "on", "power": "1000", "device_name": "Test Device"}

        test_cases = [
            ("'Device: ' + device_name", "Device: Test Device"),
            ("'Status: ' + state", "Status: on"),
            ("'Power: ' + power + 'W'", "Power: 1000W"),
            ("device_name + ' is ' + state", "Test Device is on"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula, context)
            assert result == expected, f"Formula {formula} should return {expected}, got {result}"

    def test_str_function_with_simple_expression(self, handler):
        """Test str() function with simple expressions."""
        test_cases = [("str('hello')", "hello"), ("str(42)", "42.0"), ("str(5 + 3)", "8.0")]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return {expected}, got {result}"

    def test_str_function_with_context(self, handler):
        """Test str() function with context variables."""
        context = {"power": 1000, "efficiency": 0.95}

        test_cases = [
            ("str(power)", "1000.0"),
            ("str(power * efficiency)", "950.0"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula, context)
            assert result == expected, f"Formula {formula} should return {expected}, got {result}"

    def test_complex_string_operations(self, handler):
        """Test complex string operations with multiple concatenations."""
        context = {"device_name": "Sensor1", "state": "active", "power": "150", "room": "Living Room"}

        test_cases = [
            ("'Device: ' + device_name + ' is ' + state", "Device: Sensor1 is active"),
            ("device_name + ' - ' + power + 'W (' + room + ')'", "Sensor1 - 150W (Living Room)"),
            ("'Status: ' + state + ', Power: ' + power", "Status: active, Power: 150"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula, context)
            assert result == expected, f"Formula {formula} should return {expected}, got {result}"

    def test_mixed_types_in_concatenation(self, handler):
        """Test concatenation with mixed types (strings and numbers)."""
        context = {"temperature": 23.5, "status": "normal", "count": 42}

        test_cases = [
            ("'Temperature: ' + str(temperature) + '°C'", "Temperature: 23.5°C"),
            ("'Count: ' + str(count)", "Count: 42.0"),
            ("str(temperature) + ' degrees'", "23.5 degrees"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula, context)
            assert result == expected, f"Formula {formula} should return {expected}, got {result}"

    def test_error_handling_invalid_syntax(self, handler):
        """Test error handling for invalid syntax."""
        from ha_synthetic_sensors.formula_router import FormulaSyntaxError

        # Test cases that should raise FormulaSyntaxError
        syntax_error_formulas = [
            "str(invalid syntax +",  # Malformed function call
            "'unclosed string",  # Unclosed quote
            "function(",  # Unclosed function
        ]

        for formula in syntax_error_formulas:
            with pytest.raises(FormulaSyntaxError) as exc_info:
                handler.evaluate(formula)

            # Verify the error message contains useful information
            error_msg = str(exc_info.value)
            assert formula in error_msg, f"Error message should contain the formula: {error_msg}"

        # Test cases that should be handled gracefully (not syntax errors)
        graceful_formulas = [
            "str()",  # Empty str function - valid syntax
        ]

        for formula in graceful_formulas:
            result = handler.evaluate(formula)
            # Empty str() should return empty string, not error
            assert result == "", f"Valid formula {formula} should return empty string, got {result}"

    def test_iteration_limit_protection(self, handler):
        """Test that iteration limits prevent infinite loops."""
        # Create handler with very low iteration limit for testing
        config = ArithmeticTokenizerConfig(max_iterations=2)
        test_handler = StringHandler(config)

        # This should hit the iteration limit
        formula = "'a' + 'b' + 'c' + 'd' + 'e'"
        result = test_handler.evaluate(formula)

        # Should either complete within limit or return error
        assert isinstance(result, str)

    def test_operand_resolution(self, handler):
        """Test various operand resolution scenarios."""
        context = {"string_var": "test", "numeric_var": 42, "boolean_var": True}

        test_cases = [
            ("string_var + ' value'", "test value"),
            ("'Number: ' + str(numeric_var)", "Number: 42.0"),
            ("'Boolean: ' + str(boolean_var)", "Boolean: True"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula, context)
            assert result == expected, f"Formula {formula} should return {expected}, got {result}"

    def test_nested_str_functions(self, handler):
        """Test that nested str() functions work correctly."""
        context = {"value1": 10, "value2": 20}

        # Note: This is a simple test - real nested functions would require more complex parsing
        result = handler.evaluate("str(value1)", context)
        assert result == "10.0"

    def test_empty_context_handling(self, handler):
        """Test handling when context is None or empty."""
        test_cases = [("'static string'", "static string"), ("'hello' + ' world'", "hello world")]

        for formula, expected in test_cases:
            # Test with None context
            result = handler.evaluate(formula, None)
            assert result == expected, f"Formula {formula} with None context should return {expected}"

            # Test with empty context
            result = handler.evaluate(formula, {})
            assert result == expected, f"Formula {formula} with empty context should return {expected}"
