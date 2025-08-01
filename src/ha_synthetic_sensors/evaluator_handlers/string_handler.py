"""String formula handler for processing string-based formulas."""

import ast
from collections.abc import Callable
from dataclasses import dataclass
import logging
import re

from ..formula_router import EvaluatorType, FormulaRouter, FormulaSyntaxError
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
            if routing_result.user_function in ["trim", "lower", "upper", "title"]:
                # Extract inner formula from string function wrapper
                inner_formula = self._formula_router.extract_inner_formula(formula, routing_result.user_function)
                _LOGGER.debug("Extracted inner formula from %s(): %s", routing_result.user_function, inner_formula)

                # Evaluate inner formula first
                inner_result = self._evaluate_inner_expression(inner_formula, context)
                string_value = str(inner_result)

                # Apply the string function
                string_functions: dict[str, Callable[[str], str]] = {
                    "trim": lambda s: s.strip(),
                    "lower": lambda s: s.lower(),
                    "upper": lambda s: s.upper(),
                    "title": lambda s: s.title(),
                }
                if routing_result.user_function in string_functions:
                    func = string_functions[routing_result.user_function]
                    return func(string_value)

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
        if self._is_function_call(formula) and any(
            formula.startswith(f"{func}(") for func in ["str", "trim", "lower", "upper", "title"]
        ):
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
        if any(operand.startswith(f"{func}(") for func in ["str", "trim", "lower", "upper", "title"]) and operand.endswith(")"):
            # Recursively evaluate using main evaluate method
            return self.evaluate(operand, context)

        # For other function calls, return as-is for now
        return operand
