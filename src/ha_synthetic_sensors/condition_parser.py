"""Condition parsing and evaluation for collection patterns."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from .exceptions import DataValidationError
from .type_analyzer import OperandType


class ParsedCondition(TypedDict):
    """Represents a parsed condition with operator and value.

    This structure can represent any type of condition - built-in types
    (numeric, string, boolean, datetime, version) or user-defined types.
    The comparison factory will handle type detection and conversion.

    Example:
        {"operator": ">=", "value": "50"}
        {"operator": "==", "value": "192.168.1.1"}
        {"operator": "!=", "value": "off"}
    """

    operator: str
    value: str  # Raw string value for factory processing


class ParsedAttributeCondition(TypedDict):
    """Represents a parsed attribute condition.

    Contains the attribute name plus the comparison details.

    Example:
        {"attribute": "temperature", "operator": ">", "value": "20"}
        {"attribute": "ip_address", "operator": "==", "value": "192.168.1.1"}
    """

    attribute: str
    operator: str
    value: str  # Raw string value for factory processing


class ConditionParser:
    """Parser for state and attribute conditions in collection patterns."""

    @staticmethod
    def parse_state_condition(condition: str) -> ParsedCondition:
        """Parse a state condition string into a structured condition.

        Args:
            condition: State condition string (e.g., "== on", ">= 50", "!off")

        Returns:
            ParsedCondition with operator and raw value for factory processing

        Raises:
            DataValidationError: If condition format is invalid
        """
        condition = condition.strip()
        if not condition:
            raise DataValidationError("State condition cannot be empty")

        # STEP 1: Detect and reject invalid cases first

        # Check for operators without values (including compound operators like >=, <=, ==, !=)
        from .regex_helper import is_operator_only

        if is_operator_only(condition):
            raise DataValidationError(f"Invalid state condition: '{condition}' is just an operator without a value")

        from .regex_helper import has_assignment_operator

        if has_assignment_operator(condition):  # Single = (assignment, not comparison)
            raise DataValidationError(f"Invalid state condition: '{condition}'. Use '==' for comparison, not '='")

        from .regex_helper import has_non_comparison_operators

        if has_non_comparison_operators(
            condition
        ):  # Non-comparison operators anywhere (excluding - for dates/negative numbers)
            raise DataValidationError(
                f"Invalid state condition: '{condition}'. Expected comparison operators: ==, !=, <, <=, >, >="
            )

        from .regex_helper import has_multiple_comparison_operators

        if has_multiple_comparison_operators(condition):  # Multiple > or < (like >>, <<)
            raise DataValidationError(
                f"Invalid state condition: '{condition}'. Expected comparison operators: ==, !=, <, <=, >, >="
            )

        # STEP 2: Parse valid cases

        # Handle simple negation: !value (but not != operator)
        from .regex_helper import extract_negation_condition

        negated_condition = extract_negation_condition(condition)
        if negated_condition:
            value_str = negated_condition.strip()
            if not value_str:
                raise DataValidationError(f"Invalid state condition: '{condition}'. Negation '!' requires a value")
            return ParsedCondition(operator="!=", value=ConditionParser._clean_value_string(value_str))

        # Handle explicit comparison operators: >=, ==, !=, etc.
        from .regex_helper import extract_comparison_condition

        comparison_result = extract_comparison_condition(condition)
        if comparison_result:
            op, value_str = comparison_result
            value_str = value_str.strip()

            # Validate operator is recognized
            if op not in {"<=", ">=", "==", "!=", "<", ">"}:
                raise DataValidationError(f"Invalid comparison operator '{op}'. Expected: ==, !=, <, <=, >, >=")

            return ParsedCondition(operator=op, value=ConditionParser._clean_value_string(value_str))

        # Handle bare values (default to equality): value
        return ParsedCondition(operator="==", value=ConditionParser._clean_value_string(condition))

    @staticmethod
    def parse_attribute_condition(condition: str) -> ParsedAttributeCondition | None:
        """Parse an attribute condition string.

        Args:
            condition: Attribute condition string (e.g., "friendly_name == 'Living Room'")

        Returns:
            ParsedAttributeCondition or None if invalid
        """
        condition = condition.strip()
        if not condition:
            return None

        # Pattern: attribute_name operator value
        # Examples: friendly_name == "Living Room", battery_level > 50
        # Use centralized condition parsing pattern from regex helper
        from .regex_helper import create_condition_parsing_pattern, match_pattern

        pattern = create_condition_parsing_pattern()
        match = match_pattern(condition, pattern)

        if not match:
            return None

        attribute_name, operator, value_str = match.groups()
        value_str = value_str.strip()

        # Let the comparison factory handle all type inference
        cleaned_value = ConditionParser._clean_value_string(value_str)

        return ParsedAttributeCondition(attribute=attribute_name, operator=operator, value=cleaned_value)

    @staticmethod
    def _clean_value_string(value_str: str) -> str:
        """Clean a value string for processing by the comparison factory.

        Args:
            value_str: Raw value string from condition parsing

        Returns:
            Cleaned string value for the factory to process
        """
        value_str = value_str.strip()

        # Remove surrounding quotes if present
        if (value_str.startswith('"') and value_str.endswith('"')) or (value_str.startswith("'") and value_str.endswith("'")):
            value_str = value_str[1:-1]

        return value_str

    @staticmethod
    def _convert_value_for_comparison(value_str: str) -> int | float | bool | str:
        """Convert a string value to the appropriate type for comparison.

        Args:
            value_str: String value to convert

        Returns:
            Converted value (int, float, bool, or str)
        """
        # Try to convert to numeric types first
        try:
            if "." in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            pass

        # Try to convert to boolean
        if value_str.lower() in ("true", "false"):
            return value_str.lower() == "true"

        # Return as string
        return value_str

    @staticmethod
    def evaluate_condition(actual_value: OperandType, condition: ParsedCondition) -> bool:
        """Evaluate a parsed condition against an actual value.

        This method handles basic type comparisons using Python's built-in operators.

        Args:
            actual_value: The actual value to compare
            condition: Parsed condition with operator and expected value

        Returns:
            True if the condition matches
        """
        expected_value = ConditionParser._convert_value_for_comparison(condition["value"])
        operator = condition["operator"]

        # Convert actual_value to comparable type
        actual_converted = ConditionParser._convert_value_for_comparison(str(actual_value))

        # Define operator functions with explicit type annotations
        operator_functions: dict[str, Callable[[Any, Any], bool]] = {
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
        }

        try:
            if operator in operator_functions:
                return operator_functions[operator](actual_converted, expected_value)
            return False
        except TypeError:
            # If comparison fails due to type mismatch, return False
            return False

    @staticmethod
    def compare_values(actual: OperandType, op: str, expected: OperandType) -> bool:
        """Compare two values using the specified operator.

        This method handles basic type comparisons using Python's built-in operators.

        Args:
            actual: Actual value
            op: Comparison operator
            expected: Expected value

        Returns:
            True if comparison is true
        """
        # Convert both values to comparable types
        actual_converted = ConditionParser._convert_value_for_comparison(str(actual))
        expected_converted = ConditionParser._convert_value_for_comparison(str(expected))

        # Define operator functions with explicit type annotations
        operator_functions: dict[str, Callable[[Any, Any], bool]] = {
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
        }

        try:
            if op in operator_functions:
                return operator_functions[op](actual_converted, expected_converted)
            return False
        except TypeError:
            # If comparison fails due to type mismatch, return False
            return False
