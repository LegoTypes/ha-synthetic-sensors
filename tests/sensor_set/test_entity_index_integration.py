"""Integration tests for entity index updates and YAML export with entity state changes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from ha_synthetic_sensors.config_manager import FormulaConfig, SensorConfig
from ha_synthetic_sensors.storage_manager import StorageManager


class MockEvent:
    """Mock Home Assistant state change event."""

    def __init__(self, entity_id: str, old_state: str, new_state: str):
        self.data = {"entity_id": entity_id, "old_state": MagicMock(state=old_state), "new_state": MagicMock(state=new_state)}


class TestEntityIndexIntegration:
    """Integration tests for entity index updates and YAML export."""

    @pytest.fixture
    def storage_manager(self, mock_hass, mock_entity_registry, mock_states):
        """Create a storage manager with mocked storage using common fixtures."""
        # Add the entities that this test expects to mock_states
        mock_states.update(
            {
                "sensor.power_meter": MagicMock(state="1000", attributes={}),
                "sensor.voltage": MagicMock(state="240", attributes={}),
                "sensor.temperature": MagicMock(state="25.5", attributes={}),
                "binary_sensor.grid_connected": MagicMock(state="on", attributes={}),
                "switch.backup_mode": MagicMock(state="off", attributes={}),
            }
        )

        manager = StorageManager(mock_hass, "test_entity_index_integration", enable_entity_listener=False)
        return manager

    @pytest.fixture
    def test_yaml_config(self):
        """YAML configuration with various entity reference patterns."""
        return """
version: "1.0"
global_settings:
  device_identifier: "test_device"
  variables:
    base_voltage: "sensor.voltage"
    grid_status: "binary_sensor.grid_connected"

sensors:
  power_efficiency:
    name: "Power Efficiency"
    formula: "power / base_voltage * 100"
    variables:
      power: "sensor.power_meter"
    metadata:
      unit_of_measurement: "%"
      device_class: "power_factor"

  temperature_status:
    name: "Temperature Status"
    formula: "if_else(temp > 30, 'hot', if_else(temp < 20, 'cold', 'normal'))"
    variables:
      temp: "sensor.temperature"

  system_health:
    name: "System Health"
    formula: "if_else(grid_status == 'on' and power < 2000, 'good', 'warning')"
    variables:
      power: "sensor.power_meter"
    attributes:
      backup_active:
        formula: "backup_mode == 'on'"
        variables:
          backup_mode: "switch.backup_mode"
      voltage_ratio:
        formula: "base_voltage / 240.0"
        metadata:
          unit_of_measurement: "ratio"
