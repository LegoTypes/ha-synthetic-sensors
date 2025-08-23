"""Tests for name resolver module."""

from unittest.mock import MagicMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from ha_synthetic_sensors.name_resolver import NameResolver


class TestNameResolver:
    """Test cases for NameResolver."""

    @pytest.fixture
    def sample_variables(self):
        """Create sample variable mappings."""
        return {
            "temp": "sensor.temperature",
            "humidity": "sensor.humidity",
            "power": "sensor.power_meter",
        }

    def test_initialization(self, mock_hass, mock_entity_registry, mock_states, sample_variables):
        """Test name resolver initialization."""
        resolver = NameResolver(mock_hass, sample_variables)
        assert resolver._hass == mock_hass
        assert resolver._variables == sample_variables

    def test_update_variables(self, mock_hass, mock_entity_registry, mock_states):
        """Test updating variable mappings."""
        variables = {"temp": "sensor.temperature"}
        resolver = NameResolver(mock_hass, variables)

        # Update variables to add new mapping
        new_variables = variables.copy()
        new_variables["humidity"] = "sensor.humidity"
        resolver.update_variables(new_variables)

        assert "humidity" in resolver.variables
        assert resolver.variables["humidity"] == "sensor.humidity"

        # Update variables to remove mapping
        final_variables = {"humidity": "sensor.humidity"}
        resolver.update_variables(final_variables)

        assert "temp" not in resolver.variables
        assert "humidity" in resolver.variables

    def test_validate_variables(self, mock_hass, mock_entity_registry, mock_states, sample_variables):
        """Test variable validation."""
        resolver = NameResolver(mock_hass, sample_variables)

        # Mock existing entities
        mock_hass.states.get.side_effect = lambda entity_id: (
            MagicMock(state="42.0") if entity_id in ["sensor.temperature", "sensor.humidity"] else None
        )

        validation_result = resolver.validate_variables()
        # Should have error for missing power entity
        assert not validation_result["is_valid"]
        assert any("sensor.power_meter" in error for error in validation_result["errors"])

    def test_normalize_name(self, mock_hass, mock_entity_registry, mock_states):
        """Test name normalization functionality."""
        variables = {}
        resolver = NameResolver(mock_hass, variables)

        # Test normalize_name function
        result = resolver.normalize_name("HVAC Upstairs System")
        assert result == "hvac_upstairs_system"

        result = resolver.normalize_name("Kitchen Temperature")
        assert result == "kitchen_temperature"

    def test_extract_entity_references(self, mock_hass, mock_entity_registry, mock_states, sample_variables):
        """Test extracting entity references from formulas."""
        resolver = NameResolver(mock_hass, sample_variables)

        # Test entity references extraction
        references = resolver.extract_entity_references('entity("sensor.test") + 10')
        assert "sensor.test" in references

        references = resolver.extract_entity_references('entity("binary_sensor.motion") + entity("sensor.temp")')
        assert "binary_sensor.motion" in references
        assert "sensor.temp" in references

    def test_get_formula_dependencies(self, mock_hass, mock_entity_registry, mock_states, sample_variables):
        """Test getting formula dependencies."""
        resolver = NameResolver(mock_hass, sample_variables)

        # Test formula with variables and direct references
        formula = "temp + entity('sensor.other') + humidity"
        dependencies = resolver.get_formula_dependencies(formula)

        assert "sensor.temperature" in dependencies["entity_ids"]
        assert "sensor.humidity" in dependencies["entity_ids"]
        assert "sensor.other" in dependencies["entity_ids"]
        assert "temp" in dependencies["variable_mappings"]
        assert "humidity" in dependencies["variable_mappings"]

    def test_validate_entity_id(self, mock_hass, mock_entity_registry, mock_states):
        """Test entity ID validation."""
        variables = {}
        resolver = NameResolver(mock_hass, variables)

        # Valid entity IDs
        assert resolver.validate_entity_id("sensor.temperature")
        assert resolver.validate_entity_id("binary_sensor.motion")
        assert resolver.validate_entity_id("switch.light")

        # Invalid entity IDs
        assert not resolver.validate_entity_id("invalid")
        assert not resolver.validate_entity_id("sensor")
        assert not resolver.validate_entity_id("sensor.temp.value")

    def test_extract_entity_type(self, mock_hass, mock_entity_registry, mock_states):
        """Test entity type extraction."""
        variables = {}
        resolver = NameResolver(mock_hass, variables)

        assert resolver.extract_entity_type("sensor.temperature") == "sensor"
        assert resolver.extract_entity_type("binary_sensor.motion") == "binary_sensor"
        assert resolver.extract_entity_type("switch.light") == "switch"
        assert resolver.extract_entity_type("invalid") is None

    def test_validate_variable_name(self, mock_hass, mock_entity_registry, mock_states):
        """Test variable name validation."""
        variables = {}
        resolver = NameResolver(mock_hass, variables)

        # Valid variable names
        assert resolver.validate_variable_name("temp")
        assert resolver.validate_variable_name("_temp")
        assert resolver.validate_variable_name("temp_1")
        assert resolver.validate_variable_name("temperature_sensor")

        # Invalid variable names
        assert not resolver.validate_variable_name("1temp")
        assert not resolver.validate_variable_name("temp-1")
        assert not resolver.validate_variable_name("temp.1")

    def test_validate_sensor_config(self, mock_hass, mock_entity_registry, mock_states):
        """Test sensor configuration validation."""
        variables = {"temp": "sensor.temperature"}
        resolver = NameResolver(mock_hass, variables)

        # Valid sensor config
        valid_config = {
            "unique_id": "test_sensor",
            "entity_id": "sensor.test",
            "formulas": [{"id": "main", "formula": "temp + 10"}],
        }
        result = resolver.validate_sensor_config(valid_config)
        assert len(result["errors"]) == 0

        # Invalid sensor config
        invalid_config = {
            "unique_id": "",  # Empty unique_id
            "formulas": [],  # No formulas
        }
        result = resolver.validate_sensor_config(invalid_config)
        assert len(result["errors"]) > 0

    def test_resolve_entity_references(self, mock_hass, mock_entity_registry, mock_states):
        """Test resolving entity references in formulas."""
        variables = {"temp": "sensor.temperature"}
        resolver = NameResolver(mock_hass, variables)

        # Formula with variables and direct references
        formula = "temp + sensor.other + binary_sensor.motion"
        entity_ids = resolver.resolve_entity_references(formula, variables)

        assert "sensor.temperature" in entity_ids
        assert "sensor.other" in entity_ids
        assert "binary_sensor.motion" in entity_ids

    def test_add_remove_entity_mapping(self, mock_hass, mock_entity_registry, mock_states):
        """Test adding and removing entity mappings."""
        variables = {}
        resolver = NameResolver(mock_hass, variables)

        # Add mapping
        resolver.add_entity_mapping("temp", "sensor.temperature")
        assert "temp" in resolver.variables
        assert resolver.variables["temp"] == "sensor.temperature"

        # Remove mapping
        assert resolver.remove_entity_mapping("temp") is True
        assert "temp" not in resolver.variables

        # Remove non-existent mapping
        assert resolver.remove_entity_mapping("nonexistent") is False

    def test_clear_mappings(self, mock_hass, mock_entity_registry, mock_states, sample_variables):
        """Test clearing all mappings."""
        resolver = NameResolver(mock_hass, sample_variables)
        assert len(resolver.variables) > 0

        resolver.clear_mappings()
        assert len(resolver.variables) == 0
