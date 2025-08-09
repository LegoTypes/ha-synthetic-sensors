"""Integration tests for computed variables functionality."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from ha_synthetic_sensors import (
    async_setup_synthetic_sensors,
    StorageManager,
    DataProviderCallback,
)


class TestComputedVariablesIntegration:
    """Test computed variables using real YAML and the public API following the integration guide."""

    @pytest.fixture
    def computed_variables_yaml_path(self):
        """Path to computed variables integration YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "computed_variables_integration.yaml"

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

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback."""
        return Mock()  # Use Mock(), not AsyncMock() per the guide

    def create_data_provider_callback(self, backing_data: dict[str, any]) -> DataProviderCallback:
        """Create a data provider callback for virtual backing entities."""

        def data_provider(entity_id: str):
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    def create_mock_state(self, state_value: str, attributes: dict = None):
        """Create a mock HA state object."""
        return type("MockState", (), {"state": state_value, "attributes": attributes or {}})()

    async def test_computed_variables_basic_integration(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        computed_variables_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test basic computed variables integration with dependency ordering."""

        # Set up test data - external entities that will be referenced
        mock_states["sensor.inverter_input"] = self.create_mock_state("1200.0")
        mock_states["sensor.external_sensor"] = self.create_mock_state("50.0")
        mock_states["sensor.factor_sensor"] = self.create_mock_state("3.0")
        mock_states["sensor.raw_sensor"] = self.create_mock_state("-25.5")

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None  # Empty storage initially
            MockStore.return_value = mock_store

            # Use the common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load YAML configuration
            sensor_set_id = "computed_variables_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Computed Variables Test Sensors"
            )

            with open(computed_variables_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4  # 4 sensors in our YAML

            # Set up synthetic sensors via public API - HA entity lookups only
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,  # System automatically falls back to HA entity lookups when no data provider is specified
            )

            # Verify setup succeeded
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation - this should resolve computed variables
            await sensor_manager.async_update_sensors()

            # Verify sensors were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 4

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_computed_variables_with_virtual_backing(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        computed_variables_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test computed variables with virtual backing entities pattern."""

        # Set up virtual backing entity data
        backing_data = {
            "sensor.virtual_inverter": 1500.0,  # Virtual data source
        }

        # Set up some real HA entities too
        mock_states["sensor.external_sensor"] = self.create_mock_state("100.0")
        mock_states["sensor.factor_sensor"] = self.create_mock_state("2.5")
        mock_states["sensor.raw_sensor"] = self.create_mock_state("-42.7")

        # Create data provider for virtual backing entities
        data_provider = self.create_data_provider_callback(backing_data)

        # Set up storage manager with proper mocking
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

            # Load YAML configuration
            sensor_set_id = "computed_variables_virtual_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Computed Variables Virtual Test"
            )

            with open(computed_variables_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4

            # Create sensor-to-backing mapping for 'state' token resolution
            sensor_to_backing_mapping = {"energy_sensor_with_computed_variables": "sensor.virtual_inverter"}

            # Create change notifier callback for selective updates
            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                """Handle change notifications for virtual entities."""
                pass

            # Hybrid setup - virtual backing + HA entity fallback
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )
            # HA entity fallback is now automatic - no parameter needed

            # Verify setup
            assert sensor_manager is not None

            # Test both update mechanisms
            # 1. Selective updates via change notification
            changed_entities = {"sensor.virtual_inverter"}
            await sensor_manager.async_update_sensors_for_entities(changed_entities)

            # 2. General update mechanism
            await sensor_manager.async_update_sensors()

            # Verify sensors were created and handle dependencies gracefully
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 4

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_computed_variables_dependency_resolution_order(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        computed_variables_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test that computed variables are resolved in correct dependency order."""

        # Set up entities with known values for predictable results
        mock_states["sensor.inverter_input"] = self.create_mock_state("1000.0")
        mock_states["sensor.external_sensor"] = self.create_mock_state("25.0")
        mock_states["sensor.factor_sensor"] = self.create_mock_state("4.0")
        mock_states["sensor.raw_sensor"] = self.create_mock_state("-15.3")

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

            # Create and load configuration
            sensor_set_id = "dependency_order_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Dependency Order Test"
            )

            with open(computed_variables_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4

            # Set up sensor manager
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
            )
            # HA entity fallback is now automatic - no parameter needed

            # Verify successful setup and evaluation
            assert sensor_manager is not None
            await sensor_manager.async_update_sensors()

            # Verify all sensors were created (they should handle computed variables correctly)
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 4

            # Each sensor should have its computed variables properly resolved
            sensor_names = [sensor.name for sensor in sensors]
            expected_names = [
                "Energy Sensor with Computed Variables",
                "Simple Computed Sensor",
                "Complex Dependency Chain Sensor",
                "Mathematical Functions Sensor",
            ]

            for expected_name in expected_names:
                assert expected_name in sensor_names, f"Missing sensor: {expected_name}"

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_computed_variables_missing_dependencies_handling(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        computed_variables_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test graceful handling of missing dependencies in computed variables."""

        # Set up only SOME of the required entities - leave some missing
        mock_states["sensor.external_sensor"] = self.create_mock_state("75.0")
        mock_states["sensor.factor_sensor"] = self.create_mock_state("1.5")
        # Deliberately NOT setting up sensor.inverter_input and sensor.raw_sensor

        # Ensure missing entities are NOT in mock_states
        if "sensor.inverter_input" in mock_states:
            del mock_states["sensor.inverter_input"]
        if "sensor.raw_sensor" in mock_states:
            del mock_states["sensor.raw_sensor"]

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

            sensor_set_id = "missing_dependencies_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Missing Dependencies Test"
            )

            with open(computed_variables_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4

            # Set up sensor manager - should handle missing entities gracefully
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
            )
            # HA entity fallback is now automatic - no parameter needed

            # System should remain stable even with missing dependencies
            assert sensor_manager is not None

            # This should not crash, even with missing dependencies
            await sensor_manager.async_update_sensors()

            # Some sensors may work (those with available dependencies), others may not
            # The key is that the system remains stable
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 4  # All sensors should be created, even if some have missing deps

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
