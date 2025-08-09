from ha_synthetic_sensors.config_models import ComputedVariable
from ha_synthetic_sensors.utils_config import validate_computed_variable_references


def test_validate_computed_variable_references_self_reference_detected() -> None:
    errors = validate_computed_variable_references(
        {
            "a": ComputedVariable("a + 1"),
        }
    )
    assert any("references itself" in e for e in errors)


def test_validate_computed_variable_references_entity_id_allowed() -> None:
    # Formula references an entity_id; should not be flagged undefined
    errors = validate_computed_variable_references(
        {
            "x": ComputedVariable("sensor.kitchen + 2"),
        }
    )
    # No undefined variable message expected
    assert not any("undefined variables" in e for e in errors)
