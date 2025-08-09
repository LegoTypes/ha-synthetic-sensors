from types import SimpleNamespace

import pytest

from ha_synthetic_sensors.evaluator_handlers.metadata_handler import MetadataHandler
from ha_synthetic_sensors.type_definitions import ReferenceValue


class _StateObj:
    def __init__(self, entity_id: str):
        self.entity_id = entity_id
        self.attributes = {"friendly_name": "Kitchen Power"}


class _Hass:
    def __init__(self, states_map: dict[str, _StateObj]):
        self.states = SimpleNamespace(get=lambda eid: states_map.get(eid))


def test_process_metadata_functions_resolves_with_referencevalue_hass() -> None:
    hass = _Hass({"sensor.kitchen": _StateObj("sensor.kitchen")})
    context = {"_hass": ReferenceValue(reference="_hass", value=hass)}
    formula = "metadata(sensor.kitchen, 'entity_id')"
    out = MetadataHandler.process_metadata_functions(formula, context)
    # entity_id returns quoted string via handler.process substitution for consistency
    assert out == '"sensor.kitchen"'


def test_metadata_handler_evaluate_with_variable_and_key() -> None:
    hass = _Hass({"sensor.kitchen": _StateObj("sensor.kitchen")})
    handler = MetadataHandler(hass=hass)
    ctx = {"dev": ReferenceValue(reference="sensor.kitchen", value=0)}
    out = handler.evaluate("metadata(dev, 'friendly_name')", ctx)
    # Should return quoted string in processed formula
    assert out == '"Kitchen Power"'


def test_process_metadata_functions_missing_hass_is_fatal() -> None:
    with pytest.raises(Exception):
        MetadataHandler.process_metadata_functions("metadata(sensor.kitchen, 'entity_id')", context={})
