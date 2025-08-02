"""Comprehensive integration test for date arithmetic with cross-sensor references."""

import pytest
from unittest.mock import AsyncMock, patch

from ha_synthetic_sensors.storage_manager import StorageManager


class TestDateArithmeticComprehensive:
    """Comprehensive integration test for date arithmetic through the public API."""

    @pytest.fixture
    def test_yaml_path(self):
        """Path to the comprehensive test YAML fixture."""
        return "tests/fixtures/integration/date_arithmetic_comprehensive.yaml"

    @pytest.fixture
    def test_yaml_content(self, test_yaml_path):
        """Load the comprehensive test YAML content."""
        with open(test_yaml_path, "r", encoding="utf-8") as f:
            return f.read()

    async def test_comprehensive_date_arithmetic_integration(
        self, mock_hass, mock_entity_registry, mock_states, test_yaml_content
    ):
        """Test comprehensive date arithmetic including cross-sensor references and all duration functions."""

        # Create storage manager with mocked Store
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None  # Empty storage initially
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create a sensor set for comprehensive testing
            sensor_set_id = "date_arithmetic_comprehensive_test"

            # Check if sensor set already exists and delete if it does
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import YAML with comprehensive date arithmetic features
            result = await storage_manager.async_from_yaml(yaml_content=test_yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded - should import all 7 sensors
            assert result["sensors_imported"] == 7, f"Expected 7 sensors, got {result['sensors_imported']}"
            assert len(result["sensor_unique_ids"]) == 7

            # Get the stored sensors
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 7

            # Verify each sensor type exists and has correct configuration
            sensor_by_id = {sensor.unique_id: sensor for sensor in sensors}

            # Test 1: Basic date arithmetic
            future_calc = sensor_by_id["future_date_calculator"]
            assert future_calc.name == "Future Date Calculator"
            # Should use date() + days() functions

            # Test 2: Complex multi-duration arithmetic
            complex_calc = sensor_by_id["complex_date_calculation"]
            assert complex_calc.name == "Complex Date Calculation"
            # Should use multiple duration functions: weeks(), days(), hours()

            # Test 3: Date differences
            duration_sensor = sensor_by_id["project_duration"]
            assert duration_sensor.name == "Project Duration"
            # Should calculate date difference

            # Test 4: Maintenance scheduling with variables
            maintenance_sensor = sensor_by_id["next_maintenance_due"]
            assert maintenance_sensor.name == "Next Maintenance Due"
            # Should use months() duration function

            # Test 5: Cross-sensor references with attributes
            milestone_sensor = sensor_by_id["milestone_tracker"]
            assert milestone_sensor.name == "Milestone Tracker"
            # Should have multiple formula configs (main + attributes)
            assert len(milestone_sensor.formulas) >= 3  # Main formula + 2 attributes

            # Test 6: Practical Home Assistant use case
            activity_sensor = sensor_by_id["activity_monitor"]
            assert activity_sensor.name == "Activity Monitor"
            # Should have time-based attributes (main + 2 attributes)
            assert len(activity_sensor.formulas) >= 3

            # Test 7: Business logic with conditional date arithmetic
            schedule_sensor = sensor_by_id["schedule_optimizer"]
            assert schedule_sensor.name == "Schedule Optimizer"
            # Should have conditional logic and business hours calculation (main + 2 attributes)
            assert len(schedule_sensor.formulas) >= 3

            # Verify that sensor set was created and sensors have the expected device identifier
            assert storage_manager.sensor_set_exists(sensor_set_id)

            # Verify that all sensors have the correct device identifier from global settings
            for sensor in sensors:
                assert sensor.device_identifier == "test_device_date_arithmetic_comprehensive"

    async def test_date_function_validation_integration(self, mock_hass, mock_entity_registry, mock_states):
        """Test that date function validation works correctly through the public API."""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "date_validation_test"

            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Test all duration functions are recognized in validation
            yaml_content = """
version: "1.0"

global_settings:
  device_identifier: "test_device_date_validation"

sensors:
  # Test all duration functions
  duration_functions_test:
    name: "Duration Functions Test"
    formula: "1"  # Simple base formula
    attributes:
      test_seconds: seconds(30)
      test_minutes: minutes(15)
      test_hours: hours(6)
      test_days: days(7)
      test_weeks: weeks(2)
      test_months: months(3)

  # Test date function with variables
  date_with_variables:
    name: "Date With Variables"
    formula: "date(start_time)"
    variables:
      start_time: "2025-01-01T12:00:00"
    metadata:
      device_class: "timestamp"
"""

            # Import should succeed - validates that all functions are recognized
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 2, f"Expected 2 sensors, got {result['sensors_imported']}"

            # Verify sensors were created with attributes
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 2

            duration_test_sensor = next(s for s in sensors if s.unique_id == "duration_functions_test")

            # Verify that the sensor was created (validation passed for all duration functions)
            assert duration_test_sensor.name == "Duration Functions Test"

            # Verify the main formula exists
            assert len(duration_test_sensor.formulas) >= 1

    async def test_formula_routing_integration(self, mock_hass, mock_entity_registry, mock_states):
        """Test that formula routing correctly identifies date arithmetic formulas."""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "formula_routing_test"

            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Test formulas that should be routed to different evaluators
            yaml_content = """
version: "1.0"

global_settings:
  device_identifier: "test_device_formula_routing"

sensors:
  # Should route to DateHandler (has date() function)
  date_function_test:
    name: "Date Function Test"
    formula: "date('2025-01-01')"
    metadata:
      device_class: "date"

  # Should route to DateHandler (has duration functions)
  duration_arithmetic_test:
    name: "Duration Arithmetic Test"
    formula: "date('2025-01-01') + days(30)"
    metadata:
      device_class: "date"

  # Should route to StringHandler (has string literals)
  string_operation_test:
    name: "String Operation Test"
    formula: "'Hello ' + 'World'"
    metadata:
      device_class: "enum"

  # Should route to NumericHandler (default)
  numeric_calculation_test:
    name: "Numeric Calculation Test"
    formula: "42 * 1.5"
    metadata:
      unit_of_measurement: "units"
"""

            # Import should succeed with proper routing
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 4, f"Expected 4 sensors, got {result['sensors_imported']}"

            # Verify all sensors were created successfully
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 4

            sensor_names = [s.unique_id for s in sensors]
            expected_names = [
                "date_function_test",
                "duration_arithmetic_test",
                "string_operation_test",
                "numeric_calculation_test",
            ]

            for expected_name in expected_names:
                assert expected_name in sensor_names, f"Missing sensor: {expected_name}"
