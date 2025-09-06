from types import SimpleNamespace

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.evaluator_phases.context_building.context_building_phase import (
    ContextBuildingPhase,
)
from ha_synthetic_sensors.type_definitions import ReferenceValue
from ha_synthetic_sensors.evaluation_context import HierarchicalEvaluationContext
from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalContextDict


def _create_hierarchical_context(initial_vars: dict[str, object] = None) -> HierarchicalContextDict:
    """Create a proper HierarchicalContextDict for testing."""
    hierarchical_context = HierarchicalEvaluationContext("test")
    context_dict = HierarchicalContextDict(hierarchical_context)

    if initial_vars:
        for key, value in initial_vars.items():
            if isinstance(value, ReferenceValue):
                hierarchical_context.set(key, value)
            else:
                # Wrap raw values in ReferenceValue objects
                hierarchical_context.set(key, ReferenceValue(reference=key, value=value))

    return context_dict


def test_build_evaluation_context_includes_hass_current_sensor_and_globals() -> None:
    phase = ContextBuildingPhase()
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda _eid: None))
    phase.set_evaluator_dependencies(
        hass=hass, data_provider_callback=None, dependency_handler=None, sensor_to_backing_mapping={}
    )
    phase.set_global_settings({"variables": {"g": 5}})

    # Existing context with a ReferenceValue should be preserved
    existing_ctx = _create_hierarchical_context({"x": ReferenceValue(reference="x", value=1)})
    # Numeric variable should be added directly
    cfg = FormulaConfig(id="main", formula="1+1", variables={"y": 10})
    scfg = SensorConfig(unique_id="s1", entity_id="sensor.s1", formulas=[cfg])

    out = phase.build_evaluation_context(dependencies=set(), context=existing_ctx, config=cfg, sensor_config=scfg)

    assert "_hass" in out
    assert "current_sensor_entity_id" in out and isinstance(out["current_sensor_entity_id"], ReferenceValue)
    assert "g" in out and isinstance(out["g"], ReferenceValue)
    assert "y" in out  # numeric from config variables
