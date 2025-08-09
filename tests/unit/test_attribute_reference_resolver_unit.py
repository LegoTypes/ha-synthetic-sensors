from ha_synthetic_sensors.evaluator_phases.variable_resolution.attribute_reference_resolver import (
    AttributeReferenceResolver,
)


def test_attribute_reference_resolver_can_resolve_and_substitute_numeric() -> None:
    r = AttributeReferenceResolver()
    assert r.can_resolve("level1", "level1") is True
    # Context contains a numeric value for attribute 'level1'
    context = {"level1": 7}
    assert r.resolve("level1", "level1", context) == 7
    # In a formula, 'level1 + 1' should become '7 + 1'
    out = r.resolve_references_in_formula("level1 + 1", context)
    assert out in ("7 + 1", "7+1")
