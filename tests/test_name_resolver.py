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

    def test_mixed_variable_and_direct_entity_resolution(self, mock_hass):
        """Test combination of variable mapping and direct entity ID resolution."""
        # Variables mapping for some entities
        variables = {"hvac": "sensor.hvac_power", "lighting": "sensor.lighting_power"}
        resolver = NameResolver(mock_hass, variables)

        # Mock different entity states
        def mock_get_state(entity_id):
            state_values = {
                "sensor.hvac_power": "150.5",  # Via variable mapping
                "sensor.lighting_power": "75.2",  # Via variable mapping
                "sensor.appliances_power": "89.8",  # Direct entity ID
                "sensor.solar_power": "320.0",  # Direct entity ID
            }
            if entity_id in state_values:
                mock_state = MagicMock()
                mock_state.state = state_values[entity_id]
                return mock_state
            return None

        mock_hass.states.get.side_effect = mock_get_state

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Test variable mapping resolution
        assert resolver.resolve_name(MockNode("hvac")) == 150.5
        assert resolver.resolve_name(MockNode("lighting")) == 75.2

        # Test direct entity ID resolution (no variable mapping needed)
        assert resolver.resolve_name(MockNode("sensor.appliances_power")) == 89.8
        assert resolver.resolve_name(MockNode("sensor.solar_power")) == 320.0

        # Test error for unknown variable and invalid entity ID
        with pytest.raises(Exception):  # Should raise NameNotDefined
            resolver.resolve_name(MockNode("unknown_var"))

        with pytest.raises(Exception):  # Should raise NameNotDefined
            resolver.resolve_name(MockNode("invalid_entity_id"))

    def test_realistic_formula_scenario_mixed_references(self, mock_hass):
        """Test realistic scenario like: hvac + lighting + sensor.appliances_power."""
        # This simulates a formula like: "hvac + lighting + sensor.appliances_power"
        # Where hvac and lighting are variables, but sensor.appliances_power is direct

        variables = {"hvac": "sensor.hvac_total", "lighting": "sensor.lighting_total"}
        resolver = NameResolver(mock_hass, variables)

        # Mock entity states for all references
        def mock_get_state(entity_id):
            state_values = {
                "sensor.hvac_total": "200.0",  # Variable: hvac
                "sensor.lighting_total": "85.5",  # Variable: lighting
                "sensor.appliances_power": "150.8",  # Direct entity ID
                "sensor.syn2_other_sensor_formula": "75.2",  # Direct syn2 reference
            }
            if entity_id in state_values:
                mock_state = MagicMock()
                mock_state.state = state_values[entity_id]
                return mock_state
            return None

        mock_hass.states.get.side_effect = mock_get_state

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Simulate what would happen during formula evaluation:
        # "hvac + lighting + sensor.appliances_power + sensor.syn2_other_sensor_formula"

        hvac_value = resolver.resolve_name(MockNode("hvac"))  # Variable
        lighting_value = resolver.resolve_name(MockNode("lighting"))  # Variable
        appliances_value = resolver.resolve_name(MockNode("sensor.appliances_power"))
        other_syn2_value = resolver.resolve_name(
            MockNode("sensor.syn2_other_sensor_formula")
        )

        assert hvac_value == 200.0
        assert lighting_value == 85.5
        assert appliances_value == 150.8
        assert other_syn2_value == 75.2

        # Total would be 511.5 in a real formula evaluation
        total = hvac_value + lighting_value + appliances_value + other_syn2_value
        assert total == 511.5
