"""Integration tests for string operations."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from ha_synthetic_sensors.storage_manager import StorageManager


class TestStringOperationsIntegration:
    """Integration tests for string operations through the public API."""

    async def test_basic_string_concatenation(self, mock_hass, mock_entity_registry, mock_states):
        """Test basic string concatenation operations."""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "string_operations_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Load string operations YAML fixture
            yaml_fixture_path = "tests/fixtures/integration/string_operations_basic.yaml"
            with open(yaml_fixture_path, "r") as f:
                string_yaml = f.read()

            # Import string operations YAML - should succeed
            result = await storage_manager.async_from_yaml(yaml_content=string_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Verify sensors were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Verify string concatenation sensor
            string_sensor = next((s for s in sensors if "string_concatenation" in s.unique_id), None)
            assert string_sensor is not None
            assert string_sensor.name == "String Concatenation Test"

            # Verify mixed string variable sensor
            mixed_sensor = next((s for s in sensors if "mixed_string_variable" in s.unique_id), None)
            assert mixed_sensor is not None
            assert mixed_sensor.name == "Mixed String Variable Test"

            # Verify numeric default sensor (should still work)
            numeric_sensor = next((s for s in sensors if "numeric_default" in s.unique_id), None)
            assert numeric_sensor is not None
            assert numeric_sensor.name == "Numeric Default Test"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_string_operations_with_existing_validation(self, mock_hass, mock_entity_registry, mock_states):
        """Test that string operations work with existing validation system."""

        # Test YAML with string operations that should pass validation
        valid_string_yaml = """
version: "1.0"

global_settings:
  device_identifier: "string_validation_device"

