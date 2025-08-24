"""Core helper functions extracted from Evaluator to reduce module complexity.

These functions are thin wrappers that implement logic previously inside
`Evaluator` methods so the main `evaluator.py` module shrinks in size and
complexity for linting.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from .evaluation_common import (
    check_dependency_management_conditions,
    handle_evaluation_exception,
    process_alternate_state_result,
)
from .evaluator_results import EvaluatorResults
from .type_definitions import EvaluationResult

_LOGGER = logging.getLogger(__name__)


def process_early_result(
    evaluator: Any, resolution_result: Any, config: Any, eval_context: dict[str, Any], sensor_config: Any
) -> EvaluationResult:
    """Process an early result detected during variable resolution.

    This consolidates alternate-state handling in Phase 4.
    """
    return process_alternate_state_result(
        result=getattr(resolution_result, "early_result", None),
        config=config,
        eval_context=eval_context,
        sensor_config=sensor_config,
        core_evaluator=evaluator.execution_engine.core_evaluator,
        resolve_all_references_in_formula=evaluator.resolve_all_references_in_formula,
        pre_eval=True,
    )


def should_use_dependency_management(
    evaluator: Any, sensor_config: Any, context: Any, bypass_dependency_management: bool, config: Any
) -> bool:
    """Determine whether dependency-aware evaluation should be used.

    Lightweight wrapper to allow extraction from large module.
    """
    if not check_dependency_management_conditions(sensor_config, context, bypass_dependency_management):
        return False
    # Delegate to evaluator's existing private check
    # Guard return to bool to satisfy strict typing when evaluator internals are untyped
    return bool(evaluator.needs_dependency_resolution(config, sensor_config))


def evaluate_formula_normally(
    evaluator: Any, config: Any, eval_context: dict[str, Any], context: Any, sensor_config: Any, formula_name: str
) -> EvaluationResult:
    """Evaluate formula using the normal evaluation path and finalize result."""
    result_value = evaluator.execute_formula_evaluation(config, eval_context, context, config.id, sensor_config)
    evaluator.error_handler.handle_successful_evaluation(formula_name)

    # Cache numeric results
    if isinstance(result_value, float | int):
        evaluator.cache_handler.cache_result(config, eval_context, config.id, float(result_value))

    return EvaluatorResults.create_success_from_result(result_value)


def evaluate_with_dependency_management(
    evaluator: Any, config: Any, context: dict[str, Any], sensor_config: Any
) -> EvaluationResult:
    """Evaluate a formula using dependency manager (extracted helper).

    This function encapsulates the logic of building a complete context via
    the generic dependency manager and then evaluating the formula.
    """
    try:
        complete_context = evaluator.generic_dependency_manager.build_evaluation_context(
            sensor_config=sensor_config, evaluator=evaluator, base_context=context
        )

        formula_name = config.name or config.id

        check_result, eval_context = evaluator.perform_pre_evaluation_checks(
            config, complete_context, sensor_config, formula_name
        )
        if check_result is not None:
            return cast(EvaluationResult, check_result)

        if eval_context is None:
            return EvaluatorResults.create_error_result("Failed to build evaluation context", state="unknown")

        result = evaluator.execute_formula_evaluation(config, eval_context, complete_context, config.id, sensor_config)

        evaluator.error_handler.handle_successful_evaluation(formula_name)
        return EvaluatorResults.create_success_from_result(result)

    except Exception as e:
        handle_evaluation_exception(e, config, formula_name)
        # Fallback may be untyped; cast to EvaluationResult for strict typing
        return cast(EvaluationResult, evaluator.fallback_to_normal_evaluation(config, context, sensor_config))
