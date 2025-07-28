"""Tests for FormulaReferenceResolver."""

import pytest

from ha_synthetic_sensors.formula_reference_resolver import FormulaReferenceResolver
from ha_synthetic_sensors.config_models import Config, SensorConfig, FormulaConfig


class TestFormulaReferenceResolver:
    """Test formula reference resolution functionality."""

    @pytest.fixture
    def resolver(self):
        """Create a FormulaReferenceResolver instance."""
        return FormulaReferenceResolver()

    @pytest.fixture
    def simple_config_with_references(self):
        """Create a simple config with cross-sensor references."""
        # Main sensor formula
        main_formula = FormulaConfig(id="simple_parent_reference", formula="state * 2")

        # Attribute formula with parent sensor reference
        attr_formula = FormulaConfig(id="simple_parent_reference_doubled_state", formula="simple_parent_reference * 3")

        sensor = SensorConfig(
            unique_id="simple_parent_reference",
            entity_id="sensor.span_panel_instantaneous_power",
            formulas=[main_formula, attr_formula],
        )

        config = Config(sensors=[sensor])
        config.cross_sensor_references = {"simple_parent_reference": {"simple_parent_reference"}}

        return config

    @pytest.fixture
    def complex_config_with_references(self):
        """Create a complex config with multiple cross-sensor references."""
        # Base power sensor
        base_power_main = FormulaConfig(id="base_power", formula="state * 1.0")
        base_power_sensor = SensorConfig(
            unique_id="base_power", entity_id="sensor.span_panel_instantaneous_power", formulas=[base_power_main]
        )

        # Solar power sensor
        solar_power_main = FormulaConfig(id="solar_power", formula="state * 0.8")
        solar_power_sensor = SensorConfig(unique_id="solar_power", entity_id="sensor.solar_power", formulas=[solar_power_main])

        # Total power sensor (references base_power and solar_power)
        total_power_main = FormulaConfig(id="total_power", formula="base_power + solar_power")
        total_power_attr = FormulaConfig(id="total_power_efficiency", formula="solar_power / total_power * 100")
        total_power_sensor = SensorConfig(unique_id="total_power", formulas=[total_power_main, total_power_attr])

        config = Config(sensors=[base_power_sensor, solar_power_sensor, total_power_sensor])
        config.cross_sensor_references = {"total_power": {"base_power", "solar_power", "total_power"}}

        return config

    def test_resolve_simple_parent_reference(self, resolver, simple_config_with_references):
        """Test resolving simple parent sensor reference."""
        entity_mappings = {"simple_parent_reference": "sensor.simple_parent_reference_2"}

        resolved_config = resolver.resolve_all_references_in_config(simple_config_with_references, entity_mappings)

        # Check that the config was resolved
        assert len(resolved_config.sensors) == 1
        sensor = resolved_config.sensors[0]

        # Main formula should be unchanged (no references)
        assert sensor.formulas[0].formula == "state * 2"

        # Attribute formula should use state token for self-reference
        assert sensor.formulas[1].formula == "state * 3"

    def test_resolve_complex_references(self, resolver, complex_config_with_references):
        """Test resolving complex cross-sensor references."""
        entity_mappings = {
            "base_power": "sensor.base_power_2",
            "solar_power": "sensor.solar_power_3",
            "total_power": "sensor.total_power_4",
        }

        resolved_config = resolver.resolve_all_references_in_config(complex_config_with_references, entity_mappings)

        # Check sensors were resolved correctly
        assert len(resolved_config.sensors) == 3

        # Base power sensor - no references to resolve
        base_sensor = resolved_config.sensors[0]
        assert base_sensor.formulas[0].formula == "state * 1.0"

        # Solar power sensor - no references to resolve
        solar_sensor = resolved_config.sensors[1]
        assert solar_sensor.formulas[0].formula == "state * 0.8"

        # Total power sensor - references should be resolved
        total_sensor = resolved_config.sensors[2]
        assert total_sensor.formulas[0].formula == "sensor.base_power_2 + sensor.solar_power_3"
        # Self-reference in attribute should use state token
        assert total_sensor.formulas[1].formula == "sensor.solar_power_3 / state * 100"

    def test_no_references_to_resolve(self, resolver):
        """Test config with no cross-sensor references."""
        main_formula = FormulaConfig(id="independent_sensor", formula="state * 2.5")
        sensor = SensorConfig(unique_id="independent_sensor", formulas=[main_formula])
        config = Config(sensors=[sensor])

        entity_mappings = {"some_other_sensor": "sensor.some_other_sensor_2"}

        resolved_config = resolver.resolve_all_references_in_config(config, entity_mappings)

        # Formula should be unchanged
        assert resolved_config.sensors[0].formulas[0].formula == "state * 2.5"

    def test_empty_entity_mappings(self, resolver, simple_config_with_references):
        """Test handling of empty entity mappings."""
        resolved_config = resolver.resolve_all_references_in_config(simple_config_with_references, {})

        # Config should be returned unchanged
        assert len(resolved_config.sensors) == 1
        sensor = resolved_config.sensors[0]
        assert sensor.formulas[1].formula == "simple_parent_reference * 3"  # Unchanged

    def test_partial_entity_mappings(self, resolver, complex_config_with_references):
        """Test handling of partial entity mappings."""
        # Only provide mapping for some sensors
        entity_mappings = {
            "base_power": "sensor.base_power_2"
            # Missing: solar_power, total_power
        }

        resolved_config = resolver.resolve_all_references_in_config(complex_config_with_references, entity_mappings)

        total_sensor = resolved_config.sensors[2]
        # Only base_power should be resolved, others remain as sensor keys
        assert total_sensor.formulas[0].formula == "sensor.base_power_2 + solar_power"
        assert total_sensor.formulas[1].formula == "solar_power / total_power * 100"

    def test_tokenization_preserves_formula_structure(self, resolver):
        """Test that tokenization preserves complex formula structure."""
        formula_string = "( base_power + solar_power ) / 2 >= 1000.5"
        entity_mappings = {"base_power": "sensor.base_power_2", "solar_power": "sensor.solar_power_3"}

        resolved = resolver._resolve_references_in_formula_string(formula_string, entity_mappings)

        # Should preserve structure and resolve references
        expected = "( sensor.base_power_2 + sensor.solar_power_3 ) / 2 >= 1000.5"
        assert resolved == expected

    def test_tokenization_avoids_partial_matches(self, resolver):
        """Test that tokenization avoids partial word matches."""
        formula_string = "base_power_extended + base_power + some_base_power_thing"
        entity_mappings = {"base_power": "sensor.base_power_2"}

        resolved = resolver._resolve_references_in_formula_string(formula_string, entity_mappings)

        # Only exact matches should be replaced
        expected = "base_power_extended + sensor.base_power_2 + some_base_power_thing"
        assert resolved == expected

    def test_get_replacement_summary(self, resolver, complex_config_with_references):
        """Test getting replacement summary without modifying config."""
        entity_mappings = {
            "base_power": "sensor.base_power_2",
            "solar_power": "sensor.solar_power_3",
            "total_power": "sensor.total_power_4",
        }

        summary = resolver.get_replacement_summary(complex_config_with_references, entity_mappings)

        # Should report what would be replaced
        assert "total_power" in summary
        total_replacements = summary["total_power"]

        # Check main formula replacement info
        assert "total_power" in total_replacements
        main_info = total_replacements["total_power"]
        assert main_info["original_formula"] == "base_power + solar_power"
        assert main_info["replacements"] == {"base_power": "sensor.base_power_2", "solar_power": "sensor.solar_power_3"}

    # Legacy tokenization tests removed - implementation now uses modular ReferencePatternDetector and ReferenceReplacer
    # def test_tokenize_formula_preserving_structure(self, resolver):
    #     """Test formula tokenization preserves structure."""
    #     formula = "base_power * 1.5 + (solar_power / 2)"
    #
    #     tokens = resolver._tokenize_formula_preserving_structure(formula)
    #
    #     # Should include all tokens including operators and whitespace
    #     expected_tokens = ["base_power", " ", "*", " ", "1.5", " ", "+", " ", "(", "solar_power", " ", "/", " ", "2", ")"]
    #     assert tokens == expected_tokens
    #
    # def test_reconstruct_formula_from_tokens(self, resolver):
    #     """Test formula reconstruction from tokens."""
    #     resolved_tokens = ["sensor.base_power_2", " ", "*", " ", "3"]
    #
    #     result = resolver._reconstruct_formula_from_tokens(resolved_tokens)
    #
    #     assert result == "sensor.base_power_2 * 3"

    def test_formula_with_decimal_numbers(self, resolver):
        """Test that decimal numbers are not mistaken for entity references."""
        formula_string = "base_power * 1.5 + 0.25"
        entity_mappings = {"base_power": "sensor.base_power_2"}

        resolved = resolver._resolve_references_in_formula_string(formula_string, entity_mappings)

        # Decimals should not be affected
        assert resolved == "sensor.base_power_2 * 1.5 + 0.25"

    def test_formula_with_complex_expressions(self, resolver):
        """Test complex formula expressions."""
        formula_string = "max(base_power, solar_power) if total_power > 0 else 0"
        entity_mappings = {
            "base_power": "sensor.base_power_2",
            "solar_power": "sensor.solar_power_3",
            "total_power": "sensor.total_power_4",
        }

        resolved = resolver._resolve_references_in_formula_string(formula_string, entity_mappings)

        expected = "max(sensor.base_power_2, sensor.solar_power_3) if sensor.total_power_4 > 0 else 0"
        assert resolved == expected

    def test_resolve_references_in_variables(self, resolver):
        """Test resolving sensor key references in variables."""
        variables = {
            "base_sensor": "base_power",  # Should be resolved
            "numeric_value": 100,  # Should remain unchanged
            "string_literal": "some_string",  # Should remain unchanged (not a sensor key)
            "solar_ref": "solar_power",  # Should be resolved
        }

        entity_mappings = {"base_power": "sensor.base_power_2", "solar_power": "sensor.solar_power_3"}

        resolved = resolver._resolve_references_in_variables(variables, entity_mappings)

        expected = {
            "base_sensor": "sensor.base_power_2",  # Resolved
            "numeric_value": 100,  # Unchanged
            "string_literal": "some_string",  # Unchanged
            "solar_ref": "sensor.solar_power_3",  # Resolved
        }
        assert resolved == expected

    def test_resolve_references_in_dependencies(self, resolver):
        """Test resolving sensor key references in dependencies."""
        dependencies = {
            "base_power",  # Should be resolved
            "sensor.existing_entity",  # Should remain unchanged (already entity ID)
            "solar_power",  # Should be resolved
            "other_reference",  # Should remain unchanged (not in mappings)
        }

        entity_mappings = {"base_power": "sensor.base_power_2", "solar_power": "sensor.solar_power_3"}

        resolved = resolver._resolve_references_in_dependencies(dependencies, entity_mappings)

        expected = {
            "sensor.base_power_2",  # Resolved
            "sensor.existing_entity",  # Unchanged
            "sensor.solar_power_3",  # Resolved
            "other_reference",  # Unchanged
        }
        assert resolved == expected

    def test_resolve_references_in_attributes_simple(self, resolver):
        """Test resolving sensor key references in simple attributes."""
        attributes = {
            "source_sensor": "base_power",  # Should be resolved
            "constant_value": "literal_string",  # Should remain unchanged
            "numeric_attr": 42,  # Should remain unchanged
            "another_sensor": "solar_power",  # Should be resolved
        }

        entity_mappings = {"base_power": "sensor.base_power_2", "solar_power": "sensor.solar_power_3"}

        resolved = resolver._resolve_references_in_attributes(attributes, entity_mappings)

        expected = {
            "source_sensor": "sensor.base_power_2",  # Resolved
            "constant_value": "literal_string",  # Unchanged
            "numeric_attr": 42,  # Unchanged
            "another_sensor": "sensor.solar_power_3",  # Resolved
        }
        assert resolved == expected

    def test_resolve_references_in_attributes_nested(self, resolver):
        """Test resolving sensor key references in nested attributes."""
        attributes = {
            "config": {
                "primary_sensor": "base_power",  # Should be resolved
                "settings": {
                    "backup_sensor": "solar_power",  # Should be resolved (nested)
                    "threshold": 100,  # Should remain unchanged
                },
            },
            "sensor_list": ["base_power", "solar_power", "other_sensor"],  # List items should be resolved
            "mixed_list": [
                {"sensor": "base_power", "multiplier": 1.5},  # Dict in list should be resolved
                "literal_string",
            ],
        }

        entity_mappings = {"base_power": "sensor.base_power_2", "solar_power": "sensor.solar_power_3"}

        resolved = resolver._resolve_references_in_attributes(attributes, entity_mappings)

        expected = {
            "config": {
                "primary_sensor": "sensor.base_power_2",  # Resolved
                "settings": {
                    "backup_sensor": "sensor.solar_power_3",  # Resolved (nested)
                    "threshold": 100,  # Unchanged
                },
            },
            "sensor_list": ["sensor.base_power_2", "sensor.solar_power_3", "other_sensor"],  # List resolved
            "mixed_list": [
                {"sensor": "sensor.base_power_2", "multiplier": 1.5},  # Dict in list resolved
                "literal_string",
            ],
        }
        assert resolved == expected

    def test_comprehensive_formula_resolution(self, resolver):
        """Test complete formula resolution including all types of references."""
        from ha_synthetic_sensors.config_models import FormulaConfig

        # Create a formula with references in all possible locations
        formula = FormulaConfig(
            id="comprehensive_test",
            formula="base_power + solar_power * 2",  # Formula string with references
            variables={
                "backup_sensor": "base_power",  # Variable referencing sensor key
                "threshold": 1000,  # Numeric variable (unchanged)
                "monitoring_sensor": "solar_power",  # Another variable reference
            },
            dependencies={"base_power", "solar_power", "sensor.external_entity"},  # Mixed dependencies
            attributes={
                "source": "base_power",  # Simple attribute reference
                "config": {
                    "primary": "solar_power",  # Nested reference
                    "timeout": 30,  # Numeric value (unchanged)
                },
                "sensor_array": ["base_power", "solar_power"],  # Array with references
            },
        )

        entity_mappings = {"base_power": "sensor.base_power_2", "solar_power": "sensor.solar_power_3"}

        resolved = resolver._resolve_references_in_formula(formula, entity_mappings, "comprehensive_test")

        # Verify formula string resolution
        assert resolved.formula == "sensor.base_power_2 + sensor.solar_power_3 * 2"

        # Verify variables resolution
        assert resolved.variables == {
            "backup_sensor": "sensor.base_power_2",  # Resolved
            "threshold": 1000,  # Unchanged
            "monitoring_sensor": "sensor.solar_power_3",  # Resolved
        }

        # Verify dependencies resolution
        assert resolved.dependencies == {
            "sensor.base_power_2",  # Resolved
            "sensor.solar_power_3",  # Resolved
            "sensor.external_entity",  # Unchanged (already entity ID)
        }

        # Verify attributes resolution
        assert resolved.attributes == {
            "source": "sensor.base_power_2",  # Resolved
            "config": {
                "primary": "sensor.solar_power_3",  # Resolved
                "timeout": 30,  # Unchanged
            },
            "sensor_array": ["sensor.base_power_2", "sensor.solar_power_3"],  # Resolved
        }

    def test_empty_and_none_handling(self, resolver):
        """Test handling of empty and None values in all resolution methods."""
        entity_mappings = {"test_sensor": "sensor.test_sensor_2"}

        # Test empty/None variables
        assert resolver._resolve_references_in_variables({}, entity_mappings) == {}
        assert resolver._resolve_references_in_variables({"key": "value"}, {}) == {"key": "value"}

        # Test empty/None dependencies
        assert resolver._resolve_references_in_dependencies(set(), entity_mappings) == set()
        assert resolver._resolve_references_in_dependencies({"test"}, {}) == {"test"}

        # Test empty/None attributes
        assert resolver._resolve_references_in_attributes({}, entity_mappings) == {}
        assert resolver._resolve_references_in_attributes({"key": "value"}, {}) == {"key": "value"}
