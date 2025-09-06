from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ha_synthetic_sensors.evaluator_handlers.metadata_handler import MetadataHandler
from ha_synthetic_sensors.type_definitions import ReferenceValue


def test_process_metadata_functions_resolves_with_referencevalue_hass() -> None:
    hass = Mock()
    # Create proper mock state with attributes dict
    mock_state = Mock()
    mock_state.attributes = {}
    mock_state.entity_id = "sensor.kitchen"
    hass.states.get.return_value = mock_state

    # EvaluationContext should contain ReferenceValue objects
    context = {"_hass": ReferenceValue(reference="_hass", value=hass)}
    formula = "metadata(sensor.kitchen, 'entity_id')"
    out = MetadataHandler.process_metadata_functions(formula, context)
    # AST caching approach: metadata functions now return placeholder function calls
    assert out.startswith("metadata_result(")


def test_metadata_handler_evaluate_with_variable_and_key(mock_hass, mock_entity_registry, mock_states) -> None:
    # Create a proper state object instead of Mock to avoid isoformat confusion
    class MockState:
        def __init__(self, entity_id: str, attributes: dict):
            self.entity_id = entity_id
            self.attributes = attributes

    # Set up mock state for the entity that will be referenced
    mock_state = MockState("sensor.kitchen", {"friendly_name": "Kitchen Power"})
    mock_hass.states.get.return_value = mock_state

    # Set up mock entity registry entry using the DynamicMockEntityRegistry
    mock_registry_entry = Mock()
    mock_registry_entry.entity_id = "sensor.kitchen"
    mock_registry_entry.friendly_name = "Kitchen Power"
    # Register the entity in the mock registry
    mock_entity_registry.register_entity("sensor.kitchen", "kitchen", "sensor", friendly_name="Kitchen Power")

    # Also register the state in mock_states
    mock_states["sensor.kitchen"] = mock_state

    handler = MetadataHandler(hass=mock_hass)
    # EvaluationContext should contain ReferenceValue objects with proper entity ID reference
    ctx = {"dev": ReferenceValue(reference="sensor.kitchen", value=0)}
    processed_formula, metadata_results = handler.evaluate("metadata(dev, 'friendly_name')", ctx)
    # AST caching approach: returns placeholder formula and metadata results separately
    assert processed_formula.startswith("metadata_result(")
    assert len(metadata_results) == 1
    # The metadata result should contain the actual friendly name value
    metadata_key = list(metadata_results.keys())[0]
    assert metadata_results[metadata_key] == "Kitchen Power"


def test_process_metadata_functions_missing_hass_is_fatal() -> None:
    with pytest.raises(Exception):
        MetadataHandler.process_metadata_functions("metadata(sensor.kitchen, 'entity_id')", context={})
