"""Tests for device class functionality."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass

from ha_synthetic_sensors.device_classes import (
    ALL_NON_NUMERIC_DEVICE_CLASSES,
    ALWAYS_NUMERIC_DOMAINS,
    COMMON_NUMERIC_SENSOR_DEVICE_CLASSES,
    NEVER_NUMERIC_DOMAINS,
    NON_NUMERIC_BINARY_SENSOR_DEVICE_CLASSES,
    NON_NUMERIC_SENSOR_DEVICE_CLASSES,
    VALID_HA_DOMAINS,
    classify_domain_numeric_expectation,
    is_device_class_numeric,
    is_valid_ha_domain,
)


class TestDeviceClassConstants:
    """Test device class constant definitions."""

    def test_non_numeric_sensor_device_classes(self):
        """Test non-numeric sensor device classes are correctly defined."""
        expected = {
            SensorDeviceClass.DATE,
            SensorDeviceClass.ENUM,
            SensorDeviceClass.TIMESTAMP,
        }
        assert expected == NON_NUMERIC_SENSOR_DEVICE_CLASSES

    def test_binary_sensor_device_classes_comprehensive(self):
        """Test that binary sensor device classes are properly defined."""
        # Test that we have a reasonable number of binary sensor device classes
        # (Home Assistant has around 25+ binary sensor device classes)
        assert len(NON_NUMERIC_BINARY_SENSOR_DEVICE_CLASSES) >= 20

        # Test that some key binary sensor device classes are included
        expected_classes = {
            BinarySensorDeviceClass.DOOR,
            BinarySensorDeviceClass.WINDOW,
            BinarySensorDeviceClass.MOTION,
            BinarySensorDeviceClass.CONNECTIVITY,
            BinarySensorDeviceClass.BATTERY,
        }

        # Check that expected classes are in our constants
        for device_class in expected_classes:
            assert device_class in NON_NUMERIC_BINARY_SENSOR_DEVICE_CLASSES, (
                f"Expected binary sensor device class {device_class} not found"
            )

    def test_combined_non_numeric_classes(self):
        """Test that combined set includes both sensor and binary sensor classes."""
        expected = NON_NUMERIC_SENSOR_DEVICE_CLASSES | NON_NUMERIC_BINARY_SENSOR_DEVICE_CLASSES
        assert expected == ALL_NON_NUMERIC_DEVICE_CLASSES

    def test_numeric_sensor_classes_are_actually_numeric(self):
        """Test that numeric sensor classes don't overlap with non-numeric ones."""
        # There should be no overlap between numeric and non-numeric sensor classes
        overlap = COMMON_NUMERIC_SENSOR_DEVICE_CLASSES & NON_NUMERIC_SENSOR_DEVICE_CLASSES
        assert len(overlap) == 0, f"Found overlap: {overlap}"


