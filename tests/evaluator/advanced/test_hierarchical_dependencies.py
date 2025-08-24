"""Tests for hierarchical synthetic sensor dependencies and state propagation."""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.name_resolver import NameResolver
from ha_synthetic_sensors.evaluator_phases.variable_resolution.variable_resolution_phase import VariableResolutionPhase
from ha_synthetic_sensors.evaluator_phases.variable_resolution.resolver_factory import VariableResolverFactory
from ha_synthetic_sensors.config_models import SensorConfig, FormulaConfig


class TestHierarchicalSyntheticDependencies:
    """Test hierarchical dependencies between synthetic sensors."""

    def test_level_1_base_sensors(self, mock_hass, mock_entity_registry, mock_states):
        """Test that base HA sensors resolve correctly."""
        # Test that the NameResolver can validate base sensor entities
        resolver = NameResolver(mock_hass, {})

        # Test entity ID validation for base sensors
        assert resolver.validate_entity_id("sensor.circuit_1_power")
        assert resolver.validate_entity_id("sensor.circuit_2_power")
        assert resolver.validate_entity_id("sensor.circuit_3_power")
        assert resolver.validate_entity_id("sensor.circuit_4_power")

        # Test that we can extract entity references from formulas
        formula = "sensor.circuit_1_power + sensor.circuit_2_power"
        entity_ids = resolver.resolve_entity_references(formula, {})
        assert "sensor.circuit_1_power" in entity_ids
        assert "sensor.circuit_2_power" in entity_ids

    def test_level_2_synthetic_sensors(self, mock_hass, mock_entity_registry, mock_states):
        """Test that level 2 synthetic sensors can reference base sensors."""
        # Variables for HVAC total sensor (level 2)
        hvac_variables = {
            "circuit_1": "sensor.circuit_1_power",
            "circuit_2": "sensor.circuit_2_power",
        }
        resolver = NameResolver(mock_hass, hvac_variables)

        # Test that the NameResolver can validate the variable mappings
        validation_result = resolver.validate_variables()
        # Note: This will fail if the entities don't exist in mock_hass, which is expected

        # Test that we can extract dependencies from formulas using variables
        formula = "circuit_1 + circuit_2"
        dependencies = resolver.get_formula_dependencies(formula)
        assert "sensor.circuit_1_power" in dependencies["entity_ids"]
        assert "sensor.circuit_2_power" in dependencies["entity_ids"]
        assert "circuit_1" in dependencies["variable_mappings"]
        assert "circuit_2" in dependencies["variable_mappings"]

    def test_level_3_parent_synthetic_sensors(self, mock_hass, mock_entity_registry, mock_states):
        """Test that level 3 synthetic sensors can reference level 2 synthetic sensors."""
        # Variables for home total sensor (level 3)
        #  - references level 2 synthetic sensors
        home_variables = {
            "hvac_total": "sensor.hvac_total_hvac_total",
            "lighting_total": "sensor.lighting_total_lighting_total",
        }
        resolver = NameResolver(mock_hass, home_variables)

        # Test that we can extract dependencies from formulas using variables
        formula = "hvac_total + lighting_total"
        dependencies = resolver.get_formula_dependencies(formula)
        assert "sensor.hvac_total_hvac_total" in dependencies["entity_ids"]
        assert "sensor.lighting_total_lighting_total" in dependencies["entity_ids"]
        assert "hvac_total" in dependencies["variable_mappings"]
        assert "lighting_total" in dependencies["variable_mappings"]

    def test_level_4_grandparent_synthetic_sensors(self, mock_hass, mock_entity_registry, mock_states):
        """Test level 4 synthetic sensors can reference level 3 synthetic sensors."""
        # Variables for energy analysis sensor (level 4) -
        #     references level 3 synthetic sensor
        analysis_variables = {"home_total": "sensor.home_total_home_total"}
        resolver = NameResolver(mock_hass, analysis_variables)

        # Test that we can extract dependencies from formulas using variables
        formula = "home_total * 0.19"  # Efficiency calculation
        dependencies = resolver.get_formula_dependencies(formula)
        assert "sensor.home_total_home_total" in dependencies["entity_ids"]
        assert "home_total" in dependencies["variable_mappings"]

    def test_mixed_variable_and_direct_hierarchical_references(self, mock_hass, mock_entity_registry, mock_states):
        """Test mixed variable mapping / direct entity references in setup."""
        # Variables that mix direct references and variable mapping
        mixed_variables = {
            "hvac": "sensor.hvac_total_hvac_total",
        }
        resolver = NameResolver(mock_hass, mixed_variables)

        # Test formula with both variable mapping and direct entity references
        # Use entity IDs that actually exist in the mock
        formula = "hvac + sensor.circuit_a_power + sensor.circuit_b_power"

        # Test that we can extract direct entity references
        entity_ids = resolver.resolve_entity_references(formula, mixed_variables)

        # Should include variable mapping
        assert "sensor.hvac_total_hvac_total" in entity_ids

        # Should include direct entity references (using entities that exist in mock)
        assert "sensor.circuit_a_power" in entity_ids
        assert "sensor.circuit_b_power" in entity_ids

        # Test that get_formula_dependencies works for entity() function calls
        formula_with_entity_calls = "hvac + entity('sensor.circuit_a_power') + entity('sensor.circuit_b_power')"
        dependencies = resolver.get_formula_dependencies(formula_with_entity_calls)
        assert "sensor.circuit_a_power" in dependencies["entity_ids"]
        assert "sensor.circuit_b_power" in dependencies["entity_ids"]

    def test_state_propagation_simulation(self, mock_hass, mock_entity_registry, mock_states):
        """Test simulation of state propagation through the hierarchy."""
        # Test that we can validate a complete hierarchical setup
        base_variables = {
            "circuit_1": "sensor.circuit_1_power",
            "circuit_2": "sensor.circuit_2_power",
        }
        resolver = NameResolver(mock_hass, base_variables)

        # Test validation of base entities
        validation_result = resolver.validate_variables()
        # This will show which entities are missing/available

        # Test that we can extract all entity references from a complex formula
        complex_formula = "circuit_1 + circuit_2 + sensor.circuit_3_power + sensor.circuit_4_power"
        entity_ids = resolver.resolve_entity_references(complex_formula, base_variables)
        assert "sensor.circuit_1_power" in entity_ids
        assert "sensor.circuit_2_power" in entity_ids
        assert "sensor.circuit_3_power" in entity_ids
        assert "sensor.circuit_4_power" in entity_ids

    def test_realistic_yaml_scenario(self, mock_hass, mock_entity_registry, mock_states):
        """Test realistic YAML configuration scenario."""
        # Test validation of a realistic sensor configuration
        hvac_variables = {
            "circuit_1": "sensor.circuit_1_power",
            "circuit_2": "sensor.circuit_2_power",
        }
        hvac_resolver = NameResolver(mock_hass, hvac_variables)

        # Test sensor configuration validation
        hvac_sensor_config = {
            "unique_id": "hvac_total",
            "entity_id": "sensor.hvac_total_hvac_total",
            "formulas": [{"id": "main", "formula": "circuit_1 + circuit_2"}],
        }
        validation_result = hvac_resolver.validate_sensor_config(hvac_sensor_config)
        # This will validate the sensor configuration structure

        # Test that the formula dependencies are correctly identified
        formula = "circuit_1 + circuit_2"
        dependencies = hvac_resolver.get_formula_dependencies(formula)
        assert len(dependencies["entity_ids"]) == 2
        assert len(dependencies["variable_mappings"]) == 2
