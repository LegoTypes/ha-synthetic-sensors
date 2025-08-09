"""
Formula Evaluator Service - Unified formula evaluation for all types.

This service provides a single place where all formula evaluation happens:
- Main sensor formulas
- Computed variables
- Attribute formulas

All formulas are siblings that use the same evaluation pipeline.
"""

import logging
from typing import Any

from .config_models import FormulaConfig
from .core_formula_evaluator import CoreFormulaEvaluator
from .type_definitions import ContextValue

_LOGGER = logging.getLogger(__name__)


class FormulaEvaluatorService:
    """
    Unified formula evaluation service for main formulas, variables, and attributes.

    This is the single source of truth for formula evaluation across the entire system.
    All formula types (main, variable, attribute) are siblings that use the same pipeline.
    """

    _core_evaluator: CoreFormulaEvaluator | None = None
    _evaluator: Any | None = None

    @classmethod
    def initialize(cls, core_evaluator: CoreFormulaEvaluator) -> None:
        """Initialize the service with a CoreFormulaEvaluator instance."""
        cls._core_evaluator = core_evaluator
        _LOGGER.debug("FormulaEvaluatorService initialized with CoreFormulaEvaluator")

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if the service has been initialized."""
        return cls._core_evaluator is not None

    @classmethod
    def set_evaluator(cls, evaluator: Any) -> None:
        """Attach the high-level Evaluator to enable full pipeline evaluation."""
        cls._evaluator = evaluator
        _LOGGER.debug("FormulaEvaluatorService attached Evaluator for pipeline execution")

    @classmethod
    def evaluate_formula(
        cls, resolved_formula: str, original_formula: str, context: dict[str, ContextValue]
    ) -> float | str | bool:
        """
        Evaluate a main sensor formula.

        Args:
            resolved_formula: Formula with variables resolved
            original_formula: Original formula before variable resolution
            context: Evaluation context with ReferenceValue objects

        Returns:
            Evaluated result
        """
        if not cls._core_evaluator:
            raise RuntimeError("FormulaEvaluatorService not initialized")

        _LOGGER.debug("FORMULA_SERVICE: Evaluating main formula: %s", resolved_formula)
        return cls._core_evaluator.evaluate_formula(resolved_formula, original_formula, context)

    @classmethod
    def evaluate_formula_via_pipeline(
        cls,
        formula: str,
        context: dict[str, ContextValue],
        *,
        variables: dict[str, object] | None = None,
        bypass_dependency_management: bool = True,
    ) -> dict[str, object]:
        """Evaluate a raw formula string via the full evaluator pipeline.

        This is used for computed-variable formulas so they follow the same
        ordering and processing (metadata, conversions, resolution) as main/attribute formulas.

        Returns Evaluator EvaluationResult dict.
        """
        if cls._evaluator is None:
            raise RuntimeError("FormulaEvaluatorService Evaluator not attached")

        # Narrow variables type to expected mapping for FormulaConfig
        # Use the exact expected type for FormulaConfig.variables
        safe_variables: dict[str, str | int | float | Any] = {}
        if variables:
            for k, v in variables.items():
                if isinstance(v, (str | int | float)):
                    safe_variables[k] = v

        temp_config = FormulaConfig(
            id=f"temp_cv_{abs(hash(formula))}",
            name="Computed Variable",
            formula=formula,
            variables=safe_variables,
            attributes={},
        )

        result: dict[str, object] = cls._evaluator.evaluate_formula_with_sensor_config(
            temp_config,
            context,
            sensor_config=None,
            bypass_dependency_management=bypass_dependency_management,
        )
        return result
