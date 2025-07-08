"""Test empty collection behavior - aggregation functions return 0 for robustness."""

from unittest.mock import MagicMock

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator


def test_empty_collection_sum_returns_zero():
    """Test that sum() with no matching entities returns 0."""
    mock_hass = MagicMock()

    # Mock entity_ids to return empty list (no entities match the pattern)
    mock_hass.states.entity_ids.return_value = []

    evaluator = Evaluator(mock_hass)

    # Formula with collection function that matches no entities
    config = FormulaConfig(id="test_empty_sum", formula='sum("device_class:nonexistent_device_class")')

    # Should return 0, not raise an error
    result = evaluator.evaluate_formula(config)

    assert result["success"] is True
    assert result["value"] == 0


def test_empty_collection_avg_returns_zero():
    """Test that avg() with no matching entities returns 0."""
    mock_hass = MagicMock()

    # Mock entity_ids to return empty list
    mock_hass.states.entity_ids.return_value = []

    evaluator = Evaluator(mock_hass)

    config = FormulaConfig(id="test_empty_avg", formula='avg("regex:sensor\\.nonexistent_.*")')

    # Should return 0, not raise an error
    result = evaluator.evaluate_formula(config)

    assert result["success"] is True
    assert result["value"] == 0


def test_empty_collection_max_returns_zero():
    """Test that max() with no matching entities returns 0."""
    mock_hass = MagicMock()

    # Mock entity_ids to return empty list
    mock_hass.states.entity_ids.return_value = []

    evaluator = Evaluator(mock_hass)

    config = FormulaConfig(
        id="test_empty_max",
        formula='max("state:>9999")',  # Condition that no entity will match
    )

    # Should return 0, not raise an error
    result = evaluator.evaluate_formula(config)

    assert result["success"] is True
    assert result["value"] == 0


def test_empty_collection_min_returns_zero():
    """Test that min() with no matching entities returns 0."""
    mock_hass = MagicMock()

    # Mock entity_ids to return empty list
    mock_hass.states.entity_ids.return_value = []

    evaluator = Evaluator(mock_hass)

    config = FormulaConfig(
        id="test_empty_min",
        formula='min("state:<-9999")',  # Condition that no entity will match
    )

    # Should return 0, not raise an error
    result = evaluator.evaluate_formula(config)

    assert result["success"] is True
    assert result["value"] == 0


def test_collection_with_zero_sum_returns_zero():
    """Test that sum() with entities that legitimately sum to 0 returns 0."""
    mock_hass = MagicMock()

    # Mock entities that exist and have numeric values that sum to 0
    mock_hass.states.entity_ids.return_value = ["sensor.test1", "sensor.test2"]

    # Mock states for entities
    mock_state1 = MagicMock()
    mock_state1.state = "5"
    mock_state1.attributes = {"device_class": "power"}

    mock_state2 = MagicMock()
    mock_state2.state = "-5"
    mock_state2.attributes = {"device_class": "power"}

    def mock_get_state(entity_id):
        if entity_id == "sensor.test1":
            return mock_state1
        elif entity_id == "sensor.test2":
            return mock_state2
        return None

    mock_hass.states.get.side_effect = mock_get_state

    evaluator = Evaluator(mock_hass)

    config = FormulaConfig(id="test_zero_sum", formula='sum("device_class:power")')

    # Should return 0 (legitimate result)
    result = evaluator.evaluate_formula(config)

    assert result["success"] is True
    assert result["value"] == 0.0


def test_collection_with_non_numeric_entities_returns_zero():
    """Test that collection with entities that have non-numeric values returns 0."""
    mock_hass = MagicMock()

    # Mock entities that exist but have non-numeric values
    mock_hass.states.entity_ids.return_value = ["binary_sensor.test1", "binary_sensor.test2"]

    # Mock states for entities with non-numeric values
    mock_state1 = MagicMock()
    mock_state1.state = "on"  # Non-numeric
    mock_state1.attributes = {"device_class": "door"}

    mock_state2 = MagicMock()
    mock_state2.state = "off"  # Non-numeric
    mock_state2.attributes = {"device_class": "door"}

    def mock_get_state(entity_id):
        if entity_id == "binary_sensor.test1":
            return mock_state1
        elif entity_id == "binary_sensor.test2":
            return mock_state2
        return None

    mock_hass.states.get.side_effect = mock_get_state

    evaluator = Evaluator(mock_hass)

    config = FormulaConfig(id="test_non_numeric", formula='sum("device_class:door")')

    # Should return 0 because no numeric values found
    result = evaluator.evaluate_formula(config)

    assert result["success"] is True
    assert result["value"] == 0


def test_count_function_with_empty_collection():
    """Test that count() function behavior with empty collections."""
    mock_hass = MagicMock()

    # Mock entity_ids to return empty list
    mock_hass.states.entity_ids.return_value = []

    evaluator = Evaluator(mock_hass)

    config = FormulaConfig(id="test_empty_count", formula='count("device_class:nonexistent")')

    # For count(), empty collection should return 0
    result = evaluator.evaluate_formula(config)

    assert result["success"] is True
    assert result["value"] == 0


def test_collection_in_complex_formula():
    """Test that empty collections work properly in complex formulas."""
    mock_hass = MagicMock()

    # Mock entity_ids to return empty list
    mock_hass.states.entity_ids.return_value = []

    evaluator = Evaluator(mock_hass)

    config = FormulaConfig(
        id="test_complex_formula",
        formula='sum("device_class:nonexistent") + 10',  # Formula with empty collection
    )

    # Should work and return 10 (0 + 10)
    result = evaluator.evaluate_formula(config)

    assert result["success"] is True
    assert result["value"] == 10


def test_empty_collections_workaround_example():
    """Test workaround example for detecting empty collections.

    This demonstrates how users can detect empty collections if needed
    by checking if count() returns 0.
    """
    mock_hass = MagicMock()

    # Mock entity_ids to return empty list
    mock_hass.states.entity_ids.return_value = []

    evaluator = Evaluator(mock_hass)

    # Example of conditional logic to handle empty collections
    config = FormulaConfig(id="test_workaround", formula='sum("device_class:power") if count("device_class:power") > 0 else -1')

    # Should return -1 because count returns 0 (no entities)
    result = evaluator.evaluate_formula(config)

    assert result["success"] is True
    assert result["value"] == -1
