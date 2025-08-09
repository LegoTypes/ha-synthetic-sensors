from types import SimpleNamespace

from ha_synthetic_sensors.evaluator_phases.variable_resolution.self_reference_resolver import (
    SelfReferenceResolver,
)


def test_self_reference_hass_numeric_and_unknown_paths() -> None:
    r = SelfReferenceResolver()
    r.set_sensor_to_backing_mapping({"s1": "sensor.s1"})

    class State:
        def __init__(self, state):
            self.state = state

    class Hass:
        def __init__(self, value):
            self.states = SimpleNamespace(get=lambda _eid: State(value))

    # HASS numeric string becomes numeric
    r.set_dependency_handler(SimpleNamespace(hass=Hass("42")))
    assert r.resolve("x", "sensor.s1", {}) == 42

    # HASS unknown normalized should compare case-insensitively
    r.set_dependency_handler(SimpleNamespace(hass=Hass("UNKNOWN")))
    assert str(r.resolve("x", "sensor.s1", {})).lower() == "unknown"


def test_self_reference_attribute_context_uses_state_then_registry() -> None:
    r = SelfReferenceResolver()
    r.set_sensor_to_backing_mapping({"s2": "sensor.s2"})

    # Attribute indicators present in context -> use state when numeric
    ctx = {"state": 3, "some_attr": 1}
    assert r.resolve("x", "sensor.s2", ctx) == 3

    # If state missing, ask registry
    class Registry:
        def get_sensor_value(self, key):  # noqa: D401, ANN001
            return 7 if key == "s2" else None

    r.set_sensor_registry_phase(Registry())
    assert r.resolve("x", "sensor.s2", {"some_attr": True}) == 7
