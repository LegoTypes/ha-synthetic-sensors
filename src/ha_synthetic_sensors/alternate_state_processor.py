"""Comprehensive alternate state handler processor.

This module implements the two-phase alternate state handler system:
1. Pre-evaluation optimization for single alternate states
2. Post-evaluation processing for results and exceptions
"""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import STATE_UNKNOWN

from .config_models import AlternateStateHandler, FormulaConfig, SensorConfig
from .constants_alternate import (
    ALTERNATE_STATE_NONE,
    ALTERNATE_STATE_UNAVAILABLE,
    ALTERNATE_STATE_UNKNOWN,
    identify_alternate_state_value,
)
from .formula_evaluator_service import FormulaEvaluatorService
from .type_definitions import ReferenceValue

_LOGGER = logging.getLogger(__name__)


class AlternateStateProcessor:
    """Processes alternate state handlers with pre and post evaluation checks."""

    def __init__(self) -> None:
        """Initialize the alternate state processor."""
        self._logger = _LOGGER.getChild(self.__class__.__name__)

    def check_pre_evaluation_states(
        self,
        context: dict[str, Any],
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
        if not config.alternate_state_handler:
            return None

        # Check if we have a simple single-variable case
        if len(context) != 1:
            return False

        # Get the single variable value
        var_name, var_value = next(iter(context.items()))

        # Check if it's an alternate state that should trigger handlers
        # Use the shared helper mapping contract: returns a string for detected alternate
        # states or False when no alternate state is detected. Preserve that
        # contract here so callers can distinguish a legitimate None handler
        # result from "no alternate state detected".
        # If the context contains ReferenceValue wrappers, unwrap to the raw value
        raw_val = var_value.value if isinstance(var_value, ReferenceValue) else var_value
        alternate_state = identify_alternate_state_value(raw_val)
        self._logger.debug(
            "Pre-evaluation check: Single variable '%s' = %s (raw_val: %s, type: %s), alternate_state = %s",
            var_name,
            var_value,
            raw_val,
            type(raw_val).__name__,
            alternate_state,
        )
        # The helper returns False when no alternate state detected
        if alternate_state is False:
            return False

        self._logger.debug(
            "Pre-evaluation optimization: Single variable '%s' is %s, triggering alternate handler", var_name, alternate_state
        )

        # Trigger the appropriate alternate state handler
        return self._trigger_alternate_handler(
            cast(str, alternate_state),
            config.alternate_state_handler,
            context,
            config,
            sensor_config,
            core_evaluator,
            resolve_all_references_in_formula,
        )

    def process_evaluation_result(
        self,
        result: float | str | bool | None,
        exception: Exception | None,
        context: dict[str, Any],
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

        if not config.alternate_state_handler:
            return result if exception is None else None

        # Handle None results - distinguish between legitimate None values and missing state guards
        # If this was a pre-evaluation handler result, preserve literal None
        if exception is None and result is None:
            if pre_eval:
                # Handler explicitly returned None to preserve STATE_NONE semantics
                self._logger.debug("Pre-eval handler returned explicit None; preserving None result")
                return None

            # Check if this None result came from a legitimate None value (should trigger NONE handler)
            # vs. a missing state guard (should trigger UNAVAILABLE handler)
            # If any context variable contains a legitimate None value, this should be NONE
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
                res = self._trigger_alternate_handler(
                    ALTERNATE_STATE_NONE,
                    config.alternate_state_handler,
                    context,
                    config,
                    sensor_config,
                    core_evaluator,
                    resolve_all_references_in_formula,
                )

                return res
            else:
                self._logger.debug("Evaluation returned None (missing state guard), triggering UNAVAILABLE alternate handler")
                res = self._trigger_alternate_handler(
                    ALTERNATE_STATE_UNAVAILABLE,
                    config.alternate_state_handler,
                    context,
                    config,
                    sensor_config,
                    core_evaluator,
                    resolve_all_references_in_formula,
                )

                return res

        # Handle exceptions - map to appropriate alternate state
        if exception is not None:
            # Map exception types to alternate states
            exception_str = str(exception).lower()
            if STATE_UNAVAILABLE in exception_str:
                alternate_state = ALTERNATE_STATE_UNAVAILABLE
            elif STATE_UNKNOWN in exception_str:
                alternate_state = ALTERNATE_STATE_UNKNOWN
            else:
                # Default to none for other exceptions
                alternate_state = ALTERNATE_STATE_NONE

            self._logger.debug(
                "Evaluation exception occurred: %s, mapping to %s state and triggering alternate handler",
                str(exception),
                alternate_state,
            )
            res = self._trigger_alternate_handler(
                alternate_state,
                config.alternate_state_handler,
                context,
                config,
                sensor_config,
                core_evaluator,
                resolve_all_references_in_formula,
            )

            return res

        # Handle successful results that are alternate states
        # _identify_alternate_state follows the shared helper contract and returns
        # a string identifying the alternate state or False when no alternate state is detected.
        result_alternate_state = self._identify_alternate_state(result)
        # Only proceed if the helper did not return False (i.e., an alternate state was detected)
        if result_alternate_state is not False:
            self._logger.debug("Evaluation result is %s, triggering alternate handler", result_alternate_state)
            return self._trigger_alternate_handler(
                cast(str, result_alternate_state),
                config.alternate_state_handler,
                context,
                config,
                sensor_config,
                core_evaluator,
                resolve_all_references_in_formula,
            )

        # Normal result, no alternate state handling needed
        return result

    def _identify_alternate_state(self, value: Any) -> str | bool:
        """Delegate alternate state detection to shared helper."""
        # Use the shared helper function to detect HA special states
        alt = identify_alternate_state_value(value)
        # Preserve the shared helper's contract: return string for detected state or False when none
        return alt

    def _trigger_alternate_handler(
        self,
        state_type: str,
        handler: AlternateStateHandler,
        context: dict[str, Any],
        config: FormulaConfig,
        sensor_config: SensorConfig | None = None,
        core_evaluator: Any | None = None,
        resolve_all_references_in_formula: Any | None = None,
    ) -> float | str | bool | None:
        """Trigger the appropriate alternate state handler.

        Args:
            state_type: The type of alternate state (none, unknown, unavailable)
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

        self._logger.debug(
            "Handler selection for state_type='%s': none=%s, unknown=%s, unavailable=%s, fallback=%s",
            state_type,
            handler.none,
            handler.unknown,
            handler.unavailable,
            handler.fallback,
        )

        # Try specific handler first
        # CRITICAL FIX: Check if handler is explicitly set, not just non-None
        # This allows None as a valid handler value (important for energy sensors)
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
        context: dict[str, Any],
        config: FormulaConfig,
        _sensor_config: SensorConfig | None = None,
    ) -> float | str | bool | None:
        """Evaluate alternate state handler value using standard formula pipeline.

        Alternate state handlers are just formulas - they should use the same
        evaluation pipeline as main formulas, attributes, and computed variables.
        """
        try:
            # Handle literal values directly
            if handler_value is None:
                return None  # Preserve None explicitly
            if isinstance(handler_value, bool | int | float):
                return handler_value
            if isinstance(handler_value, str) and not any(
                op in handler_value for op in ["+", "-", "*", "/", "(", ")", "<", ">", "=", " and ", " or ", " not "]
            ):
                # Simple string without operators - treat as literal
                return handler_value

            # For formulas (string or object form), use the standard evaluation pipeline
            if isinstance(handler_value, dict) and "formula" in handler_value:
                # Object form: create temporary FormulaConfig and use standard pipeline
                handler_config = FormulaConfig(
                    id=f"{config.id}_alt_handler",
                    formula=handler_value["formula"],
                    variables=handler_value.get("variables", {}),
                )

                # Merge contexts: base context + handler-specific variables
                merged_context = dict(context) if context else {}
                for key, value in handler_config.variables.items():
                    merged_context[key] = value

                # Delegate to standard formula evaluation
                return FormulaEvaluatorService.evaluate_formula(
                    handler_config.formula,
                    handler_config.formula,
                    merged_context,
                    allow_unresolved_states=False,
                )
            else:
                # String formula - delegate to standard evaluation
                return FormulaEvaluatorService.evaluate_formula(
                    str(handler_value),
                    str(handler_value),
                    context,
                    allow_unresolved_states=False,
                )

        except Exception as e:
            self._logger.debug("Alternate handler evaluation failed: %s", str(e))
            # Fallback to literal value for simple types
            if isinstance(handler_value, bool | int | float | str):
                return handler_value
            return None


# Global instance for use throughout the system
alternate_state_processor = AlternateStateProcessor()
