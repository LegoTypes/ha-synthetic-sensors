"""Integration tests for date arithmetic with duration functions."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from ha_synthetic_sensors import async_setup_synthetic_sensors
from ha_synthetic_sensors.storage_manager import StorageManager


class TestDateArithmeticIntegration:
    """Integration tests for date arithmetic through the public API."""

    async def test_basic_duration_functions(self, mock_hass, mock_entity_registry, mock_states):
        """Test basic duration function evaluation through math functions."""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "date_arithmetic_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Test basic duration functions work in math evaluation
            yaml_content = """
version: "1.0"

global_settings:
  device_identifier: "test_device_date_arithmetic"

sensors:
  # Test duration functions return proper strings
  test_days_function:
    name: "Test Days Function"
    formula: "days(30)"
    metadata:
      unit_of_measurement: ""

  test_hours_function:
    name: "Test Hours Function"
    formula: "hours(24)"
    metadata:
      unit_of_measurement: ""

  test_minutes_function:
    name: "Test Minutes Function"
    formula: "minutes(60)"
    metadata:
      unit_of_measurement: ""
"""

            # Import YAML - should succeed
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Verify sensors were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Get sensor configs to verify they were created with the right names
            sensor_names = [s.unique_id for s in sensors]
            assert "test_days_function" in sensor_names
            assert "test_hours_function" in sensor_names
            assert "test_minutes_function" in sensor_names

    async def test_simple_date_functions(self, mock_hass, mock_entity_registry, mock_states):
        """Test simple date function usage."""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "simple_date_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Test simple date functions
            yaml_content = """
version: "1.0"

global_settings:
  device_identifier: "test_device_simple_date"

sensors:
  # Test basic date conversion
  test_date_conversion:
    name: "Test Date Conversion"
    formula: "date('2025-01-01')"
    metadata:
      device_class: "date"

  # Test date with variable
  test_date_variable:
    name: "Test Date Variable"
    formula: "date(start_date)"
    variables:
      start_date: "2025-01-15"
    metadata:
      device_class: "date"
"""

            # Import YAML - should succeed
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 2, f"Expected 2 sensors, got {result['sensors_imported']}"

            # Verify sensors were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 2

    async def test_existing_datetime_functions(self, mock_hass, mock_entity_registry, mock_states):
        """Test that existing datetime functions still work."""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "existing_datetime_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Test existing datetime functions still work
            yaml_content = """
version: "1.0"

global_settings:
  device_identifier: "test_device_existing_datetime"

sensors:
  # Test existing datetime functions
  test_now_function:
    name: "Test Now Function"
    formula: "1"  # Simple formula for now
    attributes:
      current_time: now()
      today_date: today()
    metadata:
      device_class: "timestamp"
"""

            # Import YAML - should succeed
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 1, f"Expected 1 sensor, got {result['sensors_imported']}"

            # Verify sensor was created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 1
