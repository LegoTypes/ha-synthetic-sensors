"""Tests for dependency parser module."""

import pytest

from ha_synthetic_sensors.dependency_parser import DependencyParser


from unittest.mock import patch


class TestDependencyParser:
    """Test cases for DependencyParser."""

    @pytest.fixture(autouse=True)
    def setup_patches(self, mock_hass):
        """Set up patches for all tests in this class."""
        with patch("ha_synthetic_sensors.constants_entities.er.async_get", side_effect=lambda h: h.entity_registry):
            yield

    @pytest.fixture
    def parser(self, mock_hass):
        """Create a DependencyParser instance."""
        return DependencyParser(mock_hass)

    def test_initialization(self, parser):
        """Test parser initialization."""
        assert parser is not None
        assert hasattr(parser, "_entity_patterns")
        assert hasattr(parser, "_states_pattern")
        assert hasattr(parser, "direct_entity_pattern")
        assert hasattr(parser, "_variable_pattern")
        assert hasattr(parser, "_excluded_terms")

    def test_extract_entity_function_calls(self, parser):
        """Test extraction of entity() function calls."""
        # Test entity() function
        formula = 'entity("sensor.temperature") + entity("sensor.humidity")'
        entities = parser.extract_entity_references(formula)
        assert "sensor.temperature" in entities
        assert "sensor.humidity" in entities

        # Test state() function
        formula = 'state("sensor.power") * 2'
        entities = parser.extract_entity_references(formula)
        assert "sensor.power" in entities

        # Test states[] notation
        formula = 'states["sensor.voltage"] / 10'
        entities = parser.extract_entity_references(formula)
        assert "sensor.voltage" in entities

    def test_extract_states_dot_notation(self, parser):
        """Test extraction of states.domain.entity notation."""
        formula = "states.sensor.temperature + states.sensor.humidity"
        entities = parser.extract_entity_references(formula)
        assert "sensor.temperature" in entities
        assert "sensor.humidity" in entities

    def test_extract_direct_entity_references(self, parser):
        """Test extraction of direct entity ID references."""
        formula = "sensor.kitchen_temp + sensor.living_room_temp"
        entities = parser.extract_entity_references(formula)
        assert "sensor.kitchen_temp" in entities
        assert "sensor.living_room_temp" in entities

    def test_extract_variables(self, parser):
        """Test extraction of variable names."""
        formula = "temp + humidity * 2"
        variables = parser.extract_variables(formula)
        assert "temp" in variables
        assert "humidity" in variables

        # Test with entity references - should exclude entity parts
        formula = "temp + sensor.humidity + variable"
        variables = parser.extract_variables(formula)
        assert "temp" in variables
        assert "variable" in variables
        assert "sensor" not in variables  # Part of entity ID - should be excluded
        assert "humidity" not in variables  # Part of entity ID - should be excluded

    def test_extract_dependencies_comprehensive(self, parser):
        """Test comprehensive dependency extraction."""
        formula = 'entity("sensor.power") + temp + states.sensor.voltage + sensor.current'
        dependencies = parser.extract_dependencies(formula)

        # Should include all types of references
        assert "sensor.power" in dependencies
        assert "temp" in dependencies
        assert "sensor.voltage" in dependencies
        assert "sensor.current" in dependencies

    def test_extract_dependencies_excludes_keywords(self, parser):
        """Test that Python keywords are excluded from dependencies."""
        formula = "temp + if + else + and"
        dependencies = parser.extract_dependencies(formula)

        assert "temp" in dependencies
        assert "if" not in dependencies
        assert "else" not in dependencies
        assert "and" not in dependencies

    def test_extract_dependencies_excludes_math_functions(self, parser):
        """Test that math functions are excluded from dependencies."""
        formula = "sin(temp) + cos(angle) + abs(value)"
        dependencies = parser.extract_dependencies(formula)

        assert "temp" in dependencies
        assert "angle" in dependencies
        assert "value" in dependencies
        assert "sin" not in dependencies
        assert "cos" not in dependencies
        assert "abs" not in dependencies

    def test_validate_formula_syntax_balanced_parentheses(self, parser):
        """Test validation of balanced parentheses."""
        # Valid formula
        errors = parser.validate_formula_syntax("(temp + humidity) * 2")
        assert len(errors) == 0

        # Unbalanced parentheses
        errors = parser.validate_formula_syntax("(temp + humidity) * 2)")
        assert any("parentheses" in error for error in errors)

        errors = parser.validate_formula_syntax("((temp + humidity) * 2")
        assert any("parentheses" in error for error in errors)

    def test_validate_formula_syntax_balanced_brackets(self, parser):
        """Test validation of balanced brackets."""
        # Valid formula
        errors = parser.validate_formula_syntax('states["sensor.temp"] + 5')
        assert len(errors) == 0

        # Unbalanced brackets
        errors = parser.validate_formula_syntax('states["sensor.temp"] + 5]')
        assert any("brackets" in error for error in errors)

        errors = parser.validate_formula_syntax('states[["sensor.temp"] + 5')
        assert any("brackets" in error for error in errors)

    def test_validate_formula_syntax_balanced_quotes(self, parser):
        """Test validation of balanced quotes."""
        # Valid formula
        errors = parser.validate_formula_syntax('entity("sensor.temp") + 5')
        assert len(errors) == 0

        # Unbalanced double quotes
        errors = parser.validate_formula_syntax('entity("sensor.temp) + 5')
        assert any("double quotes" in error for error in errors)

        # Unbalanced single quotes
        errors = parser.validate_formula_syntax("entity('sensor.temp) + 5")
        assert any("single quotes" in error for error in errors)

    def test_validate_formula_syntax_empty_formula(self, parser):
        """Test validation of empty formulas."""
        errors = parser.validate_formula_syntax("")
        assert any("empty" in error for error in errors)

        errors = parser.validate_formula_syntax("   ")
        assert any("empty" in error for error in errors)

    def test_validate_formula_syntax_incomplete_operators(self, parser):
        """Test validation of incomplete operators."""
        test_cases = [
            "temp +",
            "temp -",
            "temp *",
            "temp /",
            "temp =",
            "temp .",
            "temp ,",
        ]

        for formula in test_cases:
            errors = parser.validate_formula_syntax(formula)
            assert any("incomplete operator" in error for error in errors)

    def test_has_entity_references_true(self, parser):
        """Test has_entity_references returns True for formulas with entities."""
        test_cases = [
            'entity("sensor.temp")',
            'state("sensor.humidity")',
            'states["sensor.power"]',
            "states.sensor.voltage",
            "sensor.current + 5",
        ]

        for formula in test_cases:
            assert parser.has_entity_references(formula) is True

    def test_has_entity_references_false(self, parser):
        """Test has_entity_references returns False for formulas without entities."""
        test_cases = [
            "temp + humidity",
            "sin(angle) + cos(angle)",
            "5 + 10 * 2",
            "variable_name",
        ]

        for formula in test_cases:
            assert parser.has_entity_references(formula) is False

    def test_extract_dependencies_complex_formula(self, parser):
        """Test dependency extraction from complex formulas."""
        formula = """
        (entity("sensor.power_1") + entity("sensor.power_2")) * efficiency +
        states.sensor.voltage * current +
        sensor.frequency / base_freq +
        custom_variable
        """

        dependencies = parser.extract_dependencies(formula)

        # Should include entity references
        assert "sensor.power_1" in dependencies
        assert "sensor.power_2" in dependencies
        assert "sensor.voltage" in dependencies
        assert "sensor.frequency" in dependencies

        # Should include variables
        assert "efficiency" in dependencies
        assert "current" in dependencies
        assert "base_freq" in dependencies
        assert "custom_variable" in dependencies

    def test_extract_dependencies_with_entity_id_parts_exclusion(self, parser):
        """Test that parts of entity IDs are properly excluded from variables."""
        formula = "sensor.temperature + sensor.humidity + power_total"
        dependencies = parser.extract_dependencies(formula)

        # Should include full entity IDs
        assert "sensor.temperature" in dependencies
        assert "sensor.humidity" in dependencies

        # Should include variables
        assert "power_total" in dependencies

        # Should NOT include parts of entity IDs as separate variables
        assert "sensor" not in dependencies
        assert "temperature" not in dependencies
        assert "humidity" not in dependencies

    def test_excluded_terms_building(self, parser):
        """Test that excluded terms are properly built."""
        excluded = parser._excluded_terms

        # Should include Python keywords
        assert "if" in excluded
        assert "else" in excluded
        assert "and" in excluded
        assert "or" in excluded
        assert "not" in excluded
        assert "True" in excluded
        assert "False" in excluded
        assert "None" in excluded

        # Should include built-in types
        assert "str" in excluded
        assert "int" in excluded
        assert "float" in excluded
        assert "bool" in excluded

        # Should include mathematical constants
        assert "pi" in excluded
        assert "e" in excluded

        # Should include math function names
        assert "sin" in excluded
        assert "cos" in excluded
        assert "abs" in excluded

    def test_extract_variables_excludes_all_reserved_terms(self, parser):
        """Test that all reserved terms are excluded from variable extraction."""
        # Formula with many reserved terms
        formula = "temp + sin + cos + if + else + and + or + int + float + pi + e"
        variables = parser.extract_variables(formula)

        # Only 'temp' should be considered a variable
        assert "temp" in variables
        # Math functions should be excluded (our improvement)
        assert "sin" not in variables
        assert "cos" not in variables
        # Keywords should be excluded
        assert "if" not in variables
        assert "else" not in variables

    def test_mixed_quote_styles(self, parser):
        """Test handling of mixed quote styles in entity references."""
        formula = (
            """entity("sensor.temp") + state('sensor.humidity') + """
            """states["sensor.power"]"""
        )
        entities = parser.extract_entity_references(formula)

        assert "sensor.temp" in entities
        assert "sensor.humidity" in entities
        assert "sensor.power" in entities

    def test_edge_cases_entity_extraction(self, parser):
        """Test edge cases in entity extraction."""
        # Entity IDs with underscores and numbers
        formula = "sensor.temp_1 + sensor.humidity_2_avg"
        entities = parser.extract_entity_references(formula)
        assert "sensor.temp_1" in entities
        assert "sensor.humidity_2_avg" in entities

        # Empty entity references (should not crash but may not extract empty strings)
        formula = 'entity("") + state("")'
        entities = parser.extract_entity_references(formula)
        # Empty strings may or may not be extracted - this is implementation dependent

    def test_formula_with_no_dependencies(self, parser):
        """Test formulas with no dependencies."""
        formula = "5 + 10 * 2"
        dependencies = parser.extract_dependencies(formula)
        assert len(dependencies) == 0

        errors = parser.validate_formula_syntax(formula)
        assert len(errors) == 0

        assert not parser.has_entity_references(formula)
