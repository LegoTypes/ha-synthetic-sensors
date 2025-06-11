"""Tests for hierarchical synthetic sensor dependencies and state propagation."""

from unittest.mock import MagicMock

import pytest

from ha_synthetic_sensors.name_resolver import NameResolver


class TestHierarchicalSyntheticDependencies:
    """Test hierarchical dependencies between synthetic sensors."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance with hierarchical sensor states."""
        hass = MagicMock()
        hass.states = MagicMock()

        # Mock hierarchical sensor state chain
        def mock_get_state(entity_id):
            state_values = {
                # Level 1: Base sensors (real HA entities)
                "sensor.circuit_1_power": "100.0",
                "sensor.circuit_2_power": "150.0",
                "sensor.circuit_3_power": "75.0",
                "sensor.circuit_4_power": "125.0",
                # Level 2: Intermediate synthetic sensors
                # circuit_1 + circuit_2
                "sensor.syn2_hvac_total_hvac_total": "250.0",
                # circuit_3 + circuit_4
                "sensor.syn2_lighting_total_lighting_total": "200.0",
                # Level 3: Parent synthetic sensor
                # hvac_total + lighting_total
                "sensor.syn2_home_total_home_total": "450.0",
                # Level 4: Grandparent synthetic sensor
                # home_total * 0.19
                "sensor.syn2_energy_analysis_efficiency": "85.5",
            }

            if entity_id in state_values:
                mock_state = MagicMock()
                mock_state.state = state_values[entity_id]
                return mock_state
            return None

        hass.states.get.side_effect = mock_get_state
        return hass

    def test_level_1_base_sensors(self, mock_hass):
        """Test that base HA sensors resolve correctly."""
        resolver = NameResolver(mock_hass, {})

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Test direct entity ID resolution for base sensors
        assert resolver.resolve_name(MockNode("sensor.circuit_1_power")) == 100.0
        assert resolver.resolve_name(MockNode("sensor.circuit_2_power")) == 150.0
        assert resolver.resolve_name(MockNode("sensor.circuit_3_power")) == 75.0
        assert resolver.resolve_name(MockNode("sensor.circuit_4_power")) == 125.0

    def test_level_2_synthetic_sensors(self, mock_hass):
        """Test that level 2 synthetic sensors can reference base sensors."""
        # Variables for HVAC total sensor (level 2)
        hvac_variables = {
            "circuit_1": "sensor.circuit_1_power",
            "circuit_2": "sensor.circuit_2_power",
        }
        resolver = NameResolver(mock_hass, hvac_variables)

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Test that synthetic sensor can reference base sensors via variables
        assert resolver.resolve_name(MockNode("circuit_1")) == 100.0
        assert resolver.resolve_name(MockNode("circuit_2")) == 150.0

        # Test that the synthetic sensor itself is a valid entity
        assert resolver.resolve_name(MockNode("sensor.syn2_hvac_total_hvac_total")) == 250.0

    def test_level_3_parent_synthetic_sensors(self, mock_hass):
        """Test that level 3 synthetic sensors can reference level 2 synsensors."""
        # Variables for home total sensor (level 3)
        #  - references level 2 synthetic sensors
        home_variables = {
            "hvac_total": "sensor.syn2_hvac_total_hvac_total",
            "lighting_total": "sensor.syn2_lighting_total_lighting_total",
        }
        resolver = NameResolver(mock_hass, home_variables)

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Test that parent synthetic sensor can reference child synthetic sensors
        assert resolver.resolve_name(MockNode("hvac_total")) == 250.0
        assert resolver.resolve_name(MockNode("lighting_total")) == 200.0

        # Test that the parent synthetic sensor itself is available
        assert resolver.resolve_name(MockNode("sensor.syn2_home_total_home_total")) == 450.0

    def test_level_4_grandparent_synthetic_sensors(self, mock_hass):
        """Test level 4 synthetic sensors can reference level 3 synthetic sensors."""
        # Variables for energy analysis sensor (level 4) -
        #     references level 3 synthetic sensor
        analysis_variables = {"home_total": "sensor.syn2_home_total_home_total"}
        resolver = NameResolver(mock_hass, analysis_variables)

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Test that grandparent synthetic sensor can reference parent synthetic sensor
        assert resolver.resolve_name(MockNode("home_total")) == 450.0

        # Test that the grandparent synthetic sensor itself is available
        assert resolver.resolve_name(MockNode("sensor.syn2_energy_analysis_efficiency")) == 85.5

    def test_mixed_variable_and_direct_hierarchical_references(self, mock_hass):
        """Test mixed variable mapping / direct entity references in setup."""
        # Variables that mix direct references and variable mapping
        mixed_variables = {
            "hvac": "sensor.syn2_hvac_total_hvac_total",  # Variable mapping to syn2
        }
        resolver = NameResolver(mock_hass, mixed_variables)

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Test variable mapping to synthetic sensor
        assert resolver.resolve_name(MockNode("hvac")) == 250.0

        # Test direct entity ID reference to synthetic sensor (no variable mapping)
        assert resolver.resolve_name(MockNode("sensor.syn2_lighting_total_lighting_total")) == 200.0

        # Test direct entity ID reference to grandparent synthetic sensor
        assert resolver.resolve_name(MockNode("sensor.syn2_energy_analysis_efficiency")) == 85.5

        # Test direct entity ID reference to base sensor
        assert resolver.resolve_name(MockNode("sensor.circuit_1_power")) == 100.0

    def test_state_propagation_simulation(self, mock_hass):
        """Test simulated state propagation through hierarchical chain."""
        # This simulates what happens when state changes propagate
        # In real implementation, this would be handled by Home Assistant's
        # state management

        # Start with updated base sensor values
        def mock_get_updated_state(entity_id):
            updated_state_values = {
                # Level 1: Updated base sensors
                "sensor.circuit_1_power": "120.0",  # Changed from 100.0
                "sensor.circuit_2_power": "150.0",  # Same
                "sensor.circuit_3_power": "80.0",  # Changed from 75.0
                "sensor.circuit_4_power": "125.0",  # Same
                # Level 2: Updated synthetic sensors (would be recalculated)
                "sensor.syn2_hvac_total_hvac_total": "270.0",  # 120 + 150
                "sensor.syn2_lighting_total_lighting_total": "205.0",  # 80 + 125
                # Level 3: Updated parent synthetic sensor (would be recalculated)
                "sensor.syn2_home_total_home_total": "475.0",  # 270 + 205
                # Level 4: Updated grandparent synthetic sensor (would be recalculated)
                "sensor.syn2_energy_analysis_efficiency": "90.25",  # 475 * 0.19
            }

            if entity_id in updated_state_values:
                mock_state = MagicMock()
                mock_state.state = updated_state_values[entity_id]
                return mock_state
            return None

        # Update mock to return new states
        mock_hass.states.get.side_effect = mock_get_updated_state

        # Test that all levels show updated values
        resolver = NameResolver(mock_hass, {})

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Level 1: Base sensors
        assert resolver.resolve_name(MockNode("sensor.circuit_1_power")) == 120.0
        assert resolver.resolve_name(MockNode("sensor.circuit_3_power")) == 80.0

        # Level 2: Intermediate synthetic sensors
        assert resolver.resolve_name(MockNode("sensor.syn2_hvac_total_hvac_total")) == 270.0
        assert resolver.resolve_name(MockNode("sensor.syn2_lighting_total_lighting_total")) == 205.0

        # Level 3: Parent synthetic sensor
        assert resolver.resolve_name(MockNode("sensor.syn2_home_total_home_total")) == 475.0

        # Level 4: Grandparent synthetic sensor
        assert resolver.resolve_name(MockNode("sensor.syn2_energy_analysis_efficiency")) == 90.25

    def test_realistic_yaml_scenario(self, mock_hass):
        """Test a realistic YAML configuration scenario."""
        # This represents what would be in a real YAML config

        # Level 2 sensor: HVAC Total
        # formula: "circuit_1 + circuit_2"
        # variables: {"circuit_1": "sensor.circuit_1_power",
        #     "circuit_2": "sensor.circuit_2_power"}
        hvac_resolver = NameResolver(
            mock_hass,
            {
                "circuit_1": "sensor.circuit_1_power",
                "circuit_2": "sensor.circuit_2_power",
            },
        )

        # Level 3 sensor: Home Total
        # formula: "hvac_total + lighting_total"
        # variables: {"hvac_total": "sensor.syn2_hvac_total_hvac_total",
        #     "lighting_total": "sensor.syn2_lighting_total_lighting_total"}
        home_resolver = NameResolver(
            mock_hass,
            {
                "hvac_total": "sensor.syn2_hvac_total_hvac_total",
                "lighting_total": "sensor.syn2_lighting_total_lighting_total",
            },
        )

        # Level 4 sensor: Energy Analysis
        # formula: "home_total * 0.19"
        #     (or could be direct: "sensor.syn2_home_total_home_total * 0.19")
        analysis_resolver = NameResolver(mock_hass, {"home_total": "sensor.syn2_home_total_home_total"})

        class MockNode:
            def __init__(self, name):
                self.id = name

        # Test Level 2: HVAC sensor can resolve base sensors
        assert hvac_resolver.resolve_name(MockNode("circuit_1")) == 100.0
        assert hvac_resolver.resolve_name(MockNode("circuit_2")) == 150.0

        # Test Level 3: Home sensor can resolve Level 2 synthetic sensors
        assert home_resolver.resolve_name(MockNode("hvac_total")) == 250.0
        assert home_resolver.resolve_name(MockNode("lighting_total")) == 200.0

        # Test Level 4: Analysis sensor can resolve Level 3 synthetic sensor
        assert analysis_resolver.resolve_name(MockNode("home_total")) == 450.0

        # Test that any level can also use direct entity ID references
        assert hvac_resolver.resolve_name(MockNode("sensor.circuit_3_power")) == 75.0
        assert home_resolver.resolve_name(MockNode("sensor.syn2_energy_analysis_efficiency")) == 85.5
        assert analysis_resolver.resolve_name(MockNode("sensor.circuit_1_power")) == 100.0
