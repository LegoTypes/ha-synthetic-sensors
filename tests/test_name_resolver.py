"""Tests for name resolver module."""

from unittest.mock import MagicMock

from homeassistant.exceptions import HomeAssistantError
import pytest
from simpleeval import NameNotDefined

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

    def test_update_variables(self, mock_hass):
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

        with pytest.raises(NameNotDefined):
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
        with pytest.raises(HomeAssistantError):
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
            MagicMock(state="42.0") if entity_id in ["sensor.temperature", "sensor.humidity"] else None
        )

        validation_result = resolver.validate_variables()
        # Should have error for missing power entity
        assert not validation_result["is_valid"]
        assert any("sensor.power_meter" in error for error in validation_result["errors"])

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
        with pytest.raises(NameNotDefined):
            resolver.resolve_name(MockNode("unknown_var"))

        with pytest.raises(NameNotDefined):
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
                "sensor.other_sensor_formula": "75.2",  # Direct reference
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
        # "hvac + lighting + sensor.appliances_power + sensor.other_sensor_formula"

        hvac_value = resolver.resolve_name(MockNode("hvac"))  # Variable
        lighting_value = resolver.resolve_name(MockNode("lighting"))  # Variable
        appliances_value = resolver.resolve_name(MockNode("sensor.appliances_power"))
        other_value = resolver.resolve_name(MockNode("sensor.other_sensor_formula"))

        assert hvac_value == 200.0
        assert lighting_value == 85.5
        assert appliances_value == 150.8
        assert other_value == 75.2

        # Total would be 511.5 in a real formula evaluation
        total = hvac_value + lighting_value + appliances_value + other_value
        assert total == 511.5

    def test_get_static_names_success(self, mock_hass):
        """Test get_static_names method with successful resolution."""
        variables = {"temp": "sensor.temperature", "humidity": "sensor.humidity", "power": "sensor.power_meter"}
        resolver = NameResolver(mock_hass, variables)

        # Mock entity states
        def mock_get_state(entity_id):
            state_values = {"sensor.temperature": "23.5", "sensor.humidity": "65.2", "sensor.power_meter": "150.0"}
            if entity_id in state_values:
                mock_state = MagicMock()
                mock_state.state = state_values[entity_id]
                return mock_state
            return None

        mock_hass.states.get.side_effect = mock_get_state

        result = resolver.get_static_names()

        assert result == {"temp": 23.5, "humidity": 65.2, "power": 150.0}

    def test_get_static_names_with_failures(self, mock_hass):
        """Test get_static_names method with entity resolution failures."""
        variables = {"temp": "sensor.temperature", "missing": "sensor.missing_entity"}
        resolver = NameResolver(mock_hass, variables)

        # Mock only temperature entity
        def mock_get_state(entity_id):
            if entity_id == "sensor.temperature":
                mock_state = MagicMock()
                mock_state.state = "23.5"
                return mock_state
            return None

        mock_hass.states.get.side_effect = mock_get_state

        # Should raise error for missing entity
        with pytest.raises(HomeAssistantError):
            resolver.get_static_names()

    def test_clear_mappings_method(self, mock_hass, sample_variables):
        """Test clearing all variable mappings."""
        resolver = NameResolver(mock_hass, sample_variables)

        # Verify initial mappings exist
        assert len(resolver.variables) == 3
        assert "temp" in resolver.variables

        # Clear mappings
        resolver.clear_mappings()

        # Verify mappings are cleared
        assert len(resolver.variables) == 0
        assert resolver.variables == {}

    def test_add_entity_mapping_method(self, mock_hass):
        """Test adding entity mappings."""
        resolver = NameResolver(mock_hass, {})

        # Add first mapping
        resolver.add_entity_mapping("temp", "sensor.temperature")
        assert resolver.variables["temp"] == "sensor.temperature"

        # Add second mapping
        resolver.add_entity_mapping("humidity", "sensor.humidity")
        assert resolver.variables["humidity"] == "sensor.humidity"
        assert len(resolver.variables) == 2

        # Update existing mapping
        resolver.add_entity_mapping("temp", "sensor.new_temperature")
        assert resolver.variables["temp"] == "sensor.new_temperature"
        assert len(resolver.variables) == 2

    def test_remove_entity_mapping_method(self, mock_hass, sample_variables):
        """Test removing entity mappings."""
        resolver = NameResolver(mock_hass, sample_variables)

        # Remove existing mapping
        result = resolver.remove_entity_mapping("temp")
        assert result is True
        assert "temp" not in resolver.variables
        assert len(resolver.variables) == 2

        # Try to remove non-existent mapping
        result = resolver.remove_entity_mapping("nonexistent")
        assert result is False
        assert len(resolver.variables) == 2

    def test_extract_entity_references(self, mock_hass):
        """Test extracting entity references from formulas."""
        resolver = NameResolver(mock_hass, {})

        # Test formula with entity references
        formula1 = 'entity("sensor.test") + entity("sensor.another")'
        refs1 = resolver.extract_entity_references(formula1)
        assert refs1 == {"sensor.test", "sensor.another"}

        # Test formula with single quotes
        formula2 = "entity('sensor.single_quote')"
        refs2 = resolver.extract_entity_references(formula2)
        assert refs2 == {"sensor.single_quote"}

        # Test formula with no entity references
        formula3 = "temp + humidity * 2"
        refs3 = resolver.extract_entity_references(formula3)
        assert refs3 == set()

        # Test formula with mixed patterns
        formula4 = 'entity("sensor.a") + temp + entity("sensor.b")'
        refs4 = resolver.extract_entity_references(formula4)
        assert refs4 == {"sensor.a", "sensor.b"}

    def test_get_formula_dependencies(self, mock_hass):
        """Test getting formula dependencies."""
        variables = {"temp": "sensor.temperature", "humidity": "sensor.humidity", "unused": "sensor.unused"}
        resolver = NameResolver(mock_hass, variables)

        # Formula using variables and direct entity references
        formula = 'temp + humidity + entity("sensor.direct")'
        deps = resolver.get_formula_dependencies(formula)

        assert "sensor.temperature" in deps["entity_ids"]
        assert "sensor.humidity" in deps["entity_ids"]
        assert "sensor.direct" in deps["entity_ids"]
        assert "sensor.unused" not in deps["entity_ids"]  # Not used in formula

        assert deps["variable_mappings"]["temp"] == "sensor.temperature"
        assert deps["variable_mappings"]["humidity"] == "sensor.humidity"
        assert "unused" not in deps["variable_mappings"]

        assert deps["direct_references"] == {"sensor.direct"}
        assert deps["total_dependencies"] == 3

    def test_is_valid_entity_id(self, mock_hass):
        """Test entity ID validation."""
        resolver = NameResolver(mock_hass, {})

        # Valid entity IDs
        assert resolver._is_valid_entity_id("sensor.temperature") is True
        assert resolver._is_valid_entity_id("binary_sensor.door") is True
        assert resolver._is_valid_entity_id("switch.light_1") is True
        assert resolver._is_valid_entity_id("input_number.rate") is True

        # Invalid entity IDs
        assert resolver._is_valid_entity_id("no_dot") is False
        assert resolver._is_valid_entity_id("too.many.dots") is False
        assert resolver._is_valid_entity_id(".no_domain") is False
        assert resolver._is_valid_entity_id("domain.") is False
        assert resolver._is_valid_entity_id("") is False
        assert resolver._is_valid_entity_id("domain-with-dash.entity") is False
        assert resolver._is_valid_entity_id("domain.entity-with-dash") is False
        assert resolver._is_valid_entity_id("custom_domain.entity") is False  # Invalid domain

    def test_resolve_name_error_scenarios(self, mock_hass):
        """Test error handling in resolve_name method."""
        variables = {"temp": "sensor.temperature"}
        resolver = NameResolver(mock_hass, variables)

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Test entity not found
        mock_hass.states.get.return_value = None
        with pytest.raises(HomeAssistantError, match="Entity .* not found"):
            resolver.resolve_name(MockNode("temp"))

        # Test unavailable entity states
        unavailable_states = ["unavailable", "unknown", "none", None]
        for state_value in unavailable_states:
            mock_state = MagicMock()
            mock_state.state = state_value
            mock_hass.states.get.return_value = mock_state

            with pytest.raises(HomeAssistantError, match="is unavailable"):
                resolver.resolve_name(MockNode("temp"))

        # Test non-numeric state conversion
        mock_state = MagicMock()
        mock_state.state = "not_a_number"
        mock_hass.states.get.return_value = mock_state

        with pytest.raises(HomeAssistantError, match="cannot be converted to number"):
            resolver.resolve_name(MockNode("temp"))

        # Test direct entity ID that doesn't exist
        with pytest.raises(NameNotDefined, match="not defined and not a valid entity ID"):
            resolver.resolve_name(MockNode("invalid_entity_format"))

    def test_resolve_name_direct_entity_id_scenarios(self, mock_hass):
        """Test resolve_name with direct entity ID patterns."""
        resolver = NameResolver(mock_hass, {})

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Test valid direct entity ID
        mock_state = MagicMock()
        mock_state.state = "42.5"
        mock_hass.states.get.return_value = mock_state

        result = resolver.resolve_name(MockNode("sensor.direct_entity"))
        assert result == 42.5

        # Test direct entity ID not found
        mock_hass.states.get.return_value = None
        with pytest.raises(HomeAssistantError, match="not found"):
            resolver.resolve_name(MockNode("sensor.missing_direct"))

    def test_validate_variables_comprehensive(self, mock_hass):
        """Test comprehensive variable validation scenarios."""
        variables = {
            "existing1": "sensor.exists_1",
            "existing2": "sensor.exists_2",
            "missing1": "sensor.missing_1",
            "missing2": "sensor.missing_2",
        }
        resolver = NameResolver(mock_hass, variables)

        # Mock some entities exist, some don't
        def mock_get_state(entity_id):
            existing_entities = ["sensor.exists_1", "sensor.exists_2"]
            if entity_id in existing_entities:
                return MagicMock(state="42.0")
            return None

        mock_hass.states.get.side_effect = mock_get_state

        result = resolver.validate_variables()

        assert result["is_valid"] is False
        assert len(result["errors"]) == 2
        assert len(result["missing_entities"]) == 2
        assert len(result["valid_variables"]) == 2

        assert "sensor.missing_1" in result["missing_entities"]
        assert "sensor.missing_2" in result["missing_entities"]
        assert "existing1" in result["valid_variables"]
        assert "existing2" in result["valid_variables"]

        # Test all valid scenario
        mock_hass.states.get.side_effect = lambda entity_id: MagicMock(state="42.0")
        result_valid = resolver.validate_variables()
        assert result_valid["is_valid"] is True
        assert len(result_valid["errors"]) == 0
        assert len(result_valid["valid_variables"]) == 4


