"""
Tests for extended string functions in StringHandler.

This module tests the extended string manipulation functions including:
- String validation: isalpha(), isdigit(), isnumeric(), isalnum()
- Advanced replacement: replace_all()
- String splitting/joining: split(), join()
- String padding: pad_left(), pad_right(), center()
"""

import pytest
from unittest.mock import MagicMock

from ha_synthetic_sensors.evaluator_handlers.string_handler import StringHandler
from ha_synthetic_sensors.formula_router import FormulaSyntaxError
from ha_synthetic_sensors.constants_formula import (
    ERROR_PATTERN_PARAMETER_COUNT_EXACT,
    ERROR_PATTERN_PARAMETER_COUNT_RANGE,
    ERROR_PATTERN_FILL_CHAR_LENGTH,
)


class TestExtendedStringFunctions:
    """Test extended string function implementations."""

    @pytest.fixture
    def handler(self):
        """Create StringHandler instance for testing."""
        return StringHandler()

    def test_can_handle_extended_functions(self, handler):
        """Test that handler can identify extended string functions."""
        # Validation functions
        assert handler.can_handle("isalpha('hello')")
        assert handler.can_handle("isdigit('123')")
        assert handler.can_handle("isnumeric('456')")
        assert handler.can_handle("isalnum('abc123')")

        # Advanced replacement
        assert handler.can_handle("replace_all('hello', 'l', 'x')")

        # Split/join functions
        assert handler.can_handle("split('a,b,c', ',')")
        assert handler.can_handle("join('a,b,c', ' | ')")

        # Padding functions
        assert handler.can_handle("pad_left('hello', 10)")
        assert handler.can_handle("pad_right('hello', 10, '*')")
        assert handler.can_handle("center('hello', 15, '-')")

    # String Validation Functions Tests
    def test_isalpha_function(self, handler):
        """Test isalpha() function."""
        assert handler.evaluate("isalpha('hello')") == "true"
        assert handler.evaluate("isalpha('Hello')") == "true"
        assert handler.evaluate("isalpha('hello123')") == "false"
        assert handler.evaluate("isalpha('123')") == "false"
        assert handler.evaluate("isalpha('hello world')") == "false"  # Space
        assert handler.evaluate("isalpha('')") == "false"  # Empty string

    def test_isdigit_function(self, handler):
        """Test isdigit() function."""
        assert handler.evaluate("isdigit('123')") == "true"
        assert handler.evaluate("isdigit('0')") == "true"
        assert handler.evaluate("isdigit('hello')") == "false"
        assert handler.evaluate("isdigit('123abc')") == "false"
        assert handler.evaluate("isdigit('12.3')") == "false"  # Decimal point
        assert handler.evaluate("isdigit('')") == "false"  # Empty string

    def test_isnumeric_function(self, handler):
        """Test isnumeric() function."""
        assert handler.evaluate("isnumeric('123')") == "true"
        assert handler.evaluate("isnumeric('0')") == "true"
        assert handler.evaluate("isnumeric('½')") == "true"  # Unicode numeric
        assert handler.evaluate("isnumeric('hello')") == "false"
        assert handler.evaluate("isnumeric('123abc')") == "false"
        assert handler.evaluate("isnumeric('')") == "false"  # Empty string

    def test_isalnum_function(self, handler):
        """Test isalnum() function."""
        assert handler.evaluate("isalnum('hello123')") == "true"
        assert handler.evaluate("isalnum('hello')") == "true"
        assert handler.evaluate("isalnum('123')") == "true"
        assert handler.evaluate("isalnum('hello world')") == "false"  # Space
        assert handler.evaluate("isalnum('hello!')") == "false"  # Special char
        assert handler.evaluate("isalnum('')") == "false"  # Empty string

    # Advanced Replacement Functions Tests
    def test_replace_all_function(self, handler):
        """Test replace_all() function."""
        assert handler.evaluate("replace_all('hello', 'l', 'x')") == "hexxo"
        assert handler.evaluate("replace_all('banana', 'a', 'o')") == "bonono"
        assert handler.evaluate("replace_all('test test test', 'test', 'demo')") == "demo demo demo"
        assert handler.evaluate("replace_all('hello', 'xyz', 'abc')") == "hello"  # No match
        assert handler.evaluate("replace_all('', 'a', 'b')") == ""  # Empty string

    def test_replace_all_with_context(self, handler):
        """Test replace_all() with context variables."""
        context = {"text": "hello world hello", "old_str": "hello", "new_str": "hi"}
        result = handler.evaluate("replace_all(text, old_str, new_str)", context)
        assert result == "hi world hi"

    # Split/Join Functions Tests
    def test_split_function(self, handler):
        """Test split() function."""
        # Split with delimiter
        assert handler.evaluate("split('a,b,c', ',')") == "a,b,c"
        assert handler.evaluate("split('hello world test', ' ')") == "hello,world,test"
        assert handler.evaluate("split('a|b|c', '|')") == "a,b,c"

        # Split without delimiter (whitespace)
        assert handler.evaluate("split('hello world test')") == "hello,world,test"
        assert handler.evaluate("split('  a   b   c  ')") == "a,b,c"  # Multiple spaces

        # Edge cases
        assert handler.evaluate("split('hello', ',')") == "hello"  # No delimiter found
        assert handler.evaluate("split('', ',')") == ""  # Empty string

    def test_join_function(self, handler):
        """Test join() function."""
        assert handler.evaluate("join('a,b,c', ' | ')") == "a | b | c"
        assert handler.evaluate("join('hello,world', ' ')") == "hello world"
        assert handler.evaluate("join('a,b,c', '')") == "abc"  # No delimiter
        assert handler.evaluate("join('single', ',')") == "single"  # Single item
        assert handler.evaluate("join('', ',')") == ""  # Empty string

    def test_split_join_roundtrip(self, handler):
        """Test split() and join() work together."""
        # This tests the comma-separated format assumption
        original = "hello,world,test"
        split_result = handler.evaluate("split('hello world test', ' ')")
        assert split_result == original
        join_result = handler.evaluate(f"join('{split_result}', ' ')")
        assert join_result == "hello world test"

    # Padding Functions Tests
    def test_pad_left_function(self, handler):
        """Test pad_left() function."""
        # Default padding (space)
        assert handler.evaluate("pad_left('hello', 10)") == "     hello"
        assert handler.evaluate("pad_left('test', 6)") == "  test"

        # Custom padding character
        assert handler.evaluate("pad_left('hello', 10, '*')") == "*****hello"
        assert handler.evaluate("pad_left('test', 7, '0')") == "000test"

        # No padding needed
        assert handler.evaluate("pad_left('hello', 5)") == "hello"
        assert handler.evaluate("pad_left('hello', 3)") == "hello"  # Shorter than text

    def test_pad_right_function(self, handler):
        """Test pad_right() function."""
        # Default padding (space)
        assert handler.evaluate("pad_right('hello', 10)") == "hello     "
        assert handler.evaluate("pad_right('test', 6)") == "test  "

        # Custom padding character
        assert handler.evaluate("pad_right('hello', 10, '*')") == "hello*****"
        assert handler.evaluate("pad_right('test', 7, '0')") == "test000"

        # No padding needed
        assert handler.evaluate("pad_right('hello', 5)") == "hello"
        assert handler.evaluate("pad_right('hello', 3)") == "hello"  # Shorter than text

    def test_center_function(self, handler):
        """Test center() function."""
        # Default padding (space)
        assert handler.evaluate("center('hello', 11)") == "   hello   "
        assert handler.evaluate("center('test', 8)") == "  test  "

        # Custom padding character
        assert handler.evaluate("center('hello', 11, '*')") == "***hello***"
        assert handler.evaluate("center('test', 8, '-')") == "--test--"

        # Odd width (extra padding goes to the right)
        assert handler.evaluate("center('hi', 5)") == "  hi "

        # No padding needed
        assert handler.evaluate("center('hello', 5)") == "hello"
        assert handler.evaluate("center('hello', 3)") == "hello"  # Shorter than text

    # Parameter Validation Tests
    def test_replace_all_parameter_validation(self, handler):
        """Test replace_all() parameter validation."""
        with pytest.raises(FormulaSyntaxError, match=ERROR_PATTERN_PARAMETER_COUNT_EXACT.format(function="replace_all")):
            handler.evaluate("replace_all('hello', 'l')")  # Missing parameter

        with pytest.raises(FormulaSyntaxError, match=ERROR_PATTERN_PARAMETER_COUNT_EXACT.format(function="replace_all")):
            handler.evaluate("replace_all('hello')")  # Too few parameters

    def test_split_parameter_validation(self, handler):
        """Test split() parameter validation."""
        with pytest.raises(FormulaSyntaxError, match=ERROR_PATTERN_PARAMETER_COUNT_RANGE.format(function="split")):
            handler.evaluate("split()")  # No parameters

        with pytest.raises(FormulaSyntaxError, match=ERROR_PATTERN_PARAMETER_COUNT_RANGE.format(function="split")):
            handler.evaluate("split('a', 'b', 'c')")  # Too many parameters

    def test_join_parameter_validation(self, handler):
        """Test join() parameter validation."""
        with pytest.raises(FormulaSyntaxError, match=ERROR_PATTERN_PARAMETER_COUNT_EXACT.format(function="join")):
            handler.evaluate("join('hello')")  # Missing parameter

        with pytest.raises(FormulaSyntaxError, match=ERROR_PATTERN_PARAMETER_COUNT_EXACT.format(function="join")):
            handler.evaluate("join('a', 'b', 'c')")  # Too many parameters

    def test_padding_parameter_validation(self, handler):
        """Test padding functions parameter validation."""
        # pad_left validation
        with pytest.raises(FormulaSyntaxError, match=ERROR_PATTERN_PARAMETER_COUNT_RANGE.format(function="pad_left")):
            handler.evaluate("pad_left('hello')")  # Missing width

        with pytest.raises(FormulaSyntaxError, match=ERROR_PATTERN_FILL_CHAR_LENGTH):
            handler.evaluate("pad_left('hello', 10, 'ab')")  # Multi-character fill

        # pad_right validation
        with pytest.raises(FormulaSyntaxError, match=ERROR_PATTERN_PARAMETER_COUNT_RANGE.format(function="pad_right")):
            handler.evaluate("pad_right('hello')")  # Missing width

        with pytest.raises(FormulaSyntaxError, match=ERROR_PATTERN_FILL_CHAR_LENGTH):
            handler.evaluate("pad_right('hello', 10, '')")  # Empty fill character

        # center validation
        with pytest.raises(FormulaSyntaxError, match=ERROR_PATTERN_PARAMETER_COUNT_RANGE.format(function="center")):
            handler.evaluate("center('hello')")  # Missing width

        with pytest.raises(FormulaSyntaxError, match=ERROR_PATTERN_FILL_CHAR_LENGTH):
            handler.evaluate("center('hello', 10, 'xyz')")  # Multi-character fill

    # Integration Tests
    def test_extended_functions_with_context(self, handler):
        """Test extended functions with context variables."""
        context = {"user_input": "Hello123", "text": "apple,banana,cherry", "separator": " | ", "width": "15", "fill": "*"}

        # Validation with context
        assert handler.evaluate("isalnum(user_input)", context) == "true"

        # Split/join with context
        result = handler.evaluate("join(split(text, ','), separator)", context)
        assert result == "apple | banana | cherry"

        # Padding with context
        result = handler.evaluate("center('test', width, fill)", context)
        assert result == "******test*****"

    def test_nested_extended_functions(self, handler):
        """Test nested extended function calls."""
        # Validation in conditions - replace_all replaces exact substring, not individual chars
        assert handler.evaluate("isdigit(replace_all('abc123abc', 'abc', ''))") == "true"

        # Complex transformations
        result = handler.evaluate("center(join(split('hello world', ' '), '_'), 15, '*')")
        assert result == "**hello_world**"

        # Chained operations
        result = handler.evaluate("pad_left(replace_all('test-test', '-', '_'), 10, '0')")
        assert result == "0test_test"  # 'test_test' is 9 chars, padded to 10 = 1 zero

    def test_extended_functions_in_concatenation(self, handler):
        """Test extended functions used in string concatenation."""
        context = {"data": "apple,banana,cherry"}

        result = handler.evaluate("'Items: ' + join(split(data, ','), ' and ')", context)
        assert result == "Items: apple and banana and cherry"

        result = handler.evaluate("'Digits: ' + isdigit('123') + ', Alpha: ' + isalpha('abc')")
        assert result == "Digits: true, Alpha: true"

    def test_extended_functions_error_handling(self, handler):
        """Test error handling for extended functions."""
        # Invalid width parameter (non-numeric) - should return "unknown" due to exception handling
        result = handler.evaluate("pad_left('hello', 'invalid')")
        assert result == "unknown"

        # Functions should handle empty inputs gracefully
        assert handler.evaluate("isalpha('')") == "false"
        assert handler.evaluate("split('', ',')") == ""
        assert handler.evaluate("join('', ',')") == ""

    def test_extended_functions_empty_and_none_context(self, handler):
        """Test extended functions with empty and None context."""
        # Should work without context
        assert handler.evaluate("isalpha('hello')") == "true"
        assert handler.evaluate("replace_all('test', 't', 'x')") == "xesx"
        assert handler.evaluate("center('hi', 5)") == "  hi "

        # Should work with empty context
        assert handler.evaluate("isdigit('123')", {}) == "true"
        assert handler.evaluate("split('a,b,c', ',')", {}) == "a,b,c"
