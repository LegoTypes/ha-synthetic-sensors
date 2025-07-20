"""Factory for creating and managing formula evaluation handlers."""

import logging

from .base_handler import FormulaHandler
from .boolean_handler import BooleanHandler
from .numeric_handler import NumericHandler
from .string_handler import StringHandler

_LOGGER = logging.getLogger(__name__)


class HandlerFactory:
    """Factory for creating and managing formula evaluation handlers."""

    def __init__(self) -> None:
        """Initialize the handler factory with default handlers."""
        self._handlers: dict[str, FormulaHandler] = {}
        self._handler_types: dict[str, type[FormulaHandler]] = {}

        # Register default handlers
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register the default set of handlers."""
        self.register_handler("string", StringHandler())
        self.register_handler("numeric", NumericHandler())
        self.register_handler("boolean", BooleanHandler())

    def register_handler(self, name: str, handler: FormulaHandler) -> None:
        """Register a handler with the factory."""
        self._handlers[name] = handler
        _LOGGER.debug("Registered handler '%s': %s", name, handler.get_handler_name())

    def register_handler_type(self, name: str, handler_type: type[FormulaHandler]) -> None:
        """Register a handler type for lazy instantiation."""
        self._handler_types[name] = handler_type
        _LOGGER.debug("Registered handler type '%s': %s", name, handler_type.__name__)

    def get_handler(self, name: str) -> FormulaHandler | None:
        """Get a handler by name."""
        # First check for instantiated handlers
        if name in self._handlers:
            return self._handlers[name]

        # Then check for handler types and instantiate
        if name in self._handler_types:
            handler = self._handler_types[name]()
            self._handlers[name] = handler  # Cache the instance
            return handler

        return None

    def get_handler_for_formula(self, formula: str) -> FormulaHandler | None:
        """Get the appropriate handler for a given formula."""
        # Try each handler to see which one can handle this formula
        for handler in self._handlers.values():
            if handler.can_handle(formula):
                return handler

        # If no handler can handle it, return the numeric handler as default
        return self.get_handler("numeric")

    def get_all_handlers(self) -> dict[str, FormulaHandler]:
        """Get all registered handlers."""
        return self._handlers.copy()

    def clear_handlers(self) -> None:
        """Clear all registered handlers."""
        self._handlers.clear()
        self._handler_types.clear()
        self._register_default_handlers()
