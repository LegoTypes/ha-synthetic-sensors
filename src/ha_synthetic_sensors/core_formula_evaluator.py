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
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .constants_alternate import (
    ALTERNATE_STATE_NONE,
    ALTERNATE_STATE_UNAVAILABLE,
    ALTERNATE_STATE_UNKNOWN,
    STATE_NONE,
    identify_alternate_state_value,
)
from .enhanced_formula_evaluation import EnhancedSimpleEvalHelper
from .evaluator_handlers import HandlerFactory
from .evaluator_helpers import EvaluatorHelpers
from .exceptions import AlternateStateDetected, MissingDependencyError
from .hierarchical_context_dict import HierarchicalContextDict
from .regex_helper import create_referenced_tokens_pattern, find_all_matches
from .type_definitions import ReferenceValue

# Type for alternate state values
AlternateStateValue = str | None


class MissingStateError(ValueError):
    """Exception raised when a formula contains missing state values that should make sensor unavailable."""

    def __init__(self, missing_value: str) -> None:
        """Initialize the missing state error.

        Args:
            missing_value: The missing state value that triggered this error
        """
        super().__init__(f"Formula contains missing state '{missing_value}' - sensor should be unavailable")
        self.missing_value = missing_value


class AlternateStateDetectedError(Exception):
    """Exception raised when alternate states are detected in a formula that should not reach SimpleEval.

    This exception is used for flow control to prevent alternate state values from being
    processed by SimpleEval, which would cause evaluation errors. Instead, the formula
    should be routed to the alternate state handler.
    """

    def __init__(self, formula: str, detected_states: list[str]) -> None:
        """Initialize the alternate state detected error.

        Args:
            formula: The formula containing alternate states
            detected_states: List of alternate state values detected
        """
        super().__init__(f"Formula contains alternate states {detected_states} - routing to alternate state handler")
        self.formula = formula
        self.detected_states = detected_states


_LOGGER = logging.getLogger(__name__)


