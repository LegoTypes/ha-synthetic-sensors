"""
YAML-based CRUD operations for global settings in sensor sets.

This module provides methods for creating, updating, and managing global settings
using YAML string configurations.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import yaml as yaml_lib

from .config_types import GlobalSettingsDict
from .exceptions import SyntheticSensorsError
from .schema_validator import validate_global_settings_only
from .sensor_set_global_settings import DEVICE_INFO_FIELDS

if TYPE_CHECKING:
    from .sensor_set import SensorSet

_LOGGER = logging.getLogger(__name__)


class SensorSetGlobalsYamlCrud:
    """Handles YAML-based CRUD operations for global settings in sensor sets."""

    def __init__(self, sensor_set: SensorSet) -> None:
        """Initialize YAML CRUD handler for global settings.

        Args:
            sensor_set: SensorSet instance to operate on
        """
        self.sensor_set = sensor_set

    def _parse_global_settings_yaml(self, global_settings_yaml: str) -> GlobalSettingsDict:
        """
        Parse global settings YAML string into GlobalSettingsDict.

        Args:
            global_settings_yaml: YAML string containing global settings configuration
                                 Example:
                                 ```
                                 device_identifier: test_device
                                 variables:
                                   base_power: sensor.power_meter
                                   rate: 0.15
                                 metadata:
                                   manufacturer: Test Corp
                                 ```

        Returns:
            GlobalSettingsDict: Parsed global settings configuration

        Raises:
            SyntheticSensorsError: If YAML parsing or validation fails
        """
        try:
            # Parse the raw YAML
            global_settings_data = yaml_lib.safe_load(global_settings_yaml)

            if not isinstance(global_settings_data, dict):
                raise SyntheticSensorsError("Global settings YAML must be a dictionary")

            # Validate global settings using specialized validator that doesn't require sensors
            validation_result = validate_global_settings_only(global_settings_data)

            if not validation_result["valid"]:
                error_messages = [f"{error.path}: {error.message}" for error in validation_result["errors"]]
                raise SyntheticSensorsError(f"Global settings validation failed: {'; '.join(error_messages)}")

            # Convert the validated data to GlobalSettingsDict
            # Since we validated the structure, we can safely cast it
            return global_settings_data  # type: ignore[return-value]

        except Exception as exc:
            raise SyntheticSensorsError(f"Failed to parse global settings YAML: {exc}") from exc

    async def async_create_global_settings_from_yaml(self, global_settings_yaml: str) -> None:
        """
        Create/replace global settings for this sensor set from YAML string.

        Args:
            global_settings_yaml: YAML string containing global settings configuration
                                 Example:
                                 ```
                                 device_identifier: my_device
                                 device_name: My Smart Device
                                 variables:
                                   base_sensor: sensor.power_meter
                                   multiplier: 1.5
                                 metadata:
                                   location: Kitchen
                                 ```

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist or YAML is invalid
        """
        self.sensor_set.ensure_exists()

        global_settings = self._parse_global_settings_yaml(global_settings_yaml)

        await self.sensor_set.get_global_settings_handler().async_create_global_settings(global_settings)

    async def async_update_global_settings_from_yaml(self, global_settings_yaml: str) -> None:
        """
        Update global settings for this sensor set from YAML string (merges with existing).

        Args:
            global_settings_yaml: YAML string containing global settings updates
                                 Only specified fields will be updated, others remain unchanged.

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist or YAML is invalid
        """
        self.sensor_set.ensure_exists()

        global_settings_updates = self._parse_global_settings_yaml(global_settings_yaml)

        # Convert GlobalSettingsDict to dict[str, Any] for the API
        updates_dict: dict[str, Any] = dict(global_settings_updates)
        await self.sensor_set.get_global_settings_handler().async_update_global_settings_partial(updates_dict)

    def read_global_settings_as_yaml(self) -> str:
        """
        Read global settings for this sensor set and return as YAML string.

        Returns:
            YAML string representation of global settings

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist
        """
        self.sensor_set.ensure_exists()

        global_settings = self.sensor_set.get_global_settings_handler().read_global_settings()

        if not global_settings:
            return ""

        return yaml_lib.dump(global_settings, default_flow_style=False, sort_keys=False)

    async def async_delete_global_settings(self) -> bool:
        """
        Delete all global settings for this sensor set.

        Returns:
            True if global settings were deleted, False if none existed

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist
        """
        self.sensor_set.ensure_exists()

        return await self.sensor_set.get_global_settings_handler().async_delete_global_settings()

    # Variable-specific YAML CRUD operations

    async def async_add_variable_from_yaml(self, variable_yaml: str) -> None:
        """
        Add or update a global variable from YAML string.

        Args:
            variable_yaml: YAML string containing variable definition
                          Example:
                          ```
                          my_sensor: sensor.power_meter
                          ```
                          or for multiple variables:
                          ```
                          variables:
                            sensor_1: sensor.power_meter
                            rate: 0.15
                          ```

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist or YAML is invalid
        """
        self.sensor_set.ensure_exists()

        try:
            variables_data = yaml_lib.safe_load(variable_yaml)

            if not isinstance(variables_data, dict):
                raise SyntheticSensorsError("Variable YAML must be a dictionary")

            # Handle both formats: direct variable or nested under 'variables'
            variables_to_add = variables_data.get("variables", variables_data)

            # Add each variable
            for var_name, var_value in variables_to_add.items():
                if not isinstance(var_value, str | int | float):
                    raise SyntheticSensorsError(f"Variable '{var_name}' must be string, int, or float")

                await self.sensor_set.get_global_settings_handler().async_set_global_variable(var_name, var_value)

        except Exception as exc:
            raise SyntheticSensorsError(f"Failed to parse variable YAML: {exc}") from exc

    def read_variables_as_yaml(self) -> str:
        """
        Read global variables and return as YAML string.

        Returns:
            YAML string representation of global variables
        """
        self.sensor_set.ensure_exists()

        variables = self.sensor_set.get_global_settings_handler().list_global_variables()

        if not variables:
            return ""

        return yaml_lib.dump({"variables": variables}, default_flow_style=False, sort_keys=False)

    # Device info YAML CRUD operations

    async def async_update_device_info_from_yaml(self, device_info_yaml: str) -> None:
        """
        Update device information from YAML string.

        Args:
            device_info_yaml: YAML string containing device information
                             Example:
                             ```
                             device_identifier: my_smart_device
                             device_name: My Smart Device
                             device_manufacturer: Acme Corp
                             device_model: Smart-1000
                             ```

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist or YAML is invalid
        """
        self.sensor_set.ensure_exists()

        try:
            device_info = yaml_lib.safe_load(device_info_yaml)

            if not isinstance(device_info, dict):
                raise SyntheticSensorsError("Device info YAML must be a dictionary")

            # Validate device info fields
            valid_fields = set(DEVICE_INFO_FIELDS)

            for field_name in device_info:
                if field_name not in valid_fields:
                    raise SyntheticSensorsError(f"Invalid device info field: {field_name}")

                if not isinstance(device_info[field_name], str):
                    raise SyntheticSensorsError(f"Device info field '{field_name}' must be a string")

            await self.sensor_set.get_global_settings_handler().async_set_device_info(device_info)

        except Exception as exc:
            raise SyntheticSensorsError(f"Failed to parse device info YAML: {exc}") from exc

    def read_device_info_as_yaml(self) -> str:
        """
        Read device information and return as YAML string.

        Returns:
            YAML string representation of device information
        """
        self.sensor_set.ensure_exists()

        device_info = self.sensor_set.get_global_settings_handler().get_device_info()

        if not device_info:
            return ""

        return yaml_lib.dump(device_info, default_flow_style=False, sort_keys=False)

    # Metadata YAML CRUD operations

    async def async_update_metadata_from_yaml(self, metadata_yaml: str) -> None:
        """
        Update global metadata from YAML string.

        Args:
            metadata_yaml: YAML string containing metadata
                          Example:
                          ```
                          metadata:
                            location: Kitchen
                            installation_date: 2024-01-15
                            notes: Custom installation
                          ```

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist or YAML is invalid
        """
        self.sensor_set.ensure_exists()

        try:
            metadata_data = yaml_lib.safe_load(metadata_yaml)

            if not isinstance(metadata_data, dict):
                raise SyntheticSensorsError("Metadata YAML must be a dictionary")

            # Handle both formats: direct metadata or nested under 'metadata'
            metadata = metadata_data.get("metadata", metadata_data)

            await self.sensor_set.get_global_settings_handler().async_set_global_metadata(metadata)

        except Exception as exc:
            raise SyntheticSensorsError(f"Failed to parse metadata YAML: {exc}") from exc

    def read_metadata_as_yaml(self) -> str:
        """
        Read global metadata and return as YAML string.

        Returns:
            YAML string representation of global metadata
        """
        self.sensor_set.ensure_exists()

        metadata = self.sensor_set.get_global_settings_handler().get_global_metadata()

        if not metadata:
            return ""

        return yaml_lib.dump({"metadata": metadata}, default_flow_style=False, sort_keys=False)

    # Synchronous versions

    def create_global_settings_from_yaml(self, global_settings_yaml: str) -> None:
        """
        Create/replace global settings from YAML string (synchronous version).

        For async operations, use async_create_global_settings_from_yaml().

        Args:
            global_settings_yaml: YAML string containing global settings configuration

        Raises:
            SyntheticSensorsError: If used in async context, sensor set doesn't exist, or YAML is invalid
        """
        try:
            asyncio.get_running_loop()
            raise SyntheticSensorsError("Use async_create_global_settings_from_yaml() in async context")
        except RuntimeError:
            # No running loop, safe to use run_until_complete
            asyncio.run(self.async_create_global_settings_from_yaml(global_settings_yaml))

    def update_global_settings_from_yaml(self, global_settings_yaml: str) -> None:
        """
        Update global settings from YAML string (synchronous version).

        For async operations, use async_update_global_settings_from_yaml().

        Args:
            global_settings_yaml: YAML string containing global settings updates

        Raises:
            SyntheticSensorsError: If used in async context, sensor set doesn't exist, or YAML is invalid
        """
        try:
            asyncio.get_running_loop()
            raise SyntheticSensorsError("Use async_update_global_settings_from_yaml() in async context")
        except RuntimeError:
            # No running loop, safe to use run_until_complete
            asyncio.run(self.async_update_global_settings_from_yaml(global_settings_yaml))
