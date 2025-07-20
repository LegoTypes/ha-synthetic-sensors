"""Numeric formula handler for processing mathematical formulas."""

import logging

from simpleeval import SimpleEval

from ..math_functions import MathFunctions
from ..type_definitions import ContextValue
from .base_handler import FormulaHandler

_LOGGER = logging.getLogger(__name__)


class NumericHandler(FormulaHandler):
    """Handler for numeric formulas in the compiler-like evaluation system."""

    def __init__(self) -> None:
        """Initialize the numeric handler with math functions."""
        self._math_functions = MathFunctions.get_builtin_functions()

    def can_handle(self, formula: str) -> bool:
        """
        Determine if a formula should be processed as a numeric formula.

        Numeric formulas are the default case - any formula that doesn't match
        string or boolean patterns is treated as numeric.
        """
        # Numeric handler is the default - it handles everything that isn't explicitly
        # string or boolean. This allows for maximum flexibility.
        return True

    def evaluate(self, formula: str, context: dict[str, ContextValue] | None = None) -> float:
        """
        NUMERIC FORMULA HANDLER: Process mathematical formulas using SimpleEval.

        This method handles all numeric computations using the SimpleEval library,
        which provides safe mathematical expression evaluation without the security
        risks of Python's built-in eval().

        Supports:
        - Basic arithmetic: +, -, *, /, **, %
        - Mathematical functions: sin, cos, tan, log, exp, sqrt, etc.
        - Logical operations: and, or, not
        - Comparison operators: <, >, <=, >=, ==, !=
        - Conditional expressions: value if condition else alternative

        This separation allows for clear distinction between numeric and string processing,
        making the codebase more maintainable and extensible.
        """
        try:
            evaluator = SimpleEval(functions=self._math_functions)
            evaluator.names = context or {}

            result = evaluator.eval(formula)

            # Validate numeric result
            if not isinstance(result, (int, float)):
                raise ValueError(f"Numeric formula result must be numeric, got {type(result).__name__}: {result}")

            return float(result)
        except Exception as e:
            _LOGGER.warning("Numeric formula evaluation failed for '%s': %s", formula, e)
            raise
