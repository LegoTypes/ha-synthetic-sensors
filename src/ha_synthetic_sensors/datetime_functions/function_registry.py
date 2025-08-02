"""DateTime function registry for managing and routing function calls."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .date_functions import DateFunctions
from .duration_functions import DurationFunctions
from .protocol import DateTimeFunction
from .timezone_functions import TimezoneFunctions


class DateTimeFunctionRegistry:
    """Registry for managing datetime function handlers and routing function calls."""

    def __init__(self) -> None:
        """Initialize the registry with default handlers."""
        self._handlers: list[DateTimeFunction] = []
        self._function_cache: dict[str, DateTimeFunction] = {}
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register the default datetime function handlers."""
        self.register_handler(TimezoneFunctions())
        self.register_handler(DateFunctions())
        self.register_handler(DurationFunctions())

    def register_handler(self, handler: DateTimeFunction) -> None:
        """Register a datetime function handler.

        Args:
            handler: The datetime function handler to register
        """
        self._handlers.append(handler)
        # Update cache with supported functions
        for function_name in handler.get_supported_functions():
            self._function_cache[function_name] = handler

    def can_handle_function(self, function_name: str) -> bool:
        """Check if any registered handler can handle the given function.

        Args:
            function_name: The name of the function to check

        Returns:
            True if any handler can process the function
        """
        return function_name in self._function_cache

    def evaluate_function(self, function_name: str, args: list[Any] | None = None) -> str:
        """Evaluate a datetime function using the appropriate handler.

        Args:
            function_name: The name of the function to evaluate
            args: Optional arguments for the function

        Returns:
            ISO datetime string result

        Raises:
            ValueError: If no handler can process the function
        """
        handler = self._function_cache.get(function_name)
        if handler is None:
            supported = sorted(self._function_cache.keys())
            raise ValueError(
                f"No handler found for datetime function '{function_name}'. Supported functions: {', '.join(supported)}"
            )

        return handler.evaluate_function(function_name, args)

    def get_all_functions(self) -> dict[str, Callable[..., Any]]:
        """Get all registered datetime functions as callable functions.

        This creates a dictionary compatible with the existing MathFunctions approach,
        allowing for gradual migration.

        Returns:
            Dictionary mapping function names to callable functions
        """
        functions = {}
        for function_name in self._function_cache:
            # Create a closure that captures the function name
            def make_function(name: str) -> Callable[..., Any]:
                def datetime_function(*args: Any) -> str:
                    # Convert args tuple to list, handle no args case
                    arg_list = list(args) if args else None
                    return self.evaluate_function(name, arg_list)

                return datetime_function

            functions[function_name] = make_function(function_name)

        return functions

    def get_supported_functions(self) -> set[str]:
        """Get all supported function names.

        Returns:
            Set of all supported function names
        """
        return set(self._function_cache.keys())

    def get_handlers_info(self) -> list[dict[str, Any]]:
        """Get information about all registered handlers.

        Returns:
            List of handler information dictionaries
        """
        return [handler.get_function_info() for handler in self._handlers]

    def clear_handlers(self) -> None:
        """Clear all registered handlers and reset to defaults.

        This is useful for testing or when reconfiguring the registry.
        """
        self._handlers.clear()
        self._function_cache.clear()
        self._register_default_handlers()


# Global registry instance
_global_registry = DateTimeFunctionRegistry()


def get_datetime_function_registry() -> DateTimeFunctionRegistry:
    """Get the global datetime function registry instance.

    Returns:
        The global DateTimeFunctionRegistry instance
    """
    return _global_registry


def register_datetime_handler(handler: DateTimeFunction) -> None:
    """Register a datetime function handler with the global registry.

    Args:
        handler: The datetime function handler to register
    """
    _global_registry.register_handler(handler)


def get_datetime_functions() -> dict[str, Callable[..., Any]]:
    """Get all datetime functions as callable functions.

    This is the main interface for integrating with the existing MathFunctions system.

    Returns:
        Dictionary mapping function names to callable functions
    """
    return _global_registry.get_all_functions()
