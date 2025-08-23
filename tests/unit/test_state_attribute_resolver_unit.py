from types import SimpleNamespace

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.evaluator_phases.variable_resolution.state_attribute_resolver import (
    StateAttributeResolver,
)


def _make_dep_handler(data_provider=None):
    return SimpleNamespace(data_provider_callback=data_provider, should_use_data_provider=lambda _e: data_provider is not None)


def test_simple_state_attribute_resolution_via_provider() -> None:
    # sensor key -> backing entity mapping
    mapping = {"sensor1": "sensor.kitchen"}
    sensor_cfg = SensorConfig(unique_id="sensor1", formulas=[FormulaConfig(id="main", formula="1+1")])

    def provider(entity_id: str):
        assert entity_id == "sensor.kitchen"
        return {"exists": True, "attributes": {"voltage": 240}}

    r = StateAttributeResolver(sensor_to_backing_mapping=mapping, data_provider_callback=provider)
    context = {"sensor_config": sensor_cfg}
    result = r.resolve("state", "state.voltage", context)
    # Resolvers return raw values, ReferenceValue objects are created by VariableResolutionPhase
    assert result == 240


def test_nested_state_attribute_resolution_via_provider() -> None:
    mapping = {"sensor1": "sensor.kitchen"}
    sensor_cfg = SensorConfig(unique_id="sensor1", formulas=[FormulaConfig(id="main", formula="1+1")])

    def provider(_):
        return {"exists": True, "attributes": {"device_info": {"manufacturer": "Acme"}}}

    r = StateAttributeResolver(sensor_to_backing_mapping=mapping, data_provider_callback=provider)
    context = {"sensor_config": sensor_cfg}
    result = r.resolve("state", "state.device_info.manufacturer", context)
    # Resolvers return raw values, ReferenceValue objects are created by VariableResolutionPhase
    assert result == "Acme"
