"""Utility functions for formula configuration handling."""

from typing import Any

from .config_models import FormulaConfig
from .formula_ast_analysis_service import FormulaASTAnalysisService


def tokenize_formula(formula: str) -> set[str]:
    """Tokenize formula to extract potential variable/sensor references.

    Args:
        formula: Formula string to tokenize

    Returns:
        Set of potential variable/sensor reference tokens
    """
    # Use AST service for variable extraction
    ast_service = FormulaASTAnalysisService()
    return ast_service.extract_variables(formula)


def extract_attribute_name(formula: FormulaConfig, sensor_unique_id: str) -> str:
    """Extract attribute name from formula ID.

    Args:
        formula: Formula configuration
        sensor_unique_id: Unique ID of the sensor

    Returns:
        Attribute name extracted from formula ID, or full formula ID if no prefix match
    """
    if formula.id.startswith(f"{sensor_unique_id}_"):
        return formula.id[len(sensor_unique_id) + 1 :]
    # Fallback: use the full formula ID if it doesn't match expected pattern
    return formula.id


def extract_formula_dependencies(formula: str) -> set[str]:
    """Extract dependencies from a formula using AST analysis.

    Args:
        formula: Formula string to analyze

    Returns:
        Set of dependency identifiers (excluding reserved words)
    """
    from .shared_constants import get_reserved_words  # pylint: disable=import-outside-toplevel

    # Use AST service for dependency extraction
    ast_service = FormulaASTAnalysisService()
    analysis = ast_service.get_formula_analysis(formula)
    identifiers = analysis.dependencies

    # Filter out reserved words
    return {identifier for identifier in identifiers if identifier not in get_reserved_words()}


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
