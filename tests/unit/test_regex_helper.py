"""Tests for centralized regex helper methods.

This module tests the method-wrapped regex patterns to ensure they work correctly
and consistently across the synthetic sensors system.
"""

import pytest
from ha_synthetic_sensors.regex_helper import (
    regex_helper,
    find_string_literals,
    extract_quoted_strings,
    extract_identifiers,
    extract_simple_identifiers,
    extract_basic_entity_ids,
    extract_metadata_entities,
    extract_exclusions,
    StringRange,
)


class TestStringLiteralMethods:
    """Test string literal method functionality."""

    def test_find_string_literals_single_quotes(self):
        """Test string literal range finding with single quotes."""
        text = "formula with 'single quoted string' and other text"
        ranges = find_string_literals(text)
        assert len(ranges) == 1
        assert ranges[0].start == 13
        assert ranges[0].end == 35

    def test_find_string_literals_double_quotes(self):
        """Test string literal range finding with double quotes."""
        text = 'formula with "double quoted string" and other text'
        ranges = find_string_literals(text)
        assert len(ranges) == 1
        assert ranges[0].start == 13
        assert ranges[0].end == 35

    def test_extract_quoted_strings(self):
        """Test extraction of quoted string contents."""
        text = 'sum("device_class:power", "area:kitchen")'
        strings = extract_quoted_strings(text)
        assert strings == ["device_class:power", "area:kitchen"]

    def test_extract_quoted_strings_empty(self):
        """Test handling of empty strings."""
        text = 'test("", "non-empty")'
        strings = extract_quoted_strings(text)
        assert strings == ["", "non-empty"]


class TestIdentifierMethods:
    """Test identifier extraction methods."""

    def test_extract_identifiers_basic(self):
        """Test basic identifier extraction."""
        text = "sensor.power + battery_level"
        identifiers = extract_identifiers(text)
        assert "sensor.power" in identifiers
        assert "battery_level" in identifiers

    def test_extract_simple_identifiers(self):
        """Test simple identifier extraction (no dots)."""
        text = "sensor.power + battery_level"
        identifiers = extract_simple_identifiers(text)
        assert "sensor" in identifiers
        assert "power" in identifiers
        assert "battery_level" in identifiers
        assert "sensor.power" not in identifiers

    def test_identifier_with_numbers(self):
        """Test identifiers with numbers."""
        text = "sensor_1 + value2 + test_var_3"
        identifiers = extract_simple_identifiers(text)
        assert "sensor_1" in identifiers
        assert "value2" in identifiers
        assert "test_var_3" in identifiers

    def test_identifier_underscore_start(self):
        """Test identifiers starting with underscore."""
        text = "_private_var + __dunder__ + normal_var"
        identifiers = extract_simple_identifiers(text)
        assert "_private_var" in identifiers
        assert "__dunder__" in identifiers
        assert "normal_var" in identifiers


class TestEntityIdMethods:
    """Test entity ID extraction methods."""

    def test_extract_basic_entity_ids(self):
        """Test basic entity ID extraction."""
        text = "sensor.power + binary_sensor.door + switch.light"
        entity_ids = extract_basic_entity_ids(text)
        assert "sensor.power" in entity_ids
        assert "binary_sensor.door" in entity_ids
        assert "switch.light" in entity_ids

    def test_entity_id_with_underscores(self):
        """Test entity IDs with underscores."""
        text = "sensor.circuit_a_power + sensor.battery_level_2"
        entity_ids = extract_basic_entity_ids(text)
        assert "sensor.circuit_a_power" in entity_ids
        assert "sensor.battery_level_2" in entity_ids

    def test_entity_id_with_dots_in_name(self):
        """Test entity IDs with dots in entity name."""
        text = "sensor.device.sub.component"
        entity_ids = extract_basic_entity_ids(text)
        assert "sensor.device.sub.component" in entity_ids


class TestMetadataMethods:
    """Test metadata function extraction methods."""

    def test_extract_metadata_entities(self):
        """Test metadata function entity extraction."""
        text = 'metadata("sensor.power", "device_class")'
        entities = extract_metadata_entities(text)
        assert "sensor.power" in entities

    def test_extract_metadata_entities_multiple(self):
        """Test multiple metadata function calls."""
        text = 'metadata("sensor.power", "device_class") + metadata("sensor.voltage", "unit")'
        entities = extract_metadata_entities(text)
        assert "sensor.power" in entities
        assert "sensor.voltage" in entities


