"""Utility functions for formula configuration handling."""

from typing import Any

from .config_models import FormulaConfig
from .formula_parsing.variable_extractor import ExtractionContext, extract_variables


def tokenize_formula(formula: str) -> set[str]:
    """Tokenize formula to extract potential variable/sensor references.

    Args:
        formula: Formula string to tokenize

    Returns:
        Set of potential variable/sensor reference tokens
    """
    # Use centralized variable extraction
    return extract_variables(formula, context=ExtractionContext.GENERAL)


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
