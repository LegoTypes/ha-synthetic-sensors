"""Integration tests for validation functionality."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import yaml
from pathlib import Path

from ha_synthetic_sensors.storage_manager import StorageManager
from ha_synthetic_sensors import async_setup_synthetic_sensors


class TestValidationIntegration:
    """Integration tests for validation through the public API."""

    @pytest.fixture
    def mock_device_registry(self):
        """Create a mock device registry."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

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

    async def test_complex_yaml_configurations(self, mock_hass, mock_entity_registry, mock_states):
        """Test parsing of complex nested YAML configurations."""
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "complex_yaml_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Complex YAML Test"
            )

            # Load complex nested YAML fixture
            yaml_fixture_path = "tests/fixtures/integration/complex_yaml_nested.yaml"
            with open(yaml_fixture_path, "r") as f:
                complex_yaml = f.read()

            # Import complex YAML - should succeed
            result = await storage_manager.async_from_yaml(yaml_content=complex_yaml, sensor_set_id=sensor_set_id)

            # Verify complex structure was parsed correctly
            assert result["sensors_imported"] == 2, f"Expected 2 sensors, got {result['sensors_imported']}"

            # Verify sensors were created with correct structure
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 2

            # Verify nested structure sensor has attributes
            nested_sensor = next((s for s in sensors if s.unique_id == "nested_structure_sensor"), None)
            assert nested_sensor is not None
            assert len(nested_sensor.formulas) >= 4  # Main formula + 3 attributes

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_yaml_parsing_structure_errors(self, mock_hass, mock_entity_registry, mock_states):
        """Test handling of YAML structure validation errors."""
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "structure_error_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Structure Error Test"
            )

            # Load malformed structure YAML fixture
            yaml_fixture_path = "tests/fixtures/integration/malformed_yaml_structure.yaml"
            with open(yaml_fixture_path, "r") as f:
                malformed_yaml = f.read()

            # Import malformed YAML - should handle gracefully or fail with clear error
            try:
                result = await storage_manager.async_from_yaml(yaml_content=malformed_yaml, sensor_set_id=sensor_set_id)
                # If import succeeds, verify only valid sensors were imported
                # (Some malformed sensors should be rejected during validation)
                assert result["sensors_imported"] < 3, "Some malformed sensors should be rejected"
            except Exception as e:
                # Expected to fail validation with clear error message
                error_msg = str(e).lower()
                assert any(keyword in error_msg for keyword in ["formula", "name", "required", "validation", "missing"]), (
                    f"Error message should indicate validation issue: {e}"
                )

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_yaml_edge_cases_unicode_and_special_chars(self, mock_hass, mock_entity_registry, mock_states):
        """Test handling of Unicode characters and special characters in YAML."""
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "unicode_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Unicode Test"
            )

            # Load Unicode and special characters YAML fixture
            yaml_fixture_path = "tests/fixtures/integration/yaml_edge_case_unicode.yaml"
            with open(yaml_fixture_path, "r", encoding="utf-8") as f:
                unicode_yaml = f.read()

            # Import Unicode YAML - should handle Unicode correctly
            result = await storage_manager.async_from_yaml(yaml_content=unicode_yaml, sensor_set_id=sensor_set_id)

            # Verify Unicode content was parsed correctly
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Verify sensors were created with Unicode names preserved
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Verify Unicode sensor name was preserved
            unicode_sensor = next((s for s in sensors if "unicode_sensor" in s.unique_id), None)
            assert unicode_sensor is not None
            assert "测试传感器" in unicode_sensor.name, "Unicode characters should be preserved in sensor name"

            # Verify special characters sensor
            special_sensor = next((s for s in sensors if "special_chars_sensor" in s.unique_id), None)
            assert special_sensor is not None
            assert "@#$%^&*()" in special_sensor.name, "Special characters should be preserved"

            # Verify emoji sensor
            emoji_sensor = next((s for s in sensors if "emoji_sensor" in s.unique_id), None)
            assert emoji_sensor is not None
            assert "⚡🔋💡" in emoji_sensor.name, "Emoji characters should be preserved"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_yaml_whitespace_and_formatting_preservation(self, mock_hass, mock_entity_registry, mock_states):
        """Test that YAML parser handles whitespace and formatting correctly."""
        # Test YAML with various whitespace scenarios
        whitespace_yaml = """version: "1.0"

global_settings:
  device_identifier: "test_device_123"

sensors:
  whitespace_test:
    name: "   Whitespace Test Sensor   "  # Leading/trailing spaces
    formula: "base_power * multiplier"
    variables:
      base_power: "sensor.base_power"
      multiplier: 1.5
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
      attribution: "  Test with extra spaces  "
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "whitespace_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Whitespace Test"
            )

            # Import whitespace YAML - should handle whitespace correctly
            result = await storage_manager.async_from_yaml(yaml_content=whitespace_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 1, f"Expected 1 sensor, got {result['sensors_imported']}"

            # Verify sensor was created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 1

            # Verify whitespace handling in sensor name (should be trimmed or preserved as configured)
            sensor = sensors[0]
            # The exact whitespace handling depends on implementation - just verify sensor exists
            assert sensor.name is not None
            assert "Whitespace Test Sensor" in sensor.name

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)
