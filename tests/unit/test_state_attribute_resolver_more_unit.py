from ha_synthetic_sensors.config_models import SensorConfig
from ha_synthetic_sensors.evaluator_phases.variable_resolution.state_attribute_resolver import (
    StateAttributeResolver,
)


def test_state_attribute_resolver_simple_and_nested_paths() -> None:
    mapping = {"s1": "sensor.kitchen"}

    def provider(entity_id: str):
        assert entity_id == "sensor.kitchen"
        return {
            "exists": True,
            "value": 0,
            "attributes": {
                "voltage": 240,
                "device_info": {"manufacturer": "ACME"},
                "deep": {"level": 2},
            },
        }

    resolver = StateAttributeResolver(mapping, provider)
    sensor_cfg = SensorConfig(unique_id="s1")

    assert resolver.resolve("x", "state.voltage", {"sensor_config": sensor_cfg}) == 240
    assert resolver.resolve("x", "state.device_info.manufacturer", {"sensor_config": sensor_cfg}) == "ACME"
    # attributes path should work via backing attributes
    assert resolver.resolve("x", "state.attributes.deep.level", {"sensor_config": sensor_cfg}) == 2
