"""Helpers to evaluate alternate state handlers in a centralized place.

These helpers reduce branching in callers and keep logic consistent between
sensor-level alternates (formula pipeline) and computed-variable alternates
(enhanced simpleeval path).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .config_models import FormulaConfig, SensorConfig
from .constants_formula import ALL_OPERATORS
from .evaluator_helpers import EvaluatorHelpers

if TYPE_CHECKING:
    from .hierarchical_context_dict import HierarchicalContextDict


def _looks_like_formula(s: str) -> bool:
    """Return True if a string appears to be a formula/expression."""

    return any(op in s for op in ALL_OPERATORS)


def _strip_quotes(s: str) -> str:
    """If string is quoted, return inner content, otherwise return original."""
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


def _try_convert_numeric(s: str) -> Any:
    """Attempt to convert a numeric-looking string to int or float, otherwise return original."""
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        try:
            return int(s)
        except ValueError:
            pass
    if "." in s and s.replace(".", "").replace("-", "").isdigit():
        # safe float conversion when string structure is numeric
        try:
            return float(s)
        except ValueError:
            # Fall through to returning original string
            return s
    return s


def evaluate_formula_alternate(
    handler_formula: Any,
    eval_context: HierarchicalContextDict,
    sensor_config: SensorConfig | None,
    config: FormulaConfig,
    core_evaluator: Any,
    resolve_all_references_in_formula: Any,
) -> bool | str | float | int | None:
    """Evaluate sensor-level alternate handler for a formula.

    Supports literal values or object form {formula, variables}.
    """

    result_value: bool | str | float | int | None = None

    if handler_formula is None:
        return None

    # Literal values including numeric and boolean
    if isinstance(handler_formula, bool | int | float):
        result_value = handler_formula
    elif isinstance(handler_formula, str):
        # Quoted strings should be treated as literals
        if (handler_formula.startswith('"') and handler_formula.endswith('"')) or (
            handler_formula.startswith("'") and handler_formula.endswith("'")
        ):
            result_value = _strip_quotes(handler_formula)
        elif not _looks_like_formula(handler_formula):
            # Simple non-formula string -> literal
            result_value = handler_formula
        else:
            # It's a formula-like string; fall through to evaluation path by wrapping
            handler_formula = {"formula": handler_formula}

    # Object form with local variables
    if isinstance(handler_formula, dict) and "formula" in handler_formula:
        local_vars = handler_formula.get("variables") or {}
        # Use hierarchical context layering instead of copying
        if isinstance(local_vars, dict):
            eval_context.get_hierarchical_context().push_layer("alternate_handler", local_vars)

        resolved_handler_formula = resolve_all_references_in_formula(
            str(handler_formula["formula"]), sensor_config, eval_context, config
        )
        # Use the normal evaluation path through CoreFormulaEvaluator
        original_formula = str(handler_formula["formula"])
        eval_result = core_evaluator.evaluate_formula(resolved_handler_formula, original_formula, eval_context)
        result_value = EvaluatorHelpers.process_evaluation_result(eval_result)

    return result_value


def evaluate_computed_alternate(
    handler_formula: Any,
    eval_context: HierarchicalContextDict,
    get_enhanced_helper: Any,
    extract_values_for_simpleeval: Any,
) -> bool | str | float | int | None:
    """Evaluate computed-variable alternate using enhanced SimpleEval path.

    Supports literal values or object form {formula, variables}.
    """
    result_value: bool | str | float | int | None = None

    if handler_formula is None:
        return None

    # Literal numeric/bool
    if isinstance(handler_formula, bool | int | float):
        result_value = handler_formula
    elif isinstance(handler_formula, str):
        # Quoted literal
        if (handler_formula.startswith('"') and handler_formula.endswith('"')) or (
            handler_formula.startswith("'") and handler_formula.endswith("'")
        ):
            result_value = _strip_quotes(handler_formula)
        elif not _looks_like_formula(handler_formula):
            # Try numeric conversion for numeric-like strings
            result_value = _try_convert_numeric(handler_formula)
        else:
            # It's a formula-like string; wrap for evaluation
            handler_formula = {"formula": handler_formula}

    enhanced_helper = get_enhanced_helper()

    if isinstance(handler_formula, dict) and "formula" in handler_formula:
        local_vars = handler_formula.get("variables") or {}
        # Use hierarchical context layering instead of copying
        if isinstance(local_vars, dict):
            eval_context.get_hierarchical_context().push_layer("alternate_handler", local_vars)
        enhanced_context = extract_values_for_simpleeval(eval_context)
        success, result = enhanced_helper.try_enhanced_eval(str(handler_formula["formula"]), enhanced_context)
        if success:
            result_value = EvaluatorHelpers.process_evaluation_result(result)

    return result_value
