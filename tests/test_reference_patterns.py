"""Test different reference patterns in attribute formulas.

This tests the three reference patterns mentioned in the README:
1. "state * 24" - by main state alias
2. "energy_cost_analysis * 24 * 30" - by main sensor key
3. "sensor.syn2_energy_cost_analysis * 24 * 365" - by entity_id
"""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.evaluator import Evaluator


class TestReferencePatterns:
    """Test different ways to reference the main sensor in attribute formulas."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()

        # Mock entity states for testing
        def mock_states_get(entity_id):
            state_values = {
                "sensor.span_panel_instantaneous_power": MagicMock(state="1000"),
                "input_number.electricity_rate_cents_kwh": MagicMock(state="25"),
                "sensor.syn2_energy_cost_analysis": MagicMock(state="25.0"),  # 1000 * 25 / 1000 = 25
            }
            state_obj = state_values.get(entity_id)
            if state_obj:
                state_obj.entity_id = entity_id  # Add entity_id attribute for proper error handling
            return state_obj

        hass.states.get.side_effect = mock_states_get
        return hass

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a ConfigManager instance."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def evaluator(self, mock_hass):
        """Create an Evaluator instance."""
        return Evaluator(mock_hass)

    def test_state_alias_reference(self, config_manager, evaluator):
        """Test referencing main sensor state using 'state' alias."""
        sensor_data = {"name": "Energy Cost Analysis", "formula": "current_power * electricity_rate / 1000", "variables": {"current_power": "sensor.span_panel_instantaneous_power", "electricity_rate": "input_number.electricity_rate_cents_kwh"}, "attributes": {"daily_projected": {"formula": "state * 24", "unit_of_measurement": "¢"}}}  # Reference by state alias

        # Parse the attribute formula
        attr_config = sensor_data["attributes"]["daily_projected"]
        formula_config = config_manager._parse_attribute_formula("energy_cost_analysis", "daily_projected", attr_config, sensor_data)

        # The formula should contain 'state'
        assert formula_config.formula == "state * 24"

        # Variables should include the sensor key reference and inherited variables
        assert "energy_cost_analysis" in formula_config.variables
        assert "current_power" in formula_config.variables
        assert "electricity_rate" in formula_config.variables

        # Test evaluation - we need to provide the 'state' value in context
        context = {"state": 25.0, "current_power": 1000, "electricity_rate": 25, "energy_cost_analysis": 25.0}  # Main sensor calculated value
        result = evaluator.evaluate_formula(formula_config, context)
        assert result["success"] is True
        assert result["value"] == 600.0  # 25 * 24 = 600

    def test_sensor_key_reference(self, config_manager, evaluator):
        """Test referencing main sensor by sensor key."""
        sensor_data = {"name": "Energy Cost Analysis", "formula": "current_power * electricity_rate / 1000", "variables": {"current_power": "sensor.span_panel_instantaneous_power", "electricity_rate": "input_number.electricity_rate_cents_kwh"}, "attributes": {"monthly_projected": {"formula": "energy_cost_analysis * 24 * 30", "unit_of_measurement": "¢"}}}  # Reference by sensor key

        attr_config = sensor_data["attributes"]["monthly_projected"]
        formula_config = config_manager._parse_attribute_formula("energy_cost_analysis", "monthly_projected", attr_config, sensor_data)

        # Should have sensor key as variable pointing to entity_id
        assert "energy_cost_analysis" in formula_config.variables
        assert formula_config.variables["energy_cost_analysis"] == "sensor.syn2_energy_cost_analysis"

        # Test evaluation
        context = {"current_power": 1000, "electricity_rate": 25, "energy_cost_analysis": 25.0}  # This gets resolved from entity state
        result = evaluator.evaluate_formula(formula_config, context)
        assert result["success"] is True
        assert result["value"] == 18000.0  # 25 * 24 * 30 = 18000

    def test_entity_id_reference(self, config_manager, evaluator):
        """Test referencing main sensor by full entity_id."""
        sensor_data = {"name": "Energy Cost Analysis", "formula": "current_power * electricity_rate / 1000", "variables": {"current_power": "sensor.span_panel_instantaneous_power", "electricity_rate": "input_number.electricity_rate_cents_kwh"}, "attributes": {"annual_projected": {"formula": "sensor.syn2_energy_cost_analysis * 24 * 365", "unit_of_measurement": "¢"}}}  # Reference by entity_id

        attr_config = sensor_data["attributes"]["annual_projected"]
        formula_config = config_manager._parse_attribute_formula("energy_cost_analysis", "annual_projected", attr_config, sensor_data)

        # Should parse as direct entity reference (no need for variables)
        # But inherited variables should still be present
        assert "current_power" in formula_config.variables
        assert "electricity_rate" in formula_config.variables

        # Test evaluation - the evaluator should resolve the entity_id from hass.states
        # We don't need to provide manual context for the entity_id since it's in dependencies
        context = None  # Let evaluator resolve everything from dependencies
        result = evaluator.evaluate_formula(formula_config, context)

        assert result["success"] is True
        assert result["value"] == 219000.0  # 25 * 24 * 365 = 219000

    def test_all_reference_patterns_in_single_sensor(self, config_manager):
        """Test that all three reference patterns can coexist in a single sensor."""
        sensor_data = {"name": "Energy Cost Analysis", "formula": "current_power * electricity_rate / 1000", "variables": {"current_power": "sensor.span_panel_instantaneous_power", "electricity_rate": "input_number.electricity_rate_cents_kwh"}, "attributes": {"daily_projected": {"formula": "state * 24", "unit_of_measurement": "¢"}, "monthly_projected": {"formula": "energy_cost_analysis * 24 * 30", "unit_of_measurement": "¢"}, "annual_projected": {"formula": "sensor.syn2_energy_cost_analysis * 24 * 365", "unit_of_measurement": "¢"}}}

        # Parse all three attributes
        for attr_name in ["daily_projected", "monthly_projected", "annual_projected"]:
            attr_config = sensor_data["attributes"][attr_name]
            formula_config = config_manager._parse_attribute_formula("energy_cost_analysis", attr_name, attr_config, sensor_data)

            # All should inherit parent variables
            assert "current_power" in formula_config.variables
            assert "electricity_rate" in formula_config.variables

            # All should have sensor key reference
            assert "energy_cost_analysis" in formula_config.variables
            assert formula_config.variables["energy_cost_analysis"] == "sensor.syn2_energy_cost_analysis"

    def test_entity_id_reference_in_main_formula(self, config_manager, evaluator):
        """Test entity_id reference in main formula (not just attributes)."""
        sensor_data = {
            "name": "Grid Dependency Analysis",
            "formula": "sensor.span_panel_instantaneous_power + sensor.syn2_energy_cost_analysis",
            # No explicit variables - should auto-inject
        }

        formula_config = config_manager._parse_single_formula("grid_dependency", sensor_data)

        # Should auto-inject both entity references
        assert "sensor.span_panel_instantaneous_power" in formula_config.variables
        assert "sensor.syn2_energy_cost_analysis" in formula_config.variables

        # Test evaluation
        context = None  # Let evaluator resolve from dependencies
        result = evaluator.evaluate_formula(formula_config, context)
        assert result["success"] is True
        assert result["value"] == 1025.0  # 1000 + 25 = 1025

    def test_sensor_key_reference_in_main_formula(self, config_manager, evaluator):
        """Test sensor key reference in main formula."""
        # Create a sensor that references another synthetic sensor by key
        dependent_sensor_data = {
            "name": "Enhanced Power Analysis",
            "formula": "base_power_analysis * efficiency_factor",
            "variables": {
                "base_power_analysis": "sensor.syn2_base_power_analysis",  # Explicit variable definition
                "efficiency_factor": "input_number.electricity_rate_cents_kwh",
            },
        }

        formula_config = config_manager._parse_single_formula("enhanced_power", dependent_sensor_data)

        # Should have both explicit variables plus auto-injected entity references
        assert "base_power_analysis" in formula_config.variables
        assert "efficiency_factor" in formula_config.variables
        assert formula_config.variables["base_power_analysis"] == "sensor.syn2_base_power_analysis"

        # Should also auto-inject direct entity references found in variables
        assert "sensor.syn2_base_power_analysis" in formula_config.variables
        assert "input_number.electricity_rate_cents_kwh" in formula_config.variables
