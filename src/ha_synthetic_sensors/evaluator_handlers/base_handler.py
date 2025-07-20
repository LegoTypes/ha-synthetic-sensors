"""Base handler interface for formula evaluation."""

from abc import ABC, abstractmethod
from typing import Any

from ..type_definitions import ContextValue


class FormulaHandler(ABC):
    """Base interface for formula handlers in the compiler-like evaluation system."""

    @abstractmethod
    def can_handle(self, formula: str) -> bool:
        """Determine if this handler can process the given formula."""

    @abstractmethod
    def evaluate(self, formula: str, context: dict[str, ContextValue] | None = None) -> Any:
        """Evaluate the formula and return the result."""

    def get_handler_name(self) -> str:
        """Get the name of this handler for logging and debugging."""
        return self.__class__.__name__
