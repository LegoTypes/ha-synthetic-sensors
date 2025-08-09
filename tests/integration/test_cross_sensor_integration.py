"""Integration test for cross-sensor reference resolution with attributes."""

import os
import pytest
from unittest.mock import AsyncMock, patch
import yaml

from ha_synthetic_sensors.storage_manager import StorageManager


class TestCrossSensorIntegration:
    """Integration test for cross-sensor reference resolution in formulas and attributes."""

    @pytest.fixture
    def test_yaml_path(self):
        """Path to the test YAML fixture."""
        return "tests/fixtures/integration/cross_sensor_integration_test.yaml"

    @pytest.fixture
    def expected_yaml_path(self):
        """Path to the expected YAML fixture."""
        return "tests/fixtures/integration/cross_sensor_integration_expected.yaml"

    @pytest.fixture
    def test_yaml_content(self, test_yaml_path):
        """Load the test YAML content."""
        with open(test_yaml_path, "r", encoding="utf-8") as f:
            return f.read()

    @pytest.fixture
    def expected_yaml_content(self, expected_yaml_path):
        """Load the expected YAML content."""
        with open(expected_yaml_path, "r", encoding="utf-8") as f:
            return f.read()

    async def test_cross_sensor_integration_with_attributes(
        self, mock_hass, mock_entity_registry, mock_states, test_yaml_content, expected_yaml_content
    ):
        """Test complete cross-sensor reference resolution including attributes and entity ID collision handling."""

        # Create storage manager with mocked Store
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None  # Empty storage initially
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create a sensor set for integration testing
            sensor_set_id = "cross_sensor_integration_test"

            # Check if sensor set already exists and delete if it does
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Import YAML with cross-sensor references - this should trigger resolution
            result = await storage_manager.async_from_yaml(yaml_content=test_yaml_content, sensor_set_id=sensor_set_id)

            # Verify import succeeded
            assert result["sensors_imported"] == 2, f"Expected 2 sensors, got {result['sensors_imported']}"
            assert len(result["sensor_unique_ids"]) == 2

            # Get the stored sensors
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 2

            # Find the base power sensor
            base_power_sensor = None
            efficiency_calc_sensor = None
            for sensor in sensors:
                if sensor.unique_id == "roundtrip_base_power_sensor":
                    base_power_sensor = sensor
                elif sensor.unique_id == "roundtrip_efficiency_calc":
                    efficiency_calc_sensor = sensor

            assert base_power_sensor is not None, "roundtrip_base_power_sensor should exist"
            assert efficiency_calc_sensor is not None, "roundtrip_efficiency_calc sensor should exist"

            # Both sensors should have entity IDs assigned (may or may not have collision suffixes in test)
            assert base_power_sensor.entity_id is not None, "Base power sensor should have entity_id assigned"
            assert efficiency_calc_sensor.entity_id is not None, "Efficiency calc sensor should have entity_id assigned"

            # Verify cross-sensor reference resolution in efficiency_calc sensor
            efficiency_formula = efficiency_calc_sensor.formulas[0].formula

            # The formula should reference the base power sensor by entity ID
            assert base_power_sensor.entity_id in efficiency_formula, (
                f"Efficiency calc formula should reference base power sensor by entity ID: {efficiency_formula}"
            )

            # Verify self-reference resolution using state token
            base_power_attributes = base_power_sensor.formulas[0].attributes
            print(f"📋 Base power sensor attributes: {base_power_attributes}")

            # Check that self-references use 'state' token
            daily_power_attr = base_power_attributes.get("daily_power")
            assert daily_power_attr is not None, "daily_power attribute should exist"

            # With structure preservation fix, attributes should be dictionaries with 'formula' key
            assert isinstance(daily_power_attr, dict), f"daily_power should be a formula dict: {daily_power_attr}"
            assert "formula" in daily_power_attr, f"daily_power should have 'formula' key: {daily_power_attr}"

            # Check that the formula uses 'state' token (after self-reference resolution)
            formula_value = daily_power_attr["formula"]
            assert "state" in formula_value, f"daily_power formula should use 'state' token: {formula_value}"
            assert "roundtrip_base_power_sensor" not in formula_value, (
                f"daily_power formula should not use sensor key: {formula_value}"
            )

            # Verify variable resolution
            base_power_variables = base_power_sensor.formulas[0].variables

            # Self-reference in variable should be resolved to 'state'
            my_ref_value = base_power_variables.get("my_ref")
            assert my_ref_value == "state", f"Self-reference variable should be 'state': {my_ref_value}"

            # Export the processed YAML and verify round-trip
            exported_yaml = await storage_manager.async_export_yaml(sensor_set_id)

            # Parse exported YAML and verify it matches expected structure
            import yaml

            exported_data = yaml.safe_load(exported_yaml)
            expected_data = yaml.safe_load(expected_yaml_content)

            # Verify the exported structure matches expected
            assert "sensors" in exported_data, "Exported YAML should contain sensors"
            assert len(exported_data["sensors"]) == 2, f"Expected 2 sensors, got {len(exported_data['sensors'])}"

            # Verify base_power_sensor structure
            base_power_exported = exported_data["sensors"]["roundtrip_base_power_sensor"]
            base_power_expected = expected_data["sensors"]["roundtrip_base_power_sensor"]

            # Entity ID should be updated with HA-assigned value
            assert base_power_exported["entity_id"] == base_power_sensor.entity_id, (
                f"Exported entity_id should match HA-assigned value: {base_power_exported['entity_id']} vs {base_power_sensor.entity_id}"
            )

            # Main formula should use 'state' token for self-reference
            assert base_power_exported["formula"] == "state * 1.0", (
                f"Main formula should use 'state' token: {base_power_exported['formula']}"
            )

            # Variables should have self-references resolved to 'state'
            assert base_power_exported["variables"]["my_ref"] == "state", (
                f"Self-reference variable should be 'state': {base_power_exported['variables']['my_ref']}"
            )

            # Attributes should use 'state' token for self-references
            daily_power_formula = base_power_exported["attributes"]["daily_power"]["formula"]
            assert daily_power_formula == "state * 24", f"Daily power attribute should use 'state' token: {daily_power_formula}"

            # Verify simple string attribute remains unchanged
            tabs_info = base_power_exported["attributes"]["tabs_info"]
            assert tabs_info == "tabs [30]", f"Simple string attribute should remain unchanged: {tabs_info}"

            # Verify another string attribute with tabs notation remains unchanged
            tabs = base_power_exported["attributes"]["tabs"]
            assert tabs == "tabs [30,32]", f"Tabs attribute should remain unchanged: {tabs}"

            # Verify efficiency_calc sensor structure
            efficiency_exported = exported_data["sensors"]["roundtrip_efficiency_calc"]
            efficiency_expected = expected_data["sensors"]["roundtrip_efficiency_calc"]

            # Entity ID should be updated with HA-assigned value
            assert efficiency_exported["entity_id"] == efficiency_calc_sensor.entity_id, (
                f"Exported entity_id should match HA-assigned value: {efficiency_exported['entity_id']} vs {efficiency_calc_sensor.entity_id}"
            )

            # Formula should reference base power sensor by entity ID
            assert base_power_sensor.entity_id in efficiency_exported["formula"], (
                f"Formula should reference base power sensor by entity ID: {efficiency_exported['formula']}"
            )

            # Variables should reference base power sensor by entity ID
            assert efficiency_exported["variables"]["other_power"] == base_power_sensor.entity_id, (
                f"Cross-sensor variable should reference entity ID: {efficiency_exported['variables']['other_power']}"
            )

            # Attributes should reference base power sensor by entity ID
            power_ratio_formula = efficiency_exported["attributes"]["power_ratio"]["formula"]
            assert base_power_sensor.entity_id in power_ratio_formula, (
                f"Power ratio attribute should reference base power sensor by entity ID: {power_ratio_formula}"
            )

            # Self-references in attributes should use 'state' token
            daily_efficiency_formula = efficiency_exported["attributes"]["daily_efficiency"]["formula"]
            assert daily_efficiency_formula == "state * 24", (
                f"Daily efficiency attribute should use 'state' token: {daily_efficiency_formula}"
            )

            # Cleanup: Delete the sensor set
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)
                print(f"🧹 Cleaned up sensor set: {sensor_set_id}")
