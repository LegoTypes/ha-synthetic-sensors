"""Version comparison handler for semantic version comparisons."""

from __future__ import annotations

import re

from ..constants_types import TypeCategory
from ..exceptions import UnsupportedComparisonError
from ..type_analyzer import OperandType
from .base_handler import BaseComparisonHandler
from .comparison_protocol import ComparisonTypeInfo


class VersionComparisonHandler(BaseComparisonHandler):
    """Handler for version comparisons."""

    def get_supported_types(self) -> set[TypeCategory]:
        """Get supported type categories."""
        return {TypeCategory.VERSION}

    def get_supported_operators(self) -> set[str]:
        """Get supported operators."""
        return {"==", "!=", "<", ">", "<=", ">="}

    def get_type_info(self) -> ComparisonTypeInfo:
        """Get type information for this comparison handler."""
        return ComparisonTypeInfo(
            type_name="version",
            priority=10,  # Highest priority for version strings
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

        # Handle version tuples directly (from TypeReducer)
        if isinstance(actual_val, tuple) and isinstance(expected_val, tuple):
            return True

        try:
            actual_type = self.type_analyzer.categorize_type(actual_val)
            expected_type = self.type_analyzer.categorize_type(expected_val)

            # Only handle pure version comparisons (both sides must be versions)
            return actual_type == expected_type == TypeCategory.VERSION

        except ValueError:
            return False

    def _can_parse_as_version(self, value: OperandType) -> bool:
        """Check if a value can be parsed as a version."""
        try:
            self._parse_version(str(value))
            return True
        except (ValueError, TypeError):
            return False

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Check if this handler can compare these raw values."""
        if op not in self.get_supported_operators():  # pylint: disable=duplicate-code
            return False

        # Handle version tuples directly
        if isinstance(left_raw, tuple) and isinstance(right_raw, tuple):
            return True

        # Check if both can be parsed as versions
        return self._can_parse_as_version(left_raw) and self._can_parse_as_version(right_raw)

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Compare raw version values directly."""
        if not self.can_handle_raw(left_raw, right_raw, op):
            raise UnsupportedComparisonError(
                f"VersionComparisonHandler cannot handle comparison between {type(left_raw).__name__} and {type(right_raw).__name__} with operator '{op}'"
            )

        try:
            # Handle version tuples directly
            if isinstance(left_raw, tuple) and isinstance(right_raw, tuple):
                return self._apply_operator(left_raw, right_raw, op)

            # Convert both to version tuples and compare
            ver_left = self._parse_version(str(left_raw))
            ver_right = self._parse_version(str(right_raw))
            return self._apply_operator(ver_left, ver_right, op)

        except ValueError as e:
            raise UnsupportedComparisonError(f"Version comparison failed: {e}") from e

    def _compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform version comparison."""
        return self.compare_raw(actual_val, expected_val, op)

    def _parse_version(self, version: str) -> tuple[int, ...]:
        """Parse version string into comparable tuple.

        Requires proper version format: vx.y.z (exactly 3 parts with 'v' prefix)
        """
        # Require 'v' prefix for version strings
        if not version.lower().startswith("v"):
            raise ValueError(f"Invalid version string: {version} (must start with 'v' prefix, e.g., v1.2.3)")

        # Remove 'v' prefix
        clean_version = version.lower().lstrip("v")

        # Validate it follows version pattern (exactly 3 numbers separated by dots)
        if not re.match(r"^\d+\.\d+\.\d+([.-].*)?$", clean_version):
            raise ValueError(f"Invalid version string: {version} (must be vx.y.z format with exactly 3 parts)")

        # Extract numeric parts separated by dots (take first 3 parts before any pre-release info)
        base_version = clean_version.split("-")[0].split("+")[0]  # Remove pre-release/build info
        parts = base_version.split(".")

        if len(parts) != 3:
            raise ValueError(f"Invalid version string: {version} (must have exactly 3 parts: vx.y.z)")

        try:
            # Each part should be a valid integer
            return tuple(int(part) for part in parts)
        except ValueError as exc:
            raise ValueError(f"Invalid version string: {version}") from exc
