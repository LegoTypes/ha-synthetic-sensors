"""Unit tests for alternate handlers (literal/object) and scoped guard behavior.

These tests exercise the evaluator pipeline directly without full HA entity setup.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ha_synthetic_sensors.config_manager import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.config_models import AlternateStateHandler
from ha_synthetic_sensors.type_definitions import DataProviderResult


def _dp_for(values: dict[str, tuple[object, bool]]):
    def provider(entity_id: str) -> DataProviderResult:
        val, exists = values.get(entity_id, (None, False))
        return {"value": val, "exists": exists}

    return provider


def test_sensor_level_alternate_literal_and_object(mock_hass, mock_entity_registry, mock_states) -> None:
    """When main formula fails due to unavailable entity state, alternates should execute.

    - Literal alternate returns the literal typed value
    - Object-form alternate evaluates its formula with local variables
    """

    # Provide an entity that is unavailable to trigger handler selection
    mock_entity_registry.register_entity("sensor.unavailable_source", "sensor.unavailable_source", "sensor")
    mock_states.register_state("sensor.unavailable_source", "unavailable", {})

    # Evaluator with HA entity lookup only (Pattern 2)
    ev = Evaluator(mock_hass)
    ev.update_integration_entities({"sensor.unavailable_source"})

    # Literal alternate - properly bind variable to unavailable entity
    cfg_lit = FormulaConfig(
        id="lit",
        formula="unavailable_var + 1",
        variables={"unavailable_var": "sensor.unavailable_source"},
        alternate_state_handler=AlternateStateHandler(unavailable=10),
    )

    # Create proper hierarchical context according to architecture
    from ha_synthetic_sensors.evaluation_context import HierarchicalEvaluationContext
    from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalContextDict
    from ha_synthetic_sensors.type_definitions import ReferenceValue
    from ha_synthetic_sensors.config_models import SensorConfig

    # Create a proper sensor configuration to ensure variables are resolved correctly
    sensor_config = SensorConfig(
        unique_id="test_sensor",
        name="Test Sensor",
        entity_id="sensor.test_sensor",
        device_identifier="test_device",
        formulas=[cfg_lit],
    )

    hierarchical_context = HierarchicalEvaluationContext("alternate_literal_test")
    context_lit = HierarchicalContextDict(hierarchical_context)

    # Use evaluate_formula_with_sensor_config to properly handle sensor configuration
    res_lit = ev.evaluate_formula_with_sensor_config(cfg_lit, context_lit, sensor_config)
    assert res_lit["success"] is True
    # Should use alternate value of 10
    assert res_lit["value"] == 10
    assert res_lit["state"] == "ok"

    # Object-form alternate - properly bind variable to unavailable entity
    cfg_obj = FormulaConfig(
        id="obj",
        formula="unavailable_var * 2",
        variables={"unavailable_var": "sensor.unavailable_source"},
        alternate_state_handler=AlternateStateHandler(unavailable={"formula": "backup + 1", "variables": {"backup": 5}}),
    )

    # Create a proper sensor configuration for object alternate test
    sensor_config_obj = SensorConfig(
        unique_id="test_sensor_obj",
        name="Test Sensor Object",
        entity_id="sensor.test_sensor_obj",
        device_identifier="test_device",
        formulas=[cfg_obj],
    )

    # Create proper hierarchical context for object alternate test
    hierarchical_context_obj = HierarchicalEvaluationContext("alternate_object_test")
    hierarchical_context_obj.set("backup", ReferenceValue("backup", 5))
    context_obj = HierarchicalContextDict(hierarchical_context_obj)

    # Use evaluate_formula_with_sensor_config to properly handle sensor configuration
    res_obj = ev.evaluate_formula_with_sensor_config(cfg_obj, context_obj, sensor_config_obj)
    assert res_obj["success"] is True
    # Should use alternate formula: backup + 1 = 5 + 1 = 6
    assert res_obj["value"] == 6
    assert res_obj["state"] == "ok"


def test_guard_scoping_with_metadata_only_cv(mock_hass, mock_entity_registry, mock_states) -> None:
    """Unrelated unknown should not short-circuit a metadata-only expression.

    Formula: minutes_between(metadata(state, 'last_changed'), now()) < 30
    Context includes: state (valid entity), and an unused variable whose state is unknown.
    """

    # Valid entity for state
    mock_entity_registry.register_entity("sensor.ok", "sensor.ok", "sensor")
    mock_states.register_state("sensor.ok", "100.0", {})
    # Add last_changed metadata expected by metadata() handler
    mock_state = type(
        "MockState",
        (),
        {
            "state": "100.0",
            "attributes": {},
            "entity_id": "sensor.ok",
            "object_id": "ok",
            "domain": "sensor",
            "last_changed": datetime.now(timezone.utc) - timedelta(minutes=1),
            "last_updated": datetime.now(timezone.utc),
        },
    )()
    mock_states["sensor.ok"] = mock_state

    # Unused variable with unknown state
    mock_entity_registry.register_entity("sensor.unused", "sensor.unused", "sensor")
    mock_states.register_state("sensor.unused", "unknown", {})

    ev = Evaluator(mock_hass)
    ev.update_integration_entities({"sensor.ok", "sensor.unused"})

    cfg = FormulaConfig(
        id="guard",
        formula="minutes_between(metadata(state, 'last_changed'), now()) < 30",
        variables={"state": "sensor.ok", "unused": "sensor.unused"},
    )

    # Create proper hierarchical context according to architecture
    from ha_synthetic_sensors.evaluation_context import HierarchicalEvaluationContext
    from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalContextDict
    from ha_synthetic_sensors.config_models import SensorConfig
    from ha_synthetic_sensors.type_definitions import ReferenceValue

    hierarchical_context = HierarchicalEvaluationContext("guard_test")
    # Set up the variables in the context as they would be resolved
    hierarchical_context.set("state", ReferenceValue("sensor.ok", "100.0"))
    hierarchical_context.set("unused", ReferenceValue("sensor.unused", "unknown"))
    context = HierarchicalContextDict(hierarchical_context)

    # Create proper sensor configuration
    sensor_config = SensorConfig(
        unique_id="guard_sensor",
        name="Guard Sensor",
        entity_id="sensor.guard_sensor",
        device_identifier="test_device",
        formulas=[cfg],
    )

    res = ev.evaluate_formula_with_sensor_config(cfg, context, sensor_config)
    assert res["success"] is True
    assert res["value"] in (True, False)
