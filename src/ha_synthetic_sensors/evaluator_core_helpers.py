"""Core helper functions extracted from Evaluator to reduce module complexity.

These functions are thin wrappers that implement logic previously inside
`Evaluator` methods so the main `evaluator.py` module shrinks in size and
complexity for linting.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, cast
from .type_definitions import EvaluationResult
from .exceptions import MissingDependencyError, DataValidationError, SensorMappingError

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import STATE_UNKNOWN

from .alternate_state_processor import alternate_state_processor
from .constants_alternate import identify_alternate_state_value
from .evaluator_results import EvaluatorResults
from .evaluator_helpers import EvaluatorHelpers

_LOGGER = logging.getLogger(__name__)


def process_early_result(
    evaluator: Any, resolution_result: Any, config: Any, eval_context: dict[str, Any], sensor_config: Any
) -> EvaluationResult:
    """Process an early result detected during variable resolution.

    This consolidates alternate-state handling in Phase 4.
    """
    processed_result = alternate_state_processor.process_evaluation_result(
        result=getattr(resolution_result, "early_result", None),
        exception=None,
        context=eval_context,
        config=config,
        sensor_config=sensor_config,
        core_evaluator=evaluator._execution_engine.core_evaluator,
        resolve_all_references_in_formula=evaluator._resolve_all_references_in_formula,
        pre_eval=True,
    )

    normalized = EvaluatorHelpers.process_evaluation_result(processed_result)
    return EvaluatorResults.create_success_from_result(normalized)


def should_use_dependency_management(
    evaluator: Any, sensor_config: Any, context: Any, bypass_dependency_management: bool, config: Any
) -> bool:
    """Determine whether dependency-aware evaluation should be used.

    Lightweight wrapper to allow extraction from large module.
    """
    if not sensor_config or not context or bypass_dependency_management:
        return False
    # Delegate to evaluator's existing private check
    # Guard return to bool to satisfy strict typing when evaluator internals are untyped
    return bool(evaluator._needs_dependency_resolution(config, sensor_config))


def evaluate_formula_normally(
    evaluator: Any, config: Any, eval_context: dict[str, Any], context: Any, sensor_config: Any, formula_name: str
) -> EvaluationResult:
    """Evaluate formula using the normal evaluation path and finalize result."""
    result_value = evaluator._execute_formula_evaluation(config, eval_context, context, config.id, sensor_config)
    evaluator._error_handler.handle_successful_evaluation(formula_name)

    # Cache numeric results
    if isinstance(result_value, (float, int)):
        evaluator._cache_handler.cache_result(config, eval_context, config.id, float(result_value))

    return EvaluatorResults.create_success_from_result(result_value)


def evaluate_with_dependency_management(evaluator: Any, config: Any, context: dict[str, Any], sensor_config: Any) -> EvaluationResult:
    """Evaluate a formula using dependency manager (extracted helper).

    This function encapsulates the logic of building a complete context via
    the generic dependency manager and then evaluating the formula.
    """
    try:
        complete_context = evaluator._generic_dependency_manager.build_evaluation_context(
            sensor_config=sensor_config, evaluator=evaluator, base_context=context
        )

        formula_name = config.name or config.id

        check_result, eval_context = evaluator._perform_pre_evaluation_checks(config, complete_context, sensor_config, formula_name)
        if check_result is not None:
            return cast(EvaluationResult, check_result)

        if eval_context is None:
            return EvaluatorResults.create_error_result("Failed to build evaluation context", state="unknown")

        result = evaluator._execute_formula_evaluation(config, eval_context, complete_context, config.id, sensor_config)

        evaluator._error_handler.handle_successful_evaluation(formula_name)
        return EvaluatorResults.create_success_from_result(result)

    except Exception as e:
        _LOGGER.error("Error in dependency-aware evaluation for formula '%s': %s", config.formula, e)
        if isinstance(e, (MissingDependencyError, DataValidationError, SensorMappingError)):
            raise
        # Fallback may be untyped; cast to EvaluationResult for strict typing
        return cast(EvaluationResult, evaluator._fallback_to_normal_evaluation(config, context, sensor_config))


