"""Base comparison handler interface and abstract class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from ..constants_types import TypeCategory
from ..exceptions import UnsupportedComparisonError
from ..type_analyzer import OperandType, TypeAnalyzer
from .comparison_protocol import ComparisonCapable, ComparisonTypeInfo


class ComparisonHandler(Protocol):
    """Protocol for comparison handlers."""

    def can_handle(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Check if this handler can handle the given types and operator."""

    def compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform the comparison and return result."""


class BaseComparisonHandler(ABC, ComparisonCapable):
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

    @abstractmethod
    def get_type_info(self) -> ComparisonTypeInfo:
        """Get type information for this comparison handler."""

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

    def compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform the comparison and return result.

        This method validates the operator and delegates to the subclass implementation.
        """
        if op not in self.get_supported_operators():
            raise UnsupportedComparisonError(f"{self.__class__.__name__} does not support operator: {op}")

        if not self.can_handle(actual_val, expected_val, op):
            raise UnsupportedComparisonError(
                f"{self.__class__.__name__} cannot handle comparison between {type(actual_val).__name__} and {type(expected_val).__name__} with operator '{op}'"
            )

        return self._compare(actual_val, expected_val, op)

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Default implementation using existing can_handle method."""
        return self.can_handle(left_raw, right_raw, op)

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Default implementation using existing compare method."""
        return self.compare(left_raw, right_raw, op)

    @abstractmethod
    def _compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform the actual comparison. Subclasses must implement this."""

    def _apply_operator(self, actual: Any, expected: Any, op: str) -> bool:
        """Apply comparison operator using dictionary lookup.

        This method provides the standard operator implementations.
        Subclasses can override specific operators by overriding the individual operator methods.

        Args:
            actual: Actual value (converted to handler's native type)
            expected: Expected value (converted to handler's native type)
            op: Comparison operator

        Returns:
            Comparison result
        """
        operators = {
            "==": self._op_eq,
            "!=": self._op_ne,
            "<=": self._op_le,
            ">=": self._op_ge,
            "<": self._op_lt,
            ">": self._op_gt,
            "in": self._op_in,
            "not in": self._op_not_in,
        }

        if op in operators:
            return operators[op](actual, expected)

        raise UnsupportedComparisonError(f"{self.__class__.__name__} does not support operator: {op}")

    # Standard operator implementations - subclasses can override individual operators
    def _op_eq(self, actual: Any, expected: Any) -> bool:
        """Equality operator."""
        return bool(actual == expected)

    def _op_ne(self, actual: Any, expected: Any) -> bool:
        """Not equal operator."""
        return bool(actual != expected)

    def _op_le(self, actual: Any, expected: Any) -> bool:
        """Less than or equal operator."""
        return bool(actual <= expected)

    def _op_ge(self, actual: Any, expected: Any) -> bool:
        """Greater than or equal operator."""
        return bool(actual >= expected)

    def _op_lt(self, actual: Any, expected: Any) -> bool:
        """Less than operator."""
        return bool(actual < expected)

    def _op_gt(self, actual: Any, expected: Any) -> bool:
        """Greater than operator."""
        return bool(actual > expected)

    def _op_in(self, actual: Any, expected: Any) -> bool:
        """In operator (for string containment)."""
        return bool(actual in expected)

    def _op_not_in(self, actual: Any, expected: Any) -> bool:
        """Not in operator (for string containment)."""
        return bool(actual not in expected)
