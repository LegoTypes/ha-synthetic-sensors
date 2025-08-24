"""Integration tests for collection resolver functionality."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from ha_synthetic_sensors.storage_manager import StorageManager


class TestCollectionResolverIntegration:
    """Integration tests for collection resolution through the public API."""

    @pytest.fixture
    def collection_resolver_device_class_yaml_path(self):
        """Path to device class collection patterns YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "collection_resolver_device_class.yaml"

    @pytest.fixture
    def collection_resolver_area_yaml_path(self):
        """Path to area collection patterns YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "collection_resolver_area.yaml"

    @pytest.fixture
    def collection_resolver_state_yaml_path(self):
        """Path to state collection patterns YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "collection_resolver_state.yaml"

    @pytest.fixture
    def collection_resolver_attribute_yaml_path(self):
        """Path to attribute collection patterns YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "collection_resolver_attribute.yaml"

    @pytest.fixture
    def collection_resolver_complex_yaml_path(self):
        """Path to complex collection patterns YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "collection_resolver_complex.yaml"

    async def test_collection_resolver_device_class_patterns(
        self, mock_hass, mock_entity_registry, mock_states, collection_resolver_device_class_yaml_path
    ):
        """Test collection resolution with device class patterns."""

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

            # Load YAML from fixture
            with open(collection_resolver_device_class_yaml_path, "r") as f:
                yaml_content = f.read()

            # Import YAML - this should resolve collection patterns
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_collection_resolver_area_patterns(
        self, mock_hass, mock_entity_registry, mock_states, collection_resolver_area_yaml_path
    ):
        """Test collection resolution with area patterns."""

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

            # Load YAML from fixture
            with open(collection_resolver_area_yaml_path, "r") as f:
                yaml_content = f.read()

            # Import YAML - this should resolve area patterns
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_collection_resolver_state_patterns(
        self, mock_hass, mock_entity_registry, mock_states, collection_resolver_state_yaml_path
    ):
        """Test collection resolution with state patterns."""

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

            # Load YAML from fixture
            with open(collection_resolver_state_yaml_path, "r") as f:
                yaml_content = f.read()

            # Import YAML - this should resolve state patterns
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_collection_resolver_attribute_patterns(
        self, mock_hass, mock_entity_registry, mock_states, collection_resolver_attribute_yaml_path
    ):
        """Test collection resolution with attribute patterns."""

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

            # Load YAML from fixture
            with open(collection_resolver_attribute_yaml_path, "r") as f:
                yaml_content = f.read()

            # Import YAML - this should resolve attribute patterns
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_collection_resolver_complex_patterns(
        self, mock_hass, mock_entity_registry, mock_states, collection_resolver_complex_yaml_path
    ):
        """Test collection resolution with complex combined patterns."""

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

            # Load YAML from fixture
            with open(collection_resolver_complex_yaml_path, "r") as f:
                yaml_content = f.read()

            # Import YAML - this should resolve complex patterns
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)
