"""Utility functions for formula configuration handling."""

from typing import Any

from .config_models import FormulaConfig


def add_optional_formula_fields(formula_data: dict[str, Any], formula: FormulaConfig, include_variables: bool = False) -> None:
    """Add optional formula fields to dictionary.

    Args:
        formula_data: Dictionary to add fields to
        formula: Formula configuration
        include_variables: Whether to include variables field (used by YAML parser)
    """
    if formula.name:
        formula_data["name"] = formula.name
    if include_variables and formula.variables:
        formula_data["variables"] = formula.variables
    if formula.attributes:
        formula_data["attributes"] = formula.attributes
    if formula.metadata:
        formula_data["metadata"] = formula.metadata
