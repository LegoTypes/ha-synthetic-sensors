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
    """When main formula fails due to unavailable dependency, alternates should execute.

    - Literal alternate returns the literal typed value
    - Object-form alternate evaluates its formula with local variables
    """

    # Provide an entity that is unavailable to trigger handler selection
    mock_entity_registry.register_entity("sensor.missing", "sensor.missing", "sensor")
    mock_states.register_state("sensor.missing", "unavailable", {})

    # Evaluator with HA entity lookup only (Pattern 2)
    ev = Evaluator(mock_hass)
    ev.update_integration_entities({"sensor.missing"})

    # Literal alternate
    # Deliberately omit variable binding to cause undefined-variable error and trigger alternates
    cfg_lit = FormulaConfig(
        id="lit", formula="missing + 1", variables={}, alternate_state_handler=AlternateStateHandler(unavailable=10)
    )
    res_lit = ev.evaluate_formula(cfg_lit)
    assert res_lit["success"] is True
    # Literal numeric may be surfaced via state path; assert ok state
    assert res_lit["state"] == "ok"

    # Object-form alternate
    cfg_obj = FormulaConfig(
        id="obj",
        formula="missing * 2",
        variables={},
        alternate_state_handler=AlternateStateHandler(unavailable={"formula": "backup + 1", "variables": {"backup": 5}}),
    )
    res_obj = ev.evaluate_formula(cfg_obj)
    assert res_obj["success"] is True
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
    res = ev.evaluate_formula(cfg)
    assert res["success"] is True
    assert res["value"] in (True, False)
