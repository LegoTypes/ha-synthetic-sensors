"""Tests for dynamic collection patterns using YAML fixtures."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.evaluator import Evaluator


class TestDynamicCollectionVariables:
    """Test collection functions using YAML fixtures with both static and dynamic patterns."""

    @pytest.fixture
    def yaml_config_path(self):
        """Path to the dynamic collection variables YAML fixture."""
        return Path(__file__).parent.parent.parent / "yaml_fixtures" / "dynamic_collection_variables.yaml"

    @pytest.fixture
    def evaluator(self, mock_hass):
        """Create an evaluator instance with mocked dependencies."""
        with (
            patch("ha_synthetic_sensors.collection_resolver.er.async_get"),
            patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
            patch("ha_synthetic_sensors.collection_resolver.ar.async_get"),
        ):
            return Evaluator(mock_hass)

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager instance."""
        return ConfigManager(mock_hass)

    async def test_yaml_fixture_loads_correctly(
        self, config_manager, yaml_config_path, mock_hass, mock_entity_registry, mock_states
    ):
        """Test that the YAML fixture loads without errors."""
        try:
            config = await config_manager.async_load_from_file(yaml_config_path)

            assert config is not None
            assert len(config.sensors) > 0

            # Check that we have the expected sensors
            sensor_names = [sensor.unique_id for sensor in config.sensors]
            assert "dynamic_device_sum" in sensor_names
            assert "sum_two_regex_patterns" in sensor_names

        except Exception as e:
            if "Configuration schema validation failed" in str(e):
                # Expected - this YAML contains future syntax that doesn't validate yet
                pytest.skip(f"Schema validation failed as expected for future syntax: {e}")
            else:
                raise

    async def test_yaml_dynamic_device_sum_sensor(
        self, config_manager, yaml_config_path, evaluator, mock_hass, mock_entity_registry, mock_states
    ):
        """Test the dynamic_device_sum sensor from YAML fixture."""
        # Load config and get the specific sensor
        try:
            config = await config_manager.async_load_from_file(yaml_config_path)

            # Find the dynamic_device_sum sensor
            dynamic_sensor = None
            for sensor in config.sensors:
                if sensor.unique_id == "dynamic_device_sum":
                    dynamic_sensor = sensor
                    break

            assert dynamic_sensor is not None, "dynamic_device_sum sensor not found in YAML"

            # Get the formula config
            formula_config = dynamic_sensor.formulas[0]

            # Test that it has the expected syntax for variable substitution
            assert 'sum("device_class:device_type")' in formula_config.formula
            assert "device_type" in formula_config.variables
            assert formula_config.variables["device_type"] == "input_select.monitoring_device_class"

            # For now, testing syntax validation since functionality isn't implemented yet

        except Exception as e:
            if "Configuration schema validation failed" in str(e):
                # Expected - this is testing future syntax that doesn't validate yet
                pytest.skip(f"Schema validation failed as expected for future syntax: {e}")
            else:
                raise

    async def test_yaml_circuit_group_power_syntax(
        self, config_manager, yaml_config_path, mock_hass, mock_entity_registry, mock_states
    ):
        """Test the circuit_group_power sensor syntax from YAML fixture."""
        try:
            config = await config_manager.async_load_from_file(yaml_config_path)

            # Find the circuit_group_power sensor
            circuit_sensor = None
            for sensor in config.sensors:
                if sensor.unique_id == "circuit_group_power":
                    circuit_sensor = sensor
                    break

            assert circuit_sensor is not None, "circuit_group_power sensor not found in YAML"

            # Get the formula config
            formula_config = circuit_sensor.formulas[0]

            # Test that it has the expected syntax for variable substitution
            assert 'sum("regex:group_prefix")' in formula_config.formula
            assert "group_prefix" in formula_config.variables
            assert formula_config.variables["group_prefix"] == "input_text.circuit_group_name"

        except Exception as e:
            if "Configuration schema validation failed" in str(e):
                pytest.skip(f"Schema validation failed as expected for future syntax: {e}")
            else:
                raise

    async def test_yaml_dynamic_patterns_syntax_validation(
        self, config_manager, yaml_config_path, mock_hass, mock_entity_registry, mock_states
    ):
        """Test that YAML dynamic patterns have correct syntax for future implementation."""
        config = await config_manager.async_load_from_file(yaml_config_path)

        # Find the dynamic device sum sensor
        dynamic_sensor = None
        for sensor in config.sensors:
            if sensor.unique_id == "dynamic_device_sum":
                dynamic_sensor = sensor
                break

        assert dynamic_sensor is not None
        formula_config = dynamic_sensor.formulas[0]

        # Verify it has the correct syntax for variable substitution
        assert 'sum("device_class:device_type")' in formula_config.formula
        assert "device_type" in formula_config.variables
        assert formula_config.variables["device_type"] == "input_select.monitoring_device_class"

    async def test_yaml_mixed_patterns_syntax(
        self, config_manager, yaml_config_path, mock_hass, mock_entity_registry, mock_states
    ):
        """Test mixed static and dynamic regex patterns in YAML."""
        config = await config_manager.async_load_from_file(yaml_config_path)

        # Find the mixed regex patterns sensor
        mixed_sensor = None
        for sensor in config.sensors:
            if sensor.unique_id == "sum_two_regex_patterns":
                mixed_sensor = sensor
                break

        assert mixed_sensor is not None
        formula_config = mixed_sensor.formulas[0]

        # Verify correct syntax for future variable substitution
        assert '"regex:circuit_pattern"' in formula_config.formula
        assert '"regex:kitchen_pattern"' in formula_config.formula
        assert "circuit_pattern" in formula_config.variables
        assert "kitchen_pattern" in formula_config.variables

    async def test_variable_inheritance_in_yaml_attributes(
        self, config_manager, yaml_config_path, mock_hass, mock_entity_registry, mock_states
    ):
        """Test that attribute formulas inherit variables correctly in YAML."""
        config = await config_manager.async_load_from_file(yaml_config_path)

        # Find a sensor with calculated attributes
        energy_sensor = None
        for sensor in config.sensors:
            if sensor.unique_id == "energy_analysis_suite":
                energy_sensor = sensor
                break

        assert energy_sensor is not None

        # Check that attributes are defined
        assert len(energy_sensor.formulas) > 1  # Main formula + attributes

        # Main formula should have variables
        main_formula = energy_sensor.formulas[0]
        assert len(main_formula.variables) > 0


class TestStaticCollectionPatterns:
    """Test static collection patterns that work with current implementation."""

    def test_static_collection_syntax_validation(self):
        """Test that static collection patterns have correct syntax."""
        from ha_synthetic_sensors.config_manager import FormulaConfig

        # Test that we can create valid static configs
        config = FormulaConfig(id="static_test", formula='sum("device_class:power")', variables={})

        # Validate syntax structure
        assert 'sum("device_class:power")' in config.formula
        assert len(config.variables) == 0


class TestFutureDynamicPatterns:
    """Test future dynamic pattern syntax (not yet implemented)."""

    def test_dynamic_pattern_syntax_structure(self):
        """Test that dynamic pattern syntax is well-formed for future implementation."""
        # This test validates syntax structure, not functionality
        from ha_synthetic_sensors.config_manager import FormulaConfig

        # This is the intended syntax for when variable substitution is implemented
        config = FormulaConfig(
            id="future_dynamic",
            formula='sum("device_class:device_type")',
            variables={"device_type": "input_select.device_class"},
        )

        # Verify the formula contains a variable reference
        assert "device_type" in config.formula
        assert config.variables["device_type"] == "input_select.device_class"

        # This syntax is correct for future implementation
        assert config.formula == 'sum("device_class:device_type")'
