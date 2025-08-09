from ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase import (
    VariableResolutionPhase,
)
from ha_synthetic_sensors.type_definitions import ReferenceValue


def test_simple_variables_with_tracking_adds_ha_dependency_for_unknown() -> None:
    phase = VariableResolutionPhase()
    ctx = {"x": ReferenceValue(reference="sensor.kitchen", value="unknown")}
    formula, mappings, deps, entity_map = phase._resolve_simple_variables_with_tracking("x + 1", ctx, {})
    assert formula.strip().startswith("x")
    # Dependency note should be recorded
    assert any("is unknown" in d for d in deps)
    assert mappings.get("x") == "sensor.kitchen"
