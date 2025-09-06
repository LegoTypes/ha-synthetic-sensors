"""Integration test for comprehensive entity index functionality.

This test follows the new template pattern from integration_test_guide.md.
"""

from unittest.mock import AsyncMock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


class TestEntityIndexComprehensive:
    """Integration tests for entity index functionality."""

    @pytest.mark.asyncio
    async def test_entity_index_tracks_entities_correctly(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_device_registry,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test that entity index correctly tracks entities from sensor configurations."""

        # =============================================================================
        # CUSTOMIZE THIS SECTION FOR YOUR TEST
        # =============================================================================

        # 1. Set up your required entities (entities your YAML references)
        required_entities = {
            "sensor.power_meter": {"state": "1000.0", "attributes": {"unit": "W"}},
            "sensor.voltage_meter": {"state": "240.0", "attributes": {"unit": "V"}},
        }

        # 2. Define your YAML file path and expected sensor count
        yaml_file_path = "tests/fixtures/integration/test_entity_index_comprehensive.yaml"
        expected_sensor_count = 2
        device_identifier = "test_device_entity_index"

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

                # Create storage manager
                storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
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
                # ENTITY INDEX SPECIFIC TESTS
                # =============================================================================

                # Test that entity index tracks the entities correctly
                sensor_set = storage_manager.get_sensor_set(sensor_set_id)
                assert sensor_set is not None, "Sensor set not found"

                # Test that the entity index tracks the required entities
                assert sensor_set.is_entity_tracked("sensor.power_meter"), "Power meter entity not tracked"
                assert sensor_set.is_entity_tracked("sensor.voltage_meter"), "Voltage meter entity not tracked"

                # Test entity index statistics
                entity_stats = sensor_set.get_entity_index_stats()
                assert entity_stats is not None, "Entity index stats should not be None"
                assert "total_entities" in entity_stats, "Entity stats should include total_entities"
                assert entity_stats["total_entities"] >= 2, (
                    f"Expected at least 2 entities tracked, got {entity_stats['total_entities']}"
                )

                # Test specific sensor values
                power_sensor = entity_lookup.get("power_analysis")
                assert power_sensor is not None, (
                    f"Sensor 'power_analysis' not found. Available sensors: {list(entity_lookup.keys())}"
                )

                # Test sensor has valid value
                assert power_sensor.native_value is not None, "Sensor 'power_analysis' has None value"
                assert str(power_sensor.native_value) not in ["unknown", "unavailable", ""], (
                    f"Sensor 'power_analysis' has invalid value: {power_sensor.native_value}"
                )

                # Test expected calculation: 1000.0 * 1.1 = 1100.0
                expected_value = 1100.0
                actual_value = float(power_sensor.native_value)
                assert abs(actual_value - expected_value) < 0.001, (
                    f"Sensor 'power_analysis' value wrong: expected {expected_value}, got {actual_value}"
                )

                # Test voltage sensor
                voltage_sensor = entity_lookup.get("voltage_analysis")
                assert voltage_sensor is not None, (
                    f"Sensor 'voltage_analysis' not found. Available sensors: {list(entity_lookup.keys())}"
                )

                # Test expected calculation: 240.0 * 0.95 = 228.0
                expected_voltage = 228.0
                actual_voltage = float(voltage_sensor.native_value)
                assert abs(actual_voltage - expected_voltage) < 0.001, (
                    f"Sensor 'voltage_analysis' value wrong: expected {expected_voltage}, got {actual_voltage}"
                )

                # Clean up
                await storage_manager.async_delete_sensor_set(sensor_set_id)

        finally:
            # Restore original state
            mock_entity_registry._entities.clear()
            mock_entity_registry._entities.update(original_entities)
            mock_states.clear()
            mock_states.update(original_states)
