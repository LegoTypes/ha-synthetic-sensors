"""Helpers to evaluate alternate state handlers in a centralized place.

These helpers reduce branching in callers and keep logic consistent between
sensor-level alternates (formula pipeline) and computed-variable alternates
(enhanced simpleeval path).
"""

from __future__ import annotations

from typing import Any

from .config_models import FormulaConfig, SensorConfig
from .evaluator_helpers import EvaluatorHelpers


def evaluate_formula_alternate(
    handler_formula: Any,
    eval_context: dict[str, Any],
    sensor_config: SensorConfig | None,
    config: FormulaConfig,
    handler_factory: Any,
    resolve_all_references_in_formula: Any,
) -> bool | str | float | int | None:
    """Evaluate sensor-level alternate handler for a formula.

    Supports literal, object form {formula, variables}, or string expression.
    """
    # Literal value
    if isinstance(handler_formula, bool | int | float):
        return handler_formula

    # Object form with local variables
    if isinstance(handler_formula, dict) and "formula" in handler_formula:
        local_vars = handler_formula.get("variables") or {}
        temp_context = eval_context.copy()
        if isinstance(local_vars, dict):
            for key, val in local_vars.items():
                temp_context[key] = val

        resolved_handler_formula = resolve_all_references_in_formula(
            str(handler_formula["formula"]), sensor_config, temp_context, config
        )
        handler = handler_factory.get_handler_for_formula(resolved_handler_formula)
        if handler:
            result = handler.evaluate(resolved_handler_formula, temp_context)
        else:
            numeric_handler = handler_factory.get_handler("numeric")
            if not numeric_handler:
                return None
            result = numeric_handler.evaluate(resolved_handler_formula, temp_context)
        return EvaluatorHelpers.process_evaluation_result(result)

    # String expression (back-compat)
    resolved_handler_formula = resolve_all_references_in_formula(str(handler_formula), sensor_config, eval_context, config)
    handler = handler_factory.get_handler_for_formula(resolved_handler_formula)
    if handler:
        result = handler.evaluate(resolved_handler_formula, eval_context)
    else:
        numeric_handler = handler_factory.get_handler("numeric")
        if not numeric_handler:
            return None
        result = numeric_handler.evaluate(resolved_handler_formula, eval_context)
    return EvaluatorHelpers.process_evaluation_result(result)


def evaluate_computed_alternate(
    handler_formula: Any,
    eval_context: dict[str, Any],
    get_enhanced_helper: Any,
    extract_values_for_simpleeval: Any,
) -> bool | str | float | int | None:
    """Evaluate computed-variable alternate using enhanced SimpleEval path.

    Supports literal, object form {formula, variables}, or string expression.
    """
    # Literal value
    if isinstance(handler_formula, bool | int | float):
        return handler_formula

    enhanced_helper = get_enhanced_helper()

    # Object form with local variables
    if isinstance(handler_formula, dict) and "formula" in handler_formula:
        local_vars = handler_formula.get("variables") or {}
        temp_context = eval_context.copy()
        if isinstance(local_vars, dict):
            for key, val in local_vars.items():
                temp_context[key] = val
        enhanced_context = extract_values_for_simpleeval(temp_context)
        success, result = enhanced_helper.try_enhanced_eval(str(handler_formula["formula"]), enhanced_context)
        if success:
            return EvaluatorHelpers.process_evaluation_result(result)
        return None

    # String expression (back-compat)
    enhanced_context = extract_values_for_simpleeval(eval_context)
    success, result = enhanced_helper.try_enhanced_eval(str(handler_formula), enhanced_context)
    if success:
        return EvaluatorHelpers.process_evaluation_result(result)
    return None
