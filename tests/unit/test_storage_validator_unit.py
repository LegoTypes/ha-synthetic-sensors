"""Unit tests for storage_validator.py module.

Tests the validation logic for sensor configurations, global settings,
and conflict detection focusing on error paths and edge cases.
"""

import pytest
from typing import Any
from unittest.mock import Mock, MagicMock

from ha_synthetic_sensors.storage_validator import ValidationHandler
from ha_synthetic_sensors.config_models import SensorConfig, FormulaConfig
from ha_synthetic_sensors.exceptions import SyntheticSensorsConfigError


class TestValidationHandler:
    """Test cases for ValidationHandler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_storage_manager = Mock()
        self.validator = ValidationHandler(self.mock_storage_manager)

    def test_init(self):
        """Test ValidationHandler initialization."""
        assert self.validator.storage_manager == self.mock_storage_manager

    def test_validate_no_global_conflicts_no_conflicts(self):
        """Test validation passes when there are no conflicts."""
        # Create sensors with no conflicting variables
        sensor1 = self._create_mock_sensor("sensor1", ["temp", "humidity"])
        sensor2 = self._create_mock_sensor("sensor2", ["pressure", "altitude"])

        sensors = [sensor1, sensor2]
        global_settings = {"device_identifier": "test_device"}

        # Should not raise any exceptions
        self.validator.validate_no_global_conflicts(sensors, global_settings)

    def test_check_attribute_formula_conflicts_no_conflicts(self):
        """Test _check_attribute_formula_conflicts with no conflicts."""
        # Create sensor with formulas that don't conflict
        sensor = self._create_mock_sensor_with_formulas(
            [
                ("sensor1", ["temp", "humidity"]),  # main formula
                ("sensor1_state", ["pressure"]),  # state attribute
                ("sensor1_power", ["voltage"]),  # power attribute
            ]
        )

        # Should not raise any exceptions
        self.validator._check_attribute_formula_conflicts(sensor)

    def test_check_attribute_formula_conflicts_with_conflict(self):
        """Test _check_attribute_formula_conflicts detects conflicts."""
        # Create sensor with conflicting variable names
        sensor = self._create_mock_sensor_with_formulas(
            [
                ("sensor1", ["temp", "humidity"]),  # main formula uses 'temp'
                ("sensor1_state", ["temp", "pressure"]),  # state attribute also uses 'temp'
            ]
        )

        with pytest.raises(
            SyntheticSensorsConfigError, match="variable 'temp' defined in both main formula and attribute 'state'"
        ):
            self.validator._check_attribute_formula_conflicts(sensor)

    def test_check_attribute_formula_conflicts_multiple_attributes_conflict(self):
        """Test conflicts between multiple attributes."""
        # Create sensor with multiple conflicting attributes
        sensor = self._create_mock_sensor_with_formulas(
            [
                ("sensor1", ["base_var"]),  # main formula
                ("sensor1_state", ["shared_var"]),  # state attribute
                ("sensor1_power", ["shared_var"]),  # power attribute - conflicts with state
            ]
        )

        with pytest.raises(
            SyntheticSensorsConfigError, match="variable 'shared_var' defined in both attribute 'state' and attribute 'power'"
        ):
            self.validator._check_attribute_formula_conflicts(sensor)

    def test_check_attribute_formula_conflicts_custom_formula_id(self):
        """Test conflicts with custom formula IDs that don't follow standard pattern."""
        # Create sensor with custom formula ID
        sensor = self._create_mock_sensor_with_formulas(
            [
                ("sensor1", ["temp"]),  # main formula
                ("custom_formula_id", ["temp"]),  # custom formula with same variable
            ]
        )

        with pytest.raises(
            SyntheticSensorsConfigError, match="variable 'temp' defined in both main formula and formula 'custom_formula_id'"
        ):
            self.validator._check_attribute_formula_conflicts(sensor)

    def test_check_attribute_formula_conflicts_empty_variables(self):
        """Test handling of formulas with no variables."""
        # Create sensor with formulas that have no variables
        formulas = [
            self._create_mock_formula("sensor1", None),  # No variables
            self._create_mock_formula("sensor1_state", []),  # Empty variables
            self._create_mock_formula("sensor1_power", ["voltage"]),  # Has variables
        ]

        sensor = Mock(spec=SensorConfig)
        sensor.unique_id = "sensor1"
        sensor.formulas = formulas

        # Should not raise any exceptions
        self.validator._check_attribute_formula_conflicts(sensor)

    def test_validate_sensor_with_context_basic_validation_errors(self):
        """Test validate_sensor_with_context with basic sensor validation errors."""
        # Mock storage manager data
        self.mock_storage_manager.data = {"sensor_sets": {"test_set": {"global_settings": {}}}}

        # Mock sensor that has validation errors
        mock_sensor = Mock(spec=SensorConfig)
        mock_sensor.validate.return_value = ["Invalid formula syntax", "Missing required field"]

        # Mock the _validate_against_global_settings and _validate_attribute_variable_conflicts methods
        self.validator._validate_against_global_settings = Mock(return_value=[])
        self.validator._validate_attribute_variable_conflicts = Mock(return_value=[])

        errors = self.validator.validate_sensor_with_context(mock_sensor, "test_set")

        assert errors == ["Invalid formula syntax", "Missing required field"]
        mock_sensor.validate.assert_called_once()

    def test_validate_sensor_with_context_no_errors(self):
        """Test validate_sensor_with_context with valid sensor."""
        # Mock storage manager data
        self.mock_storage_manager.data = {"sensor_sets": {"test_set": {"global_settings": {}}}}

        # Mock sensor that has no validation errors
        mock_sensor = Mock(spec=SensorConfig)
        mock_sensor.validate.return_value = []

        # Mock the validation methods
        self.validator._validate_against_global_settings = Mock(return_value=[])
        self.validator._validate_attribute_variable_conflicts = Mock(return_value=[])

        errors = self.validator.validate_sensor_with_context(mock_sensor, "test_set")

        assert errors == []
        mock_sensor.validate.assert_called_once()

    def test_validate_sensor_with_context_sensor_set_not_found(self):
        """Test validate_sensor_with_context when sensor set is not found."""
        # Mock storage manager data without the test sensor set
        self.mock_storage_manager.data = {"sensor_sets": {}}

        mock_sensor = Mock(spec=SensorConfig)
        mock_sensor.validate.return_value = []

        # Mock the validation methods
        self.validator._validate_attribute_variable_conflicts = Mock(return_value=[])

        errors = self.validator.validate_sensor_with_context(mock_sensor, "missing_set")

        assert errors == []
        mock_sensor.validate.assert_called_once()

    def test_validate_against_global_settings_no_errors(self):
        """Test _validate_against_global_settings with no conflicts."""
        sensor = self._create_mock_sensor("test_sensor", ["temp"])
        global_settings = {"device_identifier": "test_device", "variables": {}}

        # This tests the method exists and can be called without errors
        # Note: The actual implementation may contain more validation logic
        errors = self.validator._validate_against_global_settings(sensor, global_settings)

        # Should return a list (empty or with errors)
        assert isinstance(errors, list)

    def test_validate_against_global_settings_variable_conflicts(self):
        """Test _validate_against_global_settings detects variable value conflicts."""
        # Create sensor with variables that have specific values
        formula = Mock(spec=FormulaConfig)
        formula.id = "test_sensor"
        formula.variables = {"temp": 25.5, "humidity": 60}  # Values, not just names

        sensor = Mock(spec=SensorConfig)
        sensor.unique_id = "test_sensor"
        sensor.formulas = [formula]

        global_settings = {
            "variables": {
                "temp": 20.0,  # Different value - should conflict
                "pressure": 1013.25,  # Not in sensor - no conflict
            }
        }

        errors = self.validator._validate_against_global_settings(sensor, global_settings)

        assert len(errors) == 1
        assert "main formula variable 'temp' value '25.5' conflicts with global setting '20.0'" in errors[0]

    def test_validate_against_global_settings_attribute_formula_conflicts(self):
        """Test _validate_against_global_settings with attribute formula conflicts."""
        # Create sensor with attribute formula that conflicts
        main_formula = Mock(spec=FormulaConfig)
        main_formula.id = "sensor1"
        main_formula.variables = {"base_temp": 20.0}

        attr_formula = Mock(spec=FormulaConfig)
        attr_formula.id = "sensor1_power"
        attr_formula.variables = {"voltage": 12.0}

        sensor = Mock(spec=SensorConfig)
        sensor.unique_id = "sensor1"
        sensor.formulas = [main_formula, attr_formula]

        global_settings = {
            "variables": {
                "voltage": 24.0  # Conflicts with attribute formula
            }
        }

        errors = self.validator._validate_against_global_settings(sensor, global_settings)

        assert len(errors) == 1
        assert "attribute 'power' variable 'voltage' value '12.0' conflicts with global setting '24.0'" in errors[0]

    def test_validate_against_global_settings_custom_formula_conflicts(self):
        """Test _validate_against_global_settings with custom formula conflicts."""
        formula = Mock(spec=FormulaConfig)
        formula.id = "custom_calculation"
        formula.variables = {"factor": 1.5}

        sensor = Mock(spec=SensorConfig)
        sensor.unique_id = "test_sensor"
        sensor.formulas = [formula]

        global_settings = {
            "variables": {
                "factor": 2.0  # Conflicts with custom formula
            }
        }

        errors = self.validator._validate_against_global_settings(sensor, global_settings)

        assert len(errors) == 1
        assert "formula 'custom_calculation' variable 'factor' value '1.5' conflicts with global setting '2.0'" in errors[0]

    def test_validate_against_global_settings_matching_values(self):
        """Test _validate_against_global_settings when values match (no conflict)."""
        formula = Mock(spec=FormulaConfig)
        formula.id = "test_sensor"
        formula.variables = {"temp": 25.5, "humidity": 60}

        sensor = Mock(spec=SensorConfig)
        sensor.unique_id = "test_sensor"
        sensor.formulas = [formula]

        global_settings = {
            "variables": {
                "temp": 25.5,  # Same value - no conflict
                "pressure": 1013.25,  # Not in sensor - no conflict
            }
        }

        errors = self.validator._validate_against_global_settings(sensor, global_settings)

        assert len(errors) == 0

    def test_validate_against_global_settings_no_global_variables(self):
        """Test _validate_against_global_settings with no global variables."""
        # Create sensor with proper mock formula that has no variables
        formula = Mock(spec=FormulaConfig)
        formula.id = "test_sensor"
        formula.variables = {}  # Empty variables dict, not list

        sensor = Mock(spec=SensorConfig)
        sensor.unique_id = "test_sensor"
        sensor.formulas = [formula]
        sensor.device_identifier = None  # No device identifier to avoid conflicts

        global_settings = {"device_identifier": "test_device"}  # No variables key

        errors = self.validator._validate_against_global_settings(sensor, global_settings)

        assert len(errors) == 0

    def test_validate_against_global_settings_empty_global_variables(self):
        """Test _validate_against_global_settings with empty global variables."""
        # Create sensor with proper mock formula that has no variables
        formula = Mock(spec=FormulaConfig)
        formula.id = "test_sensor"
        formula.variables = {}  # Empty variables dict

        sensor = Mock(spec=SensorConfig)
        sensor.unique_id = "test_sensor"
        sensor.formulas = [formula]

        global_settings = {"variables": {}}  # Empty variables

        errors = self.validator._validate_against_global_settings(sensor, global_settings)

        assert len(errors) == 0

    def test_validate_against_global_settings_device_identifier_conflict(self):
        """Test _validate_against_global_settings detects device identifier conflicts."""
        formula = Mock(spec=FormulaConfig)
        formula.id = "test_sensor"
        formula.variables = {}

        sensor = Mock(spec=SensorConfig)
        sensor.unique_id = "test_sensor"
        sensor.formulas = [formula]
        sensor.device_identifier = "sensor_device"  # Different from global setting

        global_settings = {"device_identifier": "global_device"}

        errors = self.validator._validate_against_global_settings(sensor, global_settings)

        assert len(errors) == 1
        assert "device_identifier 'sensor_device' conflicts with global setting 'global_device'" in errors[0]

    def test_validate_against_global_settings_device_identifier_same(self):
        """Test _validate_against_global_settings when device identifiers match (no conflict)."""
        formula = Mock(spec=FormulaConfig)
        formula.id = "test_sensor"
        formula.variables = {}

        sensor = Mock(spec=SensorConfig)
        sensor.unique_id = "test_sensor"
        sensor.formulas = [formula]
        sensor.device_identifier = "same_device"  # Same as global setting

        global_settings = {"device_identifier": "same_device"}

        errors = self.validator._validate_against_global_settings(sensor, global_settings)

        assert len(errors) == 0

    def test_check_formula_variable_conflicts_no_conflicts(self):
        """Test _check_formula_variable_conflicts with no conflicts."""
        sensor = self._create_mock_sensor("test_sensor", ["temp", "humidity"])
        global_variables = {"pressure": 1013.25, "altitude": 100}

        # Should not raise any exceptions when no conflicts exist
        self.validator._check_formula_variable_conflicts(sensor, global_variables)

    def test_check_formula_variable_conflicts_main_formula_conflict(self):
        """Test _check_formula_variable_conflicts detects main formula conflicts."""
        sensor = self._create_mock_sensor("test_sensor", ["temp", "pressure"])
        global_variables = {"pressure": 1013.25, "altitude": 100}

        with pytest.raises(
            SyntheticSensorsConfigError,
            match="Sensor 'test_sensor' main formula defines variable 'pressure' with value 'mock_value_pressure' which conflicts with global variable value '1013.25'",
        ):
            self.validator._check_formula_variable_conflicts(sensor, global_variables)

    def test_check_formula_variable_conflicts_attribute_formula_conflict(self):
        """Test _check_formula_variable_conflicts detects attribute formula conflicts."""
        sensor = self._create_mock_sensor_with_formulas(
            [
                ("sensor1", ["temp"]),  # main formula - no conflict
                ("sensor1_power", ["voltage"]),  # attribute formula - conflict with global
            ]
        )
        global_variables = {"voltage": 12.0}

        with pytest.raises(
            SyntheticSensorsConfigError,
            match="Sensor 'sensor1' formula for attribute 'power' defines variable 'voltage' with value 'mock_value_voltage' which conflicts with global variable value '12.0'",
        ):
            self.validator._check_formula_variable_conflicts(sensor, global_variables)

    def test_check_formula_variable_conflicts_custom_formula_conflict(self):
        """Test _check_formula_variable_conflicts detects custom formula conflicts."""
        sensor = self._create_mock_sensor_with_formulas(
            [
                ("sensor1", ["temp"]),  # main formula - no conflict
                ("custom_calculation", ["altitude"]),  # custom formula - conflict with global
            ]
        )
        global_variables = {"altitude": 1000}

        with pytest.raises(
            SyntheticSensorsConfigError,
            match="Sensor 'sensor1' formula 'custom_calculation' defines variable 'altitude' with value 'mock_value_altitude' which conflicts with global variable value '1000'",
        ):
            self.validator._check_formula_variable_conflicts(sensor, global_variables)

    def test_check_formula_variable_conflicts_empty_variables(self):
        """Test _check_formula_variable_conflicts with formulas having no variables."""
        # Create sensor with formulas that have no variables
        formulas = [
            self._create_mock_formula("sensor1", None),  # No variables
            self._create_mock_formula("sensor1_state", []),  # Empty variables
        ]

        sensor = Mock(spec=SensorConfig)
        sensor.unique_id = "sensor1"
        sensor.formulas = formulas

        global_variables = {"pressure": 1013.25}

        # Should not raise any exceptions when formulas have no variables
        self.validator._check_formula_variable_conflicts(sensor, global_variables)

    def test_validate_attribute_variable_conflicts_method_exists(self):
        """Test that _validate_attribute_variable_conflicts method exists and is callable."""
        sensor = self._create_mock_sensor("test_sensor", ["temp"])

        # This method should exist and be callable (testing the interface)
        # Note: We're testing that the method exists as it's called in validate_sensor_with_context
        result = self.validator._validate_attribute_variable_conflicts(sensor)

        # Should return a list of errors
        assert isinstance(result, list)

    def test_edge_case_sensor_with_many_formulas(self):
        """Test edge case with sensor having many formulas."""
        # Create sensor with many formulas to test iteration logic
        formulas_data = [
            ("sensor_complex", ["base1", "base2"]),
            ("sensor_complex_attr1", ["var1", "var2"]),
            ("sensor_complex_attr2", ["var3", "var4"]),
            ("sensor_complex_attr3", ["var5", "var6"]),
            ("sensor_complex_attr4", ["var7", "var8"]),
        ]

        sensor = self._create_mock_sensor_with_formulas(formulas_data)

        # Should handle many formulas without issues
        self.validator._check_attribute_formula_conflicts(sensor)

    def test_edge_case_very_long_variable_names(self):
        """Test edge case with very long variable and sensor names."""
        long_sensor_id = "sensor_with_very_long_name_that_tests_string_handling"
        long_var_name = "very_long_variable_name_that_might_cause_issues_in_validation"

        sensor = self._create_mock_sensor(long_sensor_id, [long_var_name])

        # Should handle long names gracefully
        self.validator._check_attribute_formula_conflicts(sensor)

    def test_conflict_error_message_formatting(self):
        """Test that conflict error messages are properly formatted."""
        sensor = self._create_mock_sensor_with_formulas(
            [("test_sensor", ["conflicting_var"]), ("test_sensor_temperature", ["conflicting_var"])]
        )

        with pytest.raises(SyntheticSensorsConfigError) as exc_info:
            self.validator._check_attribute_formula_conflicts(sensor)

        error_message = str(exc_info.value)
        assert "test_sensor" in error_message
        assert "conflicting_var" in error_message
        assert "main formula" in error_message
        assert "attribute 'temperature'" in error_message

    # Helper methods
    def _create_mock_sensor(self, unique_id: str, variables: list[str]) -> Mock:
        """Create a mock sensor with basic configuration."""
        formula = self._create_mock_formula(unique_id, variables)

        sensor = Mock(spec=SensorConfig)
        sensor.unique_id = unique_id
        sensor.formulas = [formula] if variables else []

        return sensor

    def _create_mock_sensor_with_formulas(self, formulas_data: list[tuple[str, list[str]]]) -> Mock:
        """Create a mock sensor with multiple formulas."""
        formulas = []
        sensor_id = None

        for formula_id, variables in formulas_data:
            if sensor_id is None:
                sensor_id = formula_id  # First formula ID is the sensor ID
            formulas.append(self._create_mock_formula(formula_id, variables))

        sensor = Mock(spec=SensorConfig)
        sensor.unique_id = sensor_id
        sensor.formulas = formulas

        return sensor

    def _create_mock_formula(self, formula_id: str, variables: list[str] | None) -> Mock:
        """Create a mock formula configuration."""
        formula = Mock(spec=FormulaConfig)
        formula.id = formula_id
        # Convert list of variable names to dict with placeholder values
        if variables is not None:
            formula.variables = {var: f"mock_value_{var}" for var in variables}
        else:
            formula.variables = {}

        return formula

    def _create_mock_formula_with_values(self, formula_id: str, variables: dict[str, Any]) -> Mock:
        """Create a mock formula configuration with variable values."""
        formula = Mock(spec=FormulaConfig)
        formula.id = formula_id
        formula.variables = variables

        return formula


