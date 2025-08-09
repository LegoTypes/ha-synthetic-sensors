"""Integration test for SPAN 29-sensor YAML configuration to reproduce storage issue."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

# Use public API imports as shown in integration guide
from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager


class TestSpan29SensorsIntegration:
    """Integration test to reproduce the SPAN 29-sensor loading issue."""

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback."""
        return Mock()

    @pytest.fixture
    def mock_device_registry(self):
        """Create a mock device registry."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_device_entry = Mock()
        mock_device_entry.name = "SPAN Panel"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "span-sim-001")}
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    async def test_span_29_sensors_yaml_loading(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test SPAN YAML with 29 sensors to reproduce the storage issue."""
        # Set up mock HA states for the SPAN backing entities
        mock_states["sensor.span_simulator_current_power"] = type("MockState", (), {"state": "1500.0", "attributes": {}})()
        mock_states["sensor.span_simulator_feed_through_power"] = type("MockState", (), {"state": "800.0", "attributes": {}})()
        mock_states["sensor.span_simulator_main_meter_produced_energy"] = type(
            "MockState", (), {"state": "1250.5", "attributes": {}}
        )()
        mock_states["sensor.span_simulator_main_meter_consumed_energy"] = type(
            "MockState", (), {"state": "2450.8", "attributes": {}}
        )()
        mock_states["sensor.span_simulator_feed_through_produced_energy"] = type(
            "MockState", (), {"state": "950.2", "attributes": {}}
        )()
        mock_states["sensor.span_simulator_feed_through_consumed_energy"] = type(
            "MockState", (), {"state": "1850.4", "attributes": {}}
        )()

        # Add backing entities for all 23 circuit sensors
        circuit_entities = [
            "sensor.span_simulator_circuit_1_power",
            "sensor.span_simulator_circuit_2_power",
            "sensor.span_simulator_circuit_3_power",
            "sensor.span_simulator_circuit_4_power",
            "sensor.span_simulator_circuit_5_power",
            "sensor.span_simulator_circuit_6_power",
            "sensor.span_simulator_circuit_7_power",
            "sensor.span_simulator_circuit_8_power",
            "sensor.span_simulator_circuit_9_power",
            "sensor.span_simulator_circuit_12_power",
            "sensor.span_simulator_circuit_11_power",
            "sensor.span_simulator_circuit_12_power_2",
            "sensor.span_simulator_circuit_13_power",
            "sensor.span_simulator_circuit_14_power",
            "sensor.span_simulator_circuit_15_power",
            "sensor.span_simulator_circuit_16_power",
            "sensor.span_simulator_circuit_17_power",
            "sensor.span_simulator_circuit_18_20_power",
            "sensor.span_simulator_circuit_19_21_power",
            "sensor.span_simulator_circuit_22_power",
            "sensor.span_simulator_circuit_23_25_power",
            "sensor.span_simulator_circuit_24_26_power",
            "sensor.span_simulator_circuit_27_29_power",
        ]

        for entity_id in circuit_entities:
            mock_states[entity_id] = type("MockState", (), {"state": "150.0", "attributes": {}})()

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_span_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set and load the full SPAN YAML
            sensor_set_id = "span_29_sensor_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="span-sim-001", name="SPAN 29 Sensor Test"
            )

            # Load the full SPAN YAML with 29 sensors
            yaml_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "span_full_29_sensors.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            print(f"\n=== LOADING SPAN YAML WITH 29 SENSORS ===")
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            print(f"async_from_yaml result: {result}")

            # CRITICAL TEST: Check how many sensors were actually stored
            stored_sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            print(f"Stored sensors count: {len(stored_sensors)}")

            if len(stored_sensors) != 29:
                print(f"❌ REPRODUCTION: Only {len(stored_sensors)}/29 sensors stored!")
                print("Stored sensor IDs:")
                for i, sensor in enumerate(stored_sensors):
                    print(f"  {i + 1}. {sensor.unique_id}")
            else:
                print(f"✅ All 29 sensors stored successfully")

            # Now set up sensor manager to test entity creation
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Check how many entities were created
            created_entities = []
            for call_args in mock_async_add_entities.call_args_list:
                entities = call_args[0][0]  # First positional argument is the list of entities
                created_entities.extend(entities)

            print(f"Created entities count: {len(created_entities)}")

            # Test that storage correctly reflects what was loaded
            expected_sensor_count = 29
            assert result["sensors_imported"] == expected_sensor_count, (
                f"Expected {expected_sensor_count} sensors imported, got {result['sensors_imported']}"
            )

            assert len(stored_sensors) == expected_sensor_count, (
                f"Expected {expected_sensor_count} sensors stored, got {len(stored_sensors)}"
            )

            # Verify specific sensors exist
            sensor_ids = [s.unique_id for s in stored_sensors]

            # Check main panel sensors (these are the 6 that usually work)
            main_panel_sensors = [
                "span_span-sim-001_current_power",
                "span_span-sim-001_feed_through_power",
                "span_span-sim-001_main_meter_produced_energy",
                "span_span-sim-001_main_meter_consumed_energy",
                "span_span-sim-001_feed_through_produced_energy",
                "span_span-sim-001_feed_through_consumed_energy",
            ]

            for sensor_id in main_panel_sensors:
                assert sensor_id in sensor_ids, f"Main panel sensor {sensor_id} missing from storage"

            # Check circuit sensors (these are the 23 that usually fail)
            circuit_sensors = [
                "span_span-sim-001_master_bedroom_lights_power",
                "span_span-sim-001_living_room_lights_power",
                "span_span-sim-001_kitchen_lights_power",
                "span_span-sim-001_bedroom_lights_power",
                "span_span-sim-001_bathroom_lights_power",
            ]

            for sensor_id in circuit_sensors:
                assert sensor_id in sensor_ids, f"Circuit sensor {sensor_id} missing from storage"

            # Test sensor evaluation
            await sensor_manager.async_update_sensors()

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)
