from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase import (
    VariableResolutionPhase,
)


def test_cross_sensor_self_reference_in_attribute_replaced_with_state() -> None:
    phase = VariableResolutionPhase()
    sensor_cfg = SensorConfig(unique_id="s1")
    attr_cfg = FormulaConfig(id="s1_attr", formula="s1 + 1")
    out = phase._resolve_cross_sensor_references("s1 + 1", {}, sensor_cfg, attr_cfg)
    assert out.startswith("state") or " state " in out