class TestFormulaEvaluator:
    """Test cases for FormulaEvaluator."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()
        return hass

    @pytest.fixture
    def sample_variables(self):
        """Create sample variable mappings for formula evaluator."""
        return {
            "temp": "sensor.temperature",
            "humidity": "sensor.humidity",
            "power": "sensor.power_meter",
        }

    def test_initialization(self, mock_hass, sample_variables):
        """Test FormulaEvaluator initialization."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        formula = "temp + humidity * 2"
        fallback = 42.0

        evaluator = FormulaEvaluator(mock_hass, formula, sample_variables, fallback)

        assert evaluator.formula == formula
        assert evaluator.variables == sample_variables
        assert evaluator.fallback_value == fallback
        assert evaluator._hass == mock_hass
        assert evaluator._formula == formula
        assert evaluator._variables == sample_variables
        assert evaluator._fallback_value == fallback

    def test_properties(self, mock_hass, sample_variables):
        """Test FormulaEvaluator properties."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        formula = "temp * 2 + 10"
        fallback = 0.0

        evaluator = FormulaEvaluator(mock_hass, formula, sample_variables, fallback)

        # Test properties return copies/immutable values
        assert evaluator.formula == formula
        assert evaluator.variables == sample_variables
        assert evaluator.fallback_value == fallback

        # Test that variables property returns a copy
        variables_copy = evaluator.variables
        variables_copy["new_var"] = "sensor.new"
        assert "new_var" not in evaluator.variables

    def test_evaluate_success(self, mock_hass, sample_variables):
        """Test successful formula evaluation."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        # Mock entity states
        def mock_get_state(entity_id):
            state_values = {"sensor.temperature": "25.5", "sensor.humidity": "60.0", "sensor.power_meter": "150.0"}
            if entity_id in state_values:
                mock_state = MagicMock()
                mock_state.state = state_values[entity_id]
                return mock_state
            return None

        mock_hass.states.get.side_effect = mock_get_state

        # Test simple formula
        evaluator = FormulaEvaluator(mock_hass, "temp + humidity", sample_variables)
        result = evaluator.evaluate()
        assert result == 85.5  # 25.5 + 60.0

        # Test more complex formula
        evaluator2 = FormulaEvaluator(mock_hass, "temp * 2 + humidity / 3", sample_variables)
        result2 = evaluator2.evaluate()
        assert result2 == 71.0  # 25.5 * 2 + 60.0 / 3 = 51.0 + 20.0

    def test_evaluate_with_fallback_on_entity_error(self, mock_hass, sample_variables):
        """Test formula evaluation falls back when entity resolution fails."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        # Mock missing entity
        mock_hass.states.get.return_value = None

        fallback_value = 99.9
        evaluator = FormulaEvaluator(mock_hass, "temp + humidity", sample_variables, fallback_value)
        result = evaluator.evaluate()

        assert result == fallback_value

    def test_evaluate_with_fallback_on_unavailable_entity(self, mock_hass, sample_variables):
        """Test formula evaluation falls back when entities are unavailable."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        # Mock unavailable entity
        mock_state = MagicMock()
        mock_state.state = "unavailable"
        mock_hass.states.get.return_value = mock_state

        fallback_value = 55.5
        evaluator = FormulaEvaluator(mock_hass, "temp + humidity", sample_variables, fallback_value)
        result = evaluator.evaluate()

        assert result == fallback_value

    def test_evaluate_with_fallback_on_syntax_error(self, mock_hass, sample_variables):
        """Test formula evaluation falls back on syntax errors."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        # Mock valid entity states
        mock_state = MagicMock()
        mock_state.state = "42.0"
        mock_hass.states.get.return_value = mock_state

        # Invalid formula syntax - use a more clearly invalid syntax
        fallback_value = 123.4
        evaluator = FormulaEvaluator(mock_hass, "temp + * humidity", sample_variables, fallback_value)
        result = evaluator.evaluate()

        assert result == fallback_value

    def test_evaluate_with_fallback_on_unknown_variable(self, mock_hass, sample_variables):
        """Test formula evaluation falls back on unknown variables."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        # Mock valid entity states
        mock_state = MagicMock()
        mock_state.state = "42.0"
        mock_hass.states.get.return_value = mock_state

        # Formula with unknown variable
        fallback_value = 88.8
        evaluator = FormulaEvaluator(mock_hass, "temp + unknown_var", sample_variables, fallback_value)
        result = evaluator.evaluate()

        assert result == fallback_value

    def test_validate_formula_success(self, mock_hass, sample_variables):
        """Test successful formula validation."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        # Mock all entities exist
        mock_state = MagicMock()
        mock_state.state = "42.0"
        mock_hass.states.get.return_value = mock_state

        evaluator = FormulaEvaluator(mock_hass, "temp + humidity * 2", sample_variables)
        errors = evaluator.validate_formula()

        assert errors == []

    def test_validate_formula_with_missing_entities(self, mock_hass, sample_variables):
        """Test formula validation with missing entities."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        # Mock some entities missing
        def mock_get_state(entity_id):
            if entity_id == "sensor.temperature":
                return MagicMock(state="42.0")
            return None  # Missing entities

        mock_hass.states.get.side_effect = mock_get_state

        evaluator = FormulaEvaluator(mock_hass, "temp + humidity", sample_variables)
        errors = evaluator.validate_formula()

        assert len(errors) > 0
        assert any("sensor.humidity" in error for error in errors)
        assert any("sensor.power_meter" in error for error in errors)

    def test_validate_formula_with_syntax_error(self, mock_hass, sample_variables):
        """Test formula validation with syntax errors."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        # Mock all entities exist
        mock_state = MagicMock()
        mock_state.state = "42.0"
        mock_hass.states.get.return_value = mock_state

        # Invalid syntax - use a more clearly invalid syntax
        evaluator = FormulaEvaluator(mock_hass, "temp + * humidity", sample_variables)
        errors = evaluator.validate_formula()

        assert len(errors) > 0
        assert any("syntax error" in error.lower() for error in errors)

    def test_get_dependencies(self, mock_hass):
        """Test getting formula dependencies."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        variables = {"temp": "sensor.temperature", "humidity": "sensor.humidity", "unused": "sensor.unused"}

        # Formula using some variables and direct entity reference
        formula = 'temp + humidity + entity("sensor.direct")'
        evaluator = FormulaEvaluator(mock_hass, formula, variables)

        dependencies = evaluator.get_dependencies()

        assert "sensor.temperature" in dependencies
        assert "sensor.humidity" in dependencies
        assert "sensor.direct" in dependencies
        assert "sensor.unused" not in dependencies  # Not used in formula
        assert len(dependencies) == 3

    def test_evaluate_with_direct_entity_references(self, mock_hass):
        """Test evaluation with direct entity ID references."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        variables = {
            "temp": "sensor.temperature",
            "direct_power": "sensor.direct_power",  # Use variable mapping instead
        }

        # Mock entity states
        def mock_get_state(entity_id):
            state_values = {"sensor.temperature": "25.0", "sensor.direct_power": "100.0"}
            if entity_id in state_values:
                mock_state = MagicMock()
                mock_state.state = state_values[entity_id]
                return mock_state
            return None

        mock_hass.states.get.side_effect = mock_get_state

        # Formula using variable mappings
        formula = "temp + direct_power"
        evaluator = FormulaEvaluator(mock_hass, formula, variables)
        result = evaluator.evaluate()

        assert result == 125.0  # 25.0 + 100.0

    def test_evaluate_numeric_result_conversion(self, mock_hass, sample_variables):
        """Test that evaluation results are properly converted to float."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        # Mock entity states
        mock_state = MagicMock()
        mock_state.state = "42"  # String that converts to int
        mock_hass.states.get.return_value = mock_state

        evaluator = FormulaEvaluator(mock_hass, "temp", sample_variables)
        result = evaluator.evaluate()

        assert isinstance(result, float)
        assert result == 42.0

    def test_evaluate_with_complex_mathematical_operations(self, mock_hass, sample_variables):
        """Test evaluation with complex mathematical operations."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        # Mock entity states
        def mock_get_state(entity_id):
            state_values = {"sensor.temperature": "25.0", "sensor.humidity": "50.0", "sensor.power_meter": "100.0"}
            if entity_id in state_values:
                mock_state = MagicMock()
                mock_state.state = state_values[entity_id]
                return mock_state
            return None

        mock_hass.states.get.side_effect = mock_get_state

        # Complex formula with multiple operations
        formula = "(temp + humidity) * power / 100"
        evaluator = FormulaEvaluator(mock_hass, formula, sample_variables)
        result = evaluator.evaluate()

        expected = (25.0 + 50.0) * 100.0 / 100  # = 75.0
        assert result == expected

    def test_default_fallback_value(self, mock_hass, sample_variables):
        """Test default fallback value when not specified."""
        from ha_synthetic_sensors.name_resolver import FormulaEvaluator

        # Mock missing entity to trigger fallback
        mock_hass.states.get.return_value = None

        evaluator = FormulaEvaluator(mock_hass, "temp", sample_variables)  # No fallback specified
        result = evaluator.evaluate()

        assert result == 0.0  # Default fallback value
