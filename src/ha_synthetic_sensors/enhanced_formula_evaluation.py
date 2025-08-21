"""Enhanced formula evaluation using SimpleEval with compilation caching."""

from __future__ import annotations

import logging
from typing import Any

from .formula_compilation_cache import FormulaCompilationCache
from .math_functions import MathFunctions

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
        lower = formula.lower()
        if "metadata(" in lower:
            _LOGGER.debug("Enhanced SimpleEval SKIP: formula='%s' contains metadata - routing to MetadataHandler", formula)
            return False

        # Avoid trying to enhanced-evaluate ternary operator expressions (a ? b : c)
        # SimpleEval-based enhanced evaluator doesn't support the custom ternary syntax; let core evaluator handle it.
        if "?" in formula and ":" in formula:
            _LOGGER.debug(
                "Enhanced SimpleEval SKIP: formula='%s' appears to contain ternary operator - routing to core evaluator",
                formula,
            )
            return False

        # Everything else handled by enhanced SimpleEval
        _LOGGER.debug("Enhanced SimpleEval CAN_HANDLE: formula='%s'", formula)
        return True

    def get_enhanced_functions(self) -> set[str]:
        """Get set of all enhanced functions available in SimpleEval.

        Returns:
            Set of function names available for enhanced evaluation
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
        """Get detailed information about available functions.

        Returns:
            Dictionary with function categorization and statistics
        """
        # Get enhanced functions from MathFunctions (same as compilation cache uses)
        functions = MathFunctions.get_all_functions()

        # Categorize functions for analysis
        categories = {
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
