"""Factory for creating and managing formula evaluation handlers."""

from collections.abc import Callable
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

from ..constants_handlers import (
    ERROR_NO_HANDLER_FOR_FORMULA,
    HANDLER_TYPE_BOOLEAN,
    HANDLER_TYPE_DATE,
    HANDLER_TYPE_METADATA,
    HANDLER_TYPE_NUMERIC,
    HANDLER_TYPE_STRING,
)
from ..type_definitions import ContextValue
from .base_handler import FormulaHandler

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class HandlerFactory:
    """Factory for creating and managing formula evaluation handlers."""

    def __init__(
        self,
        expression_evaluator: Callable[[str, dict[str, ContextValue] | None], Any] | None = None,
        hass: HomeAssistant | None = None,
    ) -> None:
        """Initialize the handler factory.

        Args:
            expression_evaluator: Callback for handlers to delegate complex expression evaluation
            hass: Home Assistant instance for handlers that need access to entity states
        """
        self._handlers: dict[str, FormulaHandler] = {}
        self._handler_types: dict[str, type[FormulaHandler]] = {}
        self._expression_evaluator = expression_evaluator
        self._hass = hass

        # Register default handler types for lazy instantiation
        self._register_default_handler_types()

    def _register_default_handler_types(self) -> None:
        """Register the default set of handler types for lazy instantiation."""
        # WFF: The nature of the handler factory warrants this import-outside-toplevel
        # Import handlers lazily to avoid circular imports
        # pylint: disable=import-outside-toplevel
        from .boolean_handler import BooleanHandler
        from .date_handler import DateHandler
        from .metadata_handler import MetadataHandler
        from .numeric_handler import NumericHandler
        from .string_handler import StringHandler

        self.register_handler_type(HANDLER_TYPE_METADATA, MetadataHandler)  # First priority for metadata() calls
        self.register_handler_type(HANDLER_TYPE_STRING, StringHandler)
        self.register_handler_type(HANDLER_TYPE_NUMERIC, NumericHandler)
        self.register_handler_type(HANDLER_TYPE_BOOLEAN, BooleanHandler)
        self.register_handler_type(HANDLER_TYPE_DATE, DateHandler)

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
            handler = self._create_handler_instance(name)
            if handler:
                self._handlers[name] = handler  # Cache the instance
                return handler

        return None

    def _create_handler_instance(self, name: str) -> FormulaHandler | None:
        """Create a handler instance with proper dependency injection."""
        if name not in self._handler_types:
            return None
        handler_type = self._handler_types[name]

        # Check if this is the metadata handler that needs hass instance
        if name == HANDLER_TYPE_METADATA:
            return handler_type(expression_evaluator=self._expression_evaluator, hass=self._hass)

        # All other handlers accept expression_evaluator as a standard parameter
        return handler_type(expression_evaluator=self._expression_evaluator)

    def get_handler_for_formula(self, formula: str) -> FormulaHandler | None:
        """Get the appropriate handler for a given formula."""
        # Try each instantiated handler first
        for handler in self._handlers.values():
            if handler.can_handle(formula):
                return handler

        # If no instantiated handler can handle it, try instantiating other registered types
        for name, _ in self._handler_types.items():
            if name not in self._handlers:
                # Instantiate the handler to test if it can handle this formula
                maybe_handler = self._create_handler_instance(name)
                if maybe_handler is not None and maybe_handler.can_handle(formula):
                    # Cache it since it can handle this type of formula
                    # Now we know maybe_handler is definitely not None
                    valid_handler: FormulaHandler = maybe_handler
                    self._handlers[name] = valid_handler
                    return valid_handler

        # If no handler can handle it, this indicates a routing problem
        # The formula should have been routable to at least one handler
        raise ValueError(ERROR_NO_HANDLER_FOR_FORMULA.format(formula=formula))

    def get_all_handlers(self) -> dict[str, FormulaHandler]:
        """Get all registered handlers."""
        return self._handlers.copy()

    def clear_handlers(self) -> None:
        """Clear all registered handlers."""
        self._handlers.clear()
        self._handler_types.clear()
        self._register_default_handler_types()
