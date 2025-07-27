"""Tests for utils module."""

import pytest

from ha_synthetic_sensors.utils import denormalize_entity_id


class TestUtils:
    """Test utility functions."""

    def test_denormalize_entity_id_sensor(self):
        """Test denormalizing sensor entity IDs."""
        # Test sensor normalization
        assert denormalize_entity_id("sensor_power_meter") == "sensor.power_meter"
        assert denormalize_entity_id("sensor_temperature_reading") == "sensor.temperature_reading"
        assert denormalize_entity_id("sensor_humidity_sensor") == "sensor.humidity_sensor"

    def test_denormalize_entity_id_binary_sensor(self):
        """Test denormalizing binary sensor entity IDs."""
        # Test binary sensor normalization (function replaces first underscore only)
        assert denormalize_entity_id("binary_sensor_motion_detector") == "binary.sensor_motion_detector"
        assert denormalize_entity_id("binary_sensor_door_sensor") == "binary.sensor_door_sensor"
        assert denormalize_entity_id("binary_sensor_presence_sensor") == "binary.sensor_presence_sensor"

    def test_denormalize_entity_id_switch(self):
        """Test denormalizing switch entity IDs."""
        # Test switch normalization
        assert denormalize_entity_id("switch_living_room_light") == "switch.living_room_light"
        assert denormalize_entity_id("switch_kitchen_light") == "switch.kitchen_light"
        assert denormalize_entity_id("switch_outdoor_light") == "switch.outdoor_light"

    def test_denormalize_entity_id_other_domains(self):
        """Test denormalizing other entity domains."""
        # Test other domains (only specific patterns are supported)
        assert denormalize_entity_id("light_bedroom_lamp") == "light.bedroom_lamp"
        assert denormalize_entity_id("climate_thermostat") == "climate.thermostat"
        # cover_ is not in the supported patterns, so it returns None
        assert denormalize_entity_id("cover_garage_door") is None

    def test_denormalize_entity_id_with_hyphens(self):
        """Test denormalizing entity IDs with hyphens."""
        # Test with hyphens (should be preserved)
        assert denormalize_entity_id("sensor_power-meter") == "sensor.power-meter"
        assert denormalize_entity_id("binary_sensor_motion-detector") == "binary.sensor_motion-detector"
        assert denormalize_entity_id("switch_living-room-light") == "switch.living-room-light"

    def test_denormalize_entity_id_already_normalized(self):
        """Test denormalizing already normalized entity IDs."""
        # Test already normalized IDs (function doesn't handle these, returns None)
        assert denormalize_entity_id("sensor.power_meter") is None
        assert denormalize_entity_id("binary_sensor.motion_detector") is None
        assert denormalize_entity_id("switch.living_room_light") is None

    def test_denormalize_entity_id_edge_cases(self):
        """Test denormalizing entity IDs with edge cases."""
        # Test edge cases (most return None as they don't match patterns)
        assert denormalize_entity_id("sensor") is None  # No underscore
        assert denormalize_entity_id("sensor_") == "sensor."  # Underscore at end (matches sensor_ pattern)
        assert denormalize_entity_id("_sensor") is None  # Underscore at start (no pattern match)
        assert denormalize_entity_id("") is None  # Empty string
