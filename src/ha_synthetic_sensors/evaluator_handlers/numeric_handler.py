"""Numeric formula handler for processing mathematical formulas."""

from collections.abc import Callable
import logging
from typing import Any

from ..enhanced_formula_evaluation import EnhancedSimpleEvalHelper
from ..formula_compilation_cache import FormulaCompilationCache
from ..formula_router import EvaluatorType, FormulaRouter
from ..type_analyzer import TypeAnalyzer
from ..type_definitions import ContextValue, ReferenceValue
from .base_handler import FormulaHandler

_LOGGER = logging.getLogger(__name__)


class NumericHandler(FormulaHandler):
    """Handler for numeric formulas in the compiler-like evaluation system."""

    _enhanced_helper: EnhancedSimpleEvalHelper | None

    def __init__(
        self,
        expression_evaluator: Callable[[str, dict[str, ContextValue] | None], Any] | None = None,
        use_enhanced_evaluation: bool = False,
    ) -> None:
        """Initialize the numeric handler with formula compilation cache.

        Args:
            expression_evaluator: Optional custom expression evaluator
            use_enhanced_evaluation: If True, use enhanced SimpleEval for fast-path evaluation
        """
        super().__init__(expression_evaluator)
        self._use_enhanced_evaluation = use_enhanced_evaluation

        # Initialize enhanced evaluation helper if requested
        if use_enhanced_evaluation:
            self._enhanced_helper = EnhancedSimpleEvalHelper()
            # Use enhanced compilation cache
            self._compilation_cache = FormulaCompilationCache(use_enhanced_functions=True)
        else:
            self._enhanced_helper = None
            # Use standard compilation cache
            self._compilation_cache = FormulaCompilationCache(use_enhanced_functions=False)

        self._type_analyzer = TypeAnalyzer()

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

        This method supports both enhanced evaluation (Phase 2) and standard evaluation:

        Enhanced Mode (use_enhanced_evaluation=True):
        - Tries enhanced SimpleEval first for fast-path evaluation
        - Supports duration arithmetic: minutes(5) / minutes(1) -> 5.0
        - Falls back to standard compilation cache if enhanced fails

        Standard Mode (use_enhanced_evaluation=False):
        - Uses traditional compilation cache approach
        - Maintains full backward compatibility

        This provides significant performance improvement by avoiding formula re-parsing
        on every evaluation, while maintaining safety through SimpleEval.

        Supports:
        - Basic arithmetic: +, -, *, /, **, %
        - Mathematical functions: sin, cos, tan, log, exp, sqrt, etc.
        - Logical operations: and, or, not
        - Comparison operators: <, >, <=, >=, ==, !=
        - Conditional expressions: value if condition else alternative
        - Enhanced: Duration functions and arithmetic (when enhanced mode enabled)
        """
        try:
            # Extract values from ReferenceValue objects for evaluation
            numeric_context = self._extract_values_for_numeric_evaluation(context or {})

            # Enhanced evaluation path (Phase 2)
            if self._use_enhanced_evaluation and self._enhanced_helper:
                # Try enhanced SimpleEval first
                success, result = self._enhanced_helper.try_enhanced_eval(formula, numeric_context)
                if success:
                    # Enhanced evaluation succeeded
                    if isinstance(result, int | float):
                        _LOGGER.debug("Enhanced evaluation SUCCESS (numeric): %s -> %s", formula, result)
                        return float(result)
                    if hasattr(result, "total_seconds") and not isinstance(result, int | float):  # timedelta object
                        # This means we got a timedelta object, which NumericHandler shouldn't handle
                        # This should be routed to DurationHandler instead
                        _LOGGER.warning("Enhanced evaluation returned timedelta for NumericHandler: %s -> %s", formula, result)
                        # Fall through to standard evaluation which will fail and route correctly
                    else:
                        # Enhanced evaluation returned non-numeric result - routing error
                        _LOGGER.warning(
                            "Enhanced evaluation routing error: %s -> %s (%s)", formula, result, type(result).__name__
                        )
                        # Fall through to standard evaluation

                _LOGGER.debug("Enhanced evaluation FALLBACK to standard for: %s", formula)

            # Standard evaluation path (always available as fallback)
            compiled_formula = self._compilation_cache.get_compiled_formula(formula)
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

        Uses the type analyzer to convert string values like '30' to numeric values like 30.
        This is the proper integration point for the type analyzer system.

        Args:
            context: EvaluationContext containing ReferenceValue objects

        Returns:
            Dictionary with variable names mapped to their properly typed values for SimpleEval
        """
        numeric_context: dict[str, Any] = {}

        for key, value in context.items():
            if isinstance(value, ReferenceValue):
                # Extract the value from ReferenceValue
                raw_value = value.value

                # Handle None values (missing/unavailable entities)
                if raw_value is None:
                    numeric_context[key] = None
                    _LOGGER.debug("NumericHandler: Kept %s=None (unavailable)", key)
                    continue

                # Use type analyzer to convert to appropriate type (e.g., '30' -> 30)
                can_reduce, numeric_value = self._type_analyzer.try_reduce_to_numeric(raw_value)
                if can_reduce:
                    # Successfully converted to numeric
                    numeric_context[key] = numeric_value
                    _LOGGER.debug("NumericHandler: Converted %s='%s' -> %s (numeric)", key, raw_value, numeric_value)
                else:
                    # Keep original value if can't convert to numeric
                    numeric_context[key] = raw_value
                    _LOGGER.debug("NumericHandler: Kept %s='%s' (non-numeric)", key, raw_value)
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
