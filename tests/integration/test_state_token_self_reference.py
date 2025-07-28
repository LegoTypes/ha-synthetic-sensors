"""Integration test for state token self-reference replacement strategy."""

import os
import pytest
from unittest.mock import AsyncMock, patch
import yaml

from ha_synthetic_sensors.storage_manager import StorageManager


class TestStateTokenSelfReference:
    """Integration test for state token replacement strategy in self-references."""

    @pytest.fixture
    def test_yaml_path(self):
        """Path to the test YAML fixture."""
        return "tests/fixtures/integration/state_token_self_reference_test.yaml"

    @pytest.fixture
    def expected_yaml_path(self):
        """Path to the expected YAML fixture."""
        return "tests/fixtures/integration/state_token_self_reference_expected.yaml"

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

    async def test_state_token_self_reference_replacement(
        self, mock_hass, mock_states, test_yaml_content, expected_yaml_content
    ):
        """Test that self-references in attributes use state token instead of entity_id."""

        # Create storage manager with mocked Store
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None  # Empty storage initially
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create a sensor set for integration testing
            sensor_set_id = "state_token_self_reference_test"

            # Check if sensor set already exists and delete if it does
            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            print(f"📋 Loading test YAML from fixture...")
            print(f"📋 Test YAML content:\n{test_yaml_content}")

            # Import YAML with self-references - this should trigger state token replacement
            result = await storage_manager.async_from_yaml(yaml_content=test_yaml_content, sensor_set_id=sensor_set_id)

            print(f"📊 Import result: {result}")
            print(f"📝 Sensors imported: {result['sensors_imported']}")
            print(f"📝 Sensor unique IDs: {result['sensor_unique_ids']}")

            # Verify import succeeded
            assert result["sensors_imported"] == 2, f"Expected 2 sensors, got {result['sensors_imported']}"
            assert len(result["sensor_unique_ids"]) == 2

            # Get the stored sensors
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 2

            # Find the main sensor with self-references
            main_sensor = None
            for sensor in sensors:
                if sensor.unique_id == "test_power_analyzer":
                    main_sensor = sensor
                    break

            assert main_sensor is not None, "test_power_analyzer sensor should exist"

            # Verify formula resolution
            formula = main_sensor.formulas[0].formula
            print(f"📋 Resolved formula: {formula}")

            # Check that self-references in formula were resolved to state token
            expected_formula = "state * 1.1"
            actual_formula = formula
            print(f"📋 Expected formula: {expected_formula}")
            print(f"📋 Actual formula: {actual_formula}")

            # Self-references should be replaced with 'state' token
            assert actual_formula == expected_formula, f"Expected formula '{expected_formula}', got '{actual_formula}'"

            # Verify attribute resolution - this is the key test
            attributes = main_sensor.formulas[0].attributes
            print(f"📋 Resolved attributes: {attributes}")

            # Check specific attribute resolutions - these should use 'state' token, not entity_id
            expected_attributes = {
                "daily_power": "state * 24",
                "weekly_power": "state * 24 * 7",
                "monthly_power": "state * 24 * 30",
                "power_efficiency": "state / 1000 * 100",
                "cost_per_hour": "state * 0.25",
                "cost_per_day": "state * 0.25 * 24",
            }

            for attr_name, expected_value in expected_attributes.items():
                assert attr_name in attributes, f"Attribute '{attr_name}' should exist"
                actual_value = attributes[attr_name]
                assert actual_value == expected_value, (
                    f"Attribute '{attr_name}' should be '{expected_value}', got '{actual_value}'"
                )
                print(f"✅ Attribute '{attr_name}' correctly uses state token: '{actual_value}'")

            # Verify that NO attributes use entity_id for self-reference
            for attr_name, attr_value in attributes.items():
                # Check that attributes don't contain the sensor's entity_id for self-reference
                # They should use 'state' token instead
                assert "sensor.test_power_analyzer" not in attr_value, (
                    f"Attribute '{attr_name}' should not use entity_id for self-reference, got '{attr_value}'"
                )
                # Verify they do use 'state' token
                assert "state" in attr_value, (
                    f"Attribute '{attr_name}' should use 'state' token for self-reference, got '{attr_value}'"
                )

            # Export the processed YAML using StorageManager async method
            print(f"📋 Exporting processed YAML...")
            exported_yaml = await storage_manager.async_export_yaml(sensor_set_id)
            print(f"📋 Exported YAML:\n{exported_yaml}")

            # Parse both YAMLs for comparison
            exported_data = yaml.safe_load(exported_yaml)
            expected_data = yaml.safe_load(expected_yaml_content)

            # Compare the exported result with expected
            print(f"📋 Comparing exported vs expected...")

            # Compare sensors structure
            assert "sensors" in exported_data, "Exported YAML should contain 'sensors' key"
            assert "sensors" in expected_data, "Expected YAML should contain 'sensors' key"

            exported_sensors = exported_data["sensors"]
            expected_sensors = expected_data["sensors"]

            # Verify all expected sensors exist
            for sensor_key in expected_sensors:
                assert sensor_key in exported_sensors, f"Expected sensor '{sensor_key}' not found in export"

                expected_sensor = expected_sensors[sensor_key]
                exported_sensor = exported_sensors[sensor_key]

                # Compare formulas
                if "formula" in expected_sensor:
                    assert "formula" in exported_sensor, f"Expected formula for sensor '{sensor_key}'"
                    assert exported_sensor["formula"] == expected_sensor["formula"], (
                        f"Formula mismatch for '{sensor_key}': expected '{expected_sensor['formula']}', got '{exported_sensor['formula']}'"
                    )

                # Compare attributes - this is the critical test
                if "attributes" in expected_sensor:
                    assert "attributes" in exported_sensor, f"Expected attributes for sensor '{sensor_key}'"

                    expected_attrs = expected_sensor["attributes"]
                    exported_attrs = exported_sensor["attributes"]

                    for attr_name, expected_attr in expected_attrs.items():
                        assert attr_name in exported_attrs, f"Expected attribute '{attr_name}' for sensor '{sensor_key}'"

                        # Handle both simple string values and formula objects
                        if isinstance(expected_attr, dict) and "formula" in expected_attr:
                            expected_value = expected_attr["formula"]
                            exported_value = exported_attrs[attr_name]["formula"]
                        else:
                            expected_value = expected_attr
                            exported_value = exported_attrs[attr_name]

                        assert exported_value == expected_value, (
                            f"Attribute '{attr_name}' mismatch for '{sensor_key}': expected '{expected_value}', got '{exported_value}'"
                        )

                        # Verify state token usage
                        if "state" in expected_value:
                            assert "state" in exported_value, (
                                f"Attribute '{attr_name}' should use 'state' token, got '{exported_value}'"
                            )

            print(
                f"✅ State token self-reference test passed! All attributes correctly use 'state' token instead of entity_id."
            )

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_state_token_vs_entity_id_behavior(self, mock_hass, mock_states):
        """Test the behavioral difference between state token and entity_id in self-references."""

        # Create storage manager with mocked Store
        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "state_token_behavior_test"

            if storage_manager.sensor_set_exists(sensor_set_id):
                await storage_manager.async_delete_sensor_set(sensor_set_id)

            await storage_manager.async_create_sensor_set(sensor_set_id)

            # Test YAML with both state token and entity_id self-references
            test_yaml = """
sensors:
  behavior_test_sensor:
    entity_id: sensor.test_power_source
    formula: state * 2
    metadata:
      unit_of_measurement: W
    attributes:
      # Method 1: Direct state token (post-evaluation result)
      correct_daily: state * 24
      # Method 2: Entity_id self-reference (should also be converted to state token)
      incorrect_daily: sensor.behavior_test_sensor * 24
"""

            # Import YAML
            result = await storage_manager.async_from_yaml(yaml_content=test_yaml, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1

            # Get the sensor
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            sensor = sensors[0]
            attributes = sensor.formulas[0].attributes

            # Verify state token is used correctly
            assert "correct_daily" in attributes
            assert attributes["correct_daily"] == "state * 24"

            # Verify entity_id self-reference is ALSO replaced with state token
            # This is correct behavior - ALL self-references in attributes should use state token
            assert "incorrect_daily" in attributes
            # The entity_id self-reference should also be replaced with state token
            assert attributes["incorrect_daily"] == "state * 24"

            print(f"✅ State token vs entity_id behavior test passed!")
            print(f"   State token reference: {attributes['correct_daily']}")
            print(f"   Entity ID self-reference (also converted to state): {attributes['incorrect_daily']}")

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
