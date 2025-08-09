from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.evaluator_phases.dependency_management.dependency_management_phase import (
    DependencyManagementPhase,
)


def test_extract_formula_dependencies_state_handling_main_vs_attribute() -> None:
    phase = DependencyManagementPhase()
    # Force extractor to return {'state'} so we can test substitution logic without full factory
    phase._manager_factory = type(
        "MF",
        (),
        {  # type: ignore[attr-defined]
            "manage_dependency": staticmethod(lambda action, **kwargs: {"state"} if action == "extract" else set())
        },
    )()
    # Backing mapping present for main formula
    phase.set_evaluator_dependencies(dependency_handler=None, sensor_to_backing_mapping={"s1": "sensor.backing"})

    main_cfg = FormulaConfig(id="main", formula="state + 1")
    scfg = SensorConfig(unique_id="s1")
    deps_main = phase._extract_formula_dependencies(main_cfg, context=None, sensor_config=scfg)
    # state replaced with backing entity
    assert "sensor.backing" in deps_main and "state" not in deps_main

    # Attribute formula: state removed from deps
    attr_cfg = FormulaConfig(id="s1_attr", formula="state * 2")
    deps_attr = phase._extract_formula_dependencies(attr_cfg, context=None, sensor_config=scfg)
    assert "state" not in deps_attr


def test_handle_dependency_issues_unavailable_and_unknown() -> None:
    phase = DependencyManagementPhase()
    # Unavailable takes precedence
    res_unavail = phase.handle_dependency_issues(set(), {"sensor.a"}, set(), "f")
    assert isinstance(res_unavail, dict) and res_unavail.get("state") == "unavailable"
    # Unknown only
    res_unknown = phase.handle_dependency_issues(set(), set(), {"sensor.b"}, "f")
    assert isinstance(res_unknown, dict) and res_unknown.get("state") == "unknown"
