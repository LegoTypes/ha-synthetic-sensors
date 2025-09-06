"""Comprehensive tests for all alternate state handler forms including FALLBACK and STATE_NONE.

Tests all supported forms:
1. Literal values: numbers, strings, booleans
2. Object form: {formula: "...", variables: {...}}
3. Special YAML constants: STATE_NONE (converted to Python None)
4. New FALLBACK handler priority system
"""

from __future__ import annotations

import pytest
from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.config_models import AlternateStateHandler
from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalContextDict
from ha_synthetic_sensors.evaluation_context import HierarchicalEvaluationContext


def _create_empty_context() -> HierarchicalContextDict:
    """Create empty HierarchicalContextDict for testing - architectural compliance."""
    hierarchical_context = HierarchicalEvaluationContext("test")
    return HierarchicalContextDict(hierarchical_context)


def _dp_for(values: dict[str, tuple[object, bool]]):
    """Create a data provider function for testing."""

    def provider(entity_id: str):
        val, exists = values.get(entity_id, (None, False))
        return {"value": val, "exists": exists}

    return provider


class TestAlternateHandlerForms:
    """Test all supported forms of alternate state handlers."""

    def test_literal_numeric_handlers(self, mock_hass, mock_entity_registry, mock_states):
        """Test literal numeric values: int, float."""
        # Setup unavailable entity to trigger handlers
        mock_entity_registry.register_entity("sensor.missing", "sensor.missing", "sensor")
        mock_states.register_state("sensor.missing", "unavailable", {})

        ev = Evaluator(mock_hass)
        ev.update_integration_entities({"sensor.missing"})

        # Set up data provider to return the unavailable state
        data_provider = _dp_for({"sensor.missing": ("unavailable", True)})
        ev._dependency_handler.data_provider_callback = data_provider

        # Test integer literal
        cfg_int = FormulaConfig(
            id="int_test",
            formula="missing_var + 1",  # Will fail, trigger handler
            variables={"missing_var": "sensor.missing"},  # Entity reference
            alternate_state_handler=AlternateStateHandler(unavailable=42, unknown=100, none=0, fallback=999),
        )
        result = ev.evaluate_formula(cfg_int, _create_empty_context())
        assert result["success"] is True
        assert result["value"] == 42  # unavailable handler triggered

        # Test float literal
        cfg_float = FormulaConfig(
            id="float_test",
            formula="missing_var * 2",
            variables={"missing_var": "sensor.missing"},
            alternate_state_handler=AlternateStateHandler(unavailable=3.14, unknown=2.71, none=0.0, fallback=99.9),
        )
        result = ev.evaluate_formula(cfg_float, _create_empty_context())
        assert result["success"] is True
        assert result["value"] == 3.14

    def test_literal_string_handlers(self, mock_hass, mock_entity_registry, mock_states):
        """Test literal string values."""
        mock_entity_registry.register_entity("sensor.missing", "sensor.missing", "sensor")
        mock_states.register_state("sensor.missing", "unknown", {})

        ev = Evaluator(mock_hass)
        ev.update_integration_entities({"sensor.missing"})

        # Set up data provider to return the unknown state
        data_provider = _dp_for({"sensor.missing": ("unknown", True)})
        ev._dependency_handler.data_provider_callback = data_provider

        cfg = FormulaConfig(
            id="string_test",
            formula="str(missing_var) + 'test'",
            variables={"missing_var": "sensor.missing"},
            alternate_state_handler=AlternateStateHandler(
                unavailable="unavailable_string",  # Simple string literal
                unknown="unknown_string",  # Simple string literal
                none="none_string",  # Simple string literal
                fallback="fallback_string",  # Simple string literal
            ),
        )
        result = ev.evaluate_formula(cfg, _create_empty_context())
        assert result["success"] is True
        assert result["value"] == "unknown_string"  # unknown handler triggered

    def test_literal_boolean_handlers(self, mock_hass, mock_entity_registry, mock_states):
        """Test literal boolean values."""
        mock_entity_registry.register_entity("sensor.missing", "sensor.missing", "sensor")
        mock_states.register_state("sensor.missing", "unavailable", {})

        ev = Evaluator(mock_hass)
        ev.update_integration_entities({"sensor.missing"})

        # Set up data provider to return the unavailable state
        data_provider = _dp_for({"sensor.missing": ("unavailable", True)})
        ev._dependency_handler.data_provider_callback = data_provider

        cfg = FormulaConfig(
            id="bool_test",
            formula="missing_var > 0",
            variables={"missing_var": "sensor.missing"},
            alternate_state_handler=AlternateStateHandler(unavailable=True, unknown=False, none=True, fallback=False),
        )
        result = ev.evaluate_formula(cfg, _create_empty_context())
        assert result["success"] is True
        assert result["value"] is True  # unavailable handler triggered

    def test_object_form_handlers(self, mock_hass, mock_entity_registry, mock_states):
        """Test object form: {formula: "...", variables: {...}}."""
        mock_entity_registry.register_entity("sensor.missing", "sensor.missing", "sensor")
        mock_states.register_state("sensor.missing", "unavailable", {})

        ev = Evaluator(mock_hass)
        ev.update_integration_entities({"sensor.missing"})

        # Set up data provider to return the unavailable state
        data_provider = _dp_for({"sensor.missing": ("unavailable", True)})
        ev._dependency_handler.data_provider_callback = data_provider

        cfg = FormulaConfig(
            id="object_test",
            formula="missing_var * 2",
            variables={"missing_var": "sensor.missing"},
            alternate_state_handler=AlternateStateHandler(
                unavailable={
                    "formula": "backup_value * multiplier + offset",
                    "variables": {"backup_value": 10, "multiplier": 2, "offset": 5},
                },
                unknown={"formula": "default_unknown", "variables": {"default_unknown": -1}},
                none={"formula": "none_calc", "variables": {"none_calc": 0}},
                fallback={"formula": "fallback_calc + extra", "variables": {"fallback_calc": 500, "extra": 99}},
            ),
        )

        # Create a proper sensor configuration for the test
        from ha_synthetic_sensors.config_models import SensorConfig

        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            entity_id="sensor.test_sensor",
            device_identifier="test_device",
            formulas=[cfg],
        )

        result = ev.evaluate_formula_with_sensor_config(cfg, _create_empty_context(), sensor_config)
        assert result["success"] is True
        assert result["value"] == 25  # (10 * 2) + 5 = 25

    def test_none_value_handlers(self, mock_hass, mock_entity_registry, mock_states):
        """Test Python None values (for energy sensors)."""
        # Setup entity with None state to trigger none handler
        mock_entity_registry.register_entity("sensor.none_entity", "sensor.none_entity", "sensor")
        mock_states.register_state("sensor.none_entity", None, {})

        ev = Evaluator(mock_hass)
        ev.update_integration_entities({"sensor.none_entity"})

        # Set up data provider to return the None state
        data_provider = _dp_for({"sensor.none_entity": (None, True)})
        ev._dependency_handler.data_provider_callback = data_provider

        cfg = FormulaConfig(
            id="none_test",
            formula="entity_state",  # Use valid variable name instead of reserved 'state' token
            variables={"entity_state": "sensor.none_entity"},
            alternate_state_handler=AlternateStateHandler(
                unavailable=0,
                unknown=-1,
                none=None,  # Preserve None for energy sensors
                fallback=999,
            ),
        )
        result = ev.evaluate_formula(cfg, _create_empty_context())
        assert result["success"] is True
        assert result["value"] is None  # none handler preserves None when entity_state is None


