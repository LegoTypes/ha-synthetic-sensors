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
    core_evaluator: Any,
    resolve_all_references_in_formula: Any,
) -> bool | str | float | int | None:
    """Evaluate sensor-level alternate handler for a formula.

    Supports literal values or object form {formula, variables}.
    """

    # Handle None values first
    if handler_formula is None:
        return None

    # Literal value (including strings)
    if isinstance(handler_formula, bool | int | float | str):
        # For strings, only evaluate if they look like formulas (contain operators or variables)
        # Simple strings should be returned as literals
        if isinstance(handler_formula, str):
            # If it's a simple string without operators, treat as literal
            if not any(op in handler_formula for op in ["+", "-", "*", "/", "(", ")", "<", ">", "=", " and ", " or ", " not "]):
                return handler_formula
            # If it's a quoted string, treat as literal
            if (handler_formula.startswith('"') and handler_formula.endswith('"')) or (
                handler_formula.startswith("'") and handler_formula.endswith("'")
            ):
                return handler_formula[1:-1]  # Remove quotes
        else:
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
        # Use the normal evaluation path through CoreFormulaEvaluator
        original_formula = str(handler_formula["formula"])
        result = core_evaluator.evaluate_formula(resolved_handler_formula, original_formula, temp_context)
        return EvaluatorHelpers.process_evaluation_result(result)

    # If we get here, it's an unsupported handler format
    return None


def evaluate_computed_alternate(
    handler_formula: Any,
    eval_context: dict[str, Any],
    get_enhanced_helper: Any,
    extract_values_for_simpleeval: Any,
) -> bool | str | float | int | None:
    """Evaluate computed-variable alternate using enhanced SimpleEval path.

    Supports literal values or object form {formula, variables}.
    """
    # Handle None values first
    if handler_formula is None:
        return None

    # Literal value (including strings)
    if isinstance(handler_formula, bool | int | float | str):
        # For strings, only evaluate if they look like formulas (contain operators or variables)
        # Simple strings should be returned as literals
        if isinstance(handler_formula, str):
            # If it's a simple string without operators, treat as literal
            if not any(op in handler_formula for op in ["+", "-", "*", "/", "(", ")", "<", ">", "=", " and ", " or ", " not "]):
                # Try to convert numeric strings to their appropriate types
                if handler_formula.isdigit():
                    return int(handler_formula)
                try:
                    # Try float conversion for decimal numbers
                    if "." in handler_formula and handler_formula.replace(".", "").replace("-", "").isdigit():
                        return float(handler_formula)
                except ValueError:
                    pass
                return handler_formula
            # If it's a quoted string, treat as literal
            if (handler_formula.startswith('"') and handler_formula.endswith('"')) or (
                handler_formula.startswith("'") and handler_formula.endswith("'")
            ):
                return handler_formula[1:-1]  # Remove quotes
        else:
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

    # If we get here, it's an unsupported handler format
    return None
