import pytest

from ha_synthetic_sensors.config_models import FormulaConfig
from ha_synthetic_sensors.evaluator_phases.variable_resolution.formula_helpers import FormulaHelpers


def test_find_metadata_function_parameter_ranges_extracts_first_param() -> None:
    formula = "sum(1,2) + metadata(device, 'icon') + 5 * metadata(sensor.temp, 'unit')"
    ranges = FormulaHelpers.find_metadata_function_parameter_ranges(formula)
    # Extract protected substrings by ranges
    protected = [formula[start:end] for start, end in ranges]
    assert "device" in protected
    assert "sensor.temp" in protected


def test_identify_variables_for_attribute_access_marks_entity_vars() -> None:
    cfg = FormulaConfig(
        id="main",
        formula="dev.battery_level + count",
        variables={"dev": "sensor.kitchen", "count": 3},
    )
    result = FormulaHelpers.identify_variables_for_attribute_access(cfg.formula, cfg)
    assert result == {"dev"}


@pytest.mark.parametrize(
    "deps,expected_state",
    [
        (["x (sensor.a) is unavailable"], "unavailable"),
        (["x (sensor.a) is unknown"], "unknown"),
    ],
)
def test_detect_ha_state_in_formula_via_dependencies(deps: list[str], expected_state: str) -> None:
    res = FormulaHelpers.detect_ha_state_in_formula("1 + 2", deps, {})
    assert res is not None
    assert res.has_ha_state is True
    assert res.ha_state_value == expected_state


def test_detect_ha_state_in_formula_detects_quoted_unknown() -> None:
    # Single state optimization only works when entire formula is a state value
    # A formula like '"unknown" + 2' is not a single state, so should return None
    res = FormulaHelpers.detect_ha_state_in_formula('"unknown" + 2', [], {})
    assert res is None  # Formula contains state but is not a single state

    # Test that single quoted state is detected
    res = FormulaHelpers.detect_ha_state_in_formula('"unknown"', [], {})
    assert res is not None and res.ha_state_value == "unknown"


def test_detect_ha_state_in_formula_when_formula_itself_is_state_value() -> None:
    res = FormulaHelpers.detect_ha_state_in_formula("unavailable", [], {})
    assert res is not None and res.ha_state_value == "unavailable"
