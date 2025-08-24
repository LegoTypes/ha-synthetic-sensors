"""Focused test for the computed variable validation fix.

This test specifically verifies that the computed variable validation bug was fixed:
- Before fix: YAML parsing would fail with validation errors
- After fix: YAML parsing succeeds (we test that)

The runtime evaluation is a separate concern tested elsewhere.
"""

from unittest.mock import AsyncMock, patch

import pytest

from ha_synthetic_sensors import StorageManager


class TestComputedVariableValidationFix:
    """Test the specific validation fix for computed variables referencing global variables."""

    @pytest.mark.asyncio
    async def test_yaml_parsing_with_global_computed_variables_succeeds(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_device_registry,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test that YAML with computed variables referencing globals can be parsed successfully.

        This is the core test for the validation fix described in computed_variable_validation_fix.md.
        Before the fix, this YAML would fail to parse with computed variable validation errors.
        After the fix, the YAML parsing should succeed.
        """

        # Create simple YAML that would have failed before the fix
        test_yaml = """
version: "1.0"

global_settings:
  device_identifier: "test_device_validation_fix"
  variables:
    # Global variables that computed variables will reference
    energy_grace_period_minutes: "30"
    power_threshold_watts: "500"

sensors:
  # Simple sensor that would have failed validation before the fix
  test_sensor:
    name: "Test Global Computed Variables"
    formula: "state + 0"
    variables:
      # This computed variable references a global variable
      # Before the fix: would cause validation error during YAML parsing
      # After the fix: should parse successfully
      within_grace:
        formula: "energy_grace_period_minutes > 25"
        alternate_states:
          UNAVAILABLE: "false"
      # This computed variable also references a global variable
      above_threshold:
        formula: "power_threshold_watts > 400"
        alternate_states:
          UNAVAILABLE: "false"
      # This computed variable uses built-in functions
      # Before the fix: minutes() would not be recognized during validation
      # After the fix: should be recognized as a valid built-in function
      time_calculation:
        formula: "minutes(30) + hours(2)"
        alternate_states:
          UNAVAILABLE: "0"
"""

        # Save original state for cleanup
        original_entities = dict(mock_entity_registry._entities)
        original_states = dict(mock_states)

        try:
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
                sensor_set_id = "test_validation_fix"
                await storage_manager.async_create_sensor_set(
                    sensor_set_id=sensor_set_id, device_identifier="test_device_validation_fix", name="Validation Fix Test"
                )

                # THIS IS THE CRITICAL TEST: YAML parsing should succeed
                # Before the fix, this would raise ConfigEntryError with computed variable validation failure
                result = await storage_manager.async_from_yaml(yaml_content=test_yaml, sensor_set_id=sensor_set_id)

                # If we get here, the validation fix worked!
                assert result["sensors_imported"] == 1, (
                    f"YAML import failed: expected 1 sensor, got {result['sensors_imported']}. "
                    f"This indicates the computed variable validation fix didn't work. Result: {result}"
                )

                print("✅ SUCCESS: YAML with computed variables referencing globals parsed successfully!")
                print(f"✅ Sensors imported: {result['sensors_imported']}")
                print("✅ The computed variable validation fix is working correctly")

                # Verify the sensors exist in storage (they should, since import succeeded)
                sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
                assert len(sensors) == 1, f"Expected 1 sensor in storage, got {len(sensors)}"

                sensor = sensors[0]
                assert sensor.unique_id == "test_sensor", f"Wrong sensor unique_id: {sensor.unique_id}"

                # Verify the computed variables are present (they should be, since validation passed)
                formula = sensor.formulas[0]  # Main formula
                computed_vars = [name for name, var in formula.variables.items() if hasattr(var, "formula")]
                expected_computed_vars = ["within_grace", "above_threshold", "time_calculation"]

                for expected_var in expected_computed_vars:
                    assert expected_var in computed_vars, (
                        f"Computed variable '{expected_var}' not found. Available: {computed_vars}. "
                        f"This indicates the validation fix has a problem."
                    )

                print(f"✅ Computed variables found: {computed_vars}")

                # Clean up
                await storage_manager.async_delete_sensor_set(sensor_set_id)

        finally:
            # Restore original state
            mock_entity_registry._entities.clear()
            mock_entity_registry._entities.update(original_entities)
            mock_states.clear()
            mock_states.update(original_states)

    @pytest.mark.asyncio
    async def test_validation_fix_prevents_false_positives(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_device_registry,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test that the validation fix doesn't create false positives for actual errors."""

        # Create YAML with an actual validation error (truly undefined variable)
        test_yaml_with_real_error = """
version: "1.0"

global_settings:
  device_identifier: "test_device_validation_fix_errors"
  variables:
    valid_global: "30"

sensors:
  test_sensor:
    name: "Test Real Validation Error"
    formula: "state + 0"
    variables:
      # This should pass validation (references valid global)
      valid_computed:
        formula: "valid_global > 25"
        alternate_states:
          UNAVAILABLE: "false"
      # This should fail validation (references truly undefined variable)
      invalid_computed:
        formula: "truly_undefined_variable > 50"
        alternate_states:
          UNAVAILABLE: "false"
"""

        # Save original state for cleanup
        original_entities = dict(mock_entity_registry._entities)
        original_states = dict(mock_states)

        try:
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

                sensor_set_id = "test_validation_errors"
                await storage_manager.async_create_sensor_set(
                    sensor_set_id=sensor_set_id,
                    device_identifier="test_device_validation_fix_errors",
                    name="Validation Error Test",
                )

                # This should fail with a validation error (the fix shouldn't prevent real errors)
                with pytest.raises(Exception) as exc_info:
                    await storage_manager.async_from_yaml(yaml_content=test_yaml_with_real_error, sensor_set_id=sensor_set_id)

                # Verify it failed for the right reason (undefined variable, not global variable access)
                error_message = str(exc_info.value)
                assert "truly_undefined_variable" in error_message, (
                    f"Expected error about 'truly_undefined_variable', got: {error_message}"
                )

                print("✅ SUCCESS: Validation still catches real errors correctly")
                print(f"✅ Error message: {error_message}")

                # Clean up (sensor set might not exist if creation failed)
                try:
                    await storage_manager.async_delete_sensor_set(sensor_set_id)
                except:
                    pass

        finally:
            # Restore original state
            mock_entity_registry._entities.clear()
            mock_entity_registry._entities.update(original_entities)
            mock_states.clear()
            mock_states.update(original_states)


def test_computed_variable_validation_direct():
    """Direct test of the computed variable validation function fix."""
    from ha_synthetic_sensors.utils_config import validate_computed_variable_references
    from ha_synthetic_sensors.config_models import ComputedVariable

    # Test the exact scenario that was failing before the fix
    variables = {"within_grace": ComputedVariable(formula="energy_grace_period_minutes > 25")}

    # Before fix: This would return validation errors because global vars not available
    # After fix: This should pass when global variables are provided
    global_variables = {"energy_grace_period_minutes": "30"}

    errors = validate_computed_variable_references(variables, "test_sensor", global_variables)

    assert len(errors) == 0, (
        f"Computed variable validation failed: {errors}. "
        f"This indicates the global variables fix isn't working in the validation function."
    )

    # Test built-in functions are recognized
    builtin_variables = {"time_calc": ComputedVariable(formula="minutes(30) + hours(2)")}

    errors = validate_computed_variable_references(builtin_variables, "test_sensor")

    assert len(errors) == 0, (
        f"Built-in function validation failed: {errors}. This indicates the built-in functions fix isn't working."
    )

    print("✅ SUCCESS: Direct validation function tests pass")
    print("✅ Global variables are properly recognized during validation")
    print("✅ Built-in functions are properly recognized during validation")
