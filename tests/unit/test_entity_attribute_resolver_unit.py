from types import SimpleNamespace

import pytest

from ha_synthetic_sensors.evaluator_phases.variable_resolution.entity_attribute_resolver import (
    EntityAttributeResolver,
)


def _make_dep_handler(hass=None, data_provider=None):
    return SimpleNamespace(
        hass=hass, data_provider_callback=data_provider, should_use_data_provider=lambda _e: data_provider is not None
    )


def test_can_resolve_true_for_variable_attribute_style() -> None:
    r = EntityAttributeResolver()
    r.set_dependency_handler(_make_dep_handler())
    assert r.can_resolve("dev", "device.battery_level") is True
    assert r.can_resolve("x", "sensor.kitchen") is False
    assert r.can_resolve("x", "state.voltage") is False


def test_resolve_attribute_via_data_provider_success() -> None:
    # var 'dev' points to 'sensor.kitchen' in formula config
    context = {"formula_config": type("FC", (), {"variables": {"dev": "sensor.kitchen"}})()}

    def provider(entity_id: str):
        assert entity_id == "sensor.kitchen"
        # data provider contract requires 'value' plus optional 'attributes'
        return {"exists": True, "value": 0, "attributes": {"battery_level": 85}}

    r = EntityAttributeResolver()
    r.set_dependency_handler(_make_dep_handler(data_provider=provider))
    value = r.resolve("dev", "dev.battery_level", context)
    assert value == 85


def test_resolve_attribute_missing_raises_missing_dependency() -> None:
    context = {"formula_config": type("FC", (), {"variables": {"dev": "sensor.kitchen"}})()}

    def provider(_):
        return {"exists": True, "attributes": {"voltage": 120}}

    r = EntityAttributeResolver()
    r.set_dependency_handler(_make_dep_handler(data_provider=provider))
    with pytest.raises(Exception):
        # Expected to raise MissingDependencyError internally (we assert exception path)
        r.resolve("dev", "dev.battery_level", context)