class TestFallbackPrioritySystem:
    """Test the FALLBACK handler priority system."""

    def test_specific_handler_overrides_fallback(self, mock_hass, mock_entity_registry, mock_states):
        """Specific handlers should take priority over FALLBACK."""
        mock_entity_registry.register_entity("sensor.missing", "sensor.missing", "sensor")
        mock_states.register_state("sensor.missing", "unavailable", {})

        ev = Evaluator(mock_hass)
        ev.update_integration_entities({"sensor.missing"})

        # Set up data provider to return the unavailable state
        data_provider = _dp_for({"sensor.missing": ("unavailable", True)})
        ev._dependency_handler.data_provider_callback = data_provider

        cfg = FormulaConfig(
            id="priority_test",
            formula="missing_var + 1",
            variables={"missing_var": "sensor.missing"},
            alternate_state_handler=AlternateStateHandler(
                unavailable=100,  # Specific handler
                fallback=999,  # Should NOT be used
            ),
        )
        result = ev.evaluate_formula(cfg, _create_empty_context())
        assert result["success"] is True
        assert result["value"] == 100  # Specific handler used, not fallback

    def test_fallback_when_no_specific_handler(self, mock_hass, mock_entity_registry, mock_states):
        """FALLBACK should be used when no specific handler matches."""
        mock_entity_registry.register_entity("sensor.missing", "sensor.missing", "sensor")
        mock_states.register_state("sensor.missing", "unavailable", {})

        ev = Evaluator(mock_hass)
        ev.update_integration_entities({"sensor.missing"})

        # Set up data provider to return the unavailable state
        data_provider = _dp_for({"sensor.missing": ("unavailable", True)})
        ev._dependency_handler.data_provider_callback = data_provider

        cfg = FormulaConfig(
            id="fallback_test",
            formula="missing_var + 1",
            variables={"missing_var": "sensor.missing"},
            alternate_state_handler=AlternateStateHandler(
                # No unavailable handler defined
                unknown=200,  # Different error type
                fallback=777,  # Should be used
            ),
        )
        result = ev.evaluate_formula(cfg, _create_empty_context())
        assert result["success"] is True
        assert result["value"] == 777  # Fallback used

    def test_fallback_handler_behavior(self, mock_hass, mock_entity_registry, mock_states):
        """Test FALLBACK handler catches all alternate states when no specific handler defined."""
        mock_entity_registry.register_entity("sensor.missing", "sensor.missing", "sensor")
        mock_states.register_state("sensor.missing", "unavailable", {})

        ev = Evaluator(mock_hass)
        ev.update_integration_entities({"sensor.missing"})

        # Set up data provider to return the unavailable state
        data_provider = _dp_for({"sensor.missing": ("unavailable", True)})
        ev._dependency_handler.data_provider_callback = data_provider

        # Test that FALLBACK handler catches unavailable state when no specific unavailable handler
        cfg_fallback_catches_all = FormulaConfig(
            id="fallback_catches_all",
            formula="missing_var + 1",
            variables={"missing_var": "sensor.missing"},
            alternate_state_handler=AlternateStateHandler(
                # Only unknown and fallback defined, no unavailable handler
                unknown=555,
                fallback=999,  # Should catch unavailable state
            ),
        )
        result = ev.evaluate_formula(cfg_fallback_catches_all, _create_empty_context())
        assert result["success"] is True
        assert result["value"] == 999  # FALLBACK handler used for unavailable state

        # Test that when no specific handler and no FALLBACK, returns None (sensor becomes unavailable)
        cfg_no_handlers = FormulaConfig(
            id="no_handlers",
            formula="missing_var + 1",
            variables={"missing_var": "sensor.missing"},
            alternate_state_handler=AlternateStateHandler(
                # Only unknown defined, no unavailable handler, no fallback
                unknown=555
            ),
        )
        result = ev.evaluate_formula(cfg_no_handlers, _create_empty_context())
        assert result["success"] is True
        assert result["value"] is None  # No handler for unavailable state, returns None

        # Test that specific handlers take priority over FALLBACK
        cfg_specific_over_fallback = FormulaConfig(
            id="specific_over_fallback",
            formula="missing_var + 1",
            variables={"missing_var": "sensor.missing"},
            alternate_state_handler=AlternateStateHandler(
                unavailable=333,  # Specific handler should be used
                fallback=777,  # Should NOT be used
            ),
        )
        result = ev.evaluate_formula(cfg_specific_over_fallback, _create_empty_context())
        assert result["success"] is True
        assert result["value"] == 333  # Specific handler used, not fallback


