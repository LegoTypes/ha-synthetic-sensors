"""
Unit tests for YAML export alternate state handler formatting.

Tests that the YAML export properly handles ComputedVariable serialization
and alternate state handler case formatting.
"""

import pytest
from unittest.mock import MagicMock

from ha_synthetic_sensors.storage_yaml_handler import YamlHandler
from ha_synthetic_sensors.config_models import (
    FormulaConfig,
    SensorConfig,
    ComputedVariable,
    AlternateStateHandler,
)


class TestYamlExportAlternateStateHandlers:
    """Test YAML export handling of alternate state handlers."""

    def test_computed_variable_serialization_with_alternate_handlers(self):
        """Test that ComputedVariable objects are properly serialized to YAML format."""
        # Create alternate state handler for variable
        var_alt_handler = AlternateStateHandler(unavailable="false", unknown="false")

        # Create computed variable
        computed_var = ComputedVariable(
            formula="minutes_between(metadata(state, 'last_changed'), now()) < grace_period_minutes",
            dependencies=set(),
            alternate_state_handler=var_alt_handler,
        )

        # Create main formula with the computed variable
        main_formula = FormulaConfig(id="test_sensor", formula="state", variables={"within_grace": computed_var})

        # Create sensor config
        sensor_config = SensorConfig(unique_id="test_sensor", formulas=[main_formula], device_identifier="test-device")

        # Mock storage manager
        mock_storage = MagicMock()
        mock_storage.data = {
            "sensor_sets": {"test_set": {"global_settings": {}}},
            "sensors": {"test_sensor": {"sensor_set_id": "test_set", "config_data": sensor_config}},
        }
        mock_storage.deserialize_sensor_config = lambda x: x

        # Create YAML handler and export
        yaml_handler = YamlHandler(mock_storage)
        yaml_output = yaml_handler.export_yaml("test_set")

        # Verify no Python object serialization corruption
        assert "!!python/object:" not in yaml_output
        assert "ComputedVariable" not in yaml_output
        assert "AlternateStateHandler" not in yaml_output

        # Verify proper variable structure in output
        assert "variables:" in yaml_output
        assert "within_grace:" in yaml_output
        assert "formula: minutes_between" in yaml_output

        # Verify alternate_states structure for computed variable
        assert "alternate_states:" in yaml_output
        assert "UNAVAILABLE: 'false'" in yaml_output
        assert "UNKNOWN: 'false'" in yaml_output

        # Verify no lowercase corruption
        assert "unavailable: 'false'" not in yaml_output
        assert "unknown: 'false'" not in yaml_output

    def test_sensor_level_alternate_state_handlers(self):
        """Test that sensor-level alternate state handlers are exported with proper casing."""
        # Create sensor-level alternate state handler
        sensor_alt_handler = AlternateStateHandler(
            unavailable="state if within_grace else UNKNOWN", unknown="state if within_grace else UNKNOWN"
        )

        # Create main formula with alternate state handler
        main_formula = FormulaConfig(id="test_sensor", formula="state", alternate_state_handler=sensor_alt_handler)

        # Create sensor config
        sensor_config = SensorConfig(unique_id="test_sensor", formulas=[main_formula], device_identifier="test-device")

        # Mock storage manager
        mock_storage = MagicMock()
        mock_storage.data = {
            "sensor_sets": {"test_set": {"global_settings": {}}},
            "sensors": {"test_sensor": {"sensor_set_id": "test_set", "config_data": sensor_config}},
        }
        mock_storage.deserialize_sensor_config = lambda x: x

        # Create YAML handler and export
        yaml_handler = YamlHandler(mock_storage)
        yaml_output = yaml_handler.export_yaml("test_set")

        # Verify sensor-level alternate state handlers are present with proper casing
        assert "alternate_states:" in yaml_output
        assert "UNAVAILABLE: state if within_grace else UNKNOWN" in yaml_output
        assert "UNKNOWN: state if within_grace else UNKNOWN" in yaml_output

        # Verify no lowercase corruption
        assert "unavailable: state if" not in yaml_output
        assert "unknown: state if" not in yaml_output

    def test_combined_sensor_and_variable_alternate_handlers(self):
        """Test export with both sensor-level and variable-level alternate state handlers."""
        # Create variable alternate state handler
        var_alt_handler = AlternateStateHandler(unavailable="false", unknown="false")

        # Create computed variable
        computed_var = ComputedVariable(
            formula="minutes_between(metadata(state, 'last_changed'), now()) < grace_period_minutes",
            alternate_state_handler=var_alt_handler,
        )

        # Create sensor alternate state handler
        sensor_alt_handler = AlternateStateHandler(
            unavailable="state if within_grace else UNKNOWN", unknown="state if within_grace else UNKNOWN"
        )

        # Create main formula with both types
        main_formula = FormulaConfig(
            id="test_sensor",
            formula="state",
            variables={"within_grace": computed_var},
            alternate_state_handler=sensor_alt_handler,
        )

        # Create sensor config
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            entity_id="sensor.test",
            formulas=[main_formula],
            device_identifier="test-device",
        )

        # Mock storage manager
        mock_storage = MagicMock()
        mock_storage.data = {
            "sensor_sets": {"test_set": {"global_settings": {"device_identifier": "test-device"}}},
            "sensors": {"test_sensor": {"sensor_set_id": "test_set", "config_data": sensor_config}},
        }
        mock_storage.deserialize_sensor_config = lambda x: x

        # Create YAML handler and export
        yaml_handler = YamlHandler(mock_storage)
        yaml_output = yaml_handler.export_yaml("test_set")

        # Verify structure and content
        assert "entity_id: sensor.test" in yaml_output
        assert "name: Test Sensor" in yaml_output
        assert "formula: state" in yaml_output

        # Verify sensor-level handlers
        assert "alternate_states:" in yaml_output
        assert "UNAVAILABLE: state if within_grace else UNKNOWN" in yaml_output
        assert "UNKNOWN: state if within_grace else UNKNOWN" in yaml_output

        # Verify variable structure
        assert "variables:" in yaml_output
        assert "within_grace:" in yaml_output
        assert "formula: minutes_between" in yaml_output

        # Verify variable-level handlers
        lines = yaml_output.split("\n")
        variable_section_found = False
        for i, line in enumerate(lines):
            if "within_grace:" in line:
                variable_section_found = True
                # Check subsequent lines for the variable's alternate handlers
                remaining_lines = lines[i : i + 10]  # Check next few lines for alternate_states
                remaining_text = "\n".join(remaining_lines)
                assert "alternate_states:" in remaining_text
                assert "UNAVAILABLE: 'false'" in remaining_text
                assert "UNKNOWN: 'false'" in remaining_text
                break

        assert variable_section_found, "Variable section not found in YAML output"

        # Verify no corruption
        assert "!!python/object:" not in yaml_output
        assert "unavailable: 'false'" not in yaml_output
        assert "unknown: 'false'" not in yaml_output

    def test_alternate_handlers_literal_and_object_forms_export(self):
        """Extend export tests to include literal and object-form alternate handlers (non-breaking)."""
        # Literal boolean alternates at sensor level
        sensor_alt_literal = AlternateStateHandler(unavailable=True, unknown=False)

        # Computed variable with object-form alternates would be serialized by schema rules; here we verify no corruption
        computed_var = ComputedVariable(
            formula="state * 1.0",
            alternate_state_handler=AlternateStateHandler(unavailable="0", unknown="1"),
        )

        main = FormulaConfig(
            id="test_literal_object",
            formula="state",
            variables={"cv": computed_var},
            alternate_state_handler=sensor_alt_literal,
        )

        sensor_config = SensorConfig(unique_id="test_literal_object", formulas=[main], device_identifier="dev")

        mock_storage = MagicMock()
        mock_storage.data = {
            "sensor_sets": {"set": {"global_settings": {"device_identifier": "dev"}}},
            "sensors": {"test_literal_object": {"sensor_set_id": "set", "config_data": sensor_config}},
        }
        mock_storage.deserialize_sensor_config = lambda x: x

        yaml_output = YamlHandler(mock_storage).export_yaml("set")

        # Sensor-level literal booleans should appear as YAML booleans
        assert "alternate_states:" in yaml_output
        assert "UNAVAILABLE: true" in yaml_output or "UNAVAILABLE: True" in yaml_output
        assert "UNKNOWN: false" in yaml_output or "UNKNOWN: False" in yaml_output

        # Ensure computed variable still exports handlers as strings for back-compat
        assert "cv:" in yaml_output
        # Adjacent lines should include alternate_states with UNAVAILABLE/UNKNOWN under cv
        assert "alternate_states:" in yaml_output
        assert ("UNAVAILABLE: '0'" in yaml_output) or ('UNAVAILABLE: "0"' in yaml_output)
        assert ("UNKNOWN: '1'" in yaml_output) or ('UNKNOWN: "1"' in yaml_output)
