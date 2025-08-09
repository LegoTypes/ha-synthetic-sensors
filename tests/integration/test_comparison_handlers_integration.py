"""Integration tests for comparison handlers using the synthetic sensors public API."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime
from pathlib import Path

from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager, DataProviderCallback
from ha_synthetic_sensors.exceptions import ComparisonHandlerError


class TestComparisonHandlersIntegration:
    """Integration tests for comparison handlers with real YAML fixtures."""

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_numeric_comparisons")}
        return mock_device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry for testing."""
        config_entry = Mock()
        config_entry.entry_id = "test_entry_id"
        config_entry.domain = "test_domain"
        return config_entry

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback."""
        return Mock()

    @pytest.fixture
    def comparison_handlers_numeric_yaml_path(self):
        """Path to numeric comparison handlers YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "comparison_handlers_numeric.yaml"

    @pytest.fixture
    def comparison_handlers_datetime_yaml_path(self):
        """Path to datetime comparison handlers YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "comparison_handlers_datetime.yaml"

    @pytest.fixture
    def comparison_handlers_version_yaml_path(self):
        """Path to version comparison handlers YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "comparison_handlers_version.yaml"

    @pytest.fixture
    def comparison_handlers_equality_yaml_path(self):
        """Path to equality comparison handlers YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "comparison_handlers_equality.yaml"

    @pytest.fixture
    def comparison_handlers_errors_yaml_path(self):
        """Path to error handling comparison handlers YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "comparison_handlers_errors.yaml"

    @pytest.fixture
    def comparison_handlers_string_containment_yaml_path(self):
        """Path to string containment comparison handlers YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "comparison_handlers_string_containment.yaml"

    def create_data_provider_callback(self, backing_data: dict[str, any]) -> DataProviderCallback:
        """Create a data provider callback for virtual backing entities."""

        def data_provider(entity_id: str):
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    def create_mock_state(self, state_value: str, attributes: dict[str, any] | None = None):
        """Create a mock HA state object."""
        return type("MockState", (), {"state": state_value, "attributes": attributes or {}})()

    async def test_numeric_comparison_handlers_integration(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        comparison_handlers_numeric_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test numeric comparison handlers with collection patterns."""

        # Set up mock entities with numeric attributes and states
        mock_states["sensor.high_power_device_1"] = self.create_mock_state(
            "900", {"power_rating": 850, "efficiency_rating": 95.5, "accuracy": 99.2, "standby_power": 15}
        )
        mock_states["sensor.high_power_device_2"] = self.create_mock_state(
            "1200", {"power_rating": 1200, "efficiency_rating": 88.0, "accuracy": 97.8, "standby_power": 20}
        )
        mock_states["sensor.low_power_device_1"] = self.create_mock_state(
            "50", {"power_rating": 75, "efficiency_rating": 40.2, "accuracy": 85.5, "standby_power": 5}
        )
        mock_states["sensor.low_power_device_2"] = self.create_mock_state(
            "25", {"power_rating": 60, "efficiency_rating": 35.8, "accuracy": 88.0, "standby_power": 3}
        )

        # Set up virtual backing entity
        backing_data = {"sensor.base_power_meter": 600.0}

        # Create data provider
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

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load YAML configuration
            sensor_set_id = "numeric_comparison_tests"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device_numeric_comparisons",
                name="Numeric Comparison Tests",
            )

            with open(comparison_handlers_numeric_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 7

            # Set up synthetic sensors via public API
            sensor_to_backing_mapping = {"power_efficiency": "sensor.base_power_meter"}

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Test sensor manager creation
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation
            await sensor_manager.async_update_sensors_for_entities({"sensor.base_power_meter"})
            await sensor_manager.async_update_sensors()

            # Verify results
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 7

            # Verify sensor names match expected patterns
            expected_sensor_keys = {
                "high_power_devices",
                "low_power_devices",
                "active_high_consumption",
                "efficient_devices",
                "precision_devices",
                "power_analysis",
                "power_efficiency",
            }
            actual_sensor_keys = {sensor.unique_id for sensor in sensors}
            assert actual_sensor_keys == expected_sensor_keys

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_datetime_comparison_handlers_integration(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        comparison_handlers_datetime_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test datetime comparison handlers with ISO strings and datetime objects."""

        # Set up mock entities with datetime attributes and states
        mock_states["sensor.recent_device_1"] = self.create_mock_state(
            "2024-06-15T14:30:00Z",
            {
                "last_seen": "2024-06-10T10:00:00Z",
                "last_updated": "2024-06-15T14:30:00Z",
                "manufacture_date": "2023-01-15T00:00:00Z",
                "last_maintenance": "2023-12-01T09:00:00Z",
                "next_service": "2024-07-01T10:00:00Z",
                "warranty_expires": "2025-01-15T23:59:59Z",
            },
        )
        mock_states["sensor.old_device_1"] = self.create_mock_state(
            "2023-11-20T08:15:00Z",
            {
                "last_seen": "2023-11-20T08:15:00Z",
                "last_updated": "2023-11-20T08:15:00Z",
                "manufacture_date": "2022-03-10T00:00:00Z",
                "last_maintenance": "2023-06-15T14:00:00Z",
                "next_service": "2024-01-15T10:00:00Z",
                "warranty_expires": "2024-03-10T23:59:59Z",
            },
        )
        mock_states["sensor.vintage_device_1"] = self.create_mock_state(
            "2023-01-01T00:00:00Z",
            {
                "last_seen": "2024-01-05T12:00:00Z",
                "last_updated": "2024-01-05T12:00:00Z",
                "manufacture_date": "2020-05-01T00:00:00Z",
                "last_maintenance": "2023-05-01T09:00:00Z",
                "next_service": "2024-05-01T10:00:00Z",
                "warranty_expires": "2023-05-01T23:59:59Z",
            },
        )

        # Set up virtual backing entity
        backing_data = {"sensor.current_timestamp": "2024-06-15T15:00:00Z"}

        # Create data provider
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
            mock_device_registry.async_get_device.return_value.identifiers = {
                ("ha_synthetic_sensors", "test_device_datetime_comparisons")
            }

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load YAML configuration
            sensor_set_id = "datetime_comparison_tests"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device_datetime_comparisons",
                name="DateTime Comparison Tests",
            )

            with open(comparison_handlers_datetime_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 7

            # Set up synthetic sensors via public API
            sensor_to_backing_mapping = {"time_based_mode": "sensor.current_timestamp"}

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Test sensor manager creation
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation
            await sensor_manager.async_update_sensors_for_entities({"sensor.current_timestamp"})
            await sensor_manager.async_update_sensors()

            # Verify results
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 7

            # Verify sensor names match expected patterns
            expected_sensor_keys = {
                "recent_devices",
                "old_devices",
                "active_recent",
                "vintage_devices",
                "maintenance_due",
                "time_based_mode",
                "service_candidates",
            }
            actual_sensor_keys = {sensor.unique_id for sensor in sensors}
            assert actual_sensor_keys == expected_sensor_keys

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_version_comparison_handlers_integration(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        comparison_handlers_version_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test version comparison handlers with semantic version strings."""

        # Set up mock entities with version attributes and states
        mock_states["sensor.modern_device_1"] = self.create_mock_state(
            "3.1.0",
            {
                "firmware_version": "3.1.0",
                "software_version": "2.5.0",
                "release_version": "3.0.1",
                "current_version": "3.1.0",
                "min_supported_version": "2.0.0",
                "driver_version": "2.2.0",
                "semantic_version": "3.1.0",
                "version_tag": "v3.1.0",
            },
        )
        mock_states["sensor.legacy_device_1"] = self.create_mock_state(
            "1.2.0",
            {
                "firmware_version": "1.2.0",
                "software_version": "1.0.5",
                "release_version": "1.5.0",
                "current_version": "1.2.0",
                "min_supported_version": "1.0.0",
                "driver_version": "1.8.0",
                "semantic_version": "1.2.0",
                "version_tag": "v1.2.0",
            },
        )
        mock_states["sensor.mixed_device_1"] = self.create_mock_state(
            "2.8.0",
            {
                "firmware_version": "2.8.0",
                "software_version": "2.0.0",
                "release_version": "2.5.0",
                "current_version": "2.8.0",
                "min_supported_version": "2.5.0",
                "driver_version": "3.1.0",
                "semantic_version": "2.8.0",
                "version_tag": "v2.8.0",
            },
        )

        # Set up virtual backing entity
        backing_data = {"sensor.base_version": "2.1.0"}

        # Create data provider
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
            mock_device_registry.async_get_device.return_value.identifiers = {
                ("ha_synthetic_sensors", "test_device_version_comparisons")
            }

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load YAML configuration
            sensor_set_id = "version_comparison_tests"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device_version_comparisons",
                name="Version Comparison Tests",
            )

            with open(comparison_handlers_version_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 9

            # Set up synthetic sensors via public API
            sensor_to_backing_mapping = {"version_status": "sensor.base_version"}

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Test sensor manager creation
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation
            await sensor_manager.async_update_sensors_for_entities({"sensor.base_version"})
            await sensor_manager.async_update_sensors()

            # Verify results
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 9

            # Verify sensor names match expected patterns
            expected_sensor_keys = {
                "compatible_firmware",
                "legacy_devices",
                "updated_devices",
                "stable_versions",
                "prefixed_versions",
                "upgrade_candidates",
                "version_status",
                "maintenance_needed",
                "mixed_version_formats",
            }
            actual_sensor_keys = {sensor.unique_id for sensor in sensors}
            assert actual_sensor_keys == expected_sensor_keys

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_equality_comparison_handlers_integration(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        comparison_handlers_equality_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test equality and inequality operations with mixed types."""

        # Set up mock entities with mixed type attributes and states
        mock_states["sensor.active_device_1"] = self.create_mock_state(
            "on",
            {
                "mode": "auto",
                "power_rating": 100,
                "enabled": True,
                "active": True,
                "brand": "reliable",
                "status": "normal",
                "configuration": {"setting": "value"},
            },
        )
        mock_states["sensor.inactive_device_1"] = self.create_mock_state(
            "off",
            {
                "mode": "manual",
                "power_rating": 75,
                "enabled": False,
                "active": False,
                "brand": "unknown",
                "status": "error",
                "configuration": None,
            },
        )
        mock_states["sensor.variable_device_1"] = self.create_mock_state(
            "150",
            {
                "mode": "auto",
                "power_rating": 150,
                "enabled": True,
                "active": True,
                "brand": "premium",
                "status": "normal",
                "configuration": {"advanced": True},
            },
        )

        # Set up virtual backing entity
        backing_data = {"sensor.base_state": "on"}

        # Create data provider
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
            mock_device_registry.async_get_device.return_value.identifiers = {
                ("ha_synthetic_sensors", "test_device_equality_comparisons")
            }

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load YAML configuration
            sensor_set_id = "equality_comparison_tests"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device_equality_comparisons",
                name="Equality Comparison Tests",
            )

            with open(comparison_handlers_equality_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 10

            # Set up synthetic sensors via public API
            sensor_to_backing_mapping = {"state_matcher": "sensor.base_state"}

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Test sensor manager creation
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation
            await sensor_manager.async_update_sensors_for_entities({"sensor.base_state"})
            await sensor_manager.async_update_sensors()

            # Verify results
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 10

            # Verify sensor names match expected patterns
            expected_sensor_keys = {
                "active_devices",
                "non_auto_devices",
                "exact_power_devices",
                "variable_power_devices",
                "enabled_devices",
                "disabled_devices",
                "state_matcher",
                "filtered_devices",
                "mixed_filter",
                "configured_devices",
            }
            actual_sensor_keys = {sensor.unique_id for sensor in sensors}
            assert actual_sensor_keys == expected_sensor_keys

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_comparison_error_handling_integration(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        comparison_handlers_errors_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test comparison handler error scenarios and graceful degradation."""

        # Set up mock entities that will trigger various error conditions
        mock_states["sensor.problematic_device_1"] = self.create_mock_state(
            "text_state",
            {
                "name": "device_name",  # String that can't be compared to numbers
                "enabled": "on",  # Boolean-like that can't be ordered
                "invalid_date": "not_a_date",  # Invalid datetime string
                "bad_version": "invalid.version.format",  # Invalid version
                "null_attribute": None,  # None values
                "valid_power": 150,  # Valid numeric for working comparisons
                "power_rating": 75,  # Valid numeric for working comparisons
            },
        )

        # Also set up some valid entities for comparison
        mock_states["sensor.valid_device_1"] = self.create_mock_state(
            "2024-07-01T10:00:00Z",
            {"last_seen": "2024-06-15T14:30:00Z", "version": "2.5.0", "power_rating": 125, "valid_power": 200},
        )

        # Set up virtual backing entity
        backing_data = {"sensor.base_value": 100.0}

        # Create data provider
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
            mock_device_registry.async_get_device.return_value.identifiers = {
                ("ha_synthetic_sensors", "test_device_comparison_errors")
            }

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load YAML configuration
            sensor_set_id = "error_handling_tests"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_comparison_errors", name="Error Handling Tests"
            )

            with open(comparison_handlers_errors_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 9

            # Set up synthetic sensors via public API
            sensor_to_backing_mapping = {"complex_error_handling": "sensor.base_value"}

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Test sensor manager creation
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation - this should handle errors gracefully
            await sensor_manager.async_update_sensors_for_entities({"sensor.base_value"})
            await sensor_manager.async_update_sensors()

            # Verify results - sensors should be created even if some have evaluation errors
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 9

            # Verify sensor names match expected patterns
            expected_sensor_keys = {
                "invalid_string_numeric",
                "invalid_boolean_ordering",
                "invalid_datetime",
                "invalid_version",
                "null_comparison",
                "valid_datetime_string",
                "valid_version_string",
                "complex_error_handling",
                "mixed_valid_invalid",
            }
            actual_sensor_keys = {sensor.unique_id for sensor in sensors}
            assert actual_sensor_keys == expected_sensor_keys

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_string_containment_handlers_integration(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        comparison_handlers_string_containment_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test string containment operations with 'in' and 'not in' operators."""

        # Set up mock entities with string attributes that test containment
        mock_states["sensor.living_room_light"] = self.create_mock_state(
            "active",
            {"name": "Living Room Smart Light", "manufacturer": "SmartCorp", "status": "Active", "room": "Living Room"},
        )
        mock_states["sensor.kitchen_appliance"] = self.create_mock_state(
            "on", {"name": "Kitchen Dishwasher", "manufacturer": "ApplianceCorp", "status": "Running", "room": "Kitchen"}
        )
        mock_states["sensor.bedroom_sensor"] = self.create_mock_state(
            "inactive",
            {"name": "Bedroom Temperature Sensor", "manufacturer": "SensorCorp", "status": "Inactive", "room": "Bedroom"},
        )
        mock_states["sensor.error_device"] = self.create_mock_state(
            "error_state", {"name": "Faulty Device", "manufacturer": "Unknown", "status": "Error", "room": "Utility"}
        )
        mock_states["sensor.no_name_device"] = self.create_mock_state(
            "unknown",
            {
                "name": "",  # Empty name for testing
                "manufacturer": "GenericCorp",
                "status": "Unknown",
                "room": "Storage",
            },
        )

        # Set up virtual backing entity
        backing_data = {"sensor.test_filter": "Living"}

        # Create data provider
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
            mock_device_registry.async_get_device.return_value.identifiers = {
                ("ha_synthetic_sensors", "test_device_string_containment")
            }

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load YAML configuration
            sensor_set_id = "string_containment_tests"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_string_containment", name="String Containment Tests"
            )

            with open(comparison_handlers_string_containment_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 10

            # Set up synthetic sensors via public API
            sensor_to_backing_mapping = {"room_categorizer": "sensor.test_filter"}

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Test sensor manager creation
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation
            await sensor_manager.async_update_sensors_for_entities({"sensor.test_filter"})
            await sensor_manager.async_update_sensors()

            # Verify results
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 10

            # Verify sensor names match expected patterns
            expected_sensor_keys = {
                "living_room_devices",
                "non_kitchen_devices",
                "active_status_devices",
                "non_error_devices",
                "branded_devices",
                "filtered_device_count",
                "exact_status_match",
                "all_devices_with_names",
                "multi_room_devices",
                "room_categorizer",
            }
            actual_sensor_keys = {sensor.unique_id for sensor in sensors}
            assert actual_sensor_keys == expected_sensor_keys

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
