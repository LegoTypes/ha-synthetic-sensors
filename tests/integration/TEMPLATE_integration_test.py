"""BULLETPROOF Integration Test Template for Synthetic Sensors.

COPY THIS FILE and modify the marked sections for your specific test.
This template includes bulletproof assertions and error handling.
"""

from unittest.mock import AsyncMock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


class TestYourFeature:  # Replace with your test class name
    """Integration tests for your specific feature."""

    @pytest.mark.asyncio
    async def test_your_feature_name(  # Replace with your test method name
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_device_registry,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test your specific feature end-to-end."""

        # =============================================================================
        # CUSTOMIZE THIS SECTION FOR YOUR TEST
        # =============================================================================

        # 1. Set up your required entities (entities your YAML references)
        required_entities = {
            "sensor.input_entity": {"state": "100.0", "attributes": {"unit": "W"}},
            "sensor.other_entity": {"state": "50.0", "attributes": {"unit": "V"}},
            # Add your entities here based on your YAML variables
        }

        # 2. Define your YAML file path and expected sensor count
        yaml_file_path = "tests/fixtures/integration/your_test_fixture.yaml"  # Replace with your YAML file
        expected_sensor_count = 1  # Set the number of sensors in your YAML
        device_identifier = "test_device_your_feature"  # Must match your YAML global_settings

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

                # Set up synthetic sensors
                sensor_manager = await async_setup_synthetic_sensors(
                    hass=mock_hass,
                    config_entry=mock_config_entry,
                    async_add_entities=mock_async_add_entities,
                    storage_manager=storage_manager,
                    device_identifier=device_identifier,
                )

                # BULLETPROOF ASSERTION 2: Sensor manager must be created
                assert sensor_manager is not None, "Sensor manager creation failed"

                # BULLETPROOF ASSERTION 3: Entities must be added to HA
                assert mock_async_add_entities.call_args_list, (
                    "async_add_entities was never called - no entities were added to HA"
                )

                # Update sensors to ensure formulas are evaluated
                await sensor_manager.async_update_sensors()

                # Get all created entities
                all_entities = []
                for call in mock_async_add_entities.call_args_list:
                    entities_list = call.args[0] if call.args else []
                    all_entities.extend(entities_list)

                # BULLETPROOF ASSERTION 4: Exact entity count verification
                assert len(all_entities) == expected_sensor_count, (
                    f"Wrong number of entities created: expected {expected_sensor_count}, "
                    f"got {len(all_entities)}. Entities: {[getattr(e, 'unique_id', 'no_id') for e in all_entities]}"
                )

                # Create lookup for easier testing
                entity_lookup = {entity.unique_id: entity for entity in all_entities}

                # =============================================================================
                # ADD YOUR SPECIFIC ASSERTIONS HERE
                # =============================================================================

                # Example bulletproof assertions - customize for your sensors:

                # Test specific sensor by unique_id
                test_sensor = entity_lookup.get("your_sensor")  # Replace with your sensor ID
                assert test_sensor is not None, (
                    f"Sensor 'your_sensor' not found. Available sensors: {list(entity_lookup.keys())}"
                )

                # Test sensor has value (not None, not "unknown", not "unavailable")
                assert test_sensor.native_value is not None, "Sensor 'your_sensor_unique_id' has None value"
                assert str(test_sensor.native_value) not in ["unknown", "unavailable", ""], (
                    f"Sensor 'your_sensor_unique_id' has invalid value: {test_sensor.native_value}"
                )

                # Test specific expected value (customize calculation)
                expected_value = 150.0  # Calculate based on your formula and input data
                actual_value = float(test_sensor.native_value)
                assert abs(actual_value - expected_value) < 0.001, (
                    f"Sensor 'your_sensor_unique_id' value wrong: expected {expected_value}, got {actual_value}"
                )

                # Test sensor attributes if relevant
                if hasattr(test_sensor, "extra_state_attributes") and test_sensor.extra_state_attributes:
                    # Add specific attribute tests
                    # Example: assert test_sensor.extra_state_attributes.get("unit_of_measurement") == "W"
                    pass

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


# =============================================================================
# HELPER METHODS (COPY AS NEEDED)
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


# =============================================================================
# CHECKLIST FOR CREATING YOUR TEST:
# =============================================================================
"""
1. [ ] Copy this file to test_your_feature_integration.py
2. [ ] Replace class name TestYourFeature with TestYourActualFeature
3. [ ] Replace method name test_your_feature_name with test_your_actual_feature
4. [ ] Create your YAML fixture file and put it in tests/yaml_fixtures/
5. [ ] Update required_entities with entities your YAML references
6. [ ] Update yaml_file_path with your actual YAML file
7. [ ] Update expected_sensor_count with the number of sensors in your YAML
8. [ ] Update device_identifier to match your YAML global_settings.device_identifier
9. [ ] Replace "your_sensor_unique_id" with actual sensor IDs from your YAML
10. [ ] Calculate expected_value based on your formula and test data
11. [ ] Add any specific attribute assertions you need
12. [ ] Run the test and fix any issues

BULLETPROOF ASSERTION PRINCIPLES:
- Never just check if something exists without checking its value
- Always provide detailed error messages showing what you got vs expected
- Test exact values, not just "not None"
- Test all sensors, not just one
- Always clean up in finally block
- Fail fast with specific error messages
"""
