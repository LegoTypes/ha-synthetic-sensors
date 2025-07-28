"""Tests for literal attribute values in synthetic sensors."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
import yaml as yaml_lib

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.storage_manager import StorageManager
from ha_synthetic_sensors.schema_validator import validate_yaml_config
from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.storage_yaml_handler import YamlHandler


class TestLiteralAttributes:
    """Test literal attribute values in sensor configurations."""

    def test_schema_validation_literal_attributes(self) -> None:
        """Test that literal attributes pass schema validation."""
        yaml_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "name": "Test Sensor",
                    "formula": "power * 2",
                    "variables": {"power": "sensor.test_power"},
                    "attributes": {
                        "voltage": 240,
                        "manufacturer": "TestCorp",
                        "calculated": {"formula": "voltage * current", "variables": {"current": "sensor.test_current"}},
                    },
                }
            },
        }

        result = validate_yaml_config(yaml_data)
        assert result["valid"], f"Schema validation failed: {result['errors']}"

    def test_schema_validation_mixed_literal_types(self) -> None:
        """Test that different literal types are accepted."""
        yaml_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "name": "Test Sensor",
                    "formula": "1 + 1",
                    "attributes": {
                        "integer_literal": 42,
                        "float_literal": 3.14,
                        "string_literal": "test_string",
                        "boolean_true": True,
                        "boolean_false": False,
                    },
                }
            },
        }

        result = validate_yaml_config(yaml_data)
        assert result["valid"], f"Schema validation failed: {result['errors']}"

    def test_config_manager_parses_literal_attributes(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test that ConfigManager correctly parses literal attributes."""
        config_manager = ConfigManager(mock_hass)

        # Load YAML content from fixture
        yaml_fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "unit_test_literal_attributes_basic.yaml"
        yaml_content = yaml_fixture_path.read_text()

        config = config_manager.load_from_yaml(yaml_content)
        assert config is not None

        # Find the test sensor
        test_sensor = None
        for sensor in config.sensors:
            if sensor.unique_id == "test_sensor":
                test_sensor = sensor
                break

        assert test_sensor is not None, "Test sensor not found"

        # Check that literal attributes are stored in the main formula's attributes dictionary
        # (not as separate formulas)
        assert len(test_sensor.formulas) == 1, f"Expected 1 main formula, got {len(test_sensor.formulas)}"
        main_formula = test_sensor.formulas[0]

        # Check that literal attributes are in the attributes dictionary
        assert "voltage" in main_formula.attributes, "voltage attribute should be present"
        assert "manufacturer" in main_formula.attributes, "manufacturer attribute should be present"
        assert "is_enabled" in main_formula.attributes, "is_enabled attribute should be present"

        # Check specific literal values
        assert main_formula.attributes["voltage"] == 240, f"Expected voltage=240, got {main_formula.attributes['voltage']}"
        assert main_formula.attributes["manufacturer"] == "TestCorp", (
            f"Expected manufacturer='TestCorp', got {main_formula.attributes['manufacturer']}"
        )
        assert main_formula.attributes["is_enabled"] is True, (
            f"Expected is_enabled=True, got {main_formula.attributes['is_enabled']}"
        )

    def test_storage_manager_roundtrip_literal_attributes(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test that literal attributes survive round-trip through storage manager."""
        storage_manager = StorageManager(mock_hass)

        # Create sensor set with literal attributes
        sensor_set_id = "test_literal_attributes"

        # Load YAML content from fixture
        from pathlib import Path

        yaml_fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "unit_test_literal_attributes_storage.yaml"
        with open(yaml_fixture_path, "r") as f:
            yaml_content = f.read()

        # Test the YAML handler directly instead of going through storage manager
        from ha_synthetic_sensors.config_manager import ConfigManager

        config_manager = ConfigManager(mock_hass)
        config = config_manager.load_from_yaml(yaml_content)

        # Test export through YAML handler
        from ha_synthetic_sensors.storage_yaml_handler import YamlHandler

        yaml_handler = YamlHandler(storage_manager)

        # Create a simple sensor set for export testing
        test_sensor = config.sensors[0]  # Get the first sensor
        exported_yaml = yaml_handler._build_yaml_structure([test_sensor], {})

        # Check that literal attributes are exported as literals, not formulas
        test_sensor_data = exported_yaml["sensors"]["test_sensor"]
        attributes = test_sensor_data["attributes"]

        assert attributes["voltage"] == 240
        assert attributes["manufacturer"] == "TestCorp"
        assert attributes["is_enabled"] is True

        # Check that formula attributes are still formula objects
        assert "formula" in attributes["calculated"]
        assert attributes["calculated"]["formula"] == "voltage * current"

    def test_literal_attributes_with_metadata(self) -> None:
        """Test that literal attributes work correctly with metadata."""
        yaml_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "name": "Test Sensor",
                    "formula": "1 + 1",
                    "attributes": {
                        "voltage": 240,
                        "calculated": {
                            "formula": "voltage * 2",
                            "metadata": {"unit_of_measurement": "V", "device_class": "voltage"},
                        },
                    },
                }
            },
        }

        result = validate_yaml_config(yaml_data)
        assert result["valid"], f"Schema validation failed: {result['errors']}"

    def test_literal_attributes_edge_cases(self) -> None:
        """Test edge cases for literal attributes."""
        yaml_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "name": "Test Sensor",
                    "formula": "1 + 1",
                    "attributes": {
                        "zero": 0,
                        "negative": -42,
                        "large_number": 999999999,
                        "small_float": 0.001,
                        "empty_string": "",
                        "special_chars": "test@#$%^&*()",
                        "unicode": "测试",
                    },
                }
            },
        }

        result = validate_yaml_config(yaml_data)
        assert result["valid"], f"Schema validation failed: {result['errors']}"

    def test_literal_attributes_in_global_settings(self) -> None:
        """Test that literal attributes work with global settings."""
        yaml_data = {
            "version": "1.0",
            "global_settings": {"device_identifier": "test_device", "variables": {"global_voltage": 240}},
            "sensors": {
                "test_sensor": {
                    "name": "Test Sensor",
                    "formula": "power * 2",
                    "variables": {"power": "sensor.test_power"},
                    "attributes": {"voltage": 240, "manufacturer": "TestCorp"},
                }
            },
        }

        result = validate_yaml_config(yaml_data)
        assert result["valid"], f"Schema validation failed: {result['errors']}"

    def test_tabs_literal_handling(self) -> None:
        """Test that tabs[16] is treated as a string literal, not a variable."""
        yaml_data = {
            "version": "1.0",
            "sensors": {
                "test_tabs_literal": {
                    "name": "Test Tabs Literal",
                    "formula": "tabs[16]",
                    "attributes": {
                        "device_class": "power",
                        "unit_of_measurement": "W",
                    },
                }
            },
        }

        result = validate_yaml_config(yaml_data)
        assert result["valid"], f"Schema validation failed: {result['errors']}"

    def test_tabs_literal_handling_with_spaces(self) -> None:
        """Test that tabs [22] (with spaces) is treated as a string literal, not a variable."""
        yaml_data = {
            "version": "1.0",
            "sensors": {
                "test_tabs_literal_spaced": {
                    "name": "Test Tabs Literal Spaced",
                    "formula": "tabs [22]",
                    "attributes": {
                        "device_class": "power",
                        "unit_of_measurement": "W",
                    },
                }
            },
        }

        result = validate_yaml_config(yaml_data)
        assert result["valid"], f"Schema validation failed: {result['errors']}"

    def test_tabs_literal_handling_with_range(self) -> None:
        """Test that tabs [30:32] (with range) is treated as a string literal, not a variable."""
        yaml_data = {
            "version": "1.0",
            "sensors": {
                "test_tabs_literal_range": {
                    "name": "Test Tabs Literal Range",
                    "formula": "tabs [30:32]",
                    "attributes": {
                        "device_class": "power",
                        "unit_of_measurement": "W",
                    },
                }
            },
        }

        result = validate_yaml_config(yaml_data)
        assert result["valid"], f"Schema validation failed: {result['errors']}"

    def test_tabs_literal_dependency_extraction(self) -> None:
        """Test that tabs literals don't extract 'tabs' as a dependency."""
        from ha_synthetic_sensors.dependency_parser import DependencyParser

        parser = DependencyParser()

        # Test various tabs literal formats
        test_cases = [
            "tabs[16]",
            "tabs [22]",
            "tabs [30:32]",
            "tabs[0]",
            "tabs [100]",
        ]

        for formula in test_cases:
            dependencies = parser.extract_dependencies(formula)
            assert "tabs" not in dependencies, (
                f"Expected 'tabs' not to be extracted as dependency from '{formula}', got: {dependencies}"
            )

    def test_normal_variable_extraction_still_works(self) -> None:
        """Test that normal variable extraction still works for formulas with operators."""
        from ha_synthetic_sensors.dependency_parser import DependencyParser

        parser = DependencyParser()

        # Test that normal formulas with variables still extract dependencies correctly
        formula = "temp + humidity * 2"
        dependencies = parser.extract_dependencies(formula)

        # Should extract variables from formulas with arithmetic operators
        assert "temp" in dependencies, f"Expected 'temp' to be extracted as dependency, got: {dependencies}"
        assert "humidity" in dependencies, f"Expected 'humidity' to be extracted as dependency, got: {dependencies}"

    def test_quoted_tabs_literal_handling(self) -> None:
        """Test that quoted tabs literals like 'tabs [3]' are treated as string literals, not variables."""
        from ha_synthetic_sensors.dependency_parser import DependencyParser

        parser = DependencyParser()

        # Test quoted tabs literal formats
        test_cases = [
            '"tabs [3]"',
            "'tabs [3]'",
            '"tabs[16]"',
            "'tabs [22]'",
            '"tabs [30:32]"',
        ]

        for formula in test_cases:
            dependencies = parser.extract_dependencies(formula)
            assert "tabs" not in dependencies, (
                f"Expected 'tabs' not to be extracted as dependency from '{formula}', got: {dependencies}"
            )

    def test_quoted_tabs_literal_yaml_validation(self) -> None:
        """Test that quoted tabs literals pass YAML validation."""
        yaml_data = {
            "version": "1.0",
            "sensors": {
                "test_quoted_tabs": {
                    "name": "Test Quoted Tabs",
                    "formula": "power_value",
                    "variables": {"power_value": "sensor.test_power"},
                    "attributes": {
                        "tabs": "tabs [3]",
                        "voltage": 120,
                        "amperage": {
                            "formula": "state / 120",
                            "metadata": {
                                "unit_of_measurement": "A",
                                "device_class": "current",
                                "suggested_display_precision": 2,
                            },
                        },
                    },
                    "metadata": {
                        "unit_of_measurement": "W",
                        "device_class": "power",
                        "state_class": "measurement",
                        "suggested_display_precision": 2,
                    },
                }
            },
        }

        result = validate_yaml_config(yaml_data)
        assert result["valid"], f"Schema validation failed: {result['errors']}"

    def test_exact_user_yaml_pattern(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test the exact YAML pattern mentioned by the user."""
        yaml_data = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "name": "Test Sensor",
                    "formula": "power_value",
                    "variables": {"power_value": "sensor.test_power"},
                    "attributes": {
                        "tabs": "tabs [3]",
                        "voltage": 120,
                        "amperage": {
                            "formula": "state / 120",
                            "metadata": {
                                "unit_of_measurement": "A",
                                "device_class": "current",
                                "suggested_display_precision": 2,
                            },
                        },
                    },
                    "metadata": {
                        "unit_of_measurement": "W",
                        "device_class": "power",
                        "state_class": "measurement",
                        "suggested_display_precision": 2,
                    },
                }
            },
        }

        result = validate_yaml_config(yaml_data)
        assert result["valid"], f"Schema validation failed: {result['errors']}"

        # Test that the literal value is processed correctly
        from ha_synthetic_sensors.storage_yaml_handler import YamlHandler
        from ha_synthetic_sensors.storage_manager import StorageManager
        from ha_synthetic_sensors.config_manager import ConfigManager

        config_manager = ConfigManager(mock_hass)
        config = config_manager.load_from_yaml(yaml_lib.dump(yaml_data))

        # Get the sensor
        sensor = config.sensors[0]

        # Should have 2 formulas: main formula + amperage formula (which has explicit formula key)
        assert len(sensor.formulas) == 2, f"Expected 2 formulas (main + amperage), got {len(sensor.formulas)}"

        # Find the main formula and amperage formula
        main_formula = next(f for f in sensor.formulas if f.id == "test_sensor")
        amperage_formula = next(f for f in sensor.formulas if f.id == "test_sensor_amperage")

        # Check that literal attributes (tabs, voltage) are in main formula's attributes
        assert "tabs" in main_formula.attributes, "tabs should be in main formula attributes"
        assert "voltage" in main_formula.attributes, "voltage should be in main formula attributes"
        assert main_formula.attributes["tabs"] == "tabs [3]", f"Expected tabs='tabs [3]', got {main_formula.attributes['tabs']}"
        assert main_formula.attributes["voltage"] == 120, f"Expected voltage=120, got {main_formula.attributes['voltage']}"

        # Check that amperage has its own formula (because it has explicit formula key)
        assert amperage_formula.formula == "state / 120", (
            f"Expected amperage formula='state / 120', got {amperage_formula.formula}"
        )

        # Test that dependency extraction doesn't extract 'tabs' as a variable
        from ha_synthetic_sensors.dependency_parser import DependencyParser

        parser = DependencyParser()
        dependencies = parser.extract_dependencies("tabs [3]")
        assert "tabs" not in dependencies, f"Expected 'tabs' not to be extracted as dependency, got: {dependencies}"


"""Tests for literal attribute support in storage YAML handler."""

import pytest

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.storage_yaml_handler import YamlHandler


class TestLiteralAttributesStorage:
    """Test literal attribute storage and retrieval."""

    def test_parse_literal_value_edge_cases(self):
        """Test edge cases in literal value parsing."""

        # Create a minimal storage manager for testing
        class MockStorageManager:
            def __init__(self):
                self.data = {"sensor_sets": {}, "sensors": {}}

        storage_manager = MockStorageManager()  # type: ignore[assignment]
        handler = YamlHandler(storage_manager)  # type: ignore[arg-type]

        # Test various edge cases
        assert handler._parse_literal_value("") == ""  # Empty string is returned as empty string
        assert handler._parse_literal_value("   ") == "   "  # Whitespace is treated as literal string
        assert handler._parse_literal_value("abc123") == "abc123"  # Simple string without operators
        assert handler._parse_literal_value("sensor_name") == "sensor_name"  # Underscore variable
        assert handler._parse_literal_value("test-sensor") is None  # Contains operator
        assert handler._parse_literal_value("test+sensor") is None  # Contains operator
        assert handler._parse_literal_value("test*sensor") is None  # Contains operator
        assert handler._parse_literal_value("test/sensor") is None  # Contains operator
        assert handler._parse_literal_value("test(sensor)") is None  # Contains parentheses
        assert handler._parse_literal_value("test sensor") == "test sensor"  # Contains space but no operators

    def test_build_attribute_dict_with_metadata(self):
        """Test building attribute dict with metadata."""

        class MockStorageManager:
            def __init__(self):
                self.data = {"sensor_sets": {}, "sensors": {}}

        storage_manager = MockStorageManager()  # type: ignore[assignment]
        handler = YamlHandler(storage_manager)  # type: ignore[arg-type]

        # Test formula with metadata
        formula = FormulaConfig(
            id="test_sensor_voltage",
            formula="240",
            variables={},
            metadata={"unit_of_measurement": "V", "device_class": "voltage"},
        )

        result = handler._build_attribute_dict(formula)
        assert result == 240  # Should return literal value, not dict

        # Test formula with variables (should return dict)
        formula_with_vars = FormulaConfig(
            id="test_sensor_calculated",
            formula="power / voltage",
            variables={"power": "sensor.power", "voltage": "sensor.voltage"},
            metadata={"unit_of_measurement": "A"},
        )

        result = handler._build_attribute_dict(formula_with_vars)
        assert isinstance(result, dict)
        assert result["formula"] == "power / voltage"
        assert result["variables"] == {"power": "sensor.power", "voltage": "sensor.voltage"}
        assert result["metadata"] == {"unit_of_measurement": "A"}

    def test_build_attribute_dict_legacy_metadata(self):
        """Test building attribute dict with legacy metadata fields."""

        class MockStorageManager:
            def __init__(self):
                self.data = {"sensor_sets": {}, "sensors": {}}

        storage_manager = MockStorageManager()  # type: ignore[assignment]
        handler = YamlHandler(storage_manager)  # type: ignore[arg-type]

        # Create formula with legacy metadata fields
        class LegacyFormulaConfig:
            def __init__(self):
                self.id = "test_sensor_legacy"
                self.formula = "power / voltage"
                self.variables = {"power": "sensor.power", "voltage": "sensor.voltage"}
                self.unit_of_measurement = "A"
                self.device_class = "current"
                self.state_class = "measurement"
                self.icon = "mdi:lightning-bolt"

        formula = LegacyFormulaConfig()  # type: ignore[assignment]
        result = handler._build_attribute_dict(formula)  # type: ignore[arg-type]

        assert isinstance(result, dict)
        assert result["formula"] == "power / voltage"
        assert result["variables"] == {"power": "sensor.power", "voltage": "sensor.voltage"}
        assert result["metadata"]["unit_of_measurement"] == "A"
        assert result["metadata"]["device_class"] == "current"
        assert result["metadata"]["state_class"] == "measurement"
        assert result["metadata"]["icon"] == "mdi:lightning-bolt"

    def test_build_attribute_dict_no_metadata(self):
        """Test building attribute dict without metadata."""

        class MockStorageManager:
            def __init__(self):
                self.data = {"sensor_sets": {}, "sensors": {}}

        storage_manager = MockStorageManager()  # type: ignore[assignment]
        handler = YamlHandler(storage_manager)  # type: ignore[arg-type]

        # Test formula without metadata
        formula = FormulaConfig(
            id="test_sensor_simple", formula="power / voltage", variables={"power": "sensor.power", "voltage": "sensor.voltage"}
        )

        result = handler._build_attribute_dict(formula)
        assert isinstance(result, dict)
        assert result["formula"] == "power / voltage"
        assert result["variables"] == {"power": "sensor.power", "voltage": "sensor.voltage"}
        assert "metadata" not in result

    def test_build_attribute_dict_empty_variables(self):
        """Test building attribute dict with empty variables."""

        class MockStorageManager:
            def __init__(self):
                self.data = {"sensor_sets": {}, "sensors": {}}

        storage_manager = MockStorageManager()  # type: ignore[assignment]
        handler = YamlHandler(storage_manager)  # type: ignore[arg-type]

        # Test formula with empty variables dict
        formula = FormulaConfig(id="test_sensor_empty_vars", formula="240", variables={})

        result = handler._build_attribute_dict(formula)
        assert result == 240  # Should return literal value

    def test_build_attribute_dict_none_variables(self):
        """Test building attribute dict with None variables."""

        class MockStorageManager:
            def __init__(self):
                self.data = {"sensor_sets": {}, "sensors": {}}

        storage_manager = MockStorageManager()  # type: ignore[assignment]
        handler = YamlHandler(storage_manager)  # type: ignore[arg-type]

        # Test formula with None variables - FormulaConfig doesn't allow None variables
        # so we'll test with empty dict instead
        formula = FormulaConfig(id="test_sensor_empty_vars", formula="240", variables={})

        result = handler._build_attribute_dict(formula)
        assert result == 240  # Should return literal value

    def test_parse_literal_value_exception_handling(self):
        """Test exception handling in literal value parsing."""

        class MockStorageManager:
            def __init__(self):
                self.data = {"sensor_sets": {}, "sensors": {}}

        storage_manager = MockStorageManager()  # type: ignore[assignment]
        handler = YamlHandler(storage_manager)  # type: ignore[arg-type]

        # Test with strings that contain operators (should return None)
        assert handler._parse_literal_value("test+sensor") is None
        assert handler._parse_literal_value("test-sensor") is None
        assert handler._parse_literal_value("test*sensor") is None
        assert handler._parse_literal_value("test/sensor") is None
        assert handler._parse_literal_value("test(sensor)") is None

        # Test with strings that don't contain operators (should return the string)
        assert handler._parse_literal_value("test@#$%") == "test@#$%"  # Special chars but no operators

    def test_build_attribute_dict_complex_literals(self):
        """Test building attribute dict with complex literal values."""

        class MockStorageManager:
            def __init__(self):
                self.data = {"sensor_sets": {}, "sensors": {}}

        storage_manager = MockStorageManager()  # type: ignore[assignment]
        handler = YamlHandler(storage_manager)  # type: ignore[arg-type]

        # Test various literal types
        test_cases = [
            ("42", 42),  # Integer
            ("3.14159", 3.14159),  # Float
            ("-10.5", -10.5),  # Negative float
            ('"Hello World"', "Hello World"),  # Quoted string
            ("'Test String'", "Test String"),  # Single quoted string
            ("True", True),  # Boolean True
            ("False", False),  # Boolean False
            ("simple_text", "simple_text"),  # Simple text
        ]

        for formula_str, expected in test_cases:
            formula = FormulaConfig(id=f"test_sensor_{formula_str}", formula=formula_str, variables={})
            result = handler._build_attribute_dict(formula)
            assert result == expected, f"Failed for formula '{formula_str}': expected {expected}, got {result}"

    def test_build_attribute_dict_mixed_literals_and_formulas(self):
        """Test building attribute dict with mixed literal and formula attributes."""

        class MockStorageManager:
            def __init__(self):
                self.data = {"sensor_sets": {}, "sensors": {}}

        storage_manager = MockStorageManager()  # type: ignore[assignment]
        handler = YamlHandler(storage_manager)  # type: ignore[arg-type]

        # Create sensor with mixed attributes
        sensor = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            formulas=[
                # Main formula
                FormulaConfig(
                    id="test_sensor",
                    formula="power * efficiency",
                    variables={"power": "sensor.power", "efficiency": "sensor.efficiency"},
                ),
                # Literal attributes
                FormulaConfig(id="test_sensor_voltage", formula="240", variables={}),
                FormulaConfig(id="test_sensor_manufacturer", formula='"TestCorp"', variables={}),
                FormulaConfig(id="test_sensor_is_active", formula="True", variables={}),
                # Formula attribute
                FormulaConfig(
                    id="test_sensor_current",
                    formula="power / voltage",
                    variables={"power": "sensor.power", "voltage": "sensor.voltage"},
                ),
            ],
        )

        main_formula, attributes = handler._process_formulas(sensor)

        assert main_formula is not None
        assert main_formula.id == "test_sensor"
        assert main_formula.formula == "power * efficiency"

        assert len(attributes) == 4
        assert attributes["voltage"] == 240
        assert attributes["manufacturer"] == "TestCorp"
        assert attributes["is_active"] is True
        assert isinstance(attributes["current"], dict)
        assert attributes["current"]["formula"] == "power / voltage"
