"""Test that None values and bad data cause fatal errors instead of warnings."""

from unittest.mock import MagicMock

import pytest

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.constants_alternate import STATE_NONE
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.exceptions import DataValidationError
from ha_synthetic_sensors.type_definitions import DataProviderResult, ReferenceValue


def test_data_provider_returning_none_causes_fatal_error(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that when data provider callback returns None, it causes a fatal DataValidationError."""

    # Create evaluator with data provider callback that returns None
    def bad_data_provider(entity_id: str) -> None:
        return None  # This should cause a fatal error

    evaluator = Evaluator(mock_hass, data_provider_callback=bad_data_provider)
    evaluator.update_integration_entities({"sensor.test"})  # Tell evaluator this entity comes from integration

    config = FormulaConfig(id="test_formula", formula="test_var + 10", variables={"test_var": "sensor.test"})

    # Should raise DataValidationError for None data provider
    with pytest.raises(DataValidationError, match="Data provider callback returned None"):
        evaluator.evaluate_formula(config)


def test_data_provider_returning_none_causes_fatal_error_consistent(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that when data provider callback returns None, it consistently causes a fatal error."""

    # Create evaluator with data provider callback that returns None
    def bad_data_provider(entity_id: str) -> None:
        return None  # This should cause a fatal error

    evaluator = Evaluator(mock_hass, data_provider_callback=bad_data_provider)
    evaluator.update_integration_entities({"sensor.test"})  # Tell evaluator this entity comes from integration

    config = FormulaConfig(id="test_formula", formula="test_var + 10", variables={"test_var": "sensor.test"})

    # Should raise DataValidationError for None data provider
    with pytest.raises(DataValidationError, match="Data provider callback returned None"):
        evaluator.evaluate_formula(config)


def test_data_provider_returning_none_value_handled_gracefully(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that when data provider returns valid structure but None value, it maps to 'unknown'.

    In Home Assistant, entities with no value (None) return state 'unknown'.
    This is the correct behavior for integration scenarios.
    """

    # Create evaluator with data provider that returns None value
    def none_value_provider(entity_id: str) -> DataProviderResult:
        return {
            "value": None,
            "exists": True,
        }  # Entity exists but has None value - should be handled gracefully

    evaluator = Evaluator(mock_hass, data_provider_callback=none_value_provider)
    evaluator.update_integration_entities({"sensor.test"})  # Tell evaluator this entity comes from integration

    config = FormulaConfig(id="test_formula", formula="test_var", variables={"test_var": "sensor.test"})

    # Should handle None values gracefully by returning a semantic alternate state (no numeric value)
    result = evaluator.evaluate_formula(config)
    assert result["success"] is True
    # Implementation may return OK with STATE_UNKNOWN; prefer the HA constant instead of raw strings
    assert result.get("state") in ("ok", STATE_UNKNOWN)
    assert result["value"] in (STATE_UNKNOWN, None)


def test_data_provider_returning_unavailable_state_handled_gracefully(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that unavailable state values are handled gracefully and map to STATE_UNAVAILABLE."""

    # Create evaluator with data provider that returns unavailable state
    def unavailable_provider(entity_id: str) -> DataProviderResult:
        return {"value": "unavailable", "exists": True}  # Should be handled gracefully

    evaluator = Evaluator(mock_hass, data_provider_callback=unavailable_provider)
    evaluator.update_integration_entities({"sensor.test"})  # Tell evaluator this entity comes from integration

    config = FormulaConfig(id="test_formula", formula="test_var", variables={"test_var": "sensor.test"})

    # Should handle gracefully with state reflection
    result = evaluator.evaluate_formula(config)

    assert result["success"] is True  # Non-fatal - reflects dependency state
    # Phase 1 preserves HA-provided state values; expect either STATE_UNAVAILABLE or STATE_UNKNOWN
    assert result.get("state") in (STATE_UNAVAILABLE, STATE_UNKNOWN)
    # Accept None or the HA state constant for value; prefer None for alternate states
    assert result.get("value") in (STATE_UNAVAILABLE, None)


def test_context_with_reference_value_objects(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that context variables are properly handled as ReferenceValue objects."""

    evaluator = Evaluator(mock_hass)

    config = FormulaConfig(id="test_formula", formula="test_var + 5", variables={})

    # Create context with ReferenceValue objects (ReferenceValue architecture)
    context = {"test_var": ReferenceValue("sensor.test", 10.0)}

    result = evaluator.evaluate_formula(config, context)
    assert result["success"] is True
    # Check the actual calculated value - should be 10.0 + 5 = 15.0
    assert result["value"] == 15.0, f"Expected 15.0 for test_var + 5, got {result['value']}"


def test_none_value_in_reference_value_handled_gracefully(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that None values in ReferenceValue objects map to 'unknown'.

    In Home Assistant, entities with no value (None) return state 'unknown'.
    This is the correct behavior for integration scenarios.
    """

    evaluator = Evaluator(mock_hass)

    config = FormulaConfig(id="test_formula", formula="test_var", variables={})

    # Create context with ReferenceValue containing None value
    context = {"test_var": ReferenceValue("sensor.test", None)}

    result = evaluator.evaluate_formula(config, context)
    # Should handle None values gracefully by returning a semantic alternate state (no numeric value)
    assert result["success"] is True
    assert result.get("state") in (STATE_UNKNOWN)
    assert result["value"] in (STATE_UNKNOWN, None)


def test_reference_value_extraction_in_formulas(mock_hass, mock_entity_registry, mock_states) -> None:
    """Test that formulas can extract values from ReferenceValue objects."""

    evaluator = Evaluator(mock_hass)

    config = FormulaConfig(id="test_formula", formula="var1 + var2 * 2", variables={})

    # Create context with ReferenceValue objects
    context = {"var1": ReferenceValue("sensor.var1", 5.0), "var2": ReferenceValue("sensor.var2", 3.0)}

    result = evaluator.evaluate_formula(config, context)
    assert result["success"] is True
    # Check the actual calculated value - should be 5.0 + (3.0 * 2) = 11.0
    assert result["value"] == 11.0, f"Expected 11.0 for var1 + var2 * 2, got {result['value']}"