class TestExclusionMethods:
    """Test exclusion pattern methods."""

    def test_extract_exclusions_quoted(self):
        """Test extraction of quoted exclusions."""
        text = '!"excluded_1", !"excluded_2"'
        exclusions = extract_exclusions(text)
        assert "excluded_1" in exclusions
        assert "excluded_2" in exclusions

    def test_extract_exclusions_unquoted(self):
        """Test extraction of unquoted exclusions."""
        text = "!excluded_1, !excluded_2"
        exclusions = extract_exclusions(text)
        assert "excluded_1" in exclusions
        assert "excluded_2" in exclusions

    def test_extract_exclusions_mixed(self):
        """Test extraction of mixed quoted and unquoted exclusions."""
        text = '!excluded_1, !"excluded_2"'
        exclusions = extract_exclusions(text)
        assert "excluded_1" in exclusions
        assert "excluded_2" in exclusions


class TestRegexHelperClass:
    """Test the RegexHelper class directly."""

    def test_pattern_caching(self):
        """Test that patterns are cached for performance."""
        helper = regex_helper

        # Call the same method twice
        result1 = helper.extract_identifiers("test.value")
        result2 = helper.extract_identifiers("test.value")

        # Results should be the same
        assert result1 == result2

        # Pattern should be cached (we can't easily test this without accessing internals)
        assert len(helper._patterns) > 0

    def test_different_patterns_cached_separately(self):
        """Test that different patterns are cached separately."""
        helper = regex_helper

        # Use different methods that use different patterns
        identifiers = helper.extract_identifiers("test.value")
        simple_identifiers = helper.extract_simple_identifiers("test.value")

        # Should have different results
        assert identifiers != simple_identifiers
        assert "test.value" in identifiers
        assert "test" in simple_identifiers
        assert "value" in simple_identifiers


class TestFormulaVariableResolutionMethods:
    """Test the new formula variable resolution methods."""

    def test_extract_formula_variables_for_resolution(self):
        """Test formula variable extraction for resolution."""
        from ha_synthetic_sensors.regex_helper import extract_formula_variables_for_resolution

        formula = "sensor_power + max(battery_level, 100)"
        variables = extract_formula_variables_for_resolution(formula)
        assert "sensor_power" in variables
        assert "battery_level" in variables
        assert "max" in variables

    def test_filter_variables_needing_resolution(self):
        """Test filtering of variables that need resolution."""
        from ha_synthetic_sensors.regex_helper import filter_variables_needing_resolution

        variables = ["sensor_power", "max", "battery_level", "sum"]
        filtered = filter_variables_needing_resolution(variables)
        assert "sensor_power" in filtered
        assert "battery_level" in filtered
        assert "max" not in filtered
        assert "sum" not in filtered

    def test_filter_variables_custom_functions(self):
        """Test filtering with custom function set."""
        from ha_synthetic_sensors.regex_helper import filter_variables_needing_resolution

        variables = ["sensor_power", "custom_func", "battery_level"]
        custom_functions = {"custom_func"}
        filtered = filter_variables_needing_resolution(variables, custom_functions)
        assert "sensor_power" in filtered
        assert "battery_level" in filtered
        assert "custom_func" not in filtered


class TestRealWorldExamples:
    """Test methods against real-world formula examples."""

    def test_complex_formula_entity_extraction(self):
        """Test entity extraction from complex formula."""
        formula = 'sensor.circuit_a_power + sensor.circuit_b_power + metadata("sensor.panel", "device_class")'

        # Test basic entity ID extraction
        entity_ids = extract_basic_entity_ids(formula)
        assert "sensor.circuit_a_power" in entity_ids
        assert "sensor.circuit_b_power" in entity_ids

        # Test metadata entity extraction
        metadata_entities = extract_metadata_entities(formula)
        assert "sensor.panel" in metadata_entities

    def test_formula_with_string_literals(self):
        """Test extraction with string literals that should be ignored."""
        formula = 'sensor.power + "sensor.fake_entity" + battery_level'

        # Basic entity extraction should find real entities
        entity_ids = extract_basic_entity_ids(formula)
        assert "sensor.power" in entity_ids

        # String literal extraction should find quoted strings
        quoted_strings = extract_quoted_strings(formula)
        assert "sensor.fake_entity" in quoted_strings

        # Identifier extraction should find all identifiers
        identifiers = extract_identifiers(formula)
        assert "sensor.power" in identifiers
        assert "battery_level" in identifiers

    def test_aggregation_formula_with_exclusions(self):
        """Test extraction from formula with exclusions."""
        formula = 'sum("device_class:power") + exclusions("!sensor.excluded")'

        # Should extract quoted strings
        quoted_strings = extract_quoted_strings(formula)
        assert "device_class:power" in quoted_strings
        assert "!sensor.excluded" in quoted_strings

        # Should extract exclusions from exclusion text
        exclusions = extract_exclusions("!sensor.excluded")
        assert "sensor.excluded" in exclusions
