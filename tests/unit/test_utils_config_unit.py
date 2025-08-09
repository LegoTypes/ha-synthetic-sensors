import pytest

from ha_synthetic_sensors.config_models import ComputedVariable, FormulaConfig
from ha_synthetic_sensors.utils_config import (
    clear_computed_variable_cache,
    get_computed_variable_cache_stats,
    validate_computed_variable_references,
)


def test_computed_variable_cache_clear_and_stats() -> None:
    # Stats should be a dict before and after clear
    stats_before = get_computed_variable_cache_stats()
    assert isinstance(stats_before, dict)
    clear_computed_variable_cache()
    stats_after = get_computed_variable_cache_stats()
    assert isinstance(stats_after, dict)


def test_validate_computed_variable_references_detects_undefined_refs() -> None:
    variables = {
        "a": 1,
        "b": ComputedVariable("a + c + now()"),  # 'c' is undefined, 'now' is allowed
    }
    errors = validate_computed_variable_references(variables, config_id="cfg", global_variables={"g": 2})
    assert errors and "undefined variables" in errors[0]


@pytest.mark.parametrize(
    "cv_formula",
    ["1/0", "foo(]"],
)
def test_validate_computed_variable_references_does_not_crash_on_bad_formulas(cv_formula: str) -> None:
    variables = {"x": ComputedVariable(cv_formula)}
    # This validation only checks names; it should not raise on syntax, just return no undefined vars
    errors = validate_computed_variable_references(variables)
    assert isinstance(errors, list)
