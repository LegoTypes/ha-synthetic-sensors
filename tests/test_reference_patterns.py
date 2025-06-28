"""Test different reference patterns in attribute formulas.

This tests the three reference patterns mentioned in the README:
1. "state * 24" - by main state alias
2. "energy_cost_analysis * 24 * 30" - by main sensor key
3. "sensor.energy_cost_analysis * 24 * 365" - by entity_id
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.dependency_parser import DependencyParser
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
                "sensor.energy_cost_analysis": MagicMock(state="25.0"),  # 1000 * 25 / 1000 = 25
                "input_number.efficiency_factor": MagicMock(state="95"),
                "sensor.backup_power_system": MagicMock(state="100", attributes={"battery_level": 85}),
                "sensor.base_power_analysis": MagicMock(state="500"),
                "sensor.base_power_meter": MagicMock(state="750"),
                "input_number.base_efficiency": MagicMock(state="90"),
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

    @pytest.fixture
    def reference_patterns_yaml(self):
        """Load the reference patterns YAML fixture."""
        fixture_path = Path(__file__).parent / "yaml_fixtures" / "reference_patterns.yaml"
        with open(fixture_path) as f:
            return yaml.safe_load(f)

    def test_state_alias_reference(self, config_manager, evaluator, reference_patterns_yaml):
        """Test referencing main sensor state using 'state' alias."""
        config = config_manager._parse_yaml_config(reference_patterns_yaml)

        # Find the energy_cost_analysis sensor and its daily_projected attribute
        sensor_config = next(s for s in config.sensors if s.unique_id == "energy_cost_analysis")
        daily_formula = next(f for f in sensor_config.formulas if f.id == "energy_cost_analysis_daily_projected")

        # The formula should contain 'state'
        assert daily_formula.formula == "state * 24"

        # Variables should include the sensor key reference and inherited variables
        assert "energy_cost_analysis" in daily_formula.variables
        assert "current_power" in daily_formula.variables
        assert "electricity_rate" in daily_formula.variables

        # Test evaluation - we need to provide the 'state' value in context
        context = {
            "state": 25.0,
            "current_power": 1000,
            "electricity_rate": 25,
            "energy_cost_analysis": 25.0,
        }
        result = evaluator.evaluate_formula(daily_formula, context)
        assert result["success"] is True
        assert result["value"] == 600.0  # 25 * 24 = 600

    def test_sensor_key_reference(self, config_manager, evaluator, reference_patterns_yaml):
        """Test referencing main sensor by sensor key."""
        config = config_manager._parse_yaml_config(reference_patterns_yaml)

        # Find the energy_cost_analysis sensor and its monthly_projected attribute
        sensor_config = next(s for s in config.sensors if s.unique_id == "energy_cost_analysis")
        monthly_formula = next(f for f in sensor_config.formulas if f.id == "energy_cost_analysis_monthly_projected")

        # Should have sensor key as variable pointing to entity_id
        assert "energy_cost_analysis" in monthly_formula.variables
        assert monthly_formula.variables["energy_cost_analysis"] == "sensor.energy_cost_analysis"

        # Test evaluation
        context = {
            "current_power": 1000,
            "electricity_rate": 25,
            "energy_cost_analysis": 25.0,
        }
        result = evaluator.evaluate_formula(monthly_formula, context)
        assert result["success"] is True
        assert result["value"] == 18000.0  # 25 * 24 * 30 = 18000

    def test_entity_id_reference(self, config_manager, evaluator, reference_patterns_yaml):
        """Test referencing main sensor by full entity_id."""
        config = config_manager._parse_yaml_config(reference_patterns_yaml)

        # Find the energy_cost_analysis sensor and its annual_projected attribute
        sensor_config = next(s for s in config.sensors if s.unique_id == "energy_cost_analysis")
        annual_formula = next(f for f in sensor_config.formulas if f.id == "energy_cost_analysis_annual_projected")

        # Should parse as direct entity reference (no need for variables)
        # But inherited variables should still be present
        assert "current_power" in annual_formula.variables
        assert "electricity_rate" in annual_formula.variables

        # Test evaluation - the evaluator should resolve the entity_id from hass.states
        context = None  # Let evaluator resolve everything from dependencies
        result = evaluator.evaluate_formula(annual_formula, context)

        assert result["success"] is True
        assert result["value"] == 219000.0  # 25 * 24 * 365 = 219000

    def test_all_reference_patterns_in_single_sensor(self, config_manager, reference_patterns_yaml):
        """Test that all three reference patterns can coexist in a single sensor."""
        config = config_manager._parse_yaml_config(reference_patterns_yaml)

        # Find the comprehensive_analysis sensor which has all three patterns
        sensor_config = next(s for s in config.sensors if s.unique_id == "comprehensive_analysis")

        # Get all three attribute formulas
        daily_formula = next(f for f in sensor_config.formulas if f.id == "comprehensive_analysis_daily_state_ref")
        monthly_formula = next(f for f in sensor_config.formulas if f.id == "comprehensive_analysis_monthly_key_ref")
        annual_formula = next(f for f in sensor_config.formulas if f.id == "comprehensive_analysis_annual_entity_ref")

        # All should inherit parent variables
        for formula in [daily_formula, monthly_formula, annual_formula]:
            assert "base_power" in formula.variables
            assert "base_efficiency" in formula.variables
            # All should have sensor key reference
            assert "comprehensive_analysis" in formula.variables
            assert formula.variables["comprehensive_analysis"] == "sensor.comprehensive_analysis"

    def test_entity_id_reference_in_main_formula(self, config_manager, evaluator, reference_patterns_yaml):
        """Test entity_id reference in main formula (not just attributes)."""
        config = config_manager._parse_yaml_config(reference_patterns_yaml)

        # Find the grid_dependency_analysis sensor
        sensor_config = next(s for s in config.sensors if s.unique_id == "grid_dependency_analysis")
        formula_config = sensor_config.formulas[0]  # Main formula

        # Should auto-inject both entity references
        assert "sensor.span_panel_instantaneous_power" in formula_config.variables
        assert "sensor.energy_cost_analysis" in formula_config.variables

        # Test evaluation
        context = None  # Let evaluator resolve from dependencies
        result = evaluator.evaluate_formula(formula_config, context)
        assert result["success"] is True
        assert result["value"] == 1025.0  # 1000 + 25 = 1025

    def test_sensor_key_reference_in_main_formula(self, config_manager, evaluator, reference_patterns_yaml):
        """Test sensor key reference in main formula."""
        config = config_manager._parse_yaml_config(reference_patterns_yaml)

        # Find the enhanced_power_analysis sensor
        sensor_config = next(s for s in config.sensors if s.unique_id == "enhanced_power_analysis")
        formula_config = sensor_config.formulas[0]  # Main formula

        # Should have both explicit variables plus auto-injected entity references
        assert "base_power_analysis" in formula_config.variables
        assert "efficiency_factor" in formula_config.variables
        assert formula_config.variables["base_power_analysis"] == "sensor.base_power_analysis"

        # Should also auto-inject direct entity references found in variables
        assert "sensor.base_power_analysis" in formula_config.variables
        assert "input_number.electricity_rate_cents_kwh" in formula_config.variables

    def test_entity_id_with_attribute_access(self, config_manager, reference_patterns_yaml):
        """Test entity_id references combined with attribute access."""
        config = config_manager._parse_yaml_config(reference_patterns_yaml)

        # Find the power_efficiency sensor and its battery_adjusted attribute
        sensor_config = next(s for s in config.sensors if s.unique_id == "power_efficiency")
        battery_formula = next(f for f in sensor_config.formulas if f.id == "power_efficiency_battery_adjusted")

        # Should inherit parent variables plus have main sensor reference
        assert "current_power" in battery_formula.variables  # Inherited
        assert "device_efficiency" in battery_formula.variables  # Inherited
        assert "backup_device" in battery_formula.variables  # Inherited
        assert "power_efficiency" in battery_formula.variables  # Main sensor reference

        # Should also extract the direct entity_id reference
        assert "sensor.energy_cost_analysis" in battery_formula.variables

        # The formula should parse correctly with dependency extraction
        parser = DependencyParser()
        parsed = parser.parse_formula_dependencies(battery_formula.formula, battery_formula.variables)

        # Should detect the dot notation reference
        assert "backup_device.battery_level" in parsed.dot_notation_refs

        # Should detect the direct entity reference as static dependency
        assert "sensor.energy_cost_analysis" in parsed.static_dependencies