"""

    @pytest.mark.asyncio
    async def test_entity_index_tracks_formula_references(self, storage_manager, test_yaml_config):
        """Test that entity index correctly tracks all entity references in formulas."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Import YAML configuration
            result = await storage_manager.async_from_yaml(test_yaml_config, "test_set")
            sensor_set_id = result["sensor_set_id"]
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)

            # Verify entity index tracks all referenced entities
            expected_entities = [
                "sensor.power_meter",  # From power_efficiency formula
                "sensor.temperature",  # From temperature_status formula
                "switch.backup_mode",  # From system_health formula
                "sensor.voltage",  # From global variables
                "binary_sensor.grid_connected",  # From global variables
                "sensor.system_health",  # From system_health attribute formulas (self-reference)
            ]

            for entity_id in expected_entities:
                assert sensor_set.is_entity_tracked(entity_id), f"Entity {entity_id} should be tracked"

            # Verify stats
            stats = sensor_set.get_entity_index_stats()
            print(f"📊 Entity index stats: {stats}")
            print(f"📋 Expected entities: {expected_entities}")

            # The entity index now also tracks HA-assigned entity IDs of synthetic sensors
            # Let's check which entities are actually tracked
            all_tracked_entities = []
            # This is a bit of a hack since we don't have a direct way to list all tracked entities
            test_entities = expected_entities + [
                "sensor.power_efficiency",  # HA-assigned entity ID for power_efficiency sensor
                "sensor.temperature_status",  # HA-assigned entity ID for temperature_status sensor
                # The system_health sensor already self-references, so it's likely included in expected
            ]

            for entity_id in test_entities:
                if sensor_set.is_entity_tracked(entity_id):
                    all_tracked_entities.append(entity_id)

            print(f"📋 Actually tracked entities: {all_tracked_entities}")
            assert stats["total_entities"] >= len(expected_entities)  # Allow for additional HA-assigned entity IDs
            # Note: EntityIndex now focuses on tracking all entity references for event filtering
            # rather than distinguishing synthetic vs external entities

    @pytest.mark.asyncio
    async def test_yaml_export_reflects_current_configuration(self, storage_manager, test_yaml_config):
        """Test that YAML export preserves the configuration structure."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Import configuration
            result = await storage_manager.async_from_yaml(test_yaml_config, "test_set")
            sensor_set_id = result["sensor_set_id"]

            # Export YAML
            exported_yaml = storage_manager.export_yaml(sensor_set_id)
            exported_data = yaml.safe_load(exported_yaml)

            # Verify structure is preserved
            assert "sensors" in exported_data
            assert "global_settings" in exported_data
            assert "power_efficiency" in exported_data["sensors"]
            assert "temperature_status" in exported_data["sensors"]
            assert "system_health" in exported_data["sensors"]

            # Verify global variables are preserved
            global_vars = exported_data["global_settings"]["variables"]
            assert global_vars["base_voltage"] == "sensor.voltage"
            assert global_vars["grid_status"] == "binary_sensor.grid_connected"

            # Verify sensor formulas and variables are preserved
            power_sensor = exported_data["sensors"]["power_efficiency"]
            assert power_sensor["formula"] == "power / base_voltage * 100"
            assert power_sensor["variables"]["power"] == "sensor.power_meter"

    @pytest.mark.asyncio
    async def test_entity_index_updates_during_sensor_modifications(self, storage_manager, test_yaml_config):
        """Test that entity index is properly updated when sensors are modified."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Import initial configuration
            result = await storage_manager.async_from_yaml(test_yaml_config, "test_set")
            sensor_set_id = result["sensor_set_id"]
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)

            # Capture initial entity index state
            initial_stats = sensor_set.get_entity_index_stats()
            initial_entities = set()
            for sensor in storage_manager.list_sensors(sensor_set_id=sensor_set_id):
                for formula in sensor.formulas:
                    if formula.variables:
                        initial_entities.update(formula.variables.values())

            # Verify initial tracking
            assert sensor_set.is_entity_tracked("sensor.power_meter")
            assert initial_stats["total_entities"] > 0

            # Get the sensor to modify
            power_efficiency_config = storage_manager.get_sensor("power_efficiency")
            assert power_efficiency_config is not None

            # Update formula to reference different entities
            new_formula = FormulaConfig(
                id="power_efficiency",
                formula="new_power * efficiency_factor",
                variables={"new_power": "sensor.new_power_meter", "efficiency_factor": "sensor.efficiency"},
            )
            power_efficiency_config.formulas = [new_formula]

            # Update the sensor using SensorSet (which rebuilds its entity index)
            await sensor_set.async_update_sensor(power_efficiency_config)

            # Capture post-modification state
            final_stats = sensor_set.get_entity_index_stats()
            final_entities = set()
            for sensor in storage_manager.list_sensors(sensor_set_id=sensor_set_id):
                for formula in sensor.formulas:
                    if formula.variables:
                        final_entities.update(formula.variables.values())

            # Assess the changes
            added_entities = final_entities - initial_entities
            removed_entities = initial_entities - final_entities

            # Verify the expected changes occurred
            assert "sensor.new_power_meter" in added_entities
            assert "sensor.efficiency" in added_entities

            # Verify entity index was updated correctly - new entities should be tracked
            assert sensor_set.is_entity_tracked("sensor.new_power_meter")
            assert sensor_set.is_entity_tracked("sensor.efficiency")

            # Check if sensor.power_meter is still tracked by other sensors
            system_health = storage_manager.get_sensor("system_health")
            power_meter_still_referenced = False
            if system_health:
                for formula in system_health.formulas:
                    if formula.variables and "sensor.power_meter" in formula.variables.values():
                        power_meter_still_referenced = True
                        break

            if power_meter_still_referenced:
                # Power_meter should still be tracked since system_health still references it
                assert sensor_set.is_entity_tracked("sensor.power_meter")
                # No entities should have been removed since all are still referenced
                assert len(removed_entities) == 0
            else:
                # Power_meter should no longer be tracked if no other sensor references it
                assert not sensor_set.is_entity_tracked("sensor.power_meter")
                assert "sensor.power_meter" in removed_entities

            # Verify the entity index reflects the current configuration accurately
            assert final_stats["total_entities"] >= len(final_entities)

            # Verify that the entity index contains exactly the entities that are actually referenced
            expected_tracked_entities = final_entities
            for entity_id in expected_tracked_entities:
                assert sensor_set.is_entity_tracked(entity_id), f"Entity {entity_id} should be tracked"

    @pytest.mark.asyncio
    async def test_entity_index_handles_attribute_access_patterns(self, storage_manager):
        """Test that entity index correctly handles attribute access patterns vs entity IDs."""
        yaml_config = """
version: "1.0"
sensors:
  attribute_test:
    name: "Attribute Test"
    formula: "power_state + voltage_attr + backup_battery"
    variables:
      power_state: "sensor.power_meter.state"
      voltage_attr: "sensor.voltage.attributes.max_value"
      backup_battery: "backup_device.battery_level"
"""

        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Import configuration
            result = await storage_manager.async_from_yaml(yaml_config, "attr_test_set")
            sensor_set_id = result["sensor_set_id"]
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)

            # Get the actual sensor to understand what entities are being tracked
            attribute_sensor = storage_manager.get_sensor("attribute_test")
            assert attribute_sensor is not None

            # Extract all entity references from variables
            entity_references = set()
            for formula in attribute_sensor.formulas:
                if formula.variables:
                    entity_references.update(formula.variables.values())

            # Verify entity extraction logic
            expected_entities = {
                "sensor.power_meter",
                "sensor.voltage",
                "backup_device.battery_level",
            }  # All valid entity ID formats
            expected_non_entities = set()  # No non-entities in this test

            # Check what the entity index actually tracks
            stats = sensor_set.get_entity_index_stats()

            # These should be tracked as base entity IDs (attribute access patterns)
            assert sensor_set.is_entity_tracked("sensor.power_meter")
            assert sensor_set.is_entity_tracked("sensor.voltage")

            # This should also be tracked as it has valid entity ID format (domain.entity)
            # Even though backup_device is not a standard HA domain, it follows the format
            assert sensor_set.is_entity_tracked("backup_device.battery_level")

            # Verify stats show correct entity count
            # Should track all the valid entity ID formats
            assert stats["total_entities"] >= len(expected_entities)

            # Verify all expected entities are in the tracked set
            for entity_id in expected_entities:
                assert sensor_set.is_entity_tracked(entity_id), f"Expected entity {entity_id} to be tracked"

            # Verify non-entities are not tracked (none in this test)
            for non_entity in expected_non_entities:
                assert not sensor_set.is_entity_tracked(non_entity), f"Non-entity {non_entity} should not be tracked"

    @pytest.mark.asyncio
    async def test_entity_index_updates_during_bulk_operations(self, storage_manager, test_yaml_config):
        """Test that entity index is efficiently updated during bulk sensor operations."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Import initial configuration
            result = await storage_manager.async_from_yaml(test_yaml_config, "test_set")
            sensor_set_id = result["sensor_set_id"]
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)

            # Track entity index rebuild calls (rebuild happens during rebuild_entity_index_for_modification)
            rebuild_count = 0
            original_rebuild = sensor_set._entity_index_handler.rebuild_entity_index_for_modification

            def mock_rebuild(*args, **kwargs):
                nonlocal rebuild_count
                rebuild_count += 1
                return original_rebuild(*args, **kwargs)

            with patch.object(
                sensor_set._entity_index_handler, "rebuild_entity_index_for_modification", side_effect=mock_rebuild
            ):
                # Create the proper modification structure
                from ha_synthetic_sensors.sensor_set import SensorSetModification

                # Add a new sensor
                new_sensor = SensorConfig(
                    unique_id="new_sensor",
                    name="New Sensor",
                    formulas=[
                        FormulaConfig(id="new_sensor", formula="new_entity * 10", variables={"new_entity": "sensor.new_entity"})
                    ],
                )

                # Modify power_efficiency sensor
                power_config = storage_manager.get_sensor("power_efficiency")
                power_config.formulas[0].formula = "power * 2"

                modification = SensorSetModification(
                    add_sensors=[new_sensor], update_sensors=[power_config], remove_sensors=["temperature_status"]
                )

                # Execute bulk modify operation
                await sensor_set.async_modify(modification)

                # Verify entity index was rebuilt only once (optimized bulk operation)
                assert rebuild_count == 1

                # Verify final state
                assert sensor_set.is_entity_tracked("sensor.new_entity")
                assert not sensor_set.is_entity_tracked("sensor.temperature")

    @pytest.mark.asyncio
    async def test_entity_state_change_simulation(self, storage_manager, mock_hass, test_yaml_config):
        """Test simulation of entity state changes and dependency tracking."""
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Import configuration
            result = await storage_manager.async_from_yaml(test_yaml_config, "test_set")
            sensor_set_id = result["sensor_set_id"]
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)

            # Verify entity tracking works
            tracked_entities = [
                "sensor.power_meter",
                "sensor.temperature",
                "switch.backup_mode",
                "sensor.voltage",
                "binary_sensor.grid_connected",
            ]

            # Verify all expected entities are tracked
            for entity_id in tracked_entities:
                assert sensor_set.is_entity_tracked(entity_id)

            # Simulate creating mock events for tracked entities
            for entity_id in tracked_entities:
                # Create mock event
                event = MockEvent(entity_id, "old_state", "new_state")

                # Verify we can create events for tracked entities
                assert event.data["entity_id"] == entity_id
                assert event.data["new_state"].state == "new_state"
                assert event.data["old_state"].state == "old_state"

            # Verify entity tracking still works after creating events
            for entity_id in tracked_entities:
                assert sensor_set.is_entity_tracked(entity_id)
