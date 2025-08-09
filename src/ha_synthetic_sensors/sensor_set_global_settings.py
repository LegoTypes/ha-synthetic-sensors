"""Global settings functionality for SensorSet with CRUD operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .config_types import GlobalSettingsDict
from .constants_device import DEVICE_INFO_FIELDS
from .exceptions import SyntheticSensorsError

if TYPE_CHECKING:
    from .storage_manager import StorageManager

_LOGGER = logging.getLogger(__name__)


class SensorSetGlobalSettings:
    """Handles global settings operations for a sensor set."""

    def __init__(self, storage_manager: StorageManager, sensor_set_id: str) -> None:
        """Initialize global settings handler.

        Args:
            storage_manager: StorageManager instance
            sensor_set_id: Sensor set identifier
        """
        self.storage_manager = storage_manager
        self.sensor_set_id = sensor_set_id

    def get_global_settings(self) -> dict[str, Any]:
        """
        Get global settings for this sensor set.

        Returns:
            Dictionary of global settings (empty dict if none or sensor set doesn't exist)
        """
        data = self.storage_manager.data
        sensor_set_data = data["sensor_sets"].get(self.sensor_set_id)
        if sensor_set_data is None:
            return {}
        global_settings: dict[str, Any] = sensor_set_data.get("global_settings", {})
        return global_settings

    async def async_set_global_settings(self, global_settings: GlobalSettingsDict, current_sensors: list[Any]) -> None:
        """
        Set global settings for this sensor set.

        Args:
            global_settings: New global settings to set
            current_sensors: Current sensors for validation
        """
        # Validate global settings don't conflict with sensor variables
        if global_settings:
            self.storage_manager.validate_no_global_conflicts(current_sensors, global_settings)

        # Update global settings in storage
        await self._update_global_settings(global_settings)

    async def async_update_global_settings(self, updates: dict[str, Any], current_sensors: list[Any]) -> None:
        """
        Update specific global settings while preserving others.

        Args:
            updates: Dictionary of global setting updates to merge
            current_sensors: Current sensors for validation
        """
        current_global_settings = self.get_global_settings()
        updated_global_settings = current_global_settings.copy()
        updated_global_settings.update(updates)

        # Cast to GlobalSettingsDict since it's compatible
        typed_global_settings: GlobalSettingsDict = updated_global_settings  # type: ignore[assignment]
        await self.async_set_global_settings(typed_global_settings, current_sensors)

    async def _update_global_settings(self, global_settings: GlobalSettingsDict) -> None:
        """
        Update global settings in storage.

        Args:
            global_settings: Global settings to store
        """
        data = self.storage_manager.data

        # Ensure sensor set exists
        if self.sensor_set_id not in data["sensor_sets"]:
            raise ValueError(f"Sensor set {self.sensor_set_id} does not exist")

        # Update global settings
        data["sensor_sets"][self.sensor_set_id]["global_settings"] = global_settings

        # Save to storage
        await self.storage_manager.async_save()

        _LOGGER.debug("Updated global settings for sensor set %s", self.sensor_set_id)

    def build_final_global_settings(self, modification_global_settings: dict[str, Any] | None) -> dict[str, Any]:
        """
        Build final global settings for a modification.

        Args:
            modification_global_settings: Global settings from modification

        Returns:
            Final global settings dictionary
        """
        if modification_global_settings is None:
            return self.get_global_settings()

        current_global_settings = self.get_global_settings()
        final_global_settings = current_global_settings.copy()
        final_global_settings.update(modification_global_settings)

        return final_global_settings

    def update_global_variables_for_entity_changes(
        self, variables: dict[str, Any], entity_id_changes: dict[str, str]
    ) -> dict[str, Any]:
        """
        Update global variables to reflect entity ID changes.

        Args:
            variables: Original global variables
            entity_id_changes: Mapping of old entity ID to new entity ID

        Returns:
            Updated global variables with entity ID changes applied
        """
        updated_variables = {}

        for var_name, var_value in variables.items():
            if isinstance(var_value, str) and var_value in entity_id_changes:
                # This variable references an entity that's being renamed
                updated_variables[var_name] = entity_id_changes[var_value]
            else:
                # No change needed
                updated_variables[var_name] = var_value

        return updated_variables

    async def update_global_settings_direct(self, global_settings: GlobalSettingsDict) -> None:
        """Update global settings directly (public method)."""
        await self._update_global_settings(global_settings)

    # CRUD-style operations for individual global settings components

    async def async_create_global_settings(self, global_settings: GlobalSettingsDict) -> None:
        """
        Create global settings for this sensor set (replaces any existing).

        Args:
            global_settings: Complete global settings configuration

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist or validation fails
        """
        if not self._sensor_set_exists():
            raise SyntheticSensorsError(f"Sensor set {self.sensor_set_id} does not exist")

        current_sensors = self._get_current_sensors()
        await self.async_set_global_settings(global_settings, current_sensors)

    def read_global_settings(self) -> GlobalSettingsDict:
        """
        Read complete global settings for this sensor set.

        Returns:
            Complete global settings dictionary (empty if none exist)
        """
        settings = self.get_global_settings()
        # Ensure we return a properly typed GlobalSettingsDict
        typed_settings: GlobalSettingsDict = settings  # type: ignore[assignment]
        return typed_settings

    async def async_update_global_settings_partial(self, updates: dict[str, Any]) -> None:
        """
        Update specific global settings while preserving others.

        Args:
            updates: Dictionary of global setting updates to merge
        """
        current_global_settings = self.get_global_settings()
        updated_global_settings = current_global_settings.copy()
        updated_global_settings.update(updates)

        # Cast to GlobalSettingsDict since it's compatible
        typed_global_settings: GlobalSettingsDict = updated_global_settings  # type: ignore[assignment]
        await self.async_set_global_settings(typed_global_settings, self._get_current_sensors())

    async def async_delete_global_settings(self) -> bool:
        """
        Delete global settings for this sensor set.

        Returns:
            True if deleted, False if no global settings existed
        """
        data = self.storage_manager.data
        sensor_set_data = data["sensor_sets"].get(self.sensor_set_id)
        if sensor_set_data is None:
            return False

        if "global_settings" not in sensor_set_data:
            return False

        # Delete global settings
        del sensor_set_data["global_settings"]
        sensor_set_data["updated_at"] = self.storage_manager.get_current_timestamp()

        await self.storage_manager.async_save()

        _LOGGER.debug("Deleted global settings for sensor set %s", self.sensor_set_id)
        return True

    # Variable-specific CRUD operations

    async def async_set_global_variable(self, variable_name: str, variable_value: str | int | float) -> None:
        """
        Set a global variable for this sensor set.

        Args:
            variable_name: Name of the variable to set
            variable_value: Value to set for the variable
        """
        current_global_settings = self.get_global_settings()
        if "variables" not in current_global_settings:
            current_global_settings["variables"] = {}

        current_global_settings["variables"][variable_name] = variable_value

        # Cast to GlobalSettingsDict since it's compatible
        typed_global_settings: GlobalSettingsDict = current_global_settings  # type: ignore[assignment]
        await self.async_set_global_settings(typed_global_settings, self._get_current_sensors())

    def get_global_variable(self, variable_name: str) -> str | int | float | None:
        """
        Get a global variable value for this sensor set.

        Args:
            variable_name: Name of the variable to get

        Returns:
            Variable value or None if not found
        """
        global_settings = self.get_global_settings()
        variables = global_settings.get("variables", {})
        value = variables.get(variable_name)
        if isinstance(value, (str | int | float)) or value is None:
            return value
        return None

    async def async_delete_global_variable(self, variable_name: str) -> bool:
        """
        Delete a global variable for this sensor set.

        Args:
            variable_name: Name of the variable to delete

        Returns:
            True if deleted, False if variable didn't exist
        """
        current_global_settings = self.get_global_settings()
        variables = current_global_settings.get("variables", {})

        if variable_name not in variables:
            return False

        del variables[variable_name]

        # Cast to GlobalSettingsDict since it's compatible
        typed_global_settings: GlobalSettingsDict = current_global_settings  # type: ignore[assignment]
        await self.async_set_global_settings(typed_global_settings, self._get_current_sensors())

        _LOGGER.debug("Deleted global variable %s for sensor set %s", variable_name, self.sensor_set_id)
        return True

    def list_global_variables(self) -> dict[str, str | int | float]:
        """
        List all global variables for this sensor set.

        Returns:
            Dictionary of variable names to values
        """
        global_settings = self.get_global_settings()
        variables = global_settings.get("variables", {})
        # Filter to only include valid variable types
        result: dict[str, str | int | float] = {}
        for key, value in variables.items():
            if isinstance(value, (str | int | float)):
                result[key] = value
        return result

    # Device settings CRUD operations

    async def async_set_device_info(self, device_info: dict[str, str]) -> None:
        """
        Set device information for this sensor set.

        Args:
            device_info: Device information dictionary
        """
        current_global_settings = self.get_global_settings()

        # Update device info fields
        for field in DEVICE_INFO_FIELDS:
            if field in device_info:
                current_global_settings[field] = device_info[field]

        # Cast to GlobalSettingsDict since it's compatible
        typed_global_settings: GlobalSettingsDict = current_global_settings  # type: ignore[assignment]
        await self.async_set_global_settings(typed_global_settings, self._get_current_sensors())

    def get_device_info(self) -> dict[str, str]:
        """
        Get device information for this sensor set.

        Returns:
            Dictionary of device information fields
        """
        global_settings = self.get_global_settings()
        device_info = {}

        for field in DEVICE_INFO_FIELDS:
            if field in global_settings:
                device_info[field] = global_settings[field]

        return device_info

    # Metadata CRUD operations

    async def async_set_global_metadata(self, metadata: dict[str, Any]) -> None:
        """
        Set global metadata for this sensor set.

        Args:
            metadata: Global metadata dictionary
        """
        current_global_settings = self.get_global_settings()
        current_global_settings["metadata"] = metadata

        # Cast to GlobalSettingsDict since it's compatible
        typed_global_settings: GlobalSettingsDict = current_global_settings  # type: ignore[assignment]
        await self.async_set_global_settings(typed_global_settings, self._get_current_sensors())

    def get_global_metadata(self) -> dict[str, Any]:
        """
        Get global metadata for this sensor set.

        Returns:
            Global metadata dictionary (empty dict if none)
        """
        global_settings = self.get_global_settings()
        metadata = global_settings.get("metadata", {})
        if isinstance(metadata, dict):
            return metadata
        return {}

    async def async_delete_global_metadata(self) -> bool:
        """
        Delete global metadata for this sensor set.

        Returns:
            True if deleted, False if no metadata existed
        """
        current_global_settings = self.get_global_settings()

        if "metadata" not in current_global_settings:
            return False

        del current_global_settings["metadata"]

        # Cast to GlobalSettingsDict since it's compatible
        typed_global_settings: GlobalSettingsDict = current_global_settings  # type: ignore[assignment]
        await self.async_set_global_settings(typed_global_settings, self._get_current_sensors())

        _LOGGER.debug("Deleted global metadata for sensor set %s", self.sensor_set_id)
        return True

    # Helper methods

    def _sensor_set_exists(self) -> bool:
        """Check if the sensor set exists."""
        data = self.storage_manager.data
        return self.sensor_set_id in data["sensor_sets"]

    def _get_current_sensors(self) -> list[Any]:
        """Get current sensors for validation."""
        return self.storage_manager.list_sensors(sensor_set_id=self.sensor_set_id)
