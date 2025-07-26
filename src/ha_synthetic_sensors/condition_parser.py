"""Condition parsing and evaluation for collection patterns."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
import re
from typing import Any, Callable, Protocol

from simpleeval import SimpleEval

from .constants_types import BuiltinValueType, TypeCategory
from .exceptions import ComparisonHandlerError, DataValidationError, UnsupportedComparisonError
from .type_analyzer import OperandType, TypeAnalyzer, TypeReducer


class ComparisonHandler(Protocol):
    """Protocol for comparison handlers."""

    def can_handle(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Check if this handler can handle the given types and operator."""

    def compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform the comparison and return result."""


class BaseComparisonHandler(ABC):
    """Base class for comparison handlers with common functionality."""

    def __init__(self) -> None:
        """Initialize with type analyzer."""
        self.type_analyzer = TypeAnalyzer()

    @abstractmethod
    def get_supported_types(self) -> set[TypeCategory]:
        """Get the type categories this handler supports."""

    @abstractmethod
    def get_supported_operators(self) -> set[str]:
        """Get the operators this handler supports."""

    def can_handle(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Check if this handler can handle the given types and operator.

        Args:
            actual_val: Actual value
            expected_val: Expected value
            op: Comparison operator

        Returns:
            True if handler can process this comparison
        """
        # Check if operator is supported
        if op not in self.get_supported_operators():
            return False

        # Special handling for version tuples (from TypeReducer) in VersionComparisonHandler
        if (
            self.__class__.__name__ == "VersionComparisonHandler"
            and isinstance(actual_val, tuple)
            and isinstance(expected_val, tuple)
        ):
            return True

        try:
            actual_type = self.type_analyzer.categorize_type(actual_val)
            expected_type = self.type_analyzer.categorize_type(expected_val)

            # Check if both types are supported or if valid cross-type conversion exists
            supported_types = self.get_supported_types()

            # Same-type comparisons
            if actual_type == expected_type and actual_type in supported_types:
                return True

            # Cross-type conversions (subclasses can override this logic)
            return self._can_handle_cross_type(actual_type, expected_type)

        except ValueError:
            # Type analysis failed (e.g., None values)
            return False

    def _can_handle_cross_type(self, actual_type: TypeCategory, expected_type: TypeCategory) -> bool:
        """Check if cross-type conversion is supported. Override in subclasses."""
        return False

    @abstractmethod
    def compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform the comparison and return result."""


class NumericComparisonHandler(BaseComparisonHandler):
    """Handler for numeric comparisons."""

    def get_supported_types(self) -> set[TypeCategory]:
        """Get supported type categories."""
        return {TypeCategory.NUMERIC}

    def get_supported_operators(self) -> set[str]:
        """Get supported operators."""
        return {"<", ">", "<=", ">="}

    def compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform numeric comparison.

        Args:
            actual_val: Actual numeric value
            expected_val: Expected numeric value
            op: Comparison operator

        Returns:
            Comparison result

        Raises:
            UnsupportedComparisonError: If comparison cannot be performed
        """
        try:
            actual_type = self.type_analyzer.categorize_type(actual_val)
            expected_type = self.type_analyzer.categorize_type(expected_val)

            if actual_type != TypeCategory.NUMERIC or expected_type != TypeCategory.NUMERIC:
                raise UnsupportedComparisonError(
                    f"NumericComparisonHandler cannot compare {actual_type.value} and {expected_type.value}"
                )

            # Convert to numeric types for comparison
            # Use type analyzer to ensure we can convert to numeric
            if not self.type_analyzer.can_reduce_to_numeric(actual_val):
                raise UnsupportedComparisonError(f"Cannot convert {actual_val} to numeric")
            if not self.type_analyzer.can_reduce_to_numeric(expected_val):
                raise UnsupportedComparisonError(f"Cannot convert {expected_val} to numeric")

            _, actual_numeric = self.type_analyzer.try_reduce_to_numeric(actual_val)
            _, expected_numeric = self.type_analyzer.try_reduce_to_numeric(expected_val)

            return self._compare_numeric(actual_numeric, expected_numeric, op)

        except ValueError as e:
            raise UnsupportedComparisonError(f"Numeric comparison failed: {e}") from e

    def _compare_numeric(self, actual: float, expected: float, op: str) -> bool:
        """Perform numeric comparison."""
        comparison_ops: dict[str, Callable[[float, float], bool]] = {
            "<=": lambda a, e: a <= e,
            ">=": lambda a, e: a >= e,
            "<": lambda a, e: a < e,
            ">": lambda a, e: a > e,
        }
        return comparison_ops[op](float(actual), float(expected))


