"""Integration test for engine-managed __last_valid_state attribute behavior."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


@pytest.mark.asyncio
async def test_last_good_state_attribute_preserved_and_updated(
    mock_hass,
    mock_entity_registry,
    mock_states,
    mock_config_entry,
    mock_async_add_entities,
    mock_device_registry,
):
    """Verify __last_valid_state/__last_valid_changed are set from calculated state and preserved on alternates."""

    # Save original state for restoration
    original_entities = dict(mock_entity_registry._entities)
    original_states = dict(mock_states)

    try:
        # YAML fixture path for a simple sensor that uses 'state' token
        yaml_path = Path(__file__).parent.parent / "fixtures" / "integration" / "last_good_state_attribute.yaml"
        with open(yaml_path, "r") as f:
            yaml_content = f.read()

        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
            patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "last_good_set"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_last_good",
                name="Last Good Test",
            )

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            # Fixture defines two sensors: the main sensor and a reader sensor
            assert result["sensors_imported"] == 2

            # Backing data provider (virtual backing entity)
            backing_data = {"sensor.test_backing": 10.0}

            def create_data_provider_callback(backing_data: dict[str, any]):
                def data_provider(entity_id: str):
                    return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

                return data_provider

            data_provider = create_data_provider_callback(backing_data)

            sensor_to_backing_mapping = {"last_good_sensor": "sensor.test_backing"}

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Collect created entities and set hass/platform
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)
            mock_platform = Mock()
            for entity in all_entities:
                entity.hass = mock_hass
                entity.platform = mock_platform

            # Initial update - backing=10 -> sensor state = 20
            await sensor_manager.async_update_sensors()

            entity_lookup = {entity.unique_id: entity for entity in all_entities}
            sensor = entity_lookup.get("last_good_sensor")
            assert sensor is not None, f"Sensor not found. Available: {list(entity_lookup.keys())}"

            # Validate calculated native value
            assert float(sensor.native_value) == 20.0, f"Expected 20.0, got {sensor.native_value}"

            attrs = getattr(sensor, "extra_state_attributes", {}) or {}
            # last_valid_state should be set to the calculated state (20.0)
            assert "last_valid_state" in attrs, "last_valid_state attribute missing"
            assert float(attrs["last_valid_state"]) == 20.0, f"Expected last_valid_state 20.0, got {attrs['last_valid_state']}"
            assert "last_valid_changed" in attrs, "last_valid_changed attribute missing"

            first_ts = attrs["last_valid_changed"]

            # Simulate backing entity becoming None/unavailable -> alternate state
            backing_data["sensor.test_backing"] = None
            await sensor_manager.async_update_sensors_for_entities({"sensor.test_backing"})

            # After alternate write, __last_valid_state should remain unchanged
            attrs = getattr(sensor, "extra_state_attributes", {}) or {}
            assert float(attrs.get("last_valid_state", 0)) == 20.0, "last_valid_state should be preserved on alternate state"
            assert attrs.get("last_valid_changed") == first_ts, "last_valid_changed should be preserved on alternate state"

            # Now restore new valid backing value -> should update last-good
            backing_data["sensor.test_backing"] = 11.0
            await sensor_manager.async_update_sensors_for_entities({"sensor.test_backing"})

            attrs = getattr(sensor, "extra_state_attributes", {}) or {}
            # New calculated value = 22.0
            assert float(attrs.get("last_valid_state", 0)) == 22.0, (
                f"Expected updated last_valid_state 22.0, got {attrs.get('last_valid_state')}"
            )
            assert attrs.get("last_valid_changed") != first_ts, "last_valid_changed should be updated after new valid state"

            # After new valid backing (22.0), attribute should update
            await sensor_manager.async_update_sensors()
            attrs = getattr(sensor, "extra_state_attributes", {}) or {}
            assert float(attrs.get("last_valid_state", 0)) == 22.0, (
                f"Attribute updated should be 22.0, got {attrs.get('last_valid_state')}"
            )

            await storage_manager.async_delete_sensor_set(sensor_set_id)

    finally:
        # Restore original state
        mock_entity_registry._entities.clear()
        mock_entity_registry._entities.update(original_entities)
        mock_states.clear()
        mock_states.update(original_states)
