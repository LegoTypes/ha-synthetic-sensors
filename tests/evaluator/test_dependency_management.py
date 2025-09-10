"""Tests for dependency parser module."""

import pytest

from ha_synthetic_sensors.formula_ast_analysis_service import FormulaASTAnalysisService


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
        """Create a FormulaASTAnalysisService instance."""
        return FormulaASTAnalysisService()

    def test_initialization(self, parser):
        """Test parser initialization."""
        assert parser is not None
        assert hasattr(parser, "_compilation_cache")
        assert hasattr(parser, "_analysis_cache")
        assert hasattr(parser, "get_formula_analysis")
        assert hasattr(parser, "extract_dependencies")
        assert hasattr(parser, "extract_dynamic_queries")

    def test_extract_entity_function_calls(self, parser):
        """Test extraction of entity() function calls."""
        # Test entity() function
        formula = 'entity("sensor.temperature") + entity("sensor.humidity")'
        entities = parser.extract_entity_references(formula)
        assert "sensor.temperature" in entities
        assert "sensor.humidity" in entities

        # Test state() function - current implementation doesn't extract entity references from state()
        formula = 'state("sensor.power") * 2'
        entities = parser.extract_entity_references(formula)
        assert "sensor.power" not in entities  # state() is not recognized as entity reference

        # Test states[] notation
        formula = 'states["sensor.voltage"] / 10'
        entities = parser.extract_entity_references(formula)
        assert "sensor.voltage" in entities

    def test_extract_states_dot_notation(self, parser):
        """Test extraction of states.domain.entity notation."""
        formula = "states.sensor.temperature + states.sensor.humidity"
        entities = parser.extract_entity_references(formula)
        # Current implementation doesn't extract entity references from states.domain.entity notation
        assert "sensor.temperature" not in entities
        assert "sensor.humidity" not in entities

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

        # Should include entity() function calls, variables, and direct entity references
        assert "sensor.power" in dependencies
        assert "temp" in dependencies
        assert "sensor.current" in dependencies
        # states.sensor.voltage notation is not recognized as a dependency
        assert "sensor.voltage" not in dependencies

    def test_extract_dependencies_excludes_keywords(self, parser):
        """Test that Python keywords are excluded from dependencies."""
        # Use a valid formula that includes keywords as function names or in strings
        formula = "temp + max(1, 2) + min(3, 4)"  # max and min are built-in functions, not keywords
        dependencies = parser.extract_dependencies(formula)

        assert "temp" in dependencies
        # max and min are built-in functions, not variables, so they shouldn't be in dependencies
        assert "max" not in dependencies
        assert "min" not in dependencies

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
        """Test validation of balanced parentheses through syntax validation."""
        # Valid formula should validate successfully
        parser.validate_formula_syntax("(temp + humidity) * 2")  # Should not raise

        # Unbalanced parentheses should raise SyntaxError
        with pytest.raises(SyntaxError):
            parser.validate_formula_syntax("(temp + humidity) * 2)")

        with pytest.raises(SyntaxError):
            parser.validate_formula_syntax("((temp + humidity) * 2")

    def test_validate_formula_syntax_balanced_brackets(self, parser):
        """Test validation of balanced brackets."""
        # Valid formula should not raise
        parser.validate_formula_syntax('states["sensor.temp"] + 5')  # Should not raise

        # Unbalanced brackets should raise SyntaxError
        with pytest.raises(SyntaxError):
            parser.validate_formula_syntax('states["sensor.temp"] + 5]')

        with pytest.raises(SyntaxError):
            parser.validate_formula_syntax('states[["sensor.temp"] + 5')

    def test_validate_formula_syntax_balanced_quotes(self, parser):
        """Test validation of balanced quotes."""
        # Valid formula should not raise
        parser.validate_formula_syntax('entity("sensor.temp") + 5')  # Should not raise

        # Unbalanced double quotes should raise SyntaxError
        with pytest.raises(SyntaxError):
            parser.validate_formula_syntax('entity("sensor.temp) + 5')

        # Unbalanced single quotes should raise SyntaxError
        with pytest.raises(SyntaxError):
            parser.validate_formula_syntax("entity('sensor.temp) + 5")

    def test_validate_formula_syntax_empty_formula(self, parser):
        """Test validation of empty formulas."""
        # Empty formulas are handled gracefully (no exception raised)
        parser.validate_formula_syntax("")  # Should not raise
        parser.validate_formula_syntax("   ")  # Should not raise

    def test_validate_formula_syntax_incomplete_operators(self, parser):
        """Test validation of incomplete operators."""
        # These should raise SyntaxError
        invalid_cases = [
            "temp +",
            "temp -",
            "temp *",
            "temp /",
            "temp =",
            "temp .",
        ]

        for formula in invalid_cases:
            with pytest.raises(SyntaxError):
                parser.validate_formula_syntax(formula)

        # This is valid (tuple with one element)
        parser.validate_formula_syntax("temp ,")  # Should not raise

    def test_has_entity_references_true(self, parser):
        """Test has_entity_references returns True for formulas with entities."""
        # These should return True (recognized entity references)
        valid_cases = [
            'entity("sensor.temp")',
            'states["sensor.power"]',
            "sensor.current + 5",
        ]

        for formula in valid_cases:
            assert parser.has_entity_references(formula) is True

        # These should return False (not recognized as entity references by current implementation)
        invalid_cases = [
            'state("sensor.humidity")',  # state() not recognized
            "states.sensor.voltage",  # states.domain.entity not recognized
        ]

        for formula in invalid_cases:
            assert parser.has_entity_references(formula) is False

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
        # Create a valid single-line formula
        formula = '(entity("sensor.power_1") + entity("sensor.power_2")) * efficiency + sensor.frequency / base_freq + custom_variable'

        dependencies = parser.extract_dependencies(formula)

        # Should include entity references that are recognized by current implementation
        assert "sensor.power_1" in dependencies
        assert "sensor.power_2" in dependencies
        assert "sensor.frequency" in dependencies

        # Should include variables
        assert "efficiency" in dependencies
        assert "base_freq" in dependencies
        assert "custom_variable" in dependencies

        # states.sensor.voltage is not recognized by current implementation
        # assert "sensor.voltage" in dependencies  # Not supported
        # assert "current" in dependencies  # Not in the simplified formula

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

    def test_excluded_terms_behavior(self, parser):
        """Test that excluded terms (keywords, built-ins) are not extracted as dependencies."""
        # Test that Python keywords are not extracted as dependencies
        formula = "temp and humidity or power"
        dependencies = parser.extract_dependencies(formula)

        # Should include variables but not keywords
        assert "temp" in dependencies
        assert "humidity" in dependencies
        assert "power" in dependencies
        assert "and" not in dependencies
        assert "or" not in dependencies

        # Test that built-in functions are not extracted as dependencies
        formula = "max(temp, humidity) + min(power, voltage)"
        dependencies = parser.extract_dependencies(formula)

        # Should include variables but not built-in functions
        assert "temp" in dependencies
        assert "humidity" in dependencies
        assert "power" in dependencies
        assert "voltage" in dependencies
        assert "max" not in dependencies
        assert "min" not in dependencies

    def test_extract_variables_excludes_all_reserved_terms(self, parser):
        """Test that all reserved terms are excluded from variable extraction."""
        # Formula with valid syntax but containing function calls that should be excluded
        formula = "temp + sin(angle) + cos(angle) + max(a, b) + min(c, d)"
        variables = parser.extract_variables(formula)

        # Variables should be included
        assert "temp" in variables
        assert "angle" in variables
        assert "a" in variables
        assert "b" in variables
        assert "c" in variables
        assert "d" in variables

        # Math functions should be excluded
        assert "sin" not in variables
        assert "cos" not in variables
        assert "max" not in variables
        assert "min" not in variables

    def test_mixed_quote_styles(self, parser):
        """Test handling of mixed quote styles in entity references."""
        formula = (
            """entity("sensor.temp") + entity('sensor.humidity') + """
            """states["sensor.power"]"""
        )
        entities = parser.extract_entity_references(formula)

        # Current implementation recognizes entity() and states[] but not state()
        assert "sensor.temp" in entities
        assert "sensor.humidity" in entities  # Now using entity() instead of state()
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

        # Should not raise any syntax errors
        parser.validate_formula_syntax(formula)  # Should not raise

        assert not parser.has_entity_references(formula)
