"""Condition parser for collection resolver.

This module handles parsing and evaluation of state and attribute conditions
used in collection patterns.
"""

import logging
import re
from typing import Any

from simpleeval import SimpleEval

from .exceptions import DataValidationError

_LOGGER = logging.getLogger(__name__)


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
        # Handle equality operators
        if op in ("==", "!="):
            return bool(actual_val == expected_val) if op == "==" else bool(actual_val != expected_val)

        # For numeric comparisons, ensure both values are numeric
        if not (isinstance(actual_val, (int, float)) and isinstance(expected_val, (int, float))):
            _LOGGER.warning("Non-numeric comparison attempted: %s %s %s", actual_val, op, expected_val)
            return False

        # Define comparison operations
        comparison_ops: dict[str, Any] = {
            "<=": lambda a, e: a <= e,
            ">=": lambda a, e: a >= e,
            "<": lambda a, e: a < e,
            ">": lambda a, e: a > e,
        }

        # Execute comparison if operator is supported
        if op in comparison_ops:
            return bool(comparison_ops[op](actual_val, expected_val))

        _LOGGER.warning("Unknown comparison operator: %s", op)
        return False
