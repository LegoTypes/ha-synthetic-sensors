"""Tests for the Formula AST Analysis Service."""

import pytest

from ha_synthetic_sensors.formula_ast_analysis_service import (
    FormulaASTAnalysisService,
    FormulaAnalysis,
)
from ha_synthetic_sensors.formula_compilation_cache import FormulaCompilationCache


class TestFormulaASTAnalysisService:
    """Test the Formula AST Analysis Service."""

    def test_basic_variable_extraction(self):
        """Test extraction of basic variables from formula."""
        service = FormulaASTAnalysisService()

        analysis = service.get_formula_analysis("state + computed_var")

        assert "state" in analysis.variables
        assert "computed_var" in analysis.variables
        assert len(analysis.variables) == 2

    def test_entity_reference_extraction(self):
        """Test extraction of entity references."""
        service = FormulaASTAnalysisService()

        # Test direct entity reference
        analysis = service.get_formula_analysis("sensor.temperature + sensor.humidity")

        assert "sensor.temperature" in analysis.entity_references
        assert "sensor.humidity" in analysis.entity_references
        assert "sensor.temperature" in analysis.dependencies
        assert "sensor.humidity" in analysis.dependencies

    def test_metadata_call_extraction(self):
        """Test extraction of metadata function calls."""
        service = FormulaASTAnalysisService()

        # Test metadata with variable
        analysis = service.get_formula_analysis("metadata(state, 'last_changed')")

        assert ("state", "last_changed") in analysis.metadata_calls
        assert "state" in analysis.dependencies  # Variable should be a dependency

        # Test metadata with string literal entity
        analysis2 = service.get_formula_analysis("metadata(sensor.test, 'unit_of_measurement')")

        assert ("sensor.test", "unit_of_measurement") in analysis2.metadata_calls

    def test_collection_function_extraction(self):
        """Test extraction of collection/aggregation functions."""
        service = FormulaASTAnalysisService()

        analysis = service.get_formula_analysis("mean(sensor1, sensor2, sensor3)")

        assert "mean" in analysis.collection_functions
        assert ("mean", ["sensor1", "sensor2", "sensor3"]) in analysis.function_calls
        assert "sensor1" in analysis.dependencies
        assert "sensor2" in analysis.dependencies
        assert "sensor3" in analysis.dependencies

    def test_complex_formula_analysis(self):
        """Test analysis of complex formula with multiple elements."""
        service = FormulaASTAnalysisService()

        formula = "(sensor.power * 1.5 + computed_var) / mean(sensor.voltage, sensor.current) + metadata(state, 'last_updated')"

        analysis = service.get_formula_analysis(formula)

        # Check variables
        assert "state" in analysis.variables
        assert "computed_var" in analysis.variables

        # Check entity references
        assert "sensor.power" in analysis.entity_references
        assert "sensor.voltage" in analysis.entity_references
        assert "sensor.current" in analysis.entity_references

        # Check metadata calls
        assert ("state", "last_updated") in analysis.metadata_calls

        # Check collection functions
        assert "mean" in analysis.collection_functions

        # Check dependencies
        assert "computed_var" in analysis.dependencies
        assert "sensor.power" in analysis.dependencies
        assert "state" in analysis.dependencies

    def test_caching_behavior(self):
        """Test that analysis results are cached."""
        service = FormulaASTAnalysisService()

        # First call should miss cache
        analysis1 = service.get_formula_analysis("state + computed_var")
        stats1 = service.get_statistics()
        assert stats1["cache_misses"] == 1
        assert stats1["cache_hits"] == 0

        # Second call should hit cache
        analysis2 = service.get_formula_analysis("state + computed_var")
        stats2 = service.get_statistics()
        assert stats2["cache_misses"] == 1
        assert stats2["cache_hits"] == 1

        # Should be the same object (cached)
        assert analysis1 is analysis2

    def test_state_token_detection(self):
        """Test detection of special 'state' token."""
        service = FormulaASTAnalysisService()

        analysis = service.get_formula_analysis("state * 2")
        assert analysis.has_state_token is True

        analysis2 = service.get_formula_analysis("sensor.power * 2")
        assert analysis2.has_state_token is False

    def test_entity_function_extraction(self):
        """Test extraction of entity() function calls."""
        service = FormulaASTAnalysisService()

        analysis = service.get_formula_analysis("entity('sensor.test') + 10")

        assert ("entity", ["sensor.test"]) in analysis.function_calls
        assert "sensor.test" in analysis.entity_references
        assert "sensor.test" in analysis.dependencies

    def test_states_subscript_extraction(self):
        """Test extraction of states['sensor.name'] pattern."""
        service = FormulaASTAnalysisService()

        analysis = service.get_formula_analysis("states['sensor.temperature'] + states['sensor.humidity']")

        assert "sensor.temperature" in analysis.entity_references
        assert "sensor.humidity" in analysis.entity_references
        assert "sensor.temperature" in analysis.dependencies
        assert "sensor.humidity" in analysis.dependencies

    def test_cross_sensor_reference_detection(self):
        """Test proper detection of cross-sensor references."""
        service = FormulaASTAnalysisService()

        # Test actual variable reference
        assert service.is_cross_sensor_reference("base_sensor + 10", "base_sensor") is True

        # Test string literal (should not be detected)
        assert service.is_cross_sensor_reference("'base_sensor' + other", "base_sensor") is False

        # Test partial match (should not match)
        assert service.is_cross_sensor_reference("my_base_sensor + 10", "base_sensor") is False

    def test_convenience_methods(self):
        """Test convenience methods for variable and dependency extraction."""
        service = FormulaASTAnalysisService()

        # Test extract_variables
        variables = service.extract_variables("var1 + var2 + sensor.test")
        assert "var1" in variables
        assert "var2" in variables
        # Note: 'sensor.test' is treated as an entity reference, not a variable

        # Test extract_dependencies
        dependencies = service.extract_dependencies("var1 + sensor.temperature")
        assert "var1" in dependencies
        assert "sensor.temperature" in dependencies

        # Test extract_metadata_calls
        metadata_calls = service.extract_metadata_calls("metadata(state, 'last_changed') + metadata(sensor1, 'unit')")
        assert ("state", "last_changed") in metadata_calls
        assert ("sensor1", "unit") in metadata_calls

    def test_error_handling(self):
        """Test graceful handling of invalid formulas."""
        service = FormulaASTAnalysisService()

        # Invalid syntax should return empty analysis
        analysis = service.get_formula_analysis("invalid syntax ++")

        # Should return empty analysis without crashing
        assert isinstance(analysis, FormulaAnalysis)
        assert len(analysis.variables) == 0
        assert len(analysis.dependencies) == 0

    def test_attribute_access_dependency(self):
        """Test that attribute access creates proper dependencies."""
        service = FormulaASTAnalysisService()

        analysis = service.get_formula_analysis("temperature_sensor.value + humidity_sensor.state")

        # The base variables should be dependencies
        assert "temperature_sensor" in analysis.dependencies
        assert "humidity_sensor" in analysis.dependencies

        # The full references should not be in entity_references
        # (they're variable.attribute, not domain.entity)
        assert "temperature_sensor.value" not in analysis.entity_references
        assert "humidity_sensor.state" not in analysis.entity_references

    def test_nested_function_calls(self):
        """Test extraction from nested function calls."""
        service = FormulaASTAnalysisService()

        analysis = service.get_formula_analysis("max(mean(s1, s2), sum(s3, s4))")

        assert "mean" in analysis.collection_functions
        assert "max" in analysis.collection_functions
        assert "sum" in analysis.collection_functions

        assert "s1" in analysis.dependencies
        assert "s2" in analysis.dependencies
        assert "s3" in analysis.dependencies
        assert "s4" in analysis.dependencies

    def test_no_string_literal_extraction(self):
        """Test that variables are not extracted from string literals."""
        service = FormulaASTAnalysisService()

        analysis = service.get_formula_analysis("'sensor.test' + 'computed_var'")

        # Should not extract variables from strings
        assert "sensor" not in analysis.variables
        assert "test" not in analysis.variables
        assert "computed_var" not in analysis.variables

        # Should not have dependencies from string literals
        assert len(analysis.dependencies) == 0
