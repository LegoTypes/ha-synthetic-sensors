"""Numeric formula handler for processing mathematical formulas."""

from collections.abc import Callable
import logging
from typing import Any

from ..formula_compilation_cache import FormulaCompilationCache
from ..formula_router import EvaluatorType, FormulaRouter
from ..type_definitions import ContextValue, ReferenceValue
from .base_handler import FormulaHandler

_LOGGER = logging.getLogger(__name__)


class NumericHandler(FormulaHandler):
    """Handler for numeric formulas in the compiler-like evaluation system."""

    def __init__(self, expression_evaluator: Callable[[str, dict[str, ContextValue] | None], Any] | None = None) -> None:
        """Initialize the numeric handler with formula compilation cache."""
        super().__init__(expression_evaluator)
        self._compilation_cache = FormulaCompilationCache()

    def can_handle(self, formula: str) -> bool:
        """
        Determine if a formula should be processed as a numeric formula.

        Only handles formulas that are actually numeric in nature.
        """
        # Use FormulaRouter to determine if this should be handled as numeric
        router = FormulaRouter()
        routing_result = router.route_formula(formula)
        return routing_result.evaluator_type == EvaluatorType.NUMERIC

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

            # Extract values from ReferenceValue objects for numeric evaluation
            numeric_context = self._extract_values_for_numeric_evaluation(context or {})

            # Evaluate using the pre-compiled formula
            result = compiled_formula.evaluate(numeric_context)

            # Validate numeric result - NumericHandler should ONLY handle numeric formulas
            if isinstance(result, int | float):
                return float(result)

            # If we get non-numeric results, this indicates a ROUTING ERROR
            # The formula should have been sent to the appropriate handler (string/boolean)
            raise ValueError(
                f"ROUTING ERROR: NumericHandler received non-numeric result. Formula '{formula}' -> {type(result).__name__}: {result}. This should be routed to a different handler."
            )
        except Exception as e:
            _LOGGER.warning("Numeric formula evaluation failed for '%s': %s", formula, e)
            raise

    def _extract_values_for_numeric_evaluation(self, context: dict[str, ContextValue]) -> dict[str, Any]:
        """Extract values from ReferenceValue objects for numeric evaluation.

        Args:
            context: EvaluationContext containing ReferenceValue objects

        Returns:
            Dictionary with variable names mapped to their values for SimpleEval
        """
        numeric_context: dict[str, Any] = {}

        for key, value in context.items():
            if isinstance(value, ReferenceValue):
                # Extract the value from ReferenceValue for numeric computation
                numeric_context[key] = value.value
                _LOGGER.debug("NumericHandler: Extracted %s -> %s (from ReferenceValue)", key, value.value)
            else:
                # Keep other values as-is (functions, constants, etc.)
                numeric_context[key] = value

        return numeric_context

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
