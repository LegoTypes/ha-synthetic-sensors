"""Boolean formula handler for processing logical expressions."""

import logging
import re

from ..type_definitions import ContextValue
from .base_handler import FormulaHandler
from .numeric_handler import NumericHandler

_LOGGER = logging.getLogger(__name__)


class BooleanHandler(FormulaHandler):
    """Handler for boolean formulas in the compiler-like evaluation system."""

    def can_handle(self, formula: str) -> bool:
        """
        Determine if a formula should be processed as a boolean formula.

        Boolean formulas are identified by:
        1. Comparison operations: <, >, <=, >=, ==, !=
        2. Logical operations: and, or, not
        3. Boolean literals: True, False
        4. Boolean functions: is_on(), is_off(), etc.
        """
        # Check for comparison operators
        if re.search(r"\b(and|or|not)\b", formula, re.IGNORECASE):
            return True

        # Check for comparison operators
        if re.search(r"[<>=!]=?", formula):
            return True

        # Check for boolean literals
        if re.search(r"\b(True|False)\b", formula):
            return True

            # Check for boolean functions
        return re.search(r"\b(is_on|is_off|is_home|is_away)\b", formula, re.IGNORECASE) is not None

    def evaluate(self, formula: str, context: dict[str, ContextValue] | None = None) -> bool:
        """
        BOOLEAN FORMULA HANDLER: Process logical expressions.

        This method handles boolean logic and comparisons using SimpleEval,
        providing safe evaluation of logical expressions.

        Supports:
        - Comparison operations: <, >, <=, >=, ==, !=
        - Logical operations: and, or, not
        - Boolean literals: True, False
        - Boolean functions: is_on(), is_off(), etc.
        """
        try:
            # For now, delegate to numeric handler since SimpleEval handles boolean logic
            # Future: Implement dedicated boolean evaluation with boolean-specific functions
            numeric_handler = NumericHandler()
            result = numeric_handler.evaluate(formula, context)

            # Convert result to boolean
            if isinstance(result, bool):
                return result
            if isinstance(result, (int, float)):
                return bool(result)
            raise ValueError(f"Boolean formula result must be boolean, got {type(result).__name__}: {result}")

        except Exception as e:
            _LOGGER.warning("Boolean formula evaluation failed for '%s': %s", formula, e)
            raise
