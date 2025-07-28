"""String comparison handler for string value comparisons."""

from __future__ import annotations

from ..constants_types import TypeCategory
from ..exceptions import UnsupportedComparisonError
from ..type_analyzer import OperandType
from .base_handler import BaseComparisonHandler
from .comparison_protocol import ComparisonTypeInfo


class StringComparisonHandler(BaseComparisonHandler):
    """Handler for string comparisons (equality and containment only)."""

    def get_supported_types(self) -> set[TypeCategory]:
        """Get supported type categories."""
        return {TypeCategory.STRING}

    def get_supported_operators(self) -> set[str]:
        """Get supported operators."""
        return {"==", "!=", "in", "not in"}

    def get_type_info(self) -> ComparisonTypeInfo:
        """Get type information for this comparison handler."""
        return ComparisonTypeInfo(
            type_name="string",
            priority=40,  # Higher priority than numeric
            supported_operators=self.get_supported_operators(),
            can_handle_user_types=False,
        )

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Check if this handler can compare these raw values."""
        if op not in self.get_supported_operators():
            return False

        # String handler can handle any values that can be converted to strings
        return isinstance(left_raw, str) and isinstance(right_raw, str)

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Compare raw string values directly."""
        if not self.can_handle_raw(left_raw, right_raw, op):
            raise UnsupportedComparisonError(
                f"StringComparisonHandler cannot handle comparison between {type(left_raw).__name__} and {type(right_raw).__name__} with operator '{op}'"
            )

        try:
            str_left = str(left_raw)
            str_right = str(right_raw)

            return self._apply_operator(str_left, str_right, op)

        except ValueError as e:
            raise UnsupportedComparisonError(f"String comparison failed: {e}") from e

    def _compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform string comparison."""
        return self.compare_raw(actual_val, expected_val, op)
