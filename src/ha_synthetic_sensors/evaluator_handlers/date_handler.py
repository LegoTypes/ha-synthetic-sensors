"""Date formula handler for processing date-based formulas with arithmetic support."""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import re
from typing import Any, Literal, cast

from ..datetime_functions import get_datetime_function_registry
from ..formula_router import EvaluatorType, FormulaRouter
from ..shared_constants import DATETIME_FUNCTIONS
from ..type_analyzer import DateTimeParser, OperandType, TypeAnalyzer, TypeCategory
from ..type_definitions import ContextValue
from .base_handler import FormulaHandler

_LOGGER = logging.getLogger(__name__)


@dataclass
class DateArithmeticConfig:
    """Configuration for date arithmetic processing."""

    max_iterations: int = 100  # Defensive limit against edge cases
    enable_iteration_logging: bool = False  # For debugging


@dataclass
class DateArithmeticOperation:
    """Strongly-typed representation of a date arithmetic operation."""

    left_operand: str
    operator: Literal["+", "-"]
    right_operand: str


class DateHandler(FormulaHandler):
    """Handler for date-based formulas with arithmetic support in the compiler-like evaluation system."""

    def __init__(
        self,
        config: DateArithmeticConfig | None = None,
        expression_evaluator: Callable[[str, dict[str, ContextValue] | None], Any] | None = None,
    ) -> None:
        """Initialize the date handler with configuration.

        Args:
            config: Date arithmetic configuration
            expression_evaluator: Callback to evaluate complex expressions (delegates back to main evaluator)
        """
        super().__init__(expression_evaluator)
        self._config = config or DateArithmeticConfig()
        self._formula_router = FormulaRouter()
        self._type_analyzer = TypeAnalyzer()

    def can_handle(self, formula: str) -> bool:
        """
        Determine if a formula should be processed as a date formula.

        Uses the FormulaRouter to determine if this formula should be handled
        by the date evaluator based on:
        1. Explicit date() user functions
        2. Duration functions (days(), hours(), etc.)
        3. Date arithmetic operations

        Raises:
            FormulaSyntaxError: If formula contains syntax errors
        """
        # Use FormulaRouter to determine if this should be handled as date
        # FormulaSyntaxError will propagate naturally if validation fails
        routing_result = self._formula_router.route_formula(formula)
        return routing_result.evaluator_type == EvaluatorType.DATE

    def evaluate(self, formula: str, context: dict[str, ContextValue] | None = None) -> str:
        """
        Enhanced DATE FORMULA HANDLER: Process date operations with arithmetic support.

        This method handles:
        - Date conversion: "date(timestamp_string)"
        - Date arithmetic: "date('2025-01-01') + numeric(days)"
        - Date differences: "date(end_time) - date(start_time)"
        - Iterative left-to-right processing: "date('2025-01-01') + 30 - 5"

        The evaluation process:
        1. Check for date() function wrapper
        2. Process iterative arithmetic operations (+ and -)
        3. Handle variable substitution with date conversion
        4. Return final ISO date string result
        """
        try:
            _LOGGER.debug("Evaluating date formula: %s", formula)

            # Check if this is a date function that needs unwrapping
            routing_result = self._formula_router.route_formula(formula)

            if routing_result.user_function == "date":
                # Extract inner formula from date() wrapper
                inner_formula = self._formula_router.extract_inner_formula(formula, "date")
                _LOGGER.debug("Extracted inner formula from date(): %s", inner_formula)

                # Check if the inner formula contains arithmetic operations
                if self._contains_arithmetic_operations(inner_formula):
                    return self._process_date_arithmetic(inner_formula, context)

                # Simple date conversion
                inner_result = self._evaluate_expression(inner_formula, context)
                return self._convert_to_date_string(inner_result)

            # Should not reach here as can_handle() filters appropriately
            raise ValueError(f"DateHandler received non-date formula: {formula}")

        except Exception as e:
            _LOGGER.error("Error evaluating date formula '%s': %s", formula, e)
            raise

    def _contains_arithmetic_operations(self, formula: str) -> bool:
        """Check if a formula contains arithmetic operations (+, -)."""
        # Simple check for arithmetic operators (excluding those in quotes)
        # This is a simplified version - could be enhanced for more complex parsing
        arithmetic_pattern = r"[+\-]"
        # Remove quoted strings to avoid false positives
        formula_no_quotes = re.sub(r"""["'].*?["']""", "", formula)
        return bool(re.search(arithmetic_pattern, formula_no_quotes))

    def _process_date_arithmetic(self, formula: str, context: dict[str, ContextValue] | None = None) -> str:
        """
        Process date arithmetic operations iteratively, left-to-right.

        Handles expressions like:
        - "'2025-01-01' + 30"
        - "start_date + days_offset - 5"
        - "date_var + numeric(calculation)"

        Args:
            formula: Formula containing date arithmetic
            context: Evaluation context

        Returns:
            ISO date string result
        """
        if self._config.enable_iteration_logging:
            _LOGGER.debug("Processing date arithmetic: %s", formula)

        current_formula = self._process_arithmetic_iterations(formula.strip(), context)
        return self._finalize_arithmetic_result(current_formula, context)

    def _process_arithmetic_iterations(self, formula: str, context: dict[str, ContextValue] | None = None) -> str:
        """Process arithmetic operations iteratively until no more operations remain."""
        _LOGGER.debug("Processing arithmetic iterations - input: %s", formula)
        current_formula = formula
        iteration_count = 0

        while self._contains_arithmetic_operations(current_formula) and iteration_count < self._config.max_iterations:
            iteration_count += 1
            operation = self._parse_arithmetic_operation(current_formula)
            if not operation:
                break
            result = self._execute_arithmetic_operation(operation, context)
            current_formula = f"'{result}'"

        if iteration_count >= self._config.max_iterations:
            raise ValueError(f"Date arithmetic exceeded maximum iterations ({self._config.max_iterations})")

        _LOGGER.debug("Completed arithmetic iterations - result: %s", current_formula)
        return current_formula

    def _parse_arithmetic_operation(self, formula: str) -> DateArithmeticOperation | None:
        """Parse a formula to extract the first arithmetic operation."""
        # Find the first arithmetic operation (+ or -) outside of quotes
        match = re.search(r"^((?:'[^']*'|[^+\-])+)\s*([+\-])\s*(.+)$", formula)
        if not match:
            return None

        operator = match.group(2).strip()
        if operator not in ("+", "-"):
            raise ValueError(f"Invalid arithmetic operator: {operator}")
        return DateArithmeticOperation(
            left_operand=match.group(1).strip(),
            operator=operator,  # type: ignore  # We've validated it's "+" or "-"
            right_operand=match.group(3).strip(),
        )

    def _execute_arithmetic_operation(
        self, operation: DateArithmeticOperation, context: dict[str, ContextValue] | None = None
    ) -> str:
        """Execute a single date arithmetic operation and return the result."""
        # Evaluate left operand as a date using the type system
        left_operand_value: ContextValue = operation.left_operand
        if context and operation.left_operand in context:
            left_operand_value = context[operation.left_operand]
        elif operation.left_operand.startswith("'") and operation.left_operand.endswith("'"):
            # Handle quoted literals by removing quotes
            left_operand_value = operation.left_operand[1:-1]

        # Cast to OperandType for type analyzer
        left_operand_typed = cast(OperandType, left_operand_value)
        success, left_date_value = DateTimeParser.try_reduce_to_date_string(left_operand_typed)
        if not success:
            raise ValueError(f"Cannot convert left operand to date: {left_operand_value}")

        # Dispatch to appropriate operation handler
        if operation.operator == "+":
            return self._handle_addition_operation(left_date_value, operation.right_operand, context)
        if operation.operator == "-":
            return self._handle_subtraction_operation(left_date_value, operation.right_operand, context)
        # This should never happen due to our typing, but defensive programming
        raise ValueError(f"Unsupported date arithmetic operator: {operation.operator}")

    def _handle_addition_operation(
        self, left_value: str, right_part: str, context: dict[str, ContextValue] | None = None
    ) -> str:
        """Handle date addition operations (date + days)."""
        _LOGGER.debug("Addition operation - left: %s, right: %s", left_value, right_part)

        # For date addition, the right operand should always be numeric (days to add)
        # First try simple numeric conversion
        success, right_numeric_value = self._type_analyzer.try_reduce_to_numeric(right_part)
        if not success:
            # If direct conversion fails, check context variables
            if context and right_part in context:
                context_value = context[right_part]
                # Cast to OperandType for type analyzer
                context_value_typed = cast(OperandType, context_value)
                success, right_numeric_value = self._type_analyzer.try_reduce_to_numeric(context_value_typed)
                if success:
                    pass  # Successfully converted
                else:
                    raise ValueError(f"Cannot convert context variable to numeric for addition: {context_value}")
            else:
                # For complex expressions, delegate to main evaluator
                if self._expression_evaluator is not None:
                    evaluated_result = self._expression_evaluator(right_part, context)
                    # Convert result to numeric for date arithmetic
                    if isinstance(evaluated_result, int | float):
                        right_numeric_value = float(evaluated_result)
                    else:
                        raise ValueError(f"Expression '{right_part}' did not evaluate to numeric value: {evaluated_result}")
                else:
                    raise ValueError(f"Cannot evaluate complex expression '{right_part}' - no evaluator available")

        result = self._add_days_to_date(left_value, right_numeric_value)
        _LOGGER.debug("Addition operation result: %s", result)
        return result

    def _handle_subtraction_operation(
        self, left_value: str, right_part: str, context: dict[str, ContextValue] | None = None
    ) -> str:
        """Handle date subtraction operations (date - days or date - date)."""
        _LOGGER.debug("Subtraction operation - left: %s, right: %s", left_value, right_part)

        # Use the type analyzer to determine if right operand is date or numeric
        # First resolve the operand value
        operand_value: ContextValue = right_part
        if context and right_part in context:
            operand_value = context[right_part]
        elif right_part.startswith("'") and right_part.endswith("'"):
            # Handle quoted literals by removing quotes
            operand_value = right_part[1:-1]

        # Check if it's a date value (only try for strings, not numbers)
        if isinstance(operand_value, str):
            try:
                # Cast to OperandType for type analyzer
                operand_value_typed = cast(OperandType, operand_value)
                success, right_date_value = DateTimeParser.try_reduce_to_date_string(operand_value_typed)
                if success:
                    # Date - date operation
                    result = self._subtract_dates(left_value, right_date_value)
                    _LOGGER.debug("Subtraction operation result: %s", result)
                    return result
            except (ValueError, TypeError) as e:
                _LOGGER.debug("Failed to parse '%s' as date: %s", operand_value, e)

        # Not a date, try as numeric (days to subtract)
        # Cast to OperandType for type analyzer
        operand_value_typed = cast(OperandType, operand_value)
        success, right_numeric_value = self._type_analyzer.try_reduce_to_numeric(operand_value_typed)
        if success:
            result = self._subtract_days_from_date(left_value, right_numeric_value)
            _LOGGER.debug("Subtraction operation result: %s", result)
            return result

        # For complex expressions, delegate to main evaluator
        if self._expression_evaluator is not None:
            evaluated_result = self._expression_evaluator(right_part, context)
            # Convert result to numeric for date arithmetic
            if isinstance(evaluated_result, int | float):
                right_numeric_value = float(evaluated_result)
            else:
                raise ValueError(f"Expression '{right_part}' did not evaluate to numeric value: {evaluated_result}")
        else:
            raise ValueError(f"Cannot evaluate complex expression '{right_part}' - no evaluator available")

        result = self._subtract_days_from_date(left_value, right_numeric_value)
        _LOGGER.debug("Subtraction operation result: %s", result)
        return result

    def _finalize_arithmetic_result(self, result: str, context: dict[str, ContextValue] | None = None) -> str:
        """Process the final result of arithmetic operations."""
        final_result = result.strip()

        # If it's a quoted string, remove quotes
        if final_result.startswith("'") and final_result.endswith("'"):
            inner_content = final_result[1:-1]
            # Check if it's a numeric result (like date difference in days)
            try:
                float(inner_content)
                return inner_content  # Return numeric result as-is
            except ValueError:
                # It's a date string, convert it properly
                return self._convert_to_date_string(inner_content)

        # If it's not quoted, it could be a numeric result or date string
        try:
            float(final_result)
            return final_result  # Return numeric result as-is
        except ValueError:
            # It's a date string, convert it properly
            return self._convert_to_date_string(final_result)

    def _evaluate_expression(self, expression: str, context: dict[str, ContextValue] | None = None) -> ContextValue:
        """Evaluate an expression using proper delegation.

        This method handles simple cases directly and delegates complex expressions
        back to the main evaluator to maintain separation of concerns.
        """
        # Handle context variable lookup first
        if context and expression in context:
            return context[expression]

        # Handle quoted literals directly (no need to evaluate)
        if expression.startswith("'") and expression.endswith("'"):
            return expression[1:-1]

        # For simple literals, evaluate directly
        try:
            result = ast.literal_eval(expression)
            return cast(ContextValue, result)
        except (ValueError, SyntaxError) as e:
            _LOGGER.debug("Failed to evaluate '%s' as literal: %s", expression, e)

        # For complex expressions, delegate to main evaluator if available
        if self._expression_evaluator is not None:
            return self._expression_evaluator(expression, context)  # type: ignore[no-any-return]

        # Final fallback: return as string for backward compatibility
        return expression

    def _is_datetime_function_call(self, expression: str) -> bool:
        """Check if expression is a datetime function call."""
        # Simple check for function call pattern
        if not expression.endswith("()"):
            return False
        func_name = expression[:-2]
        return func_name in DATETIME_FUNCTIONS

    def _evaluate_datetime_function(self, expression: str, context: dict[str, ContextValue] | None = None) -> str:
        """Evaluate a datetime function call using the datetime function registry."""
        if not expression.endswith("()"):
            return expression

        func_name = expression[:-2]
        registry = get_datetime_function_registry()

        if not registry.can_handle_function(func_name):
            return expression

        # Evaluate using the registry - functions return ISO datetime strings
        result = registry.evaluate_function(func_name, None)

        # Convert to date-only format using centralized conversion
        return DateTimeParser.convert_datetime_to_date_string(result)

    def _convert_to_date_string(self, value: ContextValue) -> str:
        """Convert a value to ISO date string using centralized type conversion."""
        # Cast to OperandType for type analyzer
        value_typed = cast(OperandType, value)
        success, result = DateTimeParser.try_reduce_to_date_string(value_typed)
        if success:
            return result
        # Maintain the same error message format for backward compatibility
        if isinstance(value, str):
            raise ValueError(f"Invalid date string: {value}")
        raise ValueError(f"Cannot convert {type(value)} to date: {value}")

    def _add_days_to_date(self, date_str: str, days: float) -> str:
        """Add days to a date string."""
        normalized_date = DateTimeParser.normalize_iso_timezone(date_str)
        dt = datetime.fromisoformat(normalized_date)
        result_dt = dt + timedelta(days=days)
        return result_dt.date().isoformat()

    def _subtract_days_from_date(self, date_str: str, days: float) -> str:
        """Subtract days from a date string."""
        normalized_date = DateTimeParser.normalize_iso_timezone(date_str)
        dt = datetime.fromisoformat(normalized_date)
        result_dt = dt - timedelta(days=days)
        return result_dt.date().isoformat()

    def _subtract_dates(self, date1_str: str, date2_str: str) -> str:
        """Subtract two dates and return the difference in days as a string."""
        normalized_date1 = DateTimeParser.normalize_iso_timezone(date1_str)
        normalized_date2 = DateTimeParser.normalize_iso_timezone(date2_str)
        dt1 = datetime.fromisoformat(normalized_date1)
        dt2 = datetime.fromisoformat(normalized_date2)
        diff = dt1 - dt2
        return str(diff.days)

    def _looks_like_date(self, expression: str) -> bool:
        """Check if expression looks like a date rather than a number."""
        # Use enhanced TypeAnalyzer for consistent date detection
        try:
            expression_type = self._type_analyzer.categorize_expression_type(expression)
            if expression_type == TypeCategory.DATETIME:
                return True
        except (ValueError, TypeError) as e:
            _LOGGER.debug("Failed to categorize expression type for '%s': %s", expression, e)

        # Check for datetime function calls
        return self._is_datetime_function_call(expression)
