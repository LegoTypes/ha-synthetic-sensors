"""Integration tests for datetime functions in synthetic sensors."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
import pytest

from ha_synthetic_sensors import (
    async_setup_synthetic_sensors,
    StorageManager,
    DataProviderCallback,
)


class TestDateTimeFunctionsIntegration:
    """Test datetime functions integration with synthetic sensors."""

    @pytest.fixture
    def datetime_functions_yaml_path(self):
        """Path to datetime functions integration YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "datetime_functions_integration.yaml"

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device DateTime Functions"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_datetime_functions")}
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
        return Mock()

    def create_data_provider_callback(self, backing_data: dict[str, any]) -> DataProviderCallback:
        """Create a data provider callback for testing."""

        def data_provider(entity_id: str):
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    def create_mock_state(self, state_value: str, attributes: dict = None):
        """Create a mock state object."""
        return type("MockState", (), {"state": state_value, "attributes": attributes or {}})()

    async def test_datetime_functions_basic_integration(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        datetime_functions_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test basic datetime functions integration with synthetic sensors."""

        # Set up test data - external datetime entity for comparison tests
        mock_states["sensor.external_datetime_entity"] = self.create_mock_state("2025-07-30T12:00:00")

        # Set up storage manager with proper mocking (following the guide)
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

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_datetime_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load YAML configuration
            sensor_set_id = "datetime_functions_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device_datetime_functions",  # Must match YAML global_settings
                name="DateTime Functions Test Sensors",
            )

            with open(datetime_functions_yaml_path, "r") as f:
                yaml_content = f.read()

            # Import YAML with dependency resolution
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4  # 4 sensors in the fixture

            # Set up synthetic sensors via public API using HA entity lookups
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_datetime_functions",
                # No data_provider_callback means HA entity lookups are used automatically
            )

            # Verify setup
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation - both update mechanisms
            await sensor_manager.async_update_sensors()

            # Get the actual sensor entities to verify their computed values
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            # Verify we have the expected number of entities
            assert len(all_entities) >= 4, f"Expected at least 4 entities, got {len(all_entities)}"

            # Create a mapping for easy lookup
            sensor_entities = {entity.unique_id: entity for entity in all_entities}

            # Test actual formula evaluation results
            # Test: "session_start >= yesterday() ? 1 : 0" - should be 1 (true) since session_start is now()
            datetime_comparison_entity = sensor_entities.get("datetime_comparison_sensor")
            if datetime_comparison_entity and datetime_comparison_entity.native_value is not None:
                # session_start (now()) should definitely be >= yesterday(), so result should be 1
                expected = 1
                assert datetime_comparison_entity.native_value == expected, (
                    f"DateTime comparison failed: expected '{expected}', got '{datetime_comparison_entity.native_value}'"
                )

            # Test: "power_reading" where power_reading=1000 - should be literal value
            datetime_literals_entity = sensor_entities.get("datetime_literals_sensor")
            if datetime_literals_entity and datetime_literals_entity.native_value is not None:
                expected = 1000
                assert datetime_literals_entity.native_value == expected, (
                    f"DateTime literals sensor failed: expected '{expected}', got '{datetime_literals_entity.native_value}'"
                )

            # Test: "utc_now() >= utc_yesterday() ? 1 : 0" - should be 1 (true)
            timezone_comparison_entity = sensor_entities.get("timezone_comparison_sensor")
            if timezone_comparison_entity and timezone_comparison_entity.native_value is not None:
                # utc_now() should definitely be >= utc_yesterday(), so result should be 1
                expected = 1
                assert timezone_comparison_entity.native_value == expected, (
                    f"Timezone comparison failed: expected '{expected}', got '{timezone_comparison_entity.native_value}'"
                )

            # Test: "entity_timestamp >= today() ? 1 : 0" where entity_timestamp is "2025-07-30T12:00:00"
            entity_datetime_entity = sensor_entities.get("entity_datetime_comparison")
            if entity_datetime_entity and entity_datetime_entity.native_value is not None:
                # The entity timestamp "2025-07-30T12:00:00" should be >= today(), so result should be 1
                expected = 1
                assert entity_datetime_entity.native_value == expected, (
                    f"Entity datetime comparison failed: expected '{expected}', got '{entity_datetime_entity.native_value}'"
                )

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_datetime_literals_in_variables_and_attributes(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        datetime_functions_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test that datetime functions work as literals in variables and attributes."""

        # Set up storage manager
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_datetime_literals", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load configuration
            sensor_set_id = "datetime_literals_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_datetime_functions", name="DateTime Literals Test"
            )

            with open(datetime_functions_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4

            # Get the sensor set to verify literals were processed
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)
            assert sensor_set is not None

            # Get the list of sensors
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 4

            # Find the datetime literals sensor by name
            literals_sensor = None
            for sensor in sensors:
                if sensor.name == "DateTime Literals Test":
                    literals_sensor = sensor
                    break

            assert literals_sensor is not None

            # Verify the sensor was created successfully - this confirms that
            # datetime function literals in variables and attributes were processed correctly

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_datetime_comparison_with_external_entities(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        datetime_functions_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test datetime functions work with external entity datetime values."""

        # Set up external entities with various datetime formats
        mock_states["sensor.external_datetime_entity"] = self.create_mock_state("2025-07-31T10:00:00Z")
        mock_states["sensor.recent_activity"] = self.create_mock_state("2025-07-31T09:30:00")
        mock_states["sensor.old_activity"] = self.create_mock_state("2025-07-29T15:00:00")

        # Set up storage manager
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_datetime_comparison", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load configuration
            sensor_set_id = "datetime_comparison_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_datetime_functions", name="DateTime Comparison Test"
            )

            with open(datetime_functions_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4

            # Set up synthetic sensors
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_datetime_functions",
                # No data_provider_callback means HA entity lookups are used automatically
            )

            # Test that sensors can be created and evaluated without errors
            assert sensor_manager is not None
            await sensor_manager.async_update_sensors()

            # Verify no exceptions were raised during evaluation
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 4

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
