"""Error handling and circuit breaker logic for formula evaluation."""

import logging

from .evaluator_config import CircuitBreakerConfig, RetryConfig
from .evaluator_results import EvaluatorResults
from .exceptions import is_fatal_error, is_retriable_error
from .type_definitions import EvaluationResult

_LOGGER = logging.getLogger(__name__)


class EvaluatorErrorHandler:
    """Handles error classification, circuit breaker logic, and error counting."""

    def __init__(self, circuit_breaker_config: CircuitBreakerConfig, retry_config: RetryConfig):
        """Initialize the error handler.

        Args:
            circuit_breaker_config: Circuit breaker configuration
            retry_config: Retry configuration for transitory errors
        """
        self._circuit_breaker_config = circuit_breaker_config
        self._retry_config = retry_config

        # TIER 1: Fatal Error Circuit Breaker (Traditional Pattern)
        # Tracks configuration errors, syntax errors, missing entities, etc.
        self._error_count: dict[str, int] = {}

        # TIER 2: Transitory Error Tracking (Intelligent Resilience)
        # Tracks temporary issues like unknown/unavailable entity states.
        self._transitory_error_count: dict[str, int] = {}

    def handle_evaluation_error(self, err: Exception, formula_name: str) -> EvaluationResult:
        """Handle evaluation errors with appropriate error classification.

        Args:
            err: The exception that occurred
            formula_name: Name of the formula that failed

        Returns:
            Error evaluation result
        """
        if is_fatal_error(err):
            return self._handle_fatal_error(err, formula_name)
        if is_retriable_error(err):
            return self._handle_retriable_error(err, formula_name)
        return self._handle_unknown_error(err, formula_name)

    def _handle_fatal_error(self, err: Exception, formula_name: str) -> EvaluationResult:
        """Handle fatal errors (configuration issues, syntax errors, etc.).

        Args:
            err: The fatal exception
            formula_name: Name of the formula that failed

        Returns:
            Error evaluation result
        """
        error_msg = f"Fatal error in formula '{formula_name}': {err}"
        _LOGGER.error(error_msg)
        self.increment_error_count(formula_name)
        return EvaluatorResults.create_error_result(error_msg, state="unavailable")

    def _handle_retriable_error(self, err: Exception, formula_name: str) -> EvaluationResult:
        """Handle retriable errors (temporary issues, network problems, etc.).

        Args:
            err: The retriable exception
            formula_name: Name of the formula that failed

        Returns:
            Error evaluation result
        """
        error_msg = f"Retriable error in formula '{formula_name}': {err}"
        _LOGGER.warning(error_msg)
        self.increment_transitory_error_count(formula_name)
        return EvaluatorResults.create_error_result(error_msg, state="unknown")

    def _handle_unknown_error(self, err: Exception, formula_name: str) -> EvaluationResult:
        """Handle unknown errors (unclassified exceptions).

        Args:
            err: The unknown exception
            formula_name: Name of the formula that failed

        Returns:
            Error evaluation result
        """
        error_msg = f"Unknown error in formula '{formula_name}': {err}"
        _LOGGER.error(error_msg)
        self.increment_transitory_error_count(formula_name)
        return EvaluatorResults.create_error_result(error_msg, state="unknown")

    def should_skip_evaluation(self, formula_name: str) -> bool:
        """Check if evaluation should be skipped due to circuit breaker.

        Args:
            formula_name: Name of the formula to check

        Returns:
            True if evaluation should be skipped
        """
        error_count = self._error_count.get(formula_name, 0)
        should_skip = error_count >= self._circuit_breaker_config.max_fatal_errors

        if should_skip:
            _LOGGER.debug(
                "Formula '%s': Skipping evaluation due to circuit breaker (errors: %d/%d)",
                formula_name,
                error_count,
                self._circuit_breaker_config.max_fatal_errors,
            )

        return should_skip

    def increment_error_count(self, formula_name: str) -> None:
        """Increment error count for a formula.

        Args:
            formula_name: Name of the formula
        """
        current_count = self._error_count.get(formula_name, 0)
        new_count = current_count + 1
        self._error_count[formula_name] = new_count

        _LOGGER.debug(
            "Formula '%s': Error count: %d/%d (threshold: %d)",
            formula_name,
            new_count,
            self._circuit_breaker_config.max_fatal_errors,
            self._circuit_breaker_config.max_fatal_errors,
        )

        if new_count >= self._circuit_breaker_config.max_fatal_errors:
            _LOGGER.warning(
                "Formula '%s': Circuit breaker triggered after %d errors",
                formula_name,
                new_count,
            )

    def increment_transitory_error_count(self, formula_name: str) -> None:
        """Increment transitory error count for a formula.

        Args:
            formula_name: Name of the formula
        """
        current_count = self._transitory_error_count.get(formula_name, 0)
        new_count = current_count + 1
        self._transitory_error_count[formula_name] = new_count

        _LOGGER.debug(
            "Formula '%s': Transitory error count: %d/%d (threshold: %d)",
            formula_name,
            new_count,
            self._retry_config.max_attempts,
            self._retry_config.max_attempts,
        )

        # Log warning if approaching retry limit but don't trigger circuit breaker
        if new_count >= self._retry_config.max_attempts:
            _LOGGER.warning(
                "Formula '%s': Reached transitory error limit (%d), but continuing evaluation attempts",
                formula_name,
                self._retry_config.max_attempts,
            )

    def handle_successful_evaluation(self, formula_name: str) -> None:
        """Reset error counters on successful evaluation.

        Args:
            formula_name: Name of the formula that succeeded
        """
        self._error_count.pop(formula_name, None)
        self._transitory_error_count.pop(formula_name, None)

    def get_error_counts(self) -> dict[str, int]:
        """Get current error counts for all formulas.

        Returns:
            Dictionary mapping formula names to error counts
        """
        return self._error_count.copy()
