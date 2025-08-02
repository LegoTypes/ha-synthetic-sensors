"""
Unit tests for advanced string functions (contains, startswith, endswith, length, replace).
"""

import pytest

from ha_synthetic_sensors.evaluator_handlers.string_handler import StringHandler, ArithmeticTokenizerConfig
from ha_synthetic_sensors.formula_router import FormulaSyntaxError


class TestAdvancedStringFunctions:
    """Test cases for advanced string function implementations."""

    @pytest.fixture
    def handler(self):
        """Create a StringHandler instance for testing."""
        config = ArithmeticTokenizerConfig(max_iterations=10, enable_iteration_logging=True)
        return StringHandler(config)

    def test_can_handle_advanced_string_functions(self, handler):
        """Test that advanced string functions are properly detected by can_handle."""
        advanced_function_formulas = [
            "contains('hello world', 'world')",
            "startswith('hello world', 'hello')",
            "endswith('hello world', 'world')",
            "length('hello world')",
            "replace('hello world', 'world', 'universe')",
            "contains(device_name, 'sensor')",
            "startswith(status, 'on')",
        ]

        for formula in advanced_function_formulas:
            assert handler.can_handle(formula), f"Should handle: {formula}"

    def test_contains_function(self, handler):
        """Test contains() function with various inputs."""
        test_cases = [
            ("contains('hello world', 'world')", "true"),
            ("contains('hello world', 'hello')", "true"),
            ("contains('hello world', 'xyz')", "false"),
            ("contains('Temperature Sensor', 'Sensor')", "true"),
            ("contains('Temperature Sensor', 'sensor')", "false"),  # Case sensitive
            ("contains('', 'test')", "false"),
            ("contains('test', '')", "true"),  # Empty string is in everything
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_startswith_function(self, handler):
        """Test startswith() function with various inputs."""
        test_cases = [
            ("startswith('hello world', 'hello')", "true"),
            ("startswith('hello world', 'world')", "false"),
            ("startswith('Temperature Sensor', 'Temperature')", "true"),
            ("startswith('Temperature Sensor', 'Sensor')", "false"),
            ("startswith('', 'test')", "false"),
            ("startswith('test', '')", "true"),  # Everything starts with empty string
            ("startswith('hello', 'hello world')", "false"),  # Prefix longer than string
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_endswith_function(self, handler):
        """Test endswith() function with various inputs."""
        test_cases = [
            ("endswith('hello world', 'world')", "true"),
            ("endswith('hello world', 'hello')", "false"),
            ("endswith('Temperature Sensor', 'Sensor')", "true"),
            ("endswith('Temperature Sensor', 'Temperature')", "false"),
            ("endswith('', 'test')", "false"),
            ("endswith('test', '')", "true"),  # Everything ends with empty string
            ("endswith('hello', 'hello world')", "false"),  # Suffix longer than string
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_length_function(self, handler):
        """Test length() function with various inputs."""
        test_cases = [
            ("length('hello world')", "11"),
            ("length('hello')", "5"),
            ("length('')", "0"),
            ("length('Temperature Sensor Device')", "25"),
            ("length('🌡️')", "2"),  # Unicode character
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_replace_function(self, handler):
        """Test replace() function with various inputs."""
        test_cases = [
            ("replace('hello world', 'world', 'universe')", "hello universe"),
            ("replace('hello world', 'hello', 'hi')", "hi world"),
            ("replace('hello hello', 'hello', 'hi')", "hi hello"),  # Only first occurrence
            ("replace('Temperature Sensor', 'Sensor', 'Device')", "Temperature Device"),
            ("replace('hello world', 'xyz', 'abc')", "hello world"),  # No match
            ("replace('', 'test', 'abc')", ""),  # Empty string
            ("replace('test', '', 'abc')", "abctest"),  # Replace empty string
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_advanced_functions_with_context(self, handler):
        """Test advanced string functions with context variables."""
        context = {
            "device_name": "Temperature Sensor",
            "status": "online_active",
            "room": "living_room",
            "message": "Device is working properly",
        }

        test_cases = [
            ("contains(device_name, 'Sensor')", "true"),
            ("startswith(status, 'online')", "true"),
            ("endswith(room, 'room')", "true"),
            ("length(device_name)", "18"),
            ("replace(room, '_', ' ')", "living room"),
            ("contains(message, 'working')", "true"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula, context)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_nested_advanced_functions(self, handler):
        """Test nested calls with advanced string functions."""
        test_cases = [
            ("contains(lower('HELLO WORLD'), 'world')", "true"),
            ("startswith(trim('  hello world  '), 'hello')", "true"),
            ("length(trim('  hello  '))", "5"),
            ("replace(upper('hello world'), 'WORLD', 'UNIVERSE')", "HELLO UNIVERSE"),
            ("contains(replace('old text', 'old', 'new'), 'new')", "true"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_advanced_functions_in_concatenation(self, handler):
        """Test advanced functions used within concatenation."""
        context = {
            "device_name": "Temperature Sensor",
            "status": "online",
            "room": "living_room",
        }

        test_cases = [
            ("'Device contains Sensor: ' + contains(device_name, 'Sensor')", "Device contains Sensor: true"),
            ("'Status starts with on: ' + startswith(status, 'on')", "Status starts with on: true"),
            ("'Name length: ' + length(device_name)", "Name length: 18"),
            ("'Clean room: ' + replace(room, '_', ' ')", "Clean room: living room"),
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula, context)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_parameter_count_validation(self, handler):
        """Test parameter count validation for multi-parameter functions."""
        from ha_synthetic_sensors.formula_router import FormulaSyntaxError

        # Test functions with wrong parameter counts
        error_cases = [
            "contains('hello')",  # Missing second parameter
            "contains('hello', 'world', 'extra')",  # Too many parameters
            "startswith('hello')",  # Missing second parameter
            "endswith('hello')",  # Missing second parameter
            "replace('hello', 'old')",  # Missing third parameter
            "replace('hello', 'old', 'new', 'extra')",  # Too many parameters
        ]

        for formula in error_cases:
            with pytest.raises(FormulaSyntaxError) as exc_info:
                handler.evaluate(formula)

            error_msg = str(exc_info.value)
            assert "requires exactly" in error_msg, f"Error message should mention parameter count: {error_msg}"

    def test_complex_parameter_expressions(self, handler):
        """Test advanced functions with complex parameter expressions."""
        context = {
            "prefix": "Device:",
            "suffix": "active",
            "old_text": "temp_sensor",
            "new_text": "temperature_sensor",
        }

        test_cases = [
            ("contains('Device: Temperature', prefix + ' Temp')", "true"),
            ("startswith('status_active', 'status_' + suffix)", "true"),  # 'status_active' starts with 'status_active'
            ("replace(old_text, 'temp', new_text)", "temperature_sensor_sensor"),  # Note: replaces 'temp' with full new_text
            ("length(prefix + ' ' + suffix)", "14"),  # "Device: active"
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula, context)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_edge_cases_and_special_characters(self, handler):
        """Test advanced functions with edge cases and special characters."""
        test_cases = [
            ("contains('Hello 🌡️ World', '🌡️')", "true"),
            ("startswith('🌡️ Temperature', '🌡️')", "true"),
            ("length('🌡️📊🏠')", "4"),  # Unicode string length in Python
            ("replace('temp-sensor-01', '-', '_')", "temp_sensor-01"),  # Only first occurrence
            ("contains('Line1\\nLine2', '\\n')", "true"),  # Literal backslash-n
        ]

        for formula, expected in test_cases:
            result = handler.evaluate(formula)
            assert result == expected, f"Formula {formula} should return '{expected}', got '{result}'"

    def test_boolean_string_results(self, handler):
        """Test that boolean functions return string 'true'/'false' not Python booleans."""
        # Test return types are strings
        result_contains = handler.evaluate("contains('hello', 'ell')")
        result_startswith = handler.evaluate("startswith('hello', 'hel')")
        result_endswith = handler.evaluate("endswith('hello', 'llo')")

        assert isinstance(result_contains, str), "contains() should return string"
        assert isinstance(result_startswith, str), "startswith() should return string"
        assert isinstance(result_endswith, str), "endswith() should return string"

        assert result_contains == "true"
        assert result_startswith == "true"
        assert result_endswith == "true"
