"""Extensible comparison registry using protocols."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..type_analyzer import OperandType
from .comparison_protocol import ComparisonCapable, ComparisonRegistry, UserComparisonType
from .handler_boolean import BooleanComparisonHandler
from .handler_datetime import DateTimeComparisonHandler
from .handler_numeric import NumericComparisonHandler
from .handler_string import StringComparisonHandler
from .handler_version import VersionComparisonHandler

if TYPE_CHECKING:
    from .comparison_protocol import ComparisonTypeInfo


class ExtensibleComparisonRegistry(ComparisonRegistry):
    """Registry that manages comparison handlers using protocols."""

    def __init__(self) -> None:
        """Initialize with built-in comparison handlers."""
        self._handlers: list[ComparisonCapable | UserComparisonType] = []
        self._register_builtin_handlers()

    def _register_builtin_handlers(self) -> None:
        """Register the built-in comparison handlers."""
        # Register handlers in priority order (lower priority numbers first)
        builtin_handlers = [
            VersionComparisonHandler(),  # priority=10
            DateTimeComparisonHandler(),  # priority=20
            BooleanComparisonHandler(),  # priority=30
            StringComparisonHandler(),  # priority=40
            NumericComparisonHandler(),  # priority=50
        ]

        for handler in builtin_handlers:
            self.register_comparison_type(handler)

    def register_comparison_type(self, handler: ComparisonCapable | UserComparisonType) -> None:
        """Register a new comparison type handler.

        Handlers are automatically sorted by priority (lower numbers = higher priority).
        """
        type_info = handler.get_type_info()

        # Insert handler in the correct priority position
        inserted = False
        for i, existing_handler in enumerate(self._handlers):
            existing_info = existing_handler.get_type_info()
            if type_info["priority"] < existing_info["priority"]:
                self._handlers.insert(i, handler)
                inserted = True
                break

        if not inserted:
            self._handlers.append(handler)

    def get_ordered_handlers(self) -> list[ComparisonCapable | UserComparisonType]:
        """Get handlers ordered by priority."""
        return self._handlers.copy()

    def find_handler(
        self, left_raw: OperandType, right_raw: OperandType, op: str
    ) -> ComparisonCapable | UserComparisonType | None:
        """Find the first handler that can handle the given comparison."""
        for handler in self._handlers:
            if handler.can_handle_raw(left_raw, right_raw, op):
                return handler
        return None

    def get_handler_info(self) -> list[ComparisonTypeInfo]:
        """Get type information for all registered handlers."""
        return [handler.get_type_info() for handler in self._handlers]


# Global registry instance
_registry: ExtensibleComparisonRegistry | None = None


def get_extensible_registry() -> ExtensibleComparisonRegistry:
    """Get the global extensible comparison registry."""
    global _registry  # pylint: disable=global-statement
    if _registry is None:
        _registry = ExtensibleComparisonRegistry()
    return _registry


def register_user_comparison_type(handler: UserComparisonType) -> None:
    """Register a user-defined comparison type with the global registry."""
    registry = get_extensible_registry()
    registry.register_comparison_type(handler)
