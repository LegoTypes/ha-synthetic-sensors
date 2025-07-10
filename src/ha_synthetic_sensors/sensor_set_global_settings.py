"""Global settings functionality for SensorSet."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .config_types import GlobalSettingsDict

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
