from types import SimpleNamespace

from ha_synthetic_sensors.config_models import FormulaConfig
from ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_processors import VariableProcessors
from ha_synthetic_sensors.type_definitions import ReferenceValue


def _dep_handler_with_provider(values: dict[tuple[str, str], float]):
    def provider(entity_id: str):
        # Return exists/value/attributes for attribute resolution
        attrs = {}
        # Extract all attributes for this entity
        for (ent, attr), val in values.items():
            if ent == entity_id:
                attrs[attr] = val
        return {"exists": True, "value": 0, "attributes": attrs}

    return SimpleNamespace(should_use_data_provider=lambda _e: True, data_provider_callback=provider)


def test_resolve_attribute_chains_uses_formula_config_entity_ids() -> None:
    # device.current where device -> sensor.current_meter in config
    cfg = FormulaConfig(id="main", formula="device.current", variables={"device": "sensor.current_meter"})
    dep = _dep_handler_with_provider({("sensor.current_meter", "current"): 7.0})
    out = VariableProcessors.resolve_attribute_chains("device.current", {}, cfg, dep)
    assert out == "7.0"


def test_resolve_variable_attribute_references_with_referencevalue_and_string() -> None:
    # Context contains a ReferenceValue for dev -> sensor.voltage_meter
    ctx = {
        "dev": ReferenceValue(reference="sensor.voltage_meter", value=None),
        "raw": "sensor.battery_device",
    }

    # AttributeReferenceResolver.resolve(..) in VariableProcessors is lenient; ensure passthrough on failure
    # We'll construct formula with two refs: one for ReferenceValue, one for raw string
    formula = "dev.voltage + raw.battery_level"
    out = VariableProcessors.resolve_variable_attribute_references(formula, ctx)
    # The default AttributeReferenceResolver returns None substitutions when resolution is not possible
    # So the formula becomes 'None + None'
    assert out in ("None + None", "None+None")


def test_resolve_simple_variables_with_usage_tracking_converts_reference_values() -> None:
    ctx = {
        "x": ReferenceValue(reference="sensor.numeric", value=12.5),
        "name": ReferenceValue(reference="meta", value="kitchen"),
    }
    formula = "x + 2 == 14.5 and name == kitchen"
    out, used = VariableProcessors.resolve_simple_variables_with_usage_tracking(formula, ctx)
    assert "12.5" in out and "kitchen" in out
    assert used == {"x", "name"}