class DateTimeComparisonHandler(BaseComparisonHandler):
    """Handler for datetime comparisons."""

    def get_supported_types(self) -> set[TypeCategory]:
        """Get supported type categories."""
        return {TypeCategory.DATETIME, TypeCategory.STRING}

    def get_supported_operators(self) -> set[str]:
        """Get supported operators."""
        return {"<", ">", "<=", ">="}

    def _can_handle_cross_type(self, actual_type: TypeCategory, expected_type: TypeCategory) -> bool:
        """Check if cross-type datetime/string conversion is supported."""
        type_pair = (actual_type, expected_type)
        valid_conversions = {
            (TypeCategory.DATETIME, TypeCategory.STRING),
            (TypeCategory.STRING, TypeCategory.DATETIME),
        }
        return type_pair in valid_conversions

    def compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform datetime comparison.

        Args:
            actual_val: Actual datetime value
            expected_val: Expected datetime value
            op: Comparison operator

        Returns:
            Comparison result

        Raises:
            UnsupportedComparisonError: If comparison cannot be performed
        """
        try:
            actual_type = self.type_analyzer.categorize_type(actual_val)
            expected_type = self.type_analyzer.categorize_type(expected_val)

            # Validate that we can handle these types
            if not (
                self._can_handle_cross_type(actual_type, expected_type)
                or (actual_type == expected_type == TypeCategory.DATETIME)
            ):
                raise UnsupportedComparisonError(
                    f"DateTimeComparisonHandler cannot compare {actual_type.value} and {expected_type.value}"
                )

            # Convert both to datetime and compare
            dt_actual = self._to_datetime(actual_val)
            dt_expected = self._to_datetime(expected_val)
            return self._compare_datetime(dt_actual, dt_expected, op)

        except ValueError as e:
            raise UnsupportedComparisonError(f"DateTime comparison failed: {e}") from e

    def _compare_datetime(self, actual: datetime, expected: datetime, op: str) -> bool:
        """Perform datetime comparison."""
        comparison_ops: dict[str, Callable[[datetime, datetime], bool]] = {
            "<=": lambda a, e: a <= e,
            ">=": lambda a, e: a >= e,
            "<": lambda a, e: a < e,
            ">": lambda a, e: a > e,
        }
        return comparison_ops[op](actual, expected)

    def _to_datetime(self, value: OperandType) -> datetime:
        """Convert value to datetime object."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            # Handle common ISO formats
            test_value = value.replace("Z", "+00:00")
            return datetime.fromisoformat(test_value)

        raise ValueError(f"Cannot convert {value} to datetime")


