"""Utility functions for formula configuration handling."""

import re
from typing import Any

from .config_models import FormulaConfig


def tokenize_formula(formula: str) -> set[str]:
    """Tokenize formula to extract potential variable/sensor references.

    Args:
        formula: Formula string to tokenize

    Returns:
        Set of potential variable/sensor reference tokens
    """
    # Pattern to match valid Python identifiers (sensor keys)
    identifier_pattern = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b")

    # Find all potential identifiers
    tokens = set(identifier_pattern.findall(formula))

    # Filter out common keywords and operators that aren't sensor references
    excluded_keywords = {
        "state",
        "and",
        "or",
        "not",
        "if",
        "else",
        "elif",
        "in",
        "is",
        "True",
        "False",
        "None",
        "def",
        "class",
        "import",
        "from",
        "sum",
        "max",
        "min",
        "avg",
        "count",
        "abs",
        "round",
        "int",
        "float",
    }

    # Remove excluded keywords
    tokens = tokens - excluded_keywords
    return tokens


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
