"""Result creation utilities for formula evaluation."""

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

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
        return {
            "success": True,
            "value": result,
            "state": "ok",
        }

    @staticmethod
    def create_success_result_with_state(state: str, **kwargs: Any) -> EvaluationResult:
        """Create a successful result with specific state (for dependency state reflection).

        Args:
            state: State to set
            **kwargs: Additional fields to include

        Returns:
            Success evaluation result with custom state
        """
        result: EvaluationResult = {
            "success": True,
            "value": None,
            "state": state,
        }
        # Add any additional fields from kwargs
        for key, value in kwargs.items():
            if key in ["unavailable_dependencies", "missing_dependencies", "value"]:
                result[key] = value  # type: ignore[literal-required]
        return result

    @staticmethod
    def create_error_result(error_message: str, state: str = "unavailable", **kwargs: Any) -> EvaluationResult:
        """Create an error evaluation result.

        Args:
            error_message: Error message
            state: State to set
            **kwargs: Additional fields to include

        Returns:
            Error evaluation result
        """
        result: EvaluationResult = {
            "success": False,
            "error": error_message,
            "value": None,
            "state": state,
        }
        # Add any additional fields from kwargs that are valid for EvaluationResult
        for key, value in kwargs.items():
            if key in ["cached", "unavailable_dependencies", "missing_dependencies"]:
                result[key] = value  # type: ignore[literal-required]
        return result

    @staticmethod
    def create_success_from_result(result: float | int | str | bool) -> EvaluationResult:
        """Create a success result from a typed evaluation value."""
        if isinstance(result, int | float):
            return EvaluatorResults.create_success_result(float(result))
        return EvaluatorResults.create_success_result_with_state("ok", value=result)

    @staticmethod
    def from_dependency_phase_result(result: dict[str, Any]) -> EvaluationResult:
        """Convert dependency-management phase result to an EvaluationResult shape."""
        if "error" in result:
            return EvaluatorResults.create_error_result(
                result["error"], state=result["state"], missing_dependencies=result.get("missing_dependencies")
            )
        return EvaluatorResults.create_success_result_with_state(
            result["state"], unavailable_dependencies=result.get("unavailable_dependencies")
        )

    @staticmethod
    def create_success_from_ha_state(
        ha_state_value: str, unavailable_dependencies: list[str] | None = None
    ) -> EvaluationResult:
        """Create a success result that reflects a detected HA state during resolution."""
        # According to design guide, all unavailable states default to STATE_UNKNOWN
        # Normalize the state value - all problematic states become STATE_UNKNOWN
        normalized_state = (
            STATE_UNKNOWN if ha_state_value in [STATE_UNAVAILABLE, STATE_UNKNOWN] or ha_state_value is None else ha_state_value
        )

        return EvaluatorResults.create_success_result_with_state(
            normalized_state,
            value=None,
            unavailable_dependencies=unavailable_dependencies or [],
        )
