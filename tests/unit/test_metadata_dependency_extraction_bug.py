"""Test for metadata function dependency extraction bug fix."""

import pytest
from unittest.mock import Mock, patch

from ha_synthetic_sensors.formula_ast_analysis_service import FormulaASTAnalysisService


class TestMetadataDependencyExtraction:
    """Test metadata function dependency extraction to prevent regression."""

    @pytest.fixture
    def parser(self):
        """Create a DependencyParser with mocked dependencies."""
        mock_hass = Mock()
        mock_hass.data = {}

        # Mock the entity registry
        mock_registry = Mock()
        mock_registry.entities = {}
        mock_hass.entity_registry = mock_registry

        with patch("ha_synthetic_sensors.constants_entities.er") as mock_er:
            mock_er.async_get.return_value = mock_registry
            yield FormulaASTAnalysisService(mock_hass)

    def test_metadata_function_string_literals_not_extracted_as_dependencies(self, parser):
        """Test that string literals in metadata function calls are not extracted as dependencies.

        This test prevents regression of the circular dependency bug where string literals
        like 'domain', 'last_changed' were incorrectly extracted as dependencies.
        """
        # Test case 1: metadata domain call
        formula = "metadata(binary_sensor.panel_status, 'domain')"
        dependencies = parser.extract_dependencies(formula)
        entities = parser.extract_entity_references(formula)

        # Should extract the entity ID but NOT the string literal 'domain'
        assert "binary_sensor.panel_status" in entities
        assert "domain" not in dependencies, "String literal 'domain' should not be extracted as dependency"
        assert "metadata" not in dependencies, "Function name 'metadata' should not be extracted as dependency"

        # Test case 2: metadata last_changed call
        formula = "metadata(sensor.temperature, 'last_changed')"
        dependencies = parser.extract_dependencies(formula)
        entities = parser.extract_entity_references(formula)

        # Should extract the entity ID but NOT the string literal 'last_changed'
        assert "sensor.temperature" in entities
        assert "last_changed" not in dependencies, "String literal 'last_changed' should not be extracted as dependency"

        # Test case 3: metadata with other properties
        test_cases = [
            ("metadata(binary_sensor.panel_status, 'last_updated')", "last_updated"),
            ("metadata(sensor.power, 'friendly_name')", "friendly_name"),
            ("metadata(switch.outlet, 'object_id')", "object_id"),
        ]

        for formula, string_literal in test_cases:
            dependencies = parser.extract_dependencies(formula)
            assert string_literal not in dependencies, (
                f"String literal '{string_literal}' should not be extracted as dependency from: {formula}"
            )

    def test_circular_dependency_scenario_prevented(self, parser):
        """Test that the circular dependency scenario is prevented.

        This test specifically checks the scenario that caused the original bug:
        An attribute named 'debug_metadata_domain' with formula containing 'domain'.
        """
        # This is the exact scenario that caused the circular dependency
        attribute_name = "debug_metadata_domain"
        formula = "metadata(binary_sensor.panel_status, 'domain')"

        dependencies = parser.extract_dependencies(formula)

        # The string 'domain' should NOT be extracted as a dependency
        # This prevents the circular reference: debug_metadata_domain -> domain -> debug_metadata_domain
        assert "domain" not in dependencies, (
            f"String literal 'domain' extracted as dependency could create circular reference "
            f"with attribute name '{attribute_name}'"
        )

        # But the entity should still be extracted
        entities = parser.extract_entity_references(formula)
        assert "binary_sensor.panel_status" in entities

    def test_metadata_function_with_variables_still_works(self, parser):
        """Test that metadata functions with variables (not string literals) still work."""
        # This should still extract the variable as a dependency
        formula = "metadata(sensor_var, 'last_changed')"
        dependencies = parser.extract_dependencies(formula)

        # Should extract the variable but not the string literal
        assert "sensor_var" in dependencies, "Variable should be extracted as dependency"
        assert "last_changed" not in dependencies, "String literal should not be extracted as dependency"

    def test_complex_metadata_formulas(self, parser):
        """Test complex formulas with metadata functions."""
        formula = (
            "minutes_between(metadata('binary_sensor.panel_status', 'last_changed'), utc_now()) if not panel_status else 0"
        )
        dependencies = parser.extract_dependencies(formula)
        entities = parser.extract_entity_references(formula)

        # Should extract entity but not string literals or function names
        assert "binary_sensor.panel_status" in entities
        # Note: panel_status is excluded because it's part of the entity ID binary_sensor.panel_status
        # This is separate from the string literal bug we're fixing
        assert "last_changed" not in dependencies, "String literal should not be extracted"
        assert "utc_now" not in dependencies, "Function name should not be extracted"
        assert "minutes_between" not in dependencies, "Function name should not be extracted"
        assert "metadata" not in dependencies, "Function name should not be extracted"
