"""Integration test for debugging direct entity reference in attributes using public API."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


class TestDirectEntityReferenceDebug:
    """Integration test for direct entity reference resolution in attributes through the public API."""

    @pytest.mark.asyncio
    async def test_direct_entity_reference_in_attributes(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test that direct entity references resolve to actual state values, not defaults."""

        # Set up required entities that YAML references - START WITH "off" state
        mock_states["binary_sensor.front_door"] = Mock(
            state="off", entity_id="binary_sensor.front_door", attributes={"device_class": "door"}
        )

        # Register entity in the entity registry
        mock_entity_registry.register_entity("binary_sensor.front_door", "front_door", "binary_sensor", device_class="door")

        # Set up storage manager with proper mocking
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

            # Create sensor set and load YAML
            sensor_set_id = "boolean_variable_debug"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Boolean Variable Debug Test"
            )

            # Load the focused YAML fixture
            yaml_fixture_path = Path(__file__).parent / "yaml_fixtures" / "boolean_variable_debug.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1, f"Expected 1 sensor imported, got {result['sensors_imported']}"

            # Set up synthetic sensors via public API (Pattern 2: HA Entity References)
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                sensor_set_id=sensor_set_id,
                # No data_provider_callback - uses HA entity lookups
                # No change_notifier - automatic via HA state tracking
                # No sensor_to_backing_mapping - entities from YAML variables
            )

            # Verify sensor manager was created
            assert sensor_manager is not None, "SensorManager was not created"
            assert mock_async_add_entities.call_args_list, "async_add_entities was never called - no entities were added to HA"

            # Get all created entities
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            assert len(all_entities) == 1, (
                f"Wrong entity count: expected 1, got {len(all_entities)}. Entities: {[getattr(e, 'unique_id', 'no_id') for e in all_entities]}"
            )

            # Create lookup for easier testing
            entity_lookup = {entity.unique_id: entity for entity in all_entities}

            # Get our test sensor
            direct_entity_sensor = entity_lookup.get("direct_entity_reference")
            assert direct_entity_sensor is not None, (
                f"Sensor 'direct_entity_reference' not found. Available: {list(entity_lookup.keys())}"
            )

            # Set hass attribute on entity to prevent warnings
            direct_entity_sensor.hass = mock_hass

            # Test formula evaluation with "off" state
            await sensor_manager.async_update_sensors()

            # Get the attributes for "off" state
            attributes_off = direct_entity_sensor.extra_state_attributes
            door_status_off = attributes_off.get("debug_door_status_direct")
            door_status_quoted_off = attributes_off.get("debug_door_status_quoted")

            print(f"TEST 1 - Entity state 'off':")
            print(f"  Mock state: {mock_states['binary_sensor.front_door'].state}")
            print(f"  Unquoted resolved value: {door_status_off} (type: {type(door_status_off)})")
            print(f"  Quoted resolved value: {door_status_quoted_off} (type: {type(door_status_quoted_off)})")

            # Now change the entity state to "on" and test again
            mock_states["binary_sensor.front_door"].state = "on"

            # Update sensors again
            await sensor_manager.async_update_sensors()

            # Get the attributes for "on" state
            attributes_on = direct_entity_sensor.extra_state_attributes
            door_status_on = attributes_on.get("debug_door_status_direct")
            door_status_quoted_on = attributes_on.get("debug_door_status_quoted")

            print(f"\nTEST 2 - Entity state 'on':")
            print(f"  Mock state: {mock_states['binary_sensor.front_door'].state}")
            print(f"  Unquoted resolved value: {door_status_on} (type: {type(door_status_on)})")
            print(f"  Quoted resolved value: {door_status_quoted_on} (type: {type(door_status_quoted_on)})")

            # CRITICAL TEST: The resolved values should be different for different states
            print(f"\nCRITICAL BUG TEST:")
            print(f"  Unquoted 'off' state resolved to: {door_status_off}")
            print(f"  Unquoted 'on' state resolved to: {door_status_on}")
            print(f"  Quoted 'off' state resolved to: {door_status_quoted_off}")
            print(f"  Quoted 'on' state resolved to: {door_status_quoted_on}")

            if door_status_off == door_status_on:
                print(f"  ❌ BUG CONFIRMED: Entity resolution always returns same value regardless of actual state!")
                print(f"  ❌ This indicates entity resolution is broken - not getting actual state from HA")
            else:
                print(f"  ✓ Entity resolution working: Different states produce different values")

            # Test that quoted version should always be the literal string
            if door_status_quoted_off == door_status_quoted_on == "binary_sensor.front_door":
                print(f"  ✓ Quoted version correctly treated as literal string")
            else:
                print(f"  ❌ Quoted version not treated as literal string: {door_status_quoted_off} vs {door_status_quoted_on}")

            # Proper assertions to catch the bug
            assert door_status_off == 0.0, f"Expected 'off' state to resolve to 0.0, got {door_status_off}"
            assert door_status_on == 1.0, f"Expected 'on' state to resolve to 1.0, got {door_status_on}"
            assert door_status_off != door_status_on, (
                f"BUG: Entity resolution returns same value ({door_status_off}) for different states!"
            )

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
