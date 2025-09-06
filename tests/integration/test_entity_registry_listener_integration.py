"""Integration test for EntityRegistryListener with real storage.

This test follows the new template pattern from integration_test_guide.md.
"""

from unittest.mock import AsyncMock, patch
import pytest
from homeassistant.core import Event
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors
from ha_synthetic_sensors.entity_registry_listener import EntityRegistryListener
from ha_synthetic_sensors.entity_change_handler import EntityChangeHandler


class TestEntityRegistryListenerIntegration:
    """Integration tests for EntityRegistryListener with real storage."""

    @pytest.mark.asyncio
    async def test_entity_id_change_updates_storage_and_sensors(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_device_registry,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test that entity ID changes update storage and trigger sensor updates."""

        # =============================================================================
        # CUSTOMIZE THIS SECTION FOR YOUR TEST
        # =============================================================================

        # 1. Set up your required entities (entities your YAML references)
        required_entities = {
            "sensor.power_meter": {"state": "1000.0", "attributes": {"unit": "W"}},
            "sensor.voltage_meter": {"state": "240.0", "attributes": {"unit": "V"}},
        }

        # 2. Define your YAML file path and expected sensor count
        yaml_file_path = "tests/fixtures/integration/test_entity_registry_listener_integration.yaml"
        expected_sensor_count = 2
        device_identifier = "test_device_entity_listener"

        # =============================================================================
        # STANDARD SETUP (DON'T CHANGE UNLESS YOU KNOW WHAT YOU'RE DOING)
        # =============================================================================

        # Save original state for cleanup
        original_entities = dict(mock_entity_registry._entities)
        original_states = dict(mock_states)

        try:
            # Register required entities
            for entity_id, data in required_entities.items():
                mock_entity_registry.register_entity(entity_id, entity_id, "sensor")
                mock_states.register_state(entity_id, data["state"], data["attributes"])

            # Set up storage manager with standard pattern
            with (
                patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
                patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
            ):
                # Standard mock setup
                mock_store = AsyncMock()
                mock_store.async_load.return_value = None
                MockStore.return_value = mock_store
                MockDeviceRegistry.return_value = mock_device_registry

                # Create storage manager with entity listener enabled
                storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=True)
                storage_manager._store = mock_store
                await storage_manager.async_load()

                # Create sensor set
                sensor_set_id = "test_sensor_set"
                await storage_manager.async_create_sensor_set(
                    sensor_set_id=sensor_set_id, device_identifier=device_identifier, name="Test Sensor Set"
                )

                # Load YAML configuration
                with open(yaml_file_path) as f:
                    yaml_content = f.read()

                result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

                # BULLETPROOF ASSERTION 1: YAML import must succeed with exact count
                assert result["sensors_imported"] == expected_sensor_count, (
                    f"YAML import failed: expected {expected_sensor_count} sensors, "
                    f"got {result['sensors_imported']}. Result: {result}"
                )

                # Set up synthetic sensors
                sensor_manager = await async_setup_synthetic_sensors(
                    hass=mock_hass,
                    config_entry=mock_config_entry,
                    async_add_entities=mock_async_add_entities,
                    storage_manager=storage_manager,
                )

                # BULLETPROOF ASSERTION 2: Sensor manager must be created
                assert sensor_manager is not None, "Sensor manager creation failed"

                # BULLETPROOF ASSERTION 3: Entities must be added to HA
                assert mock_async_add_entities.call_args_list, (
                    "async_add_entities was never called - no entities were added to HA"
                )

                # Update sensors to ensure formulas are evaluated
                await sensor_manager.async_update_sensors()

                # Get all created entities
                all_entities = []
                for call in mock_async_add_entities.call_args_list:
                    entities_list = call.args[0] if call.args else []
                    all_entities.extend(entities_list)

                # BULLETPROOF ASSERTION 4: Exact entity count verification
                assert len(all_entities) == expected_sensor_count, (
                    f"Wrong number of entities created: expected {expected_sensor_count}, "
                    f"got {len(all_entities)}. Entities: {[getattr(e, 'unique_id', 'no_id') for e in all_entities]}"
                )

                # Create lookup for easier testing
                entity_lookup = {entity.unique_id: entity for entity in all_entities}

                # =============================================================================
                # ENTITY REGISTRY LISTENER SPECIFIC TESTS
                # =============================================================================

                # Get the entity registry listener from storage manager (private attribute)
                entity_listener = storage_manager._entity_registry_listener
                assert entity_listener is not None, "Entity listener should be enabled"

                # Verify initial state - sensors should reference original entities
                power_sensor = entity_lookup.get("power_analysis")
                assert power_sensor is not None, "Power analysis sensor not found"

                # Get the sensor set to check entity tracking
                sensor_set = storage_manager.get_sensor_set(sensor_set_id)
                assert sensor_set is not None, "Sensor set not found"

                # Verify original entities are tracked
                assert sensor_set.is_entity_tracked("sensor.power_meter"), "Original power meter entity not tracked"
                assert sensor_set.is_entity_tracked("sensor.voltage_meter"), "Original voltage meter entity not tracked"

                # =============================================================================
                # TEST ENTITY ID CHANGE PROCESSING
                # =============================================================================

                # Register the new entity that we'll change to
                new_entity_id = "sensor.power_meter_new"
                mock_entity_registry.register_entity(new_entity_id, new_entity_id, "sensor")
                mock_states.register_state(new_entity_id, "1100.0", {"unit": "W"})

                # Create entity registry update event
                event = Event(
                    EVENT_ENTITY_REGISTRY_UPDATED,
                    {
                        "action": "update",
                        "entity_id": new_entity_id,
                        "old_entity_id": "sensor.power_meter",
                        "changes": {"entity_id": "sensor.power_meter"},
                    },
                )

                # Process the entity ID change
                await entity_listener._async_process_entity_id_change("sensor.power_meter", new_entity_id)

                # =============================================================================
                # VERIFY STORAGE WAS UPDATED
                # =============================================================================

                # Verify storage was saved (entity replacement should trigger save)
                mock_store.async_save.assert_called()

                # Get the updated sensor configuration to verify the entity ID was replaced
                updated_sensors = sensor_set.list_sensors()
                power_analysis_sensor = None
                for sensor in updated_sensors:
                    if sensor.unique_id == "power_analysis":
                        power_analysis_sensor = sensor
                        break

                assert power_analysis_sensor is not None, "Power analysis sensor not found after update"

                # Check if the formula variables were updated
                power_formula = power_analysis_sensor.formulas[0] if power_analysis_sensor.formulas else None
                assert power_formula is not None, "Power analysis sensor should have a formula"

                # The variable should now reference the new entity ID
                power_input_var = power_formula.variables.get("power_input")
                assert power_input_var == new_entity_id, (
                    f"Expected power_input variable to be {new_entity_id}, got {power_input_var}"
                )

                # =============================================================================
                # VERIFY ENTITY INDEX WAS UPDATED
                # =============================================================================

                # The entity index should now track the new entity instead of the old one
                # Note: The architecture reloads all managers from storage after entity ID changes,
                # which rebuilds the entity indexes with the updated configurations
                assert not sensor_set.is_entity_tracked("sensor.power_meter"), (
                    "Old power meter entity should not be tracked after reload"
                )
                assert sensor_set.is_entity_tracked(new_entity_id), "New power meter entity should be tracked after reload"

        finally:
            # =============================================================================
            # CLEANUP (ALWAYS RUNS)
            # =============================================================================

            # Restore original state
            mock_entity_registry._entities.clear()
            mock_entity_registry._entities.update(original_entities)
            mock_states.clear()
            mock_states.update(original_states)

    @pytest.mark.asyncio
    async def test_entity_id_change_in_global_variables(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_device_registry,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test that entity ID changes in global variables are handled correctly."""

        # =============================================================================
        # CUSTOMIZE THIS SECTION FOR YOUR TEST
        # =============================================================================

        # 1. Set up your required entities (entities your YAML references)
        required_entities = {
            "sensor.global_power": {"state": "500.0", "attributes": {"unit": "W"}},
        }

        # 2. Define your YAML file path and expected sensor count
        yaml_file_path = "tests/fixtures/integration/test_entity_registry_listener_global_vars.yaml"
        expected_sensor_count = 1
        device_identifier = "test_device_global_vars"

        # =============================================================================
        # STANDARD SETUP (DON'T CHANGE UNLESS YOU KNOW WHAT YOU'RE DOING)
        # =============================================================================

        # Save original state for cleanup
        original_entities = dict(mock_entity_registry._entities)
        original_states = dict(mock_states)

        try:
            # Register required entities
            for entity_id, data in required_entities.items():
                mock_entity_registry.register_entity(entity_id, entity_id, "sensor")
                mock_states.register_state(entity_id, data["state"], data["attributes"])

            # Set up storage manager with standard pattern
            with (
                patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
                patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
            ):
                # Standard mock setup
                mock_store = AsyncMock()
                mock_store.async_load.return_value = None
                MockStore.return_value = mock_store
                MockDeviceRegistry.return_value = mock_device_registry

                # Create storage manager with entity listener enabled
                storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=True)
                storage_manager._store = mock_store
                await storage_manager.async_load()

                # Create sensor set
                sensor_set_id = "test_sensor_set"
                await storage_manager.async_create_sensor_set(
                    sensor_set_id=sensor_set_id, device_identifier=device_identifier, name="Test Sensor Set"
                )

                # Load YAML configuration
                with open(yaml_file_path) as f:
                    yaml_content = f.read()

                result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

                # BULLETPROOF ASSERTION 1: YAML import must succeed with exact count
                assert result["sensors_imported"] == expected_sensor_count, (
                    f"YAML import failed: expected {expected_sensor_count} sensors, "
                    f"got {result['sensors_imported']}. Result: {result}"
                )

                # Set up synthetic sensors
                sensor_manager = await async_setup_synthetic_sensors(
                    hass=mock_hass,
                    config_entry=mock_config_entry,
                    async_add_entities=mock_async_add_entities,
                    storage_manager=storage_manager,
                )

                # Get the sensor set to check entity tracking
                sensor_set = storage_manager.get_sensor_set(sensor_set_id)
                assert sensor_set is not None, "Sensor set not found"

                # Verify original entity is tracked
                assert sensor_set.is_entity_tracked("sensor.global_power"), "Original global power entity not tracked"

                # =============================================================================
                # TEST GLOBAL VARIABLE ENTITY ID CHANGE
                # =============================================================================

                # Register the new entity that we'll change to
                new_entity_id = "sensor.global_power_new"
                mock_entity_registry.register_entity(new_entity_id, new_entity_id, "sensor")
                mock_states.register_state(new_entity_id, "600.0", {"unit": "W"})

                # Get the entity registry listener from storage manager (private attribute)
                entity_listener = storage_manager._entity_registry_listener
                assert entity_listener is not None, "Entity listener should be enabled"

                # Process the entity ID change
                await entity_listener._async_process_entity_id_change("sensor.global_power", new_entity_id)

                # =============================================================================
                # VERIFY GLOBAL VARIABLES WERE UPDATED
                # =============================================================================

                # Get the reloaded sensor set (the reload mechanism creates new instances)
                reloaded_sensor_set = storage_manager.get_sensor_set(sensor_set_id)
                assert reloaded_sensor_set is not None, "Reloaded sensor set not found"

                # Verify the new entity is now tracked instead of the old one
                # The reload mechanism should have rebuilt the entity index with updated entity IDs
                assert not reloaded_sensor_set.is_entity_tracked("sensor.global_power"), (
                    "Old global power entity should not be tracked after reload"
                )
                assert reloaded_sensor_set.is_entity_tracked(new_entity_id), (
                    "New global power entity should be tracked after reload"
                )

                # Verify storage was saved
                mock_store.async_save.assert_called()

        finally:
            # =============================================================================
            # CLEANUP (ALWAYS RUNS)
            # =============================================================================

            # Restore original state
            mock_entity_registry._entities.clear()
            mock_entity_registry._entities.update(original_entities)
            mock_states.clear()
            mock_states.update(original_states)
