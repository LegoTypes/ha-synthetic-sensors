"""Numeric formula handler for processing mathematical formulas."""

import logging
from typing import Any

from ..formula_compilation_cache import FormulaCompilationCache
from ..type_definitions import ContextValue
from .base_handler import FormulaHandler

_LOGGER = logging.getLogger(__name__)


class NumericHandler(FormulaHandler):
    """Handler for numeric formulas in the compiler-like evaluation system."""

    def __init__(self) -> None:
        """Initialize the numeric handler with formula compilation cache."""
        self._compilation_cache = FormulaCompilationCache()

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
        NUMERIC FORMULA HANDLER: Process mathematical formulas using cached compiled expressions.

        This method uses a two-tier caching approach:
        1. Formula Compilation Cache: Caches compiled SimpleEval instances to avoid re-parsing
        2. Result Cache: Caches evaluation results (handled by evaluator layer)

        This provides significant performance improvement by avoiding formula re-parsing
        on every evaluation, while maintaining safety through SimpleEval.

        Supports:
        - Basic arithmetic: +, -, *, /, **, %
        - Mathematical functions: sin, cos, tan, log, exp, sqrt, etc.
        - Logical operations: and, or, not
        - Comparison operators: <, >, <=, >=, ==, !=
        - Conditional expressions: value if condition else alternative
        """
        try:
            # Get compiled formula from cache (or compile if not cached)
            compiled_formula = self._compilation_cache.get_compiled_formula(formula)

            # Evaluate using the pre-compiled formula
            result = compiled_formula.evaluate(context or {})

            # Validate numeric result
            if not isinstance(result, (int, float)):
                raise ValueError(f"Numeric formula result must be numeric, got {type(result).__name__}: {result}")

            return float(result)
        except Exception as e:
            _LOGGER.warning("Numeric formula evaluation failed for '%s': %s", formula, e)
            raise

    def clear_compiled_formulas(self) -> None:
        """Clear all compiled formulas from cache.

        This should be called when formulas change or during configuration reload.
        """
        self._compilation_cache.clear()

    def get_compilation_cache_stats(self) -> dict[str, Any]:
        """Get formula compilation cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        return self._compilation_cache.get_statistics()
