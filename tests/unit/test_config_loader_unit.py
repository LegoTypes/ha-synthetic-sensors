"""Unit tests for ConfigLoader class."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
import yaml

from ha_synthetic_sensors.config_loader import ConfigLoader
from ha_synthetic_sensors.config_types import ConfigDict


class TestConfigLoader:
    """Test cases for ConfigLoader class."""

    def test_init(self) -> None:
        """Test ConfigLoader initialization."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        assert loader._hass == hass

    def test_load_from_file_success(self) -> None:
        """Test successful loading from file."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        test_config = {"sensors": {"test_sensor": {"formula": "1 + 1"}}}
        
        with patch("ha_synthetic_sensors.config_loader.load_yaml_file") as mock_load:
            mock_load.return_value = test_config
            result = loader.load_from_file("test.yaml")
            
            assert result == test_config
            mock_load.assert_called_once_with(Path("test.yaml"))

    def test_load_from_file_path_object(self) -> None:
        """Test loading from Path object."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        test_config = {"sensors": {"test_sensor": {"formula": "1 + 1"}}}
        test_path = Path("test.yaml")
        
        with patch("ha_synthetic_sensors.config_loader.load_yaml_file") as mock_load:
            mock_load.return_value = test_config
            result = loader.load_from_file(test_path)
            
            assert result == test_config
            mock_load.assert_called_once_with(test_path)

    def test_load_from_file_not_dict(self) -> None:
        """Test loading file that doesn't contain a dictionary."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        with patch("ha_synthetic_sensors.config_loader.load_yaml_file") as mock_load:
            mock_load.return_value = "not a dict"
            
            with pytest.raises(ConfigEntryError, match="must contain a dictionary"):
                loader.load_from_file("test.yaml")

    def test_load_from_file_exception(self) -> None:
        """Test loading file with exception."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        with patch("ha_synthetic_sensors.config_loader.load_yaml_file") as mock_load:
            mock_load.side_effect = FileNotFoundError("File not found")
            
            with pytest.raises(ConfigEntryError, match="Failed to load configuration"):
                loader.load_from_file("test.yaml")

    @pytest.mark.asyncio
    async def test_async_load_from_file_success(self) -> None:
        """Test successful async loading from file."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        test_config = {"sensors": {"test_sensor": {"formula": "1 + 1"}}}
        test_content = yaml.dump(test_config)
        
        mock_file = AsyncMock()
        mock_file.read.return_value = test_content
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_file
        mock_context.__aexit__.return_value = None
        
        with patch("aiofiles.open", return_value=mock_context) as mock_open:
            result = await loader.async_load_from_file("test.yaml")
            
            assert result == test_config
            mock_open.assert_called_once_with("test.yaml", encoding="utf-8")

    @pytest.mark.asyncio
    async def test_async_load_from_file_path_object(self) -> None:
        """Test async loading from Path object."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        test_config = {"sensors": {"test_sensor": {"formula": "1 + 1"}}}
        test_content = yaml.dump(test_config)
        test_path = Path("test.yaml")
        
        mock_file = AsyncMock()
        mock_file.read.return_value = test_content
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_file
        mock_context.__aexit__.return_value = None
        
        with patch("aiofiles.open", return_value=mock_context) as mock_open:
            result = await loader.async_load_from_file(test_path)
            
            assert result == test_config
            mock_open.assert_called_once_with(test_path, encoding="utf-8")

    @pytest.mark.asyncio
    async def test_async_load_from_file_exception(self) -> None:
        """Test async loading file with exception."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        with patch("aiofiles.open", side_effect=FileNotFoundError("File not found")):
            with pytest.raises(ConfigEntryError, match="Failed to load configuration"):
                await loader.async_load_from_file("test.yaml")

    def test_load_from_yaml_success(self) -> None:
        """Test successful loading from YAML content."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        test_config = {"sensors": {"test_sensor": {"formula": "1 + 1"}}}
        test_content = yaml.dump(test_config)
        
        with patch.object(loader, "_validate_raw_yaml_structure") as mock_validate:
            result = loader.load_from_yaml(test_content)
            
            assert result == test_config
            mock_validate.assert_called_once_with(test_content)

    def test_load_from_yaml_not_dict(self) -> None:
        """Test loading YAML that doesn't contain a dictionary."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        test_content = yaml.dump("not a dict")
        
        with patch.object(loader, "_validate_raw_yaml_structure"):
            with pytest.raises(ConfigEntryError, match="must contain a dictionary"):
                loader.load_from_yaml(test_content)

    def test_load_from_yaml_yaml_error(self) -> None:
        """Test loading invalid YAML."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        invalid_yaml = "invalid: yaml: content: ["
        
        with patch.object(loader, "_validate_raw_yaml_structure"):
            with pytest.raises(ConfigEntryError, match="Invalid YAML format"):
                loader.load_from_yaml(invalid_yaml)

    def test_load_from_yaml_exception(self) -> None:
        """Test loading YAML with exception."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        with patch.object(loader, "_validate_raw_yaml_structure") as mock_validate:
            mock_validate.side_effect = Exception("Validation error")
            
            with pytest.raises(ConfigEntryError, match="Failed to load configuration"):
                loader.load_from_yaml("test content")

    def test_load_from_dict_success(self) -> None:
        """Test successful loading from dictionary."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        test_config = {"sensors": {"test_sensor": {"formula": "1 + 1"}}}
        
        with patch("ha_synthetic_sensors.config_loader.trim_yaml_keys") as mock_trim:
            mock_trim.return_value = test_config
            result = loader.load_from_dict(test_config)
            
            assert result == test_config
            mock_trim.assert_called_once_with(test_config)

    def test_load_from_dict_not_dict(self) -> None:
        """Test loading from non-dictionary."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        with pytest.raises(ConfigEntryError, match="must be a dictionary"):
            loader.load_from_dict("not a dict")  # type: ignore[arg-type]

    def test_load_from_dict_exception(self) -> None:
        """Test loading dictionary with exception."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        test_config = {"sensors": {"test_sensor": {"formula": "1 + 1"}}}
        
        with patch("ha_synthetic_sensors.config_loader.trim_yaml_keys") as mock_trim:
            mock_trim.side_effect = Exception("Trim error")
            
            with pytest.raises(ConfigEntryError, match="Failed to load configuration"):
                loader.load_from_dict(test_config)

    def test_validate_raw_yaml_structure_success(self) -> None:
        """Test successful YAML structure validation."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        test_content = """
        sensors:
          test_sensor:
            formula: "1 + 1"
        """
        
        with patch("ha_synthetic_sensors.config_loader.extract_sensor_keys_from_yaml") as mock_extract, \
             patch("ha_synthetic_sensors.config_loader.check_duplicate_sensor_keys") as mock_check:
            mock_extract.return_value = ["test_sensor"]
            
            loader._validate_raw_yaml_structure(test_content)
            
            mock_extract.assert_called_once_with(test_content)
            mock_check.assert_called_once_with(["test_sensor"])

    def test_validate_raw_yaml_structure_no_sensors(self) -> None:
        """Test YAML structure validation with no sensors."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        test_content = "other: content"
        
        with patch("ha_synthetic_sensors.config_loader.extract_sensor_keys_from_yaml") as mock_extract, \
             patch("ha_synthetic_sensors.config_loader.check_duplicate_sensor_keys") as mock_check:
            mock_extract.return_value = []
            
            loader._validate_raw_yaml_structure(test_content)
            
            mock_extract.assert_called_once_with(test_content)
            mock_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_save_config_to_file_success(self) -> None:
        """Test successful async saving to file."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        test_config = {"sensors": {"test_sensor": {"formula": "1 + 1"}}}
        expected_yaml = yaml.dump(test_config, default_flow_style=False, sort_keys=False, indent=2)
        
        mock_file = AsyncMock()
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_file
        mock_context.__aexit__.return_value = None
        
        with patch("aiofiles.open", return_value=mock_context) as mock_open:
            await loader.async_save_config_to_file(test_config, "test.yaml")
            
            mock_open.assert_called_once_with("test.yaml", "w", encoding="utf-8")
            mock_file.write.assert_called_once_with(expected_yaml)

    @pytest.mark.asyncio
    async def test_async_save_config_to_file_path_object(self) -> None:
        """Test async saving to Path object."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        test_config = {"sensors": {"test_sensor": {"formula": "1 + 1"}}}
        test_path = Path("test.yaml")
        expected_yaml = yaml.dump(test_config, default_flow_style=False, sort_keys=False, indent=2)
        
        mock_file = AsyncMock()
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_file
        mock_context.__aexit__.return_value = None
        
        with patch("aiofiles.open", return_value=mock_context) as mock_open:
            await loader.async_save_config_to_file(test_config, test_path)
            
            mock_open.assert_called_once_with(test_path, "w", encoding="utf-8")
            mock_file.write.assert_called_once_with(expected_yaml)

    @pytest.mark.asyncio
    async def test_async_save_config_to_file_exception(self) -> None:
        """Test async saving with exception."""
        hass = MagicMock(spec=HomeAssistant)
        loader = ConfigLoader(hass)
        
        test_config = {"sensors": {"test_sensor": {"formula": "1 + 1"}}}
        
        with patch("aiofiles.open", side_effect=PermissionError("Permission denied")):
            with pytest.raises(ConfigEntryError, match="Failed to save configuration"):
                await loader.async_save_config_to_file(test_config, "test.yaml")
