"""Integration tests for string operations."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from ha_synthetic_sensors.storage_manager import StorageManager


class TestStringOperationsIntegration:
    """Integration tests for string operations through the public API."""

    async def test_basic_string_concatenation(self, mock_hass, mock_entity_registry, mock_states):
        """Test basic string concatenation operations."""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "string_operations_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Load string operations YAML fixture
            yaml_fixture_path = "tests/fixtures/integration/string_operations_basic.yaml"
            with open(yaml_fixture_path, "r") as f:
                string_yaml = f.read()

            # Import string operations YAML - should succeed
            result = await storage_manager.async_from_yaml(yaml_content=string_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Verify sensors were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Verify string concatenation sensor
            string_sensor = next((s for s in sensors if "string_concatenation" in s.unique_id), None)
            assert string_sensor is not None
            assert string_sensor.name == "String Concatenation Test"

            # Verify mixed string variable sensor
            mixed_sensor = next((s for s in sensors if "mixed_string_variable" in s.unique_id), None)
            assert mixed_sensor is not None
            assert mixed_sensor.name == "Mixed String Variable Test"

            # Verify numeric default sensor (should still work)
            numeric_sensor = next((s for s in sensors if "numeric_default" in s.unique_id), None)
            assert numeric_sensor is not None
            assert numeric_sensor.name == "Numeric Default Test"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_string_operations_with_existing_validation(self, mock_hass, mock_entity_registry, mock_states):
        """Test that string operations work with existing validation system."""

        # Test YAML with string operations that should pass validation
        valid_string_yaml = """
version: "1.0"

global_settings:
  device_identifier: "string_validation_device"

sensors:
  valid_string_sensor:
    name: "Valid String Operations"
    formula: "'Power: ' + state + 'W'"
    variables:
      state: "sensor.power_meter"
    metadata:
      unit_of_measurement: ""
      device_class: "enum"
      state_class: "measurement"

  valid_numeric_sensor:
    name: "Valid Numeric Operations"
    formula: "state * 1.1"
    variables:
      state: "sensor.power_meter"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "string_validation_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import string operations YAML - should pass validation
            result = await storage_manager.async_from_yaml(yaml_content=valid_string_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 2, f"Expected 2 sensors, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_formula_router_integration(self, mock_hass, mock_entity_registry, mock_states):
        """Test that the formula router correctly routes different formula types."""

        # Test YAML with different formula types to verify routing
        routing_test_yaml = """
version: "1.0"

global_settings:
  device_identifier: "routing_test_device"

sensors:
  string_literal_sensor:
    name: "String Literal Routing"
    formula: "'Static String Value'"
    metadata:
      unit_of_measurement: ""
      device_class: "enum"

  numeric_formula_sensor:
    name: "Numeric Formula Routing"
    formula: "42 * 2"
    metadata:
      unit_of_measurement: ""
      device_class: "enum"

  collection_function_sensor:
    name: "Collection Function Routing"
    formula: "count('device_class:power')"
    metadata:
      unit_of_measurement: "devices"
      device_class: "enum"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "routing_integration_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import routing test YAML - should succeed and route correctly
            result = await storage_manager.async_from_yaml(yaml_content=routing_test_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Verify all sensors were created (routing worked)
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_backward_compatibility_with_existing_formulas(self, mock_hass, mock_entity_registry, mock_states):
        """Test that existing numeric formulas continue to work unchanged."""

        # Use existing validation test YAML to ensure backward compatibility
        existing_formula_yaml = """
version: "1.0"

global_settings:
  device_identifier: "compatibility_test_device"

sensors:
  existing_power_sensor:
    name: "Existing Power Calculation"
    formula: "sensor.panel_power * 1.1"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  existing_count_sensor:
    name: "Existing Device Count"
    formula: "count('device_class:power')"
    metadata:
      unit_of_measurement: "devices"
      device_class: "enum"

  existing_sum_sensor:
    name: "Existing Power Sum"
    formula: "sum('device_class:power')"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "backward_compatibility_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import existing formula patterns - should continue to work
            result = await storage_manager.async_from_yaml(yaml_content=existing_formula_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded (existing formulas still work)
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)
