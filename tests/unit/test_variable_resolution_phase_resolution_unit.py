from types import SimpleNamespace

from ha_synthetic_sensors.config_models import SensorConfig
from ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase import (
    VariableResolutionPhase,
)
from ha_synthetic_sensors.type_definitions import ReferenceValue


class _Hass:
    def __init__(self):
        # minimal states object for compatibility
        self.states = SimpleNamespace(get=lambda _eid: None)


def test_state_attribute_resolution_substitutes_values(monkeypatch) -> None:
    # Ensure entity regex can be built if needed
    monkeypatch.setattr("ha_synthetic_sensors.shared_constants.get_ha_domains", lambda _h: frozenset({"sensor"}))
    phase = VariableResolutionPhase()
    phase.set_dependency_handler(SimpleNamespace(hass=_Hass(), data_provider_callback=None))
    # Provide mapping and provider for state.* resolution
    mapping = {"unit_phase": "sensor.kitchen"}

    def provider(entity_id: str):
        assert entity_id == "sensor.kitchen"
        return {"exists": True, "value": 0, "attributes": {"voltage": 120, "attributes": {"deep": {"level": 3}}}}

    phase.update_sensor_to_backing_mapping(mapping, provider)
    sensor_cfg = SensorConfig(unique_id="unit_phase")

    formula = "state.attributes.deep.level + state.voltage"
    result = phase.resolve_all_references_with_ha_detection(formula, sensor_cfg, {})
    # Both attributes should be substituted to numeric literals in the string
    assert "3" in result.resolved_formula
    assert "120" in result.resolved_formula


def test_entity_reference_resolution_with_tracking(monkeypatch) -> None:
    # Patch domains and provide hass
    monkeypatch.setattr("ha_synthetic_sensors.shared_constants.get_ha_domains", lambda _h: frozenset({"sensor"}))
    phase = VariableResolutionPhase()
    phase.set_dependency_handler(SimpleNamespace(hass=_Hass(), data_provider_callback=None))

    # Monkeypatch resolver factory to resolve entities to ReferenceValue with numeric value
    def fake_resolve(name: str, val: str, ctx: dict):
        if isinstance(val, str) and val.startswith("sensor."):
            return ReferenceValue(reference=val, value=42)
        return None

    phase._resolver_factory.resolve_variable = fake_resolve  # type: ignore[attr-defined]

    result = phase.resolve_all_references_with_ha_detection("sensor.any + 1", SensorConfig(unique_id="unit_phase"), {})
    # Entity should have been substituted to its numeric value
    assert "42" in result.resolved_formula