sensors:
  valid_string_sensor:
    name: "Valid String Operations"
    formula: "'Power: ' + state + 'W'"
    variables:
      state: "sensor.power_meter"
    metadata:
      unit_of_measurement: ""
      device_class: "enum"
      state_class: "measurement"

  valid_numeric_sensor:
    name: "Valid Numeric Operations"
    formula: "state * 1.1"
    variables:
      state: "sensor.power_meter"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "string_validation_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import string operations YAML - should pass validation
            result = await storage_manager.async_from_yaml(yaml_content=valid_string_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 2, f"Expected 2 sensors, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_formula_router_integration(self, mock_hass, mock_entity_registry, mock_states):
        """Test that the formula router correctly routes different formula types."""

        # Test YAML with different formula types to verify routing
        routing_test_yaml = """
version: "1.0"

global_settings:
  device_identifier: "routing_test_device"

sensors:
  string_literal_sensor:
    name: "String Literal Routing"
    formula: "'Static String Value'"
    metadata:
      unit_of_measurement: ""
      device_class: "enum"

  numeric_formula_sensor:
    name: "Numeric Formula Routing"
    formula: "42 * 2"
    metadata:
      unit_of_measurement: ""
      device_class: "enum"

  collection_function_sensor:
    name: "Collection Function Routing"
    formula: "count('device_class:power')"
    metadata:
      unit_of_measurement: "devices"
      device_class: "enum"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "routing_integration_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import routing test YAML - should succeed and route correctly
            result = await storage_manager.async_from_yaml(yaml_content=routing_test_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Verify all sensors were created (routing worked)
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_backward_compatibility_with_existing_formulas(self, mock_hass, mock_entity_registry, mock_states):
        """Test that existing numeric formulas continue to work unchanged."""

        # Use existing validation test YAML to ensure backward compatibility
        existing_formula_yaml = """
version: "1.0"

global_settings:
  device_identifier: "compatibility_test_device"

sensors:
  existing_power_sensor:
    name: "Existing Power Calculation"
    formula: "sensor.panel_power * 1.1"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"

  existing_count_sensor:
    name: "Existing Device Count"
    formula: "count('device_class:power')"
    metadata:
      unit_of_measurement: "devices"
      device_class: "enum"

  existing_sum_sensor:
    name: "Existing Power Sum"
    formula: "sum('device_class:power')"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
      state_class: "measurement"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "backward_compatibility_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import existing formula patterns - should continue to work
            result = await storage_manager.async_from_yaml(yaml_content=existing_formula_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded (existing formulas still work)
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_advanced_string_functions_integration(self, mock_hass, mock_entity_registry, mock_states):
        """Test advanced string functions through the public API."""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "advanced_string_operations_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Load advanced string operations YAML fixture
            yaml_fixture_path = "tests/fixtures/integration/string_operations_advanced.yaml"
            with open(yaml_fixture_path, "r") as f:
                advanced_string_yaml = f.read()

            # Import advanced string operations YAML - should succeed
            result = await storage_manager.async_from_yaml(yaml_content=advanced_string_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded (20 sensors: 16 original + 4 normalization functions)
            expected_sensors = 20
            assert result["sensors_imported"] == expected_sensors, (
                f"Expected {expected_sensors} sensors, got {result['sensors_imported']}"
            )

            # Verify sensors were created
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == expected_sensors

            # Verify specific advanced function sensors exist
            sensor_names = [s.name for s in sensors]

            # Basic string functions
            assert "Trim Function Test" in sensor_names
            assert "Case Functions Test" in sensor_names

            # Substring functions
            assert "Contains Function Test" in sensor_names
            assert "Startswith Function Test" in sensor_names
            assert "Endswith Function Test" in sensor_names

            # Analysis functions
            assert "Length Function Test" in sensor_names
            assert "Length Variable Test" in sensor_names

            # Replacement functions
            assert "Replace Function Test" in sensor_names
            assert "Replace Variable Test" in sensor_names

            # Complex combinations
            assert "Nested Functions Test" in sensor_names
            assert "Concatenation with Functions Test" in sensor_names
            assert "Complex Parameters Test" in sensor_names
            assert "Mixed Operations Test" in sensor_names
            assert "Boolean Result Concatenation Test" in sensor_names

            # Backward compatibility
            assert "Numeric Formula Compatibility" in sensor_names
            assert "Collection Function Compatibility" in sensor_names

            # Verify specific sensor configurations
            trim_sensor = next((s for s in sensors if "trim_function" in s.unique_id), None)
            assert trim_sensor is not None
            assert trim_sensor.name == "Trim Function Test"

            contains_sensor = next((s for s in sensors if "contains_function" in s.unique_id), None)
            assert contains_sensor is not None
            assert contains_sensor.name == "Contains Function Test"

            length_sensor = next((s for s in sensors if "length_function" in s.unique_id), None)
            assert length_sensor is not None
            assert length_sensor.name == "Length Function Test"

            replace_sensor = next((s for s in sensors if "replace_function" in s.unique_id), None)
            assert replace_sensor is not None
            assert replace_sensor.name == "Replace Function Test"

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_string_function_parameter_validation_integration(self, mock_hass, mock_entity_registry, mock_states):
        """Test that parameter validation works correctly in integration context."""

        # Test YAML with invalid parameter counts
        invalid_param_yaml = """
version: "1.0"

global_settings:
  device_identifier: "invalid_param_test_device"

sensors:
  invalid_contains_sensor:
    name: "Invalid Contains Parameters"
    formula: "contains('only_one_param')"
    metadata:
      unit_of_measurement: ""
      device_class: "enum"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "invalid_param_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import invalid parameter YAML - should fail gracefully
            try:
                result = await storage_manager.async_from_yaml(yaml_content=invalid_param_yaml, sensor_set_id=sensor_set_id)
                # If it doesn't raise an exception, it should import 0 sensors
                assert result["sensors_imported"] == 0, "Invalid parameter syntax should not create sensors"
            except Exception as e:
                # Should raise a validation or syntax error
                assert any(keyword in str(e).lower() for keyword in ["parameter", "syntax", "requires"]), (
                    f"Error should mention parameter validation: {e}"
                )

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_string_functions_with_real_variables_integration(self, mock_hass, mock_entity_registry, mock_states):
        """Test string functions with realistic variable scenarios."""

        # Setup mock states for more realistic testing
        mock_states.return_value = [
            Mock(
                entity_id="sensor.living_room_temperature", state="23.5", attributes={"device_name": "Living Room Temp Sensor"}
            ),
            Mock(entity_id="sensor.kitchen_humidity", state="45.2", attributes={"device_name": "Kitchen Humidity Sensor"}),
            Mock(entity_id="sensor.device_status", state="online_active", attributes={"friendly_name": "Device Status"}),
        ]

        realistic_variables_yaml = """
version: "1.0"

global_settings:
  device_identifier: "realistic_variables_test_device"

sensors:
  device_name_analysis_sensor:
    name: "Device Name Analysis"
    formula: "'Name: ' + trim(device_name) + ' | Contains Temp: ' + contains(device_name, 'Temp') + ' | Length: ' + length(device_name)"
    variables:
      device_name: "sensor.living_room_temperature.device_name"
    metadata:
      unit_of_measurement: ""
      device_class: "enum"

  status_processing_sensor:
    name: "Status Processing"
    formula: "'Status: ' + replace(upper(status), '_', ' ') + ' | Starts Online: ' + startswith(status, 'online')"
    variables:
      status: "sensor.device_status"
    metadata:
      unit_of_measurement: ""
      device_class: "enum"

  multi_device_comparison_sensor:
    name: "Multi Device Comparison"
    formula: "'Temp Length: ' + length(temp_name) + ' | Humidity Length: ' + length(humidity_name) + ' | Same Type: ' + contains(temp_name, 'Sensor')"
    variables:
      temp_name: "sensor.living_room_temperature.device_name"
      humidity_name: "sensor.kitchen_humidity.device_name"
    metadata:
      unit_of_measurement: ""
      device_class: "enum"
"""

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "realistic_variables_test"

            # Clean up if exists
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import realistic variables YAML - should succeed
            result = await storage_manager.async_from_yaml(yaml_content=realistic_variables_yaml, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 3, f"Expected 3 sensors, got {result['sensors_imported']}"

            # Verify sensors were created with realistic configurations
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            sensor_names = [s.name for s in sensors]
            assert "Device Name Analysis" in sensor_names
            assert "Status Processing" in sensor_names
            assert "Multi Device Comparison" in sensor_names

            # Cleanup
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock AddEntitiesCallback."""
        return Mock()

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        return mock_device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    async def test_string_normalization_functions_integration(
        self, mock_hass, mock_entity_registry, mock_states, mock_config_entry, mock_async_add_entities, mock_device_registry
    ):
        """Test string normalization functions through the public API."""

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock setup
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            # Use common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load YAML configuration
            sensor_set_id = "string_normalization_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="String Normalization Test Sensors"
            )

            # Load the string normalization fixture
            fixture_path = "tests/fixtures/integration/string_normalization.yaml"
            with open(fixture_path, "r") as f:
                yaml_content = f.read()

            # Import string normalization YAML - should pass validation
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 16, f"Expected 16 sensors, got {result['sensors_imported']}"

            # Set up synthetic sensors via public API
            from ha_synthetic_sensors import async_setup_synthetic_sensors

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
            )

            # Verify sensors were created via public API
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test the functionality using public API - update sensors
            await sensor_manager.async_update_sensors()

            # Verify sensors were created with correct configurations
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 16

            # Get created sensor entities and verify their states
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0]  # First argument is the list of entities
                for entity in entities_list:
                    all_entities.append(entity)

            sensor_entities = {entity.unique_id: entity for entity in all_entities}
            assert len(sensor_entities) == 16, f"Expected 16 entities, got {len(sensor_entities)}"

            # Test string normalization functions
            normalize_entity = sensor_entities["test_normalize_whitespace"]
            assert normalize_entity.native_value == "hello world"  # Normalized whitespace

            clean_entity = sensor_entities["test_clean_special_chars"]
            assert clean_entity.native_value == "devicename123"  # Special chars removed

            sanitize_entity = sensor_entities["test_sanitize_spaces"]
            assert sanitize_entity.native_value == "hello_world"  # Spaces replaced with underscores

            # Test complex nested expression
            complex_entity = sensor_entities["test_complex_device_name_normalization"]
            assert complex_entity.native_value == "SmartDevice1"  # Clean -> normalize -> sanitize pipeline

            # Test string concatenation
            concat_entity = sensor_entities["test_concatenation_with_normalize"]
            assert concat_entity.native_value == "Cleaned: hello world"  # String concatenation working

            # Test additional functions
            clean_keep_entity = sensor_entities["test_clean_keep_spaces"]
            assert clean_keep_entity.native_value == "hello world 123"  # Clean preserves spaces in alphanumeric

            sanitize_special_entity = sensor_entities["test_sanitize_special_chars"]
            assert sanitize_special_entity.native_value == "device_name_123"  # Hyphens and @ replaced with underscores

            # Cleanup
            await storage_manager.async_delete_sensor_set(sensor_set_id)
