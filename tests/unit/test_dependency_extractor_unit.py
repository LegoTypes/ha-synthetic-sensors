from ha_synthetic_sensors.config_models import ComputedVariable, FormulaConfig
from ha_synthetic_sensors.evaluator_phases.dependency_management.dependency_extractor import (
    DependencyExtractor,
)


def test_dependency_extractor_collects_entities_variables_and_state() -> None:
    extractor = DependencyExtractor()
    cfg = FormulaConfig(
        id="main",
        formula="sensor.a + state + binary_sensor.b",
        variables={"x": "sensor.c", "y": 5, "z": ComputedVariable("sensor.d * 2")},
        attributes={
            "attr1": {"formula": "sensor.e + 1", "variables": {"q": "sensor.f"}},
        },
    )
    deps = extractor.manage("extract", {"config": cfg})
    # Entities from formula
    assert "sensor.a" in deps and "binary_sensor.b" in deps
    # State token recognized
    assert "state" in deps
    # Entities from variables and computed variable formula
    assert "sensor.c" in deps and "sensor.d" in deps
    # Entities from attributes (formula and variables)
    assert "sensor.e" in deps and "sensor.f" in deps
