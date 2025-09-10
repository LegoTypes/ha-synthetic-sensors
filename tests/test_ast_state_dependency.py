"""Test AST service handling of state token and dependency extraction."""

import pytest
from ha_synthetic_sensors.formula_ast_analysis_service import FormulaASTAnalysisService


def test_state_token_not_treated_as_dependency():
    """Test that 'state' token is not treated as a regular dependency."""
    ast_service = FormulaASTAnalysisService()

    # Test simple 'state' formula
    analysis = ast_service.get_formula_analysis("state")
    print(f"Formula: 'state'")
    print(f"  Variables: {analysis.variables}")
    print(f"  Dependencies: {analysis.dependencies}")
    print(f"  Has state token: {analysis.has_state_token}")
    print()

    # The 'state' token should be recognized but not added to dependencies
    assert analysis.has_state_token is True, "Should detect state token"
    assert "state" not in analysis.dependencies, "'state' should not be in dependencies"

    # Test formula with state and other variables
    analysis2 = ast_service.get_formula_analysis("state * multiplier")
    print(f"Formula: 'state * multiplier'")
    print(f"  Variables: {analysis2.variables}")
    print(f"  Dependencies: {analysis2.dependencies}")
    print(f"  Has state token: {analysis2.has_state_token}")
    print()

    assert analysis2.has_state_token is True
    assert "state" not in analysis2.dependencies
    assert "multiplier" in analysis2.dependencies

    # Test formula with metadata functions
    analysis3 = ast_service.get_formula_analysis("metadata(state, 'last_changed')")
    print(f"Formula: metadata(state, 'last_changed')")
    print(f"  Variables: {analysis3.variables}")
    print(f"  Dependencies: {analysis3.dependencies}")
    print(f"  Has state token: {analysis3.has_state_token}")
    print(f"  Metadata calls: {analysis3.metadata_calls}")
    print()

    assert analysis3.has_state_token is True
    assert "state" not in analysis3.dependencies


def test_computed_variable_dependencies():
    """Test that computed variables are properly extracted as dependencies."""
    ast_service = FormulaASTAnalysisService()

    # Test formula with computed variables (from energy sensors)
    formula = "last_valid_state if is_within_grace_period else 'unknown'"
    analysis = ast_service.get_formula_analysis(formula)
    print(f"Formula: '{formula}'")
    print(f"  Variables: {analysis.variables}")
    print(f"  Dependencies: {analysis.dependencies}")
    print()

    # These should be recognized as dependencies
    assert "last_valid_state" in analysis.dependencies
    assert "is_within_grace_period" in analysis.dependencies


def test_dependency_isolation():
    """Test that dependency extraction is isolated per formula."""
    ast_service = FormulaASTAnalysisService()

    # First formula - simple state
    power_formula = "state"
    power_analysis = ast_service.get_formula_analysis(power_formula)

    # Second formula - complex with variables
    energy_formula = "last_valid_state if is_within_grace_period else 'unknown'"
    energy_analysis = ast_service.get_formula_analysis(energy_formula)

    # Third formula - back to simple
    another_power_formula = "state"
    another_power_analysis = ast_service.get_formula_analysis(another_power_formula)

    print("Power formula dependencies:", power_analysis.dependencies)
    print("Energy formula dependencies:", energy_analysis.dependencies)
    print("Another power formula dependencies:", another_power_analysis.dependencies)

    # Ensure no cross-contamination
    assert power_analysis.dependencies == another_power_analysis.dependencies
    assert "last_valid_state" not in power_analysis.dependencies
    assert "last_valid_state" not in another_power_analysis.dependencies


if __name__ == "__main__":
    print("Testing AST service state token handling...")
    print("=" * 60)
    test_state_token_not_treated_as_dependency()
    print("=" * 60)
    test_computed_variable_dependencies()
    print("=" * 60)
    test_dependency_isolation()
    print("=" * 60)
    print("All tests passed!")
