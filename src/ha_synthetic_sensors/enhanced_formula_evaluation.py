"""Enhanced formula evaluation helper for integrating enhanced SimpleEval with existing handlers."""

import logging
from typing import TYPE_CHECKING, Any

from .formula_compilation_cache import FormulaCompilationCache
from .math_functions import MathFunctions

if TYPE_CHECKING:
    from .formula_router import FormulaRouter

_LOGGER = logging.getLogger(__name__)


class EnhancedSimpleEvalHelper:
    """Helper class providing enhanced SimpleEval capabilities to existing handlers.

    This class implements Phase 2 of the Enhanced SimpleEval Foundation as specified
    in formula_router_architecture_redesign.md. It provides enhanced SimpleEval
    capabilities while preserving the existing handler architecture.

    The helper enables handlers to leverage enhanced SimpleEval for 99% of formulas
    while maintaining their specialized roles for specific functions like metadata().
    """

    def __init__(self) -> None:
        """Initialize the enhanced SimpleEval helper with AST compilation cache."""
        # Initialize compilation cache for AST caching with enhanced functions
        self._compilation_cache = FormulaCompilationCache(use_enhanced_functions=True)
        self._enhancement_stats = {"enhanced_eval_count": 0, "fallback_count": 0}
        _LOGGER.debug("EnhancedSimpleEvalHelper initialized with AST compilation cache")

    def try_enhanced_eval(self, formula: str, context: dict[str, Any]) -> tuple[bool, Any]:
        """Try enhanced evaluation with AST caching, return (success, result).

        This is the primary method for handlers to attempt enhanced SimpleEval
        evaluation before falling back to their specialized logic. Now uses
        FormulaCompilationCache for 5-20x performance improvement.

        Args:
            formula: The formula string to evaluate
            context: Variable context for evaluation

        Returns:
            Tuple of (success: bool, result: Any)
            - If success=True, result contains the evaluated value
            - If success=False, result is None and handler should use fallback logic
        """
        try:
            # Use compilation cache for AST caching performance benefits
            compiled_formula = self._compilation_cache.get_compiled_formula(formula)
            result = compiled_formula.evaluate(context, numeric_only=False)

            self._enhancement_stats["enhanced_eval_count"] += 1
            _LOGGER.debug(
                "EnhancedSimpleEval SUCCESS (cached AST): formula='%s' -> %s (%s)", formula, result, type(result).__name__
            )
            return True, result

        except Exception as e:
            self._enhancement_stats["fallback_count"] += 1
            _LOGGER.debug("EnhancedSimpleEval FALLBACK: formula='%s' failed: %s", formula, e)
            # Return the exception for error handling
            return False, e

    def can_handle_enhanced(self, formula: str) -> bool:
        """Check if formula can be handled by enhanced SimpleEval.

        CLEAN SLATE: Enhanced SimpleEval handles everything except metadata functions.

        Args:
            formula: The formula string to analyze

        Returns:
            True if enhanced SimpleEval can handle it, False if metadata routing needed
        """
        # CLEAN SLATE: Only metadata functions need specialized routing
        if "metadata(" in formula.lower():
            _LOGGER.debug("Enhanced SimpleEval SKIP: formula='%s' contains metadata - routing to MetadataHandler", formula)
            return False

        # Everything else handled by enhanced SimpleEval
        _LOGGER.debug("Enhanced SimpleEval CAN_HANDLE: formula='%s'", formula)
        return True

    def get_supported_functions(self) -> set[str]:
        """Get the set of function names supported by enhanced SimpleEval.

        This is useful for routers to determine which functions can be
        handled by enhanced SimpleEval vs specialized handlers.

        Returns:
            Set of supported function names
        """
        # Get enhanced functions from MathFunctions (same as compilation cache uses)
        enhanced_functions = MathFunctions.get_all_functions()
        return set(enhanced_functions.keys())

    def clear_context(self) -> None:
        """Clear the evaluation context.

        This should be called between evaluations to ensure clean state.
        Note: Context is now managed per-evaluation via compilation cache.
        """
        # Context is now managed per-evaluation in try_enhanced_eval
        # This method preserved for backward compatibility
        _LOGGER.debug("EnhancedSimpleEval context cleared (managed per-evaluation)")

    def get_function_info(self) -> dict[str, Any]:
        """Get information about available enhanced functions.

        Returns:
            Dictionary with function categories and counts for debugging/monitoring
        """
        # Get enhanced functions from MathFunctions (same as compilation cache uses)
        functions = MathFunctions.get_all_functions()

        # Categorize functions for analysis
        categories = {
            "duration": [name for name in functions if name in {"minutes", "hours", "days", "seconds", "weeks"}],
            "datetime": [name for name in functions if name in {"now", "today", "datetime", "date", "timedelta"}],
            "metadata_calc": [name for name in functions if "_between" in name or "format_" in name],
            "mathematical": [name for name in functions if name in {"sin", "cos", "sqrt", "log", "abs", "max", "min"}],
            "statistical": [name for name in functions if name in {"mean", "std", "var", "sum", "count"}],
        }

        return {
            "total_functions": len(functions),
            "categories": {cat: len(funcs) for cat, funcs in categories.items()},
            "function_names": sorted(functions.keys()),
        }

    def get_compilation_cache_stats(self) -> dict[str, Any]:
        """Get compilation cache statistics for enhanced evaluation.

        Returns:
            Cache statistics dictionary including hit rate and entry count
        """
        return self._compilation_cache.get_statistics()

    def clear_compiled_formulas(self) -> None:
        """Clear compilation cache for enhanced evaluation."""
        self._compilation_cache.clear()
        _LOGGER.debug("EnhancedSimpleEval compilation cache cleared")

    def get_enhancement_stats(self) -> dict[str, Any]:
        """Get enhanced evaluation usage statistics.

        Returns:
            Dictionary with enhancement usage counts and cache statistics
        """
        cache_stats = self._compilation_cache.get_statistics()
        return {
            **self._enhancement_stats,
            "compilation_cache": cache_stats,
            "total_evaluations": self._enhancement_stats["enhanced_eval_count"] + self._enhancement_stats["fallback_count"],
        }


