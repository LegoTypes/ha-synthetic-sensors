"""Tests for mixed variable mapping and direct entity ID reference patterns."""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.dependency_parser import DependencyParser
from ha_synthetic_sensors.name_resolver import NameResolver


class TestMixedVariableAndDirectPatterns:
    """Test all three supported patterns for entity references."""

    @pytest.fixture
    def parser(self):
        """Create a DependencyParser instance."""
        return DependencyParser()

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()

        def mock_get_state(entity_id):
            state_values = {
                # Base HA entities
                "sensor.circuit_5_power": "100.0",
                "sensor.circuit_6_power": "150.0",
                "sensor.circuit_10_power": "50.0",
                "sensor.circuit_11_power": "75.0",
                "sensor.circuit_12_power": "25.0",
                "sensor.major_appliances_power": "300.0",
                "sensor.water_heater_power": "2000.0",
                "input_number.electricity_buy_rate_cents_kwh": "10.0",
                "input_number.electricity_sell_rate_cents_kwh": "5.0",
                "sensor.span_panel_current_power": "2500.0",
                "sensor.span_panel_solar_inverter_instant_power": "3000.0",
                # Synthetic sensors
                "sensor.syn2_hvac_total_clean_hvac_total": "250.0",
                "sensor.syn2_lighting_total_direct_lighting_total": "150.0",
                "sensor.syn2_solar_analytics_solar_export": "500.0",
            }

            if entity_id in state_values:
                mock_state = MagicMock()
                mock_state.state = state_values[entity_id]
                return mock_state
            return None

        hass.states.get.side_effect = mock_get_state
        return hass

    def test_pattern_1_pure_variable_mapping(self, parser):
        """Test Pattern 1: Pure variable mapping with clean formula."""
        # Pattern 1 example: formula: "heating + cooling"
        formula = "heating + cooling"

        # Test dependency extraction
        dependencies = parser.extract_dependencies(formula)
        extracted_variables = parser.extract_variables(formula)
        entity_refs = parser.extract_entity_references(formula)

        # Should find variables but no direct entity references
        assert "heating" in extracted_variables
        assert "cooling" in extracted_variables
        assert len(entity_refs) == 0  # No direct entity IDs in formula

        # Dependencies should include both approaches
        assert "heating" in dependencies or "cooling" in dependencies

    def test_pattern_2_pure_direct_entity_references(self, parser):
        """Test Pattern 2: Pure direct entity ID references, no variables."""
        # Pattern 2 example: direct entity IDs in formula
        formula = (
            "sensor.circuit_10_power + sensor.circuit_11_power + "
            "sensor.circuit_12_power"
        )

        # Test dependency extraction
        dependencies = parser.extract_dependencies(formula)
        extracted_variables = parser.extract_variables(formula)
        entity_refs = parser.extract_entity_references(formula)

        # Should find entity references but no variables
        assert len(extracted_variables) == 0  # No variable names
        assert "sensor.circuit_10_power" in entity_refs
        assert "sensor.circuit_11_power" in entity_refs
        assert "sensor.circuit_12_power" in entity_refs

        # Dependencies should include the entity IDs
        assert "sensor.circuit_10_power" in dependencies
        assert "sensor.circuit_11_power" in dependencies
        assert "sensor.circuit_12_power" in dependencies

    def test_pattern_3_mixed_variables_and_direct_entities(self, parser):
        """Test Pattern 3: Mixed variables and direct entity IDs in same formula."""
        # Pattern 3 example: mix of variables and direct entity references
        formula = (
            "hvac_total + lighting_total + sensor.major_appliances_power + "
            "sensor.water_heater_power"
        )

        # Test dependency extraction
        dependencies = parser.extract_dependencies(formula)
        extracted_variables = parser.extract_variables(formula)
        entity_refs = parser.extract_entity_references(formula)

        # Should find both variables and direct entity references
        assert "hvac_total" in extracted_variables
        assert "lighting_total" in extracted_variables
        assert "sensor.major_appliances_power" in entity_refs
        assert "sensor.water_heater_power" in entity_refs

        # Dependencies should include everything
        expected_deps = {
            "hvac_total",
            "lighting_total",  # Variables
            "sensor.major_appliances_power",
            "sensor.water_heater_power",  # Direct entities
        }
        assert expected_deps.issubset(dependencies)

    def test_pattern_4_complex_mixed_with_input_numbers(self, parser):
        """Test Pattern 4: Complex mixed with input_number entities."""
        # Pattern 4 example: mix with input_number direct references
        formula = (
            "if(net_power > 0, net_power * "
            "input_number.electricity_buy_rate_cents_kwh / 1000, "
            "abs(net_power) * sell_rate / 1000)"
        )

        # Test dependency extraction
        dependencies = parser.extract_dependencies(formula)
        extracted_variables = parser.extract_variables(formula)
        entity_refs = parser.extract_entity_references(formula)

        # Should find variables and input_number direct reference
        assert "net_power" in extracted_variables
        assert "sell_rate" in extracted_variables
        assert "input_number.electricity_buy_rate_cents_kwh" in entity_refs

        # Dependencies should include all references
        expected_deps = {
            "net_power",
            "sell_rate",  # Variables
            "input_number.electricity_buy_rate_cents_kwh",  # Direct entity
        }
        assert expected_deps.issubset(dependencies)

    def test_pattern_5_self_referencing_synthetic_sensors(self, parser):
        """Test Pattern 5: Synthetic sensors referencing other synthetic sensors."""
        # Pattern 5 example: synthetic sensor referencing another synthetic sensor
        # directly
        formula = "max(0, solar_production - sensor.syn2_solar_analytics_solar_export)"

        # Test dependency extraction
        dependencies = parser.extract_dependencies(formula)
        extracted_variables = parser.extract_variables(formula)
        entity_refs = parser.extract_entity_references(formula)

        # Should find variable and synthetic sensor reference
        assert "solar_production" in extracted_variables
        assert "sensor.syn2_solar_analytics_solar_export" in entity_refs

        # Dependencies should include both
        expected_deps = {
            "solar_production",  # Variable
            "sensor.syn2_solar_analytics_solar_export",  # Direct synthetic sensor
        }
        assert expected_deps.issubset(dependencies)

    def test_name_resolver_pattern_1_pure_variables(self, mock_hass):
        """Test NameResolver with Pattern 1: pure variable mapping."""
        variables = {
            "heating": "sensor.circuit_5_power",
            "cooling": "sensor.circuit_6_power",
        }
        resolver = NameResolver(mock_hass, variables)

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Should resolve variables correctly
        assert resolver.resolve_name(MockNode("heating")) == 100.0
        assert resolver.resolve_name(MockNode("cooling")) == 150.0

    def test_name_resolver_pattern_2_pure_direct(self, mock_hass):
        """Test NameResolver with Pattern 2: pure direct entity references."""
        resolver = NameResolver(mock_hass, {})  # No variables

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Should resolve direct entity IDs correctly
        assert resolver.resolve_name(MockNode("sensor.circuit_10_power")) == 50.0
        assert resolver.resolve_name(MockNode("sensor.circuit_11_power")) == 75.0
        assert resolver.resolve_name(MockNode("sensor.circuit_12_power")) == 25.0

    def test_name_resolver_pattern_3_mixed(self, mock_hass):
        """Test NameResolver with Pattern 3: mixed variables and direct entities."""
        variables = {
            "hvac_total": "sensor.syn2_hvac_total_clean_hvac_total",
            "lighting_total": "sensor.syn2_lighting_total_direct_lighting_total",
        }
        resolver = NameResolver(mock_hass, variables)

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Should resolve both variables and direct entity IDs
        assert resolver.resolve_name(MockNode("hvac_total")) == 250.0  # Variable
        assert resolver.resolve_name(MockNode("lighting_total")) == 150.0  # Variable
        assert (
            resolver.resolve_name(MockNode("sensor.major_appliances_power")) == 300.0
        )  # Direct
        assert (
            resolver.resolve_name(MockNode("sensor.water_heater_power")) == 2000.0
        )  # Direct

    def test_name_resolver_pattern_4_complex_mixed_with_input_numbers(self, mock_hass):
        """Test NameResolver with Pattern 4: complex mixed with input_numbers."""
        variables = {
            "net_power": "sensor.span_panel_current_power",
            "sell_rate": "input_number.electricity_sell_rate_cents_kwh",
        }
        resolver = NameResolver(mock_hass, variables)

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Should resolve variables correctly
        assert resolver.resolve_name(MockNode("net_power")) == 2500.0  # Variable
        assert resolver.resolve_name(MockNode("sell_rate")) == 5.0  # Variable
        # Should also resolve direct input_number entity
        assert (
            resolver.resolve_name(
                MockNode("input_number.electricity_buy_rate_cents_kwh")
            )
            == 10.0
        )  # Direct

    def test_name_resolver_pattern_5_self_referencing_synthetic_sensors(
        self, mock_hass
    ):
        """Test NameResolver with Pattern 5: synthetic sensors referencing others."""
        variables = {
            "solar_production": "sensor.span_panel_solar_inverter_instant_power"
        }
        resolver = NameResolver(mock_hass, variables)

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Should resolve variable correctly
        assert resolver.resolve_name(MockNode("solar_production")) == 3000.0  # Variable
        # Should also resolve direct synthetic sensor entity
        assert (
            resolver.resolve_name(MockNode("sensor.syn2_solar_analytics_solar_export"))
            == 500.0
        )  # Direct

    def test_dependency_parser_extract_all_entities_comprehensive(self, parser):
        """Test that dependency parser can extract all entity types from formula."""
        # Complex formula with multiple entity types
        formula = (
            "sensor.power + input_number.rate + climate.thermostat + "
            "switch.pump + binary_sensor.door"
        )

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

    def test_realistic_yaml_formula_simulation(self, parser, mock_hass):
        """Test simulation of realistic YAML formulas from the example config."""

        # Test multiple realistic formulas from the example YAML
        test_cases = [
            {
                "name": "HVAC Pure Variables",
                "formula": "heating + cooling",
                "variables": {
                    "heating": "sensor.circuit_5_power",
                    "cooling": "sensor.circuit_6_power",
                },
                "expected_vars": {"heating", "cooling"},
                "expected_entities": set(),
            },
            {
                "name": "Lighting Pure Direct",
                "formula": (
                    "sensor.circuit_10_power + sensor.circuit_11_power + "
                    "sensor.circuit_12_power"
                ),
                "variables": {},
                "expected_vars": set(),
                "expected_entities": {
                    "sensor.circuit_10_power",
                    "sensor.circuit_11_power",
                    "sensor.circuit_12_power",
                },
            },
            {
                "name": "Mixed Pattern",
                "formula": (
                    "hvac_total + lighting_total + sensor.major_appliances_power + "
                    "sensor.water_heater_power"
                ),
                "variables": {
                    "hvac_total": "sensor.syn2_hvac_total_clean_hvac_total",
                    "lighting_total": (
                        "sensor.syn2_lighting_total_direct_lighting_total"
                    ),
                },
                "expected_vars": {"hvac_total", "lighting_total"},
                "expected_entities": {
                    "sensor.major_appliances_power",
                    "sensor.water_heater_power",
                },
            },
            {
                "name": "Cost Analysis Mixed",
                "formula": (
                    "if(net_power > 0, net_power * "
                    "input_number.electricity_buy_rate_cents_kwh / 1000, "
                    "abs(net_power) * sell_rate / 1000)"
                ),
                "variables": {
                    "net_power": "sensor.span_panel_current_power",
                    "sell_rate": "input_number.electricity_sell_rate_cents_kwh",
                },
                "expected_vars": {"net_power", "sell_rate"},
                "expected_entities": {"input_number.electricity_buy_rate_cents_kwh"},
            },
        ]

        for case in test_cases:
            print(f"\nTesting: {case['name']}")

            # Test dependency parser
            variables = parser.extract_variables(case["formula"])
            entities = parser.extract_entity_references(case["formula"])

            # Verify expectations
            assert case["expected_vars"].issubset(variables), (
                f"Variables mismatch for {case['name']}: "
                f"expected {case['expected_vars']}, got {variables}"
            )
            assert case["expected_entities"].issubset(entities), (
                f"Entities mismatch for {case['name']}: "
                f"expected {case['expected_entities']}, got {entities}"
            )

            # Test name resolver (if we have mock states for the entities)
            resolver = NameResolver(mock_hass, case["variables"])

            # Verify that resolver can handle the pattern
            deps = resolver.get_formula_dependencies(case["formula"])
            assert isinstance(deps, dict)
            assert "entity_ids" in deps
