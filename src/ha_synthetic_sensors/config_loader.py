"""
Configuration Loader - File loading and YAML parsing functionality.

This module handles the low-level file operations and YAML parsing for
synthetic sensor configurations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

import aiofiles
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
import yaml

from .config_helpers.yaml_helpers import check_duplicate_sensor_keys, extract_sensor_keys_from_yaml, trim_yaml_keys
from .config_types import ConfigDict
from .validation_utils import load_yaml_file

_LOGGER = logging.getLogger(__name__)


class ConfigLoader:
    """Handles file loading and YAML parsing operations."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the configuration loader.

        Args:
            hass: Home Assistant instance
        """
        self._hass = hass

    def load_from_file(self, file_path: str | Path) -> ConfigDict:
        """Load configuration from a YAML file synchronously.

        Args:
            file_path: Path to the YAML configuration file

        Returns:
            Parsed configuration dictionary

        Raises:
            ConfigEntryError: If file loading or parsing fails
        """
        try:
            yaml_data = load_yaml_file(file_path)
            if not isinstance(yaml_data, dict):
                raise ConfigEntryError(f"Configuration file {file_path} must contain a dictionary at the root level")
            return cast(ConfigDict, yaml_data)
        except Exception as e:
            _LOGGER.error("Failed to load configuration from %s: %s", file_path, e)
            raise ConfigEntryError(f"Failed to load configuration from {file_path}: {e}") from e

    async def async_load_from_file(self, file_path: str | Path) -> ConfigDict:
        """Load configuration from a YAML file asynchronously.

        Args:
            file_path: Path to the YAML configuration file

        Returns:
            Parsed configuration dictionary

        Raises:
            ConfigEntryError: If file loading or parsing fails
        """
        try:
            async with aiofiles.open(file_path, encoding="utf-8") as file:
                content = await file.read()
            return self.load_from_yaml(content)
        except Exception as e:
            _LOGGER.error("Failed to async load configuration from %s: %s", file_path, e)
            raise ConfigEntryError(f"Failed to load configuration from {file_path}: {e}") from e

    def load_from_yaml(self, yaml_content: str) -> ConfigDict:
        """Load configuration from YAML content string.

        Args:
            yaml_content: YAML content as string

        Returns:
            Parsed configuration dictionary

        Raises:
            ConfigEntryError: If YAML parsing fails
        """
        try:
            self._validate_raw_yaml_structure(yaml_content)
            yaml_data = yaml.safe_load(yaml_content)
            if not isinstance(yaml_data, dict):
                raise ConfigEntryError("YAML content must contain a dictionary at the root level")
            return cast(ConfigDict, yaml_data)
        except yaml.YAMLError as e:
            _LOGGER.error("YAML parsing error: %s", e)
            raise ConfigEntryError(f"Invalid YAML format: {e}") from e
        except Exception as e:
            _LOGGER.error("Failed to load configuration from YAML: %s", e)
            raise ConfigEntryError(f"Failed to load configuration: {e}") from e

    def load_from_dict(self, config_dict: ConfigDict) -> ConfigDict:
        """Load configuration from a dictionary.

        Args:
            config_dict: Configuration dictionary

        Returns:
            Validated configuration dictionary

        Raises:
            ConfigEntryError: If validation fails
        """
        try:
            # Validate the structure
            if not isinstance(config_dict, dict):
                raise ConfigEntryError("Configuration must be a dictionary")

            # Trim keys and return
            return trim_yaml_keys(config_dict)
        except Exception as e:
            _LOGGER.error("Failed to load configuration from dictionary: %s", e)
            raise ConfigEntryError(f"Failed to load configuration: {e}") from e

    def _validate_raw_yaml_structure(self, yaml_content: str) -> None:
        """Validate the raw YAML structure for common issues.

        Args:
            yaml_content: Raw YAML content

        Raises:
            ConfigEntryError: If validation fails
        """
        sensor_keys = extract_sensor_keys_from_yaml(yaml_content)
        if sensor_keys:
            check_duplicate_sensor_keys(sensor_keys)

    async def async_save_config_to_file(self, config_data: dict[str, Any], file_path: str | Path) -> None:
        """Save configuration data to a YAML file asynchronously.

        Args:
            config_data: Configuration data to save
            file_path: Path to save the file

        Raises:
            ConfigEntryError: If saving fails
        """
        try:
            yaml_content = yaml.dump(config_data, default_flow_style=False, sort_keys=False, indent=2)
            async with aiofiles.open(file_path, "w", encoding="utf-8") as file:
                await file.write(yaml_content)
            _LOGGER.info("Configuration saved to %s", file_path)
        except Exception as e:
            _LOGGER.error("Failed to save configuration to %s: %s", file_path, e)
            raise ConfigEntryError(f"Failed to save configuration to {file_path}: {e}") from e
