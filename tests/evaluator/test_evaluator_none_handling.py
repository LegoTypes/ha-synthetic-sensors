"""Test evaluator handling of None values from data providers - graceful error handling."""

from unittest.mock import MagicMock

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.type_definitions import DataProviderResult


def test_evaluator_handles_unknown_value_from_data_provider() -> None:
    """Test that evaluator properly handles unknown values from data provider callbacks gracefully."""
    # Mock Home Assistant instance
    mock_hass = MagicMock()
    mock_hass.states = MagicMock()

    # Mock data provider that returns unknown for an entity (e.g., panel-level sensor)
    def mock_data_provider(entity_id: str) -> DataProviderResult:
        if entity_id == "sensor.panel_power":
            return {"value": "unknown", "exists": True}  # Entity exists but has unknown value
        return {"value": None, "exists": False}  # Entity doesn't exist

    # Create evaluator with data provider
    evaluator = Evaluator(mock_hass, data_provider_callback=mock_data_provider)
    evaluator.update_integration_entities({"sensor.panel_power"})

    # Test simple variable reference where the variable resolves to unknown
    config = FormulaConfig(
        id="test_formula",
        formula="source_value",
        variables={"source_value": "sensor.panel_power"},
    )  # Simple variable reference

    # Should return success result with unknown state (graceful state reflection)
    result = evaluator.evaluate_formula(config)

    assert result["success"] is True  # Non-fatal - reflects dependency state
    assert result["state"] == "unknown"  # Reflects unknown dependency
    assert "sensor.panel_power" in result.get("unavailable_dependencies", [])


def test_evaluator_handles_unavailable_entity_reference() -> None:
    """Test that evaluator handles unavailable values for direct entity references gracefully."""
    # Mock Home Assistant instance
    mock_hass = MagicMock()
    mock_hass.states = MagicMock()

    # Mock data provider that returns unavailable for an entity
    def mock_data_provider(entity_id: str) -> DataProviderResult:
        if entity_id == "sensor.offline_sensor":
            return {"value": "unavailable", "exists": True}  # Entity exists but is unavailable
        return {"value": None, "exists": False}  # Entity doesn't exist

    # Create evaluator with data provider
    evaluator = Evaluator(mock_hass, data_provider_callback=mock_data_provider)
    evaluator.update_integration_entities({"sensor.offline_sensor"})

    # Test entity reference through variables (proper way)
    config = FormulaConfig(
        id="test_formula", formula="offline_sensor + 10", variables={"offline_sensor": "sensor.offline_sensor"}
    )

    # Should return success result with unavailable state (graceful state reflection)
    result = evaluator.evaluate_formula(config)

    assert result["success"] is True  # Non-fatal - reflects dependency state
    assert result["state"] == "unavailable"  # Reflects unavailable dependency
    assert "sensor.offline_sensor" in result.get("unavailable_dependencies", [])


def test_evaluator_works_with_valid_values() -> None:
    """Test that evaluator still works correctly with valid values."""
    # Mock Home Assistant instance
    mock_hass = MagicMock()
    mock_hass.states = MagicMock()

    # Mock data provider that returns valid values
    def mock_data_provider(entity_id: str) -> DataProviderResult:
        if entity_id == "sensor.valid_power":
            return {"value": 42.5, "exists": True}  # Valid value
        return {"value": None, "exists": False}  # Entity doesn't exist

    # Create evaluator with data provider
    evaluator = Evaluator(mock_hass, data_provider_callback=mock_data_provider)
    evaluator.update_integration_entities({"sensor.valid_power"})

    # Test simple variable reference with valid value
    config = FormulaConfig(
        id="test_formula",
        formula="power_reading",
        variables={"power_reading": "sensor.valid_power"},
    )

    result = evaluator.evaluate_formula(config)

    # Should succeed and return a numeric value (note: data provider integration has value conversion behavior)
    assert result["success"] is True
    assert isinstance(result["value"], (int, float))
    assert result["value"] > 0  # Should be a positive numeric value


if __name__ == "__main__":
    test_evaluator_handles_unknown_value_from_data_provider()
    test_evaluator_handles_unavailable_entity_reference()
    test_evaluator_works_with_valid_values()