class TestIsDeviceClassNumeric:
    """Test the is_device_class_numeric function."""

    def test_numeric_sensor_device_classes(self):
        """Test that numeric sensor device classes are correctly identified."""
        numeric_classes = [
            SensorDeviceClass.TEMPERATURE,
            SensorDeviceClass.HUMIDITY,
            SensorDeviceClass.PRESSURE,
            SensorDeviceClass.BATTERY,
            SensorDeviceClass.POWER,
            SensorDeviceClass.ENERGY,
            SensorDeviceClass.VOLTAGE,
            SensorDeviceClass.CURRENT,
        ]

        for device_class in numeric_classes:
            assert is_device_class_numeric(device_class), f"{device_class} should be numeric"

    def test_non_numeric_sensor_device_classes(self):
        """Test that non-numeric sensor device classes are correctly identified."""
        non_numeric_classes = [
            SensorDeviceClass.DATE,
            SensorDeviceClass.ENUM,
            SensorDeviceClass.TIMESTAMP,
        ]

        for device_class in non_numeric_classes:
            assert not is_device_class_numeric(device_class), f"{device_class} should be non-numeric"

    def test_binary_sensor_device_classes_are_non_numeric(self):
        """Test that all binary sensor device classes are non-numeric."""
        binary_classes = [
            BinarySensorDeviceClass.DOOR,
            BinarySensorDeviceClass.WINDOW,
            BinarySensorDeviceClass.MOTION,
            BinarySensorDeviceClass.OCCUPANCY,
            BinarySensorDeviceClass.CONNECTIVITY,
            BinarySensorDeviceClass.BATTERY,
            BinarySensorDeviceClass.PROBLEM,
        ]

        for device_class in binary_classes:
            assert not is_device_class_numeric(device_class), f"{device_class} should be non-numeric"

    def test_unknown_device_class_defaults_to_numeric(self):
        """Test that unknown device classes default to numeric."""
        # Unknown or custom device classes should default to numeric
        assert is_device_class_numeric("custom_device_class")
        assert is_device_class_numeric("unknown")
        assert is_device_class_numeric("")

    def test_none_device_class_defaults_to_numeric(self):
        """Test that None device class defaults to numeric."""
        # None should be treated as numeric (no device class specified)
        assert is_device_class_numeric(None)


class TestDeviceClassIntegration:
    """Test integration with actual Home Assistant device classes."""

    def test_all_sensor_device_classes_are_handled(self):
        """Test that our logic handles all available sensor device classes."""
        # Get all available sensor device classes from HA
        all_sensor_classes = {getattr(SensorDeviceClass, attr) for attr in dir(SensorDeviceClass) if not attr.startswith("_")}

        # Each should be classified as either numeric or non-numeric
        for device_class in all_sensor_classes:
            result = is_device_class_numeric(device_class)
            assert isinstance(result, bool), f"Device class {device_class} should return boolean"

    def test_all_binary_sensor_device_classes_are_non_numeric(self):
        """Test that all binary sensor device classes are correctly non-numeric."""
        # Test a representative sample of binary sensor device classes
        sample_binary_classes = [
            BinarySensorDeviceClass.DOOR,
            BinarySensorDeviceClass.WINDOW,
            BinarySensorDeviceClass.MOTION,
            BinarySensorDeviceClass.CONNECTIVITY,
            BinarySensorDeviceClass.BATTERY,
            BinarySensorDeviceClass.PROBLEM,
            BinarySensorDeviceClass.SAFETY,
            BinarySensorDeviceClass.SMOKE,
            BinarySensorDeviceClass.SOUND,
            BinarySensorDeviceClass.TAMPER,
        ]

        # All binary sensor device classes should be non-numeric
        for device_class in sample_binary_classes:
            assert not is_device_class_numeric(device_class), f"Binary sensor device class {device_class} should be non-numeric"

    def test_specific_numeric_examples(self):
        """Test specific examples that should be numeric."""
        numeric_examples = [
            SensorDeviceClass.TEMPERATURE,  # Temperature sensors
            SensorDeviceClass.HUMIDITY,  # Humidity sensors
            SensorDeviceClass.POWER,  # Power meters
            SensorDeviceClass.ENERGY,  # Energy meters
            SensorDeviceClass.VOLTAGE,  # Voltage sensors
            SensorDeviceClass.CURRENT,  # Current sensors
            SensorDeviceClass.FREQUENCY,  # Frequency sensors
            SensorDeviceClass.PRESSURE,  # Pressure sensors
            SensorDeviceClass.SPEED,  # Speed sensors
            SensorDeviceClass.DISTANCE,  # Distance sensors
        ]

        for device_class in numeric_examples:
            assert is_device_class_numeric(device_class), f"{device_class} should be numeric but was classified as non-numeric"

    def test_specific_non_numeric_examples(self):
        """Test specific examples that should be non-numeric."""
        non_numeric_examples = [
            SensorDeviceClass.DATE,  # Date values
            SensorDeviceClass.TIMESTAMP,  # Timestamp values
            SensorDeviceClass.ENUM,  # Enumerated values
            BinarySensorDeviceClass.DOOR,  # Door open/closed
            BinarySensorDeviceClass.MOTION,  # Motion detected/not detected
            BinarySensorDeviceClass.CONNECTIVITY,  # Connected/disconnected
        ]

        for device_class in non_numeric_examples:
            assert not is_device_class_numeric(device_class), (
                f"{device_class} should be non-numeric but was classified as numeric"
            )


