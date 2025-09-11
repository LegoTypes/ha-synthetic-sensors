"""Integration test for debugging direct entity reference in attributes using public API."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


class TestDirectEntityReferenceDebug:
    """Integration test for direct entity reference resolution in attributes through the public API."""

    @pytest.mark.asyncio
    async def test_direct_entity_reference_in_attributes(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test that panel status attributes update correctly when main sensor is None but uses fallback."""

        # Set up entities for the test
        # Virtual backing entity (only exists in data provider, not in HA)
        mock_states["sensor.backing_energy_data"] = Mock(
            state="100.0", entity_id="sensor.backing_energy_data", attributes={"device_class": "energy"}
        )
        
        # Real HA panel status sensor - START WITH "on" state (panel online)
        mock_states["binary_sensor.virtual_panel_status_test"] = Mock(
            state="on", entity_id="binary_sensor.virtual_panel_status_test", attributes={"device_class": "connectivity"}
        )

        # Register the panel status sensor in HA entity registry (it's a real HA entity)
        mock_entity_registry.register_entity("binary_sensor.virtual_panel_status_test", "virtual_panel_status_test", "binary_sensor", device_class="connectivity")
        
        # Note: The backing entity is NOT registered in HA - it only exists in the data provider

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

            # Create data provider callback that returns mock state (correct signature)
            def data_provider_callback(entity_id: str) -> dict[str, Any]:
                """Provide mock data for the test."""
                print(f"🔍 Data provider called with entity_id: {entity_id}")
                
                if entity_id in mock_states:
                    value = mock_states[entity_id].state
                    exists = True
                    print(f"  ✅ {entity_id} -> {value}")
                else:
                    value = None
                    exists = False
                    print(f"  ❌ {entity_id} not found in mock_states")
                
                result = {"value": value, "exists": exists}
                print(f"🔍 Data provider returning: {result}")
                return result
            
            # Set up synthetic sensors via public API with data provider
            sensor_to_backing_mapping = {
                "panel_status_fallback_test": "sensor.backing_energy_data"
            }
            
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                sensor_set_id=sensor_set_id,
                data_provider_callback=data_provider_callback,
                # No change_notifier - manual updates via async_update_sensors
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )
            
            # CRITICAL: Register the backing entity with the sensor manager
            # This tells the synthetic sensor system about our virtual backing entity
            backing_entity_ids = {"sensor.backing_energy_data"}
            sensor_manager.register_data_provider_entities(backing_entity_ids)
            print(f"✅ Registered backing entities: {backing_entity_ids}")

            # Verify sensor manager was created
            assert sensor_manager is not None, "SensorManager was not created"
            assert mock_async_add_entities.call_args_list, "async_add_entities was never called - no entities were added to HA"

            # Get all created entities
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            assert len(all_entities) == 1, f"Wrong entity count: expected 1, got {len(all_entities)}. Entities: {[getattr(e, 'unique_id', 'no_id') for e in all_entities]}"

            # Create lookup for easier testing
            entity_lookup = {entity.unique_id: entity for entity in all_entities}

            # Get our test sensor
            test_sensor = entity_lookup.get("panel_status_fallback_test")
            assert test_sensor is not None, f"Sensor 'panel_status_fallback_test' not found. Available: {list(entity_lookup.keys())}"

            # Set hass attribute on entity to prevent warnings
            test_sensor.hass = mock_hass

            # TEST 1: Normal operation - main sensor has value, panel is online
            await sensor_manager.async_update_sensors()

            attributes_normal = test_sensor.extra_state_attributes
            panel_status_normal = attributes_normal.get('debug_panel_status_is')
            panel_status_direct_normal = attributes_normal.get('debug_panel_status_direct')
            main_sensor_state_normal = attributes_normal.get('debug_main_sensor_state')
            fallback_used_normal = attributes_normal.get('debug_fallback_used')

            print(f"TEST 1 - Normal operation (backing entity: {mock_states['sensor.backing_energy_data'].state}, panel: {mock_states['binary_sensor.virtual_panel_status_test'].state}):")
            print(f"  Main sensor state: {test_sensor.state}")
            print(f"  Panel status (via variable): {panel_status_normal}")
            print(f"  Panel status (direct): {panel_status_direct_normal}")
            print(f"  Main sensor state attr: {main_sensor_state_normal}")
            print(f"  Fallback used: {fallback_used_normal}")
            
            # TEST 2: Set backing entity to None to trigger fallback, panel still online
            mock_states["sensor.backing_energy_data"].state = None
            
            await sensor_manager.async_update_sensors()
            
            attributes_fallback_panel_on = test_sensor.extra_state_attributes
            panel_status_fallback_on = attributes_fallback_panel_on.get('debug_panel_status_is')
            panel_status_direct_fallback_on = attributes_fallback_panel_on.get('debug_panel_status_direct')
            main_sensor_state_fallback_on = attributes_fallback_panel_on.get('debug_main_sensor_state')
            fallback_used_fallback_on = attributes_fallback_panel_on.get('debug_fallback_used')

            print(f"\nTEST 2 - Fallback triggered, panel online (backing entity: {mock_states['sensor.backing_energy_data'].state}, panel: {mock_states['binary_sensor.virtual_panel_status_test'].state}):")
            print(f"  Main sensor state: {test_sensor.state}")
            print(f"  Panel status (via variable): {panel_status_fallback_on}")
            print(f"  Panel status (direct): {panel_status_direct_fallback_on}")
            print(f"  Main sensor state attr: {main_sensor_state_fallback_on}")
            print(f"  Fallback used: {fallback_used_fallback_on}")
            
            # TEST 3: Keep backing entity None, change panel to offline
            mock_states["binary_sensor.virtual_panel_status_test"].state = "off"
            
            await sensor_manager.async_update_sensors()
            
            attributes_fallback_panel_off = test_sensor.extra_state_attributes
            panel_status_fallback_off = attributes_fallback_panel_off.get('debug_panel_status_is')
            panel_status_direct_fallback_off = attributes_fallback_panel_off.get('debug_panel_status_direct')
            main_sensor_state_fallback_off = attributes_fallback_panel_off.get('debug_main_sensor_state')
            fallback_used_fallback_off = attributes_fallback_panel_off.get('debug_fallback_used')

            print(f"\nTEST 3 - Fallback active, panel offline (backing entity: {mock_states['sensor.backing_energy_data'].state}, panel: {mock_states['binary_sensor.virtual_panel_status_test'].state}):")
            print(f"  Main sensor state: {test_sensor.state}")
            print(f"  Panel status (via variable): {panel_status_fallback_off}")
            print(f"  Panel status (direct): {panel_status_direct_fallback_off}")
            print(f"  Main sensor state attr: {main_sensor_state_fallback_off}")
            print(f"  Fallback used: {fallback_used_fallback_off}")
            
            # TEST 4: Change panel back to online while backing entity still None
            mock_states["binary_sensor.virtual_panel_status_test"].state = "on"
            
            await sensor_manager.async_update_sensors()
            
            attributes_fallback_panel_back_on = test_sensor.extra_state_attributes
            panel_status_fallback_back_on = attributes_fallback_panel_back_on.get('debug_panel_status_is')
            panel_status_direct_fallback_back_on = attributes_fallback_panel_back_on.get('debug_panel_status_direct')

            print(f"\nTEST 4 - Fallback active, panel back online (backing entity: {mock_states['sensor.backing_energy_data'].state}, panel: {mock_states['binary_sensor.virtual_panel_status_test'].state}):")
            print(f"  Main sensor state: {test_sensor.state}")
            print(f"  Panel status (via variable): {panel_status_fallback_back_on}")
            print(f"  Panel status (direct): {panel_status_direct_fallback_back_on}")
            
            # CRITICAL ASSERTIONS: Panel status attributes should update even when main sensor uses fallback
            print(f"\nCRITICAL PANEL STATUS UPDATE TEST:")
            print(f"  Panel online (normal): {panel_status_normal}")
            print(f"  Panel online (fallback): {panel_status_fallback_on}")
            print(f"  Panel offline (fallback): {panel_status_fallback_off}")
            print(f"  Panel back online (fallback): {panel_status_fallback_back_on}")
            
            # Main sensor should use fallback value when state is None
            assert test_sensor.state == 42.0, f"Expected fallback value 42.0, got {test_sensor.state}"
            assert fallback_used_fallback_on is True, f"Expected fallback_used to be True when main sensor is None"
            
            # Panel status attributes should reflect actual panel state changes
            assert panel_status_normal == 1.0, f"Expected panel online (1.0) in normal operation, got {panel_status_normal}"
            assert panel_status_fallback_on == 1.0, f"Expected panel online (1.0) during fallback, got {panel_status_fallback_on}"
            assert panel_status_fallback_off == 0.0, f"Expected panel offline (0.0) during fallback, got {panel_status_fallback_off}"
            assert panel_status_fallback_back_on == 1.0, f"Expected panel back online (1.0) during fallback, got {panel_status_fallback_back_on}"
            
            # Direct panel status should also update
            assert panel_status_direct_fallback_off == 0.0, f"Expected direct panel offline (0.0), got {panel_status_direct_fallback_off}"
            assert panel_status_direct_fallback_back_on == 1.0, f"Expected direct panel back online (1.0), got {panel_status_direct_fallback_back_on}"
            
            # Critical test: Panel status should change even during fallback
            if panel_status_fallback_on == panel_status_fallback_off:
                print(f"  ❌ BUG CONFIRMED: Panel status attribute does not update during fallback!")
                print(f"  ❌ Panel status stays {panel_status_fallback_on} regardless of actual panel state")
            else:
                print(f"  ✓ Panel status attribute updates correctly during fallback")
                
            assert panel_status_fallback_on != panel_status_fallback_off, f"BUG: Panel status attribute does not update during fallback! Both values: {panel_status_fallback_on}"

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