class VersionComparisonHandler(BaseComparisonHandler):
    """Handler for version comparisons."""

    def get_supported_types(self) -> set[TypeCategory]:
        """Get supported type categories."""
        return {TypeCategory.VERSION, TypeCategory.STRING}

    def get_supported_operators(self) -> set[str]:
        """Get supported operators."""
        return {"<", ">", "<=", ">="}

    def _can_handle_cross_type(self, actual_type: TypeCategory, expected_type: TypeCategory) -> bool:
        """Check if cross-type version/string conversion is supported."""
        type_pair = (actual_type, expected_type)
        valid_conversions = {
            (TypeCategory.VERSION, TypeCategory.STRING),
            (TypeCategory.STRING, TypeCategory.VERSION),
        }
        return type_pair in valid_conversions

    def compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform version comparison.

        Args:
            actual_val: Actual version value
            expected_val: Expected version value
            op: Comparison operator

        Returns:
            Comparison result

        Raises:
            UnsupportedComparisonError: If comparison cannot be performed
        """
        try:
            # Handle version tuples directly (from TypeReducer)
            if isinstance(actual_val, tuple) and isinstance(expected_val, tuple):
                return self._compare_version_tuples(actual_val, expected_val, op)

            actual_type = self.type_analyzer.categorize_type(actual_val)
            expected_type = self.type_analyzer.categorize_type(expected_val)

            # Validate that we can handle these types
            if not (
                self._can_handle_cross_type(actual_type, expected_type)
                or (actual_type == expected_type == TypeCategory.VERSION)
            ):
                raise UnsupportedComparisonError(
                    f"VersionComparisonHandler cannot compare {actual_type.value} and {expected_type.value}"
                )

            # Convert both to version tuples and compare
            ver_actual = self._parse_version(str(actual_val))
            ver_expected = self._parse_version(str(expected_val))
            return self._compare_version_tuples(ver_actual, ver_expected, op)

        except ValueError as e:
            raise UnsupportedComparisonError(f"Version comparison failed: {e}") from e

    def _compare_version_tuples(self, actual: tuple[int, ...], expected: tuple[int, ...], op: str) -> bool:
        """Compare version tuples."""
        comparison_ops: dict[str, Callable[[tuple[int, ...], tuple[int, ...]], bool]] = {
            "<=": lambda a, e: a <= e,
            ">=": lambda a, e: a >= e,
            "<": lambda a, e: a < e,
            ">": lambda a, e: a > e,
        }
        return comparison_ops[op](actual, expected)

    def _parse_version(self, version: str) -> tuple[int, ...]:
        """Parse version string into comparable tuple."""
        # Remove 'v' prefix if present
        clean_version = version.lower().lstrip("v")

        # Extract numeric parts
        parts = re.findall(r"\d+", clean_version)
        if not parts:
            raise ValueError(f"Invalid version string: {version}")

        return tuple(int(part) for part in parts)


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
    def _normalize_comparison_values(actual: Any, expected: Any) -> tuple[BuiltinValueType, BuiltinValueType]:
        """Normalize values for comparison using formula-based type reduction.

        Formula-Based Type Reduction Strategy:
        1. NUMERIC reduction (highest priority) - enables mathematical comparisons
        2. DATETIME reduction - for temporal comparisons
        3. VERSION reduction - for version comparisons
        4. STRING fallback - when no other reduction possible

        This ensures formula-friendly behavior:
        - "5" compared to 3 becomes 5.0 compared to 3.0
        - True compared to 1 becomes 1.0 compared to 1.0
        - "2024-01-01" compared to datetime becomes datetime comparison

        Args:
            actual: Actual value
            expected: Expected value

        Returns:
            Tuple of normalized values using best common type
        """
        type_reducer = TypeReducer()
        reduced_actual, reduced_expected, _ = type_reducer.reduce_pair_for_comparison(actual, expected)

        # Return the reduced values which are now in the best common type
        return reduced_actual, reduced_expected

    @staticmethod
    def _dispatch_comparison(actual_val: Any, expected_val: Any, op: str) -> bool:
        """Dispatch comparison to appropriate function based on operator.

        Args:
            actual_val: Actual value
            expected_val: Expected value
            op: Comparison operator

        Returns:
            True if comparison is true

        Raises:
            ComparisonHandlerError: If no handler can process the comparison
        """
        # Handle equality operators (work with any type)
        if op in ("==", "!="):
            return bool(actual_val == expected_val) if op == "==" else bool(actual_val != expected_val)

        # Try to find a comparison handler that can handle these types and operator
        handler = ConditionParser._get_comparison_handler(actual_val, expected_val, op)
        if handler:
            result = handler.compare(actual_val, expected_val, op)
            return bool(result)

        # No handler found - raise exception for deterministic failure
        raise ComparisonHandlerError(
            f"No comparison handler found for types {type(actual_val).__name__} and {type(expected_val).__name__} "
            f"with operator {op}: {actual_val} {op} {expected_val}"
        )

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
        # Return all built-in handlers in priority order
        # Future: this could be extended to support plugin handlers
        return [
            NumericComparisonHandler(),
            DateTimeComparisonHandler(),
            VersionComparisonHandler(),
        ]
