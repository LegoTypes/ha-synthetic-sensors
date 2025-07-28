"""Result creation utilities for formula evaluation."""

from typing import Any

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
