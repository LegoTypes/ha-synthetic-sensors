"""Formula execution logic for the evaluator."""

from __future__ import annotations

import logging
from typing import Any

from .config_models import FormulaConfig, SensorConfig
from .enhanced_formula_evaluation import EnhancedSimpleEvalHelper
from .evaluator_error_handler import EvaluatorErrorHandler
from .evaluator_handlers import HandlerFactory
from .evaluator_helpers import EvaluatorHelpers
from .exceptions import BackingEntityResolutionError
from .type_definitions import ContextValue, EvaluationResult, ReferenceValue

_LOGGER = logging.getLogger(__name__)


class FormulaExecutionEngine:
    """Handles the core formula execution logic for the evaluator."""

    def __init__(
        self,
        handler_factory: HandlerFactory,
        error_handler: EvaluatorErrorHandler,
        enhanced_helper: EnhancedSimpleEvalHelper,
    ):
        """Initialize the formula execution engine.

        Args:
            handler_factory: Factory for creating formula handlers
            error_handler: Error handler for circuit breaker pattern
            enhanced_helper: Enhanced evaluation helper (clean slate design - always required)
        """
        self._handler_factory = handler_factory
        self._error_handler = error_handler
        self._enhanced_helper = enhanced_helper

    def execute_formula_evaluation(
        self,
        config: FormulaConfig,
        resolved_formula: str,
        handler_context: dict[str, ContextValue],
        eval_context: dict[str, ContextValue],
        sensor_config: SensorConfig | None,
    ) -> float | str | bool:
        """Execute formula evaluation with proper handler routing.

        This is the core evaluation method that handles the clean slate routing
        architecture with enhanced SimpleEval as the primary path.

        Args:
            config: Formula configuration
            resolved_formula: Formula with variables resolved
            handler_context: Context for handlers (ReferenceValue objects)
            eval_context: Context for evaluation (mixed types)
            sensor_config: Optional sensor configuration

        Returns:
            Evaluation result

        Raises:
            ValueError: If evaluation fails
        """
        _LOGGER.debug("🔥 CLEAN_SLATE_ROUTING: Executing formula: %s", resolved_formula)

        original_formula = config.formula

        try:
            # CLEAN SLATE: Only 2 routing paths needed

            # Path 1: Metadata functions (1% - requires HA integration)
            if "metadata(" in resolved_formula.lower():
                metadata_handler = self._handler_factory.get_handler("metadata")
                if metadata_handler and metadata_handler.can_handle(original_formula):
                    _LOGGER.debug("CLEAN_SLATE_ROUTING: Metadata path for formula: %s", original_formula)
                    result = metadata_handler.evaluate(original_formula, handler_context)
                    return result  # type: ignore[no-any-return]

                raise ValueError(f"Metadata formula detected but handler not available: {original_formula}")

            # Path 2: Enhanced SimpleEval (99% - everything else)
            # Extract raw values for enhanced evaluation
            enhanced_context = self._extract_values_for_enhanced_evaluation(handler_context)

            success, result = self._enhanced_helper.try_enhanced_eval(resolved_formula, enhanced_context)

            if success:
                _LOGGER.debug(
                    "CLEAN_SLATE_ROUTING: Enhanced SimpleEval success for formula: %s -> %s", resolved_formula, result
                )
                # Handle all result types
                if isinstance(result, int | float | str | bool):
                    return result
                if hasattr(result, "total_seconds"):  # timedelta
                    # Convert timedelta to seconds for consistency
                    return float(result.total_seconds())
                if hasattr(result, "isoformat"):  # datetime/date
                    return str(result.isoformat())  # Return as ISO string

                # Convert unexpected types to string
                return str(result)

            # Enhanced SimpleEval failed - check if we have exception details
            # The result now contains the exception if enhanced evaluation failed
            if isinstance(result, Exception):
                eval_error = result
                error_msg = str(eval_error)

                # Handle specific mathematical errors gracefully by raising appropriate exceptions
                if isinstance(eval_error, ZeroDivisionError):
                    raise ValueError("Division by zero in formula")
                if isinstance(eval_error, NameError) or "undefined" in error_msg.lower() or "not defined" in error_msg.lower():
                    raise ValueError(f"Undefined variable: {error_msg}")

                # Other mathematical or evaluation errors
                raise ValueError(f"Formula evaluation error: {error_msg}")

            # No exception details available
            raise ValueError("Formula evaluation failed: unable to process expression")

        except Exception as err:
            _LOGGER.error("Formula execution failed for %s: %s", resolved_formula, err)
            raise

    def _extract_values_for_enhanced_evaluation(self, context: dict[str, ContextValue]) -> dict[str, Any]:
        """Extract raw values from ReferenceValue objects for enhanced SimpleEval evaluation.

        Args:
            context: Handler context containing ReferenceValue objects

        Returns:
            Dictionary with variable names mapped to their preprocessed values for enhanced SimpleEval
        """
        enhanced_context: dict[str, Any] = {}

        for key, value in context.items():
            if isinstance(value, ReferenceValue):
                # Extract and preprocess the raw value for enhanced evaluation
                raw_value = value.value

                # Preprocess the value to ensure compatibility with enhanced SimpleEval
                processed_value = EvaluatorHelpers.process_evaluation_result(raw_value)
                enhanced_context[key] = processed_value

                _LOGGER.debug("Enhanced context: %s = %s (from %s)", key, processed_value, raw_value)
            else:
                # Keep other context items as-is (functions, etc.)
                enhanced_context[key] = value

        return enhanced_context

    def handle_value_error(self, error: ValueError, formula_name: str) -> EvaluationResult:
        """Handle ValueError during formula evaluation."""
        error_msg = str(error)

        # Enhanced error handling with more specific checks
        if any(keyword in error_msg.lower() for keyword in ["undefined", "not defined", "name", "variable"]):
            # Variable/name resolution errors
            _LOGGER.warning("Variable resolution error in formula '%s': %s", formula_name, error_msg)
            self._error_handler.increment_error_count(formula_name)
            return EvaluationResult(success=False, value="unavailable", error=error_msg)

        if "division by zero" in error_msg.lower():
            # Mathematical errors that might be transitory
            _LOGGER.warning("Mathematical error in formula '%s': %s", formula_name, error_msg)
            self._error_handler.increment_transitory_error_count(formula_name)
            return EvaluationResult(success=False, value="unknown", error=error_msg)

        # Default: treat as fatal error
        _LOGGER.warning("Fatal error in formula '%s': %s", formula_name, error_msg)
        self._error_handler.increment_error_count(formula_name)
        return EvaluationResult(success=False, value="unavailable", error=error_msg)

    def handle_backing_entity_error(self, error: BackingEntityResolutionError, formula_name: str) -> EvaluationResult:
        """Handle BackingEntityResolutionError - these are always fatal (missing entities)."""
        _LOGGER.warning("Backing entity resolution error in formula '%s': %s", formula_name, error)
        self._error_handler.increment_error_count(formula_name)
        return EvaluationResult(success=False, value="unavailable", error=str(error))

    def convert_handler_result(self, result: Any) -> bool | str | float | int:
        """Convert handler result to expected types."""
        if isinstance(result, bool | str | float | int):
            return result
        # Convert other types to string representation
        return str(result)
