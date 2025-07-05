"""Tests for ConfigConverter functionality."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
import pytest
import yaml

from ha_synthetic_sensors.config_converter import ConfigConverter
from ha_synthetic_sensors.config_manager import Config, FormulaConfig, SensorConfig
from ha_synthetic_sensors.exceptions import SyntheticSensorsError


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    return MagicMock(spec=HomeAssistant)


@pytest.fixture
def config_converter(mock_hass):
    """Create a ConfigConverter instance for testing."""
    from unittest.mock import AsyncMock, patch

    from ha_synthetic_sensors.storage_manager import StorageManager

    # Create a mock storage manager with the hass instance
    with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
        mock_store = AsyncMock()
        mock_store.async_load.return_value = None
        mock_store.async_save = AsyncMock()
        MockStore.return_value = mock_store

        storage_manager = StorageManager(mock_hass, "test_storage")
        storage_manager._store = mock_store

        return ConfigConverter(storage_manager)


@pytest.fixture
def yaml_fixtures_dir():
    """Get the path to YAML fixtures directory."""
    return Path(__file__).parent / "yaml_fixtures"


@pytest.fixture
def basic_yaml_config(yaml_fixtures_dir):
    """Load basic YAML configuration for testing."""
    yaml_path = yaml_fixtures_dir / "storage_test_basic.yaml"
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def complex_yaml_config(yaml_fixtures_dir):
    """Load complex YAML configuration for testing."""
    yaml_path = yaml_fixtures_dir / "storage_test_complex.yaml"
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def conversion_yaml_config(yaml_fixtures_dir):
    """Load conversion test YAML configuration."""
    yaml_path = yaml_fixtures_dir / "storage_test_conversion.yaml"
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestConfigConverter:
    """Test cases for ConfigConverter."""

    async def test_yaml_to_config_basic(self, config_converter, basic_yaml_config):
        """Test basic YAML to Config conversion."""
        config = await config_converter.yaml_to_config(basic_yaml_config)

        assert isinstance(config, Config)
        assert config.version == "1.0"
        assert len(config.sensors) == 3

        # Check global settings
        assert config.global_settings["device_identifier"] == "span_panel:nj-2316-005k6"

        # Check first sensor
        sensor1 = next(s for s in config.sensors if s.unique_id == "span_panel_total_power")
        assert sensor1.name == "Total Power"
        assert sensor1.device_identifier == "span_panel:nj-2316-005k6"
        assert len(sensor1.formulas) == 1
        assert sensor1.formulas[0].formula == "instant_power"

    async def test_yaml_to_config_complex(self, config_converter, complex_yaml_config):
        """Test complex YAML to Config conversion with multiple formulas."""
        config = await config_converter.yaml_to_config(complex_yaml_config)

        assert len(config.sensors) > 10  # Complex file has many sensors

        # Check energy_analysis_suite sensor with multiple formulas (main + attributes)
        energy_sensor = next(s for s in config.sensors if s.unique_id == "energy_analysis_suite")
        assert len(energy_sensor.formulas) == 5  # 1 main + 4 attributes

        # Check main formula
        main_formula = next(f for f in energy_sensor.formulas if f.id == "energy_analysis_suite")
        assert main_formula.formula == 'sum("device_class:primary_energy_type")'
        assert main_formula.device_class == "power"

        # Check attribute formula
        secondary_formula = next(f for f in energy_sensor.formulas if f.id == "energy_analysis_suite_secondary_consumption")
        assert secondary_formula.formula == 'sum("device_class:secondary_energy_type")'
        assert secondary_formula.unit_of_measurement == "W"

    async def test_config_to_yaml(self, config_converter, basic_yaml_config, tmp_path):
        """Test Config to YAML conversion using export functionality."""
        # Convert YAML to Config first
        config = await config_converter.yaml_to_config(basic_yaml_config)

        # Load storage first
        await config_converter.storage_manager.async_load()

        # Store in storage
        sensor_set_id = await config_converter.convert_config_to_storage(config, "test_export", "test:device")

        # Export back to YAML using the export routine
        output_file = tmp_path / "exported.yaml"
        await config_converter.export_storage_to_yaml(output_file, sensor_set_id=sensor_set_id)

        # Read the exported YAML and verify structure
        import yaml

        with open(output_file, encoding="utf-8") as f:
            exported_yaml = yaml.safe_load(f)

        assert exported_yaml["version"] == "1.0"
        assert "sensors" in exported_yaml
        assert "global_settings" in exported_yaml

        # Check that sensor structure is preserved
        sensors = exported_yaml["sensors"]
        assert "span_panel_total_power" in sensors
        assert sensors["span_panel_total_power"]["name"] == "Total Power"

    async def test_config_to_json(self, config_converter, conversion_yaml_config):
        """Test Config to JSON conversion."""
        config = await config_converter.yaml_to_config(conversion_yaml_config)
        json_string = config_converter.config_to_json(config)

        # Parse the JSON string to verify structure
        json_dict = json.loads(json_string)

        assert json_dict["version"] == "1.0"
        assert "sensors" in json_dict

        # Verify JSON string is valid
        assert isinstance(json_string, str)
        reloaded = json.loads(json_string)
        assert reloaded == json_dict

    async def test_json_to_config(self, config_converter, conversion_yaml_config):
        """Test JSON to Config conversion."""
        # Convert YAML -> Config -> JSON -> Config
        original_config = await config_converter.yaml_to_config(conversion_yaml_config)
        json_string = config_converter.config_to_json(original_config)
        restored_config = config_converter.json_to_config(json_string)

        assert restored_config.version == original_config.version
        assert len(restored_config.sensors) == len(original_config.sensors)

        original_sensor = original_config.sensors[0]
        restored_sensor = restored_config.sensors[0]
        assert restored_sensor.unique_id == original_sensor.unique_id
        assert restored_sensor.name == original_sensor.name
        assert restored_sensor.device_identifier == original_sensor.device_identifier

    async def test_round_trip_conversion(self, config_converter, complex_yaml_config):
        """Test round-trip conversion: YAML -> Config -> JSON -> Config -> YAML."""
        # YAML -> Config
        config1 = await config_converter.yaml_to_config(complex_yaml_config)

        # Config -> JSON
        json_string = config_converter.config_to_json(config1)

        # JSON -> Config
        config2 = config_converter.json_to_config(json_string)

        # Config -> YAML
        yaml_dict = config_converter.config_to_yaml(config2)

        # Verify key properties are preserved
        assert yaml_dict["version"] == complex_yaml_config["version"]
        assert len(yaml_dict["sensors"]) == len(complex_yaml_config["sensors"])

    async def test_validation_errors(self, config_converter):
        """Test validation of malformed configurations."""
        # Test missing required fields
        invalid_yaml = {
            "version": "1.0",
            "sensors": {
                "invalid_sensor": {
                    "name": "Invalid Sensor"
                    # Missing formulas
                }
            },
        }

        with pytest.raises(SyntheticSensorsError):
            await config_converter.yaml_to_config(invalid_yaml)

    async def test_yaml_compatibility_validation(self, config_converter):
        """Test YAML compatibility validation."""
        # Create config with storage-only features
        formula = FormulaConfig(
            id="main", formula="test_value", variables={"test_value": "sensor.test"}, unit_of_measurement="W"
        )

        sensor = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            formulas=[formula],
            device_identifier="test:device",  # This is storage-only
        )

        config = Config(version="1.0", sensors=[sensor], global_settings={})

        issues = config_converter.validate_yaml_compatibility(config)
        assert len(issues) > 0
        assert any("device_identifier" in issue for issue in issues)

    async def test_conversion_summary(self, config_converter, basic_yaml_config):
        """Test conversion summary generation."""
        config = await config_converter.yaml_to_config(basic_yaml_config)
        summary = config_converter.generate_conversion_summary(config)

        assert summary["version"] == "1.0"
        assert summary["sensor_count"] == 3
        assert summary["global_settings_count"] > 0
        assert isinstance(summary["sensors_by_type"], dict)
        assert isinstance(summary["device_associations"], list)
        assert isinstance(summary["compatibility_issues"], list)

    async def test_error_handling_invalid_yaml(self, config_converter):
        """Test error handling with invalid YAML structure."""
        invalid_configs = [
            None,
            {"version": "1.0"},  # Missing sensors
            {"sensors": {}},  # Missing version
            {"version": "1.0", "sensors": "not_a_dict"},  # Invalid sensors type
        ]

        for invalid_config in invalid_configs:
            with pytest.raises(SyntheticSensorsError):
                await config_converter.yaml_to_config(invalid_config)

    async def test_clean_dict_for_json(self, config_converter):
        """Test the _clean_dict_for_json helper method."""
        test_data = {
            "string": "value",
            "number": 42,
            "list": [1, 2, 3],
            "set": {1, 2, 3},  # Should be converted to list
            "nested": {"inner_set": {"a", "b", "c"}, "inner_list": [4, 5, 6]},
        }

        cleaned = config_converter._clean_dict_for_json(test_data)

        assert cleaned["string"] == "value"
        assert cleaned["number"] == 42
        assert cleaned["list"] == [1, 2, 3]
        assert isinstance(cleaned["set"], list)
        assert set(cleaned["set"]) == {1, 2, 3}
        assert isinstance(cleaned["nested"]["inner_set"], list)
        assert set(cleaned["nested"]["inner_set"]) == {"a", "b", "c"}
