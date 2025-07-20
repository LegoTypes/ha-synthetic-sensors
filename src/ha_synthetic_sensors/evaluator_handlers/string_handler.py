"""String formula handler for processing string-based formulas."""

import ast
import logging
import re

from ..type_definitions import ContextValue
from .base_handler import FormulaHandler

_LOGGER = logging.getLogger(__name__)


class StringHandler(FormulaHandler):
    """Handler for string-based formulas in the compiler-like evaluation system."""

    def can_handle(self, formula: str) -> bool:
        """
        Determine if a formula should be processed as a string formula.

        String formulas are currently limited to:
        1. Simple quoted string literals (e.g., "hello world")
        2. String literals for attribute configurations (e.g., "tab [30,32]")

        This method establishes the routing logic between numeric and string handlers.
        Future enhancements will support string concatenation and evaluation.
        """
        # Don't handle collection functions - these should be numeric
        collection_functions = ["sum(", "avg(", "max(", "min(", "count("]
        if any(func in formula for func in collection_functions):
            return False

        # Don't handle string operations - these will be supported in future
        if "+" in formula and '"' in formula:
            return False

        # Only handle simple quoted string literals
        if re.match(r'^"[^"]*"$', formula.strip()):
            return True

        return False

    def evaluate(self, formula: str, context: dict[str, ContextValue] | None = None) -> str:
        """
        STRING FORMULA HANDLER: Process string literals for attributes.

        This method handles simple string literals for attribute configurations.
        Currently limited to string literals only.

        FUTURE ENHANCEMENTS:
        - String interpolation: "Power: {state}W"
        - String functions: upper(state), lower(state), format(state, ".2f")
        - Conditional strings: "ON" if state > 0 else "OFF"
        - Template processing: render_template("sensor_{id}.html", state=state)
        - String manipulation: substring, replace, split, join operations
        - String concatenation: "hello" + " " + "world"
        """
        try:
            # Use ast.literal_eval for safe string evaluation
            # This is safe for resolved formulas since all variables have been substituted
            result = ast.literal_eval(formula)

            if isinstance(result, str):
                return result
            # Convert non-string results to strings
            return str(result)
        except (ValueError, SyntaxError) as e:
            _LOGGER.warning("String formula evaluation failed for '%s': %s", formula, e)
            return "unknown"
