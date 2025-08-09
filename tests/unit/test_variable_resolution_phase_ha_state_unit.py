from types import SimpleNamespace

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase import (
    VariableResolutionPhase,
)
from ha_synthetic_sensors.type_definitions import ReferenceValue


def test_ha_state_detection_from_unavailable_dependencies_early_return(monkeypatch) -> None:
    # Patch domains so the phase can build entity regex without using HA registry
    monkeypatch.setattr("ha_synthetic_sensors.shared_constants.get_ha_domains", lambda _h: frozenset({"sensor"}))
    phase = VariableResolutionPhase()
    phase.set_dependency_handler(
        SimpleNamespace(hass=SimpleNamespace(states=SimpleNamespace(get=lambda _eid: None)), data_provider_callback=None)
    )
    # Simulate that entity tracking populated these lists via previous steps
    # Build a context with a ReferenceValue to ensure code paths accept context shape
    ctx: dict[str, ReferenceValue] = {"dummy": ReferenceValue(reference="sensor.any", value=0)}
    # Use a formula with no entities; detection should rely solely on the dependency list
    formula = "1 + 2"

    # Manually call the internal step that would produce the early return via FormulaHelpers
    result = phase.resolve_all_references_with_ha_detection(formula, None, ctx)
    # No deps → not early return yet
    assert getattr(result, "has_ha_state", False) in (False, None)

    # Now force a formula that includes the string 'unknown' to trigger early return path
    result2 = phase.resolve_all_references_with_ha_detection("unknown", None, ctx)
    assert result2.has_ha_state is True
    assert result2.ha_state_value == "unknown"
