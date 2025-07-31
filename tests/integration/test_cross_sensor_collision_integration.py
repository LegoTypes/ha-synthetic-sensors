"""Integration tests for cross-sensor collision handling using public API."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
import yaml

from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager, DataProviderCallback


class TestCrossSensorCollisionIntegration:
    """Integration tests for cross-sensor collision handling through public API."""

    @pytest.fixture
    def clean_entity_registry(self):
        """Create a clean entity registry for collision tests without pre-populated entities."""
        mock_entities = {}

        class CleanMockEntityRegistry:
            def __init__(self):
                self._entities = mock_entities
                self.entities = mock_entities

            async def async_get_or_create(self, domain, platform, unique_id, suggested_object_id=None, **kwargs):
                """Mock async_get_or_create that handles collision detection."""
                base_entity_id = f"{domain}.{suggested_object_id or unique_id}"
                entity_id = base_entity_id
                counter = 1

                # Handle collision by incrementing suffix
                while entity_id in self._entities:
                    counter += 1
                    entity_id = f"{base_entity_id}_{counter}"

                # Create mock entity entry
                mock_entry = Mock()
                mock_entry.entity_id = entity_id
                mock_entry.unique_id = unique_id
                mock_entry.domain = domain
                mock_entry.platform = platform

                # Store entity
                self._entities[entity_id] = mock_entry
                return mock_entry

            def async_get(self, entity_id):
                """Get entity by entity_id."""
                return self._entities.get(entity_id)

        return CleanMockEntityRegistry()

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback."""
        return Mock()

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        return mock_device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    def create_data_provider_callback(self, backing_data: dict[str, any]) -> DataProviderCallback:
        """Create data provider for virtual backing entities."""

        def data_provider(entity_id: str):
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    async def test_cross_sensor_collision_resolution_integration(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test cross-sensor reference resolution with collision handling using public API."""

        # Set up virtual backing entity data
        backing_data = {"sensor.span_panel_instantaneous_power": 1000.0, "sensor.circuit_a_power": 500.0}

        # Create data provider for virtual backing entities
        data_provider = self.create_data_provider_callback(backing_data)

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

            # Create sensor set
            sensor_set_id = "cross_sensor_collision_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Cross Sensor Collision Test"
            )

            # Load YAML that may cause entity collisions
            yaml_fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "integration_test_cross_sensor_collisions.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3

            # Set up synthetic sensors via public API
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test cross-sensor resolution and collision handling
            await sensor_manager.async_update_sensors()

            # Verify sensors were created and cross-references resolved
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Find the combined power sensor to verify cross-sensor resolution
            combined_sensor = next((s for s in sensors if s.unique_id == "combined_power"), None)
            assert combined_sensor is not None, "Combined power sensor should exist"

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_duplicate_sensor_collision_handling_integration(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test duplicate sensor collision handling through public API."""

        # Set up backing data
        backing_data = {"sensor.circuit_a_power": 750.0, "sensor.kitchen_temperature": 22.0}

        data_provider = self.create_data_provider_callback(backing_data)

        def change_notifier_callback(changed_entity_ids: set[str]) -> None:
            pass

        # Pre-register an entity to cause collision
        mock_entity_registry.register_entity("sensor.duplicate_sensor", "duplicate_sensor", "sensor")

        # Set up storage manager
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

            # Create sensor set
            sensor_set_id = "duplicate_collision_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Duplicate Collision Test"
            )

            # Load YAML with potential duplicate sensor
            yaml_fixture_path = (
                Path(__file__).parent.parent / "yaml_fixtures" / "integration_test_cross_sensor_duplicate_handling.yaml"
            )
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 2

            # Set up synthetic sensors - should handle collision gracefully
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
            )

            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test that collision was handled and references still work
            await sensor_manager.async_update_sensors()

            # Verify sensors were created with proper collision handling
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 2

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_complex_collision_scenarios(self, mock_hass, mock_entity_registry, mock_states):
        """Test complex collision scenarios with mixed reference types."""
        # Pre-register the collision entity to force collision using common fixtures
        mock_entity_registry.async_get_or_create(
            domain="sensor",
            platform="test_collision",
            unique_id="existing_collision_sensor",
            suggested_object_id="circuit_a_power",  # This creates sensor.circuit_a_power
        )

        # Create storage manager with mocked Store
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load the enhanced YAML fixture
            yaml_fixture_path = (
                Path(__file__).parent.parent / "yaml_fixtures" / "integration_test_cross_sensor_complex_collisions.yaml"
            )
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            # Create sensor set and import YAML
            sensor_set_id = "complex_collision_test"
            await storage_manager.async_create_sensor_set(sensor_set_id)

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 4  # Still 4 sensors, now enhanced with variables
            assert len(result["sensor_unique_ids"]) == 4

            # Export and analyze the results
            exported_yaml = await storage_manager.async_export_yaml(sensor_set_id)

            # Parse and analyze the results
            exported_data = yaml.safe_load(exported_yaml)
            sensors = exported_data["sensors"]
            global_settings = exported_data.get("global_settings", {})

            # Analyze collision sensor (should have self-references replaced with 'state')
            collision_sensor = sensors["collision_test_duplicate_sensor"]

            # Check self-references in main formula
            assert collision_sensor["formula"] == "state * 3", f"Expected 'state * 3', got '{collision_sensor['formula']}'"

            # Check self-references in attributes
            daily_energy = collision_sensor["attributes"]["daily_energy"]["formula"]
            efficiency = collision_sensor["attributes"]["efficiency"]["formula"]
            assert daily_energy == "state * 24", f"Expected 'state * 24', got '{daily_energy}'"
            assert efficiency == "state / 1000", f"Expected 'state / 1000', got '{efficiency}'"

            # Check self-references with attribute access patterns
            self_attr_entity_id = collision_sensor["attributes"]["self_attr_entity_id"]["formula"]
            self_attr_sensor_key = collision_sensor["attributes"]["self_attr_sensor_key"]["formula"]
            nested_self_attr = collision_sensor["attributes"]["nested_self_attr"]["formula"]

            assert self_attr_entity_id == "state.last_changed + 3600", (
                f"Expected 'state.last_changed + 3600', got '{self_attr_entity_id}'"
            )
            assert self_attr_sensor_key == "state.last_updated * 2", (
                f"Expected 'state.last_updated * 2', got '{self_attr_sensor_key}'"
            )
            assert nested_self_attr == "state.attributes.power_factor * 0.9", (
                f"Expected 'state.attributes.power_factor * 0.9', got '{nested_self_attr}'"
            )

            # Analyze cross-reference sensors
            collision_entity_id = collision_sensor["entity_id"]  # The collision-handled entity_id

            # Entity ID reference sensor
            reference_sensor = sensors["collision_test_reference_sensor"]

            # The entity ID reference should be updated to collision-handled entity_id
            assert collision_entity_id in reference_sensor["formula"], (
                f"Expected {collision_entity_id} in formula: {reference_sensor['formula']}"
            )

            # Sensor key reference sensor
            sensor_key_ref_sensor = sensors["collision_test_sensor_key_reference"]

            # The sensor key reference should be resolved to collision-handled entity_id
            assert collision_entity_id in sensor_key_ref_sensor["formula"], (
                f"Expected {collision_entity_id} in formula: {sensor_key_ref_sensor['formula']}"
            )

            # Test mixed reference types in attributes
            power_ratio = reference_sensor["attributes"]["power_ratio"]["formula"]

            # Both sensor key and entity ID references should resolve to same collision-handled entity
            # This should result in something like: sensor.circuit_a_power_2 / sensor.circuit_a_power_2
            # which could be simplified, but at minimum both references should be updated
            reference_count = power_ratio.count(collision_entity_id)
            assert reference_count == 2, f"Expected 2 references to {collision_entity_id} in mixed formula: {power_ratio}"

            # Test cross-reference attribute access patterns
            cross_attr_entity_id = reference_sensor["attributes"]["cross_attr_entity_id"]["formula"]
            cross_attr_mixed = reference_sensor["attributes"]["cross_attr_mixed"]["formula"]

            # Entity ID with attribute should resolve collision and preserve attribute access
            assert collision_entity_id + ".state" in cross_attr_entity_id, (
                f"Expected '{collision_entity_id}.state' in cross_attr_entity_id: {cross_attr_entity_id}"
            )
            assert collision_entity_id + ".last_changed" in cross_attr_entity_id, (
                f"Expected '{collision_entity_id}.last_changed' in cross_attr_entity_id: {cross_attr_entity_id}"
            )

            # Mixed reference with nested attributes should resolve both collision references
            assert collision_entity_id + ".attributes.daily_total" in cross_attr_mixed, (
                f"Expected '{collision_entity_id}.attributes.daily_total' in cross_attr_mixed: {cross_attr_mixed}"
            )
            assert collision_entity_id + ".last_updated" in cross_attr_mixed, (
                f"Expected '{collision_entity_id}.last_updated' in cross_attr_mixed: {cross_attr_mixed}"
            )

            # Test complex attribute patterns in other sensors
            another_ref_sensor = sensors["collision_test_another_reference"]
            complex_cross_attr = another_ref_sensor["attributes"]["complex_cross_attr"]["formula"]

            # Should have collision entity with attribute access
            assert collision_entity_id + ".attributes.power_factor" in complex_cross_attr, (
                f"Expected '{collision_entity_id}.attributes.power_factor' in complex formula: {complex_cross_attr}"
            )
            assert collision_entity_id + ".state" in complex_cross_attr, (
                f"Expected '{collision_entity_id}.state' in complex formula: {complex_cross_attr}"
            )

            # Test nested sensor key attribute patterns
            nested_sensor_key_attr = sensor_key_ref_sensor["attributes"]["nested_sensor_key_attr"]["formula"]
            chained_attr_access = sensor_key_ref_sensor["attributes"]["chained_attr_access"]["formula"]

            # Sensor key with nested attributes should resolve to collision entity
            assert collision_entity_id + ".attributes.efficiency.value" in nested_sensor_key_attr, (
                f"Expected '{collision_entity_id}.attributes.efficiency.value' in nested formula: {nested_sensor_key_attr}"
            )

            # Multiple attribute accesses on same sensor key should resolve consistently
            last_changed_count = chained_attr_access.count(collision_entity_id + ".last_changed")
            last_updated_count = chained_attr_access.count(collision_entity_id + ".last_updated")
            assert last_changed_count == 1, (
                f"Expected 1 occurrence of '.last_changed' in chained formula: {chained_attr_access}"
            )
            assert last_updated_count == 1, (
                f"Expected 1 occurrence of '.last_updated' in chained formula: {chained_attr_access}"
            )

            # Test global variable collision handling
            global_variables = global_settings.get("variables", {})
            global_collision_ref_entity_id = global_variables.get("global_collision_ref_entity_id")
            global_collision_ref_sensor_key = global_variables.get("global_collision_ref_sensor_key")

            # The global variable should be updated to point to the collision-handled entity
            collision_entity_id = collision_sensor["entity_id"]  # This should be sensor.circuit_a_power_2

            # Test global variable referencing collision entity by entity_id
            assert global_collision_ref_entity_id == collision_entity_id, (
                f"Global variable should be updated from 'sensor.circuit_a_power' to '{collision_entity_id}'"
            )

            # Test global variable referencing collision sensor by sensor key
            assert global_collision_ref_sensor_key == collision_entity_id, (
                f"Global variable should be updated from 'collision_test_duplicate_sensor' to '{collision_entity_id}'"
            )

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

            # No need for manual registry cleanup with clean_entity_registry fixture
            # Each test gets a fresh registry automatically
