"""
Integration tests for metadata functionality.

Tests the complete metadata flow from YAML import through sensor creation.
"""

from unittest.mock import Mock

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.metadata_handler import MetadataHandler
from ha_synthetic_sensors.sensor_manager import DynamicSensor


class TestMetadataIntegration:
    """Integration tests for metadata functionality."""

    def test_sensor_creation_with_metadata(self, mock_hass, mock_entity_registry, mock_states):
        """Test that sensors are created with proper metadata application."""
        # Create test configuration with metadata hierarchy
        global_settings = {
            "device_identifier": "test_device",
            "metadata": {
                "attribution": "Global attribution",
                "entity_registry_enabled_default": True,
                "suggested_display_precision": 3,
            },
        }

        formula_config = FormulaConfig(
            id="test_formula",
            formula="sensor.test * 2",
            metadata={
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
                "suggested_display_precision": 1,  # Should override global
            },
        )

        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            formulas=[formula_config],
            metadata={"icon": "mdi:flash", "entity_category": "diagnostic"},
        )

        # Mock dependencies
        evaluator = Mock()
        sensor_manager = Mock()

        # Create sensor with global settings
        sensor = DynamicSensor(mock_hass, sensor_config, evaluator, sensor_manager, None, global_settings)

        # Verify metadata inheritance hierarchy
        assert sensor._attr_native_unit_of_measurement == "W"  # From formula
        assert sensor._attr_device_class.value == "power"  # From formula
        assert sensor._attr_state_class == "measurement"  # From formula
        assert sensor._attr_icon == "mdi:flash"  # From sensor
        assert sensor._attr_attribution == "Global attribution"  # From global
        assert sensor._attr_suggested_display_precision == 1  # Formula overrides global
        assert sensor._attr_entity_category == "diagnostic"  # From sensor
        assert sensor._attr_entity_registry_enabled_default is True  # From global

    def test_metadata_storage_roundtrip(self):
        """Test that metadata survives storage serialization/deserialization."""
        # Create sensor config with metadata
        formula_config = FormulaConfig(
            id="test_formula",
            formula="sensor.test * 2",
            metadata={
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
                "icon": "mdi:flash",
                "suggested_display_precision": 2,
            },
        )

        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            formulas=[formula_config],
            metadata={"attribution": "Test attribution", "entity_category": "diagnostic"},
        )

        # Mock storage manager
        storage_manager = Mock()

        # Test serialization
        from ha_synthetic_sensors.storage_sensor_ops import SensorOpsHandler

        handler = SensorOpsHandler(storage_manager)

        serialized = handler.serialize_sensor_config(sensor_config)
        deserialized = handler.deserialize_sensor_config(serialized)

        # Verify metadata is preserved
        assert deserialized.metadata == sensor_config.metadata
        assert deserialized.formulas[0].metadata == sensor_config.formulas[0].metadata

    def test_global_metadata_inheritance(self):
        """Test that global metadata is properly inherited by sensors."""
        # Create config with global metadata
        global_settings = {
            "device_identifier": "test_device",
            "variables": {"base_power": "sensor.base_power"},
            "metadata": {
                "attribution": "Global attribution",
                "entity_registry_enabled_default": True,
                "suggested_display_precision": 3,
            },
        }

        formula_config = FormulaConfig(
            id="test_formula", formula="base_power * 2", metadata={"unit_of_measurement": "W", "device_class": "power"}
        )

        sensor_config = SensorConfig(unique_id="test_sensor", name="Test Sensor", formulas=[formula_config])

        # Test metadata handling
        metadata_handler = MetadataHandler()
        global_metadata = global_settings.get("metadata", {})

        # Test sensor metadata (inherits from global)
        sensor_metadata = metadata_handler.merge_sensor_metadata(global_metadata, sensor_config)
        assert sensor_metadata["attribution"] == "Global attribution"  # From global
        assert sensor_metadata["entity_registry_enabled_default"] is True  # From global
        assert sensor_metadata["suggested_display_precision"] == 3  # From global

        # Test attribute metadata (separate from sensor, no inheritance)
        attribute_metadata = metadata_handler.get_attribute_metadata(formula_config)
        assert attribute_metadata["unit_of_measurement"] == "W"  # Only from formula
        assert attribute_metadata["device_class"] == "power"  # Only from formula
        assert "attribution" not in attribute_metadata  # No inheritance from global/sensor

    def test_metadata_override_precedence(self):
        """Test that metadata override precedence works correctly."""
        global_metadata = {
            "attribution": "Global attribution",
            "suggested_display_precision": 3,
            "entity_registry_enabled_default": True,
        }

        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            formulas=[],
            metadata={
                "suggested_display_precision": 2,  # Should override global
                "icon": "mdi:sensor",  # New property
            },
        )

        formula_config = FormulaConfig(
            id="test_formula",
            formula="sensor.test * 2",
            metadata={
                "suggested_display_precision": 1,  # Should override both global and sensor
                "unit_of_measurement": "W",  # New property
            },
        )

        metadata_handler = MetadataHandler()

        # Test sensor metadata (global + sensor)
        sensor_metadata = metadata_handler.merge_sensor_metadata(global_metadata, sensor_config)
        assert sensor_metadata["attribution"] == "Global attribution"  # From global (not overridden)
        assert sensor_metadata["entity_registry_enabled_default"] is True  # From global (not overridden)
        assert sensor_metadata["icon"] == "mdi:sensor"  # From sensor
        assert sensor_metadata["suggested_display_precision"] == 2  # Sensor overrides global

        # Test attribute metadata (only from formula, no inheritance)
        attribute_metadata = metadata_handler.get_attribute_metadata(formula_config)
        assert attribute_metadata["suggested_display_precision"] == 1  # Only from formula
        assert attribute_metadata["unit_of_measurement"] == "W"  # Only from formula
        assert "attribution" not in attribute_metadata  # No inheritance
        assert "icon" not in attribute_metadata  # No inheritance

    def test_empty_metadata_handling(self):
        """Test that empty metadata dictionaries are handled gracefully."""
        # Test with no metadata at any level
        sensor_config = SensorConfig(unique_id="test_sensor", name="Test Sensor", formulas=[])

        formula_config = FormulaConfig(id="test_formula", formula="sensor.test * 2")

        metadata_handler = MetadataHandler()

        # Should handle empty metadata gracefully
        sensor_metadata = metadata_handler.merge_sensor_metadata({}, sensor_config)
        attribute_metadata = metadata_handler.get_attribute_metadata(formula_config)

        assert sensor_metadata == {}
        assert attribute_metadata == {}

    def test_yaml_metadata_import_export(self, mock_hass, mock_entity_registry, mock_states):
        """Test that metadata is properly handled in YAML import/export."""
        # For now, test that the ConfigManager can parse the basic structure
        # The full metadata parsing will be implemented when ConfigManager is updated
        yaml_content = """
version: "1.0"

global_settings:
  device_identifier: "test_device"
  variables:
    base_power: "sensor.test_power"

sensors:
  test_sensor:
    name: "Test Sensor"
    formula: "base_power * 2"
    variables:
      multiplier: 2
"""

        # Test that ConfigManager can parse this YAML
        from ha_synthetic_sensors.config_manager import ConfigManager

        config_manager = ConfigManager(mock_hass)

        config = config_manager.load_from_yaml(yaml_content)

        # Verify basic structure
        assert len(config.sensors) == 1
        sensor = config.sensors[0]
        assert sensor.unique_id == "test_sensor"
        assert sensor.name == "Test Sensor"
        assert len(sensor.formulas) == 1

        # Verify global settings
        assert "device_identifier" in config.global_settings
        assert config.global_settings["device_identifier"] == "test_device"
        assert "variables" in config.global_settings
        assert config.global_settings["variables"]["base_power"] == "sensor.test_power"

        # NOTE: Full metadata parsing will be tested when ConfigManager is updated
        # This test verifies the basic YAML structure is working

    def test_metadata_validation(self):
        """Test that metadata validation works correctly."""
        metadata_handler = MetadataHandler()

        # Test valid metadata
        valid_metadata = {
            "unit_of_measurement": "W",
            "device_class": "power",
            "state_class": "measurement",
            "icon": "mdi:flash",
            "suggested_display_precision": 2,
        }

        # Should not raise any errors
        ha_properties = metadata_handler.extract_ha_sensor_properties(valid_metadata)
        assert ha_properties["unit_of_measurement"] == "W"
        assert ha_properties["device_class"] == "power"
        assert ha_properties["state_class"] == "measurement"
        assert ha_properties["icon"] == "mdi:flash"
        assert ha_properties["suggested_display_precision"] == 2

        # Test with additional custom properties
        custom_metadata = valid_metadata.copy()
        custom_metadata["custom_property"] = "custom_value"

        ha_properties = metadata_handler.extract_ha_sensor_properties(custom_metadata)
        assert ha_properties["custom_property"] == "custom_value"
