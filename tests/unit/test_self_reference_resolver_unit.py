from types import SimpleNamespace

from ha_synthetic_sensors.evaluator_phases.variable_resolution.self_reference_resolver import (
    SelfReferenceResolver,
)


def test_self_reference_main_formula_resolves_via_data_provider_then_hass() -> None:
    r = SelfReferenceResolver()
    r.set_sensor_to_backing_mapping({"s1": "sensor.s1"})

    # Data provider takes precedence
    dep = SimpleNamespace(
        should_use_data_provider=lambda eid: True,
        data_provider_callback=lambda eid: {"exists": True, "value": 123},
        hass=SimpleNamespace(states=SimpleNamespace(get=lambda _eid: None)),
    )
    r.set_dependency_handler(dep)
    val = r.resolve("x", "sensor.s1", {})
    assert val == 123

    # If DP not used but HASS present
    dep2 = SimpleNamespace(
        should_use_data_provider=lambda eid: False,
        data_provider_callback=None,
        hass=SimpleNamespace(states=SimpleNamespace(get=lambda _eid: SimpleNamespace(state="42"))),
    )
    r.set_dependency_handler(dep2)
    val2 = r.resolve("x", "sensor.s1", {})
    assert val2 == 42


def test_self_reference_attribute_context_uses_state_or_registry() -> None:
    r = SelfReferenceResolver()
    r.set_sensor_to_backing_mapping({"s1": "sensor.s1"})
    # Attribute context simulated by extra keys
    registry = SimpleNamespace(get_sensor_value=lambda key: 77)
    r.set_sensor_registry_phase(registry)

    # If state value present and numeric
    out = r.resolve("x", "sensor.s1", {"state": 55, "attr": 1})
    assert out == 55

    # If no state, use registry
    out2 = r.resolve("x", "sensor.s1", {"attr": 1})
    assert out2 == 77
