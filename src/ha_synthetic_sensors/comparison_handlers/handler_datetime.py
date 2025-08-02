"""DateTime comparison handler for temporal value comparisons."""

from __future__ import annotations

from datetime import datetime

from ..constants_types import TypeCategory
from ..exceptions import UnsupportedComparisonError
from ..type_analyzer import DateTimeParser, OperandType
from .base_handler import BaseComparisonHandler
from .comparison_protocol import ComparisonTypeInfo


class DateTimeComparisonHandler(BaseComparisonHandler):
    """Handler for datetime comparisons."""

    def get_supported_types(self) -> set[TypeCategory]:
        """Get supported type categories."""
        return {TypeCategory.DATETIME}

    def get_supported_operators(self) -> set[str]:
        """Get supported operators."""
        return {"==", "!=", "<", ">", "<=", ">="}

    def get_type_info(self) -> ComparisonTypeInfo:
        """Get type information for this comparison handler."""
        return ComparisonTypeInfo(
            type_name="datetime",
            priority=20,  # High priority for datetime strings
            supported_operators=self.get_supported_operators(),
            can_handle_user_types=False,
        )

    def can_handle(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Check if this handler can handle the comparison.

        Args:
            actual_val: Actual value to compare
            expected_val: Expected value to compare
            op: Comparison operator

        Returns:
            True if this handler can handle the comparison
        """
        if op not in self.get_supported_operators():
            return False

        try:
            actual_type = self.type_analyzer.categorize_type(actual_val)
            expected_type = self.type_analyzer.categorize_type(expected_val)

            # Handle pure datetime comparisons
            if actual_type == expected_type == TypeCategory.DATETIME:
                return True

            # Handle cross-type datetime/string - datetime handler can handle string conversions
            if actual_type == TypeCategory.DATETIME and expected_type == TypeCategory.STRING:
                return self._can_convert_to_datetime(expected_val)

            if actual_type == TypeCategory.STRING and expected_type == TypeCategory.DATETIME:
                return self._can_convert_to_datetime(actual_val)

            return False

        except ValueError:
            return False

    def _can_convert_to_datetime(self, value: OperandType) -> bool:
        """Check if a value can be converted to datetime."""
        try:
            self._to_datetime(value)
            return True
        except (ValueError, TypeError):
            return False

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Check if this handler can compare these raw values."""
        if op not in self.get_supported_operators():  # pylint: disable=duplicate-code
            return False

        return self._can_convert_to_datetime(left_raw) and self._can_convert_to_datetime(right_raw)

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Compare raw datetime values directly."""
        if not self.can_handle_raw(left_raw, right_raw, op):
            raise UnsupportedComparisonError(
                f"DateTimeComparisonHandler cannot handle comparison between {type(left_raw).__name__} and {type(right_raw).__name__} with operator '{op}'"
            )

        try:
            dt_left = self._to_datetime(left_raw)
            dt_right = self._to_datetime(right_raw)
            return self._apply_operator(dt_left, dt_right, op)

        except ValueError as e:
            raise UnsupportedComparisonError(f"DateTime comparison failed: {e}") from e

    def _compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform datetime comparison."""
        return self.compare_raw(actual_val, expected_val, op)

    def _to_datetime(self, value: OperandType) -> datetime:
        """Convert value to datetime object."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            # Use centralized timezone normalization
            normalized_value = DateTimeParser.normalize_iso_timezone(value)
            return datetime.fromisoformat(normalized_value)

        raise ValueError(f"Cannot convert {value} to datetime")
