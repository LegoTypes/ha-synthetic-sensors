"""Condition parsing and evaluation for collection patterns."""

from __future__ import annotations

import re
from typing import TypedDict

from .comparison_handlers import compare_values as factory_compare_values
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
        if re.match(r"\s*(<=|>=|==|!=|<|>|[=&|%*/+-])\s*$", condition):
            raise DataValidationError(f"Invalid state condition: '{condition}' is just an operator without a value")

        if re.match(r"\s*[=]{1}[^=]", condition):  # Single = (assignment, not comparison)
            raise DataValidationError(f"Invalid state condition: '{condition}'. Use '==' for comparison, not '='")

        if re.search(r"[&|%*/+]", condition):  # Non-comparison operators anywhere (excluding - for dates/negative numbers)
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
            return ParsedCondition(operator="!=", value=ConditionParser._clean_value_string(value_str))

        # Handle explicit comparison operators: >=, ==, !=, etc.
        operator_match = re.match(r"\s*(<=|>=|==|!=|<|>)\s+(.+)", condition)  # Note: \s+ requires space
        if operator_match:
            op, value_str = operator_match.groups()
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
        pattern = r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*(<=|>=|==|!=|<|>)\s*(.+)$"
        match = re.match(pattern, condition)

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
    def evaluate_condition(actual_value: OperandType, condition: ParsedCondition) -> bool:
        """Evaluate a parsed condition against an actual value.

        This method can handle any type supported by the extensible comparison system,
        including built-in types (numeric, string, boolean, datetime, version) and
        user-defined types registered with the comparison factory.

        Args:
            actual_value: The actual value to compare (any supported type)
            condition: Parsed condition with operator and expected value

        Returns:
            True if the condition matches
        """
        return factory_compare_values(actual_value, condition["value"], condition["operator"])

    @staticmethod
    def compare_values(actual: OperandType, op: str, expected: OperandType) -> bool:
        """Compare two values using the specified operator.

        This method can handle any types supported by the extensible comparison system,
        including built-in types and user-defined types registered with the factory.

        Args:
            actual: Actual value (any supported type)
            op: Comparison operator
            expected: Expected value (any supported type)

        Returns:
            True if comparison is true
        """
        return factory_compare_values(actual, expected, op)
