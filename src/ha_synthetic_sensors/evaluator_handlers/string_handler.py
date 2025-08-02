"""String formula handler for processing string-based formulas."""

import ast
from collections.abc import Callable
from dataclasses import dataclass
import logging
import re

from ..constants_formula import (
    BASIC_STRING_FUNCTIONS,
    COMMA_SEPARATOR,
    DEFAULT_PADDING_CHAR,
    ERROR_MSG_FILL_CHAR_LENGTH,
    ERROR_MSG_PARAMETER_COUNT_EXACT,
    ERROR_MSG_PARAMETER_COUNT_RANGE,
    MULTI_PARAM_STRING_FUNCTIONS,
    STRING_FALSE,
    STRING_TRUE,
)
from ..formula_router import EvaluatorType, FormulaRouter, FormulaSyntaxError
from ..shared_constants import STRING_FUNCTIONS
from ..type_definitions import ContextValue
from .base_handler import FormulaHandler
from .numeric_handler import NumericHandler

_LOGGER = logging.getLogger(__name__)


@dataclass
class ArithmeticTokenizerConfig:
    """Configuration for arithmetic tokenization processing."""

    max_iterations: int = 100  # Defensive limit against edge cases
    enable_iteration_logging: bool = False  # For debugging


class StringHandler(FormulaHandler):
    """Handler for string-based formulas in the compiler-like evaluation system."""

    def __init__(self, config: ArithmeticTokenizerConfig | None = None) -> None:
        """Initialize the string handler with configuration."""
        self._config = config or ArithmeticTokenizerConfig()
        self._formula_router = FormulaRouter()

    def can_handle(self, formula: str) -> bool:
        """
        Determine if a formula should be processed as a string formula.

        Uses the FormulaRouter to determine if this formula should be handled
        by the string evaluator based on:
        1. Explicit user functions: str()
        2. String literals (non-collection patterns)
        3. Excludes collection functions and numeric patterns

        Raises:
            FormulaSyntaxError: If formula contains syntax errors
        """
        # Use FormulaRouter to determine if this should be handled as string
        # FormulaSyntaxError will propagate naturally if validation fails
        routing_result = self._formula_router.route_formula(formula)
        return routing_result.evaluator_type == EvaluatorType.STRING

    def evaluate(self, formula: str, context: dict[str, ContextValue] | None = None) -> str:
        """
        Enhanced STRING FORMULA HANDLER: Process string operations with arithmetic support.

        This method handles:
        - Simple string literals: "'hello world'"
        - String concatenation: "'Device: ' + state + ' status'"
        - User functions: "str(numeric_value * 1.1)"
        - Iterative left-to-right processing: "'A' + 'B' + variable + 'C'"

        The evaluation process:
        1. Check for user function wrapper (str())
        2. Process iterative arithmetic operations (+ concatenation)
        3. Handle variable substitution with string conversion
        4. Return final string result
        """
        try:
            _LOGGER.debug("Evaluating string formula: %s", formula)

            # Check if this is a user function that needs unwrapping
            routing_result = self._formula_router.route_formula(formula)

            if routing_result.user_function == "str":
                # Extract inner formula from str() wrapper
                inner_formula = self._formula_router.extract_inner_formula(formula, "str")
                _LOGGER.debug("Extracted inner formula from str(): %s", inner_formula)

                # Evaluate inner formula and convert result to string
                inner_result = self._evaluate_inner_expression(inner_formula, context)
                return str(inner_result)
            if routing_result.user_function in STRING_FUNCTIONS:
                # Extract inner formula from string function wrapper
                inner_formula = self._formula_router.extract_inner_formula(formula, routing_result.user_function)
                _LOGGER.debug("Extracted inner formula from %s(): %s", routing_result.user_function, inner_formula)

                # Handle functions with different parameter patterns
                if routing_result.user_function in BASIC_STRING_FUNCTIONS:
                    # Single parameter functions
                    inner_result = self._evaluate_inner_expression(inner_formula, context)
                    string_value = str(inner_result)

                    # Apply the string function
                    string_functions: dict[str, Callable[[str], str]] = {
                        "trim": lambda s: s.strip(),
                        "lower": lambda s: s.lower(),
                        "upper": lambda s: s.upper(),
                        "title": lambda s: s.title(),
                        "length": lambda s: str(len(s)),
                        "normalize": lambda s: re.sub(r"\s+", " ", s.strip()),  # Normalize whitespace
                        "clean": lambda s: re.sub(r"[^\w\s]", "", s).strip(),  # Remove non-alphanumeric except spaces
                        "sanitize": lambda s: re.sub(r"[^\w]", "_", s.strip()),  # Replace non-alphanumeric with underscores
                        # String validation functions - return boolean as string
                        "isalpha": lambda s: STRING_TRUE if s.isalpha() else STRING_FALSE,
                        "isdigit": lambda s: STRING_TRUE if s.isdigit() else STRING_FALSE,
                        "isnumeric": lambda s: STRING_TRUE if s.isnumeric() else STRING_FALSE,
                        "isalnum": lambda s: STRING_TRUE if s.isalnum() else STRING_FALSE,
                    }
                    if routing_result.user_function in string_functions:
                        func = string_functions[routing_result.user_function]
                        return func(string_value)

                elif routing_result.user_function in MULTI_PARAM_STRING_FUNCTIONS:
                    # Multi-parameter functions - need to parse parameters
                    return self._evaluate_multi_parameter_function(routing_result.user_function, inner_formula, context)

            # Direct string evaluation (string literals and concatenation)
            return self._evaluate_string_expression(formula, context)

        except FormulaSyntaxError:
            # Re-raise syntax errors - they should not be silenced
            raise
        except Exception as e:
            _LOGGER.warning("String formula evaluation failed for '%s': %s", formula, e)
            return "unknown"

    def _evaluate_string_expression(self, formula: str, context: dict[str, ContextValue] | None = None) -> str:
        """
        Evaluate string expressions with iterative arithmetic processing.

        Handles:
        - Simple literals: "'hello'"
        - String concatenation: "'Device: ' + state + ' status'"
        - Variable substitution with context values
        """
        # For simple string literals without variables, use ast.literal_eval
        if self._is_simple_literal(formula) and not self._has_arithmetic_operations(formula):
            try:
                literal_result = ast.literal_eval(formula.strip())
                return str(literal_result)
            except (ValueError, SyntaxError):
                pass

        # For expressions with variables or arithmetic, process iteratively
        result = self._process_iterative_arithmetic(formula, context)
        return str(result)

    def _evaluate_inner_expression(self, formula: str, context: dict[str, ContextValue] | None = None) -> str | float | int:
        """
        Evaluate inner expressions from str() functions.

        This can be either numeric or string expressions that need to be evaluated
        before converting to string.
        """
        formula = formula.strip()

        # First check if this is itself a function call that should be recursively evaluated
        if self._is_function_call(formula) and any(formula.startswith(f"{func}(") for func in STRING_FUNCTIONS):
            # Recursively evaluate this function call using the main evaluate method
            return self.evaluate(formula, context)
        # Handle simple string literals by evaluating them first
        if self._is_simple_literal(formula):
            try:
                literal_result = ast.literal_eval(formula)  # This will unwrap 'hello' to hello
                # ast.literal_eval can return various types, ensure we handle them properly
                if isinstance(literal_result, str | int | float):
                    return literal_result
                return str(literal_result)
            except (ValueError, SyntaxError):
                pass

        # First, try to substitute variables if context exists
        resolved_formula = self._substitute_variables(formula, context) if context else formula

        # Try to evaluate as numeric (for str(numeric_expr))
        try:
            if self._is_numeric_expression(resolved_formula):
                # For arithmetic expressions, we need to use a more capable evaluator
                # Since this is within str(), we'll use the numeric handler for safety

                numeric_handler = NumericHandler()
                numeric_result = numeric_handler.evaluate(resolved_formula, context)
                return numeric_result
        except (ValueError, SyntaxError, Exception):
            pass

        # If contains variables or is complex, process as string arithmetic
        if context or "+" in formula:
            result = self._process_iterative_arithmetic(formula, context)
            return str(result)

        # Fallback: return as string
        return str(formula)

    def _process_iterative_arithmetic(self, formula: str, context: dict[str, ContextValue] | None = None) -> str:
        """
        Process arithmetic operations iteratively, left-to-right.

        Example: "'Result: ' + state + ' - ' + power + 'W'"
        Iteration 1: "'Result: ' + state" → "Result: on"
        Iteration 2: "Result: on" + " - " → "Result: on - "
        Iteration 3: "Result: on - " + power → "Result: on - 1000"
        Iteration 4: "Result: on - 1000" + "W" → "Result: on - 1000W"
        """
        current_formula = formula.strip()
        iteration_count = 0

        if self._config.enable_iteration_logging:
            _LOGGER.debug("Starting iterative processing: %s", current_formula)

        while self._has_arithmetic_operations(current_formula) and iteration_count < self._config.max_iterations:
            old_formula = current_formula
            current_formula = self._process_next_operation(current_formula, context)

            iteration_count += 1

            if self._config.enable_iteration_logging:
                _LOGGER.debug("Iteration %d: %s", iteration_count, current_formula)

            # Safety check: if formula didn't change, we might be stuck
            if current_formula == old_formula:
                _LOGGER.warning("Formula processing stuck in iteration %d: %s", iteration_count, current_formula)
                break

        if iteration_count >= self._config.max_iterations:
            _LOGGER.error(
                "String processing exceeded max iterations (%d) for formula: %s", self._config.max_iterations, formula
            )
            return "error_max_iterations"

        # Final result should be a string value or variable that needs resolution
        return self._resolve_final_value(current_formula, context)

    def _is_simple_literal(self, formula: str) -> bool:
        """Check if formula is a simple quoted string literal without operations."""
        formula = formula.strip()
        # Check if it's a simple quoted string without arithmetic operations
        if (formula.startswith("'") and formula.endswith("'")) or (formula.startswith('"') and formula.endswith('"')):
            # If it contains + operators outside of quotes, it's not a simple literal
            return "+" not in formula
        return False

    def _is_numeric_expression(self, formula: str) -> bool:
        """Check if formula appears to be a numeric expression."""
        # Simple heuristic: contains only numbers, operators, dots, parentheses, spaces
        # Must not contain quotes (which would indicate strings)
        formula = formula.strip()
        return bool(re.match(r"^[\d\+\-\*\/\.\(\)\s]+$", formula)) and '"' not in formula and "'" not in formula

    def _has_arithmetic_operations(self, formula: str) -> bool:
        """Check if formula has arithmetic operations that need processing."""
        # Look for + operators (our main focus for string concatenation)
        return "+" in formula and not self._is_simple_literal(formula)

    def _process_next_operation(self, formula: str, context: dict[str, ContextValue] | None = None) -> str:
        """
        Process the next arithmetic operation in the formula.

        Finds the leftmost + operation and evaluates it.
        """
        # Simple implementation: find first + and evaluate left + right
        plus_index = formula.find("+")
        if plus_index == -1:
            return formula

        # Split into left and right parts
        left_part = formula[:plus_index].strip()
        right_part = formula[plus_index + 1 :].strip()

        # Find the end of the right operand (next + or end of string)
        next_plus = right_part.find("+")
        if next_plus != -1:
            current_right = right_part[:next_plus].strip()
            remaining = right_part[next_plus:]
        else:
            current_right = right_part
            remaining = ""

        # Evaluate left and right operands
        left_value = self._resolve_operand(left_part, context)
        right_value = self._resolve_operand(current_right, context)

        # Perform string concatenation
        result = str(left_value) + str(right_value)

        # Construct new formula with result
        if remaining:
            return f"'{result}'{remaining}"

        return f"'{result}'"

    def _resolve_operand(self, operand: str, context: dict[str, ContextValue] | None = None) -> str:
        """
        Resolve an operand to its string value.

        Handles:
        - String literals: "'hello'" → "hello"
        - Variables: "state" → context value
        - Function calls: "str(temperature)" → evaluate function
        - Nested expressions: recursively process
        """
        operand = operand.strip()

        # Handle function calls (like str(temperature))
        if self._is_function_call(operand):
            function_result = self._evaluate_function_call(operand, context)
            return str(function_result)

        # Handle string literals
        if self._is_simple_literal(operand):
            literal_result = ast.literal_eval(operand)
            return str(literal_result)

        # Handle variables from context
        if context and operand in context:
            return str(context[operand])

        # Handle numeric literals
        try:
            result = ast.literal_eval(operand)
            return str(result)
        except (ValueError, SyntaxError):
            pass

        # Default: return as-is (might be a variable name)
        return str(operand)

    def _resolve_final_value(self, formula: str, context: dict[str, ContextValue] | None = None) -> str:
        """Resolve the final processed formula to its string value."""
        formula = formula.strip()

        # Handle string literals
        if self._is_simple_literal(formula):
            result = ast.literal_eval(formula)
            return str(result)

        # Handle variables from context
        if context and formula in context:
            return str(context[formula])

        # Default: return as-is
        return str(formula)

    def _substitute_variables(self, formula: str, context: dict[str, ContextValue]) -> str:
        """
        Substitute variables in formula with their context values.

        Simple substitution for basic cases like:
        - "power * efficiency" with context {"power": 1000, "efficiency": 0.95}
        - Returns "1000 * 0.95"
        """
        result = formula
        for var_name, var_value in context.items():
            # Simple word boundary replacement to avoid partial matches
            pattern = r"\b" + re.escape(var_name) + r"\b"
            result = re.sub(pattern, str(var_value), result)
        return result

    def _is_function_call(self, operand: str) -> bool:
        """Check if operand is a function call like str(something)."""
        operand = operand.strip()
        # Check if it matches pattern: function_name(...)
        return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*\(.*\)$", operand))

    def _evaluate_function_call(self, operand: str, context: dict[str, ContextValue] | None = None) -> str | float | int:
        """
        Evaluate a function call within string concatenation.

        Currently supports:
        - str(expression): Convert expression to string
        - trim(expression): Trim whitespace
        - lower(expression): Convert to lowercase
        - upper(expression): Convert to uppercase
        - title(expression): Convert to title case
        """
        operand = operand.strip()

        # Use the main evaluate method for all recognized function calls
        # This ensures consistency and proper nested function handling
        recognized_functions = list(STRING_FUNCTIONS)
        if any(operand.startswith(f"{func}(") for func in recognized_functions) and operand.endswith(")"):
            # Recursively evaluate using main evaluate method
            return self.evaluate(operand, context)

        # For other function calls, return as-is for now
        return operand

    def _evaluate_multi_parameter_function(
        self, function_name: str, parameters: str, context: dict[str, ContextValue] | None = None
    ) -> str:
        """
        Evaluate string functions that take multiple parameters.

        Args:
            function_name: Name of the function to evaluate
            parameters: Parameter string to parse (e.g., "text, 'hello'")
            context: Variable context for evaluation

        Returns:
            String result of the function evaluation
        """
        # Parse parameters - simple comma splitting with quote awareness
        params = self._parse_function_parameters(parameters)

        # Route to specialized handlers based on function category
        if function_name in {"contains", "startswith", "endswith"}:
            return self._evaluate_string_test_function(function_name, params, context)
        if function_name in {"replace", "replace_all"}:
            return self._evaluate_string_replacement_function(function_name, params, context)
        if function_name in {"split", "join"}:
            return self._evaluate_string_split_join_function(function_name, params, context)
        if function_name in {"pad_left", "pad_right", "center"}:
            return self._evaluate_string_padding_function(function_name, params, context)
        return str(parameters)  # Fallback

    def _evaluate_string_test_function(
        self, function_name: str, params: list[str], context: dict[str, ContextValue] | None = None
    ) -> str:
        """Evaluate string test functions (contains, startswith, endswith)."""
        if len(params) != 2:
            raise FormulaSyntaxError(
                ERROR_MSG_PARAMETER_COUNT_EXACT.format(function=function_name, expected=2, actual=len(params)),
                ",".join(params),
            )

        text = str(self._evaluate_inner_expression(params[0], context))
        test_value = str(self._evaluate_inner_expression(params[1], context))

        match function_name:
            case "contains":
                return STRING_TRUE if test_value in text else STRING_FALSE
            case "startswith":
                return STRING_TRUE if text.startswith(test_value) else STRING_FALSE
            case "endswith":
                return STRING_TRUE if text.endswith(test_value) else STRING_FALSE
            case _:
                return str(test_value)  # Fallback

    def _evaluate_string_replacement_function(
        self, function_name: str, params: list[str], context: dict[str, ContextValue] | None = None
    ) -> str:
        """Evaluate string replacement functions (replace, replace_all)."""
        if len(params) != 3:
            raise FormulaSyntaxError(
                ERROR_MSG_PARAMETER_COUNT_EXACT.format(function=function_name, expected=3, actual=len(params)),
                ",".join(params),
            )

        text = str(self._evaluate_inner_expression(params[0], context))
        old = str(self._evaluate_inner_expression(params[1], context))
        new = str(self._evaluate_inner_expression(params[2], context))

        match function_name:
            case "replace":
                return text.replace(old, new, 1)  # Replace only first occurrence
            case "replace_all":
                return text.replace(old, new)  # Replace all occurrences
            case _:
                return text  # Fallback

    def _evaluate_string_split_join_function(
        self, function_name: str, params: list[str], context: dict[str, ContextValue] | None = None
    ) -> str:
        """Evaluate string split/join functions."""
        match function_name:
            case "split":
                if len(params) not in [1, 2]:
                    raise FormulaSyntaxError(
                        ERROR_MSG_PARAMETER_COUNT_RANGE.format(
                            function="split", min_params=1, max_params=2, actual=len(params)
                        ),
                        ",".join(params),
                    )

                text = str(self._evaluate_inner_expression(params[0], context))
                if len(params) == 2:
                    delimiter = str(self._evaluate_inner_expression(params[1], context))
                    parts = text.split(delimiter)
                else:
                    parts = text.split()  # Split on whitespace by default
                return COMMA_SEPARATOR.join(parts)

            case "join":
                if len(params) != 2:
                    raise FormulaSyntaxError(
                        ERROR_MSG_PARAMETER_COUNT_EXACT.format(function="join", expected=2, actual=len(params)),
                        ",".join(params),
                    )

                items_str = str(self._evaluate_inner_expression(params[0], context))
                delimiter = str(self._evaluate_inner_expression(params[1], context))
                items = [item.strip() for item in items_str.split(COMMA_SEPARATOR)]
                return delimiter.join(items)

            case _:
                return ",".join(params)  # Fallback

    def _evaluate_string_padding_function(
        self, function_name: str, params: list[str], context: dict[str, ContextValue] | None = None
    ) -> str:
        """Evaluate string padding functions (pad_left, pad_right, center)."""
        if len(params) not in [2, 3]:
            raise FormulaSyntaxError(
                ERROR_MSG_PARAMETER_COUNT_RANGE.format(function=function_name, min_params=2, max_params=3, actual=len(params)),
                ",".join(params),
            )

        text = str(self._evaluate_inner_expression(params[0], context))
        width = int(self._evaluate_inner_expression(params[1], context))
        fill_char = DEFAULT_PADDING_CHAR

        if len(params) == 3:
            fill_char = str(self._evaluate_inner_expression(params[2], context))
            if len(fill_char) != 1:
                raise FormulaSyntaxError(
                    ERROR_MSG_FILL_CHAR_LENGTH.format(function=function_name),
                    ",".join(params),
                )

        match function_name:
            case "pad_left":
                return text.rjust(width, fill_char)
            case "pad_right":
                return text.ljust(width, fill_char)
            case "center":
                return text.center(width, fill_char)
            case _:
                return text  # Fallback

    def _parse_function_parameters(self, parameters: str) -> list[str]:
        """
        Parse function parameters with simple comma splitting and quote awareness.

        Examples:
        - "text, 'hello'" → ["text", "'hello'"]
        - "'Device: ' + name, 'sensor'" → ["'Device: ' + name", "'sensor'"]

        Args:
            parameters: Parameter string to parse

        Returns:
            List of parameter strings
        """
        if not parameters.strip():
            return []

        params = []
        current_param = ""
        in_quote = False
        quote_char = None
        paren_depth = 0

        for char in parameters:
            if char in ('"', "'") and not in_quote:
                in_quote = True
                quote_char = char
                current_param += char
            elif char == quote_char and in_quote:
                in_quote = False
                quote_char = None
                current_param += char
            elif char == "(" and not in_quote:
                paren_depth += 1
                current_param += char
            elif char == ")" and not in_quote:
                paren_depth -= 1
                current_param += char
            elif char == "," and not in_quote and paren_depth == 0:
                # Found parameter separator
                params.append(current_param.strip())
                current_param = ""
            else:
                current_param += char

        # Add the last parameter
        if current_param.strip():
            params.append(current_param.strip())

        return params
