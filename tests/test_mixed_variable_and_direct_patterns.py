"""Tests for mixed variable mapping and direct entity ID reference patterns."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from ha_synthetic_sensors.dependency_parser import DependencyParser
from ha_synthetic_sensors.name_resolver import NameResolver


class TestMixedVariableAndDirectPatterns:
    """Test all three supported patterns for entity references."""

    @pytest.fixture
    def parser(self):
        """Create a DependencyParser instance."""
        return DependencyParser()

    @pytest.fixture
    def mixed_patterns_config(self):
        """Load the mixed patterns example config file."""
        config_path = Path(__file__).parent.parent / "examples" / "mixed_variable_and_direct_config.yaml"

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def mock_hass(self, mixed_patterns_config):
        """Create a mock Home Assistant instance with states derived from config."""
        hass = MagicMock()
        hass.states = MagicMock()

        # Extract all entity IDs from the config and create mock states
        def get_all_entity_ids_from_config(config):
            """Extract all entity IDs referenced in the config."""
            entity_ids = set()

            for sensor_config in config["sensors"].values():
                # Add entities from variables
                for entity_id in sensor_config.get("variables", {}).values():
                    entity_ids.add(entity_id)

                # Extract entity IDs directly referenced in formulas
                # Simple extraction - in real use DependencyParser would do this
                formula = sensor_config["formula"]
                # Look for patterns like "sensor.something", "input_number.something"
                import re

                entity_pattern = r"\b(sensor|input_number|climate|switch|binary_sensor|button|" r"device_tracker)\.[\w_]+\b"
                found_entities = re.findall(entity_pattern, formula)
                for match in found_entities:
                    # Reconstruct the full entity ID from the regex match
                    start_pos = formula.find(match + ".")
                    if start_pos != -1:
                        # Find the end of the entity ID
                        remaining = formula[start_pos:]
                        entity_match = re.match(r"[\w\.]+", remaining)
                        if entity_match:
                            entity_ids.add(entity_match.group())

            return entity_ids

        entity_ids = get_all_entity_ids_from_config(mixed_patterns_config)

        # Create mock state values - using realistic values for testing
        state_values = {}
        for entity_id in entity_ids:
            if "power" in entity_id:
                if "circuit_5" in entity_id:
                    state_values[entity_id] = "100.0"
                elif "circuit_6" in entity_id:
                    state_values[entity_id] = "150.0"
                elif "circuit_10" in entity_id:
                    state_values[entity_id] = "50.0"
                elif "circuit_11" in entity_id:
                    state_values[entity_id] = "75.0"
                elif "circuit_12" in entity_id:
                    state_values[entity_id] = "25.0"
                elif "major_appliances" in entity_id:
                    state_values[entity_id] = "300.0"
                elif "water_heater" in entity_id:
                    state_values[entity_id] = "2000.0"
                elif "span_panel_current" in entity_id:
                    state_values[entity_id] = "2500.0"
                elif "solar_inverter" in entity_id:
                    state_values[entity_id] = "3000.0"
                elif "battery" in entity_id:
                    state_values[entity_id] = "500.0"
                else:
                    state_values[entity_id] = "100.0"  # Default power value
            elif "rate" in entity_id:
                if "buy" in entity_id:
                    state_values[entity_id] = "10.0"
                elif "sell" in entity_id:
                    state_values[entity_id] = "5.0"
                else:
                    state_values[entity_id] = "8.0"  # Default rate
            elif entity_id.startswith("sensor.syn2_"):
                # Synthetic sensors
                if "hvac" in entity_id:
                    state_values[entity_id] = "250.0"
                elif "lighting" in entity_id:
                    state_values[entity_id] = "150.0"
                elif "solar_export" in entity_id:
                    state_values[entity_id] = "500.0"
                else:
                    state_values[entity_id] = "200.0"  # Default synthetic value
            else:
                state_values[entity_id] = "50.0"  # Generic default

        def mock_get_state(entity_id):
            if entity_id in state_values:
                mock_state = MagicMock()
                mock_state.state = state_values[entity_id]
                return mock_state
            return None

        hass.states.get.side_effect = mock_get_state
        return hass

    @pytest.fixture
    def pattern_test_cases(self, mixed_patterns_config):
        """Extract pattern test cases from the config file."""
        sensors = mixed_patterns_config["sensors"]

        # Map sensor IDs to patterns based on their characteristics
        test_cases = {}

        for sensor_id, sensor_config in sensors.items():
            formula = sensor_config["formula"]
            variables = sensor_config.get("variables", {})

            # Determine pattern type
            has_variables = len(variables) > 0
            has_direct_entities = any(
                entity_ref in formula
                for entity_ref in [
                    "sensor.",
                    "input_number.",
                    "climate.",
                    "switch.",
                    "binary_sensor.",
                ]
            )

            if has_variables and not has_direct_entities:
                pattern = "pure_variables"
            elif not has_variables and has_direct_entities:
                pattern = "pure_direct"
            elif has_variables and has_direct_entities:
                pattern = "mixed"
            else:
                pattern = "unknown"

            if pattern not in test_cases:
                test_cases[pattern] = []

            test_cases[pattern].append(
                {
                    "sensor_id": sensor_id,
                    "formula": formula,
                    "variables": variables,
                    "config": sensor_config,
                }
            )

        return test_cases

    def test_pattern_1_pure_variable_mapping(self, parser, pattern_test_cases):
        """Test Pattern 1: Pure variable mapping with clean formula."""
        pure_variable_cases = pattern_test_cases.get("pure_variables", [])
        assert len(pure_variable_cases) > 0, "No pure variable cases found in config"

        for case in pure_variable_cases:
            formula = case["formula"]
            variables = case["variables"]

            # Test dependency extraction
            dependencies = parser.extract_dependencies(formula)
            extracted_variables = parser.extract_variables(formula)
            entity_refs = parser.extract_entity_references(formula)

            # Should find variables but no direct entity references
            for var_name in variables:
                assert var_name in extracted_variables
            assert len(entity_refs) == 0  # No direct entity IDs in formula

            # Dependencies should include the variables
            for var_name in variables:
                assert var_name in dependencies

    def test_pattern_2_pure_direct_entity_references(self, parser, pattern_test_cases):
        """Test Pattern 2: Pure direct entity ID references, no variables."""
        pure_direct_cases = pattern_test_cases.get("pure_direct", [])
        assert len(pure_direct_cases) > 0, "No pure direct cases found in config"

        for case in pure_direct_cases:
            formula = case["formula"]
            variables = case["variables"]

            # Test dependency extraction
            dependencies = parser.extract_dependencies(formula)
            extracted_variables = parser.extract_variables(formula)
            entity_refs = parser.extract_entity_references(formula)

            # Should find entity references but no variables (no variables defined)
            assert len(extracted_variables) == 0 or all(var not in variables for var in extracted_variables)
            assert len(entity_refs) > 0  # Should have direct entity references

            # Dependencies should include the entity IDs
            for entity_id in entity_refs:
                assert entity_id in dependencies

    def test_pattern_3_mixed_variables_and_direct_entities(self, parser, pattern_test_cases):
        """Test Pattern 3: Mixed variables and direct entity IDs in same formula."""
        mixed_cases = pattern_test_cases.get("mixed", [])
        assert len(mixed_cases) > 0, "No mixed cases found in config"

        for case in mixed_cases:
            formula = case["formula"]
            variables = case["variables"]

            # Test dependency extraction
            dependencies = parser.extract_dependencies(formula)
            extracted_variables = parser.extract_variables(formula)
            entity_refs = parser.extract_entity_references(formula)

            # Should find both variables and direct entity references
            for var_name in variables:
                assert var_name in extracted_variables
            assert len(entity_refs) > 0  # Should have direct entity references

            # Dependencies should include everything
            for var_name in variables:
                assert var_name in dependencies
            for entity_id in entity_refs:
                assert entity_id in dependencies

    def test_name_resolver_patterns(self, mock_hass, pattern_test_cases):
        """Test NameResolver with all patterns from config."""
        all_cases = []
        for pattern_cases in pattern_test_cases.values():
            all_cases.extend(pattern_cases)

        assert len(all_cases) > 0, "No test cases found in config"

        for case in all_cases:
            sensor_id = case["sensor_id"]
            variables = case["variables"]

            resolver = NameResolver(mock_hass, variables)

            class MockNode:
                def __init__(self, name):
                    self.id = name

            # Test that all variables can be resolved
            for var_name, entity_id in variables.items():
                resolved_value = resolver.resolve_name(MockNode(var_name))
                assert resolved_value is not None, f"Could not resolve variable '{var_name}' -> '{entity_id}' " f"in sensor {sensor_id}"

    def test_dependency_parser_extract_all_entities_comprehensive(self, parser):
        """Test that dependency parser can extract all entity types from formula."""
        # Test with a formula that includes multiple entity domains
        formula = "sensor.power + input_number.rate + climate.thermostat + " "switch.pump + binary_sensor.door"

        entity_refs = parser.extract_entity_references(formula)

        # Should detect all different entity domain types
        expected_entities = {
            "sensor.power",
            "input_number.rate",
            "climate.thermostat",
            "switch.pump",
            "binary_sensor.door",
        }

        assert expected_entities.issubset(entity_refs)

    def test_realistic_yaml_formula_simulation(self, parser, mock_hass, mixed_patterns_config):
        """Test simulation of realistic YAML formulas from the actual example config."""

        sensors = mixed_patterns_config["sensors"]

        # Test each sensor from the actual config file
        for sensor_id, sensor_config in sensors.items():

            formula = sensor_config["formula"]
            variables = sensor_config.get("variables", {})

            # Test dependency parser
            extracted_variables = parser.extract_variables(formula)
            dependencies = parser.extract_dependencies(formula)

            # Verify that variables defined in config are found in formula
            for var_name in variables:
                assert var_name in extracted_variables, f"Variable '{var_name}' defined in config but not found in formula"

            # Test name resolver with the actual config
            resolver = NameResolver(mock_hass, variables)

            # Verify that resolver can handle the formula
            deps = resolver.get_formula_dependencies(formula)
            assert isinstance(deps, dict)
            assert "entity_ids" in deps

            # Test that dependency extraction works
            assert len(dependencies) > 0, f"No dependencies found for {sensor_id}: {formula}"
