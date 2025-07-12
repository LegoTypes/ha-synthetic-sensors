"""
Unit tests for MetadataHandler module.

Tests the core metadata merging and validation functionality.
"""

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.metadata_handler import MetadataHandler


class TestMetadataHandler:
    """Test cases for MetadataHandler."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.handler = MetadataHandler()

    def test_merge_metadata_empty_dicts(self) -> None:
        """Test merging empty metadata dictionaries."""
        result = self.handler.merge_metadata({}, {})
        assert result == {}

    def test_merge_metadata_global_only(self) -> None:
        """Test merging with only global metadata."""
        global_meta = {"unit_of_measurement": "W", "device_class": "power"}
        result = self.handler.merge_metadata(global_meta, {})
        assert result == global_meta

    def test_merge_metadata_local_only(self) -> None:
        """Test merging with only local metadata."""
        local_meta = {"unit_of_measurement": "kWh", "icon": "mdi:flash"}
        result = self.handler.merge_metadata({}, local_meta)
        assert result == local_meta

    def test_merge_metadata_local_overrides_global(self) -> None:
        """Test that local metadata overrides global metadata."""
        global_meta = {"unit_of_measurement": "W", "device_class": "power"}
        local_meta = {"unit_of_measurement": "kWh", "icon": "mdi:flash"}

        result = self.handler.merge_metadata(global_meta, local_meta)

        expected = {
            "unit_of_measurement": "kWh",  # Local overrides global
            "device_class": "power",  # Global preserved
            "icon": "mdi:flash",  # Local added
        }
        assert result == expected

    def test_merge_sensor_metadata_no_metadata_attr(self) -> None:
        """Test merging sensor metadata when sensor has no metadata attribute."""
        sensor_config = SensorConfig(unique_id="test_sensor")
        # Remove metadata attribute to simulate legacy config
        delattr(sensor_config, "metadata")

        global_meta = {"unit_of_measurement": "W"}
        result = self.handler.merge_sensor_metadata(global_meta, sensor_config)

        assert result == global_meta

    def test_merge_sensor_metadata_with_metadata_attr(self) -> None:
        """Test merging sensor metadata when sensor has metadata."""
        sensor_config = SensorConfig(unique_id="test_sensor", metadata={"device_class": "power", "icon": "mdi:flash"})

        global_meta = {"unit_of_measurement": "W", "device_class": "energy"}
        result = self.handler.merge_sensor_metadata(global_meta, sensor_config)

        expected = {
            "unit_of_measurement": "W",
            "device_class": "power",  # Sensor overrides global
            "icon": "mdi:flash",  # Sensor adds new property
        }
        assert result == expected

    def test_get_attribute_metadata(self) -> None:
        """Test getting attribute metadata (no inheritance from sensor/global)."""
        attribute_config = FormulaConfig(
            id="test_attr", formula="test_formula", metadata={"unit_of_measurement": "kWh", "suggested_display_precision": 2}
        )

        result = self.handler.get_attribute_metadata(attribute_config)

        expected = {
            "unit_of_measurement": "kWh",  # Only from attribute config
            "suggested_display_precision": 2,  # Only from attribute config
        }
        assert result == expected

    def test_validate_metadata_valid(self) -> None:
        """Test validation of valid metadata."""
        metadata = {
            "unit_of_measurement": "W",
            "device_class": "power",
            "state_class": "measurement",
            "icon": "mdi:flash",
            "suggested_display_precision": 2,
            "entity_category": "diagnostic",
            "entity_registry_enabled_default": True,
            "assumed_state": False,
            "options": ["low", "medium", "high"],
        }

        errors = self.handler.validate_metadata(metadata)
        assert errors == []

    def test_validate_metadata_invalid_types(self) -> None:
        """Test validation of metadata with invalid types."""
        metadata = {
            "unit_of_measurement": 123,  # Should be string
            "device_class": ["power"],  # Should be string
            "suggested_display_precision": "2",  # Should be int
            "entity_registry_enabled_default": "true",  # Should be bool
            "options": "low,medium,high",  # Should be list
        }

        errors = self.handler.validate_metadata(metadata)
        assert len(errors) == 5
        assert "unit_of_measurement must be a string" in errors
        assert "device_class must be a string" in errors
        assert "suggested_display_precision must be an integer" in errors
        assert "entity_registry_enabled_default must be a boolean" in errors
        assert "options must be a list" in errors

    def test_validate_metadata_invalid_entity_category(self) -> None:
        """Test validation of invalid entity category."""
        metadata = {"entity_category": "invalid"}

        errors = self.handler.validate_metadata(metadata)
        assert len(errors) == 1
        assert "entity_category must be one of: ['config', 'diagnostic', 'system']" in errors[0]

    def test_validate_metadata_not_dict(self) -> None:
        """Test validation when metadata is not a dictionary."""
        errors = self.handler.validate_metadata("not_a_dict")  # type: ignore[arg-type]
        assert len(errors) == 1
        assert "Metadata must be a dictionary" in errors

    def test_extract_ha_sensor_properties(self) -> None:
        """Test extraction of HA sensor properties."""
        metadata = {"unit_of_measurement": "W", "device_class": "power", "custom_property": "custom_value", "icon": "mdi:flash"}

        result = self.handler.extract_ha_sensor_properties(metadata)

        # All properties should be passed through
        assert result == metadata
        assert result is not metadata  # Should be a copy

    def test_merge_metadata_preserves_original_dicts(self) -> None:
        """Test that merging doesn't modify original dictionaries."""
        global_meta = {"unit_of_measurement": "W"}
        local_meta = {"device_class": "power"}

        original_global = global_meta.copy()
        original_local = local_meta.copy()

        result = self.handler.merge_metadata(global_meta, local_meta)

        # Original dictionaries should be unchanged
        assert global_meta == original_global
        assert local_meta == original_local

        # Result should contain both
        assert result == {"unit_of_measurement": "W", "device_class": "power"}

    def test_get_attribute_metadata_no_metadata_attr(self) -> None:
        """Test getting attribute metadata when FormulaConfig has no metadata attribute."""
        formula_config = FormulaConfig(id="test_id", formula="test_formula")

        result = self.handler.get_attribute_metadata(formula_config)

        expected = {}  # No metadata defined, should return empty dict
        assert result == expected

    def test_validate_metadata_attribute_restrictions(self) -> None:
        """Test validation of entity-only properties in attribute metadata."""
        # Test valid attribute metadata (should pass)
        valid_metadata = {
            "unit_of_measurement": "°C",
            "icon": "mdi:thermometer",
            "suggested_display_precision": 1,
        }
        errors = self.handler.validate_metadata(valid_metadata, is_attribute=True)
        assert errors == []

        # Test invalid attribute metadata (entity-only properties)
        invalid_metadata = {
            "device_class": "temperature",  # Entity-only
            "state_class": "measurement",  # Entity-only
            "entity_category": "diagnostic",  # Entity-only
            "unit_of_measurement": "°C",  # Valid for attributes
        }
        errors = self.handler.validate_metadata(invalid_metadata, is_attribute=True)

        # Should have errors for the entity-only properties
        assert len(errors) == 3
        assert any("device_class" in error for error in errors)
        assert any("state_class" in error for error in errors)
        assert any("entity_category" in error for error in errors)
        # Should not have error for unit_of_measurement
        assert not any("unit_of_measurement" in error for error in errors)

    def test_validate_metadata_entity_allows_all(self) -> None:
        """Test that entity metadata validation allows all properties."""
        # Test entity metadata with both entity-only and attribute-allowed properties
        entity_metadata = {
            "device_class": "temperature",
            "state_class": "measurement",
            "entity_category": "diagnostic",
            "unit_of_measurement": "°C",
            "icon": "mdi:thermometer",
        }
        errors = self.handler.validate_metadata(entity_metadata, is_attribute=False)

        # Should have no errors for entities (they can use any property)
        # Only type validation errors would occur
        type_errors = [e for e in errors if ("must be" in e and "string" in e) or "boolean" in e or "integer" in e]
        assert len(errors) == len(type_errors)  # Only type errors, no restriction errors