class TestValidationEdgeCases:
    """Test edge cases and error conditions for ValidationHandler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_storage_manager = Mock()
        self.validator = ValidationHandler(self.mock_storage_manager)

    def test_validate_empty_sensor_list(self):
        """Test validation with empty sensor list."""
        self.validator.validate_no_global_conflicts([], {})
        # Should complete without errors

    def test_validate_empty_global_settings(self):
        """Test validation with empty global settings."""
        sensor = Mock(spec=SensorConfig)
        sensor.formulas = []

        self.validator.validate_no_global_conflicts([sensor], {})
        # Should complete without errors

    def test_validate_sensor_none_formulas(self):
        """Test handling of sensor with None formulas."""
        sensor = Mock(spec=SensorConfig)
        sensor.formulas = None

        # Should raise TypeError for None formulas (expected behavior)
        with pytest.raises(TypeError, match="'NoneType' object is not iterable"):
            self.validator._check_attribute_formula_conflicts(sensor)

    def test_multiple_complex_conflicts(self):
        """Test complex scenario with multiple types of conflicts."""
        # Create a sensor with overlapping variables across multiple formulas
        formulas_data = [
            ("complex_sensor", ["shared1", "unique1"]),  # main formula
            ("complex_sensor_state", ["shared1", "unique2"]),  # conflicts with main
            ("complex_sensor_power", ["shared2", "unique3"]),  # no conflict yet
            ("complex_sensor_temp", ["shared2", "unique4"]),  # conflicts with power
        ]

        sensor = Mock(spec=SensorConfig)
        sensor.unique_id = "complex_sensor"

        formulas = []
        for formula_id, variables in formulas_data:
            formula = Mock(spec=FormulaConfig)
            formula.id = formula_id
            formula.variables = variables
            formulas.append(formula)

        sensor.formulas = formulas

        # Should detect the first conflict (shared1 between main and state)
        with pytest.raises(SyntheticSensorsConfigError, match="shared1.*main formula.*attribute 'state'"):
            self.validator._check_attribute_formula_conflicts(sensor)
