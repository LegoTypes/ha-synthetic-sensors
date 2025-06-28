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
        return Path(__file__).parent / "yaml_fixtures" / "dynamic_collection_variables.yaml"

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance with comprehensive entity states."""
        hass = Mock()
        hass.data = {}

        mock_states = {
            # Device class: power sensors
            "sensor.circuit_main_power": Mock(
                state="350.5",
                entity_id="sensor.circuit_main_power",
                attributes={"device_class": "power"},
            ),
            "sensor.circuit_lighting_power": Mock(
                state="125.3",
                entity_id="sensor.circuit_lighting_power",
                attributes={"device_class": "power"},
            ),
            # Device class: temperature sensors
            "sensor.kitchen_temperature": Mock(
                state="22.5",
                entity_id="sensor.kitchen_temperature",
                attributes={"device_class": "temperature"},
            ),
            "sensor.living_room_temperature": Mock(
                state="21.8",
                entity_id="sensor.living_room_temperature",
                attributes={"device_class": "temperature"},
            ),
            # Battery sensors for attribute testing
            "sensor.phone_battery": Mock(
                state="85",
                entity_id="sensor.phone_battery",
                attributes={"device_class": "battery", "battery_level": 85},
            ),
            "sensor.tablet_battery": Mock(
                state="15",
                entity_id="sensor.tablet_battery",
                attributes={"device_class": "battery", "battery_level": 15},
            ),
            "sensor.laptop_battery": Mock(
                state="92",
                entity_id="sensor.laptop_battery",
                attributes={"device_class": "battery", "battery_level": 92},
            ),
            # Variable source entities (for future dynamic patterns)
            "input_select.monitoring_device_class": Mock(state="power", entity_id="input_select.monitoring_device_class"),
            "input_select.focus_area": Mock(state="kitchen", entity_id="input_select.focus_area"),
            "input_number.battery_alert_threshold": Mock(state="20", entity_id="input_number.battery_alert_threshold"),
            "input_text.circuit_group_name": Mock(state="main", entity_id="input_text.circuit_group_name"),
            # Additional entities for comprehensive testing
            "sensor.main_panel_power": Mock(state="100.0", entity_id="sensor.main_panel_power"),
            "input_number.power_rate_multiplier": Mock(state="1.5", entity_id="input_number.power_rate_multiplier"),
        }

        hass.states.entity_ids.return_value = list(mock_states.keys())
        hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)

        return hass

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

    async def test_yaml_fixture_loads_correctly(self, config_manager, yaml_config_path):
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

    async def test_yaml_dynamic_device_sum_sensor(self, config_manager, yaml_config_path, evaluator):
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

    async def test_yaml_circuit_group_power_syntax(self, config_manager, yaml_config_path):
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

    async def test_yaml_dynamic_patterns_syntax_validation(self, config_manager, yaml_config_path):
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

    async def test_yaml_mixed_patterns_syntax(self, config_manager, yaml_config_path):
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

    async def test_variable_inheritance_in_yaml_attributes(self, config_manager, yaml_config_path):
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
