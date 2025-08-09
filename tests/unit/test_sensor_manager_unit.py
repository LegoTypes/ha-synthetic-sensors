from unittest.mock import MagicMock
import asyncio
import pytest

from ha_synthetic_sensors.config_models import Config, FormulaConfig, SensorConfig
from ha_synthetic_sensors.exceptions import SyntheticSensorsConfigError
from ha_synthetic_sensors.sensor_manager import SensorManager


def _make_manager(mock_hass, mock_entity_registry, mock_states) -> SensorManager:  # noqa: ARG001
    name_resolver = MagicMock()
    add_cb = MagicMock()
    return SensorManager(mock_hass, name_resolver, add_cb)


def test_generate_entity_id_default_and_explicit(mock_hass, mock_entity_registry, mock_states) -> None:  # noqa: ARG001
    mgr = _make_manager(mock_hass, mock_entity_registry, mock_states)

    # Default generation without device_identifier
    eid = mgr._generate_entity_id("my_sensor")
    assert eid == "sensor.my_sensor"

    # Explicit entity_id should be preserved
    cfg = Config(
        sensors=[
            SensorConfig(
                unique_id="s1",
                entity_id="sensor.explicit_id",
                formulas=[FormulaConfig(id="main", formula="1+1")],
            )
        ]
    )

    loop = asyncio.new_event_loop()
    try:
        sensors = loop.run_until_complete(mgr.create_sensors(cfg))
    finally:
        loop.close()
    assert sensors and sensors[0].entity_id == "sensor.explicit_id"


def test_register_data_provider_entities_validation(mock_hass, mock_entity_registry, mock_states) -> None:  # noqa: ARG001
    mgr = _make_manager(mock_hass, mock_entity_registry, mock_states)

    # Empty is an error
    with pytest.raises(SyntheticSensorsConfigError):
        mgr.register_data_provider_entities(set())

    # Invalid entries cause ValueError
    with pytest.raises(ValueError):
        mgr.register_data_provider_entities({"", None})  # type: ignore[arg-type]

    # Valid set works and is returned via getter (copy)
    valid = {"sensor.a", "sensor.b"}
    mgr.register_data_provider_entities(valid)
    got = mgr.get_registered_entities()
    assert got == valid and got is not valid
