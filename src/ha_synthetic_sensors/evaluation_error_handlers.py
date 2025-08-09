"""Evaluation error handling helpers.

These helpers focus on mapping known exceptions
to standardized EvaluationResult payloads.
"""

from __future__ import annotations

import logging

from .constants_error_strings import ERR_DIV_ZERO, ERR_EVAL, ERR_EVAL_FAILED, ERR_NONE_VALUES, ERR_UNDEFINED_VAR
from .evaluator_error_handler import EvaluatorErrorHandler
from .evaluator_results import EvaluatorResults
from .exceptions import BackingEntityResolutionError
from .type_definitions import EvaluationResult

_LOGGER = logging.getLogger(__name__)


def handle_value_error(error: ValueError, formula_name: str, error_handler: EvaluatorErrorHandler) -> EvaluationResult:
    """Handle ValueError exceptions during formula evaluation."""
    error_msg = str(error)

    # Formula evaluation failures due to None values
    if ERR_NONE_VALUES in error_msg:
        _LOGGER.warning("Formula '%s': %s", formula_name, error_msg)
        error_handler.increment_error_count(formula_name)
        return EvaluatorResults.create_success_result_with_state("unavailable", value="unavailable")

    # Mathematical and evaluation errors
    if any(phrase in error_msg for phrase in [ERR_DIV_ZERO, ERR_UNDEFINED_VAR, ERR_EVAL, ERR_EVAL_FAILED]):
        _LOGGER.warning("Formula '%s': %s", formula_name, error_msg)
        error_handler.increment_error_count(formula_name)
        return EvaluatorResults.create_error_result(error_msg, state="unavailable")

    # Re-raise other ValueError exceptions for caller to handle
    raise error


def handle_backing_entity_error(
    error: BackingEntityResolutionError, formula_name: str, error_handler: EvaluatorErrorHandler
) -> EvaluationResult:
    """Handle BackingEntityResolutionError exceptions."""
    error_handler.increment_error_count(formula_name)
    return EvaluatorResults.create_error_result(str(error), state="unavailable")
