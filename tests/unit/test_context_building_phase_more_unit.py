from types import SimpleNamespace

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.evaluator_phases.context_building.context_building_phase import (
    ContextBuildingPhase,
)


def test_is_attribute_reference_variants(mock_hass, mock_entity_registry, mock_states) -> None:
    phase = ContextBuildingPhase()
    # Set the hass dependency so _is_attribute_reference can check domains
    phase.set_evaluator_dependencies(
        hass=mock_hass,
        data_provider_callback=None,
        dependency_handler=None,
        sensor_to_backing_mapping={},
    )
    assert phase._is_attribute_reference("state.voltage") is True  # noqa: SLF001
    assert phase._is_attribute_reference("attribute.name") is True  # noqa: SLF001
    assert phase._is_attribute_reference("sensor.kitchen") is False  # noqa: SLF001
    assert phase._is_attribute_reference(123) is False  # type: ignore[arg-type]  # noqa: SLF001


def test_resolve_state_attribute_reference_uses_provider_and_mapping() -> None:
    phase = ContextBuildingPhase()

    # set evaluator deps with provider and mapping
    def provider(entity_id: str):
        assert entity_id == "sensor.backing"
        return {"exists": True, "value": 0, "attributes": {"voltage": 230}}

    phase.set_evaluator_dependencies(
        hass=SimpleNamespace(states=SimpleNamespace(get=lambda _eid: None)),
        data_provider_callback=provider,
        dependency_handler=None,
        sensor_to_backing_mapping={"s1": "sensor.backing"},
    )

    sensor_cfg = SensorConfig(unique_id="s1")
    # private helper: resolve state.voltage
    value = phase._resolve_state_attribute_reference("state.voltage", sensor_cfg)  # noqa: SLF001
    assert value == 230


def test_resolve_entity_dependencies_missing_raises() -> None:
    # Provide a resolver factory that fails resolution to force MissingDependencyError path
    class FailingFactory:
        def resolve_variable(self, variable_name, variable_value, context):  # noqa: D401, ANN001
            raise RuntimeError("fail")

    phase = ContextBuildingPhase()
    phase.set_evaluator_dependencies(
        hass=SimpleNamespace(states=SimpleNamespace(get=lambda _eid: None)),
        data_provider_callback=None,
        dependency_handler=None,
        sensor_to_backing_mapping={},
    )

    # Monkey patch the factory creator
    phase._create_resolver_factory = lambda _ctx: FailingFactory()  # type: ignore[method-assign, assignment]  # noqa: SLF001

    # Call through build to hit exception branch in _resolve_entity_dependencies
    deps: set[str] = {"sensor.missing"}
    try:
        phase.build_evaluation_context(deps, context=None, config=FormulaConfig(id="main", formula="1+1"))
        assert False, "Expected MissingDependencyError"
    except Exception as e:
        assert "Failed to resolve entity dependency" in str(e)
