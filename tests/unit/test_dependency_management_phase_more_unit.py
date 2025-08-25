from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.evaluator_phases.dependency_management.dependency_management_phase import (
    DependencyManagementPhase,
)


def test_handle_dependency_issues_priority_and_none() -> None:
    phase = DependencyManagementPhase()
    # Missing -> raises
    try:
        _ = phase.handle_dependency_issues({"a"}, set(), set(), "f")
        assert False, "Expected missing dependency error"
    except Exception as e:
        assert "Missing dependencies" in str(e)

        # Unavailable takes priority over unknown, but both return STATE_UNKNOWN for consistency
        res = phase.handle_dependency_issues(set(), {"x"}, {"y"}, "f")
        assert isinstance(res, dict) and res.get("state") == "unknown"

    # Only unknown -> unknown state
    res = phase.handle_dependency_issues(set(), set(), {"y"}, "f")
    assert isinstance(res, dict) and res.get("state") == "unknown"


def test_extract_formula_dependencies_state_token_rules() -> None:
    phase = DependencyManagementPhase()
    # Force extractor to return {'state'}
    phase._manager_factory = type(
        "MF",
        (),
        {  # type: ignore[attr-defined]
            "manage_dependency": staticmethod(lambda action, **kwargs: {"state"} if action == "extract" else set())
        },
    )()

    # Main formula with backing entity -> replace state with entity id
    phase.set_evaluator_dependencies(dependency_handler=None, sensor_to_backing_mapping={"s1": "sensor.backing"})
    deps = phase._extract_formula_dependencies(  # noqa: SLF001
        FormulaConfig(id="main", formula="state+1"), context=None, sensor_config=SensorConfig(unique_id="s1")
    )
    assert "sensor.backing" in deps and "state" not in deps

    # Attribute formula -> discard state
    deps_attr = phase._extract_formula_dependencies(  # noqa: SLF001
        FormulaConfig(id="s1_attr", formula="state+1"), context=None, sensor_config=SensorConfig(unique_id="s1")
    )
    assert "state" not in deps_attr
