from ha_synthetic_sensors.evaluator_phases.variable_resolution.attribute_reference_resolver import (
    AttributeReferenceResolver,
)
from ha_synthetic_sensors.type_definitions import ReferenceValue


def test_attribute_reference_resolver_can_resolve_and_substitute_numeric() -> None:
    r = AttributeReferenceResolver()
    assert r.can_resolve("level1", "level1") is True
    # Context contains a ReferenceValue for attribute 'level1' (ReferenceValue architecture)
    context = {"level1": ReferenceValue("level1", 7)}
    # Resolvers now return ReferenceValue objects (new architecture)
    result = r.resolve("level1", "level1", context)
    assert isinstance(result, ReferenceValue)
    assert result.value == 7
    assert result.reference == "level1"
    # In a formula, 'level1 + 1' should become '7 + 1'
    out = r.resolve_references_in_formula("level1 + 1", context)
    assert out in ("7 + 1", "7+1")
