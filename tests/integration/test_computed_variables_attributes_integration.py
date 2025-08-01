"""Integration tests for computed variables in attribute formulas with proper state scoping."""

import pytest
from unittest.mock import MagicMock
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.config_models import ComputedVariable


class TestComputedVariablesInAttributesIntegration:
    """Test computed variables within attribute formulas in a complete integration scenario."""

    @pytest.fixture
    def computed_vars_attributes_yaml(self, load_yaml_fixture):
        """Load the computed variables with attributes integration fixture."""
        return load_yaml_fixture("computed_variables_with_attributes_integration")

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create config manager with mock HA."""
        return ConfigManager(mock_hass)

    def test_computed_variables_attributes_yaml_loads_and_validates(self, config_manager, computed_vars_attributes_yaml):
        """Test that the integration fixture loads and validates correctly."""
        # Validate the YAML structure
        validation_result = config_manager.validate_yaml_data(computed_vars_attributes_yaml)
        assert validation_result["valid"], (
            f"YAML validation failed: {[e['message'] for e in validation_result.get('errors', [])]}"
        )

        # Load the configuration
        config = config_manager.load_from_dict(computed_vars_attributes_yaml)

        # Verify sensors were loaded
        assert len(config.sensors) == 3
        sensor_names = [s.name for s in config.sensors]
        assert "Power Sensor with Computed Attributes" in sensor_names
        assert "Temperature with State-Dependent Computed Attributes" in sensor_names
        assert "Efficiency Sensor with Nested Computations" in sensor_names

    def test_power_sensor_computed_variables_in_attributes_parsing(self, config_manager, computed_vars_attributes_yaml):
        """Test parsing of computed variables in power sensor attributes."""
        config = config_manager.load_from_dict(computed_vars_attributes_yaml)

        # Find the power sensor
        power_sensor = next(s for s in config.sensors if s.unique_id == "power_sensor_with_computed_attributes")

        # Should have main formula + 3 attribute formulas
        assert len(power_sensor.formulas) == 4  # main + power_percentage + power_category + power_analysis

        # Check that attribute formulas have computed variables
        attr_formulas = power_sensor.formulas[1:]  # Skip main formula

        # power_percentage attribute
        percentage_formula = next(f for f in attr_formulas if f.id.endswith("_power_percentage"))
        assert "computed_percent" in percentage_formula.variables
        assert isinstance(percentage_formula.variables["computed_percent"], ComputedVariable)
        assert percentage_formula.variables["computed_percent"].formula == "round((state / max_power) * 100, 1)"

        # power_category attribute with multiple computed variables
        category_formula = next(f for f in attr_formulas if f.id.endswith("_power_category"))
        computed_vars = [k for k, v in category_formula.variables.items() if isinstance(v, ComputedVariable)]
        assert len(computed_vars) >= 5  # is_low, is_medium, is_high, is_very_high, final_category

        # Verify state references in computed variables
        assert category_formula.variables["is_low"].formula == "state < low_threshold"
        assert (
            category_formula.variables["final_category"].formula
            == "'low' if is_low else ('medium' if is_medium else ('high' if is_high else 'very_high'))"
        )

    def test_temperature_sensor_state_scoping_in_computed_variables(self, config_manager, computed_vars_attributes_yaml):
        """Test that state properly scopes to main sensor result in temperature sensor attributes."""
        config = config_manager.load_from_dict(computed_vars_attributes_yaml)

        # Find the temperature sensor
        temp_sensor = next(s for s in config.sensors if s.unique_id == "temperature_sensor_with_state_dependent_attributes")

        # Check attribute formulas
        attr_formulas = temp_sensor.formulas[1:]  # Skip main formula

        # temperature_status attribute
        status_formula = next(f for f in attr_formulas if f.id.endswith("_temperature_status"))
        assert isinstance(status_formula.variables["temp_status"], ComputedVariable)
        # The formula should reference 'state' which will be the main sensor's post-evaluation result
        assert "state <=" in status_formula.variables["temp_status"].formula

        # temperature_metrics attribute
        metrics_formula = next(f for f in attr_formulas if f.id.endswith("_temperature_metrics"))
        temp_f_var = metrics_formula.variables["temp_fahrenheit"]
        assert isinstance(temp_f_var, ComputedVariable)
        assert temp_f_var.formula == "(state * 9/5) + 32"  # Uses state for Fahrenheit conversion

    def test_efficiency_sensor_nested_computed_variables_with_state(self, config_manager, computed_vars_attributes_yaml):
        """Test nested computed variables with state references in efficiency sensor."""
        config = config_manager.load_from_dict(computed_vars_attributes_yaml)

        # Find the efficiency sensor
        eff_sensor = next(s for s in config.sensors if s.unique_id == "efficiency_sensor_with_nested_computed_vars")

        # Main formula should have computed variables
        main_formula = eff_sensor.formulas[0]
        assert isinstance(main_formula.variables["raw_efficiency"], ComputedVariable)
        assert isinstance(main_formula.variables["final_efficiency"], ComputedVariable)

        # Check attribute formulas use state correctly
        attr_formulas = eff_sensor.formulas[1:]

        # efficiency_rating attribute
        rating_formula = next(f for f in attr_formulas if f.id.endswith("_efficiency_rating"))
        rating_vars = [k for k, v in rating_formula.variables.items() if isinstance(v, ComputedVariable)]
        assert "is_excellent" in rating_vars
        assert "is_good" in rating_vars
        assert "rating" in rating_vars

        # Verify state references in attribute computed variables
        assert rating_formula.variables["is_excellent"].formula == "state >= excellent_threshold"
        assert "state >=" in rating_formula.variables["is_good"].formula

    @pytest.mark.asyncio
    async def test_end_to_end_computed_variables_attributes_evaluation(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, computed_vars_attributes_yaml
    ):
        """Test end-to-end evaluation of computed variables in attributes."""
        # Set up mock entity states
        mock_states.update(
            {
                "sensor.raw_power": MagicMock(state="1800", attributes={}),
                "sensor.raw_temperature": MagicMock(state="20.5", attributes={}),
                "sensor.input_power": MagicMock(state="1000", attributes={}),
                "sensor.output_power": MagicMock(state="850", attributes={}),
            }
        )

        # Load configuration
        config = config_manager.load_from_dict(computed_vars_attributes_yaml)

        # Find the power sensor for detailed testing
        power_sensor = next(s for s in config.sensors if s.unique_id == "power_sensor_with_computed_attributes")

        # Create sensor manager
        def mock_data_provider(entity_id: str):
            entity_state = mock_states.get(entity_id)
            if entity_state:
                return {"value": float(entity_state.state), "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            mock_hass,
            MagicMock(),  # name_resolver
            mock_add_entities,
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register data provider entities
        sensor_manager.register_data_provider_entities(
            {"sensor.raw_power", "sensor.raw_temperature", "sensor.input_power", "sensor.output_power"}
        )

        # Test main formula evaluation
        evaluator = sensor_manager._evaluator
        main_formula = power_sensor.formulas[0]

        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, power_sensor)
        assert main_result["success"] is True
        # Main result: 1800 * 0.9 = 1620W
        expected_main_value = 1620.0
        assert main_result["value"] == expected_main_value

        # Test attribute formula evaluation with state context
        attr_formulas = power_sensor.formulas[1:]  # Skip main formula

        # Test power_percentage attribute (should use state = 1620)
        percentage_formula = next(f for f in attr_formulas if f.id.endswith("_power_percentage"))
        context = {"state": main_result["value"]}  # Pass main result as state

        percentage_result = evaluator.evaluate_formula_with_sensor_config(percentage_formula, context, power_sensor)
        assert percentage_result["success"] is True
        # Expected: round((1620 / 2000) * 100, 1) = 81.0%
        assert percentage_result["value"] == 81.0

        # Test power_category attribute (should categorize 1620W as "high")
        category_formula = next(f for f in attr_formulas if f.id.endswith("_power_category"))

        category_result = evaluator.evaluate_formula_with_sensor_config(category_formula, context, power_sensor)
        assert category_result["success"] is True
        # 1620W >= 1200 (medium_threshold) and < 1800 (high_threshold), so should be "high"
        assert category_result["value"] == "high"

        print(f"✅ End-to-end computed variables in attributes test passed!")
        print(f"   Main sensor result: {main_result['value']}W")
        print(f"   Power percentage: {percentage_result['value']}%")
        print(f"   Power category: {category_result['value']}")

    def test_computed_variables_preserve_existing_functionality(self, config_manager, computed_vars_attributes_yaml):
        """Test that computed variables don't break existing attribute functionality."""
        config = config_manager.load_from_dict(computed_vars_attributes_yaml)

        # Verify all sensors loaded correctly
        assert len(config.sensors) == 3

        # Verify each sensor has expected number of formulas
        sensors_formula_counts = {}
        for sensor in config.sensors:
            sensors_formula_counts[sensor.unique_id] = len(sensor.formulas)

        # Expected: main + attributes
        assert sensors_formula_counts["power_sensor_with_computed_attributes"] == 4  # 1 main + 3 attrs
        assert sensors_formula_counts["temperature_sensor_with_state_dependent_attributes"] == 3  # 1 main + 2 attrs
        assert sensors_formula_counts["efficiency_sensor_with_nested_computed_vars"] == 3  # 1 main + 2 attrs

        # Verify that regular (non-computed) variables still work
        power_sensor = next(s for s in config.sensors if s.unique_id == "power_sensor_with_computed_attributes")
        main_formula = power_sensor.formulas[0]

        # Check that simple variables are still parsed correctly
        assert "input_power" in main_formula.variables
        assert main_formula.variables["input_power"] == "sensor.raw_power"  # Simple entity reference
        assert "efficiency" in main_formula.variables
        assert main_formula.variables["efficiency"] == 0.9  # Simple literal value
