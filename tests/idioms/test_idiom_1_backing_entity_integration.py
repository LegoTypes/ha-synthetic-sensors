"""Integration tests for Idiom 1: Backing Entity State Resolution using public API."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager, DataProviderCallback


class TestIdiom1BackingEntityIntegration:
    """Integration tests for Idiom 1: Backing Entity State Resolution using public API."""

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback."""
        return Mock()

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        return mock_device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    def create_data_provider_callback(self, backing_data: dict[str, any]) -> DataProviderCallback:
        """Create data provider for virtual backing entities."""

        def data_provider(entity_id: str):
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    async def test_backing_entity_integration_public_api(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test backing entity integration using only the public API."""

        # Set up virtual backing entity data
        backing_data = {"sensor.span_panel_instantaneous_power": 1000.0}

        # Create data provider for virtual backing entities
        data_provider = self.create_data_provider_callback(backing_data)

        # Create change notifier callback for selective updates
        def change_notifier_callback(changed_entity_ids: set[str]) -> None:
            pass  # Enable real-time selective sensor updates

        # Create sensor-to-backing mapping for 'state' token resolution
        sensor_to_backing_mapping = {"power_analyzer": "sensor.span_panel_instantaneous_power"}

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set and load YAML
            sensor_set_id = "idiom1_backing_entity_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Idiom 1 Backing Entity Test"
            )

            # Load YAML content from fixture (create if needed)
            yaml_fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "integration_test_idiom1_backing_entity.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] >= 1

            # Set up synthetic sensors via public API with virtual backing entities
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,  # For virtual entities
                change_notifier=change_notifier_callback,  # Enable selective updates
                sensor_to_backing_mapping=sensor_to_backing_mapping,  # Map 'state' token
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation with backing entity
            await sensor_manager.async_update_sensors_for_entities({"sensor.span_panel_instantaneous_power"})
            await sensor_manager.async_update_sensors()

            # Verify sensors were created and handle backing entity properly
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) >= 1

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_missing_backing_entity_integration(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test integration behavior when backing entity is missing."""

        # No backing data - entity is missing
        backing_data = {}

        data_provider = self.create_data_provider_callback(backing_data)

        def change_notifier_callback(changed_entity_ids: set[str]) -> None:
            pass

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "idiom1_missing_backing_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Idiom 1 Missing Backing Test"
            )

            # Load YAML that references missing backing entity
            yaml_fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "integration_test_idiom1_missing_backing.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] >= 1

            # Set up synthetic sensors - should handle missing backing gracefully
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test update behavior with missing entity - should not crash
            await sensor_manager.async_update_sensors()

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
