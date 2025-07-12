"""
Tests for metadata constants module.

Tests the metadata property classification and validation functions.
"""

from ha_synthetic_sensors.constants_metadata import (
    ALL_KNOWN_METADATA_PROPERTIES,
    ATTRIBUTE_ALLOWED_METADATA_PROPERTIES,
    ENTITY_ONLY_METADATA_PROPERTIES,
    get_entity_only_property_reason,
    is_attribute_allowed_property,
    is_entity_only_property,
    is_registry_property,
    is_sensor_behavior_property,
    is_statistics_property,
    is_ui_property,
    validate_attribute_metadata_properties,
)


class TestMetadataConstants:
    """Test metadata constants and classification functions."""

    def test_entity_only_properties_classification(self) -> None:
        """Test that entity-only properties are correctly classified."""
        # Test known entity-only properties
        assert is_entity_only_property("device_class")
        assert is_entity_only_property("state_class")
        assert is_entity_only_property("entity_category")
        assert is_entity_only_property("entity_registry_enabled_default")
        assert is_entity_only_property("entity_registry_visible_default")
        assert is_entity_only_property("assumed_state")
        assert is_entity_only_property("available")
        assert is_entity_only_property("last_reset")
        assert is_entity_only_property("force_update")

        # Test attribute-allowed properties
        assert not is_entity_only_property("unit_of_measurement")
        assert not is_entity_only_property("icon")
        assert not is_entity_only_property("suggested_display_precision")
        assert not is_entity_only_property("attribution")

        # Test unknown properties (should be allowed on attributes)
        assert not is_entity_only_property("custom_property")
        assert not is_entity_only_property("unknown_field")

    def test_attribute_allowed_properties_classification(self) -> None:
        """Test that attribute-allowed properties are correctly classified."""
        # Test known attribute-allowed properties
        assert is_attribute_allowed_property("unit_of_measurement")
        assert is_attribute_allowed_property("icon")
        assert is_attribute_allowed_property("suggested_display_precision")
        assert is_attribute_allowed_property("attribution")

        # Test entity-only properties
        assert not is_attribute_allowed_property("device_class")
        assert not is_attribute_allowed_property("state_class")
        assert not is_attribute_allowed_property("entity_category")

        # Test unknown properties (should be allowed on attributes)
        assert is_attribute_allowed_property("custom_property")
        assert is_attribute_allowed_property("unknown_field")

    def test_entity_only_property_reasons(self) -> None:
        """Test that entity-only properties have descriptive reasons."""
        # Test that all entity-only properties have reasons
        for prop in ENTITY_ONLY_METADATA_PROPERTIES:
            reason = get_entity_only_property_reason(prop)
            assert reason is not None
            assert isinstance(reason, str)
            assert len(reason) > 0
            assert prop in reason  # Reason should mention the property name

        # Test that attribute-allowed properties don't have reasons
        assert get_entity_only_property_reason("unit_of_measurement") is None
        assert get_entity_only_property_reason("icon") is None
        assert get_entity_only_property_reason("unknown_property") is None

    def test_registry_properties_classification(self) -> None:
        """Test that registry properties are correctly classified."""
        assert is_registry_property("entity_registry_enabled_default")
        assert is_registry_property("entity_registry_visible_default")

        assert not is_registry_property("device_class")
        assert not is_registry_property("unit_of_measurement")
        assert not is_registry_property("unknown_property")

    def test_statistics_properties_classification(self) -> None:
        """Test that statistics properties are correctly classified."""
        assert is_statistics_property("state_class")
        assert is_statistics_property("last_reset")

        assert not is_statistics_property("device_class")
        assert not is_statistics_property("unit_of_measurement")
        assert not is_statistics_property("unknown_property")

    def test_ui_properties_classification(self) -> None:
        """Test that UI properties are correctly classified."""
        assert is_ui_property("entity_category")
        assert is_ui_property("icon")
        assert is_ui_property("suggested_display_precision")
        assert is_ui_property("suggested_unit_of_measurement")

        assert not is_ui_property("device_class")
        assert not is_ui_property("state_class")
        assert not is_ui_property("unknown_property")

    def test_sensor_behavior_properties_classification(self) -> None:
        """Test that sensor behavior properties are correctly classified."""
        assert is_sensor_behavior_property("device_class")
        assert is_sensor_behavior_property("assumed_state")
        assert is_sensor_behavior_property("available")
        assert is_sensor_behavior_property("force_update")

        assert not is_sensor_behavior_property("entity_category")
        assert not is_sensor_behavior_property("unit_of_measurement")
        assert not is_sensor_behavior_property("unknown_property")

    def test_all_known_properties_completeness(self) -> None:
        """Test that ALL_KNOWN_METADATA_PROPERTIES includes all defined properties."""
        # All entity-only properties should be in the complete set
        for prop in ENTITY_ONLY_METADATA_PROPERTIES:
            assert prop in ALL_KNOWN_METADATA_PROPERTIES

        # All attribute-allowed properties should be in the complete set
        for prop in ATTRIBUTE_ALLOWED_METADATA_PROPERTIES:
            assert prop in ALL_KNOWN_METADATA_PROPERTIES

    def test_property_sets_no_overlap_where_expected(self) -> None:
        """Test that certain property sets don't overlap where they shouldn't."""
        # Entity-only and attribute-allowed should not overlap
        entity_only_set = set(ENTITY_ONLY_METADATA_PROPERTIES.keys())
        attribute_allowed_set = ATTRIBUTE_ALLOWED_METADATA_PROPERTIES

        overlap = entity_only_set & attribute_allowed_set
        assert len(overlap) == 0, f"Unexpected overlap: {overlap}"

    def test_validate_attribute_metadata_properties_valid(self) -> None:
        """Test validation of valid attribute metadata."""
        valid_metadata = {
            "unit_of_measurement": "°C",
            "icon": "mdi:thermometer",
            "suggested_display_precision": 1,
            "attribution": "Weather Service",
            "custom_property": "custom_value",
        }

        errors = validate_attribute_metadata_properties(valid_metadata)
        assert errors == []

    def test_validate_attribute_metadata_properties_invalid(self) -> None:
        """Test validation of invalid attribute metadata."""
        invalid_metadata = {
            "device_class": "temperature",  # Entity-only
            "state_class": "measurement",  # Entity-only
            "entity_category": "diagnostic",  # Entity-only
            "unit_of_measurement": "°C",  # Valid for attributes
            "custom_property": "custom_value",  # Valid for attributes
        }

        errors = validate_attribute_metadata_properties(invalid_metadata)

        # Should have exactly 3 errors for the entity-only properties
        assert len(errors) == 3

        # Check that each entity-only property generates an error
        error_text = " ".join(errors)
        assert "device_class" in error_text
        assert "state_class" in error_text
        assert "entity_category" in error_text

        # Check that valid properties don't generate errors
        assert "unit_of_measurement" not in error_text
        assert "custom_property" not in error_text

    def test_validate_attribute_metadata_properties_empty(self) -> None:
        """Test validation of empty attribute metadata."""
        errors = validate_attribute_metadata_properties({})
        assert errors == []

    def test_validate_attribute_metadata_properties_all_entity_only(self) -> None:
        """Test validation when all properties are entity-only."""
        all_entity_only = dict.fromkeys(ENTITY_ONLY_METADATA_PROPERTIES.keys(), "test_value")

        errors = validate_attribute_metadata_properties(all_entity_only)

        # Should have one error per entity-only property
        assert len(errors) == len(ENTITY_ONLY_METADATA_PROPERTIES)

        # Each property should be mentioned in the errors
        error_text = " ".join(errors)
        for prop in ENTITY_ONLY_METADATA_PROPERTIES:
            assert prop in error_text
