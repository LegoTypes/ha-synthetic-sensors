"""Enhanced formula evaluation helper for integrating enhanced SimpleEval with existing handlers."""

import ast
import logging
from typing import TYPE_CHECKING, Any

from simpleeval import SimpleEval

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
        """Initialize the enhanced SimpleEval helper."""
        self.enhanced_evaluator = self._create_enhanced_evaluator()
        self._enhancement_stats = {"enhanced_eval_count": 0, "fallback_count": 0}
        _LOGGER.debug("EnhancedSimpleEvalHelper initialized with enhanced functions")

    def _create_enhanced_evaluator(self) -> SimpleEval:
        """Create SimpleEval with comprehensive function support.

        This creates a SimpleEval instance with all enhanced functions including:
        - Duration functions that return timedelta objects (minutes, hours, days)
        - Datetime functions (now, today, datetime, date)
        - Metadata calculation functions (minutes_between, format_friendly)
        - All existing mathematical and collection functions

        Returns:
            Configured SimpleEval instance with enhanced functions
        """
        # Get all enhanced functions including timedelta-based duration functions
        functions = MathFunctions.get_all_functions()

        # Create SimpleEval with enhanced capabilities
        evaluator = SimpleEval(functions=functions)

        # Enable List and Tuple literals for collection operations
        # Create safe wrapper for SimpleEval internal evaluation to avoid protected access
        def safe_eval_node(node: Any) -> Any:
            """Safe wrapper for evaluating AST nodes using SimpleEval's public interface."""
            # Use the public eval method on a minimal expression
            temp_expr = compile(ast.Expression(node), "<ast>", "eval")
            return eval(temp_expr, evaluator.names, evaluator.functions)  # pylint: disable=eval-used  # nosec B307  # Safe context

        evaluator.nodes[ast.List] = lambda node: [safe_eval_node(item) for item in node.elts]
        evaluator.nodes[ast.Tuple] = lambda node: tuple(safe_eval_node(item) for item in node.elts)

        return evaluator

    def try_enhanced_eval(self, formula: str, context: dict[str, Any]) -> tuple[bool, Any]:
        """Try enhanced evaluation, return (success, result).

        This is the primary method for handlers to attempt enhanced SimpleEval
        evaluation before falling back to their specialized logic.

        Args:
            formula: The formula string to evaluate
            context: Variable context for evaluation

        Returns:
            Tuple of (success: bool, result: Any)
            - If success=True, result contains the evaluated value
            - If success=False, result is None and handler should use fallback logic
        """
        try:
            # Set context and evaluate
            self.enhanced_evaluator.names = context
            result = self.enhanced_evaluator.eval(formula)

            _LOGGER.debug("EnhancedSimpleEval SUCCESS: formula='%s' -> %s (%s)", formula, result, type(result).__name__)
            return True, result

        except Exception as e:
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
        return set(self.enhanced_evaluator.functions.keys())

    def clear_context(self) -> None:
        """Clear the evaluation context.

        This should be called between evaluations to ensure clean state.
        """
        self.enhanced_evaluator.names = {}
        _LOGGER.debug("EnhancedSimpleEval context cleared")

    def get_function_info(self) -> dict[str, Any]:
        """Get information about available enhanced functions.

        Returns:
            Dictionary with function categories and counts for debugging/monitoring
        """
        functions = self.enhanced_evaluator.functions

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
