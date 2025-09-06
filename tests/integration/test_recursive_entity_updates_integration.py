"""Integration test for recursive entity ID updates in nested alternate state structures."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

# Use public API imports as shown in integration guide
from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager
from ha_synthetic_sensors.type_definitions import ReferenceValue


class TestRecursiveEntityUpdatesIntegration:
    """Integration test to verify recursive entity ID updates work in nested structures."""

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
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_recursive_updates")}
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    async def test_recursive_entity_id_updates_in_nested_structures(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test that entity ID updates work recursively in deeply nested alternate state structures."""
        # Set up mock HA states for the backing entities (SPAN export entities)
        mock_states["sensor.main_meter_consumed_energy"] = type("MockState", (), {"state": "100.0", "attributes": {}})()
        mock_states["sensor.main_meter_produced_energy"] = type("MockState", (), {"state": "200.0", "attributes": {}})()
        # Also add binary_sensor used in complex formulas (both old and prefixed)
        mock_states["binary_sensor.panel_status"] = type("MockState", (), {"state": "off", "attributes": {}})()
        mock_states["binary_sensor.span_panel_panel_status"] = type("MockState", (), {"state": "off", "attributes": {}})()

        # Define a helper to resolve HA entities via our mock_states during variable resolution
        def _fake_resolve_via_hass_entity(dependency_handler, entity_id, original_reference):
            st = mock_states.get(entity_id)
            if st is None:
                return None
            return ReferenceValue(reference=entity_id, value=st.state)

        # Set up storage manager with proper mocking
        # Also patch the EntityReferenceResolver.resolve to consult our mock_states first
        from ha_synthetic_sensors.evaluator_phases.variable_resolution.entity_reference_resolver import (
            EntityReferenceResolver,
        )

        original_entity_resolve = EntityReferenceResolver.resolve
        original_entity_can_resolve = EntityReferenceResolver.can_resolve

        def _patched_entity_can_resolve(self, variable_name, variable_value):
            # If this entity exists in the test's mock_states, treat it as resolvable
            try:
                if isinstance(variable_value, str) and variable_value in mock_states:
                    return True
            except Exception:
                pass
            return original_entity_can_resolve(self, variable_name, variable_value)

        EntityReferenceResolver.can_resolve = _patched_entity_can_resolve

        def _patched_entity_resolve(self, variable_name, variable_value, context):
            # If the entity exists in the test's mock_states, return a ReferenceValue immediately
            try:
                from ha_synthetic_sensors.type_definitions import ReferenceValue

                st = mock_states.get(variable_value)
                if st is not None:
                    return ReferenceValue(reference=variable_value, value=st.state)
            except Exception:
                pass
            return original_entity_resolve(self, variable_name, variable_value, context)

        EntityReferenceResolver.resolve = _patched_entity_resolve

        try:
            with (
                patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
                patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
            ):
                mock_store = AsyncMock()
                mock_store.async_load.return_value = None
                MockStore.return_value = mock_store

                MockDeviceRegistry.return_value = mock_device_registry

                storage_manager = StorageManager(mock_hass, "test_recursive_storage", enable_entity_listener=False)
                storage_manager._store = mock_store
                await storage_manager.async_load()

                # Ensure mock_store.async_load returns the live storage data during reloads
                async def _mock_store_load():
                    return storage_manager.data

                mock_store.async_load.side_effect = _mock_store_load

                # Create sensor set and load the recursive test YAML
                sensor_set_id = "recursive_test"
                await storage_manager.async_create_sensor_set(
                    sensor_set_id=sensor_set_id, device_identifier="test_device_recursive_updates", name="Recursive Update Test"
                )

                # Load the recursive test YAML
                yaml_fixture_path = (
                    Path(__file__).parent.parent / "fixtures" / "integration" / "test_recursive_entity_updates.yaml"
                )
                with open(yaml_fixture_path, "r") as f:
                    yaml_content = f.read()

                result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

                # Verify sensor was loaded
                stored_sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)

                assert result["sensors_imported"] == 1, f"Expected 1 sensor imported, got {result['sensors_imported']}"

                assert len(stored_sensors) == 1, f"Expected 1 sensor stored, got {len(stored_sensors)}"

                # Ensure common registry contains backing and synthetic entities so resolution succeeds
                # Register backing HA entities referenced in YAML
                mock_entity_registry.register_entity(
                    entity_id="sensor.main_meter_consumed_energy",
                    unique_id="main_meter_consumed_energy",
                    domain="sensor",
                )
                mock_entity_registry.register_entity(
                    entity_id="sensor.main_meter_produced_energy",
                    unique_id="main_meter_produced_energy",
                    domain="sensor",
                )
                # Register binary sensor entities
                mock_entity_registry.register_entity(
                    entity_id="binary_sensor.panel_status",
                    unique_id="panel_status",
                    domain="binary_sensor",
                )
                mock_entity_registry.register_entity(
                    entity_id="binary_sensor.span_panel_panel_status",
                    unique_id="span_panel_panel_status",
                    domain="binary_sensor",
                )
                # Register the synthetic sensor entity created from YAML
                mock_entity_registry.register_entity(
                    entity_id="sensor.recursive_test_sensor",
                    unique_id="recursive_test_sensor",
                    domain="sensor",
                )

                # Set up sensor manager to test entity creation
                sensor_manager = await async_setup_synthetic_sensors(
                    hass=mock_hass,
                    config_entry=mock_config_entry,
                    async_add_entities=mock_async_add_entities,
                    storage_manager=storage_manager,
                )

                assert sensor_manager is not None
                assert mock_async_add_entities.called

                # TEST RECURSIVE ENTITY ID UPDATES USING PUBLIC API
                # Get the sensor set through the public API
                sensor_set = storage_manager.get_sensor_set(sensor_set_id)
                assert sensor_set is not None, "Sensor set not found"

                # Define entity ID changes to match the SPAN integration exported YAML
                entity_id_changes = {
                    "sensor.main_meter_consumed_energy": "sensor.span_panel_main_meter_consumed_energy",
                    "sensor.main_meter_produced_energy": "sensor.span_panel_main_meter_produced_energy",
                    "binary_sensor.panel_status": "binary_sensor.span_panel_panel_status",
                }

                # Apply entity ID changes using the public API
                from ha_synthetic_sensors.sensor_set import SensorSetModification

                modification = SensorSetModification(entity_id_changes=entity_id_changes)
                result = await sensor_set.async_modify(modification)

                # Verify the changes were applied
                assert result["entity_ids_changed"] == 3, (
                    f"Expected 3 entity IDs changed, got {result.get('entity_ids_changed', 'unknown')}"
                )

                # Get the updated sensor configuration through the public API
                updated_sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
                assert len(updated_sensors) == 1, f"Expected 1 updated sensor, got {len(updated_sensors)}"
                updated_sensor = updated_sensors[0]

                # Verify changes reflected in serialized configuration and exported YAML
                config_str = str(storage_manager.serialize_sensor_config(updated_sensor))
                assert "sensor.span_panel_main_meter_consumed_energy" in config_str, (
                    f"Prefixed entity ID not present in sensor config: {config_str}"
                )
                assert "sensor.main_meter_consumed_energy" not in config_str, (
                    f"Old entity ID still present in sensor config: {config_str}"
                )

                updated_config = await storage_manager.async_export_yaml(sensor_set_id=sensor_set_id)
                assert "sensor.span_panel_main_meter_consumed_energy" in updated_config, (
                    f"Prefixed entity ID not present in exported YAML: {updated_config[:500]}..."
                )
                assert "sensor.main_meter_consumed_energy" not in updated_config, (
                    f"Old entity ID still present in exported YAML: {updated_config[:500]}..."
                )

                # Verify no old entity IDs remain anywhere in the configuration
                config_str = str(storage_manager.serialize_sensor_config(updated_sensor))
                assert "sensor.main_meter_consumed_energy" not in config_str, (
                    f"Old entity reference still found in configuration: {config_str}"
                )
                assert "sensor.main_meter_produced_energy" not in config_str, (
                    f"Old entity reference still found in configuration: {config_str}"
                )

                # Export the updated configuration to YAML and verify it
                updated_config = await storage_manager.async_export_yaml(sensor_set_id=sensor_set_id)

                # Verify the YAML contains the new entity IDs
                assert "sensor.span_panel_main_meter_consumed_energy" in updated_config, (
                    f"New entity ID not found in exported YAML: {updated_config[:500]}..."
                )
                assert "sensor.span_panel_main_meter_produced_energy" in updated_config, (
                    f"Another new entity ID not found in exported YAML: {updated_config[:500]}..."
                )

                # Verify the YAML does NOT contain the old entity IDs
                assert "sensor.main_meter_consumed_energy" not in updated_config, (
                    f"Old entity ID still found in exported YAML: {updated_config[:500]}..."
                )
                assert "sensor.main_meter_produced_energy" not in updated_config, (
                    f"Another old entity ID still found in exported YAML: {updated_config[:500]}..."
                )

                # Test sensor evaluation through the public API
                await sensor_manager.async_update_sensors()

                # Cleanup
                if storage_manager.sensor_set_exists(sensor_set_id):
                    await storage_manager.async_delete_sensor_set(sensor_set_id)
        finally:
            # Restore resolver methods to avoid affecting other tests
            from ha_synthetic_sensors.evaluator_phases.variable_resolution.entity_reference_resolver import (
                EntityReferenceResolver as _ERR,
            )

            _ERR.resolve = original_entity_resolve
            _ERR.can_resolve = original_entity_can_resolve
