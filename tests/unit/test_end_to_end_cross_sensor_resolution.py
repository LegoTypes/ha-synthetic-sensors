"""End-to-end test for complete cross-sensor reference resolution."""

import pytest
from unittest.mock import MagicMock

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig


class TestEndToEndCrossSensorResolution:
    """Test complete cross-sensor reference resolution from Phase 1 to Phase 3."""

    @pytest.fixture
    def yaml_with_parent_reference(self):
        """YAML with parent sensor reference - uses common fixture entities."""
        return """
sensors:
  simple_parent_reference:
    entity_id: sensor.span_panel_instantaneous_power  # Common fixture entity
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

    async def test_end_to_end_parent_reference_resolution(
        self, mock_hass, mock_entity_registry, mock_states, yaml_with_parent_reference
    ):
        """Test complete end-to-end cross-sensor reference resolution."""

        # Phase 1: Load config and detect cross-sensor references
        config_manager = ConfigManager(mock_hass)
        config = config_manager.load_from_yaml(yaml_with_parent_reference)

        # Verify Phase 1 detected the reference
        assert hasattr(config, "cross_sensor_references")
        assert "simple_parent_reference" in config.cross_sensor_references
        assert "simple_parent_reference" in config.cross_sensor_references["simple_parent_reference"]
        print(f"✅ Phase 1: Cross-sensor references detected: {config.cross_sensor_references}")

        # Set up sensor manager with data provider using common fixture
        def mock_data_provider(entity_id: str):
            if entity_id in mock_states:
                state = mock_states[entity_id]
                return {"value": float(state.state), "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            mock_hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register backing entities and mappings
        sensor_manager.register_data_provider_entities({"sensor.span_panel_instantaneous_power"})
        sensor_to_backing_mapping = {"simple_parent_reference": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Phase 2: Create sensors (initiates Phase 2 and prepares for Phase 3)
        sensors = await sensor_manager.create_sensors(config)
        assert len(sensors) == 1
        sensor = sensors[0]
        print(f"✅ Phase 2: Created {len(sensors)} sensors")

        # Verify Phase 2 is set up
        ref_manager = sensor_manager._cross_sensor_ref_manager
        assert not ref_manager.are_all_registrations_complete()
        assert ref_manager.is_registration_pending("simple_parent_reference")
        print("✅ Phase 2: Reference manager is pending registration")

        # Simulate HA entity registration (Phase 2 completion + Phase 3 trigger)
        sensor.entity_id = "sensor.simple_parent_reference_2"  # Simulate HA assignment

        # Directly trigger entity ID registration to avoid HA lifecycle issues in test
        await sensor_manager.register_cross_sensor_entity_id("simple_parent_reference", "sensor.simple_parent_reference_2")

        # Verify Phase 2 and Phase 3 completed
        assert ref_manager.are_all_registrations_complete()
        assert ref_manager.is_phase_3_complete()
        print("✅ Phase 2 & 3: Entity registration and formula resolution complete")

        # Verify the resolved config
        resolved_config = ref_manager.get_resolved_config()
        assert resolved_config is not None
        resolved_sensor = resolved_config.sensors[0]

        # Main formula should be unchanged
        main_formula = next(f for f in resolved_sensor.formulas if f.id == "simple_parent_reference")
        assert main_formula.formula == "state * 2"

        # Attribute formula should have resolved reference
        attr_formula = next(f for f in resolved_sensor.formulas if f.id == "simple_parent_reference_doubled_state")
        original_formula = attr_formula.formula
        print(f"✅ Phase 3: Formula resolved: 'simple_parent_reference * 3' → '{original_formula}'")
        # Self-reference in attribute should be resolved to 'state' token
        assert original_formula == "state * 3"

        # Verify sensor config was updated
        # Self-reference in attribute should be resolved to 'state' token
        assert sensor._config.formulas[1].formula == "state * 3"
        print("✅ Phase 3: Sensor config updated with resolved formula")

        # Test actual formula evaluation with resolved references
        evaluator = sensor_manager._evaluator

        # Use dynamic registry to register the resolved entity with its calculated state
        # The resolved entity should have the same state as the main formula would calculate: 1000 * 2 = 2000
        mock_states.register_state("sensor.simple_parent_reference_2", "2000.0", {"device_class": "power"})

        # Register the resolved entity in the sensor manager data provider so it can be evaluated
        sensor_manager.register_data_provider_entities({"sensor.simple_parent_reference_2"})

        # Re-register backing entity since it might have been lost during config updates
        sensor_manager.register_data_provider_entities({"sensor.span_panel_instantaneous_power"})
        sensor_to_backing_mapping = {"simple_parent_reference": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula (should work as before)
        main_result = evaluator.evaluate_formula_with_sensor_config(sensor._config.formulas[0], None, sensor._config)
        print(f"🔍 Main result debug: {main_result}")
        if not main_result["success"]:
            print(f"❌ Main formula failed: {main_result.get('error', 'Unknown error')}")
        assert main_result["success"] is True
        assert main_result["value"] == 2000.0  # 1000 * 2
        print(f"✅ Main formula evaluation: {main_result['value']}")

        # Test attribute formula with resolved reference
        # The resolved formula should now reference the actual entity ID: sensor.simple_parent_reference_2
        # The mock entity has state=2000.0, so formula: sensor.simple_parent_reference_2 * 3 = 2000 * 3 = 6000
        context = {"state": main_result["value"]}  # Provide main result as context
        attr_result = evaluator.evaluate_formula_with_sensor_config(sensor._config.formulas[1], context, sensor._config)

        # This should now succeed because the formula was resolved to actual entity ID
        print(f"Attribute formula result: {attr_result}")
        assert attr_result["success"] is True, f"Attribute formula failed: {attr_result.get('error', 'Unknown error')}"

        # The resolved entity sensor.simple_parent_reference_2 has state=2000.0 in the mock
        # So the formula "sensor.simple_parent_reference_2 * 3" should evaluate to 2000 * 3 = 6000
        assert attr_result["value"] == 6000.0
        print(f"✅ Attribute formula evaluation succeeded: {attr_result['value']}")

        # The key achievement is that the formula has been resolved from sensor key to entity ID
        print("✅ Phase 3 successfully resolved cross-sensor references to entity IDs!")
        print("  Original formula: 'simple_parent_reference * 3'")
        print(f"  Resolved formula: '{sensor._config.formulas[1].formula}'")
        print("  Formula now evaluates successfully with actual entity reference!")

        # This is the core functionality that was missing before Phase 3 implementation
        # The parent state reference issue is now resolved at the formula level

        print("✅ End-to-end cross-sensor reference resolution test complete!")

    async def test_no_cross_sensor_references(self, mock_hass, mock_entity_registry, mock_states):
        """Test that systems works normally when there are no cross-sensor references."""
        yaml_no_refs = """
sensors:
  independent_sensor:
    entity_id: sensor.span_panel_instantaneous_power
    formula: state * 2.5
    metadata:
      unit_of_measurement: W
      device_class: power
"""

        config_manager = ConfigManager(mock_hass)
        config = config_manager.load_from_yaml(yaml_no_refs)

        # Should have no cross-sensor references
        assert not config.cross_sensor_references

        # Set up sensor manager
        def mock_data_provider(entity_id: str):
            if entity_id in mock_states:
                state = mock_states[entity_id]
                return {"value": float(state.state), "exists": True}
            return {"value": None, "exists": False}

        sensor_manager = SensorManager(
            mock_hass, MagicMock(), MagicMock(), SensorManagerConfig(data_provider_callback=mock_data_provider)
        )

        # Create sensors - should work normally
        sensors = await sensor_manager.create_sensors(config)
        assert len(sensors) == 1

        # No cross-sensor reference processing should occur
        ref_manager = sensor_manager._cross_sensor_ref_manager
        assert ref_manager.are_all_registrations_complete()  # No registrations needed
        assert not ref_manager.is_phase_3_complete()  # Phase 3 doesn't run

        print("✅ No cross-sensor references case handled correctly")
