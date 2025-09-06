"""
Formula Evaluator Service - Unified formula evaluation for all types.

This service provides a single place where all formula evaluation happens:
- Main sensor formulas
- Computed variables
- Attribute formulas

All formulas are siblings that use the same evaluation pipeline.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .hierarchical_context_dict import HierarchicalContextDict

from .config_models import FormulaConfig

if TYPE_CHECKING:
    from .config_models import AlternateStateHandler
from .core_formula_evaluator import CoreFormulaEvaluator

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
        cls,
        resolved_formula: str,
        original_formula: str,
        context: "HierarchicalContextDict",
        *,
        allow_unresolved_states: bool = False,
    ) -> float | str | bool | None:
        """
        Evaluate a main sensor formula using Phase 3 execution only.

        This method is used by the main evaluator pipeline after Phases 0-2 have already
        processed the formula (cache checks, variable resolution, dependency management).
        It provides a direct execution path to avoid re-running the full pipeline.

        ARCHITECTURAL REASONING:
        - Main formulas go through the complete pipeline (Phases 0-4) in evaluator.py
        - By the time they reach Phase 3 (execution), all preprocessing is complete
        - Calling the full pipeline again would be redundant and inefficient
        - This method provides a streamlined execution path for pre-processed formulas

        PERFORMANCE BENEFITS:
        - Avoids creating temporary FormulaConfig objects
        - Skips redundant cache checks and variable resolution
        - Eliminates duplicate dependency management processing
        - Reduces memory allocation and processing overhead

        Args:
            resolved_formula: Formula with variables already resolved and substituted
            original_formula: Original formula before variable resolution (for context)
            context: Evaluation context with ReferenceValue objects

        Returns:
            Evaluated result value

        Used by:
            - Main sensor formulas in evaluator.py _execute_with_handler()
            - Alternate state handlers that need direct execution
        """
        if not cls._core_evaluator:
            raise RuntimeError("FormulaEvaluatorService not initialized")

        _LOGGER.debug("FORMULA_SERVICE: Evaluating main formula: %s", resolved_formula)

        # Set the allow_unresolved_states flag on the core evaluator
        cls._core_evaluator.set_allow_unresolved_states(allow_unresolved_states)

        # Let AlternateStateDetected exceptions propagate to Phase 4 handler
        return cls._core_evaluator.evaluate_formula(resolved_formula, original_formula, context)

    @classmethod
    def evaluate_formula_via_pipeline(
        cls,
        formula: str,
        context: "HierarchicalContextDict",
        *,
        variables: dict[str, object] | None = None,
        bypass_dependency_management: bool = True,
        allow_unresolved_states: bool = False,
        alternate_state_handler: "AlternateStateHandler | None" = None,
    ) -> dict[str, object]:
        """
        Evaluate a formula string via the complete evaluation pipeline (Phases 0-4).

        This method creates a temporary FormulaConfig and runs the full evaluation pipeline
        including cache checks, variable resolution, dependency management, execution,
        and result consolidation. Used for formulas that need complete processing.

        ARCHITECTURAL REASONING:
        - Computed variables and attributes enter the evaluation system as formula strings
        - They need the same processing as main formulas but don't go through the main pipeline
        - Creating a temporary FormulaConfig ensures they get identical processing
        - This maintains consistency across all formula types while allowing different entry points

        WHY NOT USE evaluate_formula:
        - These formulas haven't been processed through Phases 0-2 yet
        - Variable resolution, cache checks, and dependency management are still needed
        - The formula needs to be converted to a FormulaConfig for proper processing
        - Full pipeline ensures consistent error handling and state management

        NOTE ON TERMINOLOGY:
        - "Raw" vs "processed" is misleading - all formulas start as strings
        - The difference is WHEN processing occurs, not WHAT gets processed
        - Main formulas: processed by evaluator.py pipeline, then executed here
        - Other formulas: processed entirely within this method's pipeline

        CACHING AND REUSE MECHANISM:
        - This method is used for the FIRST evaluation of an attribute/variable
        - Once evaluated, the result is cached in the evaluation context
        - Subsequent references to the same attribute/variable use the cached value
        - Cached values bypass the full pipeline - they're treated as "processed"
        - This prevents redundant evaluations and ensures consistency

        PERFORMANCE TRADE-OFFS:
        - Higher overhead due to full pipeline execution
        - Temporary object creation for FormulaConfig
        - Necessary for formulas that need complete processing
        - Acceptable cost for maintaining architectural consistency

        Args:
            formula: Formula string that needs full pipeline processing
            context: Evaluation context with ReferenceValue objects
            variables: Optional variables to include in temporary config
            bypass_dependency_management: Whether to skip dependency management

        Returns:
            Complete EvaluationResult dictionary with success/error states

        Used by:
            - Computed variables that need full variable resolution and processing
            - Attribute formulas that require complete pipeline execution
            - Any formula that needs the same processing as main formulas but enters
              the pipeline at a different point
        """
        if cls._evaluator is None:
            raise RuntimeError("FormulaEvaluatorService Evaluator not attached")

        # ARCHITECTURAL FIX: Use empty variables to prevent dependency extraction contamination
        # The pipeline will resolve variables naturally from the context (ReferenceValue objects)
        # instead of from FormulaConfig.variables which was causing timestamp contamination
        # ARCHITECTURE FIX: Include alternate_state_handler for computed variables
        temp_config = FormulaConfig(
            id=f"temp_cv_{abs(hash(formula))}",
            name="Computed Variable",
            formula=formula,
            variables={},  # Empty - let pipeline resolve from context
            attributes={},
            allow_unresolved_states=allow_unresolved_states,
            alternate_state_handler=alternate_state_handler,
        )

        result: dict[str, object] = cls._evaluator.evaluate_formula_with_sensor_config(
            temp_config,
            context,
            sensor_config=None,
            bypass_dependency_management=bypass_dependency_management,
        )
        return result
