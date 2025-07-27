"""Numeric comparison handler for numeric value comparisons."""

from __future__ import annotations

from ..constants_types import TypeCategory
from ..exceptions import UnsupportedComparisonError
from ..type_analyzer import OperandType
from .base_handler import BaseComparisonHandler
from .comparison_protocol import ComparisonTypeInfo


class NumericComparisonHandler(BaseComparisonHandler):
    """Handler for numeric comparisons."""

    def get_supported_types(self) -> set[TypeCategory]:
        """Get supported type categories."""
        return {TypeCategory.NUMERIC}

    def get_supported_operators(self) -> set[str]:
        """Get supported operators."""
        return {"==", "!=", "<", ">", "<=", ">="}

    def get_type_info(self) -> ComparisonTypeInfo:
        """Get type information for this comparison handler."""
        return ComparisonTypeInfo(
            type_name="numeric",
            priority=50,  # Lower priority than specialized handlers
            supported_operators=self.get_supported_operators(),
            can_handle_user_types=False,
        )

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Check if this handler can compare these raw values."""
        if op not in self.get_supported_operators():
            return False

        # Check if both values can be converted to numeric
        left_ok, _ = self.type_analyzer.try_reduce_to_numeric(left_raw)
        right_ok, _ = self.type_analyzer.try_reduce_to_numeric(right_raw)

        return left_ok and right_ok

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Compare raw numeric values directly."""
        if not self.can_handle_raw(left_raw, right_raw, op):
            raise UnsupportedComparisonError(
                f"NumericComparisonHandler cannot handle comparison between {type(left_raw).__name__} and {type(right_raw).__name__} with operator '{op}'"
            )

        try:
            _, left_numeric = self.type_analyzer.try_reduce_to_numeric(left_raw)
            _, right_numeric = self.type_analyzer.try_reduce_to_numeric(right_raw)

            return self._apply_operator(left_numeric, right_numeric, op)

        except ValueError as e:
            raise UnsupportedComparisonError(f"Numeric comparison failed: {e}") from e

    def _compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform numeric comparison."""
        return self.compare_raw(actual_val, expected_val, op)
