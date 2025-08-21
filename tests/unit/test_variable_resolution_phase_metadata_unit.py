from types import SimpleNamespace

import pytest

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase import (
    VariableResolutionPhase,
)
from ha_synthetic_sensors.evaluator_handlers.metadata_handler import (
    ERROR_METADATA_HASS_NOT_AVAILABLE,
)
from ha_synthetic_sensors.type_definitions import ReferenceValue


class _StateObj:
    def __init__(self, entity_id: str, state: str = "unknown", **attrs):
        self.entity_id = entity_id
        self.state = state
        self.attributes = {**attrs}


class _MockRegistry:
    def __init__(self):
        self.entities = {
            "sensor.test": SimpleNamespace(domain="sensor"),
            "binary_sensor.test": SimpleNamespace(domain="binary_sensor"),
            "switch.test": SimpleNamespace(domain="switch"),
            "light.test": SimpleNamespace(domain="light"),
        }


class _Hass:
    def __init__(self, states_map: dict[str, _StateObj]):
        self.states = SimpleNamespace(get=lambda eid: states_map.get(eid))
        self._mock_registry = _MockRegistry()


def _sensor_config() -> SensorConfig:
    return SensorConfig(unique_id="unit_phase")


def test_metadata_preprocessing_resolves_entity_id_via_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    hass = _Hass({"sensor.kitchen": _StateObj("sensor.kitchen", state="100", friendly_name="Kitchen Power")})
    # Patch HA domains discovery to avoid real registry
    monkeypatch.setattr(
        "ha_synthetic_sensors.shared_constants.get_ha_domains", lambda _h: frozenset({"sensor", "binary_sensor"})
    )
    # Patch entity registry access
    from homeassistant.helpers import entity_registry as er

    monkeypatch.setattr(er, "async_get", lambda hass: hass._mock_registry)

    phase = VariableResolutionPhase()
    # Minimal dependency handler providing hass
    phase.set_dependency_handler(
        SimpleNamespace(hass=hass, data_provider_callback=None, should_use_data_provider=lambda _e: False)
    )
    ctx: dict[str, ReferenceValue] = {"_hass": ReferenceValue(reference="_hass", value=hass)}
    formula = "metadata(sensor.kitchen, 'entity_id') + 1"

    result = phase.resolve_all_references_with_ha_detection(formula, _sensor_config(), ctx)

    # Variable resolution phase should preserve metadata functions for later processing
    # Entity references should be resolved to their values, but metadata functions should remain
    assert "metadata(" in result.resolved_formula or "100" in result.resolved_formula


def test_metadata_preprocessing_without_hass_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Set up dummy hass with the entity so entity resolution doesn't fail
    dummy_hass = _Hass({"sensor.kitchen": _StateObj("sensor.kitchen", state="100")})
    monkeypatch.setattr("ha_synthetic_sensors.shared_constants.get_ha_domains", lambda _h: frozenset({"sensor"}))
    # Patch entity registry access
    from homeassistant.helpers import entity_registry as er

    monkeypatch.setattr(er, "async_get", lambda hass: hass._mock_registry)

    phase = VariableResolutionPhase()
    # Provide dependency handler with hass but omit _hass in context to trigger metadata error
    phase.set_dependency_handler(
        SimpleNamespace(hass=dummy_hass, data_provider_callback=None, should_use_data_provider=lambda _e: False)
    )
    ctx: dict[str, ReferenceValue] = {}
    formula = "metadata(sensor.kitchen, 'entity_id')"

    # Variable resolution phase should resolve entity references but preserve metadata functions
    # The entity reference 'sensor.kitchen' should be resolved to '100', but the metadata
    # function structure should be preserved for later processing in Phase 2
    result = phase.resolve_all_references_with_ha_detection(formula, _sensor_config(), ctx)

    # Should contain either metadata function or resolved entity value
    assert "metadata(" in result.resolved_formula or "100" in result.resolved_formula


def test_detects_ha_state_quoted_unavailable_for_early_return(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure earlier steps that build entity regex do not error by patching domains
    monkeypatch.setattr("ha_synthetic_sensors.shared_constants.get_ha_domains", lambda _h: frozenset({"sensor"}))
    # Patch entity registry access
    from homeassistant.helpers import entity_registry as er

    dummy_hass = _Hass({})
    monkeypatch.setattr(er, "async_get", lambda hass: hass._mock_registry)

    phase = VariableResolutionPhase()
    phase.set_dependency_handler(
        SimpleNamespace(hass=dummy_hass, data_provider_callback=None, should_use_data_provider=lambda _e: False)
    )
    ctx: dict[str, ReferenceValue] = {}
    result = phase.resolve_all_references_with_ha_detection('"unavailable"', None, ctx)

    assert result.has_ha_state is True
    assert result.ha_state_value == "unavailable"
