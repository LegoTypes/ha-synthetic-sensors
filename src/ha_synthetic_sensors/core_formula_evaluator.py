"""Core formula evaluation component implementing the CLEAN SLATE routing architecture.

This module provides a reusable formula evaluation service that can be used by:
- Main sensor formulas (via FormulaExecutionEngine)
- Computed variables (future)
- Attribute formulas (future)

The CLEAN SLATE routing architecture:
1. Path 1: Metadata functions → MetadataHandler
2. Path 2: Everything else → Enhanced SimpleEval
"""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .enhanced_formula_evaluation import EnhancedSimpleEvalHelper
from .evaluator_handlers import HandlerFactory
from .evaluator_helpers import EvaluatorHelpers
from .type_definitions import ContextValue, ReferenceValue


class MissingStateError(ValueError):
    """Exception raised when a formula contains missing state values that should make sensor unavailable."""

    def __init__(self, missing_value: str) -> None:
        """Initialize the missing state error.

        Args:
            missing_value: The missing state value that triggered this error
        """
        super().__init__(f"Formula contains missing state '{missing_value}' - sensor should be unavailable")
        self.missing_value = missing_value


_LOGGER = logging.getLogger(__name__)


class CoreFormulaEvaluator:
    """Core formula evaluation service implementing CLEAN SLATE routing.

    This class encapsulates the formula evaluation logic that was previously
    embedded in FormulaExecutionEngine, making it reusable across different
    contexts (main formulas, computed variables, attributes).
    """

    def __init__(
        self,
        handler_factory: HandlerFactory,
        enhanced_helper: EnhancedSimpleEvalHelper,
    ) -> None:
        """Initialize the core formula evaluator.

        Args:
            handler_factory: Factory for creating evaluation handlers
            enhanced_helper: Enhanced SimpleEval helper for math operations
        """
        self._handler_factory = handler_factory
        self._enhanced_helper = enhanced_helper

    def evaluate_formula(
        self,
        resolved_formula: str,
        original_formula: str,
        handler_context: dict[str, ContextValue],
    ) -> float | str | bool:
        """Evaluate a formula using the CLEAN SLATE routing architecture.

        Args:
            resolved_formula: Formula with variables resolved (used for Enhanced SimpleEval)
            original_formula: Original formula (used for metadata handler)
            handler_context: Context containing ReferenceValue objects

        Returns:
            Evaluation result

        Raises:
            ValueError: If evaluation fails
        """

        try:
            # Only 2 routing paths needed simpleeval for 99% of cases and then other handlers (like metadata)

            # NOTE: Metadata functions are now processed in Phase 2: Metadata Processing (VariableResolutionPhase)
            # before values are extracted from ReferenceValues

            # Path 1: Route metadata() to MetadataHandler if present
            if "metadata(" in original_formula.lower():
                handler = self._handler_factory.get_handler("metadata")
                if handler and handler.can_handle(original_formula):
                    processed = handler.evaluate(original_formula, handler_context)
                    # After metadata returns string/numeric, evaluate through enhanced path uniformly
                    resolved_formula = str(processed)

            # Path 2: Enhanced SimpleEval (default)
            # Phase 3: Value Resolution (CoreFormulaEvaluator): Substitute ReferenceValue objects with their values in formula
            # Guard design (future-proof):
            # - We only apply missing-state guard to variables that are actually value-substituted for evaluation.
            # - Specialized handlers (by convention) take their first parameter as an entity reference (or None).
            #   Those reference arguments should NOT trigger the missing-state guard because they do not consume the
            #   numeric/boolean state; they consume the entity reference itself. The metadata() handler follows this
            #   convention today. Future handlers should do the same.
            pre_sub_formula = resolved_formula
            resolved_formula = self._substitute_values_in_formula(resolved_formula, handler_context)

            # Extract raw values for enhanced evaluation
            enhanced_context = self._extract_values_for_enhanced_evaluation(handler_context, pre_sub_formula)

            # Check if extraction found missing states that should make sensor unavailable
            if enhanced_context is None:
                # Get the missing state value for the error message
                state_value = handler_context.get("state")
                missing_value = state_value.value if isinstance(state_value, ReferenceValue) else STATE_UNKNOWN
                # Raise a specific exception to trigger unavailable state
                raise MissingStateError(str(missing_value))

            success, result = self._enhanced_helper.try_enhanced_eval(resolved_formula, enhanced_context)

            if success:
                # Normalize result to a single return
                final_result: float | int | str | bool
                if isinstance(result, (int | float | str | bool)):
                    final_result = result
                elif hasattr(result, "total_seconds"):
                    # Convert timedelta to seconds for consistency
                    final_result = float(result.total_seconds())
                elif hasattr(result, "isoformat"):
                    final_result = str(result.isoformat())
                else:
                    final_result = str(result)
                return final_result

            # Enhanced SimpleEval failed - check if we have exception details
            # The result now contains the exception if enhanced evaluation failed
            if isinstance(result, Exception):
                eval_error = result
                error_msg = str(eval_error)
                is_zero_div = isinstance(eval_error, ZeroDivisionError)
                is_undefined = isinstance(eval_error, NameError) or (
                    "undefined" in error_msg.lower() or "not defined" in error_msg.lower()
                )
                if is_zero_div:
                    raise ValueError("Division by zero in formula")
                if is_undefined:
                    raise ValueError(f"Undefined variable: {error_msg}")
                raise ValueError(f"Formula evaluation error: {error_msg}")

            # No exception details available
            raise ValueError("Formula evaluation failed: unable to process expression")

        except Exception as err:
            _LOGGER.error("Core formula evaluation failed for %s: %s", resolved_formula, err)
            raise

    def _extract_values_for_enhanced_evaluation(
        self, context: dict[str, ContextValue], referenced_formula: str | None = None
    ) -> dict[str, Any] | None:
        """Extract raw values from ReferenceValue objects for enhanced SimpleEval evaluation.

        Args:
            context: Handler context containing ReferenceValue objects

        Returns:
            Dictionary with variable names mapped to their preprocessed values for enhanced SimpleEval,
            or None if missing state values are found that should trigger unavailable sensor
        """
        enhanced_context: dict[str, Any] = {}
        referenced_names: set[str] | None = None
        if referenced_formula:
            try:
                # Extract identifiers that will be substituted during value resolution.
                # This approximates the set of variables that are value-consuming in Phase 3.
                referenced_names = set(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", referenced_formula))
            except Exception:
                referenced_names = None

        # Check for missing state values that should trigger unavailable sensor state
        # Use Home Assistant constants for missing states
        missing_states = [STATE_UNKNOWN, STATE_UNAVAILABLE]

        # Check if this is an alternate state handler evaluation
        is_alternate_handler = context.get("__is_alternate_handler__", False)

        for key, value in context.items():
            # Skip the alternate handler marker
            if key == "__is_alternate_handler__":
                continue
            if isinstance(value, ReferenceValue):
                # Extract and preprocess raw value using priority analyzer.
                raw_value = value.value
                # Scoped missing-state guard:
                # Apply guard only when this variable is referenced in the pre-substitution formula
                # (i.e., it will be value-substituted). Reference arguments to specialized handlers
                # (e.g., metadata(entity_ref, ...)) should not trigger the guard by convention.
                # For alternate handlers, allow 'state' to be unknown/unavailable since that's when they should run
                should_apply_guard = (
                    (referenced_names is None or key in referenced_names)
                    and isinstance(raw_value, str)
                    and raw_value.lower() in missing_states
                    and not (is_alternate_handler and key == "state")
                )
                if should_apply_guard:
                    _LOGGER.debug("Found missing state '%s' = '%s', sensor should become unavailable", key, raw_value)
                    return None

                # Preprocess the value using priority analyzer (boolean-first, then numeric)
                processed_value = EvaluatorHelpers.process_evaluation_result(raw_value)
                enhanced_context[key] = processed_value

                _LOGGER.debug("Enhanced context: %s = %s (from %s)", key, processed_value, raw_value)
            else:
                # Keep other context items as-is (functions, etc.)
                enhanced_context[key] = value

        return enhanced_context

    def _substitute_values_in_formula(self, formula: str, handler_context: dict[str, ContextValue]) -> str:
        """PHASE 3: Substitute ReferenceValue objects with their actual values in the formula."""
        # Pattern to match variable names
        variable_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")

        def replace_with_value(match: re.Match[str]) -> str:
            var_name = match.group(1)

            # Skip reserved words and function names
            if var_name in ["metadata", "state", "min", "max", "abs", "round", "int", "float", "str", "len", "sum", "avg"]:
                return var_name

            # Check if variable exists in context
            if var_name in handler_context:
                value = handler_context[var_name]
                actual_value = value.value if isinstance(value, ReferenceValue) else value

                # Handle string values - convert numeric strings to numbers for math operations
                if isinstance(actual_value, str):
                    coerced = EvaluatorHelpers.preprocess_value_for_enhanced_eval(actual_value)
                    if isinstance(coerced, bool | int | float):
                        return str(coerced)
                    return f'"{coerced}"'
                return str(actual_value)

            # Not in context, return unchanged
            return var_name

        substituted = variable_pattern.sub(replace_with_value, formula)

        # Secondary safeguard: resolve any remaining dotted entity_id tokens using handler_context
        # This covers cases where earlier phases intentionally preserved dotted tokens for metadata
        # or missed substitution due to context propagation timing differences (runtime scenarios).
        entity_pattern = re.compile(
            r"(?:^|(?<=\s)|(?<=\()|(?<=[+\-*/]))([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z0-9_.]+)(?=\s|$|[+\-*/)])"
        )

        def replace_entity_with_value(match: re.Match[str]) -> str:
            entity_id = match.group(1)
            alias = entity_id.replace(".", "_").replace("-", "_")
            context_value: Any | None = None
            if alias in handler_context:
                context_value = handler_context[alias]
            elif entity_id in handler_context:
                context_value = handler_context[entity_id]

            if context_value is None:
                # If not in context, leave unchanged and let SimpleEval error for true missing deps
                return entity_id

            actual_value = context_value.value if isinstance(context_value, ReferenceValue) else context_value
            if isinstance(actual_value, str):
                coerced = EvaluatorHelpers.preprocess_value_for_enhanced_eval(actual_value)
                return str(coerced) if isinstance(coerced, bool | int | float) else f'"{coerced}"'
            return str(actual_value)

        substituted2 = entity_pattern.sub(replace_entity_with_value, substituted)
        return substituted2
