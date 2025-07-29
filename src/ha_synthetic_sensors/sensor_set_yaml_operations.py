"""
YAML operations mixin for SensorSet.

This module contains YAML-related operations that can be mixed into the SensorSet class
to reduce the main class size and improve organization.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .sensor_set_globals_yaml_crud import SensorSetGlobalsYamlCrud
    from .sensor_set_validation import SensorSetValidation
    from .sensor_set_yaml_crud import SensorSetYamlCrud
    from .storage_manager import StorageManager

_LOGGER = logging.getLogger(__name__)


class SensorSetYamlOperationsMixin:
    """Mixin class providing YAML operations for SensorSet."""

    # These attributes will be provided by the SensorSet class
    storage_manager: StorageManager
    sensor_set_id: str
    _yaml_crud: SensorSetYamlCrud
    _globals_yaml_crud: SensorSetGlobalsYamlCrud
    _validation: SensorSetValidation

    def _ensure_exists(self) -> None:
        """Ensure sensor set exists - implemented by SensorSet."""
        raise NotImplementedError

    def rebuild_entity_index(self) -> None:
        """Rebuild entity index - implemented by SensorSet."""
        raise NotImplementedError

    @property
    def metadata(self) -> Any:
        """Get sensor set metadata - implemented by SensorSet."""
        raise NotImplementedError

    # YAML-based CRUD Operations

    async def async_add_sensor_from_yaml(self, sensor_yaml: str) -> None:
        """
        Add a sensor to this sensor set from YAML string.

        Args:
            sensor_yaml: YAML string containing sensor configuration WITH sensor key
                        Example:
                        ```
                        power_analysis:
                          formula: base_power * multiplier
                          name: Power Analysis
                          unit_of_measurement: W
                          device_class: power
                          metadata:
                            unit_of_measurement: W
                            device_class: power
                        ```

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist, YAML is invalid, or sensor already exists
        """
        self._ensure_exists()

        await self._yaml_crud.async_add_sensor_from_yaml(sensor_yaml)

    async def async_update_sensor_from_yaml(self, sensor_yaml: str) -> bool:
        """
        Update a sensor in this sensor set from YAML string.

        Args:
            sensor_yaml: YAML string containing updated sensor configuration WITH sensor key
                        The sensor key must match an existing sensor.

        Returns:
            True if sensor was updated, False if sensor doesn't exist

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist or YAML is invalid
        """
        self._ensure_exists()

        return await self._yaml_crud.async_update_sensor_from_yaml(sensor_yaml)

    def add_sensor_from_yaml(self, sensor_yaml: str) -> None:
        """
        Add a sensor to this sensor set from YAML string (synchronous version).

        For async operations, use async_add_sensor_from_yaml().

        Args:
            sensor_yaml: YAML string containing sensor configuration WITH sensor key

        Raises:
            SyntheticSensorsError: If used in async context, sensor set doesn't exist, YAML is invalid, or sensor already exists
        """
        self._yaml_crud.add_sensor_from_yaml(sensor_yaml)

    def update_sensor_from_yaml(self, sensor_yaml: str) -> bool:
        """
        Update a sensor in this sensor set from YAML string (synchronous version).

        For async operations, use async_update_sensor_from_yaml().

        Args:
            sensor_yaml: YAML string containing updated sensor configuration WITH sensor key

        Returns:
            True if sensor was updated, False if sensor doesn't exist

        Raises:
            SyntheticSensorsError: If used in async context, sensor set doesn't exist, or YAML is invalid
        """
        return self._yaml_crud.update_sensor_from_yaml(sensor_yaml)

    # YAML-based Global Settings CRUD Operations

    async def async_create_global_settings_from_yaml(self, global_settings_yaml: str) -> None:
        """Create/replace global settings from YAML string."""
        await self._globals_yaml_crud.async_create_global_settings_from_yaml(global_settings_yaml)
        self.rebuild_entity_index()
        if hasattr(self.storage_manager, "evaluator") and self.storage_manager.evaluator:
            await self.storage_manager.evaluator.async_invalidate_sensor_set_cache(self.sensor_set_id)

    async def async_update_global_settings_from_yaml(self, global_settings_yaml: str) -> None:
        """Update global settings from YAML string (merges with existing)."""
        await self._globals_yaml_crud.async_update_global_settings_from_yaml(global_settings_yaml)
        self.rebuild_entity_index()
        if hasattr(self.storage_manager, "evaluator") and self.storage_manager.evaluator:
            await self.storage_manager.evaluator.async_invalidate_sensor_set_cache(self.sensor_set_id)

    def read_global_settings_as_yaml(self) -> str:
        """Read global settings as YAML string."""
        return self._globals_yaml_crud.read_global_settings_as_yaml()

    def create_global_settings_from_yaml(self, global_settings_yaml: str) -> None:
        """Create/replace global settings from YAML string (synchronous)."""
        self._globals_yaml_crud.create_global_settings_from_yaml(global_settings_yaml)
        self.rebuild_entity_index()

    def update_global_settings_from_yaml(self, global_settings_yaml: str) -> None:
        """Update global settings from YAML string (synchronous)."""
        self._globals_yaml_crud.update_global_settings_from_yaml(global_settings_yaml)
        self.rebuild_entity_index()

    # YAML Variable Operations

    async def async_add_variable_from_yaml(self, variable_yaml: str) -> None:
        """Add or update global variables from YAML string."""
        await self._globals_yaml_crud.async_add_variable_from_yaml(variable_yaml)
        self.rebuild_entity_index()
        if hasattr(self.storage_manager, "evaluator") and self.storage_manager.evaluator:
            await self.storage_manager.evaluator.async_invalidate_sensor_set_cache(self.sensor_set_id)

    def read_variables_as_yaml(self) -> str:
        """Read global variables as YAML string."""
        return self._globals_yaml_crud.read_variables_as_yaml()

    # YAML Device Info Operations

    async def async_update_device_info_from_yaml(self, device_info_yaml: str) -> None:
        """Update device information from YAML string."""
        await self._globals_yaml_crud.async_update_device_info_from_yaml(device_info_yaml)

    def read_device_info_as_yaml(self) -> str:
        """Read device information as YAML string."""
        return self._globals_yaml_crud.read_device_info_as_yaml()

    # YAML Metadata Operations

    async def async_update_metadata_from_yaml(self, metadata_yaml: str) -> None:
        """Update global metadata from YAML string."""
        await self._globals_yaml_crud.async_update_metadata_from_yaml(metadata_yaml)

    def read_metadata_as_yaml(self) -> str:
        """Read global metadata as YAML string."""
        return self._globals_yaml_crud.read_metadata_as_yaml()

    # YAML Import/Export Operations

    async def async_import_yaml(self, yaml_content: str) -> None:
        """
        Import sensors from YAML content into this sensor set.

        Args:
            yaml_content: Complete YAML configuration content

        Raises:
            SyntheticSensorsError: If YAML is invalid
        """
        # Get device identifier from metadata
        metadata = self.metadata
        device_identifier = metadata.device_identifier if metadata else None

        # Import the YAML using the storage manager
        await self.storage_manager.async_from_yaml(
            yaml_content=yaml_content,
            sensor_set_id=self.sensor_set_id,
            device_identifier=device_identifier,
        )

        _LOGGER.debug("Imported YAML to sensor set: %s", self.sensor_set_id)

    async def async_export_yaml(self) -> str:
        """
        Export sensor set configuration to YAML string (async version).

        Returns:
            YAML string containing sensor set configuration

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist
        """
        self._ensure_exists()

        # Use thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.storage_manager.export_yaml, self.sensor_set_id)

    def export_yaml(self) -> str:
        """
        Export sensor set configuration to YAML string.

        Returns:
            YAML string containing sensor set configuration

        Raises:
            SyntheticSensorsError: If sensor set doesn't exist
        """
        self._ensure_exists()

        return self.storage_manager.export_yaml(self.sensor_set_id)

    async def async_validate_import(self, yaml_content: str) -> dict[str, Any]:
        """
        Validate YAML content before importing without actually importing.

        Args:
            yaml_content: YAML content to validate

        Returns:
            Dictionary with validation results:
            - "yaml_errors": YAML parsing errors
            - "config_errors": Configuration validation errors
            - "sensor_errors": Per-sensor validation errors
        """
        # Use the validation handler from the sensor set
        return await self._validation.async_validate_import(yaml_content)
