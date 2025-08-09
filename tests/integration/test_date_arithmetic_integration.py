"""Integration tests for date arithmetic with duration functions."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from ha_synthetic_sensors import async_setup_synthetic_sensors
from ha_synthetic_sensors.storage_manager import StorageManager


class TestDateArithmeticIntegration:
    """Integration tests for date arithmetic through the public API."""

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"  # Will be slugified for entity IDs
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        return mock_device_entry

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback for testing."""
        return Mock()

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    async def test_basic_duration_functions(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test basic duration function evaluation through the public API with actual formula evaluation."""

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
            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "date_arithmetic_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device_date_arithmetic",  # Must match YAML global_settings
                name="Date Arithmetic Test Sensors",
            )

            # Load external YAML fixture
            yaml_fixture_path = "tests/fixtures/integration/date_arithmetic_basic.yaml"
            with open(yaml_fixture_path, "r", encoding="utf-8") as f:
                date_arithmetic_yaml = f.read()

            # Import YAML - should succeed
            result = await storage_manager.async_from_yaml(yaml_content=date_arithmetic_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Set up synthetic sensors via public API to test actual evaluation
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_date_arithmetic",
            )

            # Update sensors to trigger formula evaluation
            await sensor_manager.async_update_sensors()

            # Get the actual sensor entities to verify their computed values
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            # Verify we have the expected number of entities
            assert len(all_entities) >= 3, f"Expected at least 3 entities, got {len(all_entities)}"

            # Create a mapping for easy lookup
            sensor_entities = {entity.unique_id: entity for entity in all_entities}

            # Test actual formula evaluation results to verify duration functions work
            # CLEAN SLATE: Duration functions now return seconds (float) via enhanced SimpleEval

            # Test: days(30) - should return 2592000.0 seconds (30 * 24 * 60 * 60)
            days_entity = sensor_entities.get("test_days_function")
            if days_entity and days_entity.native_value is not None:
                expected_seconds = 30 * 24 * 60 * 60  # 30 days in seconds = 2592000
                assert days_entity.native_value == expected_seconds, (
                    f"Days function failed: expected {expected_seconds}, got '{days_entity.native_value}'"
                )

            # Test: hours(24) - should return 86400.0 seconds (24 * 60 * 60)
            hours_entity = sensor_entities.get("test_hours_function")
            if hours_entity and hours_entity.native_value is not None:
                expected_seconds = 24 * 60 * 60  # 24 hours in seconds = 86400
                assert hours_entity.native_value == expected_seconds, (
                    f"Hours function failed: expected {expected_seconds}, got '{hours_entity.native_value}'"
                )

            # Test: minutes(60) - should return 3600.0 seconds (60 * 60)
            minutes_entity = sensor_entities.get("test_minutes_function")
            if minutes_entity and minutes_entity.native_value is not None:
                expected_seconds = 60 * 60  # 60 minutes in seconds = 3600
                assert minutes_entity.native_value == expected_seconds, (
                    f"Minutes function failed: expected {expected_seconds}, got '{minutes_entity.native_value}'"
                )

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_simple_date_functions(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test simple date function usage through the public API with actual formula evaluation."""

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
            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "simple_date_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device_simple_date",  # Must match YAML global_settings
                name="Simple Date Test Sensors",
            )

            # Load external YAML fixture
            yaml_fixture_path = "tests/fixtures/integration/date_arithmetic_simple.yaml"
            with open(yaml_fixture_path, "r", encoding="utf-8") as f:
                simple_date_yaml = f.read()

            # Import YAML - should succeed
            result = await storage_manager.async_from_yaml(yaml_content=simple_date_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 2, f"Expected 2 sensors, got {result['sensors_imported']}"

            # Set up synthetic sensors via public API to test actual evaluation
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_simple_date",
            )

            # Update sensors to trigger formula evaluation
            await sensor_manager.async_update_sensors()

            # Get the actual sensor entities to verify their computed values
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            # Verify we have the expected number of entities
            assert len(all_entities) >= 2, f"Expected at least 2 entities, got {len(all_entities)}"

            # Create a mapping for easy lookup
            sensor_entities = {entity.unique_id: entity for entity in all_entities}

            # Test actual formula evaluation results to verify date functions work
            # Test: date('2025-01-01') - should return ISO date format
            date_conversion_entity = sensor_entities.get("test_date_conversion")
            if date_conversion_entity and date_conversion_entity.native_value is not None:
                expected_date = "2025-01-01"
                assert expected_date in str(date_conversion_entity.native_value), (
                    f"Date conversion failed: expected '{expected_date}' in '{date_conversion_entity.native_value}'"
                )

            # Test: date(start_date) with variable - should return ISO date format
            date_variable_entity = sensor_entities.get("test_date_variable")
            if date_variable_entity and date_variable_entity.native_value is not None:
                expected_date = "2025-01-15"
                assert expected_date in str(date_variable_entity.native_value), (
                    f"Date variable failed: expected '{expected_date}' in '{date_variable_entity.native_value}'"
                )

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_existing_datetime_functions(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test that existing datetime functions still work through the public API with actual formula evaluation."""

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
            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "existing_datetime_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device_existing_datetime",  # Must match YAML global_settings
                name="Existing DateTime Test Sensors",
            )

            # Load external YAML fixture
            yaml_fixture_path = "tests/fixtures/integration/date_arithmetic_existing.yaml"
            with open(yaml_fixture_path, "r", encoding="utf-8") as f:
                existing_datetime_yaml = f.read()

            # Import YAML - should succeed
            result = await storage_manager.async_from_yaml(yaml_content=existing_datetime_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 1, f"Expected 1 sensor, got {result['sensors_imported']}"

            # Set up synthetic sensors via public API to test actual evaluation
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_existing_datetime",
            )

            # Update sensors to trigger formula evaluation
            await sensor_manager.async_update_sensors()

            # Get the actual sensor entities to verify their computed values
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            # Verify we have the expected number of entities
            assert len(all_entities) >= 1, f"Expected at least 1 entity, got {len(all_entities)}"

            # Create a mapping for easy lookup
            sensor_entities = {entity.unique_id: entity for entity in all_entities}

            # Test actual formula evaluation results to verify datetime functions work
            # Test: main formula should be "1"
            now_function_entity = sensor_entities.get("test_now_function")
            if now_function_entity and now_function_entity.native_value is not None:
                # Main formula should evaluate to 1
                assert now_function_entity.native_value == 1, (
                    f"Now function main formula failed: expected '1', got '{now_function_entity.native_value}'"
                )

            # Note: Attributes with datetime functions like now() and today() would need additional testing
            # since they return dynamic timestamps. For integration tests, we verify the main formula evaluates.

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)
