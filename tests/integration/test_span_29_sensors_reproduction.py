"""Integration Test to Reproduce SPAN 29-Sensor Loading Issue.

This test reproduces the issue where only 6 out of 29 SPAN sensors
are being stored during YAML processing, using the established
integration test patterns and public API.
"""

from unittest.mock import AsyncMock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


class TestSpan29SensorsReproduction:
    """Integration tests to reproduce SPAN 29-sensor storage issue."""

    @pytest.mark.asyncio
    async def test_span_29_sensors_storage_issue(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_device_registry,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test reproduction of SPAN 29-sensor storage issue."""

        # =============================================================================
        # SPAN TEST CONFIGURATION
        # =============================================================================

        # 1. Set up all SPAN backing entities (what the 'state' token resolves to)
        span_backing_entities = {
            # Main panel sensors (these work - get stored)
            "sensor.span_simulator_current_power": {"state": "1500.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_feed_through_power": {"state": "800.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_main_meter_produced_energy": {"state": "1250.5", "attributes": {"unit": "Wh"}},
            "sensor.span_simulator_main_meter_consumed_energy": {"state": "2450.8", "attributes": {"unit": "Wh"}},
            "sensor.span_simulator_feed_through_produced_energy": {"state": "950.2", "attributes": {"unit": "Wh"}},
            "sensor.span_simulator_feed_through_consumed_energy": {"state": "1850.4", "attributes": {"unit": "Wh"}},
            # Circuit sensors (these fail - don't get stored)
            "sensor.span_simulator_circuit_1_power": {"state": "120.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_2_power": {"state": "85.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_3_power": {"state": "95.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_4_power": {"state": "65.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_5_power": {"state": "45.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_6_power": {"state": "75.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_7_power": {"state": "110.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_8_power": {"state": "90.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_9_power": {"state": "55.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_12_power": {"state": "100.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_11_power": {"state": "80.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_12_power_2": {"state": "70.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_13_power": {"state": "60.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_14_power": {"state": "50.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_15_power": {"state": "200.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_16_power": {"state": "0.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_17_power": {"state": "0.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_18_20_power": {"state": "0.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_19_21_power": {"state": "0.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_22_power": {"state": "150.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_23_25_power": {"state": "2200.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_24_26_power": {"state": "0.0", "attributes": {"unit": "W"}},
            "sensor.span_simulator_circuit_27_29_power": {"state": "0.0", "attributes": {"unit": "W"}},
        }

        # 2. SPAN test configuration
        yaml_file_path = "tests/fixtures/integration/span_29_sensors_reproduction.yaml"
        expected_sensor_count = 29  # All 29 SPAN sensors
        device_identifier = "span-sim-001"  # Must match YAML global_settings

        # =============================================================================
        # STANDARD SETUP (DON'T CHANGE UNLESS YOU KNOW WHAT YOU'RE DOING)
        # =============================================================================

        # Save original state for cleanup
        original_entities = dict(mock_entity_registry._entities)
        original_states = dict(mock_states)

        try:
            # Set up virtual backing entities (NOT registered in HA)
            # These provide data via data_provider_callback, not HA registry

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

                # Set up virtual backing entities data provider
                def create_data_provider_callback(backing_data: dict[str, any]):
                    def data_provider(entity_id: str):
                        return {"value": backing_data.get(entity_id, {}).get("state"), "exists": entity_id in backing_data}

                    return data_provider

                data_provider = create_data_provider_callback(span_backing_entities)

                # Create sensor-to-backing mapping for 'state' token resolution
                sensor_to_backing_mapping = {
                    "span_span-sim-001_current_power": "sensor.span_simulator_current_power",
                    "span_span-sim-001_feed_through_power": "sensor.span_simulator_feed_through_power",
                    "span_span-sim-001_main_meter_produced_energy": "sensor.span_simulator_main_meter_produced_energy",
                    "span_span-sim-001_main_meter_consumed_energy": "sensor.span_simulator_main_meter_consumed_energy",
                    "span_span-sim-001_feed_through_produced_energy": "sensor.span_simulator_feed_through_produced_energy",
                    "span_span-sim-001_feed_through_consumed_energy": "sensor.span_simulator_feed_through_consumed_energy",
                    "span_span-sim-001_master_bedroom_lights_power": "sensor.span_simulator_circuit_1_power",
                    "span_span-sim-001_living_room_lights_power": "sensor.span_simulator_circuit_2_power",
                    "span_span-sim-001_kitchen_lights_power": "sensor.span_simulator_circuit_3_power",
                    "span_span-sim-001_bedroom_lights_power": "sensor.span_simulator_circuit_4_power",
                    "span_span-sim-001_bathroom_lights_power": "sensor.span_simulator_circuit_5_power",
                    "span_span-sim-001_exterior_lights_power": "sensor.span_simulator_circuit_6_power",
                    "span_span-sim-001_master_bedroom_outlets_power": "sensor.span_simulator_circuit_7_power",
                    "span_span-sim-001_living_room_outlets_power": "sensor.span_simulator_circuit_8_power",
                    "span_span-sim-001_kitchen_outlets_1_power": "sensor.span_simulator_circuit_9_power",
                    "span_span-sim-001_kitchen_outlets_2_power": "sensor.span_simulator_circuit_12_power",
                    "span_span-sim-001_office_outlets_power": "sensor.span_simulator_circuit_11_power",
                    "span_span-sim-001_garage_outlets_power": "sensor.span_simulator_circuit_12_power_2",
                    "span_span-sim-001_laundry_outlets_power": "sensor.span_simulator_circuit_13_power",
                    "span_span-sim-001_guest_room_outlets_power": "sensor.span_simulator_circuit_14_power",
                    "span_span-sim-001_refrigerator_power": "sensor.span_simulator_circuit_15_power",
                    "span_span-sim-001_dishwasher_power": "sensor.span_simulator_circuit_16_power",
                    "span_span-sim-001_washing_machine_power": "sensor.span_simulator_circuit_17_power",
                    "span_span-sim-001_dryer_power": "sensor.span_simulator_circuit_18_20_power",
                    "span_span-sim-001_oven_power": "sensor.span_simulator_circuit_19_21_power",
                    "span_span-sim-001_microwave_power": "sensor.span_simulator_circuit_22_power",
                    "span_span-sim-001_main_hvac_power": "sensor.span_simulator_circuit_23_25_power",
                    "span_span-sim-001_heat_pump_backup_power": "sensor.span_simulator_circuit_24_26_power",
                    "span_span-sim-001_ev_charger_garage_power": "sensor.span_simulator_circuit_27_29_power",
                }

                # Create change notifier callback
                def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                    pass  # For this test, we don't need change notification logic

                # Set up synthetic sensors with virtual backing entities
                sensor_manager = await async_setup_synthetic_sensors(
                    hass=mock_hass,
                    config_entry=mock_config_entry,
                    async_add_entities=mock_async_add_entities,
                    storage_manager=storage_manager,
                    device_identifier=device_identifier,
                    data_provider_callback=data_provider,
                    change_notifier=change_notifier_callback,
                    sensor_to_backing_mapping=sensor_to_backing_mapping,
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
                # SPAN 29-SENSOR REPRODUCTION TESTS
                # =============================================================================

                # CRITICAL TEST: Check if we reproduced the storage issue
                stored_sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)

                print(f"\n🔍 REPRODUCTION TEST RESULTS:")
                print(f"  • YAML imported: {result['sensors_imported']} sensors")
                print(f"  • HA entities created: {len(all_entities)} entities")
                print(f"  • Storage contains: {len(stored_sensors)} sensors")

                if len(stored_sensors) != expected_sensor_count:
                    print(f"  🚨 REPRODUCTION SUCCESS: Only {len(stored_sensors)}/29 sensors stored!")
                    print(f"  📋 Stored sensors:")
                    for sensor in stored_sensors:
                        print(f"    - {sensor.unique_id}")
                else:
                    print(f"  ✅ All 29 sensors stored correctly")

                # Verify main panel sensors (the 6 that usually work)
                main_panel_sensor_ids = [
                    "span_span-sim-001_current_power",
                    "span_span-sim-001_feed_through_power",
                    "span_span-sim-001_main_meter_produced_energy",
                    "span_span-sim-001_main_meter_consumed_energy",
                    "span_span-sim-001_feed_through_produced_energy",
                    "span_span-sim-001_feed_through_consumed_energy",
                ]

                # Verify circuit sensors (the 23 that usually fail)
                circuit_sensor_ids = [
                    "span_span-sim-001_master_bedroom_lights_power",
                    "span_span-sim-001_living_room_lights_power",
                    "span_span-sim-001_kitchen_lights_power",
                    "span_span-sim-001_bedroom_lights_power",
                    "span_span-sim-001_bathroom_lights_power",
                    # Add a few more key ones to test
                    "span_span-sim-001_refrigerator_power",
                    "span_span-sim-001_main_hvac_power",
                ]

                # BULLETPROOF ASSERTION 5: Main panel sensors must exist
                for sensor_id in main_panel_sensor_ids:
                    sensor = entity_lookup.get(sensor_id)
                    assert sensor is not None, (
                        f"Main panel sensor '{sensor_id}' not found. Available: {list(entity_lookup.keys())}"
                    )

                # BULLETPROOF ASSERTION 6: Circuit sensors must exist
                for sensor_id in circuit_sensor_ids:
                    sensor = entity_lookup.get(sensor_id)
                    assert sensor is not None, (
                        f"Circuit sensor '{sensor_id}' not found. Available: {list(entity_lookup.keys())}"
                    )

                # Test a few sensor values to ensure formulas work
                current_power_sensor = entity_lookup.get("span_span-sim-001_current_power")
                assert current_power_sensor is not None and current_power_sensor.native_value == 1500.0, (
                    f"Current power sensor failed: {current_power_sensor}, "
                    f"value={getattr(current_power_sensor, 'native_value', 'N/A')}"
                )

                circuit_sensor = entity_lookup.get("span_span-sim-001_master_bedroom_lights_power")
                assert circuit_sensor is not None and circuit_sensor.native_value == 120.0, (
                    f"Circuit sensor failed: {circuit_sensor}, value={getattr(circuit_sensor, 'native_value', 'N/A')}"
                )

                # Test sensor attributes are properly set
                test_sensor = current_power_sensor
                if hasattr(test_sensor, "extra_state_attributes") and test_sensor.extra_state_attributes:
                    assert test_sensor.extra_state_attributes.get("voltage") == 240, (
                        f"Current power sensor missing voltage attribute: {test_sensor.extra_state_attributes}"
                    )

                # Test all sensors have valid values (bulletproof check)
                for entity in all_entities:
                    unique_id = getattr(entity, "unique_id", "unknown")
                    value = getattr(entity, "native_value", None)

                    # Every sensor must have a valid value
                    assert value is not None, f"Sensor '{unique_id}' has None value"
                    assert str(value) not in ["unknown", "unavailable", ""], f"Sensor '{unique_id}' has invalid value: {value}"

                    # Every sensor must have basic attributes
                    assert hasattr(entity, "name"), f"Sensor '{unique_id}' missing name attribute"
                    assert hasattr(entity, "unique_id"), f"Sensor '{unique_id}' missing unique_id attribute"

                # Clean up
                await storage_manager.async_delete_sensor_set(sensor_set_id)

        finally:
            # Restore original state
            mock_entity_registry._entities.clear()
            mock_entity_registry._entities.update(original_entities)
            mock_states.clear()
            mock_states.update(original_states)


# =============================================================================
# HELPER METHODS (COPY AS NEEDED)
# =============================================================================


def assert_sensor_exists_and_has_value(entity_lookup, sensor_id, expected_value=None):
    """Bulletproof assertion helper for sensor existence and value."""
    sensor = entity_lookup.get(sensor_id)
    assert sensor is not None, f"Sensor '{sensor_id}' not found. Available: {list(entity_lookup.keys())}"

    assert sensor.native_value is not None, f"Sensor '{sensor_id}' has None value"
    assert str(sensor.native_value) not in ["unknown", "unavailable", ""], (
        f"Sensor '{sensor_id}' has invalid value: {sensor.native_value}"
    )

    if expected_value is not None:
        actual = float(sensor.native_value)
        assert abs(actual - expected_value) < 0.001, (
            f"Sensor '{sensor_id}' wrong value: expected {expected_value}, got {actual}"
        )

    return sensor


def assert_sensor_attribute(sensor, attr_name, expected_value):
    """Bulletproof assertion helper for sensor attributes."""
    assert hasattr(sensor, "extra_state_attributes"), f"Sensor '{sensor.unique_id}' has no extra_state_attributes"

    attrs = sensor.extra_state_attributes or {}
    actual_value = attrs.get(attr_name)

    assert actual_value == expected_value, (
        f"Sensor '{sensor.unique_id}' attribute '{attr_name}': expected {expected_value}, got {actual_value}"
    )


# =============================================================================
# CHECKLIST FOR CREATING YOUR TEST:
# =============================================================================
"""
1. [ ] Copy this file to test_your_feature_integration.py
2. [ ] Replace class name TestYourFeature with TestYourActualFeature
3. [ ] Replace method name test_your_feature_name with test_your_actual_feature
4. [ ] Create your YAML fixture file and put it in tests/yaml_fixtures/
5. [ ] Update required_entities with entities your YAML references
6. [ ] Update yaml_file_path with your actual YAML file
7. [ ] Update expected_sensor_count with the number of sensors in your YAML
8. [ ] Update device_identifier to match your YAML global_settings.device_identifier
9. [ ] Replace "your_sensor_unique_id" with actual sensor IDs from your YAML
10. [ ] Calculate expected_value based on your formula and test data
11. [ ] Add any specific attribute assertions you need
12. [ ] Run the test and fix any issues

BULLETPROOF ASSERTION PRINCIPLES:
- Never just check if something exists without checking its value
- Always provide detailed error messages showing what you got vs expected
- Test exact values, not just "not None"
- Test all sensors, not just one
- Always clean up in finally block
- Fail fast with specific error messages
"""