class TestStateNoneYamlConstant:
    """Test STATE_NONE YAML constant support."""

    def test_state_none_yaml_processing(self):
        """Test that STATE_NONE in YAML gets converted to Python None."""
        # This would typically be handled by YAML processing layer
        # For now, we test the concept by directly using None
        handler = AlternateStateHandler(
            unavailable=0,
            unknown=-1,
            none=None,  # This is what STATE_NONE should become
            fallback=999,
        )

        # Verify the handler accepts None
        assert handler.none is None
        assert handler.unavailable == 0
        assert handler.unknown == -1
        assert handler.fallback == 999

    def test_energy_sensor_none_preservation(self, mock_hass, mock_entity_registry, mock_states):
        """Test that None values are preserved for energy sensors (no ValueError)."""
        # This simulates what would happen with STATE_NONE in YAML
        mock_entity_registry.register_entity("sensor.energy", "sensor.energy", "sensor")
        mock_states.register_state("sensor.energy", None, {})

        ev = Evaluator(mock_hass)
        ev.update_integration_entities({"sensor.energy"})

        # Set up data provider to return the None state
        data_provider = _dp_for({"sensor.energy": (None, True)})
        ev._dependency_handler.data_provider_callback = data_provider

        cfg = FormulaConfig(
            id="energy_none",
            formula="state",
            variables={"state": "sensor.energy"},
            alternate_state_handler=AlternateStateHandler(
                none=None  # STATE_NONE equivalent - preserve None for energy sensors
            ),
        )
        result = ev.evaluate_formula(cfg, _create_empty_context())
        assert result["success"] is True
        assert result["value"] is None  # None preserved, no ValueError


