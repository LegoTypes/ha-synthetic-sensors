"""Integration Test for Metadata Function Features.

Tests the metadata() function integration with synthetic sensors using proper public API patterns.
"""

from unittest.mock import AsyncMock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


class TestSpanDebugMinimal:
    """Minimal debug test for span_grace_period_validation_test sensor."""

    @pytest.mark.asyncio
    async def test_span_sensor_debug(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_device_registry,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test metadata function integration end-to-end."""

        # =============================================================================
        # CUSTOMIZE THIS SECTION FOR METADATA FUNCTION TEST
        # =============================================================================

        # 1. Set up required entities (entities the YAML references)
        required_entities = {
            "sensor.basic_power_meter": {"state": "1000.0", "attributes": {"unit_of_measurement": "W"}},
            "sensor.basic_temp_probe": {"state": "25.5", "attributes": {"unit_of_measurement": "°C"}},
            "sensor.external_power_meter": {"state": "750.0", "attributes": {"unit_of_measurement": "W"}},
        }

        # 2. Set up virtual backing entity data (avoids registry collisions)
        backing_data = {
            "sensor.metadata_self_reference_backing": 42.0,  # Virtual backing entity for self-reference test
            "sensor.span_grace_period_test": 1250.5,  # SPAN Panel grace period validation test
        }

        # 3. Define YAML file path and expected sensor count
        yaml_file_path = "tests/fixtures/integration/span_debug_minimal.yaml"
        expected_sensor_count = 1  # Count of sensors in the YAML file
        device_identifier = "test_device_span_debug"  # Must match YAML global_settings

        # 4. Create data provider for virtual backing entities
        def create_data_provider_callback(backing_data: dict[str, any]):
            def data_provider(entity_id: str):
                return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

            return data_provider

        data_provider_callback = create_data_provider_callback(backing_data)

        # 5. Create sensor-to-backing mapping for 'state' token resolution
        sensor_to_backing_mapping = {
            "metadata_self_reference_test": "sensor.metadata_self_reference_backing",
            "span_grace_period_validation_test": "sensor.span_grace_period_test",
        }

        # =============================================================================
        # STANDARD SETUP (DON'T CHANGE UNLESS YOU KNOW WHAT YOU'RE DOING)
        # =============================================================================

        # Save original state for cleanup
        original_entities = dict(mock_entity_registry._entities)
        original_states = dict(mock_states)

        try:
            # Register required entities
            for entity_id, data in required_entities.items():
                mock_entity_registry.register_entity(entity_id, entity_id, "sensor")
                mock_states.register_state(entity_id, data["state"], data["attributes"])

            # Set up storage manager with standard pattern
            with (
                patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
                patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
            ):
                # Standard mock setup
                mock_store = AsyncMock()
                mock_store.async_load.return_value = None
                MockStore.return_value = mock_store
                MockDeviceRegistry.return_value = mock_device_registry

                # Create storage manager
                storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
                storage_manager._store = mock_store
                await storage_manager.async_load()

                # Create sensor set
                sensor_set_id = "test_sensor_set"
                await storage_manager.async_create_sensor_set(
                    sensor_set_id=sensor_set_id, device_identifier=device_identifier, name="Test Sensor Set"
                )

                # Load YAML configuration
                with open(yaml_file_path) as f:
                    yaml_content = f.read()

                result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

                # BULLETPROOF ASSERTION 1: YAML import must succeed with exact count
                assert result["sensors_imported"] == expected_sensor_count, (
                    f"YAML import failed: expected {expected_sensor_count} sensors, "
                    f"got {result['sensors_imported']}. Result: {result}"
                )

                # Set up synthetic sensors with virtual backing entities
                sensor_manager = await async_setup_synthetic_sensors(
                    hass=mock_hass,
                    config_entry=mock_config_entry,
                    async_add_entities=mock_async_add_entities,
                    storage_manager=storage_manager,
                    sensor_to_backing_mapping=sensor_to_backing_mapping,
                    data_provider_callback=data_provider_callback,
                )

                # BULLETPROOF ASSERTION 2: Sensor manager must be created
                assert sensor_manager is not None, "Sensor manager creation failed"

                # BULLETPROOF ASSERTION 3: Entities must be added to HA
                assert mock_async_add_entities.call_args_list, (
                    "async_add_entities was never called - no entities were added to HA"
                )

                # Get all created entities immediately after creation
                all_entities = []
                for call in mock_async_add_entities.call_args_list:
                    entities_list = call.args[0] if call.args else []
                    all_entities.extend(entities_list)

                # Set hass attribute on all entities BEFORE update (required to prevent "Attribute hass is None" errors)
                for entity in all_entities:
                    entity.hass = mock_hass

                # Add synthetic sensors to mock states so they can reference themselves for metadata queries
                from datetime import datetime, timezone

                for entity in all_entities:
                    if hasattr(entity, "entity_id") and entity.entity_id:
                        # Create mock state with proper metadata attributes for metadata handler
                        mock_state = type(
                            "MockState",
                            (),
                            {
                                "state": str(entity.native_value) if entity.native_value is not None else "unknown",
                                "attributes": getattr(entity, "extra_state_attributes", {}) or {},
                            },
                        )()
                        # Add metadata properties that metadata handler expects
                        mock_state.entity_id = entity.entity_id
                        mock_state.object_id = entity.entity_id.split(".")[-1] if "." in entity.entity_id else entity.entity_id
                        mock_state.domain = entity.entity_id.split(".")[0] if "." in entity.entity_id else "sensor"
                        mock_state.last_changed = datetime.now(timezone.utc)
                        mock_state.last_updated = datetime.now(timezone.utc)

                        mock_states[entity.entity_id] = mock_state

                # Update sensors to ensure formulas are evaluated (after hass attribute and states are set)
                await sensor_manager.async_update_sensors()

                # BULLETPROOF ASSERTION 4: Exact entity count verification
                assert len(all_entities) == expected_sensor_count, (
                    f"Wrong number of entities created: expected {expected_sensor_count}, "
                    f"got {len(all_entities)}. Entities: {[getattr(e, 'unique_id', 'no_id') for e in all_entities]}"
                )

                # Create lookup for easier testing
                entity_lookup = {entity.unique_id: entity for entity in all_entities}

                # =============================================================================
                # METADATA FUNCTION SPECIFIC ASSERTIONS
                # =============================================================================

                # Test span grace period validation sensor
                span_sensor = entity_lookup.get("span_grace_period_validation_test")
                assert span_sensor is not None, (
                    f"Sensor 'span_grace_period_validation_test' not found. Available sensors: {list(entity_lookup.keys())}"
                )

                # The sensor should have a value (either the backing entity value or alternate state)
                assert span_sensor.native_value is not None, "Sensor 'span_grace_period_validation_test' has None value"
                print(f"DEBUG: span_sensor.native_value = {span_sensor.native_value}")
                print(f"DEBUG: span_sensor.state = {span_sensor.state}")

                # Should return the backing entity value since we're using 'state' formula
                expected_grace_period_value = 1250.5
                actual_grace_period_value = float(span_sensor.native_value)
                assert abs(actual_grace_period_value - expected_grace_period_value) < 0.001, (
                    f"Sensor 'span_grace_period_validation_test' wrong value: expected {expected_grace_period_value}, got {actual_grace_period_value}"
                )

                # Verify grace period attributes exist and have expected values
                grace_period_attrs = getattr(span_sensor, "extra_state_attributes", {}) or {}
                assert "grace_period_active" in grace_period_attrs, "grace_period_active attribute missing"
                assert "source_entity" in grace_period_attrs, "source_entity attribute missing"

                # source_entity should be the sensor's own entity_id
                assert grace_period_attrs["source_entity"] == "sensor.span_grace_period_test", (
                    f"source_entity attribute wrong: expected 'sensor.span_grace_period_test', got {grace_period_attrs['source_entity']}"
                )

                # Test completed - sensor evaluation and attributes are working correctly
                print("DEBUG: SPAN grace period validation test completed successfully")

                # Test all sensors have valid values (bulletproof check)
                for entity in all_entities:
                    unique_id = getattr(entity, "unique_id", "unknown")
                    value = getattr(entity, "native_value", None)

                    # Every sensor must have a valid value
                    assert value is not None, f"Sensor '{unique_id}' has None value"
                    assert str(value) not in ["unknown", "unavailable", ""], f"Sensor '{unique_id}' has invalid value: {value}"

                    # Every sensor must have basic attributes
                    assert hasattr(entity, "name"), f"Sensor '{unique_id}' missing name attribute"
                    assert hasattr(entity, "unique_id"), f"Sensor '{unique_id}' missing unique_id attribute"

                # Clean up
                await storage_manager.async_delete_sensor_set(sensor_set_id)

        finally:
            # Restore original state
            mock_entity_registry._entities.clear()
            mock_entity_registry._entities.update(original_entities)
            mock_states.clear()
            mock_states.update(original_states)

    @pytest.mark.asyncio
    async def test_metadata_state_token_in_computed_variables_startup_fix(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_device_registry,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test that computed variables with metadata(state, ...) work during startup.

        This test specifically covers the fix for the issue where computed variables
        containing metadata(state, 'last_valid_state') would fail during startup with:
        'State token cannot be resolved: no backing entity mapping, no sensor entity_id, and no previous value available'

        The fix ensures that state tokens inside metadata function parameters are not
        processed by variable resolution, allowing metadata processing to handle them properly.
        """

        # Set up required entities
        required_entities = {
            "sensor.test_backing_entity": {"state": "1000.0", "attributes": {"unit_of_measurement": "W"}},
        }

        # Set up virtual backing entity data
        backing_data = {
            "sensor.test_backing_entity": 1000.0,
        }

        # Define YAML file path and expected sensor count
        yaml_file_path = "tests/fixtures/integration/metadata_state_token_startup_fix.yaml"
        expected_sensor_count = 2  # Count of sensors in the YAML file
        device_identifier = "test_device_metadata_state_fix"

        # Create data provider for virtual backing entities
        def create_data_provider_callback(backing_data: dict[str, any]):
            def data_provider(entity_id: str):
                return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

            return data_provider

        data_provider_callback = create_data_provider_callback(backing_data)

        # Create sensor-to-backing mapping for 'state' token resolution
        sensor_to_backing_mapping = {
            "metadata_state_computed_variable_test": "sensor.test_backing_entity",
            "metadata_state_attribute_test": "sensor.test_backing_entity",
        }

        # Save original state for cleanup
        original_entities = dict(mock_entity_registry._entities)
        original_states = dict(mock_states)

        try:
            # Register required entities
            for entity_id, data in required_entities.items():
                mock_entity_registry.register_entity(entity_id, entity_id, "sensor")
                mock_states.register_state(entity_id, data["state"], data["attributes"])

            # Set up storage manager
            with (
                patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
                patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
            ):
                # Standard mock setup
                mock_store = AsyncMock()
                mock_store.async_load.return_value = None
                MockStore.return_value = mock_store
                MockDeviceRegistry.return_value = mock_device_registry

                # Create storage manager
                storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
                storage_manager._store = mock_store
                await storage_manager.async_load()

                # Create sensor set
                sensor_set_id = "test_sensor_set_state_fix"
                await storage_manager.async_create_sensor_set(
                    sensor_set_id=sensor_set_id, device_identifier=device_identifier, name="Test Sensor Set State Fix"
                )

                # Load YAML configuration
                with open(yaml_file_path) as f:
                    yaml_content = f.read()

                result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

                # ASSERTION 1: YAML import must succeed
                assert result["sensors_imported"] == expected_sensor_count, (
                    f"YAML import failed: expected {expected_sensor_count} sensors, "
                    f"got {result['sensors_imported']}. Result: {result}"
                )

                # Set up synthetic sensors - this is where the bug would have occurred
                # The fix ensures that metadata(state, ...) in computed variables doesn't trigger
                # state resolution during sensor creation
                sensor_manager = await async_setup_synthetic_sensors(
                    hass=mock_hass,
                    config_entry=mock_config_entry,
                    async_add_entities=mock_async_add_entities,
                    storage_manager=storage_manager,
                    sensor_to_backing_mapping=sensor_to_backing_mapping,
                    data_provider_callback=data_provider_callback,
                )

                # ASSERTION 2: Sensor manager must be created successfully
                assert sensor_manager is not None, "Sensor manager creation failed - the startup fix didn't work"

                # ASSERTION 3: Entities must be added to HA
                assert mock_async_add_entities.call_args_list, (
                    "async_add_entities was never called - sensor creation failed during startup"
                )

                # Get all created entities
                all_entities = []
                for call in mock_async_add_entities.call_args_list:
                    entities_list = call.args[0] if call.args else []
                    all_entities.extend(entities_list)

                # Set hass attribute on all entities
                for entity in all_entities:
                    entity.hass = mock_hass

                # Add synthetic sensors to mock states
                from datetime import datetime, timezone

                for entity in all_entities:
                    if hasattr(entity, "entity_id") and entity.entity_id:
                        mock_state = type(
                            "MockState",
                            (),
                            {
                                "state": str(entity.native_value) if entity.native_value is not None else "unknown",
                                "attributes": getattr(entity, "extra_state_attributes", {}) or {},
                            },
                        )()
                        mock_state.entity_id = entity.entity_id
                        mock_state.object_id = entity.entity_id.split(".")[-1] if "." in entity.entity_id else entity.entity_id
                        mock_state.domain = entity.entity_id.split(".")[0] if "." in entity.entity_id else "sensor"
                        mock_state.last_changed = datetime.now(timezone.utc)
                        mock_state.last_updated = datetime.now(timezone.utc)
                        mock_states[entity.entity_id] = mock_state

                # Update sensors to trigger evaluation
                await sensor_manager.async_update_sensors()

                # ASSERTION 4: Exact entity count verification
                assert len(all_entities) == expected_sensor_count, (
                    f"Wrong number of entities created: expected {expected_sensor_count}, "
                    f"got {len(all_entities)}. Entities: {[getattr(e, 'unique_id', 'no_id') for e in all_entities]}"
                )

                # Create lookup for testing
                entity_lookup = {entity.unique_id: entity for entity in all_entities}

                # Test the computed variable sensor that uses metadata(state, ...)
                computed_var_sensor = entity_lookup.get("metadata_state_computed_variable_test")
                assert computed_var_sensor is not None, (
                    f"Sensor 'metadata_state_computed_variable_test' not found. Available: {list(entity_lookup.keys())}"
                )

                # The sensor should have been created successfully (the main fix verification)
                assert computed_var_sensor.native_value is not None, (
                    "Sensor with metadata(state, ...) computed variable failed to evaluate"
                )

                # Test the attribute sensor that uses metadata(state, ...) in attributes
                attr_sensor = entity_lookup.get("metadata_state_attribute_test")
                assert attr_sensor is not None, (
                    f"Sensor 'metadata_state_attribute_test' not found. Available: {list(entity_lookup.keys())}"
                )

                # Check that attributes with metadata(state, ...) work
                attrs = getattr(attr_sensor, "extra_state_attributes", {}) or {}
                assert "last_valid_state_attr" in attrs, "Attribute using metadata(state, ...) was not created"

                # The key test: both sensors were created without the startup error
                # If the fix didn't work, sensor creation would have failed with:
                # "State token cannot be resolved: no backing entity mapping, no sensor entity_id, and no previous value available"

                # Clean up
                await storage_manager.async_delete_sensor_set(sensor_set_id)

        finally:
            # Restore original state
            mock_entity_registry._entities.clear()
            mock_entity_registry._entities.update(original_entities)
            mock_states.clear()
            mock_states.update(original_states)


# =============================================================================
# HELPER METHODS
# =============================================================================


def assert_sensor_exists_and_has_value(entity_lookup, sensor_id, expected_value=None):
    """Bulletproof assertion helper for sensor existence and value."""
    sensor = entity_lookup.get(sensor_id)
    assert sensor is not None, f"Sensor '{sensor_id}' not found. Available: {list(entity_lookup.keys())}"

    assert sensor.native_value is not None, f"Sensor '{sensor_id}' has None value"
    assert str(sensor.native_value) not in ["unknown", "unavailable", ""], (
        f"Sensor '{sensor_id}' has invalid value: {sensor.native_value}"
    )

    if expected_value is not None:
        actual = float(sensor.native_value)
        assert abs(actual - expected_value) < 0.001, (
            f"Sensor '{sensor_id}' wrong value: expected {expected_value}, got {actual}"
        )

    return sensor


def assert_sensor_attribute(sensor, attr_name, expected_value):
    """Bulletproof assertion helper for sensor attributes."""
    assert hasattr(sensor, "extra_state_attributes"), f"Sensor '{sensor.unique_id}' has no extra_state_attributes"

    attrs = sensor.extra_state_attributes or {}
    actual_value = attrs.get(attr_name)

    assert actual_value == expected_value, (
        f"Sensor '{sensor.unique_id}' attribute '{attr_name}': expected {expected_value}, got {actual_value}"
    )
