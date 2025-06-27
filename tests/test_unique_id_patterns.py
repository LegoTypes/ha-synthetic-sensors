"""Test that unique_id pattern allows hyphens as required by Home Assistant."""

# bandit: skip

from typing import Any

from ha_synthetic_sensors.schema_validator import SchemaValidator


def test_unique_id_allows_hyphens() -> None:
    """Test that unique_id pattern allows hyphens, matching real Span device examples."""
    # Using actual Span device unique IDs from the registry
    config: dict[str, Any] = {"version": "1.0", "sensors": {"span_nj-4919-005k6_select_795e8eddb4f448af9625130332a41df8": {"name": "Test Sensor with Hyphens", "formula": "5 + 3", "unit_of_measurement": "test"}}}

    validator = SchemaValidator()
    result = validator.validate_config(config)

    assert result["valid"] is True, f"Validation failed with errors: {result['errors']}"
    assert len(result["errors"]) == 0


def test_unique_id_patterns() -> None:
    """Test various unique_id patterns including real Span device examples."""
    # Mix of real Span device patterns and HA test patterns
    valid_patterns = [
        "simple",
        "with_underscores",
        "with-hyphens",
        "mixed-pattern_test",
        "a",  # single character
        "test123",
        "test-123_sensor",
        # Real Span device unique IDs from registry
        "span_nj-2316-008k0_select_795e8eddb4f448af9625130332a41df8",
        "span_nj-2316-007k6_number_fe123456789abcdef0123456789abcdef",
        "span_nj-2316-045k9_switch_abc123def456789fedcba0987654321abc",
        "device-model-v1_sensor_001",
        "integration-name_device-id_entity-type",
        # Patterns from HA core tests
        "11:22:33:44:55:AA-binary_sensor-my",
        "52.52-49-00-Air_temperature-00",
        "x-a",
        "x-b",
        "1_onpeak",
        "lot123v1-is_on",
        "TOTALLY_UNIQUE",  # uppercase
        "Test_123",
        "device.model-v1_sensor",
    ]

    for pattern in valid_patterns:
        config: dict[str, Any] = {"version": "1.0", "sensors": {pattern: {"name": f"Test sensor {pattern}", "formula": "5 + 3", "unit_of_measurement": "test"}}}

        validator = SchemaValidator()
        result = validator.validate_config(config)

        assert result["valid"] is True, f"Pattern '{pattern}' should be valid but failed validation"
        assert len(result["errors"]) == 0, f"Pattern '{pattern}' should not have errors: {result['errors']}"


if __name__ == "__main__":
    test_unique_id_allows_hyphens()
    test_unique_id_patterns()