class CoreFormulaEvaluator:
    """Core formula evaluation service implementing Phase 3 of the Pipeline Formula Execution.

    This class encapsulates the pure formula evaluation logic, making it reusable across different
    contexts (main formulas, computed variables, attributes). It focuses solely on evaluating
    a resolved formula with a given context, without handling variable resolution, caching,
    or pipeline orchestration.

    RELATIONSHIP: This is the core evaluation engine that is used by FormulaEvaluatorService
    and called by the main evaluator pipeline via _execute_with_handler -> FormulaEvaluatorService.
    The main evaluator handles the full pipeline (variable resolution, caching, error handling)
    while this class handles only the formula evaluation itself.
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
        self._allow_unresolved_states = False

    def set_allow_unresolved_states(self, allow: bool) -> None:
        """Set whether to allow unresolved states to proceed into evaluation.

        Args:
            allow: If True, alternate states will be allowed to proceed into formula evaluation
                  If False (default), alternate states will be detected early and trigger handlers
        """
        self._allow_unresolved_states = allow

    def evaluate_formula(
        self,
        resolved_formula: str,
        original_formula: str,
        handler_context: HierarchicalContextDict,
    ) -> float | str | bool | None:
        """Evaluate a formula using the routing architecture.

        This method implements pure formula evaluation logic - it takes a resolved formula
        and context, then evaluates it using Enhanced SimpleEval with metadata function
        processing and alternate state detection.

        This is the core evaluation engine that can be reused across different contexts
        (main formulas, computed variables, attributes) without pipeline orchestration.

        Args:
            resolved_formula: Formula with variables resolved (used for Enhanced SimpleEval)
            original_formula: Original formula (used for metadata handler)
            handler_context: Hierarchical context containing ReferenceValue objects

        Returns:
            Evaluation result

        Raises:
            AlternateStateDetected: If the formula result is an alternate state
            ValueError: If evaluation fails

        RELATIONSHIP: This is called by FormulaEvaluatorService.evaluate_formula, which is
        called by _execute_with_handler in the main evaluator pipeline. This method focuses
        purely on formula evaluation while the pipeline handles variable resolution,
        caching, and error management.
        """

        try:
            # Process metadata functions in the formula before evaluation
            resolved_formula = self._process_metadata_functions(original_formula, resolved_formula, handler_context)

            _LOGGER.debug("About to proceed to Enhanced SimpleEval with formula: %s", resolved_formula)
            # Enhanced SimpleEval with AST Caching (default path for all formulas)
            enhanced_context = self._extract_values_for_enhanced_evaluation(handler_context, resolved_formula)
            success, result = self._enhanced_helper.try_enhanced_eval(resolved_formula, enhanced_context)

            if success:
                return self._process_successful_evaluation(result)

            # Enhanced SimpleEval failed - handle the failure
            self._handle_evaluation_failure(result)
            return None  # This line should never be reached due to exception

        # Definitive Alternate State Detected (actual instance of one of the alternate states as the formula result)
        except AlternateStateDetected as e:
            _LOGGER.debug("Alternate state detected: %s", e.message)
            raise
        # General failure in evaluation will result in STATE_NONE alternate state (i.e. None as reference part of ReferenceValue)
        except Exception as err:
            # Any evaluation failure results in AlternateStateDetected with STATE_NONE
            _LOGGER.debug("General formula evaluation failure: %s", str(err))
            raise AlternateStateDetected(f"Formula evaluation failed: {err}", STATE_NONE, "none") from err

    def _process_metadata_functions(
        self, original_formula: str, resolved_formula: str, handler_context: HierarchicalContextDict
    ) -> str:
        """Process metadata functions in the formula before evaluation."""
        if "metadata(" not in original_formula.lower():
            return resolved_formula

        handler = self._handler_factory.get_handler("metadata")
        if not (handler and handler.can_handle(original_formula)):
            _LOGGER.debug("METADATA_HANDLER_UNAVAILABLE: No metadata handler available or can't handle formula")
            return resolved_formula

        _LOGGER.debug("METADATA_HANDLER_PROCESSING: Processing formula with metadata handler")
        # Use the helper method to ensure consistent transformation for AST caching
        processed, metadata_results = handler.evaluate(original_formula, handler_context)
        # Metadata functions return their final values directly
        # This is a formula that needs further evaluation (may contain alternate states)
        resolved_formula = str(processed)

        # Debug: Check if metadata results contain the expected values
        if metadata_results:
            for key, value in metadata_results.items():
                _LOGGER.debug("METADATA_RESULT_DETAIL: %s = %s (type: %s)", key, value, type(value).__name__)
        else:
            _LOGGER.debug("METADATA_RESULT_EMPTY: No metadata results returned")

        # Add metadata results to handler context for SimpleEval
        self._add_metadata_results_to_context(metadata_results, handler_context)
        return resolved_formula

    def _add_metadata_results_to_context(
        self, metadata_results: dict[str, Any], handler_context: HierarchicalContextDict
    ) -> None:
        """Add metadata results to handler context for SimpleEval."""
        if not metadata_results:
            return

        # Wrap metadata results in ReferenceValue objects to comply with HierarchicalContextDict
        for key, value in metadata_results.items():
            # Store metadata results in evaluation context for SimpleEval lookup
            # Use the key itself as the reference since these are internal metadata keys
            # Use the hierarchical context's unified setter method
            handler_context._hierarchical_context.set(key, ReferenceValue(reference=key, value=value))  # pylint: disable=protected-access
            _LOGGER.debug("METADATA_CONTEXT_ADDED: Successfully stored metadata result: %s = %s", key, value)

    def _process_successful_evaluation(self, result: Any) -> float | int | str | bool:
        """Process and normalize successful evaluation result."""
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

        # Check if the final formula result is an alternate state
        alternate_state = self._get_alternate_state(final_result)
        if alternate_state is not False:
            raise AlternateStateDetected(
                f"Formula result '{final_result}' is alternate state",
                final_result,
                str(alternate_state) if alternate_state is not True else None,
            )

        return final_result

    def _handle_evaluation_failure(self, result: Any) -> None:
        """Handle evaluation failure cases."""
        # Enhanced SimpleEval failed - check if we have exception details
        # The result now contains the exception if enhanced evaluation failed
        if isinstance(result, Exception):
            eval_error = result
            error_msg = str(eval_error)
            raise AlternateStateDetected(error_msg, STATE_NONE, "none")

        # No exception details available
        raise AlternateStateDetected("Formula evaluation failed: unable to process expression", STATE_NONE, "none")

    def _extract_values_for_enhanced_evaluation(
        self, context: HierarchicalContextDict, referenced_formula: str
    ) -> dict[str, Any]:
        """Extract raw values from ReferenceValue objects for enhanced SimpleEval evaluation.

        Args:
            context: Hierarchical context containing ReferenceValue objects
            referenced_formula: The formula that references these variables

        Returns:
            Dictionary with variable names mapped to their preprocessed values for enhanced SimpleEval
        """
        enhanced_context: dict[str, Any] = {}

        # Precompute referenced variable tokens from the referenced_formula so we only
        # early-detect alternate states for variables actually used by the formula.
        # Use centralized referenced tokens pattern from regex helper
        pattern = create_referenced_tokens_pattern()
        referenced_tokens = set(find_all_matches(referenced_formula, pattern))
        _LOGGER.debug("CORE_EVAL_REFERENCED_TOKENS: Formula '%s' -> tokens: %s", referenced_formula, referenced_tokens)

        # Only process variables that are actually referenced in the formula
        for key in referenced_tokens:
            if key in context:
                value = context[key]
                if isinstance(value, ReferenceValue):
                    # Extract and preprocess raw value using priority analyzer.
                    raw_value = value.value
                    _LOGGER.debug("Processing key '%s' with raw_value '%s'", key, raw_value)

                    # Check for truly missing dependencies (None references)
                    if value.reference is None:
                        _LOGGER.debug(
                            "Found missing dependency '%s' with None reference, raising MissingDependencyError from _extract_values_for_enhanced_evaluation",
                            key,
                        )
                        raise MissingDependencyError(f"Missing dependency for variable '{key}'")

                    # Early detection of alternate states (unless allow_unresolved_states is True).
                    if not getattr(self, "_allow_unresolved_states", False):
                        # If the value comes from a ReferenceValue (i.e., backing entity or resolver)
                        # and its inner value is None, treat this as an HA UNKNOWN state rather than
                        # the YAML/literal STATE_NONE sentinel. This preserves the semantic that
                        # missing backing entity values are transient (UNKNOWN) and should hit the
                        # UNKNOWN handler if configured.
                        # Preserve semantics: a ReferenceValue wrapper with an inner Python None
                        # represents a resolved backing entity with no value (STATE_NONE). Use
                        # the standard alternate-state detection to map that to STATE_NONE so
                        # the NONE or FALLBACK handlers run. Only literal STATE_UNKNOWN strings
                        # should map to STATE_UNKNOWN.
                        _LOGGER.debug(
                            "CORE_EVAL_ALTERNATE_CHECK: Checking variable '%s' with raw_value '%s' (type: %s)",
                            key,
                            raw_value,
                            type(raw_value),
                        )
                        alternate_state = self._get_alternate_state(raw_value)
                        _LOGGER.debug("CORE_EVAL_ALTERNATE_RESULT: Variable '%s' alternate_state = %s", key, alternate_state)
                        if alternate_state is not False:
                            raise AlternateStateDetected(
                                f"Variable '{key}' contains alternate state '{alternate_state}'",
                                alternate_state,
                                str(alternate_state) if alternate_state is not True else None,
                            )

                    # Preprocess the value using priority analyzer (boolean-first, then numeric)
                    processed_value = EvaluatorHelpers.process_evaluation_result(raw_value)
                    enhanced_context[key] = processed_value

                    _LOGGER.debug("Enhanced context: %s = %s (from %s)", key, processed_value, raw_value)
                else:
                    # Non-ReferenceValue items - add directly to enhanced context
                    enhanced_context[key] = value

        # Also add any remaining context items that aren't ReferenceValues but are referenced in the formula (functions, etc.)
        for key, value in context.items():
            if key not in enhanced_context and not isinstance(value, ReferenceValue) and key in referenced_tokens:
                _LOGGER.debug(
                    "Adding referenced non-ReferenceValue context item: %s = %s (type: %s)", key, value, type(value).__name__
                )
                enhanced_context[key] = value

        return enhanced_context

    def _get_alternate_state(self, value: Any) -> AlternateStateValue | bool:
        """Check if the final result value of a formula is an alternate state value.

        Args:
            value: The value to check

        Returns:
            The alternate state value if the value is an alternate state, None otherwise
        """
        # Delegate alternate-state identification to shared helper and map
        alt = identify_alternate_state_value(value)
        if isinstance(alt, str):
            if alt == ALTERNATE_STATE_NONE:
                return STATE_NONE
            if alt == ALTERNATE_STATE_UNKNOWN:
                return STATE_UNKNOWN
            if alt == ALTERNATE_STATE_UNAVAILABLE:
                return STATE_UNAVAILABLE
        return False
