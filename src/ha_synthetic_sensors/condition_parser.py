"""Condition parsing and evaluation for collection patterns."""

import logging
import re
from typing import Any, Callable, Protocol

from simpleeval import SimpleEval

from .exceptions import DataValidationError

_LOGGER = logging.getLogger(__name__)


class ComparisonHandler(Protocol):
    """Protocol for comparison handlers."""

    def can_handle(self, actual_val: Any, expected_val: Any, op: str) -> bool:
        """Check if this handler can handle the given types and operator."""

    def compare(self, actual_val: Any, expected_val: Any, op: str) -> bool:
        """Perform the comparison and return result."""


class ConditionParser:
    """Parser for state and attribute conditions in collection patterns."""

    @staticmethod
    def parse_state_condition(condition: str) -> tuple[str, bool | float | int | str]:
        """Parse a state condition string into operator and expected value.

        Args:
            condition: State condition string (e.g., "== on", ">= 50", "!off")

        Returns:
            Tuple of (operator, expected_value)

        Raises:
            DataValidationError: If condition format is invalid
        """
        condition = condition.strip()
        if not condition:
            raise DataValidationError("State condition cannot be empty")

        # STEP 1: Detect and reject invalid cases first

        # Check for operators without values (including compound operators like >=, <=, ==, !=)
        if re.match(r"\s*(<=|>=|==|!=|<|>|[=&|%*/+-])\s*$", condition):
            raise DataValidationError(f"Invalid state condition: '{condition}' is just an operator without a value")

        if re.match(r"\s*[=]{1}[^=]", condition):  # Single = (assignment, not comparison)
            raise DataValidationError(f"Invalid state condition: '{condition}'. Use '==' for comparison, not '='")

        if re.search(r"[&|%*/+-]", condition):  # Non-comparison operators anywhere
            raise DataValidationError(
                f"Invalid state condition: '{condition}'. Expected comparison operators: ==, !=, <, <=, >, >="
            )

        if re.search(r">{2,}|<{2,}", condition):  # Multiple > or < (like >>, <<)
            raise DataValidationError(
                f"Invalid state condition: '{condition}'. Expected comparison operators: ==, !=, <, <=, >, >="
            )

        # STEP 2: Parse valid cases

        # Handle simple negation: !value (but not != operator)
        negation_match = re.match(r"\s*!(?!=)\s*(.+)", condition)  # Negative lookahead: ! not followed by =
        if negation_match:
            value_str = negation_match.group(1).strip()
            if not value_str:
                raise DataValidationError(f"Invalid state condition: '{condition}'. Negation '!' requires a value")
            expected_value = ConditionParser._convert_value_string(value_str)
            return "!=", expected_value

        # Handle explicit comparison operators: >=, ==, !=, etc.
        operator_match = re.match(r"\s*(<=|>=|==|!=|<|>)\s+(.+)", condition)  # Note: \s+ requires space
        if operator_match:
            op, value_str = operator_match.groups()
            value_str = value_str.strip()

            # Convert HA state values (on/off/etc) to proper types
            expected_value = ConditionParser._convert_value_string(value_str)

            # Validate operator with SimpleEval
            test_formula = f"1 {op} {expected_value!r}"
            try:
                evaluator = SimpleEval()
                result = evaluator.eval(test_formula)
                if not isinstance(result, bool):
                    raise DataValidationError(
                        f"Invalid comparison operator '{op}'. Expected comparison operators: ==, !=, <, <=, >, >="
                    )
            except Exception as e:
                raise DataValidationError(f"Invalid operator syntax in '{condition}': {e!s}") from e
            return op, expected_value

        # Handle bare values (default to equality): value
        expected_value = ConditionParser._convert_value_string(condition)
        return "==", expected_value

    @staticmethod
    def parse_attribute_condition(condition: str) -> tuple[str, str, bool | float | int | str] | None:
        """Parse an attribute condition string.

        Args:
            condition: Attribute condition string (e.g., "friendly_name == 'Living Room'")

        Returns:
            Tuple of (attribute_name, operator, expected_value) or None if invalid
        """
        condition = condition.strip()
        if not condition:
            return None

        # Pattern: attribute_name operator value
        # Examples: friendly_name == "Living Room", battery_level > 50
        pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*(<=|>=|==|!=|<|>)\s*(.+)$"
        match = re.match(pattern, condition)

        if not match:
            return None

        attribute_name, operator, value_str = match.groups()
        value_str = value_str.strip()

        # Remove quotes from string values
        if (value_str.startswith('"') and value_str.endswith('"')) or (value_str.startswith("'") and value_str.endswith("'")):
            value_str = value_str[1:-1]

        # Convert value to appropriate type
        expected_value = ConditionParser._convert_value_string(value_str)

        return attribute_name, operator, expected_value

    @staticmethod
    def _convert_value_string(value_str: str) -> bool | float | int | str:
        """Convert a string value to the appropriate type.

        Args:
            value_str: String value to convert

        Returns:
            Converted value with appropriate type
        """
        value_str = value_str.strip()

        # Handle boolean values
        if value_str.lower() in ("true", "on", "yes", "1"):
            return True
        if value_str.lower() in ("false", "off", "no", "0"):
            return False

        # Handle numeric values
        try:
            if "." in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            pass

        # Return as string
        return value_str

    @staticmethod
    def compare_values(actual: bool | float | str, op: str, expected: bool | float | int | str) -> bool:
        """Compare two values using the specified operator.

        Args:
            actual: Actual value
            op: Comparison operator
            expected: Expected value

        Returns:
            True if comparison is true
        """
        # Normalize values for comparison
        actual_val, expected_val = ConditionParser._normalize_comparison_values(actual, expected)

        # Dispatch to appropriate comparison function
        return ConditionParser._dispatch_comparison(actual_val, expected_val, op)

    @staticmethod
    def _normalize_comparison_values(actual: Any, expected: Any) -> tuple[float | str | bool, float | str | bool]:
        """Normalize values for comparison.

        Args:
            actual: Actual value
            expected: Expected value

        Returns:
            Tuple of normalized values
        """
        # If both are numeric, convert to float for comparison
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            return float(actual), float(expected)

        # If both are strings, keep as strings
        if isinstance(actual, str) and isinstance(expected, str):
            return actual, expected

        # If both are booleans, keep as booleans
        if isinstance(actual, bool) and isinstance(expected, bool):
            return actual, expected

        # Mixed types - convert to strings for comparison
        return str(actual), str(expected)

    @staticmethod
    def _dispatch_comparison(actual_val: Any, expected_val: Any, op: str) -> bool:
        """Dispatch comparison to appropriate function based on operator.

        Args:
            actual_val: Actual value
            expected_val: Expected value
            op: Comparison operator

        Returns:
            True if comparison is true
        """
        # Handle equality operators (work with any type)
        if op in ("==", "!="):
            return bool(actual_val == expected_val) if op == "==" else bool(actual_val != expected_val)

        # Try to find a comparison handler that can handle these types and operator
        handler = ConditionParser._get_comparison_handler(actual_val, expected_val, op)
        if handler:
            result = handler.compare(actual_val, expected_val, op)
            return bool(result)

        # No handler found - log warning and return False
        _LOGGER.warning(
            "No comparison handler found for types %s and %s with operator %s: %s %s %s",
            type(actual_val).__name__,
            type(expected_val).__name__,
            op,
            actual_val,
            op,
            expected_val,
        )
        return False

    @staticmethod
    def _get_comparison_handler(actual_val: Any, expected_val: Any, op: str) -> ComparisonHandler | None:
        """Get the appropriate comparison handler for the given types and operator.

        Args:
            actual_val: Actual value
            expected_val: Expected value
            op: Comparison operator

        Returns:
            Comparison handler or None if no handler can handle this combination
        """
        # Get all registered comparison handlers
        handlers = ConditionParser._get_comparison_handlers()

        # Find the first handler that can handle this combination
        for handler in handlers:
            if handler.can_handle(actual_val, expected_val, op):
                return handler

        return None

    @staticmethod
    def _get_comparison_handlers() -> list[ComparisonHandler]:
        """Get all registered comparison handlers.

        Returns:
            List of comparison handlers
        """
        # For now, return the built-in handlers
        # In the future, this could be extended to support plugin handlers
        return [
            ConditionParser._NumericComparisonHandler(),
            # Future: ConditionParser._StringComparisonHandler(),
            # Future: ConditionParser._BooleanComparisonHandler(),
        ]

    class _NumericComparisonHandler:
        """Handler for numeric comparisons."""

        def can_handle(self, actual_val: Any, expected_val: Any, op: str) -> bool:
            """Check if this handler can handle the given types and operator."""
            return (
                isinstance(actual_val, (int, float)) and isinstance(expected_val, (int, float)) and op in ("<=", ">=", "<", ">")
            )

        def compare(self, actual_val: float, expected_val: float, op: str) -> bool:
            """Perform numeric comparison."""
            operators: dict[str, Callable[[], bool]] = {
                "<=": lambda: actual_val <= expected_val,
                ">=": lambda: actual_val >= expected_val,
                "<": lambda: actual_val < expected_val,
                ">": lambda: actual_val > expected_val,
            }
            return operators.get(op, lambda: False)()
