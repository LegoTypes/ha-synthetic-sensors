"""Integration test for global CRUD YAML interface following test design guide."""

import pytest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from ha_synthetic_sensors import (
    async_setup_synthetic_sensors,
    StorageManager,
    DataProviderCallback,
)


class TestGlobalsYamlCrudIntegration:
    """Integration tests for the globals YAML CRUD interface."""

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"  # Will be slugified for entity IDs
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        return mock_device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    def create_data_provider_callback(self, backing_data: dict[str, Any]) -> DataProviderCallback:
        """Create data provider for virtual backing entities."""

        def data_provider(entity_id: str):
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    async def test_globals_yaml_crud_full_lifecycle(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_device_registry
    ):
        """Test complete CRUD lifecycle for global settings using YAML interface."""

        # Set up test data - virtual backing entity for sensor state token
        backing_data = {"sensor.test_backing": 1000.0}
        data_provider = self.create_data_provider_callback(backing_data)

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            # Use common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "test_globals_crud"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Test Globals CRUD Sensors"
            )

            # Get the sensor set for YAML CRUD operations
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)
            yaml_crud = sensor_set._globals_yaml_crud

            # Test 1: Create global settings from YAML fixture
            initial_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "globals_yaml_crud_initial.yaml"
            with open(initial_fixture_path, "r") as f:
                initial_yaml = f.read()

            # Import the complete YAML (includes sensors)
            result = await storage_manager.async_from_yaml(yaml_content=initial_yaml, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1

            # Verify creation by reading back
            created_globals = sensor_set.get_global_settings_handler().read_global_settings()
            assert created_globals["device_identifier"] == "test_device_123"
            assert created_globals["device_name"] == "Test Smart Device"
            assert created_globals["variables"]["multiplier"] == 1.5
            assert created_globals["metadata"]["location"] == "Kitchen"
            assert created_globals["metadata"]["manufacturer"] == "Test Corp"

            # Test 2: Update global settings (partial update)
            update_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "globals_yaml_crud_update.yaml"
            with open(update_fixture_path, "r") as f:
                update_yaml = f.read()

            await yaml_crud.async_update_global_settings_from_yaml(update_yaml)

            # Verify update (should merge with existing)
            updated_globals = sensor_set.get_global_settings_handler().read_global_settings()
            assert updated_globals["device_identifier"] == "test_device_123"  # Unchanged
            assert updated_globals["device_name"] == "Updated Smart Device"  # Updated

            # The current implementation replaces entire sections (variables, metadata)
            # This is expected behavior for this CRUD interface - it does section-level replacement
            # But we keep the multiplier variable with an updated value to show global changes affecting sensors
            assert updated_globals["variables"]["multiplier"] == 2.0  # Updated from 1.5 to 2.0
            assert updated_globals["variables"]["new_variable"] == 42  # New variables
            assert updated_globals["variables"]["efficiency"] == 0.85  # New variables
            assert updated_globals["metadata"]["location"] == "Living Room"  # Metadata section replaced
            assert "manufacturer" not in updated_globals.get("metadata", {})  # Previous metadata replaced
            assert updated_globals["metadata"]["installation_date"] == "2024-01-15"  # New metadata
            assert updated_globals["metadata"]["notes"] == "Updated via YAML CRUD"  # New metadata

            # Test 3: Variable-specific YAML operations
            variables_fixture_path = (
                Path(__file__).parent.parent / "fixtures" / "integration" / "globals_yaml_crud_variables.yaml"
            )
            with open(variables_fixture_path, "r") as f:
                variables_yaml = f.read()

            await yaml_crud.async_add_variable_from_yaml(variables_yaml)

            # Verify variables were added (this adds to existing variables from the update)
            variables = sensor_set.get_global_settings_handler().list_global_variables()
            assert variables["multiplier"] == 3.0  # Updated again from 2.0 to 3.0
            assert variables["power_multiplier"] == 2.5
            assert variables["efficiency_factor"] == 0.85
            assert variables["base_rate"] == 0.12
            # Previous variables from the update step are still there because add_variable preserves existing
            assert variables["new_variable"] == 42  # From previous update - preserved
            assert variables["efficiency"] == 0.85  # From previous update - preserved

            # Test 4: Read variables as YAML and verify format
            variables_yaml_output = yaml_crud.read_variables_as_yaml()
            assert "multiplier: 3.0" in variables_yaml_output  # Current multiplier value
            assert "power_multiplier: 2.5" in variables_yaml_output
            assert "efficiency_factor: 0.85" in variables_yaml_output
            assert "base_rate: 0.12" in variables_yaml_output
            # Previous variables are still there because add_variable preserves existing
            assert "new_variable: 42" in variables_yaml_output
            assert "efficiency: 0.85" in variables_yaml_output

            # Test 5: Device info YAML operations
            device_info_fixture_path = (
                Path(__file__).parent.parent / "fixtures" / "integration" / "globals_yaml_crud_device_info.yaml"
            )
            with open(device_info_fixture_path, "r") as f:
                device_info_yaml = f.read()

            await yaml_crud.async_update_device_info_from_yaml(device_info_yaml)

            # Verify device info
            device_info = sensor_set.get_global_settings_handler().get_device_info()
            assert device_info["device_identifier"] == "test_device_123"
            assert device_info["device_name"] == "Super Smart Device"
            assert device_info["device_manufacturer"] == "Acme Corp"
            assert device_info["device_model"] == "Smart-2000"
            assert device_info["device_sw_version"] == "v1.2.3"

            # Test 6: Read device info as YAML and verify format
            device_yaml_output = yaml_crud.read_device_info_as_yaml()
            assert "device_name: Super Smart Device" in device_yaml_output
            assert "device_manufacturer: Acme Corp" in device_yaml_output

            # Test 7: Metadata YAML operations
            metadata_fixture_path = (
                Path(__file__).parent.parent / "fixtures" / "integration" / "globals_yaml_crud_metadata.yaml"
            )
            with open(metadata_fixture_path, "r") as f:
                metadata_yaml = f.read()

            await yaml_crud.async_update_metadata_from_yaml(metadata_yaml)

            # Verify metadata
            metadata = sensor_set.get_global_settings_handler().get_global_metadata()
            assert metadata["location"] == "Garage"
            assert metadata["installation_date"] == "2024-02-01"
            assert metadata["notes"] == "Updated installation"
            assert metadata["version"] == "2.0"

            # Test 8: Read metadata as YAML and verify format
            metadata_yaml_output = yaml_crud.read_metadata_as_yaml()
            assert "location: Garage" in metadata_yaml_output
            assert "notes: Updated installation" in metadata_yaml_output

            # Test 9: Read complete global settings as YAML
            complete_yaml_output = yaml_crud.read_global_settings_as_yaml()
            assert "device_identifier: test_device_123" in complete_yaml_output
            assert "device_name: Super Smart Device" in complete_yaml_output
            assert "multiplier: 3.0" in complete_yaml_output  # Current multiplier value
            assert "power_multiplier: 2.5" in complete_yaml_output
            assert "location: Garage" in complete_yaml_output

            # Test 10: Verify that the sensor still exists and formula is still valid
            # (This demonstrates how CRUD operations can change sensor behavior through global variables)
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 1
            assert sensors[0].unique_id == "power_analysis"

            # The sensor formula still references multiplier, and the variable still exists
            # This demonstrates how global variable changes affect sensor calculations
            assert "multiplier" in sensors[0].formulas[0].formula  # Original state formula still references it
            current_multiplier = sensor_set.get_global_settings_handler().get_global_variable("multiplier")
            assert current_multiplier == 3.0  # Variable exists and has been updated through CRUD operations

            # Test 11: Delete global settings
            deleted = await yaml_crud.async_delete_global_settings()
            assert deleted is True

            # Verify deletion
            empty_globals = sensor_set.get_global_settings_handler().read_global_settings()
            assert empty_globals == {}

            # Test 12: Read empty globals returns empty string
            empty_yaml_output = yaml_crud.read_global_settings_as_yaml()
            assert empty_yaml_output == ""

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_globals_yaml_crud_validation_errors(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_device_registry
    ):
        """Test YAML CRUD validation and error handling."""

        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock setup
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "test_validation"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Test Validation"
            )

            sensor_set = storage_manager.get_sensor_set(sensor_set_id)
            yaml_crud = sensor_set._globals_yaml_crud

            # Test invalid YAML syntax
            invalid_yaml = """
            device_identifier: test_device
            variables:
              - invalid_list_instead_of_dict
            """
            with pytest.raises(Exception):  # Should raise SyntheticSensorsError
                await yaml_crud.async_create_global_settings_from_yaml(invalid_yaml)

            # Test invalid device info field
            invalid_device_yaml = """
            device_identifier: test_device
            invalid_field: should_not_exist
            """
            with pytest.raises(Exception):  # Should raise SyntheticSensorsError
                await yaml_crud.async_update_device_info_from_yaml(invalid_device_yaml)

            # Test non-dict YAML for variables
            invalid_variable_yaml = "not_a_dict"
            with pytest.raises(Exception):  # Should raise SyntheticSensorsError
                await yaml_crud.async_add_variable_from_yaml(invalid_variable_yaml)

            # Test non-dict YAML for metadata
            invalid_metadata_yaml = "['list', 'instead', 'of', 'dict']"
            with pytest.raises(Exception):  # Should raise SyntheticSensorsError
                await yaml_crud.async_update_metadata_from_yaml(invalid_metadata_yaml)

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_globals_yaml_crud_synchronous_methods(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_device_registry
    ):
        """Test synchronous wrapper methods for YAML CRUD operations."""

        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock setup
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "test_sync_methods"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Test Sync Methods"
            )

            sensor_set = storage_manager.get_sensor_set(sensor_set_id)
            yaml_crud = sensor_set._globals_yaml_crud

            # Test that synchronous methods raise error in async context
            globals_yaml = """
            device_identifier: test_device_123
            variables:
              test_var: 42
            """

            # Should raise error because we're in an async context
            with pytest.raises(Exception):  # Should raise SyntheticSensorsError about async context
                yaml_crud.create_global_settings_from_yaml(globals_yaml)

            with pytest.raises(Exception):  # Should raise SyntheticSensorsError about async context
                yaml_crud.update_global_settings_from_yaml(globals_yaml)

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
