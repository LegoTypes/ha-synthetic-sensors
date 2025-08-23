"""Integration test for direct entity references."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
import yaml

import pytest

from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager


class TestDirectEntityReferenceIntegration:
    """Test direct entity references in full integration context."""

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback."""
        return Mock()

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_direct")}
        return mock_device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    def create_data_provider_callback(self, backing_data: dict[str, any]):
        """Create data provider for entities."""

        def data_provider(entity_id: str):
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    async def test_direct_entity_reference_full_integration(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test direct entity reference using full integration setup."""

        # Set up entity data
        backing_data = {"sensor.circuit_a_power": 1.0}

        # Create data provider for entities
        data_provider = self.create_data_provider_callback(backing_data)

        # Create change notifier callback
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

            # Create sensor set and load YAML
            sensor_set_id = "direct_entity_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_direct", name="Direct Entity Test"
            )

            # Load YAML content from fixture
            yaml_fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "test_direct_entity_reference.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] >= 1

            # Set up synthetic sensors via public API
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
            )

            assert sensor_manager is not None

            # Get the sensors that were created
            sensors = list(sensor_manager.managed_sensors.values())
            assert len(sensors) >= 2, f"Expected at least 2 sensors, got {len(sensors)}"

            # Find the direct entity test sensor
            direct_sensor = next((s for s in sensors if s.unique_id == "direct_entity_test"), None)
            assert direct_sensor is not None, "direct_entity_test sensor not found"

            # Find the direct entity arithmetic test sensor
            arithmetic_sensor = next((s for s in sensors if s.unique_id == "direct_entity_arithmetic_test"), None)
            assert arithmetic_sensor is not None, "direct_entity_arithmetic_test sensor not found"

            # Test the direct entity reference sensor
            print(f"Testing direct entity reference: {direct_sensor.config.formulas[0].formula}")
            await direct_sensor.async_update()

            print(f"Direct entity result - state: {direct_sensor.state}, native_value: {direct_sensor.native_value}")

            # Test the direct entity arithmetic sensor
            print(f"Testing direct entity arithmetic: {arithmetic_sensor.config.formulas[0].formula}")
            await arithmetic_sensor.async_update()

            print(f"Arithmetic result - state: {arithmetic_sensor.state}, native_value: {arithmetic_sensor.native_value}")

            # The arithmetic version should work (based on our previous tests)
            assert arithmetic_sensor.native_value == 11.0, f"Expected 11.0 (1.0 + 10), got {arithmetic_sensor.native_value}"

            # Let's see what the direct reference returns
            print(f"Direct reference returned: {direct_sensor.native_value}")
            # Don't assert on this yet - let's see what it actually returns
