"""Boolean comparison handler for Home Assistant state values."""

from __future__ import annotations

from typing import ClassVar

from ..constants_types import TypeCategory
from ..exceptions import UnsupportedComparisonError
from ..type_analyzer import OperandType
from .base_handler import BaseComparisonHandler
from .comparison_protocol import ComparisonTypeInfo


class BooleanComparisonHandler(BaseComparisonHandler):
    """Handler for boolean and Home Assistant state comparisons."""

    # Home Assistant common state mappings
    TRUE_STATES: ClassVar[set[str]] = {"on", "true", "yes", "1", "open", "home", "active", "enabled"}
    FALSE_STATES: ClassVar[set[str]] = {"off", "false", "no", "0", "closed", "away", "inactive", "disabled"}

    def get_supported_types(self) -> set[TypeCategory]:
        """Get supported type categories."""
        return {TypeCategory.BOOLEAN, TypeCategory.STRING}

    def get_supported_operators(self) -> set[str]:
        """Get supported operators."""
        return {"==", "!="}

    def get_type_info(self) -> ComparisonTypeInfo:
        """Get type information for this comparison handler."""
        return ComparisonTypeInfo(
            type_name="boolean",
            priority=30,  # High priority for boolean states
            supported_operators=self.get_supported_operators(),
            can_handle_user_types=False,
        )

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Check if this handler can compare these raw values."""
        if op not in self.get_supported_operators():
            return False

        # If both are actual booleans, handle it
        if isinstance(left_raw, bool) and isinstance(right_raw, bool):
            return True

        # If one is boolean and the other is boolean string, handle it
        if (isinstance(left_raw, bool) and self._is_boolean_string(right_raw)) or (
            self._is_boolean_string(left_raw) and isinstance(right_raw, bool)
        ):
            return True

        # If both are boolean strings, handle it
        return self._is_boolean_string(left_raw) and self._is_boolean_string(right_raw)

    def _is_boolean_string(self, value: OperandType) -> bool:
        """Check if value is a boolean string like 'on', 'off', etc."""
        if isinstance(value, str):
            lower_val = value.lower().strip()
            return lower_val in self.TRUE_STATES or lower_val in self.FALSE_STATES
        return False

    def _is_boolean_like(self, value: OperandType) -> bool:
        """Check if value is boolean or boolean-like state."""
        if isinstance(value, bool):
            return True
        if isinstance(value, str):
            lower_val = value.lower().strip()
            return lower_val in self.TRUE_STATES or lower_val in self.FALSE_STATES
        # Numeric values can be converted to boolean (0=False, non-zero=True)
        return isinstance(value, (int, float))

    def _to_boolean(self, value: OperandType) -> bool:
        """Convert value to boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lower_val = value.lower().strip()
            if lower_val in self.TRUE_STATES:
                return True
            if lower_val in self.FALSE_STATES:
                return False
        if isinstance(value, (int, float)):
            # Convert numeric values: 0 = False, non-zero = True
            return bool(value)
        raise ValueError(f"Cannot convert {value} to boolean")

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Compare raw boolean values directly."""
        if not self.can_handle_raw(left_raw, right_raw, op):
            raise UnsupportedComparisonError(
                f"BooleanComparisonHandler cannot handle comparison between {type(left_raw).__name__} and {type(right_raw).__name__} with operator '{op}'"
            )

        try:
            bool_left = self._to_boolean(left_raw)
            bool_right = self._to_boolean(right_raw)

            if op == "==":
                return bool_left == bool_right
            if op == "!=":
                return bool_left != bool_right
            raise UnsupportedComparisonError(f"Unsupported operator for boolean: {op}")

        except ValueError as e:
            raise UnsupportedComparisonError(f"Boolean comparison failed: {e}") from e

    def _compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform boolean comparison."""
        return self.compare_raw(actual_val, expected_val, op)