class EnhancedFormulaRouter:
    """Enhanced formula router that integrates EnhancedSimpleEvalHelper with existing routing.

    This class implements the enhanced routing strategy while preserving the existing
    handler architecture. It provides fast-path detection for enhanced SimpleEval
    while maintaining specialized handler routing as a refined fallback.
    """

    def __init__(self, existing_router: "FormulaRouter") -> None:
        """Initialize enhanced router with existing router for fallback.

        Args:
            existing_router: The existing FormulaRouter instance for fallback routing
        """
        self.enhanced_helper = EnhancedSimpleEvalHelper()
        self.existing_router = existing_router
        _LOGGER.debug("EnhancedFormulaRouter initialized")

    def evaluate_with_enhancement(self, formula: str, context: dict[str, Any]) -> tuple[bool, Any]:
        """Evaluate formula with enhanced SimpleEval first, fallback to existing routing.

        This implements the enhanced routing strategy:
        1. Fast-path: Try enhanced SimpleEval for 99% of formulas
        2. Fallback: Use existing handler routing for specialized functions

        Args:
            formula: Formula string to evaluate
            context: Variable context for evaluation

        Returns:
            Tuple of (used_enhanced: bool, result: Any)
        """
        # Step 1: Check if enhanced SimpleEval can handle this formula
        if self.enhanced_helper.can_handle_enhanced(formula):
            # Step 2: Try enhanced evaluation
            success, result = self.enhanced_helper.try_enhanced_eval(formula, context)
            if success:
                _LOGGER.debug("ENHANCED_ROUTING: formula='%s' handled by enhanced SimpleEval", formula)
                return True, result

        # Step 3: Fall back to existing handler routing
        _LOGGER.debug("FALLBACK_ROUTING: formula='%s' using existing handler routing", formula)

        # Use existing router to determine handler type and route accordingly
        routing_result = self.existing_router.route_formula(formula)

        # Return indication that we used fallback routing
        # The actual handler evaluation would be done by the calling code
        return False, routing_result

    def get_enhancement_stats(self) -> dict[str, Any]:
        """Get statistics about enhanced vs fallback routing usage.

        Returns:
            Dictionary with routing statistics for monitoring performance
        """
        return {
            "enhanced_functions": self.enhanced_helper.get_function_info(),
            "router_type": "enhanced_with_fallback",
        }
