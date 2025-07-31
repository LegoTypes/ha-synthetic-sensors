"""Integration tests for variable resolution functionality using public API."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

# Use public API imports as shown in integration guide
from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager, DataProviderCallback


class TestVariableResolutionIntegration:
    """Integration tests for variable resolution through the public API."""

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

    def create_data_provider_callback(self, backing_data: dict[str, any]) -> DataProviderCallback:
        """Create a data provider callback for testing with virtual backing entities."""

        def data_provider(entity_id: str):
            """Provide test data for virtual backing entities."""
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    async def test_variable_inheritance_and_precedence(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test variable inheritance from global settings and attribute-level precedence."""
        # Set up virtual backing entity data
        backing_data = {"sensor.virtual_base": 1000.0}

        # Set up mock HA states for external entities
        mock_states["sensor.global_base_power"] = type("MockState", (), {"state": "500.0", "attributes": {}})()

        data_provider = self.create_data_provider_callback(backing_data)

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

            # Create sensor set and load complex variable resolution YAML
            sensor_set_id = "variable_resolution_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Variable Resolution Test"
            )

            yaml_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "variable_resolution_complex.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3

            # Create sensor-to-backing mapping for virtual entity
            sensor_to_backing_mapping = {"self_reference_sensor": "sensor.virtual_base"}

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass

            # Set up sensor manager to test variable resolution
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test variable resolution through evaluation
            await sensor_manager.async_update_sensors_for_entities({"sensor.virtual_base"})
            await sensor_manager.async_update_sensors()

            # Verify sensors with complex variable resolution were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Verify variable inheritance sensor exists
            inheritance_sensor = next((s for s in sensors if s.unique_id == "variable_inheritance_sensor"), None)
            assert inheritance_sensor is not None
            assert len(inheritance_sensor.formulas) >= 3  # Main formula + 2 attributes

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_entity_attribute_access_resolution(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test entity attribute access in variable resolution."""
        # Set up mock HA states with attributes for entity attribute access
        mock_states["sensor.battery_device"] = type("MockState", (), {"state": "85.0", "attributes": {"battery_level": 75.0}})()
        mock_states["sensor.current_meter"] = type("MockState", (), {"state": "5.0", "attributes": {"current": 5.0}})()
        mock_states["sensor.voltage_meter"] = type("MockState", (), {"state": "240.0", "attributes": {"voltage": 240.0}})()
        mock_states["sensor.global_base_power"] = type("MockState", (), {"state": "500.0", "attributes": {}})()

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

            # Create sensor set and load variable resolution YAML
            sensor_set_id = "entity_attribute_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Entity Attribute Test"
            )

            yaml_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "variable_resolution_complex.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3

            # Set up sensor manager with entity attribute access
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test entity attribute resolution through evaluation
            await sensor_manager.async_update_sensors()

            # Verify entity attribute access sensor was created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            attribute_sensor = next((s for s in sensors if s.unique_id == "entity_attribute_access"), None)
            assert attribute_sensor is not None

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_variable_conflict_resolution_edge_cases(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test edge cases in variable conflict resolution and inheritance."""
        # Set up mock HA states for external entities
        mock_states["sensor.base_value"] = type("MockState", (), {"state": "100.0", "attributes": {}})()

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

            # Create sensor set and load edge cases YAML
            sensor_set_id = "variable_edge_cases_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Variable Edge Cases Test"
            )

            yaml_fixture_path = (
                Path(__file__).parent.parent / "fixtures" / "integration" / "variable_resolution_edge_cases.yaml"
            )
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3

            # Set up sensor manager for edge case testing
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test variable conflict resolution through evaluation
            await sensor_manager.async_update_sensors()

            # Verify edge case sensors were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Verify variable precedence resolution sensor
            precedence_sensor = next((s for s in sensors if s.unique_id == "variable_precedence_resolution"), None)
            assert precedence_sensor is not None
            assert len(precedence_sensor.formulas) >= 3  # Main formula + 2 attributes

            # Verify numeric literal variables sensor
            numeric_sensor = next((s for s in sensors if s.unique_id == "numeric_literal_variables"), None)
            assert numeric_sensor is not None

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_type_analysis_with_variable_resolution(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test type analysis and conversion with variable resolution."""
        # Set up mock HA states for different data types
        mock_states["binary_sensor.test_switch"] = type(
            "MockState",
            (),
            {
                "state": "on",  # Boolean state that converts to 1.0
                "attributes": {},
            },
        )()
        mock_states["sensor.numeric_string"] = type(
            "MockState",
            (),
            {
                "state": "123.45",  # String that should be parsed as numeric
                "attributes": {},
            },
        )()

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

            # Create sensor set and load type analysis YAML
            sensor_set_id = "type_analysis_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Type Analysis Test"
            )

            yaml_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "type_analysis_variables.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 2

            # Set up sensor manager for type analysis testing
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test type analysis through evaluation
            await sensor_manager.async_update_sensors()

            # Verify type analysis sensors were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 2

            # Verify type analysis sensor
            type_sensor = next((s for s in sensors if s.unique_id == "type_analysis_sensor"), None)
            assert type_sensor is not None
            assert len(type_sensor.formulas) >= 3  # Main formula + 2 attributes

            # Verify complex type resolution sensor
            complex_type_sensor = next((s for s in sensors if s.unique_id == "complex_type_resolution"), None)
            assert complex_type_sensor is not None
            assert len(complex_type_sensor.formulas) >= 3  # Main formula + 2 attributes

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
