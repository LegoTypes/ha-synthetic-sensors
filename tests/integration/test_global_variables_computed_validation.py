"""Integration test for global variables with computed variables validation fix.

This test verifies that the computed variable validation fix allows:
1. Computed variables to reference global variables during YAML parsing
2. Built-in functions (minutes, hours, now, metadata) to be recognized
3. End-to-end SPAN-like scenarios with complex computed variables

This addresses the bug described in computed_variable_validation_fix.md
"""

from unittest.mock import AsyncMock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


class TestGlobalVariablesComputedValidation:
    """Integration tests for global variables with computed variables validation."""

    @pytest.mark.asyncio
    async def test_global_variables_computed_validation_fix(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_device_registry,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test that computed variables can reference global variables and built-in functions."""

        # =============================================================================
        # TEST CONFIGURATION
        # =============================================================================

        # Set up required entities (entities our YAML references)
        required_entities = {
            # Backing entities for sensors with 'state' token
            "sensor.simple_backing": {"state": "10.0", "attributes": {"unit": "min"}},
            "sensor.computed_backing": {"state": "1000.0", "attributes": {"unit": "W", "last_changed": "2024-01-01T10:00:00Z"}},
            "sensor.mixed_backing": {"state": "800.0", "attributes": {"unit": "W"}},
            "sensor.span_backing": {
                "state": "5.5",
                "attributes": {"unit": "kWh", "last_changed": "2024-01-01T10:00:00Z", "power_factor": "0.95"},
            },
        }

        # Test configuration
        yaml_file_path = "tests/fixtures/integration/global_variables_computed_validation.yaml"
        expected_sensor_count = 4  # 4 sensors in our YAML
        device_identifier = "test_device_global_computed_validation"  # Must match YAML

        # =============================================================================
        # STANDARD SETUP
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
                sensor_set_id = "test_global_computed_validation"
                await storage_manager.async_create_sensor_set(
                    sensor_set_id=sensor_set_id, device_identifier=device_identifier, name="Global Computed Validation Test"
                )

                # Load YAML configuration - THIS IS WHERE THE BUG WOULD HAVE OCCURRED
                with open(yaml_file_path) as f:
                    yaml_content = f.read()

                result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

                # BULLETPROOF ASSERTION 1: YAML import must succeed (would have failed before fix)
                assert result["sensors_imported"] == expected_sensor_count, (
                    f"YAML import failed - computed variable validation likely failed: "
                    f"expected {expected_sensor_count} sensors, got {result['sensors_imported']}. "
                    f"Result: {result}. This indicates the global variables fix didn't work."
                )

                # Create sensor to backing mapping for 'state' token resolution
                sensor_to_backing_mapping = {
                    "span_main_meter_produced_energy": "sensor.span_backing",
                    "builtin_functions_test": "sensor.computed_backing",
                    "global_math_operations": "sensor.mixed_backing",
                    "complex_expression_test": "sensor.simple_backing",
                }

                # Create data provider for virtual backing entities (Pattern 1 from guide)
                def data_provider(entity_id: str):
                    if entity_id in required_entities:
                        entity_data = required_entities[entity_id]
                        return {"value": float(entity_data["state"]), "exists": True}
                    return {"value": None, "exists": False}

                # Set up synthetic sensors
                sensor_manager = await async_setup_synthetic_sensors(
                    hass=mock_hass,
                    config_entry=mock_config_entry,
                    async_add_entities=mock_async_add_entities,
                    storage_manager=storage_manager,
                    sensor_to_backing_mapping=sensor_to_backing_mapping,
                    data_provider_callback=data_provider,  # Provide backing entity data
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
                # SPECIFIC GLOBAL VARIABLES + COMPUTED VARIABLES TESTS
                # =============================================================================

                # TEST 1: SPAN-like scenario (global variable reference - was the core issue)
                span_sensor = entity_lookup.get("span_main_meter_produced_energy")
                assert span_sensor is not None, f"SPAN sensor not found. Available: {list(entity_lookup.keys())}"
                # Formula: state + 0, should work with computed variable within_grace
                # This test ensures computed variables referencing globals work
                assert span_sensor.native_value is not None, "SPAN sensor has None value - computed variable validation failed"
                assert str(span_sensor.native_value) not in ["unknown", "unavailable", ""], (
                    f"SPAN sensor has invalid value: {span_sensor.native_value}. "
                    f"This indicates computed variables referencing globals failed to resolve."
                )

                # TEST 2: Built-in functions with computed variables (THE FIX)
                builtin_sensor = entity_lookup.get("builtin_functions_test")
                assert builtin_sensor is not None, (
                    f"Built-in functions sensor not found. Available: {list(entity_lookup.keys())}"
                )
                # This sensor uses duration functions and computed variables
                # If this has a valid value, the enhanced SimpleEval worked
                assert builtin_sensor.native_value is not None, (
                    "Built-in functions sensor has None value - function validation failed"
                )
                assert str(builtin_sensor.native_value) not in ["unknown", "unavailable", ""], (
                    f"Built-in functions sensor has invalid value: {builtin_sensor.native_value}. "
                    f"This indicates enhanced SimpleEval functions failed to resolve."
                )

                # TEST 3: Global math operations with computed variables
                math_sensor = entity_lookup.get("global_math_operations")
                assert math_sensor is not None, (
                    f"Global math operations sensor not found. Available: {list(entity_lookup.keys())}"
                )
                assert math_sensor.native_value is not None, "Global math operations sensor has None value"
                assert str(math_sensor.native_value) not in ["unknown", "unavailable", ""], (
                    f"Global math operations sensor has invalid value: {math_sensor.native_value}"
                )

                # TEST 4: Complex expression with mixed types (enhanced SimpleEval)
                complex_sensor = entity_lookup.get("complex_expression_test")
                assert complex_sensor is not None, (
                    f"Complex expression sensor not found. Available: {list(entity_lookup.keys())}"
                )
                # This sensor uses global variables, conditionals, and enhanced SimpleEval functions
                # which tests the complete integration
                assert complex_sensor.native_value is not None, (
                    "Complex expression sensor has None value - enhanced SimpleEval integration failed"
                )
                assert str(complex_sensor.native_value) not in ["unknown", "unavailable", ""], (
                    f"Complex expression sensor has invalid value: {complex_sensor.native_value}. "
                    f"Enhanced SimpleEval integration still fails."
                )

                # TEST 5: Verify computed attributes also work (part of the fix)
                if hasattr(span_sensor, "extra_state_attributes") and span_sensor.extra_state_attributes:
                    attrs = span_sensor.extra_state_attributes
                    # grace_status attribute should be computed correctly
                    if "grace_status" in attrs:
                        grace_status = attrs["grace_status"]
                        assert grace_status is not None, "Computed attribute 'grace_status' is None"
                        assert str(grace_status) not in ["unknown", "unavailable"], (
                            f"Computed attribute 'grace_status' has invalid value: {grace_status}"
                        )

                # TEST 6: Verify all sensors have valid values (comprehensive check)
                for entity in all_entities:
                    unique_id = getattr(entity, "unique_id", "unknown")
                    value = getattr(entity, "native_value", None)

                    # Every sensor must have a valid value
                    assert value is not None, (
                        f"Sensor '{unique_id}' has None value - indicates computed variable resolution failed"
                    )
                    assert str(value) not in ["unknown", "unavailable", ""], (
                        f"Sensor '{unique_id}' has invalid value: {value} - indicates formula evaluation failed"
                    )

                    # Every sensor must have basic attributes
                    assert hasattr(entity, "name"), f"Sensor '{unique_id}' missing name attribute"
                    assert hasattr(entity, "unique_id"), f"Sensor '{unique_id}' missing unique_id attribute"

                # TEST 7: Test that built-in functions are recognized
                # If we got this far without validation errors, built-in functions were recognized
                # The YAML uses: now(), metadata(), minutes() - all should be valid
                print("✅ SUCCESS: All computed variables with global references and built-in functions work correctly")
                print(f"✅ Sensors created: {[entity.unique_id for entity in all_entities]}")
                print(f"✅ Sample values: {[(entity.unique_id, entity.native_value) for entity in all_entities]}")

                # Clean up
                await storage_manager.async_delete_sensor_set(sensor_set_id)

        finally:
            # Restore original state
            mock_entity_registry._entities.clear()
            mock_entity_registry._entities.update(original_entities)
            mock_states.clear()
            mock_states.update(original_states)


# =============================================================================
# HELPER METHODS FOR DEBUGGING
# =============================================================================


def debug_print_sensor_details(entity_lookup):
    """Helper to debug sensor details if test fails."""
    print("\n=== SENSOR DEBUG INFO ===")
    for unique_id, entity in entity_lookup.items():
        print(f"Sensor: {unique_id}")
        print(f"  Name: {getattr(entity, 'name', 'N/A')}")
        print(f"  Value: {getattr(entity, 'native_value', 'N/A')}")
        print(f"  Unit: {getattr(entity, 'native_unit_of_measurement', 'N/A')}")
        if hasattr(entity, "extra_state_attributes") and entity.extra_state_attributes:
            print(f"  Attributes: {entity.extra_state_attributes}")
        print()


def assert_computed_variable_validation_fix_works(entity_lookup):
    """Specific assertion helper for the computed variable validation fix."""

    # The key test: sensors with computed variables referencing globals must exist and have valid values
    critical_sensors = [
        "computed_variables_with_globals",  # Uses global vars in computed variables
        "span_like_grace_period",  # The exact failing SPAN pattern
        "mixed_computed_variables",  # Mixed local + global computed variables
    ]

    for sensor_id in critical_sensors:
        sensor = entity_lookup.get(sensor_id)
        assert sensor is not None, (
            f"Sensor '{sensor_id}' not found - computed variable validation fix failed. Available: {list(entity_lookup.keys())}"
        )

        assert sensor.native_value is not None, (
            f"Sensor '{sensor_id}' has None value - computed variables referencing globals failed"
        )

        assert str(sensor.native_value) not in ["unknown", "unavailable", ""], (
            f"Sensor '{sensor_id}' has invalid value '{sensor.native_value}' - computed variable evaluation failed"
        )

        print(f"✅ {sensor_id}: {sensor.native_value} (validation fix working)")
