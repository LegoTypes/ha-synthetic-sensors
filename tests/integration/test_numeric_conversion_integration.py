"""Integration test for numeric string conversion."""

from pathlib import Path
from unittest.mock import MagicMock
import yaml

import pytest

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.evaluator import Evaluator


class TestNumericConversionIntegration:
    """Test numeric string conversion in integration context."""

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a ConfigManager instance."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def numeric_conversion_yaml(self):
        """Load the numeric conversion test YAML fixture."""
        fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "test_numeric_conversion.yaml"
        with open(fixture_path) as f:
            return yaml.safe_load(f)

    def test_numeric_string_conversion_with_yaml(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, numeric_conversion_yaml
    ):
        """Test that numeric strings are properly converted using YAML configuration."""

        # Set up mock state with numeric string value
        mock_state = MagicMock()
        mock_state.state = "1.0"  # Numeric string that should be converted
        mock_state.entity_id = "sensor.circuit_a_power"
        mock_state.attributes = {"device_class": "power"}

        def mock_states_get(entity_id):
            if entity_id == "sensor.circuit_a_power":
                return mock_state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        # Parse the YAML configuration
        config = config_manager._parse_yaml_config(numeric_conversion_yaml)

        # Find the numeric test sensor
        numeric_sensor = next(s for s in config.sensors if s.unique_id == "numeric_test")

        # Test the formula evaluation
        evaluator = Evaluator(mock_hass)

        # Test the main formula
        main_formula = numeric_sensor.formulas[0]
        print(f"Testing formula: {main_formula.formula}")
        print(f"Expected: power_sensor + 0 where power_sensor = 1.0, so result should be 1.0")

        # : Create proper context for evaluator
        from ha_synthetic_sensors.evaluation_context import HierarchicalEvaluationContext
        from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalContextDict

        hierarchical_context = HierarchicalEvaluationContext("numeric_test")
        context = HierarchicalContextDict(hierarchical_context)

        result = evaluator.evaluate_formula(main_formula, context)

        # The numeric string "1.0" should be converted to 1.0 and arithmetic should work
        assert result.get("success") is True, f"Formula evaluation failed: {result}"
        # Accept either numeric value or ReferenceValue-wrapped value depending on API
        # If wrapped, extract numeric portion
        value = result.get("value")
        if isinstance(value, dict) and value.get("success") is not None:
            value = value.get("value")
        assert float(value) == 1.0, f"Expected 1.0, got {value}"
        # Use constant STATE_OK if available in evaluator results, otherwise accept 'ok' string
        assert result.get("state") in ("ok",), f"Expected 'ok' state, got {result.get('state')}"

    def test_direct_entity_reference_with_yaml(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, numeric_conversion_yaml
    ):
        """Test direct entity reference using YAML configuration."""

        # Set up mock state with numeric string value
        mock_state = MagicMock()
        mock_state.state = "1.0"  # Numeric string
        mock_state.entity_id = "sensor.circuit_a_power"
        mock_state.attributes = {"device_class": "power"}

        def mock_states_get(entity_id):
            if entity_id == "sensor.circuit_a_power":
                return mock_state
            return None

        mock_hass.states.get.side_effect = mock_states_get

        # Parse the YAML configuration
        config = config_manager._parse_yaml_config(numeric_conversion_yaml)

        # Find the direct reference test sensor
        direct_sensor = next(s for s in config.sensors if s.unique_id == "direct_reference_test")

        # Test the formula evaluation
        evaluator = Evaluator(mock_hass)

        # Test the main formula
        main_formula = direct_sensor.formulas[0]
        print(f"Testing formula: {main_formula.formula}")
        print(f"Expected: Direct reference to sensor.circuit_a_power with state '1.0'")

        # : Create proper context for evaluator
        from ha_synthetic_sensors.evaluation_context import HierarchicalEvaluationContext
        from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalContextDict

        hierarchical_context = HierarchicalEvaluationContext("direct_reference_test")
        context = HierarchicalContextDict(hierarchical_context)

        result = evaluator.evaluate_formula(main_formula, context)

        print(f"Result: {result}")

        # Direct entity reference behavior - what should this return?
        assert result["success"] is True, f"Formula evaluation failed: {result}"
        # This will help us understand what the current behavior is
        print(f"Direct reference result - value: {result['value']}, state: {result['state']}")
