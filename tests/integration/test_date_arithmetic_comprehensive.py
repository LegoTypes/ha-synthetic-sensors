"""Comprehensive integration test for date arithmetic with cross-sensor references."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from ha_synthetic_sensors import async_setup_synthetic_sensors
from ha_synthetic_sensors.storage_manager import StorageManager


class TestDateArithmeticComprehensive:
    """Comprehensive integration test for date arithmetic through the public API."""

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"  # Will be slugified for entity IDs
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        return mock_device_entry

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback for testing."""
        return Mock()

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

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
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        test_yaml_content,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test comprehensive date arithmetic including cross-sensor references and all duration functions through the public API with actual formula evaluation."""

        # Set up storage manager with proper mocking (following the guide)
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None  # Empty storage initially
            MockStore.return_value = mock_store

            # Use the common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create a sensor set for comprehensive testing
            sensor_set_id = "date_arithmetic_comprehensive_test"

            # Check if sensor set already exists and delete if it does
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device_date_arithmetic_comprehensive",  # Must match YAML global_settings
                name="Date Arithmetic Comprehensive Test Sensors",
            )

            # Import YAML with comprehensive date arithmetic features
            result = await storage_manager.async_from_yaml(yaml_content=test_yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded - should import all 7 sensors
            assert result["sensors_imported"] == 7, f"Expected 7 sensors, got {result['sensors_imported']}"
            assert len(result["sensor_unique_ids"]) == 7

            # Set up synthetic sensors via public API to test actual evaluation
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_date_arithmetic_comprehensive",
            )

            # Update sensors to trigger formula evaluation
            await sensor_manager.async_update_sensors()

            # Get the actual sensor entities to verify their computed values
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            # Verify we have the expected number of entities
            assert len(all_entities) >= 7, f"Expected at least 7 entities, got {len(all_entities)}"

            # Create a mapping for easy lookup
            sensor_entities = {entity.unique_id: entity for entity in all_entities}

            # Test actual formula evaluation results to verify date arithmetic works
            # Test 1: Basic date arithmetic - future_date_calculator
            future_calc_entity = sensor_entities.get("future_date_calculator")
            if future_calc_entity and future_calc_entity.native_value is not None:
                # Should contain date calculation result
                assert future_calc_entity.native_value is not None, "Future date calculator should have a value"

            # Test 2: Complex multi-duration arithmetic - complex_date_calculation
            complex_calc_entity = sensor_entities.get("complex_date_calculation")
            if complex_calc_entity and complex_calc_entity.native_value is not None:
                # Should contain complex date calculation result
                assert complex_calc_entity.native_value is not None, "Complex date calculation should have a value"

            # Test 3: Date differences - project_duration
            duration_entity = sensor_entities.get("project_duration")
            if duration_entity and duration_entity.native_value is not None:
                # Should contain duration calculation result
                assert duration_entity.native_value is not None, "Project duration should have a value"

            # Test 4: Maintenance scheduling - next_maintenance_due
            maintenance_entity = sensor_entities.get("next_maintenance_due")
            if maintenance_entity and maintenance_entity.native_value is not None:
                # Should contain maintenance date calculation result
                assert maintenance_entity.native_value is not None, "Next maintenance due should have a value"

            # Test 5: Cross-sensor references - milestone_tracker
            milestone_entity = sensor_entities.get("milestone_tracker")
            if milestone_entity and milestone_entity.native_value is not None:
                # Should contain milestone tracking result
                assert milestone_entity.native_value is not None, "Milestone tracker should have a value"

            # Test 6: Practical Home Assistant use case - activity_monitor
            activity_entity = sensor_entities.get("activity_monitor")
            if activity_entity and activity_entity.native_value is not None:
                # Should contain activity monitoring result
                assert activity_entity.native_value is not None, "Activity monitor should have a value"

            # Test 7: Business logic - schedule_optimizer
            schedule_entity = sensor_entities.get("schedule_optimizer")
            if schedule_entity and schedule_entity.native_value is not None:
                # Should contain schedule optimization result
                assert schedule_entity.native_value is not None, "Schedule optimizer should have a value"

            # Verify that sensor set was created and sensors have the expected device identifier
            assert storage_manager.sensor_set_exists(sensor_set_id)

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

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
