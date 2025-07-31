"""Base datetime function handler following the established handler pattern."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .protocol import DateTimeFunction, DateTimeFunctionProvider


class BaseDateTimeFunction(ABC, DateTimeFunction, DateTimeFunctionProvider):
    """Base class for datetime function handlers with common functionality."""

    def __init__(self) -> None:
        """Initialize the datetime function handler."""
        self._supported_functions = self._initialize_supported_functions()

    @abstractmethod
    def _initialize_supported_functions(self) -> set[str]:
        """Initialize the set of supported function names.

        Returns:
            Set of function names this handler supports
        """

    def can_handle_function(self, function_name: str) -> bool:
        """Check if this function handler can handle the given function name.

        Args:
            function_name: The name of the function to check

        Returns:
            True if this handler can process the function
        """
        return function_name in self._supported_functions

    def get_supported_functions(self) -> set[str]:
        """Get the set of function names this handler supports.

        Returns:
            Set of supported function names
        """
        return self._supported_functions.copy()

    def get_function_info(self) -> dict[str, Any]:
        """Get information about the datetime functions provided.

        Returns:
            Dictionary containing function metadata
        """
        return {
            "handler_name": self.__class__.__name__,
            "supported_functions": list(self._supported_functions),
            "return_type": "str",
            "return_format": "ISO datetime string",
        }

    @abstractmethod
    def evaluate_function(self, function_name: str, args: list[Any] | None = None) -> str:
        """Evaluate the datetime function and return an ISO datetime string.

        Args:
            function_name: The name of the function to evaluate
            args: Optional arguments for the function

        Returns:
            ISO datetime string result

        Raises:
            ValueError: If the function is not supported or arguments are invalid
        """

    def _validate_function_name(self, function_name: str) -> None:
        """Validate that the function name is supported.

        Args:
            function_name: The function name to validate

        Raises:
            ValueError: If the function is not supported
        """
        if not self.can_handle_function(function_name):
            supported = ", ".join(sorted(self._supported_functions))
            raise ValueError(
                f"Function '{function_name}' is not supported by {self.__class__.__name__}. Supported functions: {supported}"
            )

    def _validate_no_arguments(self, function_name: str, args: list[Any] | None) -> None:
        """Validate that no arguments were provided for functions that don't accept them.

        Args:
            function_name: The function name
            args: The arguments to validate

        Raises:
            ValueError: If arguments were provided when none are expected
        """
        if args:
            raise ValueError(f"Function '{function_name}' does not accept arguments, but {len(args)} were provided")
