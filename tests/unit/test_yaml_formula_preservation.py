"""
Unit tests for YAML export formula preservation.

Tests that the YAML export properly preserves formulas as formula objects
rather than flattening them to literal strings.
"""

import pytest
from unittest.mock import MagicMock

from ha_synthetic_sensors.storage_yaml_handler import YamlHandler
from ha_synthetic_sensors.config_models import (
    FormulaConfig,
    SensorConfig,
)


class TestYamlFormulaPreservation:
    """Test YAML export preservation of formula structures."""

    def test_variable_reference_preserved_as_formula(self):
        """Test that variable references are preserved as formula objects, not flattened to strings."""
        # Create main formula
        main_formula = FormulaConfig(id="test_sensor", formula="state")

        # Create attribute formula with variable reference (no variables defined)
        attr_formula = FormulaConfig(
            id="test_sensor_debug_panel_status",
            formula="panel_status",  # This should be preserved as a formula
        )

        # Create sensor config
        sensor_config = SensorConfig(
            unique_id="test_sensor", formulas=[main_formula, attr_formula], device_identifier="test-device"
        )

        # Mock storage manager
        mock_storage = MagicMock()
        mock_storage.data = {
            "sensor_sets": {"test_set": {"global_settings": {}}},
            "sensors": {"test_sensor": {"sensor_set_id": "test_set", "config_data": sensor_config}},
        }
        mock_storage.deserialize_sensor_config = lambda x: x

        # Create YAML handler and export
        yaml_handler = YamlHandler(mock_storage)
        yaml_content = yaml_handler.export_yaml("test_set")

        # Parse the YAML to check structure
        import yaml

        parsed_yaml = yaml.safe_load(yaml_content)

        # Check that the attribute is preserved as a formula object
        sensor_data = parsed_yaml["sensors"]["test_sensor"]
        debug_attr = sensor_data["attributes"]["debug_panel_status"]

        # Should be a dict with "formula" key, not a flattened string
        assert isinstance(debug_attr, dict), f"Expected dict but got {type(debug_attr)}: {debug_attr}"
        assert "formula" in debug_attr, f"Expected 'formula' key in {debug_attr}"
        assert debug_attr["formula"] == "panel_status"

    def test_entity_reference_preserved_as_formula(self):
        """Test that entity references are preserved as formula objects, not flattened to strings."""
        # Create attribute formula with entity reference (no variables defined)
        attr_formula = FormulaConfig(
            id="test_sensor_debug_entity",
            formula="sensor.power_meter",  # This should be preserved as a formula
        )

        # Create main formula
        main_formula = FormulaConfig(id="test_sensor", formula="state")

        # Create sensor config
        sensor_config = SensorConfig(
            unique_id="test_sensor", formulas=[main_formula, attr_formula], device_identifier="test-device"
        )

        # Mock storage manager
        mock_storage = MagicMock()
        mock_storage.data = {
            "sensor_sets": {"test_set": {"global_settings": {}}},
            "sensors": {"test_sensor": {"sensor_set_id": "test_set", "config_data": sensor_config}},
        }
        mock_storage.deserialize_sensor_config = lambda x: x

        # Create YAML handler and export
        yaml_handler = YamlHandler(mock_storage)
        yaml_content = yaml_handler.export_yaml("test_set")

        # Parse the YAML to check structure
        import yaml

        parsed_yaml = yaml.safe_load(yaml_content)

        # Check that the attribute is preserved as a formula object
        sensor_data = parsed_yaml["sensors"]["test_sensor"]
        debug_attr = sensor_data["attributes"]["debug_entity"]

        # Should be a dict with "formula" key, not a flattened string
        assert isinstance(debug_attr, dict), f"Expected dict but got {type(debug_attr)}: {debug_attr}"
        assert "formula" in debug_attr, f"Expected 'formula' key in {debug_attr}"
        assert debug_attr["formula"] == "sensor.power_meter"

    def test_function_call_preserved_as_formula(self):
        """Test that function calls are preserved as formula objects, not flattened to strings."""
        # Create attribute formula with function call (no variables defined)
        attr_formula = FormulaConfig(
            id="test_sensor_debug_function",
            formula="utc_now()",  # This should be preserved as a formula
        )

        # Create main formula
        main_formula = FormulaConfig(id="test_sensor", formula="state")

        # Create sensor config
        sensor_config = SensorConfig(
            unique_id="test_sensor", formulas=[main_formula, attr_formula], device_identifier="test-device"
        )

        # Mock storage manager
        mock_storage = MagicMock()
        mock_storage.data = {
            "sensor_sets": {"test_set": {"global_settings": {}}},
            "sensors": {"test_sensor": {"sensor_set_id": "test_set", "config_data": sensor_config}},
        }
        mock_storage.deserialize_sensor_config = lambda x: x

        # Create YAML handler and export
        yaml_handler = YamlHandler(mock_storage)
        yaml_content = yaml_handler.export_yaml("test_set")

        # Parse the YAML to check structure
        import yaml

        parsed_yaml = yaml.safe_load(yaml_content)

        # Check that the attribute is preserved as a formula object
        sensor_data = parsed_yaml["sensors"]["test_sensor"]
        debug_attr = sensor_data["attributes"]["debug_function"]

        # Should be a dict with "formula" key, not a flattened string
        assert isinstance(debug_attr, dict), f"Expected dict but got {type(debug_attr)}: {debug_attr}"
        assert "formula" in debug_attr, f"Expected 'formula' key in {debug_attr}"
        assert debug_attr["formula"] == "utc_now()"

    def test_literal_values_preserved_as_formulas(self):
        """Test that even literal values are preserved as formula structures when they come from FormulaConfig."""
        # Create attribute formulas with literal values
        number_formula = FormulaConfig(
            id="test_sensor_number",
            formula="42",  # This should be preserved as formula
        )

        string_formula = FormulaConfig(
            id="test_sensor_string",
            formula='"hello world"',  # This should be preserved as formula
        )

        bool_formula = FormulaConfig(
            id="test_sensor_bool",
            formula="True",  # This should be preserved as formula
        )

        # Create main formula
        main_formula = FormulaConfig(id="test_sensor", formula="state")

        # Create sensor config
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            formulas=[main_formula, number_formula, string_formula, bool_formula],
            device_identifier="test-device",
        )

        # Mock storage manager
        mock_storage = MagicMock()
        mock_storage.data = {
            "sensor_sets": {"test_set": {"global_settings": {}}},
            "sensors": {"test_sensor": {"sensor_set_id": "test_set", "config_data": sensor_config}},
        }
        mock_storage.deserialize_sensor_config = lambda x: x

        # Create YAML handler and export
        yaml_handler = YamlHandler(mock_storage)
        yaml_content = yaml_handler.export_yaml("test_set")

        # Parse the YAML to check structure
        import yaml

        parsed_yaml = yaml.safe_load(yaml_content)

        # Check that literals are preserved as formula structures
        sensor_data = parsed_yaml["sensors"]["test_sensor"]

        # Number should be preserved as formula
        number_attr = sensor_data["attributes"]["number"]
        assert isinstance(number_attr, dict), f"Expected dict but got {type(number_attr)}: {number_attr}"
        assert "formula" in number_attr, f"Expected 'formula' key in {number_attr}"
        assert number_attr["formula"] == "42"

        # String should be preserved as formula
        string_attr = sensor_data["attributes"]["string"]
        assert isinstance(string_attr, dict), f"Expected dict but got {type(string_attr)}: {string_attr}"
        assert "formula" in string_attr, f"Expected 'formula' key in {string_attr}"
        assert string_attr["formula"] == '"hello world"'

        # Boolean should be preserved as formula
        bool_attr = sensor_data["attributes"]["bool"]
        assert isinstance(bool_attr, dict), f"Expected dict but got {type(bool_attr)}: {bool_attr}"
        assert "formula" in bool_attr, f"Expected 'formula' key in {bool_attr}"
        assert bool_attr["formula"] == "True"
