"""Result creation utilities for formula evaluation."""

from typing import Any, cast

from homeassistant.const import STATE_UNKNOWN

from .constants_alternate import identify_alternate_state_value
from .constants_evaluation_results import (
    ERROR_RESULT_KEYS,
    RESULT_KEY_ERROR,
    RESULT_KEY_MISSING_DEPENDENCIES,
    RESULT_KEY_STATE,
    RESULT_KEY_SUCCESS,
    RESULT_KEY_UNAVAILABLE_DEPENDENCIES,
    RESULT_KEY_VALUE,
    STATE_OK,
    STATE_UNAVAILABLE as EVAL_STATE_UNAVAILABLE,
    SUCCESS_RESULT_KEYS,
)
from .type_definitions import EvaluationResult


class EvaluatorResults:
    """Utilities for creating evaluation results."""

    @staticmethod
    def create_success_result(result: float) -> EvaluationResult:
        """Create a successful evaluation result.

        Args:
            result: The calculated result value

        Returns:
            Success evaluation result
        """
        base_fields = {
            RESULT_KEY_SUCCESS: True,
            RESULT_KEY_VALUE: result,
            RESULT_KEY_STATE: STATE_OK,
        }
        return cast(EvaluationResult, base_fields)

    @staticmethod
    def create_success_result_with_state(state: str, **kwargs: Any) -> EvaluationResult:
        """Create a successful result with specific state (for dependency state reflection).

        Args:
            state: State to set
            **kwargs: Additional fields to include

        Returns:
            Success evaluation result with custom state
        """
        # Build base result using only constants
        base_fields = {
            RESULT_KEY_SUCCESS: True,
            RESULT_KEY_VALUE: None,
            RESULT_KEY_STATE: state,
        }

        # Add valid additional fields
        valid_kwargs = {k: v for k, v in kwargs.items() if k in SUCCESS_RESULT_KEYS}

        return cast(EvaluationResult, {**base_fields, **valid_kwargs})

    @staticmethod
    def create_error_result(error_message: str, state: str = EVAL_STATE_UNAVAILABLE, **kwargs: Any) -> EvaluationResult:
        """Create an error evaluation result.

        Args:
            error_message: Error message
            state: State to set
            **kwargs: Additional fields to include

        Returns:
            Error evaluation result
        """
        # Build base result using only constants
        base_fields = {
            RESULT_KEY_SUCCESS: False,
            RESULT_KEY_ERROR: error_message,
            RESULT_KEY_VALUE: None,
            RESULT_KEY_STATE: state,
        }

        # Add valid additional fields
        valid_kwargs = {k: v for k, v in kwargs.items() if k in ERROR_RESULT_KEYS}

        return cast(EvaluationResult, {**base_fields, **valid_kwargs})

    @staticmethod
    def create_success_from_result(result: float | int | str | bool | None) -> EvaluationResult:
        """Create a success result from a typed evaluation value."""
        # If caller already passed an EvaluationResult-shaped dict, return it unchanged
        if isinstance(result, dict) and RESULT_KEY_SUCCESS in result:
            return cast(EvaluationResult, result)

        # CRITICAL FIX: Handle None values by returning STATE_UNKNOWN with None value
        # This preserves None values for Home Assistant while maintaining proper state handling.
        # Home Assistant will handle None appropriately by converting to STATE_UNKNOWN internally.
        if result is None:
            return EvaluatorResults.create_success_result_with_state(STATE_UNKNOWN, **{RESULT_KEY_VALUE: None})
        # CRITICAL FIX: Check for boolean first, since bool is a subclass of int in Python
        # This prevents True/False from being converted to 1.0/0.0
        if isinstance(result, bool):
            return EvaluatorResults.create_success_result_with_state(STATE_OK, **{RESULT_KEY_VALUE: result})
        if isinstance(result, int | float):
            return EvaluatorResults.create_success_result(float(result))
        # If the result is a string that represents an HA alternate state, preserve HA semantics
        if isinstance(result, str):
            try:
                alt = identify_alternate_state_value(result)
            except Exception:
                alt = False
            if isinstance(alt, str):
                # Preserve original HA state and no numeric value
                return EvaluatorResults.create_success_from_ha_state(result, None)

        return EvaluatorResults.create_success_result_with_state(STATE_OK, **{RESULT_KEY_VALUE: result})

    @staticmethod
    def from_dependency_phase_result(result: dict[str, Any]) -> EvaluationResult:
        """Convert dependency-management phase result to an EvaluationResult shape."""
        if RESULT_KEY_ERROR in result:
            return EvaluatorResults.create_error_result(
                result[RESULT_KEY_ERROR],
                state=result[RESULT_KEY_STATE],
                **{RESULT_KEY_MISSING_DEPENDENCIES: result.get(RESULT_KEY_MISSING_DEPENDENCIES)},
            )
        return EvaluatorResults.create_success_result_with_state(
            result[RESULT_KEY_STATE], **{RESULT_KEY_UNAVAILABLE_DEPENDENCIES: result.get(RESULT_KEY_UNAVAILABLE_DEPENDENCIES)}
        )

    @staticmethod
    def create_success_from_ha_state(
        ha_state_value: str, unavailable_dependencies: list[str] | None = None
    ) -> EvaluationResult:
        """Create a success result that reflects a detected HA state during resolution."""
        # Preserve the original HA state value so callers can inspect the exact
        # Home Assistant-provided state. Note that Home Assistant normally
        # normalizes missing states with None to UNKNOWN.
        # Internal `None` (STATE_NONE) is an internal semantic used by this package
        # (for example to represent YAML-level `STATE_NONE`). For downstream consistency
        # we map an internal None to `STATE_UNKNOWN` here so consumers (entities, tests)
        # observe a stable HA-facing alternate-state representation.
        # Literal HA strings such as 'unavailable' or 'unknown' are preserved
        # unchanged so callers can react to the exact HA-provided value.
        normalized_state = ha_state_value if ha_state_value is not None else STATE_UNKNOWN

        # Normalize dependency representations: accept HADependency objects or strings
        deps = unavailable_dependencies or []
        serialized = []
        for d in deps:
            try:
                serialized.append(str(d))
            except Exception:
                serialized.append(d)

        return EvaluatorResults.create_success_result_with_state(
            normalized_state, **{RESULT_KEY_VALUE: None, RESULT_KEY_UNAVAILABLE_DEPENDENCIES: serialized}
        )
