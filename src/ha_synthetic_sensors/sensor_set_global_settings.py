"""Global settings functionality for SensorSet with CRUD operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .config_types import GlobalSettingsDict
from .exceptions import SyntheticSensorsError

# Device info field names (shared constant to avoid duplication)
DEVICE_INFO_FIELDS = [
    "device_identifier",
    "device_name",
    "device_manufacturer",
    "device_model",
    "device_sw_version",
    "device_hw_version",
    "suggested_area",
]

if TYPE_CHECKING:
    from .config_models import SensorConfig
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

    async def async_set_global_settings(self, global_settings: GlobalSettingsDict, current_sensors: list[SensorConfig]) -> None:
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

    async def async_update_global_settings(self, updates: dict[str, Any], current_sensors: list[SensorConfig]) -> None:
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
        Build final global settings after applying modifications.

        Args:
            modification_global_settings: Global settings from modification (None = no change)

        Returns:
            Final global settings after modification
        """
        if modification_global_settings is None:
            # No change to global settings
            return self.get_global_settings()

        # Use the modification's global settings
        return modification_global_settings

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
        Update specific parts of global settings while preserving others.

        Args:
            updates: Dictionary of global setting updates to merge

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist or validation fails
        """
        if not self._sensor_set_exists():
            raise SyntheticSensorsError(f"Sensor set {self.sensor_set_id} does not exist")

        current_sensors = self._get_current_sensors()
        await self.async_update_global_settings(updates, current_sensors)

    async def async_delete_global_settings(self) -> bool:
        """
        Delete all global settings for this sensor set.

        Returns:
            True if global settings were deleted, False if none existed

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist
        """
        if not self._sensor_set_exists():
            raise SyntheticSensorsError(f"Sensor set {self.sensor_set_id} does not exist")

        current_settings = self.get_global_settings()
        if not current_settings:
            return False

        empty_settings: GlobalSettingsDict = {}
        await self._update_global_settings(empty_settings)
        return True

    # Variable-specific CRUD operations

    async def async_set_global_variable(self, variable_name: str, variable_value: str | int | float) -> None:
        """
        Set a specific global variable.

        Args:
            variable_name: Name of the variable to set
            variable_value: Value of the variable

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist or validation fails
        """
        current_settings = self.read_global_settings()
        variables = current_settings.get("variables", {}).copy()
        variables[variable_name] = variable_value

        updates = {"variables": variables}
        await self.async_update_global_settings_partial(updates)

    def get_global_variable(self, variable_name: str) -> str | int | float | None:
        """
        Get a specific global variable value.

        Args:
            variable_name: Name of the variable to get

        Returns:
            Variable value if found, None otherwise
        """
        current_settings = self.read_global_settings()
        variables = current_settings.get("variables", {})
        return variables.get(variable_name)

    async def async_delete_global_variable(self, variable_name: str) -> bool:
        """
        Delete a specific global variable.

        Args:
            variable_name: Name of the variable to delete

        Returns:
            True if variable was deleted, False if it didn't exist

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist
        """
        current_settings = self.read_global_settings()
        variables = current_settings.get("variables", {})

        if variable_name not in variables:
            return False

        variables = variables.copy()
        del variables[variable_name]

        updates = {"variables": variables}
        await self.async_update_global_settings_partial(updates)
        return True

    def list_global_variables(self) -> dict[str, str | int | float]:
        """
        List all global variables.

        Returns:
            Dictionary of all global variables
        """
        current_settings = self.read_global_settings()
        return current_settings.get("variables", {}).copy()

    # Device settings CRUD operations

    async def async_set_device_info(self, device_info: dict[str, str]) -> None:
        """
        Set device information in global settings.

        Args:
            device_info: Dictionary containing device information fields

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist or validation fails
        """
        await self.async_update_global_settings_partial(device_info)

    def get_device_info(self) -> dict[str, str]:
        """
        Get device information from global settings.

        Returns:
            Dictionary containing device information
        """
        current_settings = self.read_global_settings()
        device_fields = DEVICE_INFO_FIELDS

        device_info: dict[str, str] = {}
        for field in device_fields:
            value = current_settings.get(field)
            if value is not None:
                device_info[field] = str(value)

        return device_info

    # Metadata CRUD operations

    async def async_set_global_metadata(self, metadata: dict[str, Any]) -> None:
        """
        Set global metadata.

        Args:
            metadata: Dictionary containing metadata

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist or validation fails
        """
        updates = {"metadata": metadata}
        await self.async_update_global_settings_partial(updates)

    def get_global_metadata(self) -> dict[str, Any]:
        """
        Get global metadata.

        Returns:
            Dictionary containing global metadata
        """
        current_settings = self.read_global_settings()
        return current_settings.get("metadata", {}).copy()

    async def async_delete_global_metadata(self) -> bool:
        """
        Delete all global metadata.

        Returns:
            True if metadata was deleted, False if none existed

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist
        """
        current_settings = self.read_global_settings()
        if "metadata" not in current_settings or not current_settings["metadata"]:
            return False

        updates: dict[str, Any] = {"metadata": {}}
        await self.async_update_global_settings_partial(updates)
        return True

    # Helper methods

    def _sensor_set_exists(self) -> bool:
        """Check if the sensor set exists."""
        data = self.storage_manager.data
        return self.sensor_set_id in data["sensor_sets"]

    def _get_current_sensors(self) -> list[SensorConfig]:
        """Get current sensors for validation."""
        return self.storage_manager.list_sensors(sensor_set_id=self.sensor_set_id)
