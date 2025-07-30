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
    def config_manager(self, mock_hass, mock_entity_registry, mock_states):
        """Create a ConfigManager instance."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def evaluator(self, mock_hass, mock_entity_registry, mock_states):
        """Create an Evaluator instance."""
        return Evaluator(mock_hass)

    @pytest.fixture
    def reference_patterns_yaml(self):
        """Load the reference patterns YAML fixture."""
        fixture_path = Path(__file__).parent.parent.parent / "examples" / "reference_patterns_example.yaml"
        with open(fixture_path) as f:
            return yaml.safe_load(f)

    def test_state_alias_reference(
        self, config_manager, evaluator, reference_patterns_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test referencing main sensor state using 'state' alias."""
        config = config_manager._parse_yaml_config(reference_patterns_yaml)

        # Find the energy_cost_analysis sensor and its daily_projected attribute
        sensor_config = next(s for s in config.sensors if s.unique_id == "energy_cost_analysis")
        daily_formula = next(f for f in sensor_config.formulas if f.id == "energy_cost_analysis_daily_projected")

        # The formula should contain 'state'
        assert daily_formula.formula == "state * 24"

        # Variables should include inherited variables but NOT sensor key reference since formula uses 'state'
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

    def test_sensor_key_reference(
        self, config_manager, evaluator, reference_patterns_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test referencing main sensor by sensor key."""
        config = config_manager._parse_yaml_config(reference_patterns_yaml)

        # Find the energy_cost_analysis sensor and its monthly_projected attribute
        sensor_config = next(s for s in config.sensors if s.unique_id == "energy_cost_analysis")
        monthly_formula = next(f for f in sensor_config.formulas if f.id == "energy_cost_analysis_monthly_projected")

        # Should NOT auto-inject sensor key references (removed for safety)
        # The formula should use explicit entity ID or state token instead
        assert "energy_cost_analysis" not in monthly_formula.variables

        # Test evaluation
        context = {
            "current_power": 1000,
            "electricity_rate": 25,
            "energy_cost_analysis": 25.0,
        }
        result = evaluator.evaluate_formula(monthly_formula, context)
        assert result["success"] is True
        assert result["value"] == 18000.0  # 25 * 24 * 30 = 18000

    def test_entity_id_reference(
        self, config_manager, evaluator, reference_patterns_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test referencing main sensor by full entity_id."""

        # Mock the entity state that the formula needs
        mock_state = MagicMock()
        mock_state.state = "25.0"  # The value that the formula expects
        evaluator._hass.states.get.return_value = mock_state

        # Set up data provider callback that uses hass.states.get
        def mock_data_provider(entity_id: str):
            state = evaluator._hass.states.get(entity_id)
            if state:
                return {"value": float(state.state), "exists": True}
            return {"value": None, "exists": False}

        # Set the data provider callback and enable HA lookups
        evaluator.data_provider_callback = mock_data_provider
        evaluator

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
        result = evaluator.evaluate_formula_with_sensor_config(annual_formula, context, sensor_config)

        assert result["success"] is True
        assert result["value"] == 273750.0  # 31.25 * 24 * 365 = 273750 (from common registry)

    def test_all_reference_patterns_in_single_sensor(
        self, config_manager, reference_patterns_yaml, mock_hass, mock_entity_registry, mock_states
    ):
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

        # All formulas should NOT auto-inject sensor key references (removed for safety)
        # daily_formula uses 'state' - no sensor key reference
        assert "comprehensive_analysis" not in daily_formula.variables

        # monthly_formula uses 'comprehensive_analysis' - should NOT auto-inject sensor key reference
        assert "comprehensive_analysis" not in monthly_formula.variables

        # annual_formula uses 'sensor.comprehensive_analysis' - no sensor key reference needed
        assert "comprehensive_analysis" not in annual_formula.variables

    def test_entity_id_reference_in_main_formula(
        self, config_manager, evaluator, reference_patterns_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test entity_id reference in main formula (not just attributes)."""

        # Set up data provider callback that uses hass.states.get
        def mock_data_provider(entity_id: str):
            state = evaluator._hass.states.get(entity_id)
            if state:
                return {"value": float(state.state), "exists": True}
            return {"value": None, "exists": False}

        # Set the data provider callback and enable HA lookups
        evaluator.data_provider_callback = mock_data_provider
        evaluator

        config = config_manager._parse_yaml_config(reference_patterns_yaml)

        # Find the grid_dependency_analysis sensor
        sensor_config = next(s for s in config.sensors if s.unique_id == "grid_dependency_analysis")
        formula_config = sensor_config.formulas[0]  # Main formula

        # Should auto-inject both entity references
        assert "sensor.span_panel_instantaneous_power" in formula_config.variables
        assert "sensor.energy_cost_analysis" in formula_config.variables

        # Test evaluation
        context = None  # Let evaluator resolve from dependencies
        result = evaluator.evaluate_formula_with_sensor_config(formula_config, context, sensor_config)
        assert result["success"] is True
        assert result["value"] == 1031.25  # 1000.0 + 31.25 = 1031.25 (from common registry)

    def test_sensor_key_reference_in_main_formula(
        self, config_manager, evaluator, reference_patterns_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test sensor key reference in main formula."""
        config = config_manager._parse_yaml_config(reference_patterns_yaml)

        # Find the enhanced_power_analysis sensor
        sensor_config = next(s for s in config.sensors if s.unique_id == "enhanced_power_analysis")
        formula_config = sensor_config.formulas[0]  # Main formula

        # Should have both explicit variables
        assert "base_power_analysis" in formula_config.variables
        assert "efficiency_factor" in formula_config.variables
        assert formula_config.variables["base_power_analysis"] == "sensor.base_power_analysis"
        assert formula_config.variables["efficiency_factor"] == "input_number.electricity_rate_cents_kwh"

        # Should NOT auto-inject entity references that are already properly referenced through variables
        # This is correct behavior - no duplication needed
        assert len(formula_config.variables) == 2  # Only the two explicit variables

    def test_entity_id_with_attribute_access(
        self, config_manager, reference_patterns_yaml, mock_hass, mock_entity_registry, mock_states
    ):
        """Test entity_id references combined with attribute access."""
        config = config_manager._parse_yaml_config(reference_patterns_yaml)

        # Find the power_efficiency sensor and its battery_adjusted attribute
        sensor_config = next(s for s in config.sensors if s.unique_id == "power_efficiency")
        battery_formula = next(f for f in sensor_config.formulas if f.id == "power_efficiency_battery_adjusted")

        # Should inherit parent variables but NOT main sensor reference since formula uses entity_id
        assert "current_power" in battery_formula.variables  # Inherited
        assert "device_efficiency" in battery_formula.variables  # Inherited
        assert "backup_device" in battery_formula.variables  # Inherited

        # Should also extract the direct entity_id reference
        assert "sensor.energy_cost_analysis" in battery_formula.variables

        # The formula should parse correctly with dependency extraction
        parser = DependencyParser()
        parsed = parser.parse_formula_dependencies(battery_formula.formula, battery_formula.variables)

        # Should detect the dot notation reference
        assert "backup_device.battery_level" in parsed.dot_notation_refs

        # Should detect the direct entity reference as static dependency
        assert "sensor.energy_cost_analysis" in parsed.static_dependencies
