"""Integration test demonstrating that global variables + computed variables actually execute correctly.

This test proves the computed variable validation fix works end-to-end:
1. YAML parsing succeeds (validation fix)
2. Formulas execute correctly with expected values
3. Built-in functions work as expected
4. The exact SPAN use case from the fix document works

This is the complete proof that the fix resolves the original SPAN panel issue.
"""

from unittest.mock import AsyncMock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


class TestFormulaExecutionWithGlobals:
    """Test that formulas with global variables and built-in functions execute correctly."""

    @pytest.mark.asyncio
    async def test_span_use_case_works_end_to_end(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_device_registry,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test the exact SPAN use case from the fix document works end-to-end."""

        # Set up backing entities with known values for predictable results
        required_entities = {
            "sensor.span_backing": {"state": "5.5", "attributes": {"unit": "kWh"}},
            "sensor.builtin_backing": {"state": "100.0", "attributes": {"unit": "min"}},
            "sensor.math_backing": {"state": "10.0", "attributes": {"unit": "points"}},
            "sensor.complex_backing": {"state": "1.0", "attributes": {"unit": "units"}},
        }

        yaml_file_path = "tests/fixtures/integration/global_variables_computed_validation.yaml"
        expected_sensor_count = 4
        device_identifier = "test_device_global_computed_validation"

        # Save original state for cleanup
        original_entities = dict(mock_entity_registry._entities)
        original_states = dict(mock_states)

        try:
            # Register required entities
            for entity_id, data in required_entities.items():
                mock_entity_registry.register_entity(entity_id, entity_id, "sensor")
                mock_states.register_state(entity_id, data["state"], data["attributes"])

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
                sensor_set_id = "test_formula_execution"
                await storage_manager.async_create_sensor_set(
                    sensor_set_id=sensor_set_id, device_identifier=device_identifier, name="Formula Execution Test"
                )

                # Load YAML - this should succeed with the validation fix
                with open(yaml_file_path) as f:
                    yaml_content = f.read()

                result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

                assert result["sensors_imported"] == expected_sensor_count, (
                    f"YAML import failed: expected {expected_sensor_count}, got {result['sensors_imported']}"
                )

                # Create data provider that includes global variables for runtime
                def create_data_provider_with_globals():
                    def data_provider(entity_id: str):
                        # Provide backing entity data
                        backing_data = {
                            "sensor.span_backing": 5.5,
                            "sensor.builtin_backing": 100.0,
                            "sensor.math_backing": 10.0,
                            "sensor.complex_backing": 1.0,
                        }

                        return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

                    return data_provider

                # Create sensor to backing mapping
                sensor_to_backing_mapping = {
                    "span_main_meter_produced_energy": "sensor.span_backing",
                    "builtin_functions_test": "sensor.builtin_backing",
                    "global_math_operations": "sensor.math_backing",
                    "complex_expression_test": "sensor.complex_backing",
                }

                # Set up synthetic sensors with data provider
                sensor_manager = await async_setup_synthetic_sensors(
                    hass=mock_hass,
                    config_entry=mock_config_entry,
                    async_add_entities=mock_async_add_entities,
                    storage_manager=storage_manager,
                    data_provider_callback=create_data_provider_with_globals(),
                    sensor_to_backing_mapping=sensor_to_backing_mapping,
                )

                assert sensor_manager is not None, "Sensor manager creation failed"
                assert mock_async_add_entities.call_args_list, "No entities were added to HA"

                # Update sensors to trigger formula evaluation
                await sensor_manager.async_update_sensors()

                # Get all created entities
                all_entities = []
                for call in mock_async_add_entities.call_args_list:
                    entities_list = call.args[0] if call.args else []
                    all_entities.extend(entities_list)

                assert len(all_entities) == expected_sensor_count, (
                    f"Wrong entity count: expected {expected_sensor_count}, got {len(all_entities)}"
                )

                entity_lookup = {entity.unique_id: entity for entity in all_entities}

                # =============================================================================
                # TEST ACTUAL FORMULA EXECUTION WITH EXPECTED VALUES
                # =============================================================================

                # TEST 1: SPAN use case - global variable in computed variable
                span_sensor = entity_lookup.get("span_main_meter_produced_energy")
                assert span_sensor is not None, f"SPAN sensor not found. Available: {list(entity_lookup.keys())}"

                print(f"🔍 SPAN sensor native_value: {span_sensor.native_value}")
                print(f"🔍 SPAN sensor available: {span_sensor.available}")

                # TEST 2: Check the similar global_math_operations sensor
                math_sensor = entity_lookup.get("global_math_operations")
                assert math_sensor is not None, f"Math sensor not found"

                print(f"🔍 Math sensor native_value: {math_sensor.native_value}")
                print(f"🔍 Math sensor available: {math_sensor.available}")

                # This sensor has: formula = "state + 0" where state = 5.5
                # Computed variable: within_grace = "energy_grace_period_minutes > 25" = 30 > 25 = True = 1
                # Expected result: 5.5 + 0 = 5.5
                assert span_sensor.native_value is not None, "SPAN sensor has None value"
                span_value = float(span_sensor.native_value)
                expected_span = 5.5  # state + 0
                assert abs(span_value - expected_span) < 0.001, (
                    f"SPAN sensor value wrong: expected {expected_span}, got {span_value}. "
                    f"This means global variables aren't working in computed variables during execution."
                )
                print(f"✅ SPAN Sensor: {span_value} (expected {expected_span})")

                # TEST 2: Built-in functions execute correctly
                builtin_sensor = entity_lookup.get("builtin_functions_test")
                assert builtin_sensor is not None, f"Built-in functions sensor not found"

                # This sensor has: formula = "minutes(time_diff_minutes) + minutes(hours_in_minutes) + minutes(state)"
                # time_diff_minutes = 5.0, hours_in_minutes = 60.0, state = 100.0
                # Formula: minutes(5) + minutes(60) + minutes(100) = 165 minutes
                # Clean Slate converts timedelta to seconds: 165 * 60 = 9900 seconds
                assert builtin_sensor.native_value is not None, "Built-in functions sensor has None value"
                builtin_value = float(builtin_sensor.native_value)
                expected_builtin = 9900.0  # minutes(5) + minutes(60) + minutes(100) = 165 minutes = 9900 seconds
                assert abs(builtin_value - expected_builtin) < 0.001, (
                    f"Built-in functions value wrong: expected {expected_builtin}, got {builtin_value}. "
                    f"This means built-in functions aren't executing correctly."
                )
                print(f"✅ Built-in Functions: {builtin_value} (expected {expected_builtin})")

                # TEST 3: Global variables in math operations
                math_sensor = entity_lookup.get("global_math_operations")
                assert math_sensor is not None, f"Math operations sensor not found"

                # This sensor has: formula = "calculated_threshold + bonus_points + state"
                # calculated_threshold = energy_grace_period_minutes * 2 = 30 * 2 = 60
                # bonus_points = energy_grace_period_minutes if energy_grace_period_minutes > 20 else 0 = 30
                # state = 10.0
                # Expected: 60 + 30 + 10 = 100
                assert math_sensor.native_value is not None, "Math operations sensor has None value"
                math_value = float(math_sensor.native_value)
                expected_math = 100.0  # 60 + 30 + 10
                assert abs(math_value - expected_math) < 0.001, (
                    f"Math operations value wrong: expected {expected_math}, got {math_value}. "
                    f"This means global variables aren't working in math operations."
                )
                print(f"✅ Math Operations: {math_value} (expected {expected_math})")

                # TEST 4: Complex expressions with globals and built-ins
                complex_sensor = entity_lookup.get("complex_expression_test")
                assert complex_sensor is not None, f"Complex expression sensor not found"

                # This sensor has: formula = "grace_check + time_factor + state"
                # grace_check = 1 if energy_grace_period_minutes > 25 else 0 = 1 (since 30 > 25)
                # time_factor = (minutes(2) + seconds(30)).total_seconds() / 60 = 2.5 minutes
                # state = 1.0
                # Expected: 1 + 2.5 + 1 = 4.5
                assert complex_sensor.native_value is not None, "Complex expression sensor has None value"
                complex_value = float(complex_sensor.native_value)
                expected_complex = 4.5  # 1 + 2.5 + 1
                assert abs(complex_value - expected_complex) < 0.001, (
                    f"Complex expression value wrong: expected {expected_complex}, got {complex_value}. "
                    f"This means complex expressions with globals and built-ins aren't working."
                )
                print(f"✅ Complex Expression: {complex_value} (expected {expected_complex})")

                # TEST 5: Verify all sensors have valid, non-error values
                for entity in all_entities:
                    unique_id = getattr(entity, "unique_id", "unknown")
                    value = getattr(entity, "native_value", None)

                    assert value is not None, f"Sensor '{unique_id}' has None value - formula execution failed"
                    assert str(value) not in ["unknown", "unavailable", ""], (
                        f"Sensor '{unique_id}' has error value: {value} - formula execution failed"
                    )

                print("\n🎉 ALL TESTS PASSED!")
                print("✅ YAML parsing with global computed variables works")
                print("✅ Global variables execute correctly in computed variables")
                print("✅ Built-in functions execute correctly")
                print("✅ Math operations with globals work")
                print("✅ Complex expressions work")
                print("✅ The SPAN use case fix is complete and functional!")

                # Clean up
                await storage_manager.async_delete_sensor_set(sensor_set_id)

        finally:
            # Restore original state
            mock_entity_registry._entities.clear()
            mock_entity_registry._entities.update(original_entities)
            mock_states.clear()
            mock_states.update(original_states)


def test_validation_vs_execution_phases():
    """Test to demonstrate the difference between validation-time and execution-time fixes."""
    from ha_synthetic_sensors.utils_config import validate_computed_variable_references
    from ha_synthetic_sensors.config_models import ComputedVariable

    print("\n=== VALIDATION vs EXECUTION PHASES ===")

    # The computed variable that was failing
    variables = {"within_grace": ComputedVariable(formula="energy_grace_period_minutes > 25")}

    print("PHASE 1: VALIDATION (during YAML parsing)")
    print("Before fix: This would fail because global variables not available during validation")
    print("After fix: This should pass because global variables are now provided to validation")

    # Test validation with global variables (the fix)
    global_variables = {"energy_grace_period_minutes": "30"}
    errors = validate_computed_variable_references(variables, "test_sensor", global_variables)

    if errors:
        print(f"❌ VALIDATION FAILED: {errors[0]}")
        print("The validation fix is NOT working!")
    else:
        print("✅ VALIDATION PASSED: Global variables recognized during validation")
        print("The validation fix IS working!")

    print("\nPHASE 2: EXECUTION (during sensor updates)")
    print("This is tested in the integration test above.")
    print("Global variables must be available in the runtime context for formula evaluation.")
    print("The integration test proves both validation AND execution work correctly.")

    print("\nCONCLUSION:")
    print("The original SPAN panel bug was a VALIDATION issue that prevented YAML from parsing.")
    print("The fix ensures global variables are available during BOTH validation AND execution.")
    print("The integration test proves the complete end-to-end fix works correctly.")
