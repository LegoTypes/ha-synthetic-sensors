"""Comparison factory using extensible registry."""

from __future__ import annotations

from ..exceptions import UnsupportedComparisonError
from ..type_analyzer import OperandType
from .comparison_protocol import ComparisonTypeInfo, UserComparisonType
from .extensible_registry import get_extensible_registry, register_user_comparison_type


class ComparisonFactory:
    """Factory that routes comparisons using an extensible registry system."""

    def __init__(self) -> None:
        """Initialize the factory with the extensible registry."""
        self._registry = get_extensible_registry()

    def compare(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Compare two raw values using the first available handler.

        The registry handles priority ordering and user-defined handlers automatically.
        """
        handler = self._registry.find_handler(left_raw, right_raw, op)
        if handler is None:
            raise UnsupportedComparisonError(
                f"No comparison handler found for types {type(left_raw).__name__} "
                f"and {type(right_raw).__name__} with operator '{op}'"
            )

        return handler.compare_raw(left_raw, right_raw, op)

    def register_user_handler(self, handler: UserComparisonType) -> None:
        """Register a user-defined comparison handler."""
        self._registry.register_comparison_type(handler)

    def get_handler_info(self) -> list[ComparisonTypeInfo]:
        """Get information about all registered handlers."""
        return self._registry.get_handler_info()


# Global factory instance
_factory: ComparisonFactory | None = None


def get_comparison_factory() -> ComparisonFactory:
    """Get the global comparison factory instance."""
    global _factory  # pylint: disable=global-statement
    if _factory is None:
        _factory = ComparisonFactory()
    return _factory


def compare_values(left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
    """Compare two raw values using the global factory."""
    return get_comparison_factory().compare(left_raw, right_raw, op)


def register_user_comparison_handler(handler: UserComparisonType) -> None:
    """Register a user-defined comparison handler with the global factory."""
    register_user_comparison_type(handler)
