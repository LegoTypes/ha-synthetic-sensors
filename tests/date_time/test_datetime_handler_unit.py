"""Unit tests for DateTimeHandler."""

import pytest
from unittest.mock import Mock, patch
import re

from ha_synthetic_sensors.datetime_functions.datetime_handler import DateTimeHandler
from ha_synthetic_sensors.datetime_functions.function_registry import DateTimeFunctionRegistry


class TestDateTimeHandler:
    """Test DateTimeHandler functionality."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock registry for testing."""
        registry = Mock(spec=DateTimeFunctionRegistry)
        registry.can_handle_function.return_value = False
        registry.get_supported_functions.return_value = {"now", "today", "tomorrow", "yesterday"}
        registry.get_handlers_info.return_value = [
            {"handler": "TimezoneFunctions", "functions": ["now", "utc_now", "local_now"]},
            {"handler": "DateFunctions", "functions": ["today", "tomorrow", "yesterday"]},
        ]
        return registry

    @pytest.fixture
    def handler_with_mock_registry(self, mock_registry):
        """Create a DateTimeHandler with a mocked registry."""
        with patch(
            "ha_synthetic_sensors.datetime_functions.datetime_handler.get_datetime_function_registry"
        ) as mock_get_registry:
            mock_get_registry.return_value = mock_registry
            handler = DateTimeHandler()
            return handler

    def test_init(self):
        """Test DateTimeHandler initialization."""
        handler = DateTimeHandler()

        assert handler._registry is not None
        assert handler._function_pattern is not None
        assert isinstance(handler._function_pattern, re.Pattern)

    def test_function_pattern_regex(self):
        """Test that the function pattern regex works correctly."""
        handler = DateTimeHandler()

        # Test valid function calls
        assert handler._function_pattern.findall("now()") == ["now"]
        assert handler._function_pattern.findall("today()") == ["today"]
        assert handler._function_pattern.findall("tomorrow()") == ["tomorrow"]
        assert handler._function_pattern.findall("func_with_underscore()") == ["func_with_underscore"]

        # Test function calls with spaces
        assert handler._function_pattern.findall("now( )") == ["now"]
        assert handler._function_pattern.findall("now(  )") == ["now"]

        # Test multiple function calls
        assert handler._function_pattern.findall("now() + today()") == ["now", "today"]

        # Test function calls within larger expressions
        assert handler._function_pattern.findall("if now() > yesterday() then 1 else 0") == ["now", "yesterday"]

        # Test that partial matches don't work
        assert handler._function_pattern.findall("function") == []
        assert handler._function_pattern.findall("func(") == []
        assert handler._function_pattern.findall("func)") == []

    def test_can_handle_with_datetime_functions(self, handler_with_mock_registry, mock_registry):
        """Test can_handle returns True when formula contains datetime functions."""
        handler = handler_with_mock_registry

        # Mock registry to recognize 'now' as a datetime function
        mock_registry.can_handle_function.side_effect = lambda func: func == "now"

        # Should return True when formula contains datetime functions
        assert handler.can_handle("now()") is True
        assert handler.can_handle("value = now()") is True
        assert handler.can_handle("now() + 100") is True

    def test_can_handle_without_datetime_functions(self, handler_with_mock_registry, mock_registry):
        """Test can_handle returns False when formula contains no datetime functions."""
        handler = handler_with_mock_registry

        # Mock registry to not recognize any functions
        mock_registry.can_handle_function.return_value = False

        # Should return False when formula contains no datetime functions
        assert handler.can_handle("1 + 2") is False
        assert handler.can_handle("other_func()") is False
        assert handler.can_handle("value") is False

    def test_can_handle_mixed_functions(self, handler_with_mock_registry, mock_registry):
        """Test can_handle returns True when formula contains mix of datetime and other functions."""
        handler = handler_with_mock_registry

        # Mock registry to recognize only 'now' as a datetime function
        mock_registry.can_handle_function.side_effect = lambda func: func == "now"

        # Should return True if ANY function is a datetime function
        assert handler.can_handle("now() + other_func()") is True
        assert handler.can_handle("other_func() + now()") is True

    def test_can_handle_no_functions(self, handler_with_mock_registry, mock_registry):
        """Test can_handle returns False when formula contains no function calls."""
        handler = handler_with_mock_registry

        # Should return False when no functions are present
        assert handler.can_handle("1 + 2") is False
        assert handler.can_handle("variable_name") is False
        assert handler.can_handle("") is False

    def test_evaluate_with_datetime_functions(self, handler_with_mock_registry, mock_registry):
        """Test evaluate replaces datetime functions with their results."""
        handler = handler_with_mock_registry

        # Mock registry behavior
        mock_registry.can_handle_function.side_effect = lambda func: func in ["now", "today"]
        mock_registry.evaluate_function.side_effect = lambda func: {"now": "2025-07-31T12:00:00Z", "today": "2025-07-31"}[func]

        # Test single datetime function
        result = handler.evaluate("now()")
        assert result == '"2025-07-31T12:00:00Z"'

        # Test datetime function in expression
        result = handler.evaluate("value = now()")
        assert result == 'value = "2025-07-31T12:00:00Z"'

        # Test multiple datetime functions
        result = handler.evaluate("now() > today()")
        assert result == '"2025-07-31T12:00:00Z" > "2025-07-31"'

    def test_evaluate_with_mixed_functions(self, handler_with_mock_registry, mock_registry):
        """Test evaluate only replaces datetime functions, leaves others unchanged."""
        handler = handler_with_mock_registry

        # Mock registry to recognize only 'now' as datetime function
        mock_registry.can_handle_function.side_effect = lambda func: func == "now"
        mock_registry.evaluate_function.side_effect = lambda func: "2025-07-31T12:00:00Z" if func == "now" else None

        # Should replace only datetime functions
        result = handler.evaluate("now() + other_func()")
        assert result == '"2025-07-31T12:00:00Z" + other_func()'

    def test_evaluate_no_datetime_functions(self, handler_with_mock_registry, mock_registry):
        """Test evaluate returns formula unchanged when no datetime functions present."""
        handler = handler_with_mock_registry

        # Mock registry to not recognize any functions as datetime functions
        mock_registry.can_handle_function.return_value = False

        # Should return formula unchanged
        original_formula = "other_func() + 1"
        result = handler.evaluate(original_formula)
        assert result == original_formula

    def test_evaluate_with_context_parameter(self, handler_with_mock_registry, mock_registry):
        """Test evaluate handles context parameter (though it's not used)."""
        handler = handler_with_mock_registry

        mock_registry.can_handle_function.side_effect = lambda func: func == "now"
        mock_registry.evaluate_function.return_value = "2025-07-31T12:00:00Z"

        # Context should be accepted but not affect the result
        context = {"some_var": "some_value"}
        result = handler.evaluate("now()", context)
        assert result == '"2025-07-31T12:00:00Z"'

    def test_evaluate_function_with_spaces(self, handler_with_mock_registry, mock_registry):
        """Test evaluate handles function calls with spaces in parentheses."""
        handler = handler_with_mock_registry

        mock_registry.can_handle_function.side_effect = lambda func: func == "now"
        mock_registry.evaluate_function.return_value = "2025-07-31T12:00:00Z"

        # Should handle functions with spaces
        result = handler.evaluate("now( )")
        assert result == '"2025-07-31T12:00:00Z"'

        result = handler.evaluate("now(  )")
        assert result == '"2025-07-31T12:00:00Z"'

    def test_get_supported_functions(self, handler_with_mock_registry, mock_registry):
        """Test get_supported_functions returns registry's supported functions."""
        handler = handler_with_mock_registry

        expected_functions = {"now", "today", "tomorrow", "yesterday"}
        mock_registry.get_supported_functions.return_value = expected_functions

        result = handler.get_supported_functions()
        assert result == expected_functions
        mock_registry.get_supported_functions.assert_called_once()

    def test_get_handler_info(self, handler_with_mock_registry, mock_registry):
        """Test get_handler_info returns comprehensive handler information."""
        handler = handler_with_mock_registry

        expected_functions = {"now", "today", "tomorrow", "yesterday"}
        expected_handlers_info = [
            {"handler": "TimezoneFunctions", "functions": ["now", "utc_now", "local_now"]},
            {"handler": "DateFunctions", "functions": ["today", "tomorrow", "yesterday"]},
        ]

        mock_registry.get_supported_functions.return_value = expected_functions
        mock_registry.get_handlers_info.return_value = expected_handlers_info

        result = handler.get_handler_info()

        assert isinstance(result, dict)
        assert result["handler_name"] == "DateTimeHandler"
        assert result["supported_functions"] == sorted(expected_functions)
        assert result["function_handlers"] == expected_handlers_info
        assert result["processing_type"] == "function_replacement"
        assert result["output_format"] == "ISO datetime strings as quoted literals"

    def test_get_handler_name(self):
        """Test get_handler_name returns correct class name."""
        handler = DateTimeHandler()
        assert handler.get_handler_name() == "DateTimeHandler"

    def test_evaluate_error_propagation(self, handler_with_mock_registry, mock_registry):
        """Test that evaluation errors from registry are propagated."""
        handler = handler_with_mock_registry

        # Mock registry to handle function but raise error during evaluation
        mock_registry.can_handle_function.return_value = True
        mock_registry.evaluate_function.side_effect = ValueError("Test error")

        # Should propagate the error
        with pytest.raises(ValueError, match="Test error"):
            handler.evaluate("now()")

    def test_real_datetime_functions_integration(self):
        """Test with real datetime function registry (integration-style test)."""
        handler = DateTimeHandler()

        # Should be able to handle real datetime functions
        assert handler.can_handle("now()") is True
        assert handler.can_handle("today()") is True
        assert handler.can_handle("tomorrow()") is True
        assert handler.can_handle("yesterday()") is True
        assert handler.can_handle("utc_now()") is True

        # Should not handle non-existent functions
        assert handler.can_handle("non_existent_func()") is False

        # Should be able to evaluate real functions (results will be actual datetime strings)
        result = handler.evaluate("today()")
        assert result.startswith('"')
        assert result.endswith('"')
        assert len(result) > 12  # Should contain an actual date string

        # Test get_supported_functions returns real functions
        supported = handler.get_supported_functions()
        assert "now" in supported
        assert "today" in supported
        assert "tomorrow" in supported
        assert "yesterday" in supported
        assert "utc_now" in supported

    def test_edge_case_empty_formula(self, handler_with_mock_registry, mock_registry):
        """Test edge case with empty formula."""
        handler = handler_with_mock_registry

        # Should handle empty string gracefully
        assert handler.can_handle("") is False
        assert handler.evaluate("") == ""

    def test_edge_case_whitespace_formula(self, handler_with_mock_registry, mock_registry):
        """Test edge case with whitespace-only formula."""
        handler = handler_with_mock_registry

        # Should handle whitespace gracefully
        assert handler.can_handle("   ") is False
        assert handler.evaluate("   ") == "   "

    def test_complex_formula_with_multiple_datetime_functions(self, handler_with_mock_registry, mock_registry):
        """Test complex formula with multiple datetime function calls."""
        handler = handler_with_mock_registry

        # Mock registry behavior for multiple functions
        mock_registry.can_handle_function.side_effect = lambda func: func in ["now", "today", "yesterday"]
        mock_registry.evaluate_function.side_effect = lambda func: {
            "now": "2025-07-31T12:00:00Z",
            "today": "2025-07-31",
            "yesterday": "2025-07-30",
        }[func]

        # Complex formula with multiple datetime functions
        formula = "if now() > yesterday() and today() != yesterday() then 1 else 0"
        result = handler.evaluate(formula)
        expected = 'if "2025-07-31T12:00:00Z" > "2025-07-30" and "2025-07-31" != "2025-07-30" then 1 else 0'
        assert result == expected
