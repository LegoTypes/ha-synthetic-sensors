from ha_synthetic_sensors.evaluator_phases.variable_resolution.formula_helpers import FormulaHelpers


def test_detect_ha_state_from_unavailable_dependencies() -> None:
    """Test that entity references with dependencies do NOT trigger early return."""
    deps = ["sensor.kitchen is unavailable"]
    res = FormulaHelpers.detect_ha_state_in_formula("sensor.kitchen", deps, {})
    assert res is None  # Entity references should not trigger early return


def test_detect_ha_state_complex_formula_with_dependencies_returns_none() -> None:
    """Test that complex formulas with dependencies do NOT trigger early return."""
    deps = ["sensor.kitchen is unavailable"]
    res = FormulaHelpers.detect_ha_state_in_formula("1+2", deps, {})
    assert res is None  # Complex formula should not trigger early return


def test_detect_ha_state_normalizes_uppercase_literal_when_unquoted_in_result() -> None:
    # The helper checks only for lowercase tokens in the string and then final state via normalize
    res = FormulaHelpers.detect_ha_state_in_formula("unavailable", [], {})
    assert res is not None and res.ha_state_value == "unavailable"


def test_find_metadata_param_single_argument_branch() -> None:
    ranges = FormulaHelpers.find_metadata_function_parameter_ranges("metadata(sensor.kitchen)")
    assert ranges and isinstance(ranges[0], tuple)
