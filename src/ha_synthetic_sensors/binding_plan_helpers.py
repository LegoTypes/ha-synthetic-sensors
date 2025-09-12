"""Helper functions for binding plan and lazy context population.

This module provides helper functions for working with binding plans
and implementing lazy context population strategies.
"""

from __future__ import annotations

import logging
from typing import Any

from .formula_ast_analysis_service import BindingPlan, FormulaASTAnalysisService
from .hierarchical_context_dict import HierarchicalContextDict
from .lazy_resolver import LazyResolver
from .type_definitions import ReferenceValue

_LOGGER = logging.getLogger(__name__)


def build_binding_plan(ast_service: FormulaASTAnalysisService, formula: str) -> BindingPlan:
    """Build binding plan from formula AST analysis.

    This is a convenience function that delegates to the AST service.

    Args:
        ast_service: The AST analysis service instance
        formula: The formula string to analyze

    Returns:
        BindingPlan with names, strategies, and metadata about the formula
    """
    return ast_service.build_binding_plan(formula)


def prepare_minimal_layer(ctx: HierarchicalContextDict, plan: BindingPlan, lazy_resolver: LazyResolver | None = None) -> None:
    """Prepare minimal context layer with only required names from plan.

    This function creates a minimal context layer containing only the names
    specified in the binding plan, with ReferenceValue shells that will be
    resolved lazily on first access.

    Args:
        ctx: The hierarchical context to prepare
        plan: BindingPlan describing what the formula needs
        lazy_resolver: Optional lazy resolver for value resolution
    """
    if not isinstance(plan, BindingPlan):
        _LOGGER.warning("Invalid binding plan provided to prepare_minimal_layer")
        return

    # Add new layer for this formula's requirements
    layer_name = f"formula_{hash(str(plan.names))}"
    ctx.hierarchical_context.push_layer(layer_name)

    # Create ReferenceValue shells for each name in plan
    for name in plan.names:
        # Skip if already in context - don't override existing values
        if name in ctx:
            continue

        strategy = plan.strategies.get(name, "ha_state")

        # Store strategy as infrastructure metadata (not wrapped)
        ctx.hierarchical_context.set(f"_strategy_{name}", strategy)  # type: ignore[arg-type]

        # Create lazy ReferenceValue (value=None means lazy)
        if strategy == "literal":
            # Literals might have immediate values
            ref_value = ReferenceValue(reference=name, value=name)
        else:
            # Everything else is lazy
            ref_value = ReferenceValue(reference=name, value=None)

        ctx.hierarchical_context.set(name, ref_value)

    # Store plan metadata as infrastructure (not wrapped)
    ctx.hierarchical_context.set("_binding_plan", plan)  # type: ignore[arg-type]

    # If lazy resolver provided, store as infrastructure and prepare batch
    if lazy_resolver:
        ctx.hierarchical_context.set("_lazy_resolver", lazy_resolver)  # type: ignore[arg-type]
        lazy_resolver.start_new_cycle()

        # Prepare batch entities for efficient HA state lookups
        ha_entities = {name for name, strategy in plan.strategies.items() if strategy == "ha_state"}
        if ha_entities:
            lazy_resolver.prepare_batch_entities(ha_entities)
            _LOGGER.debug("Prepared batch loading for %d HA entities", len(ha_entities))


def normalize_collection_queries(ast_service: FormulaASTAnalysisService, formula: str) -> list[str]:
    """Normalize collection queries for consistent caching.

    This is a convenience function that delegates to the AST service.

    Args:
        ast_service: The AST analysis service instance
        formula: The formula string to analyze

    Returns:
        List of normalized query strings
    """
    return ast_service.normalize_collection_queries(formula)


def resolve_lazy_values(ctx: HierarchicalContextDict, names: set[str]) -> dict[str, Any]:
    """Resolve lazy values for specific names using the context's lazy resolver.

    This function triggers lazy resolution for the specified names and returns
    a dictionary suitable for formula evaluation.

    Args:
        ctx: The hierarchical context containing lazy resolver
        names: Set of names to resolve

    Returns:
        Dictionary mapping names to resolved values
    """
    lazy_resolver = ctx.get("_lazy_resolver")
    if not isinstance(lazy_resolver, LazyResolver):
        _LOGGER.debug("No lazy resolver available in context")
        return {}

    resolved_values = {}
    for name in names:
        try:
            value = lazy_resolver.resolve_if_needed(ctx, name)
            resolved_values[name] = value
        except Exception as e:
            _LOGGER.warning("Failed to resolve lazy value for %s: %s", name, e)
            resolved_values[name] = None

    return resolved_values


def create_lazy_evaluation_context(ctx: HierarchicalContextDict, formula_names: set[str]) -> dict[str, Any]:
    """Create evaluation context with lazy-resolved values for formula execution.

    This function extracts values from ReferenceValue objects, triggering lazy
    resolution as needed, and returns a context suitable for SimpleEval.

    Args:
        ctx: The hierarchical context with ReferenceValue objects
        formula_names: Names referenced in the formula

    Returns:
        Dictionary with resolved values for formula evaluation
    """
    eval_context = {}
    lazy_resolver = ctx.get("_lazy_resolver")

    for name in formula_names:
        ref_value = ctx.get(name)

        if isinstance(ref_value, ReferenceValue):
            # Use lazy resolver if available and value is None
            if ref_value.value is None and isinstance(lazy_resolver, LazyResolver):
                resolved = lazy_resolver.resolve_if_needed(ctx, name)
                eval_context[name] = resolved
            else:
                eval_context[name] = ref_value.value
        else:
            # Handle non-ReferenceValue types (should be rare in proper usage)
            if isinstance(ref_value, str | int | float | type(None)):
                eval_context[name] = ref_value
            else:
                # For other types, convert to string or use None
                eval_context[name] = str(ref_value) if ref_value is not None else None

    return eval_context


# Alias for backward compatibility
_prepare_minimal_layer = prepare_minimal_layer
