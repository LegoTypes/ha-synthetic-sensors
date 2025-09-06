"""Formula processor for synthetic sensor evaluation."""

from __future__ import annotations

import logging
from typing import Any

from .config_models import FormulaConfig, SensorConfig
from .evaluator_phases.variable_resolution.resolution_types import VariableResolutionResult
from .hierarchical_context_dict import HierarchicalContextDict
from .reference_value_manager import ReferenceValueManager
from .regex_helper import regex_helper
from .type_definitions import ReferenceValue

_LOGGER = logging.getLogger(__name__)


class FormulaProcessor:
    """Handles formula variable resolution and context preparation."""

    def __init__(self, variable_resolution_phase: Any) -> None:
        """Initialize the formula processor.

        Args:
            variable_resolution_phase: Phase for variable resolution
        """
        self._variable_resolution_phase = variable_resolution_phase

    def resolve_formula_variables(
        self, config: FormulaConfig, sensor_config: SensorConfig | None, eval_context: HierarchicalContextDict
    ) -> tuple[VariableResolutionResult, str]:
        """Resolve formula variables and return resolution result and resolved formula."""
        # BULLETPROOF: Log context type at formula processor entry
        _LOGGER.warning(
            "CONTEXT_FLOW_PROCESSOR: Received context id=%d type=%s in formula processor",
            id(eval_context),
            type(eval_context).__name__,
        )
        # Check if formula is already resolved (contains only numbers, operators, and functions)
        formula_variables = regex_helper.extract_formula_variables_for_resolution(config.formula)
        variables_needing_resolution = regex_helper.filter_variables_needing_resolution(formula_variables)

        if variables_needing_resolution:
            # Formula contains variables that need resolution
            resolution_result = self._variable_resolution_phase.resolve_all_references_with_ha_detection(
                config.formula, sensor_config, eval_context, config
            )
            resolved_formula = resolution_result.resolved_formula
        else:
            # Formula is already resolved (only literals and functions)
            # Debug logging removed to reduce verbosity
            resolution_result = VariableResolutionResult(
                resolved_formula=config.formula,
                has_ha_state=False,
            )
            resolved_formula = config.formula

        return resolution_result, resolved_formula

    def prepare_handler_context(
        self, eval_context: HierarchicalContextDict, resolution_result: VariableResolutionResult
    ) -> HierarchicalContextDict:
        """Prepare context for handlers by ensuring all values are ReferenceValue objects.

        This normalizes the context so handlers receive consistent ReferenceValue objects
        for all variables, which preserves both the original reference and resolved value.

        Args:
            eval_context: The evaluation context with mixed value types
            resolution_result: Result from variable resolution

        Returns:
            Handler context with all variables as ReferenceValue objects
        """
        # Process all context values to ensure they are ReferenceValue objects
        # Work directly with the HierarchicalContextDict to maintain architecture compliance
        for key, value in list(eval_context.items()):
            if not isinstance(value, ReferenceValue) and not key.startswith("_"):
                # Convert to ReferenceValue for consistency
                # For non-ReferenceValue items, use the key as the reference
                ReferenceValueManager.set_variable_with_reference_value(eval_context, key, key, value)
                ref_value = eval_context[key]
                if isinstance(ref_value, ReferenceValue):
                    # Debug logging removed to reduce verbosity
                    pass

        # Return the original HierarchicalContextDict with all values normalized to ReferenceValue objects
        return eval_context

    def build_evaluation_context(self, context: HierarchicalContextDict) -> HierarchicalContextDict:
        """Build the evaluation context for formula processing."""
        # ARCHITECTURE FIX: Context is now required parameter - no None checks needed

        # BULLETPROOF: Preserve HierarchicalContextDict instead of converting to regular dict
        _LOGGER.warning(
            "CONTEXT_CONVERSION_POINT: Received context type %s, preserving instead of converting", type(context).__name__
        )

        # Return the original context to preserve HierarchicalContextDict
        return context

    def resolve_all_references_in_formula(
        self, formula: str, sensor_config: SensorConfig | None, eval_context: HierarchicalContextDict
    ) -> str:
        """Resolve all references in a formula string."""
        # This is a simplified version - the full implementation would be in the variable resolution phase
        return formula

    def finalize_result(
        self,
        result: float | str | bool | None,
        config: FormulaConfig,
        context: HierarchicalContextDict,
        cache_key_id: str,
        sensor_config: SensorConfig | None,
    ) -> float | str | bool | None:
        """Finalize the evaluation result with any post-processing."""
        # CRITICAL FIX: Accept None values to preserve them through the evaluation pipeline
        # This ensures that None values (indicating missing/unavailable data) are properly
        # handled throughout the evaluation process without premature conversion to strings.
        # Post-processing logic can be added here if needed
        # Debug logging removed to reduce verbosity
        return result
