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
    def __init__(self, entity_id: str, **attrs):
        self.entity_id = entity_id
        self.attributes = {**attrs}


class _Hass:
    def __init__(self, states_map: dict[str, _StateObj]):
        self.states = SimpleNamespace(get=lambda eid: states_map.get(eid))


def _sensor_config() -> SensorConfig:
    return SensorConfig(unique_id="unit_phase")


def test_metadata_preprocessing_resolves_entity_id_via_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    hass = _Hass({"sensor.kitchen": _StateObj("sensor.kitchen", friendly_name="Kitchen Power")})
    # Patch HA domains discovery to avoid real registry
    monkeypatch.setattr(
        "ha_synthetic_sensors.shared_constants.get_ha_domains", lambda _h: frozenset({"sensor", "binary_sensor"})
    )
    phase = VariableResolutionPhase()
    # Minimal dependency handler providing hass
    phase.set_dependency_handler(
        SimpleNamespace(hass=hass, data_provider_callback=None, should_use_data_provider=lambda _e: False)
    )
    ctx: dict[str, ReferenceValue] = {"_hass": ReferenceValue(reference="_hass", value=hass)}
    formula = "metadata(sensor.kitchen, 'entity_id') + 1"

    result = phase.resolve_all_references_with_ha_detection(formula, _sensor_config(), ctx)

    # Metadata should be processed into a quoted entity_id string before evaluation
    assert '"sensor.kitchen"' in result.resolved_formula


def test_metadata_preprocessing_without_hass_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch HA domains discovery with a dummy hass to allow earlier steps to pass
    dummy_hass = _Hass({})
    monkeypatch.setattr("ha_synthetic_sensors.shared_constants.get_ha_domains", lambda _h: frozenset({"sensor"}))
    phase = VariableResolutionPhase()
    # Provide dependency handler with hass but omit _hass in context to trigger metadata error
    phase.set_dependency_handler(
        SimpleNamespace(hass=dummy_hass, data_provider_callback=None, should_use_data_provider=lambda _e: False)
    )
    ctx: dict[str, ReferenceValue] = {}
    formula = "metadata(sensor.kitchen, 'entity_id')"

    with pytest.raises(Exception) as exc:
        phase.resolve_all_references_with_ha_detection(formula, _sensor_config(), ctx)
    assert ERROR_METADATA_HASS_NOT_AVAILABLE in str(exc.value)


def test_detects_ha_state_quoted_unavailable_for_early_return(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure earlier steps that build entity regex do not error by patching domains
    monkeypatch.setattr("ha_synthetic_sensors.shared_constants.get_ha_domains", lambda _h: frozenset({"sensor"}))
    phase = VariableResolutionPhase()
    phase.set_dependency_handler(
        SimpleNamespace(hass=_Hass({}), data_provider_callback=None, should_use_data_provider=lambda _e: False)
    )
    ctx: dict[str, ReferenceValue] = {}
    result = phase.resolve_all_references_with_ha_detection('"unavailable"', None, ctx)

    assert result.has_ha_state is True
    assert result.ha_state_value == "unavailable"
