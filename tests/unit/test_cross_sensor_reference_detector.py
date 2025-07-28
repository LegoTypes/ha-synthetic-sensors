"""Tests for CrossSensorReferenceDetector."""

import pytest

from ha_synthetic_sensors.cross_sensor_reference_detector import CrossSensorReferenceDetector


class TestCrossSensorReferenceDetector:
    """Test cross-sensor reference detection functionality."""

    @pytest.fixture
    def detector(self):
        """Create a CrossSensorReferenceDetector instance."""
        return CrossSensorReferenceDetector()

    def test_scan_yaml_simple_reference(self, detector):
        """Test detection of simple cross-sensor reference."""
        yaml_data = {"sensors": {"base_power": {"formula": "state * 1.0"}, "derived_power": {"formula": "base_power * 1.1"}}}

        result = detector.scan_yaml_references(yaml_data)

        assert result == {"derived_power": {"base_power"}}

    def test_scan_yaml_multiple_references(self, detector):
        """Test detection of multiple cross-sensor references."""
        yaml_data = {
            "sensors": {
                "base_power": {"formula": "state * 1.0"},
                "solar_power": {"formula": "state * 0.8"},
                "total_power": {"formula": "base_power + solar_power"},
                "efficiency": {"formula": "solar_power / total_power * 100"},
            }
        }

        result = detector.scan_yaml_references(yaml_data)

        expected = {"total_power": {"base_power", "solar_power"}, "efficiency": {"solar_power", "total_power"}}
        assert result == expected

    def test_scan_yaml_attribute_references(self, detector):
        """Test detection of cross-sensor references in attribute formulas."""
        yaml_data = {
            "sensors": {
                "base_power": {"formula": "state * 1.0"},
                "derived_power": {
                    "formula": "base_power * 1.1",
                    "attributes": {
                        "daily": {"formula": "base_power * 24"},
                        "efficiency": {"formula": "derived_power / base_power * 100"},
                    },
                },
            }
        }

        result = detector.scan_yaml_references(yaml_data)

        # derived_power references base_power in main formula and attribute formulas
        # Plus it references itself (derived_power) in one attribute formula
        expected = {"derived_power": {"base_power", "derived_power"}}
        assert result == expected

    def test_scan_yaml_parent_sensor_reference(self, detector):
        """Test detection of parent sensor references in attributes (key use case)."""
        yaml_data = {
            "sensors": {
                "power_analyzer": {
                    "formula": "state * 1.1",
                    "attributes": {
                        "doubled_value": {
                            "formula": "power_analyzer * 2"  # References parent sensor by key
                        }
                    },
                }
            }
        }

        result = detector.scan_yaml_references(yaml_data)

        # power_analyzer references itself in attribute formula
        expected = {
            "power_analyzer": {"power_analyzer"}  # Self-reference detected
        }
        assert result == expected

    def test_scan_yaml_no_references(self, detector):
        """Test handling of sensors with no cross-sensor references."""
        yaml_data = {
            "sensors": {
                "independent_sensor": {"formula": "state * 2.0"},
                "another_sensor": {"formula": "sensor.external_entity + 10"},
            }
        }

        result = detector.scan_yaml_references(yaml_data)

        # No cross-sensor references detected
        assert result == {}

    def test_tokenize_formula(self, detector):
        """Test formula tokenization."""
        formula = "base_power_sensor * 1.1 + solar_power - 50"

        tokens = detector._tokenize_formula(formula)

        expected = {"base_power_sensor", "solar_power"}
        assert tokens == expected

    def test_tokenize_formula_excludes_keywords(self, detector):
        """Test that common keywords are excluded from tokenization."""
        formula = "sum(base_power) + max(solar_power) if state > 0 else 0"

        tokens = detector._tokenize_formula(formula)

        # Should exclude 'sum', 'max', 'if', 'else', 'state'
        expected = {"base_power", "solar_power"}
        assert tokens == expected

    def test_extract_references_from_formula(self, detector):
        """Test extraction of sensor references from formula."""
        formula = "base_power * efficiency_factor + solar_power"
        sensor_keys = {"base_power", "solar_power", "wind_power"}

        result = detector._extract_references_from_formula(formula, sensor_keys)

        expected = {"base_power", "solar_power"}
        assert result == expected

    def test_analyze_dependency_order_simple(self, detector):
        """Test dependency order analysis for simple case."""
        reference_map = {"derived_power": {"base_power"}, "efficiency": {"derived_power", "base_power"}}

        result = detector.analyze_dependency_order(reference_map)

        # base_power should come first (no dependencies)
        # derived_power should come second (depends on base_power)
        # efficiency should come last (depends on both)
        assert result.index("base_power") < result.index("derived_power")
        assert result.index("derived_power") < result.index("efficiency")

    def test_analyze_dependency_order_circular(self, detector):
        """Test detection of circular dependencies."""
        reference_map = {
            "sensor_a": {"sensor_b"},
            "sensor_b": {"sensor_a"},  # Circular!
        }

        with pytest.raises(ValueError, match="Circular dependencies detected"):
            detector.analyze_dependency_order(reference_map)

    def test_validate_references_valid(self, detector):
        """Test validation of valid references."""
        reference_map = {"derived_power": {"base_power"}, "efficiency": {"derived_power", "base_power"}}
        available_sensors = {"base_power", "derived_power", "efficiency"}

        # Should not raise exception for valid references
        result = detector.validate_references(reference_map, available_sensors)
        assert result == {}

    def test_validate_references_missing(self, detector):
        """Test validation catches missing references."""
        reference_map = {"derived_power": {"base_power", "missing_sensor"}, "efficiency": {"nonexistent_sensor"}}
        available_sensors = {"base_power", "derived_power", "efficiency"}

        with pytest.raises(ValueError, match="Missing sensor references"):
            detector.validate_references(reference_map, available_sensors)

    def test_empty_yaml_data(self, detector):
        """Test handling of empty YAML data."""
        result = detector.scan_yaml_references({})
        assert result == {}

        result = detector.scan_yaml_references({"sensors": {}})
        assert result == {}

    def test_invalid_yaml_structure(self, detector):
        """Test handling of invalid YAML structure."""
        yaml_data = {"sensors": "invalid_structure"}

        result = detector.scan_yaml_references(yaml_data)
        assert result == {}
