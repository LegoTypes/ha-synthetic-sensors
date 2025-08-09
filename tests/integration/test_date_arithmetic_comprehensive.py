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
        """Test that date arithmetic sensors can be created and imported successfully."""

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

            # Verify sensors were created with the expected configurations
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 7

            # Verify each expected sensor exists and has correct formula structure
            expected_sensors = {
                "future_date_calculator": "date(project_start_date) + days(30)",
                "complex_date_calculation": "date(project_start_date) + weeks(4) + days(3) + hours(12)",
                "project_duration": "date(end_date) - date(project_start_date)",
                "next_maintenance_due": "date(last_service_date) + months(maintenance_interval_months)",
                "milestone_tracker": "date(project_start_date) + days(progress_days)",
                "activity_monitor": "1",  # Simple numeric formula that should work
                "schedule_optimizer": "date(base_schedule_date) + days(optimization_offset)",
            }

            sensor_map = {sensor.unique_id: sensor for sensor in sensors}

            for sensor_id, expected_formula in expected_sensors.items():
                assert sensor_id in sensor_map, f"Missing sensor: {sensor_id}"
                sensor = sensor_map[sensor_id]
                assert len(sensor.formulas) >= 1, f"Sensor {sensor_id} should have at least one formula"
                main_formula = sensor.formulas[0]
                assert main_formula.formula == expected_formula, (
                    f"Sensor {sensor_id}: expected formula '{expected_formula}', got '{main_formula.formula}'"
                )

            # Verify date-related metadata is preserved
            future_calc_sensor = sensor_map["future_date_calculator"]
            assert future_calc_sensor.metadata.get("device_class") == "date"

            project_duration_sensor = sensor_map["project_duration"]
            assert project_duration_sensor.metadata.get("unit_of_measurement") == "d"
            assert project_duration_sensor.metadata.get("device_class") == "duration"

            # Verify global variables are accessible
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)
            global_settings = sensor_set.get_global_settings()
            assert global_settings is not None
            variables = global_settings.get("variables", {})
            assert "project_start_date" in variables
            assert variables["project_start_date"] == "2025-01-01"
            assert "maintenance_interval_months" in variables
            assert variables["maintenance_interval_months"] == 6

            # Verify attribute formulas exist where expected
            milestone_sensor = sensor_map["milestone_tracker"]
            # Attribute formulas have IDs that aren't "main" (they are the attribute names)
            attribute_formulas = [f for f in milestone_sensor.formulas if f.id != "main"]
            assert len(attribute_formulas) >= 2, "Milestone tracker should have attribute formulas"

            activity_sensor = sensor_map["activity_monitor"]
            activity_attribute_formulas = [f for f in activity_sensor.formulas if f.id != "main"]
            assert len(activity_attribute_formulas) >= 2, "Activity monitor should have attribute formulas"

            # Test that the system properly validates date functions
            # This verifies the formula routing and validation worked correctly during import
            for sensor in sensors:
                for formula in sensor.formulas:
                    # Should not contain validation errors or empty formulas
                    assert formula.formula is not None and formula.formula.strip() != "", (
                        f"Empty formula in sensor {sensor.unique_id}"
                    )

            # Verify that sensor set was created and has expected metadata
            assert storage_manager.sensor_set_exists(sensor_set_id)
            device_identifier = global_settings.get("device_identifier")
            assert device_identifier == "test_device_date_arithmetic_comprehensive"

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
