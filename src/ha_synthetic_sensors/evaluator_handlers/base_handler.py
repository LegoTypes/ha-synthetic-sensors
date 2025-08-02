"""Base handler interface for formula evaluation."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from ..type_definitions import ContextValue


class FormulaHandler(ABC):
    """Base interface for formula handlers in the compiler-like evaluation system."""

    def __init__(
        self, expression_evaluator: Callable[[str, dict[str, ContextValue] | None], ContextValue] | None = None
    ) -> None:
        """Initialize the handler with optional expression evaluator.

        Args:
            expression_evaluator: Callback for handlers to delegate complex expression evaluation
        """
        self._expression_evaluator = expression_evaluator

    @abstractmethod
    def can_handle(self, formula: str) -> bool:
        """Determine if this handler can process the given formula."""

    @abstractmethod
    def evaluate(self, formula: str, context: dict[str, ContextValue] | None = None) -> Any:
        """Evaluate the formula and return the result."""

    def get_handler_name(self) -> str:
        """Get the name of this handler for logging and debugging."""
        return self.__class__.__name__
