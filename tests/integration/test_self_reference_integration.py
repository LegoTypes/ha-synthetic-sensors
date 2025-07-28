"""Integration tests for self-reference resolver functionality targeting improved coverage."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

# Use public API imports as shown in integration guide
from ha_synthetic_sensors import (
    async_setup_synthetic_sensors,
    StorageManager,
    DataProviderCallback,
)


class TestSelfReferenceIntegration:
    """Integration tests for self-reference resolver through the public API."""

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
        mock_device_entry.name = "Test Device"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    @pytest.fixture
    def self_reference_basic_yaml_path(self):
        """Path to basic self-reference YAML fixture."""
        return Path(__file__).parent.parent / "yaml_fixtures" / "integration_test_self_reference_basic.yaml"

    @pytest.fixture
    def self_reference_missing_yaml_path(self):
        """Path to self-reference missing backing entity YAML fixture."""
        return Path(__file__).parent.parent / "yaml_fixtures" / "integration_test_self_reference_missing.yaml"

    @pytest.fixture
    def self_reference_cross_sensor_yaml_path(self):
        """Path to cross-sensor self-reference YAML fixture."""
        return Path(__file__).parent.parent / "yaml_fixtures" / "integration_test_self_reference_cross_sensor.yaml"

    def create_data_provider_callback(self, backing_data: dict[str, any]) -> DataProviderCallback:
        """Create a data provider callback for testing with virtual backing entities."""

        def data_provider(entity_id: str):
            """Provide test data for virtual backing entities."""
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    async def test_self_reference_with_backing_entity(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
        self_reference_basic_yaml_path,
    ):
        """Test self-reference resolution with virtual backing entities."""
        # Set up virtual backing entity data
        backing_data = {"sensor.virtual_backing_power": 1500.0, "sensor.virtual_backing_efficiency": 0.85}

        # Create data provider for virtual backing entities
        data_provider = self.create_data_provider_callback(backing_data)

        # Create change notifier callback
        def change_notifier_callback(changed_entity_ids: set[str]) -> None:
            pass

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock setup
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            # Use common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_self_ref", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "self_ref_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Self Reference Test Sensors"
            )

            # Load YAML configuration from fixture
            with open(self_reference_basic_yaml_path, "r") as f:
                yaml_content = f.read()

            # Import YAML configuration
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3

            # Create sensor-to-backing mapping for self-reference resolution
            sensor_to_backing_mapping = {
                "power_sensor": "sensor.virtual_backing_power",
                "efficiency_sensor": "sensor.virtual_backing_efficiency",
            }

            # Set up synthetic sensors via public API
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
                allow_ha_lookups=False,  # Virtual entities only
            )

            # Verify setup
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation with self-references
            await sensor_manager.async_update_sensors_for_entities({"sensor.virtual_backing_power"})
            await sensor_manager.async_update_sensors()

            # Verify sensors were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_self_reference_with_missing_backing_entity(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
        self_reference_missing_yaml_path,
    ):
        """Test self-reference resolution when backing entity is missing."""
        # Set up partial backing entity data (missing one entity)
        backing_data = {
            "sensor.virtual_backing_available": 1000.0
            # "sensor.virtual_backing_missing" intentionally missing
        }

        # Create data provider for virtual backing entities
        data_provider = self.create_data_provider_callback(backing_data)

        # Create change notifier callback
        def change_notifier_callback(changed_entity_ids: set[str]) -> None:
            pass

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock setup
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            # Use common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_self_ref_missing", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "self_ref_missing_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Self Reference Missing Test Sensors"
            )

            # Load YAML configuration from fixture
            with open(self_reference_missing_yaml_path, "r") as f:
                yaml_content = f.read()

            # Import YAML configuration
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 2

            # Create sensor-to-backing mapping including missing entity
            sensor_to_backing_mapping = {
                "available_sensor": "sensor.virtual_backing_available",
                "missing_sensor": "sensor.virtual_backing_missing",  # This one is missing
            }

            # Set up synthetic sensors via public API
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
                allow_ha_lookups=False,  # Virtual entities only
            )

            # Verify setup
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation - should handle missing dependency gracefully
            await sensor_manager.async_update_sensors_for_entities({"sensor.virtual_backing_available"})
            await sensor_manager.async_update_sensors()

            # Verify sensors were created (system should remain stable)
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 2

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_self_reference_cross_sensor_patterns(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
        self_reference_cross_sensor_yaml_path,
    ):
        """Test self-reference resolution in cross-sensor reference patterns."""
        # Set up virtual backing entity data
        backing_data = {"sensor.virtual_backing_base": 1000.0, "sensor.virtual_backing_multiplier": 2.5}

        # Create data provider for virtual backing entities
        data_provider = self.create_data_provider_callback(backing_data)

        # Create change notifier callback
        def change_notifier_callback(changed_entity_ids: set[str]) -> None:
            pass

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock setup
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            # Use common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_self_ref_cross", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "self_ref_cross_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Self Reference Cross Sensor Test"
            )

            # Load YAML configuration from fixture
            with open(self_reference_cross_sensor_yaml_path, "r") as f:
                yaml_content = f.read()

            # Import YAML configuration
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4

            # Create sensor-to-backing mapping for self-reference resolution
            sensor_to_backing_mapping = {
                "base_sensor": "sensor.virtual_backing_base",
                "multiplier_sensor": "sensor.virtual_backing_multiplier",
                "recursive_sensor": "sensor.virtual_backing_base",  # Reuse backing entity
            }

            # Set up synthetic sensors via public API
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
                allow_ha_lookups=False,  # Virtual entities only
            )

            # Verify setup
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation with complex cross-references
            await sensor_manager.async_update_sensors_for_entities({"sensor.virtual_backing_base"})
            await sensor_manager.async_update_sensors_for_entities({"sensor.virtual_backing_multiplier"})
            await sensor_manager.async_update_sensors()

            # Verify sensors were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 4

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
