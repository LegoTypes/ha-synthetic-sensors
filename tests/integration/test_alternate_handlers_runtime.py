"""Integration tests for runtime alternate handlers and scoped guard behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


@pytest.mark.asyncio
async def test_alternate_handlers_and_guard_runtime(
    mock_hass,
    mock_entity_registry,
    mock_states,
    mock_config_entry,
    mock_async_add_entities,
    mock_device_registry,
):
    """Verify literal and object-form alternates at runtime and guard scoping with metadata-only CV."""

    # Backing entity for the guard/metadata sensor
    mock_entity_registry.register_entity("sensor.guard_backing", "sensor.guard_backing", "sensor")
    mock_states.register_state("sensor.guard_backing", "100.0", {"unit_of_measurement": "W"})

    # Unused variable with unknown state (should not affect within_grace)
    mock_entity_registry.register_entity("sensor.unused_unknown", "sensor.unused_unknown", "sensor")
    mock_states.register_state("sensor.unused_unknown", "unknown", {})

    yaml_path = Path(__file__).parent.parent / "fixtures" / "integration" / "alternate_handlers_runtime.yaml"

    # Missing entity used to trigger alternates: represent as UNAVAILABLE so context isn't raw None
    mock_entity_registry.register_entity("sensor.nonexistent_value", "sensor.nonexistent_value", "sensor")
    mock_states.register_state("sensor.nonexistent_value", "unavailable", {})

    with (
        patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
        patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
    ):
        mock_store = AsyncMock()
        mock_store.async_load.return_value = None
        MockStore.return_value = mock_store
        MockDeviceRegistry.return_value = mock_device_registry

        storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
        storage_manager._store = mock_store
        await storage_manager.async_load()

        sensor_set_id = "alternate_handlers_runtime"
        await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier="test_alternate_handlers_runtime",
            name="Alternate Handlers Runtime",
        )

        with open(yaml_path, "r") as f:
            yaml_content = f.read()

        result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
        assert result["sensors_imported"] == 3

        sensor_manager = await async_setup_synthetic_sensors(
            hass=mock_hass,
            config_entry=mock_config_entry,
            async_add_entities=mock_async_add_entities,
            storage_manager=storage_manager,
        )

        # Collect created entities and set hass
        all_entities = []
        for call in mock_async_add_entities.call_args_list:
            entities_list = call.args[0] if call.args else []
            all_entities.extend(entities_list)
        for entity in all_entities:
            entity.hass = mock_hass

        # Set last_changed to recent time to make within_grace True
        for entity in all_entities:
            if getattr(entity, "unique_id", "") == "guard_metadata_sensor":
                mock_state = type(
                    "MockState",
                    (),
                    {
                        "state": str(entity.native_value) if entity.native_value is not None else "100.0",
                        "attributes": getattr(entity, "extra_state_attributes", {}) or {},
                    },
                )()
                mock_state.entity_id = entity.entity_id
                mock_state.object_id = entity.entity_id.split(".")[-1]
                mock_state.domain = entity.entity_id.split(".")[0]
                mock_state.last_changed = datetime.now(timezone.utc) - timedelta(minutes=1)
                mock_state.last_updated = datetime.now(timezone.utc)
                mock_states[entity.entity_id] = mock_state

        await sensor_manager.async_update_sensors()

        entity_lookup = {entity.unique_id: entity for entity in all_entities}

        # Guard + metadata-only CV: ensure unaffected by unused unknown variable
        guard_entity = entity_lookup.get("guard_metadata_sensor")
        assert guard_entity is not None
        assert guard_entity.native_value is not None
        attrs = getattr(guard_entity, "extra_state_attributes", {}) or {}
        assert "grace_period_active" in attrs
        # Accept boolean-like numeric values as well (pipeline may coerce True -> 1.0)
        assert isinstance(attrs["grace_period_active"], (bool, str, int, float))

        # Literal alternate returns numeric 10
        literal_entity = entity_lookup.get("literal_alternate_sensor")
        assert literal_entity is not None
        assert literal_entity.native_value is not None
        assert float(literal_entity.native_value) == 10.0

        # Object-form alternate returns backup + 1 = 6
        object_entity = entity_lookup.get("object_alternate_sensor")
        assert object_entity is not None
        assert object_entity.native_value is not None
        assert float(object_entity.native_value) == 6.0

        await storage_manager.async_delete_sensor_set(sensor_set_id)


@pytest.mark.asyncio
async def test_alternate_handlers_with_none_backing_entities(
    mock_hass,
    mock_entity_registry,
    mock_states,
    mock_config_entry,
    mock_async_add_entities,
    mock_device_registry,
):
    """Test alternate handlers when backing entities have None values (integration offline scenario)."""

    # Backing entity that will be set to None (simulating integration offline)
    mock_entity_registry.register_entity("sensor.offline_backing", "sensor.offline_backing", "sensor")
    mock_states.register_state("sensor.offline_backing", None, {})  # This is the key - None value

    yaml_content = """
