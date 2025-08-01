"""
Unit tests for basic string functions (trim, lower, upper, title).
"""

import pytest

from ha_synthetic_sensors.evaluator_handlers.string_handler import StringHandler, ArithmeticTokenizerConfig


class TestStringFunctions:
    """Test cases for basic string function implementations."""

    @pytest.fixture
    def handler(self):
        """Create a StringHandler instance for testing."""
        config = ArithmeticTokenizerConfig(max_iterations=10, enable_iteration_logging=True)
        return StringHandler(config)

    def test_can_handle_string_functions(self, handler):
        """Test that string functions are properly detected by can_handle."""
        string_function_formulas = [
            "trim('  hello world  ')",
            "lower('Hello World')",
            "upper('hello world')",
            "title('hello world')",
            "trim(state)",
            "lower(device_name)",
        ]

        for formula in string_function_formulas:
            assert handler.can_handle(formula), f"Should handle: {formula}"

    def test_cannot_handle_non_string_functions(self, handler):
        """Test that non-string functions are not handled."""
        non_string_formulas = [
            "numeric(state)",
            "date('2023-01-01')",
            "count('device_class:power')",
            "state * 1.1",
        ]

        for formula in non_string_formulas:
            assert not handler.can_handle(formula), f"Should NOT handle: {formula}"

    def test_trim_function(self, handler):
        """Test trim() function with various inputs."""
        test_cases = [
            ("trim('  hello world  ')", "hello world"),
            ("trim(' leading space')", "leading space"),
            ("trim('trailing space ')", "trailing space"),
            ("trim('  both sides  ')", "both sides"),
            ("trim('no whitespace')", "no whitespace"),
            ("trim('')", ""),
            ("trim('   ')", ""),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_lower_function(self, handler):
        """Test lower() function with various inputs."""
        test_cases = [
            ("lower('Hello World')", "hello world"),
            ("lower('UPPERCASE')", "uppercase"),
            ("lower('MiXeD cAsE')", "mixed case"),
            ("lower('already lowercase')", "already lowercase"),
            ("lower('')", ""),
            ("lower('123 Numbers')", "123 numbers"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_upper_function(self, handler):
        """Test upper() function with various inputs."""
        test_cases = [
            ("upper('hello world')", "HELLO WORLD"),
            ("upper('lowercase')", "LOWERCASE"),
            ("upper('MiXeD cAsE')", "MIXED CASE"),
            ("upper('ALREADY UPPERCASE')", "ALREADY UPPERCASE"),
            ("upper('')", ""),
            ("upper('123 numbers')", "123 NUMBERS"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_title_function(self, handler):
        """Test title() function with various inputs."""
        test_cases = [
            ("title('hello world')", "Hello World"),
            ("title('UPPERCASE')", "Uppercase"),
            ("title('MiXeD cAsE')", "Mixed Case"),
            ("title('already Title Case')", "Already Title Case"),
            ("title('')", ""),
            ("title('the quick brown fox')", "The Quick Brown Fox"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_string_functions_with_context(self, handler):
        """Test string functions with context variables."""
        context = {
            "device_name": "  Temperature Sensor  ",
            "status": "ONLINE",
            "message": "hello world",
            "room": "living room",
        }

        test_cases = [
            ("trim(device_name)", "Temperature Sensor"),
            ("lower(status)", "online"),
            ("upper(message)", "HELLO WORLD"),
            ("title(room)", "Living Room"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula, context)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_nested_string_functions(self, handler):
        """Test nested string function calls."""
        test_cases = [
            ("trim(lower('  HELLO WORLD  '))", "hello world"),
            ("upper(trim('  hello world  '))", "HELLO WORLD"),
            ("title(trim(lower('  HELLO WORLD  ')))", "Hello World"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_string_functions_with_concatenation(self, handler):
        """Test string functions used within concatenation."""
        context = {
            "device_name": "  sensor  ",
            "status": "active",
        }

        test_cases = [
            ("'Device: ' + trim(device_name)", "Device: sensor"),
            ("upper(status) + ' - Status'", "ACTIVE - Status"),
            # ("title('device') + ': ' + trim(device_name)", "Device: sensor"),  # TODO: Fix complex concatenation
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula, context)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_string_functions_with_numeric_conversion(self, handler):
        """Test string functions applied to numeric values."""
        context = {
            "temperature": 23.5,
            "count": 42,
        }

        test_cases = [
            ("upper(str(temperature))", "23.5"),
            ("lower(str(count))", "42.0"),
            ("title(str(temperature) + ' degrees')", "23.5 Degrees"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula, context)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_string_functions_error_handling(self, handler):
        """Test error handling for string functions."""
        from ha_synthetic_sensors.formula_router import FormulaSyntaxError

        # Test malformed function calls
        error_formulas = [
            "trim(unclosed string '",
            "lower(",
            "upper(missing closing",
        ]

        for formula in error_formulas:
            with pytest.raises(FormulaSyntaxError):
                handler.evaluate(formula)

    def test_string_functions_empty_and_none_context(self, handler):
        """Test string functions with empty or None context."""
        test_cases = [
            ("trim('  test  ')", "test"),
            ("lower('TEST')", "test"),
            ("upper('test')", "TEST"),
            ("title('test case')", "Test Case"),
        ]

        for formula, expected in test_cases:
            # Test with None context
            result = handler.evaluate(formula, None)
            assert result == expected, f"Formula {formula} with None context should return '{expected}'"

            # Test with empty context
            result = handler.evaluate(formula, {})
            assert result == expected, f"Formula {formula} with empty context should return '{expected}'"
