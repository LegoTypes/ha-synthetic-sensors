"""Integration tests for collection resolver functionality."""

import pytest
from unittest.mock import AsyncMock, patch
import yaml

from ha_synthetic_sensors.storage_manager import StorageManager


class TestCollectionResolverIntegration:
    """Integration tests for collection resolution through the public API."""

    async def test_collection_resolver_device_class_patterns(self, mock_hass, mock_entity_registry, mock_states):
        """Test collection resolution with device class patterns."""

        device_class_yaml = """
version: "1.0"

sensors:
  power_sum:
    name: "Power Sum"
    formula: "sum('device_class:power')"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"

  temperature_count:
    name: "Temperature Count"
    formula: "count('device_class:temperature')"
    metadata:
      unit_of_measurement: "sensors"

  mixed_collection:
    name: "Mixed Collection"
    formula: "sum('device_class:power') + avg('device_class:temperature')"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "device_class_collection_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import YAML - this should resolve collection patterns
            result = await storage_manager.async_from_yaml(yaml_content=device_class_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_collection_resolver_area_patterns(self, mock_hass, mock_entity_registry, mock_states):
        """Test collection resolution with area patterns."""

        area_yaml = """
version: "1.0"

sensors:
  living_room_power:
    name: "Living Room Power"
    formula: "sum('area:living_room')"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"

  kitchen_devices:
    name: "Kitchen Devices"
    formula: "count('area:kitchen')"
    metadata:
      unit_of_measurement: "devices"

  bedroom_temperature:
    name: "Bedroom Temperature"
    formula: "avg('area:bedroom')"
    metadata:
      unit_of_measurement: "°C"
      device_class: "temperature"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "area_collection_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import YAML - this should resolve area patterns
            result = await storage_manager.async_from_yaml(yaml_content=area_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_collection_resolver_state_patterns(self, mock_hass, mock_entity_registry, mock_states):
        """Test collection resolution with state patterns."""

        state_yaml = """
version: "1.0"

sensors:
  active_devices:
    name: "Active Devices"
    formula: "count('state:on')"
    metadata:
      unit_of_measurement: "devices"

  high_value_sensors:
    name: "High Value Sensors"
    formula: "count('state:>50')"
    metadata:
      unit_of_measurement: "sensors"

  mixed_state_patterns:
    name: "Mixed State Patterns"
    formula: "count('state:on|active|connected')"
    metadata:
      unit_of_measurement: "devices"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "state_collection_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import YAML - this should resolve state patterns
            result = await storage_manager.async_from_yaml(yaml_content=state_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_collection_resolver_attribute_patterns(self, mock_hass, mock_entity_registry, mock_states):
        """Test collection resolution with attribute patterns."""

        attribute_yaml = """
version: "1.0"

sensors:
  low_battery_devices:
    name: "Low Battery Devices"
    formula: "count('battery_level<20')"
    metadata:
      unit_of_measurement: "devices"

  high_battery_devices:
    name: "High Battery Devices"
    formula: "count('battery_level>80')"
    metadata:
      unit_of_measurement: "devices"

  online_devices:
    name: "Online Devices"
    formula: "count('online:true')"
    metadata:
      unit_of_measurement: "devices"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "attribute_collection_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import YAML - this should resolve attribute patterns
            result = await storage_manager.async_from_yaml(yaml_content=attribute_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_collection_resolver_complex_patterns(self, mock_hass, mock_entity_registry, mock_states):
        """Test collection resolution with complex combined patterns."""

        complex_yaml = """
version: "1.0"

sensors:
  complex_collection:
    name: "Complex Collection"
    formula: "sum('device_class:power|area:living_room') + count('state:on|device_class:switch')"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"

  multi_pattern:
    name: "Multi Pattern"
    formula: "avg('device_class:temperature|area:bedroom|state:>20')"
    metadata:
      unit_of_measurement: "°C"
      device_class: "temperature"

  exclusion_pattern:
    name: "Exclusion Pattern"
    formula: "count('device_class:!diagnostic|area:!basement')"
    metadata:
      unit_of_measurement: "devices"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "complex_collection_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import YAML - this should resolve complex patterns
            result = await storage_manager.async_from_yaml(yaml_content=complex_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)
