"""Integration tests for validation functionality."""

import pytest
from unittest.mock import AsyncMock, patch
import yaml

from ha_synthetic_sensors.storage_manager import StorageManager


class TestValidationIntegration:
    """Integration tests for validation through the public API."""

    async def test_validation_invalid_yaml_structure(self, mock_hass, mock_entity_registry, mock_states):
        """Test validation of invalid YAML structure."""

        invalid_yaml = """
version: "1.0"

sensors:
  invalid_sensor:
    # Missing required fields
    metadata:
      unit_of_measurement: "W"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "validation_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import YAML - this should fail validation
            try:
                result = await storage_manager.async_from_yaml(yaml_content=invalid_yaml, sensor_set_id=sensor_set_id)
                # If we get here, validation should have caught the error
                assert False, "Validation should have failed for invalid YAML"
            except Exception as e:
                # Expected to fail validation
                assert "formula" in str(e).lower() or "required" in str(e).lower() or "validation" in str(e).lower()

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_validation_invalid_formula(self, mock_hass, mock_entity_registry, mock_states):
        """Test validation of invalid formulas."""

        invalid_formula_yaml = """
version: "1.0"

sensors:
  invalid_formula_sensor:
    name: "Invalid Formula Sensor"
    formula: "invalid_function() + * 2"  # Invalid syntax
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

            sensor_set_id = "invalid_formula_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import YAML - this should fail validation
            try:
                result = await storage_manager.async_from_yaml(yaml_content=invalid_formula_yaml, sensor_set_id=sensor_set_id)
                # If we get here, validation should have caught the error
                assert False, "Validation should have failed for invalid formula"
            except Exception as e:
                # Expected to fail validation
                assert "formula" in str(e).lower() or "syntax" in str(e).lower()

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_validation_circular_references(self, mock_hass, mock_entity_registry, mock_states):
        """Test validation of circular references."""

        circular_yaml = """
version: "1.0"

sensors:
  sensor_a:
    name: "Sensor A"
    formula: "sensor_b * 2"  # References sensor_b
    metadata:
      unit_of_measurement: "W"
      device_class: "power"

  sensor_b:
    name: "Sensor B"
    formula: "sensor_a * 3"  # References sensor_a (circular!)
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

            sensor_set_id = "circular_reference_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import YAML - this should fail validation due to circular reference
            try:
                result = await storage_manager.async_from_yaml(yaml_content=circular_yaml, sensor_set_id=sensor_set_id)
                # If we get here, validation should have caught the error
                assert False, "Validation should have failed for circular reference"
            except Exception as e:
                # Expected to fail validation
                assert "circular" in str(e).lower() or "dependency" in str(e).lower()

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_validation_metadata_constraints(self, mock_hass, mock_entity_registry, mock_states):
        """Test validation of metadata constraints."""

        invalid_metadata_yaml = """
version: "1.0"

sensors:
  invalid_metadata_sensor:
    name: "Invalid Metadata Sensor"
    formula: "100"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      # Invalid metadata field
      invalid_field: "invalid_value"
      # Invalid device_class for sensor
      device_class: "invalid_device_class"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "metadata_validation_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import YAML - this should fail validation
            try:
                result = await storage_manager.async_from_yaml(yaml_content=invalid_metadata_yaml, sensor_set_id=sensor_set_id)
                # If we get here, validation should have caught the error
                assert False, "Validation should have failed for invalid metadata"
            except Exception as e:
                # Expected to fail validation
                assert "metadata" in str(e).lower() or "device_class" in str(e).lower()

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_validation_valid_configuration(self, mock_hass, mock_entity_registry, mock_states):
        """Test validation of valid configuration."""

        valid_yaml = """
version: "1.0"

sensors:
  valid_sensor:
    name: "Valid Sensor"
    formula: "sensor.panel_power * 1.1"
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

            sensor_set_id = "valid_config_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import YAML - this should pass validation
            result = await storage_manager.async_from_yaml(yaml_content=valid_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 1, f"Expected 1 sensor, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)
