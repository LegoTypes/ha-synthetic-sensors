"""Result creation utilities for formula evaluation."""

from typing import Any, cast

from homeassistant.const import STATE_UNKNOWN

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
        # Home Assistant-provided state. Special-case: if the HA-provided value is
        # None, represent that as STATE_NONE (internal None) to signal an explicit
        # None state. Do NOT normalize 'unavailable' or 'unknown' to STATE_UNKNOWN
        # here; upstream code or callers should decide how to handle those values.
        from .constants_alternate import STATE_NONE

        normalized_state = ha_state_value if ha_state_value is not None else STATE_NONE

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
