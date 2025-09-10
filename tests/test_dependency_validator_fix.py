"""Test that the dependency validator correctly handles variables vs entities."""

import pytest
from ha_synthetic_sensors.evaluator_phases.dependency_management.dependency_validator import DependencyValidator


def test_dependency_validator_skips_variables():
    """Test that variables without dots are not treated as missing entities."""
    validator = DependencyValidator()

    # Test dependencies that include both entities and variables
    dependencies = {
        "sensor.power_meter",  # Real entity
        "binary_sensor.panel_status",  # Real entity
        "last_valid_state",  # Variable (no dot)
        "last_valid_changed",  # Variable (no dot)
        "panel_offline_minutes",  # Variable (no dot)
        "is_within_grace_period",  # Variable (no dot)
    }

    # Available entities (only the real entities)
    available_entities = {"sensor.power_meter", "binary_sensor.panel_status"}

    # Call the validator
    context = {}  # Empty context for testing
    missing, unavailable, unknown = validator.manage(
        "validate",
        context,
        dependencies=dependencies,
        available_entities=available_entities,
        registered_integration_entities=set(),
        hass=None,
    )

    print(f"Dependencies: {dependencies}")
    print(f"Available entities: {available_entities}")
    print(f"Missing: {missing}")
    print(f"Unavailable: {unavailable}")
    print(f"Unknown: {unknown}")

    # Variables should NOT be in missing dependencies
    assert "last_valid_state" not in missing
    assert "last_valid_changed" not in missing
    assert "panel_offline_minutes" not in missing
    assert "is_within_grace_period" not in missing

    # Real entities should also not be missing (they're available)
    assert "sensor.power_meter" not in missing
    assert "binary_sensor.panel_status" not in missing

    # Should have no missing dependencies
    assert len(missing) == 0


def test_dependency_validator_identifies_missing_entities():
    """Test that real missing entities are still caught."""
    validator = DependencyValidator()

    dependencies = {
        "sensor.missing_sensor",  # Missing entity
        "binary_sensor.missing_binary",  # Missing entity
        "some_variable",  # Variable (should be skipped)
    }

    available_entities = set()  # No entities available

    missing, unavailable, unknown = validator.manage(
        "validate",
        context={},
        dependencies=dependencies,
        available_entities=available_entities,
        registered_integration_entities=set(),
        hass=None,
    )

    print(f"Dependencies: {dependencies}")
    print(f"Missing: {missing}")

    # Real entities should be missing
    assert "sensor.missing_sensor" in missing
    assert "binary_sensor.missing_binary" in missing

    # Variable should not be missing
    assert "some_variable" not in missing


def test_power_sensor_scenario():
    """Test the exact scenario we're seeing with power sensors."""
    validator = DependencyValidator()

    # These are the dependencies being incorrectly flagged for power sensors
    dependencies = {"last_valid_changed", "last_valid_state", "panel_offline_minutes", "panel_status"}

    # No entities available (worst case)
    available_entities = set()

    missing, unavailable, unknown = validator.manage(
        "validate",
        context={},
        dependencies=dependencies,
        available_entities=available_entities,
        registered_integration_entities=set(),
        hass=None,
        formula_name="Spa Power",  # Power sensor
    )

    print(f"Power sensor dependencies: {dependencies}")
    print(f"Missing after fix: {missing}")

    # All of these should be recognized as variables, not missing entities
    assert len(missing) == 0, f"Power sensor should have no missing dependencies, got: {missing}"


if __name__ == "__main__":
    print("Testing dependency validator fix...")
    print("=" * 60)
    test_dependency_validator_skips_variables()
    print("=" * 60)
    test_dependency_validator_identifies_missing_entities()
    print("=" * 60)
    test_power_sensor_scenario()
    print("=" * 60)
    print("All tests passed!")
