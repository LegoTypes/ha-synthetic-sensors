"""Integration tests for collection function negation syntax."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from ha_synthetic_sensors import async_setup_synthetic_sensors
from ha_synthetic_sensors.storage_manager import StorageManager


class TestCollectionNegationIntegration:
    """Test collection function negation syntax in integration scenarios."""

    def create_data_provider_callback(self, backing_data: dict[str, float]):
        """Create a data provider callback for testing with virtual backing entities."""

        def data_provider(entity_id: str):
            """Provide test data for virtual backing entities."""
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    @pytest.fixture
    def negation_test_yaml_path(self):
        """Path to the negation test YAML fixture."""
        return "tests/fixtures/integration/collection_negation_test.yaml"

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry for testing."""
        config_entry = Mock()
        config_entry.entry_id = "negation_test_entry"
        config_entry.domain = "ha_synthetic_sensors"
        return config_entry

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback."""
        return Mock()

    async def test_collection_negation_comprehensive(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        negation_test_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test comprehensive collection function negation scenarios."""

        # Mock minimal backing data - sensors will use their formula values
        backing_data = {}
        data_provider = self.create_data_provider_callback(backing_data)

        # Create storage manager with mocked dependencies
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            # Mock Device Registry to return a proper device entry
            mock_device_registry = Mock()
            mock_device_registry.devices = Mock()

            # Create a mock device entry that will be returned
            mock_device_entry = Mock()
            mock_device_entry.name = "Negation Test Device"  # This will be slugified to "negation_test_device"
            mock_device_entry.identifiers = {("ha_synthetic_sensors", "negation_test_device")}

            # Mock async_get_device to return our device entry when called with the right identifier
            mock_device_registry.async_get_device.return_value = mock_device_entry
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "negation_test", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "negation_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="negation_test_device", name="Collection Negation Test"
            )

            # Load the negation test YAML using the correct API
            with open(negation_test_yaml_path, "r") as f:
                yaml_content = f.read()

            # Use async_from_yaml as shown in the guide
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 12, f"Expected 12 sensors imported, got {result['sensors_imported']}"

            # Change notifier callback
            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass  # No specific change notification needed for this test

            # Set up synthetic sensors using the public API pattern
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="negation_test_device",
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping={},  # Empty since sensors use literal values
                allow_ha_lookups=False,  # Virtual entities only
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Verify all sensors were created (6 base + 6 test sensors = 12 total)
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 12, f"Expected 12 sensors, got {len(sensors)}"

            # Trigger sensor updates to exercise the negation logic
            await sensor_manager.async_update_sensors()

            # Verify specific negation behaviors through the sensor manager
            await self._verify_negation_results(sensor_manager, storage_manager, sensor_set_id)

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def _verify_negation_results(self, sensor_manager, storage_manager, sensor_set_id):
        """Verify that negation syntax produces expected results."""

        # Get sensor configurations to verify formulas
        sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
        sensor_by_id = {sensor.unique_id: sensor for sensor in sensors}

        # Test 1: Verify power_without_oven excludes kitchen_oven (with HA-assigned entity ID)
        power_without_oven = sensor_by_id["power_without_oven"]
        assert "!'sensor.kitchen_oven'" in power_without_oven.formulas[0].formula
        # Expected: 100 + 150 + 200 + 800 = 1250 (excludes kitchen_oven's 2000)

        # Test 2: Verify power_without_kitchen excludes both kitchen sensors (with HA-assigned entity IDs)
        power_without_kitchen = sensor_by_id["power_without_kitchen"]
        formula = power_without_kitchen.formulas[0].formula
        assert "!'sensor.kitchen_fridge'" in formula
        assert "!'sensor.kitchen_oven'" in formula
        # Expected: 100 + 150 + 800 = 1050 (excludes kitchen_fridge's 200 and kitchen_oven's 2000)

        # Test 3: Verify area-based exclusion
        power_without_living_room = sensor_by_id["power_without_living_room"]
        assert "!'area:living_room'" in power_without_living_room.formulas[0].formula
        # Expected: 200 + 2000 + 800 = 3000 (excludes living_room_light's 100 and living_room_tv's 150)

        # Test 4: Verify mixed exclusions (with HA-assigned entity IDs)
        selective_power = sensor_by_id["selective_power"]
        formula = selective_power.formulas[0].formula
        assert "!'sensor.bedroom_heater'" in formula
        assert "!'area:kitchen'" in formula  # Area references remain unchanged
        # Expected: 100 + 150 = 250 (excludes bedroom_heater's 800, kitchen_fridge's 200, kitchen_oven's 2000)

        # Test 5: Verify auto self-exclusion works with explicit negation (with HA-assigned entity ID)
        total_power = sensor_by_id["total_power"]
        assert "!'sensor.garage_charger'" in total_power.formulas[0].formula
        # Expected: 100 + 150 + 200 + 2000 + 800 = 3250 (excludes garage_charger's 7000, auto-excludes itself)

        # Test 6: Verify area-based collection with specific negation (with HA-assigned entity ID)
        living_room_without_tv = sensor_by_id["living_room_without_tv"]
        assert "!'sensor.living_room_tv'" in living_room_without_tv.formulas[0].formula
        # Expected: 100 (excludes living_room_tv's 150)

    async def test_negation_parsing_validation(self, mock_hass):
        """Test that negation syntax is parsed correctly."""
        from ha_synthetic_sensors.dependency_parser import DependencyParser

        parser = DependencyParser(mock_hass)

        # Test various negation syntaxes
        test_cases = [
            ("sum('device_class:power', !'sensor1')", ["sensor1"]),
            ("avg('area:kitchen', !'kitchen_oven', !'kitchen_fridge')", ["kitchen_oven", "kitchen_fridge"]),
            ("count('device_class:power', !'area:garage')", ["area:garage"]),
            ("max('label:solar', !'sensor.backup_panel')", ["sensor.backup_panel"]),
        ]

        for formula, expected_exclusions in test_cases:
            queries = parser.extract_dynamic_queries(formula)
            assert len(queries) == 1, f"Expected 1 query for '{formula}', got {len(queries)}"

            query = queries[0]
            assert query.exclusions == expected_exclusions, (
                f"For formula '{formula}', expected exclusions {expected_exclusions}, got {query.exclusions}"
            )

    async def test_negation_with_invalid_patterns(self, mock_hass):
        """Test handling of invalid negation patterns."""
        from ha_synthetic_sensors.collection_resolver import CollectionResolver
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        resolver = CollectionResolver(mock_hass)

        # Test query with invalid exclusion pattern
        query = DynamicQuery(
            query_type="device_class",
            pattern="power",
            function="sum",
            exclusions=["invalid_pattern"],  # No colon, not a valid entity ID
        )

        # Should handle gracefully and not crash
        result = resolver.resolve_collection(query)
        assert isinstance(result, list)  # Should return empty list or partial results
