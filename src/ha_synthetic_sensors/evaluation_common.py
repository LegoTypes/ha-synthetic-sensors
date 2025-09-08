"""Common evaluation patterns shared across evaluator modules.

This module contains shared functions to eliminate code duplication
between evaluator.py and evaluator_core_helpers.py.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .alternate_state_processor import alternate_state_processor
from .alternate_state_utils import detect_alternate_state_value
from .evaluator_helpers import EvaluatorHelpers
from .evaluator_results import EvaluatorResults
from .exceptions import DataValidationError, MissingDependencyError, SensorMappingError
from .type_definitions import EvaluationResult

if TYPE_CHECKING:
    from .hierarchical_context_dict import HierarchicalContextDict

_LOGGER = logging.getLogger(__name__)


def process_alternate_state_result(
    result: Any,
    config: Any,
    eval_context: HierarchicalContextDict,
    sensor_config: Any,
    core_evaluator: Any,
    resolve_all_references_in_formula: Any,
    pre_eval: bool = True,
    alternate_state_processor_instance: Any = None,
) -> EvaluationResult:
    """Process a result through alternate state handling and normalization.

    This consolidates the common pattern of:
    1. Processing through alternate_state_processor
    2. Normalizing with EvaluatorHelpers
    3. Creating success result
    """
    # Use provided alternate state processor instance or fall back to global
    processor = (
        alternate_state_processor_instance if alternate_state_processor_instance is not None else alternate_state_processor
    )

    processed_result = processor.process_evaluation_result(
        result=result,
        exception=None,
        context=eval_context,
        config=config,
        sensor_config=sensor_config,
        core_evaluator=core_evaluator,
        resolve_all_references_in_formula=resolve_all_references_in_formula,
        pre_eval=pre_eval,
    )

    normalized = EvaluatorHelpers.process_evaluation_result(processed_result)
    return EvaluatorResults.create_success_from_result(normalized)


def check_dependency_management_conditions(sensor_config: Any, context: Any, bypass_dependency_management: bool) -> bool:
    """Check if dependency management should be used based on common conditions."""
    return not (not sensor_config or not context or bypass_dependency_management)


def handle_alternate_state_detection(result: Any) -> tuple[bool, str | bool]:
    """Handle alternate state detection with consistent error handling.

    Returns:
        tuple: (is_alternate_state, alternate_state_value)
    """
    return detect_alternate_state_value(result)


def handle_evaluation_exception(e: Exception, config: Any, formula_name: str) -> None:
    """Handle evaluation exceptions with consistent logging and re-raising."""
    _LOGGER.error("Error in dependency-aware evaluation for formula '%s': %s", config.formula, e)
    if isinstance(e, MissingDependencyError | DataValidationError | SensorMappingError):
        raise e
