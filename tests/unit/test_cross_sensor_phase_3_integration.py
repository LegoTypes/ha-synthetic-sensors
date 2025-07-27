"""Integration tests for Phase 3 cross-sensor reference resolution."""

import pytest

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.cross_sensor_reference_manager import CrossSensorReferenceManager


class TestCrossSensorPhase3Integration:
    """Test Phase 3 integration with common registry fixture."""

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a ConfigManager instance."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def yaml_with_parent_reference(self):
        """YAML with parent sensor reference in attribute - uses common fixture entities."""
        return """
sensors:
  simple_parent_reference:
    entity_id: sensor.span_panel_instantaneous_power  # Uses common fixture entity
    formula: state * 2
    attributes:
      doubled_state:
        formula: simple_parent_reference * 3  # References parent sensor
        metadata:
          unit_of_measurement: W
    metadata:
      unit_of_measurement: W
      device_class: power
"""

    @pytest.fixture
    def yaml_with_complex_references(self):
        """YAML with complex cross-sensor references - uses common fixture entities."""
        return """
sensors:
  base_power:
    entity_id: sensor.span_panel_instantaneous_power  # Uses common fixture entity
    formula: state * 1.0
    metadata:
      unit_of_measurement: W
      device_class: power

  solar_power:
    entity_id: sensor.solar_power  # Uses common fixture entity
    formula: state * 0.8
    metadata:
      unit_of_measurement: W
      device_class: power

  total_power:
    formula: base_power + solar_power  # References other sensors
    attributes:
      efficiency:
        formula: solar_power / total_power * 100  # Multiple references
        metadata:
          unit_of_measurement: "%"
    metadata:
      unit_of_measurement: W
      device_class: power
"""

    async def test_phase_3_simple_parent_reference(self, mock_hass, config_manager, yaml_with_parent_reference):
        """Test complete Phase 3 flow with simple parent reference."""
        # Phase 1: Load config and detect references
        config = config_manager.load_from_yaml(yaml_with_parent_reference)

        assert hasattr(config, "cross_sensor_references")
        assert "simple_parent_reference" in config.cross_sensor_references
        assert "simple_parent_reference" in config.cross_sensor_references["simple_parent_reference"]

        # Phase 2: Initialize reference manager
        ref_manager = CrossSensorReferenceManager(mock_hass)
        ref_manager.initialize_from_config(config.cross_sensor_references, config)

        # Verify Phase 2 setup
        assert not ref_manager.are_all_registrations_complete()
        assert ref_manager.is_registration_pending("simple_parent_reference")

        # Phase 2: Simulate entity ID capture
        await ref_manager.register_sensor_entity_id("simple_parent_reference", "sensor.simple_parent_reference_2")

        # Phase 3: Should complete automatically
        assert ref_manager.are_all_registrations_complete()
        assert ref_manager.is_phase_3_complete()

        # Verify Phase 3 results
        resolved_config = ref_manager.get_resolved_config()
        assert resolved_config is not None

        sensor = resolved_config.sensors[0]

        # Main formula should be unchanged
        main_formula = next(f for f in sensor.formulas if f.id == "simple_parent_reference")
        assert main_formula.formula == "state * 2"

        # Attribute formula should have resolved self-reference to state token
        attr_formula = next(f for f in sensor.formulas if f.id == "simple_parent_reference_doubled_state")
        assert attr_formula.formula == "state * 3"

    async def test_phase_3_complex_references(self, mock_hass, config_manager, yaml_with_complex_references):
        """Test complete Phase 3 flow with complex cross-sensor references."""
        # Phase 1: Load config and detect references
        config = config_manager.load_from_yaml(yaml_with_complex_references)

        # Verify cross-sensor references detected
        assert "total_power" in config.cross_sensor_references
        total_refs = config.cross_sensor_references["total_power"]
        assert "base_power" in total_refs
        assert "solar_power" in total_refs
        assert "total_power" in total_refs  # Self-reference in attribute

        # Phase 2: Initialize reference manager
        ref_manager = CrossSensorReferenceManager(mock_hass)
        ref_manager.initialize_from_config(config.cross_sensor_references, config)

        # Verify multiple sensors need registration
        status = ref_manager.get_registration_status()
        assert status["pending_count"] == 3
        assert set(status["pending_sensors"]) == {"base_power", "solar_power", "total_power"}

        # Phase 2: Register entity IDs one by one
        await ref_manager.register_sensor_entity_id("base_power", "sensor.base_power_2")
        assert not ref_manager.are_all_registrations_complete()

        await ref_manager.register_sensor_entity_id("solar_power", "sensor.solar_power_3")
        assert not ref_manager.are_all_registrations_complete()

        await ref_manager.register_sensor_entity_id("total_power", "sensor.total_power_4")

        # Phase 3: Should complete automatically
        assert ref_manager.are_all_registrations_complete()
        assert ref_manager.is_phase_3_complete()

        # Verify Phase 3 results
        resolved_config = ref_manager.get_resolved_config()
        assert resolved_config is not None
        assert len(resolved_config.sensors) == 3

        # Check individual sensor resolutions
        sensors_by_id = {s.unique_id: s for s in resolved_config.sensors}

        # Base power - no references to resolve
        base_sensor = sensors_by_id["base_power"]
        base_formula = base_sensor.formulas[0]
        assert base_formula.formula == "state * 1.0"

        # Solar power - no references to resolve
        solar_sensor = sensors_by_id["solar_power"]
        solar_formula = solar_sensor.formulas[0]
        assert solar_formula.formula == "state * 0.8"

        # Total power - main formula should have resolved references
        total_sensor = sensors_by_id["total_power"]
        total_main_formula = next(f for f in total_sensor.formulas if f.id == "total_power")
        assert total_main_formula.formula == "sensor.base_power_2 + sensor.solar_power_3"

        # Total power - attribute formula should have resolved references
        # Note: total_power reference in attribute is a self-reference, so it becomes 'state'
        total_attr_formula = next(f for f in total_sensor.formulas if f.id == "total_power_efficiency")
        assert total_attr_formula.formula == "sensor.solar_power_3 / state * 100"

    async def test_phase_3_with_no_references(self, mock_hass, config_manager):
        """Test that Phase 3 handles configs with no cross-sensor references."""
        yaml_no_refs = """
sensors:
  independent_sensor:
    entity_id: sensor.span_panel_instantaneous_power
    formula: state * 2.5
    metadata:
      unit_of_measurement: W
      device_class: power
"""

        # Phase 1: Load config
        config = config_manager.load_from_yaml(yaml_no_refs)

        # Should have no cross-sensor references
        assert not config.cross_sensor_references

        # Phase 2: Initialize reference manager
        ref_manager = CrossSensorReferenceManager(mock_hass)
        ref_manager.initialize_from_config(config.cross_sensor_references, config)

        # Should complete immediately (no registrations needed)
        assert ref_manager.are_all_registrations_complete()

        # Phase 3 should not run (no references to resolve)
        assert not ref_manager.is_phase_3_complete()

    async def test_phase_3_error_handling(self, mock_hass):
        """Test Phase 3 error handling scenarios."""
        ref_manager = CrossSensorReferenceManager(mock_hass)

        # Initialize without original config
        ref_manager.initialize_from_config({"sensor_a": {"sensor_b"}})

        # Register entity ID to trigger completion
        await ref_manager.register_sensor_entity_id("sensor_a", "sensor.sensor_a_2")
        await ref_manager.register_sensor_entity_id("sensor_b", "sensor.sensor_b_3")

        # Phase 3 should not complete (no original config)
        assert ref_manager.are_all_registrations_complete()
        assert not ref_manager.is_phase_3_complete()
        assert ref_manager.get_resolved_config() is None

    def test_replacement_summary_generation(self, mock_hass, config_manager, yaml_with_complex_references):
        """Test that replacement summary correctly identifies what would be changed."""
        # Load config
        config = config_manager.load_from_yaml(yaml_with_complex_references)

        # Create reference manager
        ref_manager = CrossSensorReferenceManager(mock_hass)
        ref_manager.initialize_from_config(config.cross_sensor_references, config)

        # Test replacement summary before resolution
        entity_mappings = {
            "base_power": "sensor.base_power_2",
            "solar_power": "sensor.solar_power_3",
            "total_power": "sensor.total_power_4",
        }

        summary = ref_manager._formula_resolver.get_replacement_summary(config, entity_mappings)

        # Should identify total_power formulas that need replacement
        assert "total_power" in summary
        total_summary = summary["total_power"]

        # Main formula replacement
        assert "total_power" in total_summary
        main_replacement = total_summary["total_power"]
        assert main_replacement["original_formula"] == "base_power + solar_power"
        assert "base_power" in main_replacement["replacements"]
        assert "solar_power" in main_replacement["replacements"]

        # Attribute formula replacement
        assert "total_power_efficiency" in total_summary
        attr_replacement = total_summary["total_power_efficiency"]
        assert attr_replacement["original_formula"] == "solar_power / total_power * 100"
        assert "solar_power" in attr_replacement["replacements"]
        assert "total_power" in attr_replacement["replacements"]