class TestDomainClassification:
    """Test domain classification functionality."""

    def test_always_numeric_domains(self):
        """Test that always numeric domains are correctly classified."""
        always_numeric = ["input_number", "counter", "number"]

        for domain in always_numeric:
            assert classify_domain_numeric_expectation(domain) is True, f"Domain {domain} should always be numeric"
            assert domain in ALWAYS_NUMERIC_DOMAINS, f"Domain {domain} should be in ALWAYS_NUMERIC_DOMAINS"

    def test_never_numeric_domains(self):
        """Test that never numeric domains are correctly classified."""
        never_numeric = [
            "binary_sensor",
            "switch",
            "input_boolean",
            "device_tracker",
            "weather",
            "climate",
            "media_player",
            "light",
            "fan",
            "cover",
            "alarm_control_panel",
            "lock",
            "vacuum",
        ]

        for domain in never_numeric:
            assert classify_domain_numeric_expectation(domain) is False, f"Domain {domain} should never be numeric"
            assert domain in NEVER_NUMERIC_DOMAINS, f"Domain {domain} should be in NEVER_NUMERIC_DOMAINS"

    def test_requires_analysis_domains(self):
        """Test that some domains require further analysis."""
        requires_analysis = ["sensor"]  # sensor domain depends on device_class

        for domain in requires_analysis:
            assert classify_domain_numeric_expectation(domain) is None, f"Domain {domain} should require further analysis"

    def test_unknown_domain_requires_analysis(self):
        """Test that unknown domains require analysis."""
        unknown_domains = ["custom_domain", "unknown", ""]

        for domain in unknown_domains:
            assert classify_domain_numeric_expectation(domain) is None, f"Unknown domain {domain} should require analysis"

    def test_valid_ha_domains(self):
        """Test that valid Home Assistant domains are correctly identified."""
        valid_domains = [
            "sensor",
            "binary_sensor",
            "switch",
            "light",
            "fan",
            "cover",
            "climate",
            "lock",
            "vacuum",
            "media_player",
            "device_tracker",
            "weather",
            "camera",
            "alarm_control_panel",
            "button",
            "number",
            "input_number",
            "input_boolean",
            "counter",
            "timer",
            "automation",
        ]

        for domain in valid_domains:
            assert is_valid_ha_domain(domain), f"Domain {domain} should be valid"
            assert domain in VALID_HA_DOMAINS, f"Domain {domain} should be in VALID_HA_DOMAINS"

    def test_invalid_ha_domains(self):
        """Test that invalid domains are correctly identified."""
        invalid_domains = ["invalid_domain", "custom", "", "not_a_domain"]

        for domain in invalid_domains:
            assert not is_valid_ha_domain(domain), f"Domain {domain} should be invalid"

    def test_domain_constants_no_overlap(self):
        """Test that domain constants don't overlap."""
        # Always numeric and never numeric domains should not overlap
        overlap = ALWAYS_NUMERIC_DOMAINS & NEVER_NUMERIC_DOMAINS
        assert len(overlap) == 0, f"Found overlap between always and never numeric domains: {overlap}"

        # All domain constants should be valid HA domains
        for domain in ALWAYS_NUMERIC_DOMAINS:
            assert domain in VALID_HA_DOMAINS, f"Always numeric domain {domain} should be in valid domains"

        for domain in NEVER_NUMERIC_DOMAINS:
            assert domain in VALID_HA_DOMAINS, f"Never numeric domain {domain} should be in valid domains"
