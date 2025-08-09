"""Integration tests for variable resolution edge cases targeting variable_resolution_phase.py coverage."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

# Use public API imports as shown in integration guide
from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager, DataProviderCallback


class TestVariableResolutionEdgeCasesIntegration:
    """Integration tests for variable resolution edge cases through the public API."""

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

    async def test_complex_nested_variable_resolution(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test complex nested variable resolution with cross-references and deep nesting."""
        # Set up virtual backing entity data
        backing_data = {"sensor.virtual_nested_base": 1000.0}

        # Set up mock HA states for complex nested resolution
        mock_states["sensor.global_multiplier_entity"] = type("MockState", (), {"state": "2.5", "attributes": {}})()
        mock_states["sensor.dynamic_multiplier"] = type("MockState", (), {"state": "1.8", "attributes": {}})()
        mock_states["sensor.deep_nested_source"] = type("MockState", (), {"state": "500.0", "attributes": {}})()
        mock_states["sensor.external_reference"] = type(
            "MockState", (), {"state": "100.0", "attributes": {"some_attribute": 75.0}}
        )()

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

            # Create sensor set and load advanced variable resolution YAML
            sensor_set_id = "variable_resolution_edge_cases"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Variable Resolution Edge Cases"
            )

            yaml_fixture_path = (
                Path(__file__).parent.parent / "fixtures" / "integration" / "variable_resolution_edge_cases_advanced.yaml"
            )
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 5

            # Create sensor-to-backing mapping for virtual entity
            sensor_to_backing_mapping = {"complex_nested_resolution": "sensor.virtual_nested_base"}

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass

            # Set up sensor manager to test complex variable resolution
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test complex variable resolution through evaluation
            await sensor_manager.async_update_sensors_for_entities({"sensor.virtual_nested_base"})
            await sensor_manager.async_update_sensors()

            # Verify complex nested resolution sensor was created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 5

            # Verify complex nested resolution sensor
            nested_sensor = next((s for s in sensors if s.unique_id == "complex_nested_resolution"), None)
            assert nested_sensor is not None
            assert len(nested_sensor.formulas) >= 3  # Main formula + 2 attributes

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_state_token_context_variations(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test state token usage in different contexts and nested state attribute access."""
        # Set up virtual backing entity data
        backing_data = {"sensor.virtual_state_base": 500.0}

        # Set up mock HA states for state token testing
        mock_states["sensor.external_for_state_access"] = type("MockState", (), {"state": "25.0", "attributes": {}})()
        mock_states["sensor.state_multiplier_source"] = type("MockState", (), {"state": "1.5", "attributes": {}})()
        mock_states["sensor.external_boost_value"] = type("MockState", (), {"state": "10.0", "attributes": {}})()
        mock_states["sensor.base_power_source"] = type("MockState", (), {"state": "200.0", "attributes": {}})()
        mock_states["sensor.theoretical_maximum"] = type("MockState", (), {"state": "1000.0", "attributes": {}})()
        mock_states["sensor.reliable_source"] = type("MockState", (), {"state": "150.0", "attributes": {}})()
        mock_states["sensor.potentially_missing_entity"] = type("MockState", (), {"state": "50.0", "attributes": {}})()
        mock_states["sensor.base_source_a"] = type("MockState", (), {"state": "100.0", "attributes": {}})()
        mock_states["sensor.base_source_b"] = type("MockState", (), {"state": "75.0", "attributes": {}})()
        mock_states["sensor.dynamic_multiplier_b"] = type("MockState", (), {"state": "2.2", "attributes": {}})()
        mock_states["sensor.variable_a_source"] = type("MockState", (), {"state": "30.0", "attributes": {}})()
        mock_states["sensor.variable_c_source"] = type("MockState", (), {"state": "5.0", "attributes": {}})()

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

            # Create sensor set and load state token edge cases YAML
            sensor_set_id = "state_token_edge_cases"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="State Token Edge Cases"
            )

            yaml_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "state_token_edge_cases.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4

            # Create sensor-to-backing mapping for virtual entity
            sensor_to_backing_mapping = {
                "state_token_self_reference": "sensor.virtual_state_base",
                "state_attribute_access_complex": "sensor.virtual_state_base",
                "variable_resolution_errors": "sensor.virtual_state_base",
                "nested_formula_variables": "sensor.virtual_state_base",
            }

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass

            # Set up sensor manager to test state token variations
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test state token context variations through evaluation
            await sensor_manager.async_update_sensors_for_entities({"sensor.virtual_state_base"})
            await sensor_manager.async_update_sensors()

            # Verify state token sensors were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 4

            # Verify state token self reference sensor (the first sensor in the state_token_edge_cases.yaml)
            state_context_sensor = next((s for s in sensors if s.unique_id == "state_token_self_reference"), None)
            assert state_context_sensor is not None
            assert len(state_context_sensor.formulas) >= 4  # Main formula + 3 attributes

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_variable_scope_resolution_conflicts(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test variable scope conflicts and resolution precedence rules."""
        # Set up mock HA states for scope conflict testing
        mock_states["sensor.sensor_level_source"] = type("MockState", (), {"state": "200.0", "attributes": {}})()
        mock_states["sensor.attribute_unique_source"] = type("MockState", (), {"state": "150.0", "attributes": {}})()
        mock_states["sensor.original_source"] = type("MockState", (), {"state": "300.0", "attributes": {}})()
        mock_states["sensor.override_source"] = type("MockState", (), {"state": "50.0", "attributes": {}})()

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

            # Create sensor set and load scope conflict YAML
            sensor_set_id = "scope_conflict_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Scope Conflict Test"
            )

            yaml_fixture_path = (
                Path(__file__).parent.parent / "fixtures" / "integration" / "variable_resolution_edge_cases_advanced.yaml"
            )
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 5

            # Set up sensor manager for scope conflict testing
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test variable scope resolution through evaluation
            await sensor_manager.async_update_sensors()

            # Verify scope conflict sensors were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            scope_sensor = next((s for s in sensors if s.unique_id == "variable_scope_conflicts"), None)
            assert scope_sensor is not None
            assert len(scope_sensor.formulas) >= 3  # Main formula + 2 attributes

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_mixed_variable_types_with_collections(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test mixed variable types including collections, literals, and entity references."""
        # Set up mock entity registry for collection pattern testing
        mock_entity_registry._entities.update(
            {
                "sensor.temp_1": Mock(device_class="temperature"),
                "sensor.temp_2": Mock(device_class="temperature"),
                "sensor.power_1": Mock(device_class="power"),
                "sensor.kitchen_light": Mock(area_id="kitchen"),
            }
        )

        # Set up mock HA states for mixed variable types
        mock_states["sensor.mixed_entity_source"] = type("MockState", (), {"state": "400.0", "attributes": {}})()
        mock_states["binary_sensor.test_boolean_conversion"] = type("MockState", (), {"state": "on", "attributes": {}})()
        mock_states["sensor.string_numeric_source"] = type("MockState", (), {"state": "789.12", "attributes": {}})()
        mock_states["sensor.temp_1"] = type("MockState", (), {"state": "22.5", "attributes": {}})()
        mock_states["sensor.temp_2"] = type("MockState", (), {"state": "24.0", "attributes": {}})()
        mock_states["sensor.power_1"] = type("MockState", (), {"state": "150.0", "attributes": {}})()
        mock_states["sensor.kitchen_light"] = type("MockState", (), {"state": "75.0", "attributes": {}})()

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

            # Create sensor set and load mixed variable types YAML
            sensor_set_id = "mixed_variable_types"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Mixed Variable Types"
            )

            yaml_fixture_path = (
                Path(__file__).parent.parent / "fixtures" / "integration" / "variable_resolution_edge_cases_advanced.yaml"
            )
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 5

            # Set up sensor manager for mixed variable types testing
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test mixed variable types resolution through evaluation
            await sensor_manager.async_update_sensors()

            # Verify mixed variable types sensors were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            mixed_sensor = next((s for s in sensors if s.unique_id == "mixed_variable_types_resolution"), None)
            assert mixed_sensor is not None
            assert len(mixed_sensor.formulas) >= 3  # Main formula + 2 attributes

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_entity_attribute_access_edge_cases(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test entity attribute access edge cases and deep attribute chains."""
        # Set up mock entity registry for collection pattern testing
        mock_entity_registry._entities.update(
            {
                "sensor.power_device_1": Mock(device_class="power", domain="sensor"),
                "sensor.power_device_2": Mock(device_class="power", domain="sensor"),
                "sensor.battery_1": Mock(device_class="battery", domain="sensor"),
                "sensor.battery_2": Mock(device_class="battery", domain="sensor"),
            }
        )

        # Set up mock HA states with complex nested attributes
        mock_states["sensor.battery_device_complex"] = type(
            "MockState", (), {"state": "85.0", "attributes": {"level": 85.0, "voltage": 12.6, "temperature": 22.5}}
        )()
        mock_states["sensor.system_health_monitor"] = type(
            "MockState", (), {"state": "healthy", "attributes": {"health": {"score": 95.0, "weight": 1.2}}}
        )()
        mock_states["sensor.performance_metrics_nested"] = type(
            "MockState", (), {"state": "optimal", "attributes": {"metrics": {"performance": 88.5, "efficiency": 92.0}}}
        )()
        mock_states["sensor.performance_boost"] = type("MockState", (), {"state": "active", "attributes": {"factor": 1.15}})()
        mock_states["sensor.reliable_with_attributes"] = type(
            "MockState", (), {"state": "100.0", "attributes": {"known_attr": 75.0}}
        )()
        mock_states["sensor.entity_with_missing_attrs"] = type(
            "MockState",
            (),
            {
                "state": "50.0",
                "attributes": {},  # Missing the expected attributes
            },
        )()
        mock_states["sensor.backup_value_source"] = type("MockState", (), {"state": "25.0", "attributes": {}})()
        mock_states["sensor.collection_attribute_source"] = type(
            "MockState", (), {"state": "active", "attributes": {"efficiency": 0.85, "performance": 92.0}}
        )()
        mock_states["sensor.dynamic_attributes_entity"] = type(
            "MockState",
            (),
            {
                "state": "running",
                "attributes": {
                    "computed_field": 150.0,
                    "field_a": 10.0,
                    "field_b": 5.0,
                    "status": "active",
                    "active_value": 200.0,
                },
            },
        )()
        mock_states["sensor.runtime_calculation_result"] = type(
            "MockState", (), {"state": "complete", "attributes": {"result": {"value": 125.0, "timestamp": 1640995200}}}
        )()
        mock_states["sensor.always_reliable_entity"] = type(
            "MockState", (), {"state": "stable", "attributes": {"valid_attr": 300.0}}
        )()
        mock_states["sensor.unstable_attribute_entity"] = type(
            "MockState",
            (),
            {
                "state": "unstable",
                "attributes": {"problematic_attr": 75.0},  # Missing nonexistent_attr
            },
        )()
        mock_states["sensor.recovery_value_source"] = type("MockState", (), {"state": "500.0", "attributes": {}})()

        # Collection entities for attribute access
        mock_states["sensor.power_device_1"] = type(
            "MockState", (), {"state": "150.0", "attributes": {"battery_level": 80, "power_rating": 120}}
        )()
        mock_states["sensor.power_device_2"] = type(
            "MockState", (), {"state": "200.0", "attributes": {"battery_level": 45, "power_rating": 150}}
        )()
        mock_states["sensor.battery_1"] = type(
            "MockState", (), {"state": "90.0", "attributes": {"battery_level": 90, "power_rating": 80}}
        )()
        mock_states["sensor.battery_2"] = type(
            "MockState", (), {"state": "60.0", "attributes": {"battery_level": 60, "power_rating": 110}}
        )()

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
            patch("ha_synthetic_sensors.shared_constants.get_ha_domains") as MockGetHADomains,
        ):
            # Mock the get_ha_domains to return proper string domains
            MockGetHADomains.return_value = frozenset(["sensor", "binary_sensor", "light", "switch", "climate"])
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set and load entity attribute access edge cases YAML
            sensor_set_id = "entity_attribute_edge_cases"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Entity Attribute Edge Cases"
            )

            yaml_fixture_path = (
                Path(__file__).parent.parent / "fixtures" / "integration" / "entity_attribute_access_edge_cases.yaml"
            )
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 5

            # Set up sensor manager for entity attribute access testing
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test entity attribute access edge cases through evaluation
            await sensor_manager.async_update_sensors()

            # Verify entity attribute access sensors were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 5

            # Verify deep attribute access chains sensor
            deep_access_sensor = next((s for s in sensors if s.unique_id == "deep_attribute_access_chains"), None)
            assert deep_access_sensor is not None
            assert len(deep_access_sensor.formulas) >= 4  # Main formula + 3 attributes

            # Verify missing attribute handling sensor
            missing_attr_sensor = next((s for s in sensors if s.unique_id == "missing_attribute_handling"), None)
            assert missing_attr_sensor is not None
            assert len(missing_attr_sensor.formulas) >= 3  # Main formula + 2 attributes

            # Verify collection with attribute access sensor
            collection_attr_sensor = next((s for s in sensors if s.unique_id == "collection_with_attribute_access"), None)
            assert collection_attr_sensor is not None
            assert len(collection_attr_sensor.formulas) >= 3  # Main formula + 2 attributes

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
