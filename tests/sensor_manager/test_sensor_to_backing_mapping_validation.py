"""Tests for sensor-to-backing mapping validation."""

import pytest
from unittest.mock import MagicMock

from ha_synthetic_sensors.sensor_manager import SensorManager
from ha_synthetic_sensors.name_resolver import NameResolver


class TestSensorToBackingMappingValidation:
    """Test validation of sensor-to-backing mapping."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()
        hass.states.async_all = MagicMock(return_value=[])
        return hass

    @pytest.fixture
    def sensor_manager(self, mock_hass):
        """Create a SensorManager instance for testing."""
        name_resolver = NameResolver(mock_hass, {})
        add_entities_callback = MagicMock()
        return SensorManager(mock_hass, name_resolver, add_entities_callback)

    def test_valid_sensor_to_backing_mapping(self, sensor_manager):
        """Test that valid mapping is accepted."""
        valid_mapping = {
            "sensor_key_1": "sensor.backing_entity_1",
            "sensor_key_2": "sensor.backing_entity_2",
        }

        # Should not raise any exception
        sensor_manager.register_sensor_to_backing_mapping(valid_mapping)

        # Verify the mapping was stored
        assert sensor_manager._sensor_to_backing_mapping == valid_mapping

    def test_empty_mapping_raises_error(self, sensor_manager):
        """Test that empty mapping raises ValueError."""
        empty_mapping = {}

        with pytest.raises(ValueError, match="Empty sensor-to-backing mapping provided"):
            sensor_manager.register_sensor_to_backing_mapping(empty_mapping)

    def test_none_sensor_key_raises_error(self, sensor_manager):
        """Test that None sensor key raises ValueError."""
        invalid_mapping = {
            None: "sensor.backing_entity_1",
        }

        with pytest.raises(ValueError, match="None sensor key"):
            sensor_manager.register_sensor_to_backing_mapping(invalid_mapping)

    def test_none_backing_entity_id_raises_error(self, sensor_manager):
        """Test that None backing entity ID raises ValueError."""
        invalid_mapping = {
            "sensor_key_1": None,
        }

        with pytest.raises(ValueError, match="None backing entity ID for sensor key"):
            sensor_manager.register_sensor_to_backing_mapping(invalid_mapping)

    def test_empty_string_sensor_key_raises_error(self, sensor_manager):
        """Test that empty string sensor key raises ValueError."""
        invalid_mapping = {
            "": "sensor.backing_entity_1",
        }

        with pytest.raises(ValueError, match="Invalid sensor key"):
            sensor_manager.register_sensor_to_backing_mapping(invalid_mapping)

    def test_whitespace_only_sensor_key_raises_error(self, sensor_manager):
        """Test that whitespace-only sensor key raises ValueError."""
        invalid_mapping = {
            "   ": "sensor.backing_entity_1",
        }

        with pytest.raises(ValueError, match="Invalid sensor key"):
            sensor_manager.register_sensor_to_backing_mapping(invalid_mapping)

    def test_empty_string_backing_entity_id_raises_error(self, sensor_manager):
        """Test that empty string backing entity ID raises ValueError."""
        invalid_mapping = {
            "sensor_key_1": "",
        }

        with pytest.raises(ValueError, match="Invalid backing entity ID"):
            sensor_manager.register_sensor_to_backing_mapping(invalid_mapping)

    def test_whitespace_only_backing_entity_id_raises_error(self, sensor_manager):
        """Test that whitespace-only backing entity ID raises ValueError."""
        invalid_mapping = {
            "sensor_key_1": "   ",
        }

        with pytest.raises(ValueError, match="Invalid backing entity ID"):
            sensor_manager.register_sensor_to_backing_mapping(invalid_mapping)

    def test_non_string_sensor_key_raises_error(self, sensor_manager):
        """Test that non-string sensor key raises ValueError."""
        invalid_mapping = {
            123: "sensor.backing_entity_1",
        }

        with pytest.raises(ValueError, match="Invalid sensor key"):
            sensor_manager.register_sensor_to_backing_mapping(invalid_mapping)

    def test_non_string_backing_entity_id_raises_error(self, sensor_manager):
        """Test that non-string backing entity ID raises ValueError."""
        invalid_mapping = {
            "sensor_key_1": 456,
        }

        with pytest.raises(ValueError, match="Invalid backing entity ID"):
            sensor_manager.register_sensor_to_backing_mapping(invalid_mapping)

    def test_multiple_invalid_entries_raises_error_with_all_details(self, sensor_manager):
        """Test that multiple invalid entries are all reported."""
        invalid_mapping = {
            None: "sensor.backing_entity_1",
            "sensor_key_2": None,
            "": "sensor.backing_entity_3",
            "sensor_key_4": "",
        }

        with pytest.raises(ValueError) as exc_info:
            sensor_manager.register_sensor_to_backing_mapping(invalid_mapping)

        error_msg = str(exc_info.value)
        assert "None sensor key" in error_msg
        assert "None backing entity ID for sensor key" in error_msg
        assert "Invalid sensor key" in error_msg
        assert "Invalid backing entity ID" in error_msg


class TestDataProviderEntitiesValidation:
    """Test validation of data provider entities registration."""

    @pytest.fixture
    def sensor_manager(self, mock_hass, mock_entity_registry, mock_states):
        """Create a SensorManager instance for testing."""
        name_resolver = NameResolver(mock_hass, {})
        add_entities_callback = MagicMock()
        return SensorManager(mock_hass, name_resolver, add_entities_callback)

    def test_valid_entity_ids(self, mock_hass, mock_entity_registry, mock_states, sensor_manager):
        """Test that valid entity IDs are accepted."""
        valid_entities = {
            "sensor.backing_entity_1",
            "sensor.backing_entity_2",
        }

        # Should not raise any exception
        sensor_manager.register_data_provider_entities(valid_entities)

        # Verify the entities were stored
        assert sensor_manager._registered_entities == valid_entities

    def test_empty_entity_ids_is_allowed(self, mock_hass, mock_entity_registry, mock_states, sensor_manager):
        """Test that empty entity IDs set is allowed (just logs a warning)."""
        empty_entities = set()

        # Should not raise any exception
        sensor_manager.register_data_provider_entities(empty_entities)

        # Verify the entities were stored
        assert sensor_manager._registered_entities == empty_entities

    def test_none_entity_id_raises_error(self, mock_hass, mock_entity_registry, mock_states, sensor_manager):
        """Test that None entity ID raises ValueError."""
        invalid_entities = {
            "sensor.backing_entity_1",
            None,
        }

        with pytest.raises(ValueError, match="None entity ID"):
            sensor_manager.register_data_provider_entities(invalid_entities)

    def test_empty_string_entity_id_raises_error(self, mock_hass, mock_entity_registry, mock_states, sensor_manager):
        """Test that empty string entity ID raises ValueError."""
        invalid_entities = {
            "sensor.backing_entity_1",
            "",
        }

        with pytest.raises(ValueError, match="Invalid entity ID"):
            sensor_manager.register_data_provider_entities(invalid_entities)

    def test_whitespace_only_entity_id_raises_error(self, mock_hass, mock_entity_registry, mock_states, sensor_manager):
        """Test that whitespace-only entity ID raises ValueError."""
        invalid_entities = {
            "sensor.backing_entity_1",
            "   ",
        }

        with pytest.raises(ValueError, match="Invalid entity ID"):
            sensor_manager.register_data_provider_entities(invalid_entities)

    def test_non_string_entity_id_raises_error(self, mock_hass, mock_entity_registry, mock_states, sensor_manager):
        """Test that non-string entity ID raises ValueError."""
        invalid_entities = {
            "sensor.backing_entity_1",
            123,
        }

        with pytest.raises(ValueError, match="Invalid entity ID"):
            sensor_manager.register_data_provider_entities(invalid_entities)

    def test_multiple_invalid_entity_ids_raises_error_with_all_details(
        self, mock_hass, mock_entity_registry, mock_states, sensor_manager
    ):
        """Test that multiple invalid entity IDs are all reported."""
        invalid_entities = {
            None,
            "",
            "   ",
            123,
        }

        with pytest.raises(ValueError) as exc_info:
            sensor_manager.register_data_provider_entities(invalid_entities)

        error_msg = str(exc_info.value)
        assert "None entity ID" in error_msg
        assert "Invalid entity ID" in error_msg
