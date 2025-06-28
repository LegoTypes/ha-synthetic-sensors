"""Test entity_id field support in YAML configuration.

This tests the explicit entity_id field that allows users to override
the default entity_id generation pattern.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.sensor_manager import DynamicSensor, SensorManagerConfig


class TestEntityIdSupport:
    """Test explicit entity_id field support in YAML configuration."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()

        # Mock entity states for testing
        def mock_states_get(entity_id):
            state_values = {
                "sensor.power_meter": MagicMock(state="1000"),
                "sensor.base_power_reading": MagicMock(state="800"),
                "input_number.efficiency_multiplier": MagicMock(state="1.2"),
                "sensor.daily_energy_total": MagicMock(state="48"),
                "sensor.active_power": MagicMock(state="500"),
                "sensor.standby_power": MagicMock(state="50"),
                "input_number.max_power_rating": MagicMock(state="1000"),
                # Expected synthetic sensor entity_ids
                "sensor.standard_power_sensor": MagicMock(state="1000"),
                "sensor.custom_energy_monitor": MagicMock(state="960"),  # 800 * 1.2
                "sensor.special_consumption": MagicMock(state="2"),  # 48 / 24
                "sensor.comprehensive_energy": MagicMock(state="550"),  # 500 + 50
            }
            state_obj = state_values.get(entity_id)
            if state_obj:
                state_obj.entity_id = entity_id
            return state_obj

        hass.states.get.side_effect = mock_states_get
        return hass

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a ConfigManager instance."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def entity_id_yaml(self):
        """Load the entity_id support YAML fixture."""
        fixture_path = Path(__file__).parent / "yaml_fixtures" / "entity_id_support.yaml"
        with open(fixture_path) as f:
            return yaml.safe_load(f)

    def test_yaml_fixture_loads_correctly(self, entity_id_yaml):
        """Test that the YAML fixture loads without errors."""
        assert entity_id_yaml["version"] == "1.0"
        assert "sensors" in entity_id_yaml
        assert len(entity_id_yaml["sensors"]) == 4

    def test_standard_sensor_without_entity_id(self, config_manager, entity_id_yaml):
        """Test sensor without explicit entity_id uses default pattern."""
        config = config_manager._parse_yaml_config(entity_id_yaml)

        # Find the standard sensor
        standard_sensor = next(s for s in config.sensors if s.unique_id == "standard_power_sensor")

        # Should not have explicit entity_id set
        assert standard_sensor.entity_id is None

        # When creating a DynamicSensor, it should use the default pattern
        evaluator = Evaluator(config_manager._hass)
        mock_sensor_manager = MagicMock()
        dynamic_sensor = DynamicSensor(
            config_manager._hass,
            standard_sensor,
            evaluator,
            mock_sensor_manager,
            SensorManagerConfig(),
        )

        # Should have the unique_id without prefix (new behavior)
        assert dynamic_sensor.unique_id == "standard_power_sensor"
        # Should not have explicit entity_id set (HA will auto-generate)
        assert not hasattr(dynamic_sensor, "_attr_entity_id")

    def test_custom_entity_id_field_parsing(self, config_manager, entity_id_yaml):
        """Test that explicit entity_id field is parsed correctly."""
        config = config_manager._parse_yaml_config(entity_id_yaml)

        # Find the sensor with custom entity_id
        custom_sensor = next(s for s in config.sensors if s.unique_id == "custom_named_sensor")

        # Should have explicit entity_id set
        assert custom_sensor.entity_id == "sensor.custom_energy_monitor"

        # Check other properties are still correct
        assert custom_sensor.name == "Custom Named Energy Monitor"
        assert custom_sensor.formulas[0].formula == "base_power * efficiency_factor"

    def test_multiple_custom_entity_ids(self, config_manager, entity_id_yaml):
        """Test multiple sensors with different custom entity_ids."""
        config = config_manager._parse_yaml_config(entity_id_yaml)

        # Check first custom entity_id
        custom_sensor1 = next(s for s in config.sensors if s.unique_id == "custom_named_sensor")
        assert custom_sensor1.entity_id == "sensor.custom_energy_monitor"

        # Check second custom entity_id
        custom_sensor2 = next(s for s in config.sensors if s.unique_id == "special_consumption_tracker")
        assert custom_sensor2.entity_id == "sensor.special_consumption"

    def test_custom_entity_id_with_attributes(self, config_manager, entity_id_yaml):
        """Test sensor with custom entity_id and calculated attributes."""
        config = config_manager._parse_yaml_config(entity_id_yaml)

        # Find the comprehensive sensor
        comprehensive_sensor = next(s for s in config.sensors if s.unique_id == "comprehensive_monitor")

        # Check custom entity_id
        assert comprehensive_sensor.entity_id == "sensor.comprehensive_energy"

        # Check it has attributes
        assert len(comprehensive_sensor.formulas) == 3  # Main + 2 attributes

        # Find attribute formulas
        daily_proj = next(f for f in comprehensive_sensor.formulas if f.id == "comprehensive_monitor_daily_projection")
        efficiency = next(f for f in comprehensive_sensor.formulas if f.id == "comprehensive_monitor_efficiency_rating")

        assert daily_proj.formula == "state * 24"
        assert efficiency.formula == "state / 1000 * 100"

    def test_dynamic_sensor_respects_custom_entity_id(self, config_manager, entity_id_yaml):
        """Test that DynamicSensor respects custom entity_id field."""
        config = config_manager._parse_yaml_config(entity_id_yaml)
        evaluator = Evaluator(config_manager._hass)

        # Test standard sensor (no custom entity_id)
        standard_sensor = next(s for s in config.sensors if s.unique_id == "standard_power_sensor")
        mock_sensor_manager = MagicMock()
        standard_dynamic = DynamicSensor(
            config_manager._hass,
            standard_sensor,
            evaluator,
            mock_sensor_manager,
            SensorManagerConfig(),
        )

        # Should use unique_id without prefix (new behavior)
        assert standard_dynamic.unique_id == "standard_power_sensor"
        assert not hasattr(standard_dynamic, "_attr_entity_id")

        # Test custom entity_id sensor
        custom_sensor = next(s for s in config.sensors if s.unique_id == "custom_named_sensor")
        custom_dynamic = DynamicSensor(
            config_manager._hass,
            custom_sensor,
            evaluator,
            mock_sensor_manager,
            SensorManagerConfig(),
        )

        # Should use unique_id without prefix (new behavior)
        assert custom_dynamic.unique_id == "custom_named_sensor"
        assert hasattr(custom_dynamic, "entity_id")
        assert custom_dynamic.entity_id == "sensor.custom_energy_monitor"

    def test_entity_id_validation_in_config(self, config_manager, entity_id_yaml):
        """Test that entity_id values are validated during config parsing."""
        # This should parse without errors
        config = config_manager._parse_yaml_config(entity_id_yaml)
        assert len(config.sensors) == 4

        # Test invalid entity_id format using schema validation (which enforces HA rules)
        from ha_synthetic_sensors.schema_validator import validate_yaml_config

        invalid_yaml = entity_id_yaml.copy()
        invalid_yaml["sensors"]["invalid_entity_id_sensor"] = {
            "name": "Invalid Entity ID",
            "entity_id": "invalid_format_no_domain",
            "formula": "1 + 1",
        }  # Missing domain - should be rejected

        # Schema validation should catch the invalid entity_id format
        result = validate_yaml_config(invalid_yaml)
        assert result["valid"] is False
        assert len(result["errors"]) > 0

        # Check that the error is about entity_id format
        error_messages = [error.message for error in result["errors"]]
        assert any("invalid_format_no_domain" in msg for msg in error_messages)

    def test_entity_id_cross_references(self, config_manager, entity_id_yaml):
        """Test that custom entity_ids can be referenced by other sensors."""
        # Add a sensor that references the custom entity_id
        test_yaml = entity_id_yaml.copy()
        test_yaml["sensors"]["referencing_sensor"] = {
            "name": "Referencing Sensor",
            "formula": "sensor.custom_energy_monitor * 2",
            "unit_of_measurement": "W",
        }  # Reference custom entity_id

        config = config_manager._parse_yaml_config(test_yaml)

        # Find the referencing sensor
        ref_sensor = next(s for s in config.sensors if s.unique_id == "referencing_sensor")

        # Should auto-inject the referenced entity_id as a variable
        main_formula = ref_sensor.formulas[0]
        assert "sensor.custom_energy_monitor" in main_formula.variables
        assert main_formula.variables["sensor.custom_energy_monitor"] == "sensor.custom_energy_monitor"

    def test_entity_id_in_schema_validation(self, config_manager, entity_id_yaml):
        """Test that schema validation accepts entity_id field."""
        # Load and validate the config
        config = config_manager._parse_yaml_config(entity_id_yaml)
        errors = config_manager.validate_config(config)

        # Should have no validation errors
        assert len(errors) == 0, f"Validation errors: {errors}"

        # Test schema validation directly if available
        if hasattr(config_manager, "validate_yaml_data"):
            validation_result = config_manager.validate_yaml_data(entity_id_yaml)
            # Should now pass with the fixed YAML
            assert validation_result["valid"] is True, f"Schema validation errors: {validation_result.get('errors', [])}"
            assert len(validation_result["errors"]) == 0
