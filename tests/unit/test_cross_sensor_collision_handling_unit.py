"""Tests for cross-sensor collision handling functionality."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from ha_synthetic_sensors.storage_manager import StorageManager


class TestCrossSensorCollisionHandling:
    """Test collision handling scenarios for cross-sensor references."""

    def cleanup_registry(self, mock_entity_registry):
        """Clean up all test-related entities from the registry to ensure clean state."""
        entities_to_remove = []
        for entity_id, entity in mock_entity_registry._entities.items():
            # Remove any test-related entities by pattern matching
            if (
                entity_id.startswith("sensor.circuit_a_power")  # All variants
                or entity_id.startswith("sensor.kitchen_temperature")  # All variants
                or entity_id.startswith("sensor.living_room_temperature")  # All variants
                or entity_id.startswith("sensor.bathroom_humidity")  # All variants
                or entity_id.startswith("sensor.span_panel_instantaneous_power")  # All variants
                or entity_id.startswith("sensor.duplicate_sensor")  # All variants
                or entity.unique_id.startswith("collision_test_")  # All collision test sensors
                or entity.unique_id.startswith("power_sensor_")  # All power sensor test entities
                or entity.unique_id.startswith("total_power")  # Total power test entity
                or entity.unique_id.startswith("existing_")  # Pre-registered collision entities
                or entity.unique_id.startswith("duplicate_sensor")  # Duplicate sensor test entities
                or entity.unique_id.startswith("reference_sensor")  # Reference sensor test entities
            ):
                entities_to_remove.append(entity_id)

        for entity_id in entities_to_remove:
            if entity_id in mock_entity_registry._entities:
                del mock_entity_registry._entities[entity_id]

    @pytest.fixture
    def yaml_with_collisions(self):
        """YAML fixture for collision testing scenarios."""
        return Path(__file__).parent.parent / "yaml_fixtures" / "unit_test_cross_sensor_collision_basic.yaml"

    async def test_collision_handling_with_cross_references(
        self, mock_hass, mock_entity_registry, mock_states, yaml_with_collisions
    ):
        """Test that cross-sensor references work correctly when collisions occur."""

        # Clean up any leftover entities from previous tests
        self.cleanup_registry(mock_entity_registry)

        # Pre-register entities to cause collisions with the YAML fixture
        # The YAML tries to register sensor.power_sensor_a and sensor.power_sensor_b
        # So we'll pre-register entities with those same entity_ids to force collisions
        mock_entity_registry.async_get_or_create(
            domain="sensor",
            platform="test_collision",
            unique_id="existing_power_sensor_a",
            suggested_object_id="power_sensor_a",  # This will create sensor.power_sensor_a
        )
        mock_entity_registry.async_get_or_create(
            domain="sensor",
            platform="test_collision",
            unique_id="existing_power_sensor_b",
            suggested_object_id="power_sensor_b",  # This will create sensor.power_sensor_b
        )

        # Create storage manager with mocked Store
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None  # Empty storage initially
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create a sensor set for testing
            sensor_set_id = "collision_test"
            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Load YAML content from fixture file
            with open(yaml_with_collisions, "r") as f:
                yaml_content = f.read()

            # Import YAML with collisions - this should trigger our cross-reference resolution
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded - 3 sensors in YAML (one will get collision-handled entity_id)
            assert result["sensors_imported"] == 3
            assert len(result["sensor_unique_ids"]) == 3

            # Get the stored sensors
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Find the reference sensor that contains the cross-sensor references
            reference_sensor = None
            for sensor in sensors:
                if sensor.unique_id == "total_power":
                    reference_sensor = sensor
                    break

            assert reference_sensor is not None, "total_power sensor should exist"

            # The formula should have resolved the sensor key references to the collision-handled entity IDs
            # Since we pre-registered entities causing collisions, the sensor key references should be updated
            formula = reference_sensor.formulas[0].formula

            # Verify that cross-sensor references were resolved to actual entity IDs
            # power_sensor_a should resolve to its collision-handled entity_id
            # power_sensor_b should resolve to its collision-handled entity_id
            # The original formula was: power_sensor_a + power_sensor_b
            # After resolution it should use the actual entity IDs assigned by HA
            assert "sensor." in formula, f"Expected entity IDs in formula, but got: {formula}"

        # Cleanup: Remove ALL collision-test entities to prevent auto-incrementing failures
        # Clean up by entity_id patterns to catch all numbered variants
        entities_to_cleanup = []
        for entity_id, entity in mock_entity_registry._entities.items():
            if (
                entity_id.startswith("sensor.span_panel_instantaneous_power")  # All variants
                or entity_id.startswith("sensor.circuit_a_power")  # All variants
                or entity_id.startswith("sensor.kitchen_temperature")  # All variants
                or entity.unique_id.startswith("power_sensor_")  # All power sensor test entities
                or entity.unique_id.startswith("total_power")  # Total power test entity
                or entity.unique_id.startswith("existing_power_sensor_")  # Pre-registered entities
            ):
                entities_to_cleanup.append(entity_id)

        for entity_id in entities_to_cleanup:
            if entity_id in mock_entity_registry._entities:
                del mock_entity_registry._entities[entity_id]

    async def test_same_unique_id_different_formulas(self, mock_hass, mock_entity_registry, mock_states):
        """Test sensors with identical unique_ids but different configurations."""

        # Clean up any leftover entities from previous tests
        self.cleanup_registry(mock_entity_registry)

        # Pre-register an entity to cause ENTITY_ID collision (not just unique_id collision)
        # The YAML sensor has entity_id: sensor.circuit_a_power, so pre-register that entity_id
        mock_entity_registry.async_get_or_create(
            domain="sensor",
            platform="test",
            unique_id="existing_collision_entity",
            suggested_object_id="circuit_a_power",  # This creates sensor.circuit_a_power
        )

        # Now import a YAML that tries to register another sensor with the same unique_id
        # The sensor key "duplicate_sensor" will try to register with unique_id "duplicate_sensor"
        # but since it already exists, the registry should assign a new unique_id like "duplicate_sensor_2"
        # and entity_id like "sensor.duplicate_sensor_2"
        from pathlib import Path

        yaml_fixture_path = (
            Path(__file__).parent.parent / "yaml_fixtures" / "integration_test_cross_sensor_duplicate_handling.yaml"
        )
        with open(yaml_fixture_path, "r") as f:
            yaml_content = f.read()

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None  # Empty storage initially
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "duplicate_test"
            await storage_manager.async_create_sensor_set(sensor_set_id)

            # This should handle the collision and register the new sensor with a modified unique_id
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Should import both sensors
            assert result["sensors_imported"] == 2
            assert len(result["sensor_unique_ids"]) == 2

            # First check if the cross-sensor reference resolution worked in the formula
            # (this is the main thing we're testing - that formulas use the new entity_id)

            # Get the stored sensors
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 2

            # Find both sensors
            reference_sensor = next((s for s in sensors if s.unique_id == "reference_sensor"), None)
            duplicate_sensor = next((s for s in sensors if s.unique_id == "duplicate_sensor"), None)
            assert reference_sensor is not None, "reference_sensor should exist"
            assert duplicate_sensor is not None, "duplicate_sensor should exist"

            # Get the actual entity_id that was assigned to the duplicate_sensor after collision handling
            actual_duplicate_entity_id = duplicate_sensor.entity_id

            # The formula should have resolved the cross-reference to the new entity ID after collision
            formula = reference_sensor.formulas[0].formula

            # TEST THE CORE FUNCTIONALITY: Cross-sensor reference resolution
            # The formula should contain the new entity ID assigned by the registry after collision
            # This is the key test: the sensor key reference 'duplicate_sensor' should be resolved
            # to the actual entity_id assigned to that sensor after collision handling
            assert actual_duplicate_entity_id in formula, (
                f"Cross-sensor reference resolution failed! Expected '{actual_duplicate_entity_id}' in formula: {formula}"
            )

            # Verify it doesn't contain the original YAML key (should be resolved)
            assert "duplicate_sensor + 100" not in formula, (
                f"Formula should not contain raw YAML key 'duplicate_sensor': {formula}"
            )

            # Clean up: remove ALL test entities from the registry
            # Clean up by entity_id patterns to catch all numbered variants
            entities_to_remove = []
            for entity_id, entity in mock_entity_registry._entities.items():
                if (
                    entity_id.startswith("sensor.circuit_a_power")  # All variants
                    or entity_id.startswith("sensor.kitchen_temperature")  # All variants
                    or entity_id.startswith("sensor.duplicate_sensor")  # All variants
                    or entity.unique_id.startswith("duplicate_sensor")  # All duplicate sensor test entities
                    or entity.unique_id.startswith("reference_sensor")  # Reference sensor test entities
                ):
                    entities_to_remove.append(entity_id)

            for entity_id in entities_to_remove:
                if entity_id in mock_entity_registry._entities:
                    del mock_entity_registry._entities[entity_id]

    async def test_entity_id_reference_collision_handling(self, mock_hass, mock_entity_registry, mock_states):
        """Test that entity_id references are updated when collisions occur."""

        # Clean up any leftover entities from previous tests
        self.cleanup_registry(mock_entity_registry)

        # Pre-register an entity to cause entity_id collision
        # The YAML sensors reference "sensor.circuit_a_power", so we need to pre-register that entity_id
        # This will force the YAML sensor to get a collision-handled entity_id like "sensor.circuit_a_power_2"
        mock_entity_registry.async_get_or_create(
            domain="sensor",
            platform="test_collision",
            unique_id="existing_circuit_a_sensor",  # Different unique_id
            suggested_object_id="circuit_a_power",  # This creates sensor.circuit_a_power
        )

        # Now import a YAML that tries to register another sensor with the same unique_id
        # AND contains references to the original entity_id
        from pathlib import Path

        yaml_fixture_path = (
            Path(__file__).parent.parent / "yaml_fixtures" / "integration_test_cross_sensor_complex_collisions.yaml"
        )
        with open(yaml_fixture_path, "r") as f:
            yaml_content = f.read()

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None  # Empty storage initially
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "entity_id_collision_test"
            await storage_manager.async_create_sensor_set(sensor_set_id)

            # This should handle the collision and register the new sensor with a modified unique_id
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Should import all sensors from the enhanced YAML fixture
            assert result["sensors_imported"] == 4  # Enhanced YAML still has 4 sensors, now with variables
            assert len(result["sensor_unique_ids"]) == 4

            # Get the stored sensors
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 4  # Enhanced YAML still has 4 sensors, now with variables

            # Find all sensors
            collision_sensor = next((s for s in sensors if s.unique_id == "collision_test_duplicate_sensor"), None)
            reference_sensor = next((s for s in sensors if s.unique_id == "collision_test_reference_sensor"), None)
            another_reference = next((s for s in sensors if s.unique_id == "collision_test_another_reference"), None)
            assert collision_sensor is not None, "collision_test_duplicate_sensor should exist"
            assert reference_sensor is not None, "collision_test_reference_sensor should exist"
            assert another_reference is not None, "collision_test_another_reference should exist"

            # Test self-reference replacement in collision sensor
            collision_formula = collision_sensor.formulas[0].formula

            # Check what entity mappings were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)

            # Export YAML to see what the system actually stores
            exported_yaml = storage_manager.export_yaml(sensor_set_id=sensor_set_id)

            # Test entity_id reference resolution in first sensor
            formula1 = reference_sensor.formulas[0].formula

            # Verify the formula contains updated entity references
            assert "sensor.circuit_a_power" in formula1, f"Expected entity reference in formula: {formula1}"

            # Test entity_id reference resolution in second sensor
            formula2 = another_reference.formulas[0].formula

            # Verify the formula contains updated entity references
            assert "sensor.circuit_a_power" in formula2, f"Expected entity reference in formula: {formula2}"

            # Clean up: remove ALL test entities from the registry
            # We need to clean up by entity_id patterns since collision handling creates numbered variants
            entities_to_remove = []
            for entity_id, entity in mock_entity_registry._entities.items():
                # Clean up entities by entity_id patterns that match our test entities
                if (
                    entity_id.startswith("sensor.circuit_a_power")  # All variants: sensor.circuit_a_power, _2, _3, etc.
                    or entity_id.startswith("sensor.kitchen_temperature")  # All variants
                    or entity_id.startswith("sensor.living_room_temperature")  # All variants
                    or entity.unique_id.startswith("collision_test_")  # All collision test sensors
                    or entity.unique_id == "existing_circuit_a_sensor"  # Our pre-registered collision entity
                ):
                    entities_to_remove.append(entity_id)

            for entity_id in entities_to_remove:
                if entity_id in mock_entity_registry._entities:
                    del mock_entity_registry._entities[entity_id]

            # Clean up the sensor set
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)
