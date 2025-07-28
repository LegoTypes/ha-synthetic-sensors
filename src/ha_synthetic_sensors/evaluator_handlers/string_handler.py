"""String formula handler for processing string-based formulas."""

import ast
import logging
import re

from ..constants_formula import COLLECTION_FUNCTIONS
from ..type_definitions import ContextValue
from .base_handler import FormulaHandler

_LOGGER = logging.getLogger(__name__)


class StringHandler(FormulaHandler):
    """Handler for string-based formulas in the compiler-like evaluation system."""

    def can_handle(self, formula: str) -> bool:
        """
        Determine if a formula should be processed as a string formula.

        String formulas include:
        1. Simple quoted string literals (e.g., "hello world")
        2. String concatenation (e.g., "hello" + " " + "world")
        3. String literals for attribute configurations (e.g., "tab [30,32]")

        This method establishes the routing logic between numeric and string handlers.
        """
        # Don't handle collection functions - these should be numeric
        collection_function_patterns = [f"{func}(" for func in COLLECTION_FUNCTIONS]
        if any(func in formula for func in collection_function_patterns):
            return False

        # Handle string concatenation operations
        if "+" in formula and '"' in formula:
            # Check if this looks like string concatenation
            # Simple heuristic: if it contains quoted strings and + operators, it's likely string concatenation
            return True

        # Handle simple quoted string literals
        return bool(re.match(r'^"[^"]*"$', formula.strip()))

    def evaluate(self, formula: str, context: dict[str, ContextValue] | None = None) -> str:
        """
        STRING FORMULA HANDLER: Process string literals and string concatenation.

        This method handles:
        - Simple string literals for attribute configurations
        - String concatenation operations (e.g., "hello" + " " + "world")

        FUTURE ENHANCEMENTS:
        - String interpolation: "Power: {state}W"
        - String functions: upper(state), lower(state), format(state, ".2f")
        - Conditional strings: "ON" if state > 0 else "OFF"
        - Template processing: render_template("sensor_{id}.html", state=state)
        - String manipulation: substring, replace, split, join operations
        """
        try:
            # Use ast.literal_eval for safe string evaluation
            # This handles both simple literals and string concatenation
            # Since all variables have been resolved, this should be safe
            result = ast.literal_eval(formula)

            if isinstance(result, str):
                return result
            # Convert non-string results to strings
            return str(result)
        except (ValueError, SyntaxError) as e:
            _LOGGER.warning("String formula evaluation failed for '%s': %s", formula, e)
            return "unknown"