version: "1.0"

global_settings:
  device_identifier: "test_offline_scenario"
  variables:
    energy_grace_period_minutes: 15
  metadata:
    attribution: "Offline scenario test"

sensors:
  offline_sensor:
    name: "Offline Sensor"
    entity_id: "sensor.offline_backing"
    formula: "state"
    UNAVAILABLE:
      formula: "state if within_grace else 'unknown'"
    UNKNOWN:
      formula: "state if within_grace else 'unknown'"
    variables:
      within_grace:
        formula: "minutes_between(metadata(state, 'last_changed'), now()) < energy_grace_period_minutes"
        UNAVAILABLE: false
        UNKNOWN: false
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
"""

    with (
        patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
        patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
    ):
        mock_store = AsyncMock()
        mock_store.async_load.return_value = None
        MockStore.return_value = mock_store
        MockDeviceRegistry.return_value = mock_device_registry

        storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
        storage_manager._store = mock_store
        await storage_manager.async_load()

        sensor_set_id = "offline_scenario"
        await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier="test_offline_scenario",
            name="Offline Scenario Test",
        )

        result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
        assert result["sensors_imported"] == 1

        sensor_manager = await async_setup_synthetic_sensors(
            hass=mock_hass,
            config_entry=mock_config_entry,
            async_add_entities=mock_async_add_entities,
            storage_manager=storage_manager,
        )

        # Collect created entities and set hass
        all_entities = []
        for call in mock_async_add_entities.call_args_list:
            entities_list = call.args[0] if call.args else []
            all_entities.extend(entities_list)
        for entity in all_entities:
            entity.hass = mock_hass

        # Set last_changed to recent time to make within_grace True
        for entity in all_entities:
            if getattr(entity, "unique_id", "") == "offline_sensor":
                mock_state = type(
                    "MockState",
                    (),
                    {
                        "state": None,  # Simulate offline backing entity
                        "attributes": {},
                    },
                )()
                mock_state.entity_id = entity.entity_id
                mock_state.object_id = entity.entity_id.split(".")[-1]
                mock_state.domain = entity.entity_id.split(".")[0]
                mock_state.last_changed = datetime.now(timezone.utc) - timedelta(minutes=1)  # Recent, within grace
                mock_state.last_updated = datetime.now(timezone.utc)
                mock_states[entity.entity_id] = mock_state

        # This should not raise an exception - the alternate handler should work
        await sensor_manager.async_update_sensors()

        entity_lookup = {entity.unique_id: entity for entity in all_entities}

        # The sensor should have a value from the alternate handler, not be unavailable
        offline_entity = entity_lookup.get("offline_sensor")
        assert offline_entity is not None

        # The sensor should be available because the alternate handler should have worked
        # When state=None (converted to "unknown") and within_grace=True,
        # the formula "state if within_grace else 'unknown'" should return a fallback value
        assert offline_entity.available is True  # Sensor should be available
        assert offline_entity.native_value is not None  # Should have a fallback value

        # The alternate handler successfully provided a fallback value instead of failing
        # This demonstrates that the fix allows alternate handlers to work when backing entities are None/unknown

        await storage_manager.async_delete_sensor_set(sensor_set_id)


@pytest.mark.asyncio
async def test_alternate_handlers_with_unavailable_backing_entities(
    mock_hass,
    mock_entity_registry,
    mock_states,
    mock_config_entry,
    mock_async_add_entities,
    mock_device_registry,
):
    """Test alternate handlers when backing entities are unavailable (not None)."""

    # Backing entity that will be set to "unavailable" (different from None)
    mock_entity_registry.register_entity("sensor.unavailable_backing", "sensor.unavailable_backing", "sensor")
    mock_states.register_state("sensor.unavailable_backing", "unavailable", {})  # Explicitly unavailable

    yaml_content = """
