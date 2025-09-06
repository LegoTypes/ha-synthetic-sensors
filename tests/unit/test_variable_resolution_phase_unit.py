from types import SimpleNamespace

import pytest

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase import (
    VariableResolutionPhase,
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


class _FakeResolverFactory:
    def __init__(self, mapping, provider, hass):
        self.sensor_to_backing_mapping = mapping or {}
        self.data_provider_callback = provider
        self._hass = hass

    def get_all_resolvers(self):
        return []

    def set_sensor_registry_phase(self, _):
        pass

    def set_dependency_handler(self, _):
        pass

    def update_sensor_to_backing_mapping(self, mapping, provider):
        self.sensor_to_backing_mapping = mapping
        self.data_provider_callback = provider

    def resolve_variable(self, name, value, context):  # pragma: no cover - simple passthrough in this unit surface
        # For entity references, return a ReferenceValue so phase extracts numeric value
        if isinstance(value, str) and value.startswith("sensor."):
            return ReferenceValue(reference=value, value=42)
        if name == "state":
            return ReferenceValue(reference="state", value=100)
        # simple passthrough for literals
        return value


def _make_phase(hass=None):
    # Monkey patch factory inside phase instance for deterministic behavior in unit test
    phase = VariableResolutionPhase(sensor_to_backing_mapping=None, data_provider_callback=None, hass=hass)
    phase._resolver_factory = _FakeResolverFactory({}, None, hass)  # type: ignore[attr-defined]

    # Provide minimal dependency handler with hass and data provider that returns numbers
    def provider(entity_id: str):
        # Return a valid data provider result: numeric value with exists True
        return {"exists": True, "value": 21}

    # Set private attribute to avoid factory recreation in set_dependency_handler
    phase._dependency_handler = SimpleNamespace(  # type: ignore[attr-defined]
        hass=hass, data_provider_callback=provider, should_use_data_provider=lambda _e: True
    )
    return phase


def test_resolve_all_references_with_ha_detection_entity_and_state_paths(mock_hass) -> None:
    sensor_cfg = SensorConfig(unique_id="s1", formulas=[FormulaConfig(id="main", formula="sensor.x + state")])
    formula_cfg = sensor_cfg.formulas[0]
    eval_ctx = _create_hierarchical_context({"x": 1})

    phase = _make_phase(hass=mock_hass)
    # The fake resolver returns ReferenceValue objects for entity ids and state, so final expression becomes numeric
    result = phase.resolve_all_references_with_ha_detection(formula_cfg.formula, sensor_cfg, eval_ctx, formula_cfg)
    assert result.resolved_formula  # string formula after resolution
    assert "sensor.x" not in result.resolved_formula
    # Context should contain ReferenceValue objects - check for the entity ID key and the alias key
    assert isinstance(eval_ctx.get("sensor_x"), ReferenceValue)  # Alias key (sensor_x)
    assert isinstance(eval_ctx.get("state"), ReferenceValue)  # State key


def test_resolve_all_references_in_formula_returns_string(mock_hass) -> None:
    sensor_cfg = SensorConfig(unique_id="s1", formulas=[FormulaConfig(id="main", formula="sensor.a + 1")])
    formula_cfg = sensor_cfg.formulas[0]
    eval_ctx = _create_hierarchical_context()

    phase = _make_phase(hass=mock_hass)
    resolved = phase.resolve_all_references_in_formula(formula_cfg.formula, sensor_cfg, eval_ctx, formula_cfg)
    assert isinstance(resolved, str)
