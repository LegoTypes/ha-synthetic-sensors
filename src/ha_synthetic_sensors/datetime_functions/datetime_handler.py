"""DateTime handler for the evaluator system."""

from __future__ import annotations

from collections.abc import Callable
import re
from typing import Any

from ..evaluator_handlers.base_handler import FormulaHandler
from ..hierarchical_context_dict import HierarchicalContextDict
from ..regex_helper import create_datetime_function_pattern
from .function_registry import get_datetime_function_registry


class DateTimeHandler(FormulaHandler):
    """Handler for datetime functions in the formula evaluation system."""

    def __init__(self, expression_evaluator: Callable[[str, HierarchicalContextDict], Any] | None = None) -> None:
        """Initialize the datetime handler."""
        super().__init__(expression_evaluator)
        self._registry = get_datetime_function_registry()
        # Use centralized datetime function pattern from regex helper

        self._function_pattern = create_datetime_function_pattern()

    def can_handle(self, formula: str) -> bool:
        """Determine if this handler can process the given formula.

        Args:
            formula: The formula to check

        Returns:
            True if the formula contains datetime function calls
        """
        # Find all function calls in the formula
        function_calls = self._function_pattern.findall(formula)

        # Check if any of the function calls are datetime functions
        return any(self._registry.can_handle_function(func_name) for func_name in function_calls)

    def evaluate(self, formula: str, context: HierarchicalContextDict) -> Any:
        """Evaluate the formula with datetime function calls.

        This handler processes datetime function calls within formulas by replacing them
        with their evaluated results, then returns the processed formula for further
        evaluation by other handlers.

        Args:
            formula: The formula containing datetime function calls
            context: Optional evaluation context (not used for datetime functions)

        Returns:
            The formula with datetime function calls replaced by their ISO string results

        Raises:
            ValueError: If a datetime function cannot be evaluated
        """
        processed_formula = formula

        # Find all function calls and replace datetime functions with their results
        def replace_datetime_function(match: re.Match[str]) -> str:
            func_name = match.group(1)

            if self._registry.can_handle_function(func_name):
                # Evaluate the datetime function and return as quoted string
                result = self._registry.evaluate_function(func_name)
                return f'"{result}"'
            # Not a datetime function, leave as-is
            return match.group(0)

        processed_formula = self._function_pattern.sub(replace_datetime_function, processed_formula)

        return processed_formula

    def get_supported_functions(self) -> set[str]:
        """Get all supported datetime function names.

        Returns:
            Set of supported datetime function names
        """
        return self._registry.get_supported_functions()

    def get_handler_info(self) -> dict[str, Any]:
        """Get information about this handler and its capabilities.

        Returns:
            Dictionary containing handler information
        """
        return {
            "handler_name": self.get_handler_name(),
            "supported_functions": sorted(self.get_supported_functions()),
            "function_handlers": self._registry.get_handlers_info(),
            "processing_type": "function_replacement",
            "output_format": "ISO datetime strings as quoted literals",
        }
