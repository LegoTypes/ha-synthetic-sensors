"""Tests for name resolver module."""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.name_resolver import NameResolver


class TestNameResolver:
    """Test cases for NameResolver."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()
        return hass

    @pytest.fixture
    def sample_variables(self):
        """Create sample variable mappings."""
        return {
            "temp": "sensor.temperature",
            "humidity": "sensor.humidity",
            "power": "sensor.power_meter",
        }

    def test_initialization(self, mock_hass, sample_variables):
        """Test name resolver initialization."""
        resolver = NameResolver(mock_hass, sample_variables)
        assert resolver._hass == mock_hass
        assert resolver._variables == sample_variables

    def test_add_entity_mapping(self, mock_hass):
        """Test adding entity mappings."""
        variables = {"temp": "sensor.temperature"}
        resolver = NameResolver(mock_hass, variables)

        # Update variables to add new mapping
        new_variables = variables.copy()
        new_variables["humidity"] = "sensor.humidity"
        resolver.update_variables(new_variables)

        assert "humidity" in resolver.variables
        assert resolver.variables["humidity"] == "sensor.humidity"

    def test_remove_entity_mapping(self, mock_hass, sample_variables):
        """Test removing entity mappings."""
        resolver = NameResolver(mock_hass, sample_variables)

        # Update variables to remove mapping
        new_variables = sample_variables.copy()
        del new_variables["temp"]
        resolver.update_variables(new_variables)

        assert "temp" not in resolver.variables

    def test_clear_mappings(self, mock_hass, sample_variables):
        """Test clearing all mappings."""
        resolver = NameResolver(mock_hass, sample_variables)

        # Clear by setting empty variables
        resolver.update_variables({})

        assert len(resolver.variables) == 0

    def test_resolve_variable_direct_mapping(self, mock_hass, sample_variables):
        """Test resolving variable through direct mapping."""
        # Mock entity state
        mock_state = MagicMock()
        mock_state.state = "23.5"
        mock_hass.states.get.return_value = mock_state

        resolver = NameResolver(mock_hass, sample_variables)

        # Create mock node for simpleeval
        class MockNode:
            def __init__(self, name):
                self.id = name

        result = resolver.resolve_name(MockNode("temp"))
        assert result == 23.5

    def test_resolve_variable_direct_entity_id(self, mock_hass):
        """Test resolving variable with direct entity ID."""
        # Test that variables map correctly
        variables = {"test_var": "sensor.test_entity"}
        resolver = NameResolver(mock_hass, variables)

        assert resolver.variables["test_var"] == "sensor.test_entity"

    def test_resolve_variable_not_found(self, mock_hass, sample_variables):
        """Test handling of unknown variables."""
        resolver = NameResolver(mock_hass, sample_variables)

        # Create mock node for unknown variable
        class MockNode:
            def __init__(self, name):
                self.id = name

        with pytest.raises(Exception):  # Should raise NameNotDefined
            resolver.resolve_name(MockNode("unknown_var"))

    def test_convert_state_value(self, mock_hass, sample_variables):
        """Test state value conversion."""
        resolver = NameResolver(mock_hass, sample_variables)

        # Test numeric string
        mock_state = MagicMock()
        mock_state.state = "42.5"
        mock_hass.states.get.return_value = mock_state

        class MockNode:
            def __init__(self, name):
                self.id = name

        result = resolver.resolve_name(MockNode("temp"))
        assert result == 42.5

        # Test unavailable state
        mock_state.state = "unavailable"
        with pytest.raises(Exception):  # Should raise HomeAssistantError
            resolver.resolve_name(MockNode("temp"))

    def test_fuzzy_match_entity(self, mock_hass):
        """Test fuzzy matching of entity names."""
        variables = {"kitchen_temp": "sensor.kitchen_temperature"}
        resolver = NameResolver(mock_hass, variables)

        # Test name normalization
        normalized = resolver.normalize_name("Kitchen Temperature")
        assert normalized == "kitchen_temperature"

    def test_get_available_entities(self, mock_hass, sample_variables):
        """Test getting available entity mappings."""
        resolver = NameResolver(mock_hass, sample_variables)

        variables = resolver.variables
        assert "temp" in variables
        assert "humidity" in variables
        assert "power" in variables

    def test_validate_entities(self, mock_hass, sample_variables):
        """Test entity validation."""
        resolver = NameResolver(mock_hass, sample_variables)

        # Mock existing entities
        mock_hass.states.get.side_effect = lambda entity_id: (
            MagicMock(state="42.0")
            if entity_id in ["sensor.temperature", "sensor.humidity"]
            else None
        )

        validation_result = resolver.validate_variables()
        # Should have error for missing power entity
        assert not validation_result["is_valid"]
        assert any(
            "sensor.power_meter" in error for error in validation_result["errors"]
        )

    def test_suggest_mappings(self, mock_hass):
        """Test mapping suggestions functionality."""
        variables = {}
        resolver = NameResolver(mock_hass, variables)

        # Test normalize_name function
        result = resolver.normalize_name("HVAC Upstairs System")
        assert result == "hvac_upstairs_system"

    def test_resolve_attribute_path(self, mock_hass, sample_variables):
        """Test resolving entity attribute paths."""
        resolver = NameResolver(mock_hass, sample_variables)

        # Test entity references extraction
        references = resolver.extract_entity_references('entity("sensor.test") + 10')
        assert "sensor.test" in references

    def test_resolve_variable_with_attributes(self, mock_hass):
        """Test resolving variables that reference entity attributes."""
        variables = {"test_attr": "sensor.test_entity"}
        resolver = NameResolver(mock_hass, variables)

        # Mock entity with attributes
        mock_state = MagicMock()
        mock_state.state = "100"
        mock_state.attributes = {"unit": "W", "device_class": "power"}
        mock_hass.states.get.return_value = mock_state

        class MockNode:
            def __init__(self, name):
                self.id = name

        result = resolver.resolve_name(MockNode("test_attr"))
        assert result == 100.0