class TestMixedHandlerScenarios:
    """Test complex scenarios with mixed handler types."""

    def test_mixed_literal_and_object_handlers(self, mock_hass, mock_entity_registry, mock_states):
        """Test mixing literal and object form handlers."""
        mock_entity_registry.register_entity("sensor.test", "sensor.test", "sensor")
        mock_states.register_state("sensor.test", "unknown", {})

        ev = Evaluator(mock_hass)
        ev.update_integration_entities({"sensor.test"})

        # Set up data provider to return the unknown state
        data_provider = _dp_for({"sensor.test": ("unknown", True)})
        ev._dependency_handler.data_provider_callback = data_provider

        cfg = FormulaConfig(
            id="mixed_test",
            formula="test_var + 1",
            variables={"test_var": "sensor.test"},
            alternate_state_handler=AlternateStateHandler(
                unavailable=42,  # Literal
                unknown={  # Object form
                    "formula": "base * factor",
                    "variables": {"base": 10, "factor": 3},
                },
                none=None,  # Literal None
                fallback="fallback_string",  # Literal string
            ),
        )
        result = ev.evaluate_formula(cfg, _create_empty_context())
        assert result["success"] is True
        assert result["value"] == 30  # unknown object handler: 10 * 3

    def test_all_handlers_defined_priority(self, mock_hass, mock_entity_registry, mock_states):
        """Test priority when all handlers are defined."""
        mock_entity_registry.register_entity("sensor.unavailable", "sensor.unavailable", "sensor")
        mock_states.register_state("sensor.unavailable", "unavailable", {})

        ev = Evaluator(mock_hass)
        ev.update_integration_entities({"sensor.unavailable"})

        # Set up data provider to return the unavailable state
        data_provider = _dp_for({"sensor.unavailable": ("unavailable", True)})
        ev._dependency_handler.data_provider_callback = data_provider

        cfg = FormulaConfig(
            id="all_handlers",
            formula="unavailable_var + 1",
            variables={"unavailable_var": "sensor.unavailable"},
            alternate_state_handler=AlternateStateHandler(
                unavailable=100,  # Should be used (specific match)
                unknown=200,
                none=300,
                fallback=400,  # Should NOT be used
            ),
        )
        result = ev.evaluate_formula(cfg, _create_empty_context())
        assert result["success"] is True
        assert result["value"] == 100  # Specific unavailable handler used


# Integration test for YAML processing (would need YAML layer integration)
def test_state_none_yaml_integration():
    """Integration test for STATE_NONE YAML constant.

    This test verifies that a YAML-level STATE_NONE would conceptually map to Python None.
    The full YAML processing layer is out of scope for unit tests, so here we assert the
    conceptual mapping and ensure no exceptions are raised when constructing handlers
    with None values.
    """
    # Simulate YAML-derived handler mapping where STATE_NONE -> None
    handler = AlternateStateHandler(unavailable=0, unknown=-1, none=None, fallback=999)

    # Verify the handler accepts None and values are preserved
    assert handler.none is None
    assert handler.unavailable == 0
    assert handler.unknown == -1
    assert handler.fallback == 999
