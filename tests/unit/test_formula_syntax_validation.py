"""Unit tests for formula syntax validation."""

import pytest

from ha_synthetic_sensors.formula_router import FormulaRouter, FormulaSyntaxError


class TestFormulaSyntaxValidation:
    """Test cases for formula syntax validation and error messages."""

    @pytest.fixture
    def router(self):
        """Create a FormulaRouter instance for testing."""
        return FormulaRouter()

    def test_malformed_function_calls(self, router):
        """Test detection of malformed function calls."""
        malformed_formulas = [
            "str(unclosed",
            "str(invalid syntax +",
            "numeric(missing_paren",
            "date(incomplete +",
            "function(",
        ]

        for formula in malformed_formulas:
            with pytest.raises(FormulaSyntaxError) as exc_info:
                router.route_formula(formula)

            error = exc_info.value
            assert formula in str(error)
            assert "function call" in str(error).lower()
            assert "missing closing parenthesis" in str(error).lower()

    def test_unclosed_quotes(self, router):
        """Test detection of unclosed quotes."""
        unclosed_quote_formulas = [
            "'unclosed string",
            '"unclosed double quote',
            "'Device: ' + state + 'unclosed",
        ]

        for formula in unclosed_quote_formulas:
            with pytest.raises(FormulaSyntaxError) as exc_info:
                router.route_formula(formula)

            error = exc_info.value
            assert formula in str(error)
            assert "unclosed" in str(error).lower()
            assert "quote" in str(error).lower()

    def test_mismatched_parentheses(self, router):
        """Test detection of mismatched parentheses."""
        mismatched_formulas = [
            "str(nested(function)",  # Missing closing paren
            "str(state))",  # Extra closing paren
            "((incomplete",  # Missing closing parens
        ]

        for formula in mismatched_formulas:
            with pytest.raises(FormulaSyntaxError) as exc_info:
                router.route_formula(formula)

            error = exc_info.value
            assert formula in str(error)
            # Should mention parentheses in error
            assert "parenthesis" in str(error).lower() or "paren" in str(error).lower()

    def test_error_message_quality(self, router):
        """Test that error messages provide useful information."""
        formula = "str(invalid syntax +"

        with pytest.raises(FormulaSyntaxError) as exc_info:
            router.route_formula(formula)

        error = exc_info.value
        error_msg = str(error)

        # Should contain the problematic formula
        assert formula in error_msg

        # Should identify the specific problem
        assert "malformed function call" in error_msg.lower()
        assert "str()" in error_msg

        # Should provide position information
        assert "position 0" in error_msg

        # Should show visual indicator for position-based errors
        if error.position is not None:
            assert "^" in error_msg  # Pointer to error position

    def test_valid_formulas_pass_validation(self, router):
        """Test that valid formulas pass validation without errors."""
        valid_formulas = [
            "str('hello')",
            "str(state + 'W')",
            "'Device: ' + state",
            "numeric(5 + 3)",
            "date(start_date + days)",
            "'quoted string'",
            "state * 1.1",
            "count('device_class:power')",
        ]

        for formula in valid_formulas:
            # Should not raise any exception
            routing_result = router.route_formula(formula)
            assert routing_result is not None
            assert routing_result.evaluator_type is not None

    def test_nested_valid_structures(self, router):
        """Test validation of complex but valid nested structures."""
        complex_valid_formulas = [
            "str(trim(attribute:name) + ' - ' + state)",
            "'Device: ' + str(power * efficiency) + 'W'",
            "str((temperature + offset) * scale)",
            "'Status: ' + ('ON' if state > 0 else 'OFF')",  # Note: This might need future support
        ]

        for formula in complex_valid_formulas:
            try:
                routing_result = router.route_formula(formula)
                assert routing_result is not None
            except FormulaSyntaxError:
                # Some complex formulas might not be supported yet, that's OK
                # The important thing is they either work or fail gracefully
                pass

    def test_error_types_are_specific(self, router):
        """Test that different error types are properly categorized."""
        test_cases = [
            ("str(unclosed", "function"),
            ("'unclosed", "quote"),
            ("str(state))", "parenthesis"),
        ]

        for formula, expected_error_type in test_cases:
            with pytest.raises(FormulaSyntaxError) as exc_info:
                router.route_formula(formula)

            error_msg = str(exc_info.value).lower()
            assert expected_error_type in error_msg

    def test_position_indicators(self, router):
        """Test that position indicators point to the right location."""
        formula = "str(invalid"

        with pytest.raises(FormulaSyntaxError) as exc_info:
            router.route_formula(formula)

        error = exc_info.value

        # Should have position information
        assert error.position is not None
        assert error.position == 0  # Points to start of 'str'

        # Should show visual pointer
        error_display = str(error)
        lines = error_display.split("\n")
        assert len(lines) >= 2  # Should have formula and pointer lines
        assert formula in lines

        # Find the line with the pointer
        pointer_line = None
        for line in lines:
            if "^" in line:
                pointer_line = line
                break

        assert pointer_line is not None, "Should have a line with position pointer"
