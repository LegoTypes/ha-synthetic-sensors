"""DateTime function protocols and interfaces."""

from __future__ import annotations

from typing import Any, Protocol


class DateTimeFunction(Protocol):
    """Protocol for datetime function implementations."""

    def can_handle_function(self, function_name: str) -> bool:
        """Check if this function handler can handle the given function name.

        Args:
            function_name: The name of the function to check

        Returns:
            True if this handler can process the function
        """

    def evaluate_function(self, function_name: str, args: list[Any] | None = None) -> str:
        """Evaluate the datetime function and return an ISO datetime string.

        Args:
            function_name: The name of the function to evaluate
            args: Optional arguments for the function (most datetime functions take no args)

        Returns:
            ISO datetime string result

        Raises:
            ValueError: If the function is not supported or arguments are invalid
        """

    def get_supported_functions(self) -> set[str]:
        """Get the set of function names this handler supports.

        Returns:
            Set of supported function names
        """

    def get_function_info(self) -> dict[str, Any]:
        """Get information about the datetime functions provided.

        Returns:
            Dictionary containing function metadata
        """


class DateTimeFunctionProvider(Protocol):
    """Protocol for objects that provide datetime function metadata."""

    def get_function_info(self) -> dict[str, Any]:
        """Get information about the datetime functions provided.

        Returns:
            Dictionary containing function metadata
        """
