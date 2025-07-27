"""Unit tests for yaml_config_parser.py module."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, mock_open, patch
import pytest
import yaml
import aiofiles

from ha_synthetic_sensors.yaml_config_parser import YAMLConfigParser, trim_yaml_keys
from ha_synthetic_sensors.exceptions import SchemaValidationError
from ha_synthetic_sensors.config_models import Config, SensorConfig, FormulaConfig


class TestYAMLConfigParser:
    """Test cases for YAMLConfigParser class."""

    @pytest.fixture
    def parser(self):
        """Create YAMLConfigParser instance for testing."""
        return YAMLConfigParser()

    def test_load_yaml_file_success(self, parser, tmp_path):
        """Test successful YAML file loading."""
        # Create test YAML file
        yaml_content = """
        sensors:
          test_sensor:
            formula: "1 + 1"
        """
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_content)

        result = parser.load_yaml_file(yaml_file)

        assert result["sensors"]["test_sensor"]["formula"] == "1 + 1"

    def test_load_yaml_file_empty_content(self, parser, tmp_path):
        """Test loading empty YAML file raises ValueError."""
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")

        with pytest.raises(ValueError, match="Failed to load YAML file"):
            parser.load_yaml_file(yaml_file)

    def test_load_yaml_file_invalid_syntax(self, parser, tmp_path):
        """Test loading YAML with syntax errors."""
        yaml_content = """
        sensors:
          test_sensor:
            formula: "1 + 1"
        invalid: [unclosed bracket
        """
        yaml_file = tmp_path / "invalid.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(ValueError, match="YAML syntax error"):
            parser.load_yaml_file(yaml_file)

    def test_load_yaml_file_not_found(self, parser):
        """Test loading non-existent YAML file."""
        with pytest.raises(ValueError, match="Failed to load YAML file"):
            parser.load_yaml_file(Path("nonexistent.yaml"))

    @pytest.mark.asyncio
    async def test_async_load_yaml_file_success(self, parser, tmp_path):
        """Test successful async YAML file loading."""
        yaml_content = """
        sensors:
          test_sensor:
            formula: "2 + 2"
        """
        yaml_file = tmp_path / "test_async.yaml"
        yaml_file.write_text(yaml_content)

        result = await parser.async_load_yaml_file(yaml_file)

        assert result["sensors"]["test_sensor"]["formula"] == "2 + 2"

    @pytest.mark.asyncio
    async def test_async_load_yaml_file_empty_content(self, parser, tmp_path):
        """Test async loading empty YAML file raises ValueError."""
        yaml_file = tmp_path / "empty_async.yaml"
        yaml_file.write_text("")

        with pytest.raises(ValueError, match="Failed to load YAML file"):
            await parser.async_load_yaml_file(yaml_file)

    @pytest.mark.asyncio
    async def test_async_load_yaml_file_invalid_syntax(self, parser, tmp_path):
        """Test async loading YAML with syntax errors."""
        yaml_content = """
        sensors:
          test_sensor:
            formula: "1 + 1"
        invalid: [unclosed bracket
        """
        yaml_file = tmp_path / "invalid_async.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(ValueError, match="YAML syntax error"):
            await parser.async_load_yaml_file(yaml_file)

    @pytest.mark.asyncio
    async def test_async_load_yaml_file_not_found(self, parser):
        """Test async loading non-existent YAML file."""
        with pytest.raises(ValueError, match="Failed to load YAML file"):
            await parser.async_load_yaml_file(Path("nonexistent_async.yaml"))

    def test_validate_raw_yaml_structure_success(self, parser):
        """Test successful YAML structure validation."""
        yaml_content = """
        sensors:
          test_sensor:
            formula: "1 + 1"
        """
        # Should not raise any exception
        parser.validate_raw_yaml_structure(yaml_content)

    def test_validate_raw_yaml_structure_empty_content(self, parser):
        """Test validation with empty YAML content."""
        # Should not raise any exception for empty content
        parser.validate_raw_yaml_structure("")

    def test_validate_raw_yaml_structure_not_dict(self, parser):
        """Test validation when YAML root is not a dictionary."""
        yaml_content = "- item1\n- item2"

        with pytest.raises(ValueError, match="YAML root must be a dictionary"):
            parser.validate_raw_yaml_structure(yaml_content)

    def test_validate_raw_yaml_structure_missing_sensors(self, parser):
        """Test validation when 'sensors' key is missing."""
        yaml_content = """
        other_key: value
        """

        with pytest.raises(ValueError, match="Missing required top-level keys"):
            parser.validate_raw_yaml_structure(yaml_content)

    def test_validate_raw_yaml_structure_sensors_not_dict(self, parser):
        """Test validation when 'sensors' is not a dictionary."""
        yaml_content = """
        sensors: "not a dict"
        """

        with pytest.raises(ValueError, match="'sensors' must be a dictionary"):
            parser.validate_raw_yaml_structure(yaml_content)

    def test_validate_raw_yaml_structure_sensor_not_dict(self, parser):
        """Test validation when individual sensor is not a dictionary."""
        yaml_content = """
        sensors:
          test_sensor: "not a dict"
        """

        with pytest.raises(ValueError, match="Sensor 'test_sensor' must be a dictionary"):
            parser.validate_raw_yaml_structure(yaml_content)

    def test_validate_raw_yaml_structure_missing_formula(self, parser):
        """Test validation when sensor is missing 'formula' field."""
        yaml_content = """
        sensors:
          test_sensor:
            name: "Test Sensor"
        """

        with pytest.raises(ValueError, match="Sensor 'test_sensor' missing required 'formula' field"):
            parser.validate_raw_yaml_structure(yaml_content)

    def test_validate_raw_yaml_structure_yaml_error(self, parser):
        """Test validation with YAML syntax error."""
        yaml_content = """
        sensors:
          test_sensor:
            formula: "1 + 1"
        invalid: [unclosed bracket
        """

        with pytest.raises(ValueError, match="YAML validation error"):
            parser.validate_raw_yaml_structure(yaml_content)

    def test_config_to_yaml_basic(self, parser):
        """Test converting config object to YAML dict."""
        formula = FormulaConfig(id="main", formula="1 + 1")
        sensor = SensorConfig(unique_id="test_sensor", name="Test Sensor", formulas=[formula])
        config = Config(sensors=[sensor])

        result = parser.config_to_yaml(config)

        assert result["sensors"]["test_sensor"]["formulas"]["main"]["formula"] == "1 + 1"
        assert result["sensors"]["test_sensor"]["name"] == "Test Sensor"

    def test_config_to_yaml_with_metadata(self, parser):
        """Test converting config with metadata to YAML."""
        formula = FormulaConfig(id="main", formula="entity.state", attributes={"unit_of_measurement": "°C"})
        sensor = SensorConfig(unique_id="test_sensor", formulas=[formula])
        config = Config(sensors=[sensor], global_settings={"device_identifier": "test_device"})

        result = parser.config_to_yaml(config)

        assert result["global_settings"]["device_identifier"] == "test_device"
        assert result["sensors"]["test_sensor"]["formulas"]["main"]["attributes"]["unit_of_measurement"] == "°C"

    def test_config_to_yaml_empty_config(self, parser):
        """Test converting empty config to YAML."""
        config = Config(sensors=[], global_settings={})

        result = parser.config_to_yaml(config)

        assert result == {}

    @patch("builtins.open", side_effect=PermissionError("Permission denied"))
    def test_load_yaml_file_permission_error(self, mock_file, parser, tmp_path):
        """Test handling permission errors when loading YAML file."""
        yaml_file = tmp_path / "permission_denied.yaml"

        with pytest.raises(ValueError, match="Failed to load YAML file"):
            parser.load_yaml_file(yaml_file)

    @pytest.mark.asyncio
    @patch("aiofiles.open", side_effect=PermissionError("Permission denied"))
    async def test_async_load_yaml_file_permission_error(self, mock_file, parser, tmp_path):
        """Test handling permission errors when async loading YAML file."""
        yaml_file = tmp_path / "permission_denied_async.yaml"

        with pytest.raises(ValueError, match="Failed to load YAML file"):
            await parser.async_load_yaml_file(yaml_file)


class TestTrimYamlKeys:
    """Test cases for trim_yaml_keys utility function."""

    def test_trim_yaml_keys_simple_dict(self):
        """Test trimming whitespace from dictionary keys."""
        data = {"  key1  ": "value1", "key2": "value2", "  key3": "value3"}

        result = trim_yaml_keys(data)

        expected = {"key1": "value1", "key2": "value2", "key3": "value3"}
        assert result == expected

    def test_trim_yaml_keys_nested_dict(self):
        """Test trimming whitespace from nested dictionary keys."""
        data = {"  level1  ": {"  level2  ": {"  key  ": "value"}}}

        result = trim_yaml_keys(data)

        expected = {"level1": {"level2": {"key": "value"}}}
        assert result == expected

    def test_trim_yaml_keys_list_with_dicts(self):
        """Test trimming keys in dictionaries within lists."""
        data = {"list_key": [{"  item1  ": "value1"}, {"item2": "value2"}, {"  item3  ": "value3"}]}

        result = trim_yaml_keys(data)

        expected = {"list_key": [{"item1": "value1"}, {"item2": "value2"}, {"item3": "value3"}]}
        assert result == expected

    def test_trim_yaml_keys_non_dict(self):
        """Test trimming function with non-dictionary input."""
        # Should return the input unchanged for non-dict types
        assert trim_yaml_keys("string") == "string"
        assert trim_yaml_keys(123) == 123
        assert trim_yaml_keys([1, 2, 3]) == [1, 2, 3]
        assert trim_yaml_keys(None) is None

    def test_trim_yaml_keys_empty_dict(self):
        """Test trimming function with empty dictionary."""
        result = trim_yaml_keys({})
        assert result == {}

    def test_trim_yaml_keys_non_string_keys(self):
        """Test trimming function with non-string keys."""
        data = {123: "numeric_key", "  string_key  ": "string_value"}

        result = trim_yaml_keys(data)

        expected = {123: "numeric_key", "string_key": "string_value"}
        assert result == expected
