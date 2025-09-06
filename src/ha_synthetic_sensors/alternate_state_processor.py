"""Comprehensive alternate state handler processor.

This module implements the two-phase alternate state handler system:
1. Pre-evaluation optimization for single alternate states
2. Post-evaluation processing for results and exceptions
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import STATE_UNKNOWN

from .evaluator_results import EvaluatorResults
from .exceptions import AlternateStateDetected
from .type_definitions import ReferenceValue

if TYPE_CHECKING:
    from .hierarchical_context_dict import HierarchicalContextDict


from .config_models import AlternateStateHandler, FormulaConfig, SensorConfig
from .constants_alternate import (
    ALTERNATE_STATE_NONE,
    ALTERNATE_STATE_UNAVAILABLE,
    ALTERNATE_STATE_UNKNOWN,
    identify_alternate_state_value,
)
from .constants_formula import ALL_OPERATORS

_LOGGER = logging.getLogger(__name__)


class AlternateStateProcessor:
    """Processes alternate state handlers with pre and post evaluation checks."""

    def __init__(self, evaluator: Any = None) -> None:
        """Initialize the alternate state processor.

        Args:
            evaluator: Optional evaluator instance for proper pipeline processing.
                      If not provided, will fall back to manual variable processing.
        """
        self._logger = _LOGGER.getChild(self.__class__.__name__)
        self._evaluator = evaluator

    def check_pre_evaluation_states(
        self,
        context: HierarchicalContextDict,
        config: FormulaConfig,
        sensor_config: SensorConfig | None = None,
        core_evaluator: Any | None = None,
        resolve_all_references_in_formula: Any | None = None,
    ) -> float | str | bool | None:
        """Check for single alternate states before evaluation (optimization).

        If the context contains only one variable and it resolves to an alternate state
        (STATE_NONE, STATE_UNKNOWN, STATE_UNAVAILABLE), immediately trigger the
        appropriate alternate state handler instead of passing to SimpleEval.

        Args:
            context: Evaluation context with resolved variables
            config: Formula configuration with potential alternate state handler
            sensor_config: Optional sensor configuration

        Returns:
            Result from alternate state handler if triggered, None otherwise
        """
        self._logger.warning("PRE_EVAL_CHECK_ENTRY: Called with formula=%s", config.formula)

        # Check allow_unresolved_states value
        allow_unresolved = getattr(config, "allow_unresolved_states", False)

        # If allow_unresolved_states is True, skip all alternate state detection
        # This allows formulas to explicitly test for and handle unavailable states
        if allow_unresolved:
            self._logger.debug(
                "PRE_EVAL_CHECK: allow_unresolved_states=True, skipping alternate state detection for formula '%s'",
                config.formula,
            )
            return None

        if not config.alternate_state_handler:
            self._logger.debug("PRE_EVAL_CHECK_ENTRY: No alternate state handler, returning None")
            return None

        # Check if the formula is a single identifier (like 'state')
        stripped_formula = config.formula.strip()
        if not stripped_formula.isidentifier():
            self._logger.debug("PRE_EVAL_CHECK: Formula '%s' is not a single identifier, skipping", config.formula)
            return False

        # Get the resolved value for this identifier from the context
        resolved_value = context.get(stripped_formula)
        if resolved_value is None:
            self._logger.debug("PRE_EVAL_CHECK: Variable '%s' not found in context, skipping", stripped_formula)
            return False

        var_name = stripped_formula
        var_value = resolved_value

        # Check if it's an alternate state that should trigger handlers
        # Use the shared helper mapping contract: returns a string for detected alternate
        # states or False when no alternate state is detected. Preserve that
        # contract here so callers can distinguish a legitimate None handler
        # result from "no alternate state detected".
        raw_val = var_value.value if isinstance(var_value, ReferenceValue) else var_value
        self._logger.debug(
            "PRE_EVAL_CHECK: var_name=%s, var_value=%s (type: %s), raw_val=%s (type: %s)",
            var_name,
            var_value,
            type(var_value),
            raw_val,
            type(raw_val),
        )
        alternate_state = identify_alternate_state_value(raw_val)
        self._logger.debug("PRE_EVAL_CHECK: alternate_state=%s", alternate_state)

        if alternate_state is not False:
            raise AlternateStateDetected(
                "Alternate state detected during pre-evaluation",
                raw_val,
                str(alternate_state) if alternate_state is not True else None,
            )
        else:
            self._logger.debug(
                "Pre-evaluation optimization: Single variable '%s' is %s, letting evaluation continue to Phase 3",
                var_name,
                alternate_state,
            )

        return True

    def process_evaluation_result(
        self,
        result: float | str | bool | None,
        exception: Exception | None,
        context: HierarchicalContextDict,
        config: FormulaConfig,
        sensor_config: SensorConfig | None = None,
        core_evaluator: Any | None = None,
        resolve_all_references_in_formula: Any | None = None,
        pre_eval: bool = False,
    ) -> float | str | bool | None:
        """Process evaluation results and exceptions for alternate states.

        Args:
            result: The evaluation result (if successful)
            exception: The exception (if evaluation failed)
            context: Evaluation context
            config: Formula configuration with potential alternate state handler
            sensor_config: Optional sensor configuration
            core_evaluator: Core evaluator for formula alternate evaluation
            resolve_all_references_in_formula: Reference resolver function

        Returns:
            Processed result, potentially from alternate state handler
        """

        # Default output: if there was an exception, default to None; otherwise preserve result
        output: float | str | bool | None = result if exception is None else None
        if not config.alternate_state_handler:
            return output

        # Handle None results separately in helper to reduce branching here
        if exception is None and result is None:
            handled, output = self._process_none_result(
                context, config, sensor_config, core_evaluator, resolve_all_references_in_formula, pre_eval
            )
            if handled:
                return output

        # Handle exceptions separately in helper
        if exception is not None:
            # Process all exceptions (including AlternateStateDetected) through the unified handler
            handled, output = self._process_exception(
                exception, context, config, sensor_config, core_evaluator, resolve_all_references_in_formula
            )
            if handled:
                # Convert raw output to proper EvaluationResult format
                result_obj = EvaluatorResults.create_success_from_result(output)
                return result_obj.get("value", output) if isinstance(result_obj, dict) else output

        # Handle successful results that are alternate states
        self._logger.warning("PROCESS_EVAL_RESULT: Checking result=%s (type: %s) for alternate state", result, type(result))
        result_alternate_state = self._identify_alternate_state(result)
        self._logger.warning("PROCESS_EVAL_RESULT: result_alternate_state=%s", result_alternate_state)
        if result_alternate_state is not False:
            self._logger.debug("Evaluation result is %s, triggering alternate handler", result_alternate_state)
            # Create AlternateStateDetected exception with the identified state
            alternate_exception = AlternateStateDetected(
                message=f"Alternate state detected in evaluation result: {result_alternate_state}",
                alternate_state_value=result.value if result is not None and hasattr(result, "value") else None,
                alternate_state_type=cast(str, result_alternate_state),
            )
            return self._trigger_alternate_handler(
                alternate_exception,
                config.alternate_state_handler,
                context,
                config,
                sensor_config,
                core_evaluator,
                resolve_all_references_in_formula,
            )

        return output

    def _process_none_result(
        self,
        context: HierarchicalContextDict,
        config: FormulaConfig,
        sensor_config: SensorConfig | None,
        core_evaluator: Any | None,
        resolve_all_references_in_formula: Any | None,
        pre_eval: bool,
    ) -> tuple[bool, float | str | bool | None]:
        """Process the case where evaluation returned None.

        Returns (handled, output). If handled is True the caller should return output.
        """
        if pre_eval:
            self._logger.debug("Pre-eval handler returned explicit None; preserving None result")
            return True, None

        has_none_value = False
        for var_name, var_value in context.items():
            if isinstance(var_value, ReferenceValue):
                if var_value.value is None:
                    has_none_value = True
                    self._logger.debug("Found None value in context variable '%s', triggering NONE handler", var_name)
                    break
            elif var_value is None:
                has_none_value = True
                self._logger.debug("Found None value in context variable '%s', triggering NONE handler", var_name)
                break

        if has_none_value:
            handler = config.alternate_state_handler
            if handler is None:
                self._logger.warning("Alternate state handler missing from config when expected; returning None")
                return True, None
            # Create AlternateStateDetected exception for None state
            none_exception = AlternateStateDetected(
                message="None value detected in context variables",
                alternate_state_value=None,
                alternate_state_type=ALTERNATE_STATE_NONE,
            )
            return True, self._trigger_alternate_handler(
                none_exception,
                handler,
                context,
                config,
                sensor_config,
                core_evaluator,
                resolve_all_references_in_formula,
            )

        self._logger.debug("Evaluation returned None (missing state guard), triggering UNAVAILABLE alternate handler")
        handler = config.alternate_state_handler
        if handler is None:
            self._logger.warning("Alternate state handler missing from config when expected; returning None")
            return True, None
        # Create AlternateStateDetected exception for unavailable state
        unavailable_exception = AlternateStateDetected(
            message="Evaluation returned None (missing state guard)",
            alternate_state_value="unavailable",
            alternate_state_type=ALTERNATE_STATE_UNAVAILABLE,
        )
        return True, self._trigger_alternate_handler(
            unavailable_exception,
            handler,
            context,
            config,
            sensor_config,
            core_evaluator,
            resolve_all_references_in_formula,
        )

    def _process_exception(
        self,
        exception: Exception,
        context: HierarchicalContextDict,
        config: FormulaConfig,
        sensor_config: SensorConfig | None,
        core_evaluator: Any | None,
        resolve_all_references_in_formula: Any | None,
    ) -> tuple[bool, float | str | bool | None]:
        """Process exceptions and map them to alternate handlers.

        Returns (handled, output).
        """
        # Handle AlternateStateDetected exceptions directly using their pre-computed type
        if isinstance(exception, AlternateStateDetected):
            self._logger.debug(
                "Processing AlternateStateDetected exception with type: %s, value: %s",
                exception.alternate_state_type,
                exception.alternate_state_value,
            )
            handler = config.alternate_state_handler
            if handler is None:
                self._logger.warning("Alternate state handler missing from config when expected; returning None")
                return True, None
            return True, self._trigger_alternate_handler(
                exception,
                handler,
                context,
                config,
                sensor_config,
                core_evaluator,
                resolve_all_references_in_formula,
            )

        # For other exceptions, map them to alternate states based on their content
        exception_str = str(exception).lower()
        if STATE_UNAVAILABLE in exception_str:
            alternate_state_type = ALTERNATE_STATE_UNAVAILABLE
            alternate_state_value = STATE_UNAVAILABLE
        elif STATE_UNKNOWN in exception_str:
            alternate_state_type = ALTERNATE_STATE_UNKNOWN
            alternate_state_value = STATE_UNKNOWN
        else:
            alternate_state_type = ALTERNATE_STATE_NONE
            alternate_state_value = None

        self._logger.debug(
            "Evaluation exception occurred: %s, mapping to %s state and triggering alternate handler",
            str(exception),
            alternate_state_type,
        )

        # Create an AlternateStateDetected exception to maintain consistency
        alternate_exception = AlternateStateDetected(
            f"Exception mapped to alternate state: {exception}", alternate_state_value, alternate_state_type
        )

        handler = config.alternate_state_handler
        if handler is None:
            self._logger.warning("Alternate state handler missing from config when expected; returning None")
            return True, None
        return True, self._trigger_alternate_handler(
            alternate_exception,
            handler,
            context,
            config,
            sensor_config,
            core_evaluator,
            resolve_all_references_in_formula,
        )

    def _identify_alternate_state(self, value: Any) -> str | bool:
        """Delegate alternate state detection to shared helper."""
        # Use the shared helper function to detect HA special states
        alt = identify_alternate_state_value(value)
        # Preserve the shared helper's contract: return string for detected state or False when none
        return alt

    def _trigger_alternate_handler(
        self,
        exception: AlternateStateDetected,
        handler: AlternateStateHandler,
        context: HierarchicalContextDict,
        config: FormulaConfig,
        sensor_config: SensorConfig | None = None,
        core_evaluator: Any | None = None,
        resolve_all_references_in_formula: Any | None = None,
    ) -> float | str | bool | None:
        """Trigger the appropriate alternate state handler.

        Args:
            exception: The AlternateStateDetected exception containing state type and value
            handler: The alternate state handler configuration
            context: Evaluation context
            config: Formula configuration
            sensor_config: Optional sensor configuration
            core_evaluator: Core evaluator for formula evaluation
            resolve_all_references_in_formula: Reference resolver function

        Returns:
            Result from the alternate state handler
        """
        # Determine which handler to use based on priority
        handler_value = None
        state_type = exception.alternate_state_type

        self._logger.debug(
            "Handler selection for state_type='%s': none=%s, unknown=%s, unavailable=%s, fallback=%s",
            state_type,
            handler.none,
            handler.unknown,
            handler.unavailable,
            handler.fallback,
        )

        # Try specific handler first
        handler_found = False
        self._logger.debug("Handler selection: state_type='%s', checking handlers...", state_type)

        if state_type == ALTERNATE_STATE_NONE and hasattr(handler, "none"):
            handler_value = handler.none
            handler_found = True
            self._logger.debug("✓ Using NONE handler: %s", handler_value)
        elif state_type == ALTERNATE_STATE_UNKNOWN and hasattr(handler, "unknown"):
            # Check if unknown handler is explicitly set (not None)
            if handler.unknown is not None:
                handler_value = handler.unknown
                handler_found = True
                self._logger.debug("✓ Using UNKNOWN handler: %s", handler_value)
        elif state_type == ALTERNATE_STATE_UNAVAILABLE and hasattr(handler, "unavailable"):
            # Check if unavailable handler is explicitly set (not None)
            if handler.unavailable is not None:
                handler_value = handler.unavailable
                handler_found = True
                self._logger.debug("✓ Using UNAVAILABLE handler: %s", handler_value)

        # Try FALLBACK handler if no specific handler was found - FALLBACK catches all alternate state types
        if not handler_found and hasattr(handler, "fallback") and handler.fallback is not None:
            handler_value = handler.fallback
            handler_found = True
            self._logger.debug("Using FALLBACK handler for %s state: %s", state_type, handler_value)

        # If no specific handler and no FALLBACK handler, log warning and return None to let sensor become unavailable
        if not handler_found:
            self._logger.warning(
                "No alternate handler defined for %s state (no specific handler, no FALLBACK) - sensor will become unavailable",
                state_type,
            )
            return None

        # Evaluate the handler using the standard formula evaluation pipeline
        return self._evaluate_handler_value(handler_value, context, config, sensor_config)

    def _evaluate_handler_value(
        self,
        handler_value: Any,
        context: HierarchicalContextDict,
        config: FormulaConfig,
        _sensor_config: SensorConfig | None = None,
    ) -> float | str | bool | None:
        """Evaluate alternate state handler value using standard formula pipeline.

        Alternate state handlers are just formulas - they should use the same
        evaluation pipeline as main formulas, attributes, and computed variables.
        """
        result: float | str | bool | None = None
        try:
            # Handle literal values directly
            if handler_value is None:
                result = None
            elif isinstance(handler_value, bool | int | float):
                result = handler_value
            elif isinstance(handler_value, str) and not any(op in handler_value for op in ALL_OPERATORS):
                # Simple string without operators - treat as literal
                result = handler_value
            elif isinstance(handler_value, dict) and "formula" in handler_value:
                # Object form: Use FormulaEvaluatorService directly to avoid recursive pre-evaluation checks
                # Alternate handlers should not go through the full evaluation pipeline
                # since they're already handling an alternate state
                from .formula_evaluator_service import FormulaEvaluatorService

                result = FormulaEvaluatorService.evaluate_formula(
                    handler_value["formula"],
                    handler_value["formula"],
                    context,
                    allow_unresolved_states=True,
                )
            else:
                # String formula or other -> delegate to standard evaluation
                # Alternate state handlers should be able to evaluate formulas with unavailable states
                # since their purpose is to provide fallbacks when states are unavailable
                result = FormulaEvaluatorService.evaluate_formula(
                    str(handler_value),
                    str(handler_value),
                    context,
                    allow_unresolved_states=True,
                )

        except Exception as e:
            self._logger.debug("Alternate handler evaluation failed: %s", str(e))
            # Fallback to literal value for simple types
            result = handler_value if isinstance(handler_value, bool | int | float | str) else None

        return result


# Global instance for use throughout the system
alternate_state_processor = AlternateStateProcessor()
