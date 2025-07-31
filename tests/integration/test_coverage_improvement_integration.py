"""Integration tests targeting high-value coverage gaps identified in coverage analysis."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

# Use public API imports
from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager


class TestCoverageImprovementIntegration:
    """Integration tests designed to improve coverage in high-value, low-coverage areas."""

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

    async def test_yaml_async_file_operations_coverage(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test YAML async file operations to improve yaml_config_parser.py coverage (37%)."""
        # Set up mock states for the fixture entities
        mock_states["sensor.async_computation_source"] = type("MockState", (), {"state": "150.0", "attributes": {}})()
        mock_states["sensor.fallback_data_source"] = type("MockState", (), {"state": "75.0", "attributes": {}})()
        mock_states["sensor.encoding_test_source"] = type("MockState", (), {"state": "10.0", "attributes": {}})()

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

            # Create sensor set and load async file operations YAML
            sensor_set_id = "yaml_async_operations_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="async_test_device", name="YAML Async Operations Test"
            )

            yaml_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "yaml_async_file_operations.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            # This should exercise async_load_yaml_file and validation paths
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3

            # Set up sensor manager to test async operations
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="async_test_device",
            )

            assert sensor_manager is not None
            await sensor_manager.async_update_sensors()

            # Verify sensors were created and can be evaluated
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Verify async file test sensor
            async_file_sensor = next((s for s in sensors if s.unique_id == "async_file_test_sensor"), None)
            assert async_file_sensor is not None
            assert len(async_file_sensor.formulas) == 3  # Main + 2 attributes

            # Verify validation sensor
            validation_sensor = next((s for s in sensors if s.unique_id == "yaml_structure_validation_sensor"), None)
            assert validation_sensor is not None

            # Verify file I/O edge cases sensor
            file_io_sensor = next((s for s in sensors if s.unique_id == "file_io_edge_cases_sensor"), None)
            assert file_io_sensor is not None
            assert len(file_io_sensor.formulas) == 4  # Main + 3 attributes

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_deep_entity_attribute_resolution_coverage(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test deep entity attribute resolution to improve entity_attribute_resolver.py coverage (38%)."""
        # Set up complex mock states with nested attributes
        mock_health_state = type(
            "MockState",
            (),
            {
                "state": "100.0",
                "attributes": {
                    "status": {"level": 95.0},
                    "device": {"hardware": {"cpu": {"temperature": 45.0}, "memory": {"usage": 78.0}}},
                },
            },
        )()

        mock_performance_state = type(
            "MockState",
            (),
            {
                "state": "85.0",
                "attributes": {
                    "metrics": {"efficiency": {"score": 88.0}},
                    "data": {"measurements": {"values": {"average": 82.0, "peak": 95.0}}},
                },
            },
        )()

        mock_states["sensor.system_health_monitor"] = mock_health_state
        mock_states["sensor.performance_analytics"] = mock_performance_state
        mock_states["sensor.device_monitor_complex"] = mock_health_state
        mock_states["sensor.configuration_source"] = type(
            "MockState", (), {"state": "50.0", "attributes": {"config": {"threshold": 75.0}}}
        )()
        mock_states["sensor.status_provider"] = type(
            "MockState", (), {"state": "60.0", "attributes": {"status": {"current_value": 80.0}}}
        )()
        mock_states["sensor.data_source_nested"] = mock_performance_state

        # Add missing entity handling states
        mock_states["sensor.reliable_entity"] = type("MockState", (), {"state": "100.0", "attributes": {"value": 100.0}})()
        mock_states["sensor.working_entity"] = type("MockState", (), {"state": "50.0", "attributes": {"attr": 50.0}})()
        mock_states["sensor.primary_source"] = type("MockState", (), {"state": "25.0", "attributes": {"attr": 25.0}})()
        mock_states["sensor.secondary_source"] = type("MockState", (), {"state": "35.0", "attributes": {"attr": 35.0}})()
        mock_states["sensor.tertiary_source"] = type("MockState", (), {"state": "45.0", "attributes": {"attr": 45.0}})()

        # Add complex object type testing states
        mock_states["sensor.complex_object_entity"] = type("MockState", (), {"state": "200.0", "attributes": {}})()
        mock_states["sensor.builtin_fallback_entity"] = type("MockState", (), {"state": "300.0", "attributes": {}})()
        mock_states["sensor.value_extractable_entity"] = type(
            "MockState", (), {"state": "10.0", "attributes": {"value": 20.0, "native_value": 30.0}}
        )()
        mock_states["sensor.fallback_test_entity"] = type(
            "MockState", (), {"state": "15.0", "attributes": {"fallback_value": 25.0}}
        )()
        mock_states["sensor.potentially_none_entity"] = type("MockState", (), {"state": None, "attributes": {"value": None}})()

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

            # Create sensor set and load deep attribute resolution YAML
            sensor_set_id = "deep_attribute_resolution_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="attr_resolution_device", name="Deep Attribute Resolution Test"
            )

            yaml_fixture_path = (
                Path(__file__).parent.parent / "fixtures" / "integration" / "deep_entity_attribute_resolution.yaml"
            )
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4

            # Set up sensor manager to test attribute resolution
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="attr_resolution_device",
            )

            assert sensor_manager is not None
            await sensor_manager.async_update_sensors()

            # Verify sensors were created successfully
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 4

            # Verify deep nested attribute chains sensor
            nested_sensor = next((s for s in sensors if s.unique_id == "deep_nested_attribute_chains"), None)
            assert nested_sensor is not None
            assert len(nested_sensor.formulas) == 4  # Main + 3 attributes

            # Verify missing entity handling sensor
            missing_sensor = next((s for s in sensors if s.unique_id == "missing_entity_attribute_handling"), None)
            assert missing_sensor is not None
            assert len(missing_sensor.formulas) == 4  # Main + 3 attributes

            # Verify edge cases sensor
            edge_cases_sensor = next((s for s in sensors if s.unique_id == "attribute_resolution_edge_cases"), None)
            assert edge_cases_sensor is not None
            assert len(edge_cases_sensor.formulas) == 5  # Main + 4 attributes

            # Verify value extraction sensor
            value_extraction_sensor = next((s for s in sensors if s.unique_id == "value_extraction_complex_objects"), None)
            assert value_extraction_sensor is not None
            assert len(value_extraction_sensor.formulas) == 4  # Main + 3 attributes

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_variable_resolver_context_strategies_coverage(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test variable resolver context strategies to improve variable_resolver.py coverage (55%)."""
        # Set up mock states for variable resolution testing
        mock_states["sensor.context_dependent_source"] = type("MockState", (), {"state": "120.0", "attributes": {}})()
        mock_states["sensor.integration_priority_source"] = type("MockState", (), {"state": "80.0", "attributes": {}})()
        mock_states["sensor.primary_context_source"] = type("MockState", (), {"state": "40.0", "attributes": {}})()
        mock_states["sensor.secondary_context_source"] = type("MockState", (), {"state": "30.0", "attributes": {}})()
        mock_states["sensor.tertiary_context_source"] = type("MockState", (), {"state": "20.0", "attributes": {}})()
        mock_states["sensor.integration_source"] = type("MockState", (), {"state": "100.0", "attributes": {}})()
        mock_states["sensor.local_override_source"] = type("MockState", (), {"state": "90.0", "attributes": {}})()
        mock_states["sensor.global_fallback_source"] = type("MockState", (), {"state": "70.0", "attributes": {}})()

        # Resolution chain states
        mock_states["sensor.resolution_chain_start"] = type("MockState", (), {"state": "10.0", "attributes": {}})()
        mock_states["sensor.resolution_chain_middle"] = type("MockState", (), {"state": "20.0", "attributes": {}})()
        mock_states["sensor.resolution_chain_end"] = type("MockState", (), {"state": "30.0", "attributes": {}})()

        # Dependency states
        for dep in ["a", "b", "c"]:
            mock_states[f"sensor.dependency_{dep}"] = type(
                "MockState", (), {"state": f"{ord(dep) - ord('a') + 1}0.0", "attributes": {}}
            )()

        # Factory integration states
        mock_states["sensor.factory_created_resolver"] = type("MockState", (), {"state": "150.0", "attributes": {}})()
        mock_states["sensor.factory_managed_source"] = type("MockState", (), {"state": "125.0", "attributes": {}})()
        mock_states["sensor.factory_cached_source"] = type("MockState", (), {"state": "175.0", "attributes": {}})()

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

            # Create sensor set and load variable resolver context strategies YAML
            sensor_set_id = "variable_resolver_context_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="variable_resolver_device", name="Variable Resolver Context Test"
            )

            yaml_fixture_path = (
                Path(__file__).parent.parent / "fixtures" / "integration" / "variable_resolver_context_strategies.yaml"
            )
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4

            # Set up sensor manager to test variable resolution
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="variable_resolver_device",
            )

            assert sensor_manager is not None
            await sensor_manager.async_update_sensors()

            # Verify sensors were created successfully
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 4

            # Verify context resolution strategies sensor
            context_sensor = next((s for s in sensors if s.unique_id == "context_resolution_strategies"), None)
            assert context_sensor is not None
            assert len(context_sensor.formulas) == 4  # Main + 3 attributes

            # Verify variable resolution chains sensor
            chains_sensor = next((s for s in sensors if s.unique_id == "variable_resolution_chains"), None)
            assert chains_sensor is not None
            assert len(chains_sensor.formulas) == 4  # Main + 3 attributes

            # Verify variable type resolution sensor
        type_sensor = next((s for s in sensors if s.unique_id == "variable_type_resolution"), None)
        assert type_sensor is not None
        assert len(type_sensor.formulas) == 4  # Main + 3 attributes (restored mixed_type_handling)

        # Verify resolver factory integration sensor
        factory_sensor = next((s for s in sensors if s.unique_id == "resolver_factory_integration"), None)
        assert factory_sensor is not None
        assert len(factory_sensor.formulas) == 4  # Main + 3 attributes

        # Cleanup
        if storage_manager.sensor_set_exists(sensor_set_id):
            await storage_manager.async_delete_sensor_set(sensor_set_id)
