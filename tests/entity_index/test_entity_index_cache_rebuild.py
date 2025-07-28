"""Test entity ID cache rebuild after HA registration process."""

import pytest
from unittest.mock import AsyncMock, patch

from ha_synthetic_sensors.storage_manager import StorageManager


class TestEntityIndexCacheRebuild:
    """Test that entity ID caches are properly rebuilt with HA-assigned entity IDs."""

    @pytest.fixture
    def entity_cache_test_yaml(self):
        """Load the entity cache test YAML content."""
        with open("tests/yaml_fixtures/entity_index_cache/entity_cache_test.yaml", "r", encoding="utf-8") as f:
            return f.read()

    @pytest.fixture
    def cross_sensor_cache_test_yaml(self):
        """Load the cross-sensor cache test YAML content."""
        with open("tests/yaml_fixtures/entity_index_cache/cross_sensor_cache_test.yaml", "r", encoding="utf-8") as f:
            return f.read()

    async def test_entity_index_reflects_ha_assigned_entity_ids(
        self, mock_hass, mock_entity_registry, mock_states, entity_cache_test_yaml
    ):
        """Test that entity index contains HA-assigned entity IDs, not original ones."""

        # Load test YAML with entity ID that will cause collision
        test_yaml = entity_cache_test_yaml

        # Create storage manager with mocked Store
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "entity_cache_test"
            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import YAML - this should register with HA and update entity IDs
            result = await storage_manager.async_from_yaml(yaml_content=test_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 1
            assert len(result["sensor_unique_ids"]) == 1

            # Get the sensor set and check entity index
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)
            entity_index_stats = sensor_set.get_entity_index_stats()

            print(f"📊 Entity index stats: {entity_index_stats}")

            # Get the stored sensor to see what entity_id was actually assigned
            sensors = sensor_set.list_sensors()
            stored_sensor = sensors[0]

            print(f"📋 Original entity_id from YAML: sensor.original_entity_id")
            print(f"📋 HA-assigned entity_id: {stored_sensor.entity_id}")
            print(f"📋 Entity index contains HA-assigned ID: {sensor_set.is_entity_tracked(stored_sensor.entity_id)}")
            print(f"📋 Entity index contains original ID: {sensor_set.is_entity_tracked('sensor.original_entity_id')}")

            # CRITICAL TEST: Entity index should contain HA-assigned entity ID, not original
            assert sensor_set.is_entity_tracked(stored_sensor.entity_id), (
                f"Entity index should contain HA-assigned entity ID: {stored_sensor.entity_id}"
            )

            # CRITICAL TEST: Entity index should NOT contain original entity ID if they're different
            if stored_sensor.entity_id != "sensor.original_entity_id":
                assert not sensor_set.is_entity_tracked("sensor.original_entity_id"), (
                    f"Entity index should NOT contain original entity ID: sensor.original_entity_id"
                )
                print("✅ Entity index correctly contains HA-assigned ID, not original ID")
            else:
                print("ℹ️  HA-assigned entity ID matches original (no collision)")

            # Test that variables in formulas also use HA-assigned entity IDs in the index
            assert sensor_set.is_entity_tracked("sensor.some_other_sensor"), (
                "Entity index should contain entity IDs from variables"
            )

            # Cleanup
            await storage_manager.async_delete_sensor_set(sensor_set_id)
            print("🧹 Cleaned up test sensor set")

    async def test_entity_index_updated_after_cross_sensor_resolution(
        self, mock_hass, mock_entity_registry, mock_states, cross_sensor_cache_test_yaml
    ):
        """Test that entity index is updated after cross-sensor reference resolution."""

        # Load test YAML with cross-sensor references that will be resolved
        test_yaml = cross_sensor_cache_test_yaml

        # Create storage manager
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "cross_sensor_cache_test"
            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import YAML with cross-sensor references
            result = await storage_manager.async_from_yaml(yaml_content=test_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 2
            assert len(result["sensor_unique_ids"]) == 2

            # Get sensors and check their resolved entity IDs
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)
            sensors = sensor_set.list_sensors()

            base_sensor = next(s for s in sensors if s.unique_id == "base_sensor_cache")
            derived_sensor = next(s for s in sensors if s.unique_id == "derived_sensor_cache")

            print(f"📋 Base sensor entity_id: {base_sensor.entity_id}")
            print(f"📋 Derived sensor entity_id: {derived_sensor.entity_id}")

            # Entity index should contain both HA-assigned entity IDs
            assert sensor_set.is_entity_tracked(base_sensor.entity_id), (
                f"Entity index should contain base sensor entity ID: {base_sensor.entity_id}"
            )
            assert sensor_set.is_entity_tracked(derived_sensor.entity_id), (
                f"Entity index should contain derived sensor entity ID: {derived_sensor.entity_id}"
            )

            # Check that variables were resolved correctly
            derived_formula = derived_sensor.formulas[0]
            other_sensor_var = derived_formula.variables.get("other_sensor")

            print(f"📋 Cross-sensor variable 'other_sensor': {other_sensor_var}")

            # The cross-sensor variable should reference the HA-assigned entity ID
            assert other_sensor_var == base_sensor.entity_id, (
                f"Cross-sensor variable should reference HA-assigned entity ID: {base_sensor.entity_id}, got: {other_sensor_var}"
            )

            # Self-reference should be resolved to 'state'
            base_formula = base_sensor.formulas[0]
            self_ref_var = base_formula.variables.get("self_ref")

            print(f"📋 Self-reference variable 'self_ref': {self_ref_var}")

            assert self_ref_var == "state", f"Self-reference variable should be 'state', got: {self_ref_var}"

            # Cleanup
            await storage_manager.async_delete_sensor_set(sensor_set_id)
            print("🧹 Cleaned up test sensor set")

            print("✅ Entity index correctly updated after cross-sensor reference resolution!")
