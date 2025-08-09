"""Formula processing and preparation logic for the evaluator."""

from __future__ import annotations

import logging
import re
from typing import Any

from .config_models import FormulaConfig, SensorConfig
from .evaluator_phases.variable_resolution.resolution_types import VariableResolutionResult
from .reference_value_manager import ReferenceValueManager
from .type_definitions import ContextValue, ReferenceValue

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
        self, config: FormulaConfig, sensor_config: SensorConfig | None, eval_context: dict[str, ContextValue]
    ) -> tuple[VariableResolutionResult, str]:
        """Resolve formula variables and return resolution result and resolved formula."""
        # Check if formula is already resolved (contains only numbers, operators, and functions)
        needs_resolution_pattern = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b")
        formula_variables = needs_resolution_pattern.findall(config.formula)
        # Filter out known function names and operators
        function_names = {"min", "max", "abs", "round", "int", "float", "str", "len", "sum", "any", "all"}
        variables_needing_resolution = [var for var in formula_variables if var not in function_names]

        if variables_needing_resolution:
            # Formula contains variables that need resolution
            resolution_result = self._variable_resolution_phase.resolve_all_references_with_ha_detection(
                config.formula, sensor_config, eval_context, config
            )
            resolved_formula = resolution_result.resolved_formula
        else:
            # Formula is already resolved (only literals and functions)
            _LOGGER.debug("Formula requires no variable resolution: %s", config.formula)
            resolution_result = VariableResolutionResult(
                resolved_formula=config.formula,
                has_ha_state=False,
            )
            resolved_formula = config.formula

        return resolution_result, resolved_formula

    def prepare_handler_context(
        self, eval_context: dict[str, ContextValue], resolution_result: VariableResolutionResult
    ) -> dict[str, ContextValue]:
        """Prepare context for handlers by ensuring all values are ReferenceValue objects.

        This normalizes the context so handlers receive consistent ReferenceValue objects
        for all variables, which preserves both the original reference and resolved value.

        Args:
            eval_context: The evaluation context with mixed value types
            resolution_result: Result from variable resolution

        Returns:
            Handler context with all variables as ReferenceValue objects
        """
        handler_context: dict[str, ContextValue] = {}

        # Process all context values
        for key, value in eval_context.items():
            if isinstance(value, ReferenceValue):
                # Already a ReferenceValue - keep as-is
                handler_context[key] = value
            else:
                # Convert to ReferenceValue for consistency
                # For non-ReferenceValue items, use the key as the reference
                ReferenceValueManager.set_variable_with_reference_value(handler_context, key, key, value)
                ref_value = handler_context[key]
                if isinstance(ref_value, ReferenceValue):
                    _LOGGER.debug("Converted %s to ReferenceValue: %s -> %s", key, value, ref_value.value)

        return handler_context

    def build_evaluation_context(self, context: dict[str, ContextValue] | None) -> dict[str, ContextValue]:
        """Build the evaluation context for formula processing."""
        if context is None:
            return {}
        return dict(context)

    def resolve_all_references_in_formula(
        self, formula: str, sensor_config: SensorConfig | None, eval_context: dict[str, ContextValue]
    ) -> str:
        """Resolve all references in a formula string."""
        # This is a simplified version - the full implementation would be in the variable resolution phase
        return formula

    def finalize_result(
        self,
        result: float | str | bool,
        config: FormulaConfig,
        context: dict[str, ContextValue] | None,
        cache_key_id: str,
        sensor_config: SensorConfig | None,
    ) -> float | str | bool:
        """Finalize the evaluation result with any post-processing."""
        # Post-processing logic can be added here if needed
        _LOGGER.debug("Finalizing result for formula %s: %s", config.formula, result)
        return result
