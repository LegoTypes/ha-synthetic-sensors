"""Protocols for extensible comparison system."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypedDict, runtime_checkable

if TYPE_CHECKING:
    from ..type_analyzer import OperandType


class ComparisonTypeInfo(TypedDict):
    """Type information for comparison routing."""

    type_name: str
    priority: int  # Lower numbers = higher priority
    supported_operators: set[str]
    can_handle_user_types: bool


@runtime_checkable
class ComparisonCapable(Protocol):
    """Protocol for types that can handle comparisons."""

    def get_type_info(self) -> ComparisonTypeInfo:
        """Get type information for this comparison handler."""

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Check if this handler can compare these raw values."""

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Compare raw values directly."""


@runtime_checkable
class UserComparisonType(Protocol):
    """Protocol for user-defined comparison types."""

    def get_type_info(self) -> ComparisonTypeInfo:
        """Get type information for this user comparison type."""

    def can_handle_user_type(self, value: OperandType, metadata: dict[str, Any]) -> bool:
        """Check if this handler can process a user-defined type."""

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Check if this handler can compare these raw values."""

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Compare raw values, handling user types if applicable."""


@runtime_checkable
class ComparisonRegistry(Protocol):
    """Protocol for registering and managing comparison types."""

    def register_comparison_type(self, handler: ComparisonCapable | UserComparisonType) -> None:
        """Register a new comparison type handler."""

    def get_ordered_handlers(self) -> list[ComparisonCapable | UserComparisonType]:
        """Get handlers ordered by priority."""

    def find_handler(
        self, left_raw: OperandType, right_raw: OperandType, op: str
    ) -> ComparisonCapable | UserComparisonType | None:
        """Find the first handler that can handle the given comparison."""
