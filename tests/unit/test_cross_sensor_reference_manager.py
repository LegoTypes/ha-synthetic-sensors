"""Tests for CrossSensorReferenceManager."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from ha_synthetic_sensors.cross_sensor_reference_manager import CrossSensorReferenceManager


class TestCrossSensorReferenceManager:
    """Test cross-sensor reference manager functionality."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        return MagicMock()

    @pytest.fixture
    def ref_manager(self, mock_hass):
        """Create a CrossSensorReferenceManager instance."""
        return CrossSensorReferenceManager(mock_hass)

    def test_initialization(self, ref_manager):
        """Test manager initialization."""
        assert not ref_manager.has_cross_sensor_references()
        assert ref_manager.are_all_registrations_complete()
        assert len(ref_manager.get_all_entity_mappings()) == 0

    def test_initialize_from_config_simple(self, ref_manager):
        """Test initialization with simple cross-sensor references."""
        cross_sensor_refs = {"derived_power": {"base_power"}}

        ref_manager.initialize_from_config(cross_sensor_refs, None)

        assert ref_manager.has_cross_sensor_references()
        assert not ref_manager.are_all_registrations_complete()
        assert ref_manager.is_registration_pending("derived_power")
        assert ref_manager.is_registration_pending("base_power")

    def test_initialize_from_config_complex(self, ref_manager):
        """Test initialization with complex cross-sensor references."""
        cross_sensor_refs = {"total_power": {"base_power", "solar_power"}, "efficiency": {"solar_power", "total_power"}}

        ref_manager.initialize_from_config(cross_sensor_refs, None)

        status = ref_manager.get_registration_status()
        assert status["pending_count"] == 4  # base_power, solar_power, total_power, efficiency
        assert set(status["pending_sensors"]) == {"base_power", "solar_power", "total_power", "efficiency"}

    async def test_register_single_entity_id(self, ref_manager):
        """Test registering a single entity ID."""
        cross_sensor_refs = {
            "simple_sensor": {"simple_sensor"}  # Self-reference
        }

        ref_manager.initialize_from_config(cross_sensor_refs, None)

        # Register the entity ID
        await ref_manager.register_sensor_entity_id("simple_sensor", "sensor.simple_sensor_2")

        assert ref_manager.are_all_registrations_complete()
        assert ref_manager.is_registration_complete("simple_sensor")
        assert ref_manager.get_entity_id_for_sensor_key("simple_sensor") == "sensor.simple_sensor_2"
        assert ref_manager.get_sensor_key_for_entity_id("sensor.simple_sensor_2") == "simple_sensor"

    async def test_register_multiple_entity_ids(self, ref_manager):
        """Test registering multiple entity IDs."""
        cross_sensor_refs = {"derived_power": {"base_power"}, "efficiency": {"derived_power", "base_power"}}

        ref_manager.initialize_from_config(cross_sensor_refs, None)

        # Register entity IDs one by one
        await ref_manager.register_sensor_entity_id("base_power", "sensor.base_power_2")
        assert not ref_manager.are_all_registrations_complete()

        await ref_manager.register_sensor_entity_id("derived_power", "sensor.derived_power")
        assert not ref_manager.are_all_registrations_complete()

        await ref_manager.register_sensor_entity_id("efficiency", "sensor.efficiency")
        assert ref_manager.are_all_registrations_complete()

        # Check all mappings
        mappings = ref_manager.get_all_entity_mappings()
        expected = {
            "base_power": "sensor.base_power_2",
            "derived_power": "sensor.derived_power",
            "efficiency": "sensor.efficiency",
        }
        assert mappings == expected

    async def test_completion_callback(self, ref_manager):
        """Test completion callback execution."""
        cross_sensor_refs = {"simple_sensor": {"simple_sensor"}}

        ref_manager.initialize_from_config(cross_sensor_refs, None)

        # Add completion callback
        callback_called = False

        async def completion_callback():
            nonlocal callback_called
            callback_called = True

        ref_manager.add_completion_callback(completion_callback)

        # Register entity ID - should trigger callback
        await ref_manager.register_sensor_entity_id("simple_sensor", "sensor.simple_sensor_2")

        assert callback_called

    async def test_completion_callback_error_handling(self, ref_manager):
        """Test completion callback error handling."""
        cross_sensor_refs = {"simple_sensor": {"simple_sensor"}}

        ref_manager.initialize_from_config(cross_sensor_refs, None)

        # Add callback that raises an exception
        async def failing_callback():
            raise ValueError("Test error")

        ref_manager.add_completion_callback(failing_callback)

        # Should not raise exception despite callback failure
        await ref_manager.register_sensor_entity_id("simple_sensor", "sensor.simple_sensor_2")

        assert ref_manager.are_all_registrations_complete()

    def test_parent_sensor_reference_case(self, ref_manager):
        """Test the key use case: parent sensor references in attributes."""
        cross_sensor_refs = {
            "power_analyzer": {"power_analyzer"}  # Self-reference from attribute
        }

        ref_manager.initialize_from_config(cross_sensor_refs, None)

        assert ref_manager.is_registration_pending("power_analyzer")
        assert not ref_manager.are_all_registrations_complete()

    def test_get_registration_status(self, ref_manager):
        """Test registration status reporting."""
        cross_sensor_refs = {"sensor_a": {"sensor_b"}, "sensor_c": {"sensor_a", "sensor_b"}}

        ref_manager.initialize_from_config(cross_sensor_refs, None)

        status = ref_manager.get_registration_status()
        assert status["pending_count"] == 3
        assert status["completed_count"] == 0
        assert set(status["pending_sensors"]) == {"sensor_a", "sensor_b", "sensor_c"}
        assert status["completed_sensors"] == []
        assert status["entity_mappings"] == {}

    def test_empty_config(self, ref_manager):
        """Test handling of empty configuration."""
        ref_manager.initialize_from_config({}, None)

        assert not ref_manager.has_cross_sensor_references()
        assert ref_manager.are_all_registrations_complete()
        assert ref_manager.get_registration_status()["pending_count"] == 0

    async def test_register_non_pending_sensor(self, ref_manager):
        """Test registering a sensor that wasn't pending."""
        # Don't initialize with any references

        # Register an entity ID that wasn't pending
        await ref_manager.register_sensor_entity_id("unexpected_sensor", "sensor.unexpected")

        # Should still store the mapping
        assert ref_manager.get_entity_id_for_sensor_key("unexpected_sensor") == "sensor.unexpected"

    def test_get_missing_mappings(self, ref_manager):
        """Test getting mappings for non-existent sensors."""
        assert ref_manager.get_entity_id_for_sensor_key("nonexistent") is None
        assert ref_manager.get_sensor_key_for_entity_id("sensor.nonexistent") is None