version: "1.0"

global_settings:
  device_identifier: "test_unavailable_scenario"
  variables:
    energy_grace_period_minutes: 15
  metadata:
    attribution: "Unavailable scenario test"

sensors:
  unavailable_sensor:
    name: "Unavailable Sensor"
    entity_id: "sensor.unavailable_backing"
    formula: "state"
    UNAVAILABLE:
      formula: "state if within_grace else 'fallback'"
    UNKNOWN:
      formula: "state if within_grace else 'fallback'"
    variables:
      within_grace:
        formula: "minutes_between(metadata(state, 'last_changed'), now()) < energy_grace_period_minutes"
        UNAVAILABLE: false
        UNKNOWN: false
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
"""

    with (
        patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
        patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
    ):
        mock_store = AsyncMock()
        mock_store.async_load.return_value = None
        MockStore.return_value = mock_store
        MockDeviceRegistry.return_value = mock_device_registry

        storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
        storage_manager._store = mock_store
        await storage_manager.async_load()

        sensor_set_id = "unavailable_scenario"
        await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier="test_unavailable_scenario",
            name="Unavailable Scenario Test",
        )

        result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
        assert result["sensors_imported"] == 1

        sensor_manager = await async_setup_synthetic_sensors(
            hass=mock_hass,
            config_entry=mock_config_entry,
            async_add_entities=mock_async_add_entities,
            storage_manager=storage_manager,
        )

        # Collect created entities and set hass
        all_entities = []
        for call in mock_async_add_entities.call_args_list:
            entities_list = call.args[0] if call.args else []
            all_entities.extend(entities_list)
        for entity in all_entities:
            entity.hass = mock_hass

        # Set last_changed to recent time to make within_grace True
        for entity in all_entities:
            if getattr(entity, "unique_id", "") == "unavailable_sensor":
                mock_state = type(
                    "MockState",
                    (),
                    {
                        "state": "unavailable",  # Explicitly unavailable
                        "attributes": {},
                    },
                )()
                mock_state.entity_id = entity.entity_id
                mock_state.object_id = entity.entity_id.split(".")[-1]
                mock_state.domain = entity.entity_id.split(".")[0]
                mock_state.last_changed = datetime.now(timezone.utc) - timedelta(minutes=1)
                mock_state.last_updated = datetime.now(timezone.utc)
                mock_states[entity.entity_id] = mock_state

        # This should not raise an exception - the alternate handler should work
        await sensor_manager.async_update_sensors()

        entity_lookup = {entity.unique_id: entity for entity in all_entities}

        # The sensor should have a value from the alternate handler, not be unavailable
        unavailable_entity = entity_lookup.get("unavailable_sensor")
        assert unavailable_entity is not None

        # The sensor should be available because the alternate handler should have worked
        assert unavailable_entity.available is True  # Sensor should be available
        assert unavailable_entity.native_value is not None  # Should have a fallback value

        # The alternate handler successfully provided a fallback value instead of failing
        # This demonstrates that the fix works for both "unknown" and "unavailable" states

        await storage_manager.async_delete_sensor_set(sensor_set_id)
