"""
SensorSet - Handle for individual sensor set operations.

This module provides a focused interface for working with individual sensor sets,
including CRUD operations on sensors within the set and metadata management.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any

import yaml as yaml_lib

from .config_manager import ConfigManager
from .config_models import FormulaConfig, SensorConfig
from .config_types import GlobalSettingsDict
from .entity_index import EntityIndex
from .exceptions import SyntheticSensorsError
from .sensor_set_bulk_ops import SensorSetBulkOps
from .sensor_set_entity_index import SensorSetEntityIndex
from .sensor_set_entity_utils import apply_entity_id_changes_to_sensors_util, update_formula_variables_for_entity_changes
from .sensor_set_global_settings import SensorSetGlobalSettings

if TYPE_CHECKING:
    from .storage_manager import SensorSetMetadata, StorageManager

__all__ = ["SensorSet", "SensorSetModification"]

_LOGGER = logging.getLogger(__name__)


@dataclass
class SensorSetModification:
    """
    Specification for bulk modifications to a sensor set.

    Allows comprehensive changes while preserving sensor unique_ids (keys).
    """

    # Sensors to add (new unique_ids only)
    add_sensors: list[SensorConfig] | None = None

    # Sensors to remove (by unique_id)
    remove_sensors: list[str] | None = None

    # Sensors to update (existing unique_ids only)
    update_sensors: list[SensorConfig] | None = None

    # Entity ID changes (old_entity_id -> new_entity_id)
    entity_id_changes: dict[str, str] | None = None

    # Global settings changes
    global_settings: dict[str, Any] | None = None


class SensorSet:
    """
    Handle for individual sensor set operations.

    Provides a focused interface for working with a specific sensor set,
    including CRUD operations on sensors within the set.
    """

    def __init__(self, storage_manager: StorageManager, sensor_set_id: str) -> None:
        """
        Initialize SensorSet handle.

        Args:
            storage_manager: StorageManager instance
            sensor_set_id: Sensor set identifier
        """
        self.storage_manager = storage_manager
        self.sensor_set_id = sensor_set_id
        self._entity_index = EntityIndex(storage_manager.hass)

        # Initialize handler modules
        self._global_settings = SensorSetGlobalSettings(storage_manager, sensor_set_id)
        self._entity_index_handler = SensorSetEntityIndex(storage_manager, sensor_set_id, self._entity_index)
        self._bulk_ops = SensorSetBulkOps(storage_manager, sensor_set_id)

        # Initialize entity index with current sensors if the sensor set exists
        if self.exists:
            self.rebuild_entity_index()

    @property
    def metadata(self) -> SensorSetMetadata | None:
        """Get sensor set metadata."""
        return self.storage_manager.get_sensor_set_metadata(self.sensor_set_id)

    @property
    def exists(self) -> bool:
        """Check if sensor set exists."""
        return self.metadata is not None

    def _ensure_exists(self) -> None:
        """Ensure sensor set exists."""
        if not self.exists:
            raise SyntheticSensorsError(f"Sensor set not found: {self.sensor_set_id}")

    # Sensor CRUD Operations

    async def async_add_sensor(self, sensor_config: SensorConfig) -> None:
        """
        Add a sensor to this sensor set.

        Args:
            sensor_config: Sensor configuration to add
        """
        self._ensure_exists()

        metadata = self.metadata
        device_identifier = metadata.device_identifier if metadata else None

        await self.storage_manager.async_store_sensor(
            sensor_config=sensor_config,
            sensor_set_id=self.sensor_set_id,
            device_identifier=device_identifier,
        )

        # Rebuild entity index to include new sensor's entities
        self.rebuild_entity_index()

        _LOGGER.debug("Added sensor %s to set %s", sensor_config.unique_id, self.sensor_set_id)

    async def async_update_sensor(self, sensor_config: SensorConfig) -> bool:
        """
        Update a sensor in this sensor set.

        Args:
            sensor_config: Updated sensor configuration

        Returns:
            True if updated, False if sensor not found
        """
        self._ensure_exists()

        # Verify sensor belongs to this set
        if not self.has_sensor(sensor_config.unique_id):
            raise SyntheticSensorsError(f"Sensor {sensor_config.unique_id} not found in sensor set {self.sensor_set_id}")

        success = await self.storage_manager.async_update_sensor(sensor_config)
        if success:
            # Rebuild entity index to reflect updated sensor's entities
            self.rebuild_entity_index()
            _LOGGER.debug("Updated sensor %s in set %s", sensor_config.unique_id, self.sensor_set_id)

        return success

    async def async_remove_sensor(self, unique_id: str) -> bool:
        """
        Remove a sensor from this sensor set.

        Args:
            unique_id: Sensor unique identifier

        Returns:
            True if removed, False if not found
        """
        self._ensure_exists()

        # Verify sensor belongs to this set
        if not self.has_sensor(unique_id):
            _LOGGER.warning("Sensor %s not found in sensor set %s for removal", unique_id, self.sensor_set_id)
            return False

        success = await self.storage_manager.async_delete_sensor(unique_id)
        if success:
            # Rebuild entity index to remove deleted sensor's entities
            self.rebuild_entity_index()
            _LOGGER.debug("Removed sensor %s from set %s", unique_id, self.sensor_set_id)

        return success

    def get_sensor(self, unique_id: str) -> SensorConfig | None:
        """
        Get a sensor from this sensor set.

        Args:
            unique_id: Sensor unique identifier

        Returns:
            SensorConfig if found and belongs to this set, None otherwise
        """
        self._ensure_exists()

        sensor_config = self.storage_manager.get_sensor(unique_id)

        # Verify it belongs to this sensor set
        if sensor_config and self.has_sensor(unique_id):
            return sensor_config

        return None

    def list_sensors(self) -> list[SensorConfig]:
        """
        List all sensors in this sensor set.

        Returns:
            List of sensor configurations
        """
        self._ensure_exists()

        return self.storage_manager.list_sensors(sensor_set_id=self.sensor_set_id)

    def has_sensor(self, unique_id: str) -> bool:
        """
        Check if sensor belongs to this sensor set.

        Args:
            unique_id: Sensor unique identifier

        Returns:
            True if sensor belongs to this set, False otherwise
        """
        sensors = self.list_sensors()
        return unique_id in [s.unique_id for s in sensors]

    # Clean CRUD Interface for Sensors

    def add_sensor(self, sensor_config: SensorConfig) -> None:
        """
        Add a sensor to this sensor set (synchronous version).

        For async operations, use async_add_sensor().

        Args:
            sensor_config: Sensor configuration to add

        Raises:
            SyntheticSensorsError: If sensor already exists or validation fails
        """

        try:
            asyncio.get_running_loop()
            raise SyntheticSensorsError("Use async_add_sensor() in async context")
        except RuntimeError:
            # No running loop, safe to use run_until_complete
            asyncio.run(self.async_add_sensor(sensor_config))

    def update_sensor(self, sensor_config: SensorConfig) -> bool:
        """
        Update a sensor in this sensor set (synchronous version).

        For async operations, use async_update_sensor().

        Args:
            sensor_config: Updated sensor configuration

        Returns:
            True if sensor was updated, False if not found
        """

        try:
            asyncio.get_running_loop()
            raise SyntheticSensorsError("Use async_update_sensor() in async context")
        except RuntimeError:
            # No running loop, safe to use run_until_complete
            return asyncio.run(self.async_update_sensor(sensor_config))

    def remove_sensor(self, unique_id: str) -> bool:
        """
        Remove a sensor from this sensor set (synchronous version).

        For async operations, use async_remove_sensor().

        Args:
            unique_id: Unique identifier of sensor to remove

        Returns:
            True if sensor was removed, False if not found
        """

        try:
            asyncio.get_running_loop()
            raise SyntheticSensorsError("Use async_remove_sensor() in async context")
        except RuntimeError:
            # No running loop, safe to use run_until_complete
            return asyncio.run(self.async_remove_sensor(unique_id))

    def sensor_exists(self, unique_id: str) -> bool:
        """
        Check if a sensor exists in this sensor set.

        Alias for has_sensor() for more intuitive CRUD interface.

        Args:
            unique_id: Unique identifier of the sensor

        Returns:
            True if sensor exists, False otherwise
        """
        return self.has_sensor(unique_id)

    # Global Settings Operations

    def get_global_settings(self) -> dict[str, Any]:
        """
        Get global settings for this sensor set.

        Returns:
            Dictionary of global settings (empty dict if none)
        """
        self._ensure_exists()
        return self._global_settings.get_global_settings()

    async def async_set_global_settings(self, global_settings: GlobalSettingsDict) -> None:
        """
        Set global settings for this sensor set.

        This will replace all existing global settings and trigger:
        - Cache invalidation for affected entities
        - Entity index rebuild to track new entity references
        - Storage save

        Args:
            global_settings: New global settings to set
        """
        self._ensure_exists()

        # Use handler to set global settings (includes validation)
        current_sensors = self.list_sensors()
        await self._global_settings.async_set_global_settings(global_settings, current_sensors)

        # Rebuild entity index to track new entity references
        self.rebuild_entity_index()

        # Invalidate cache for sensors that might use these global variables
        if hasattr(self.storage_manager, "evaluator") and self.storage_manager.evaluator:
            await self.storage_manager.evaluator.async_invalidate_sensor_set_cache(self.sensor_set_id)

    async def async_update_global_settings(self, updates: dict[str, Any]) -> None:
        """
        Update specific global settings while preserving others.

        This merges the updates with existing global settings and triggers:
        - Cache invalidation for affected entities
        - Entity index rebuild to track new entity references
        - Storage save

        Args:
            updates: Dictionary of global setting updates to merge
        """
        self._ensure_exists()
        current_sensors = self.list_sensors()
        await self._global_settings.async_update_global_settings(updates, current_sensors)

        # Rebuild entity index to track new entity references
        self.rebuild_entity_index()

        # Invalidate cache for sensors that might use these global variables
        if hasattr(self.storage_manager, "evaluator") and self.storage_manager.evaluator:
            await self.storage_manager.evaluator.async_invalidate_sensor_set_cache(self.sensor_set_id)

    def _invalidate_cache_for_global_changes(self, global_settings: dict[str, Any]) -> None:
        """
        Invalidate formula caches for entities that might be affected by global setting changes.

        Args:
            global_settings: The new global settings
        """
        # Get entity change handler from storage manager
        entity_change_handler = getattr(self.storage_manager, "_entity_change_handler", None)
        if not entity_change_handler:
            return

        # Extract entity IDs from global variables
        global_variables = global_settings.get("variables", {})
        affected_entities = []

        for var_value in global_variables.values():
            if isinstance(var_value, str) and var_value.startswith(
                ("sensor.", "input_", "binary_sensor.", "switch.", "light.", "climate.")
            ):
                affected_entities.append(var_value)

        # Invalidate cache for each affected entity
        for entity_id in affected_entities:
            entity_change_handler.invalidate_cache(entity_id)

        if affected_entities:
            _LOGGER.debug("Invalidated cache for %d entities due to global settings change", len(affected_entities))

    # Bulk Operations

    async def async_replace_sensors(self, sensor_configs: list[SensorConfig]) -> None:
        """
        Replace all sensors in this sensor set.

        Args:
            sensor_configs: New sensor configurations
        """
        self._ensure_exists()

        metadata = self.metadata
        device_identifier = metadata.device_identifier if metadata else None

        # Store new sensors (this replaces existing ones)
        await self.storage_manager.async_store_sensors_bulk(
            sensor_configs=sensor_configs,
            sensor_set_id=self.sensor_set_id,
            device_identifier=device_identifier,
        )

        _LOGGER.debug("Replaced %d sensors in set %s", len(sensor_configs), self.sensor_set_id)

    async def async_modify(self, modification: SensorSetModification) -> dict[str, Any]:
        """
        Perform bulk modifications to this sensor set.

        Supports comprehensive changes while preserving sensor unique_ids (keys):
        - Add new sensors
        - Remove existing sensors
        - Update existing sensors (formulas, entity_ids, etc.)
        - Bulk entity ID changes across all sensors
        - Global settings changes

        Optimized to rebuild entity index only once and coordinate entity ID changes
        to avoid event thrashing.

        Args:
            modification: Specification of changes to make

        Returns:
            Summary of changes made

        Raises:
            SyntheticSensorsError: If validation fails or conflicts occur
        """
        self._ensure_exists()

        # Collect all changes for bulk processing
        changes_summary = {
            "sensors_added": 0,
            "sensors_removed": 0,
            "sensors_updated": 0,
            "entity_ids_changed": 0,
            "global_settings_updated": False,
        }

        # Get current sensors for validation and processing
        current_sensors = {s.unique_id: s for s in self.list_sensors()}

        # 1. Validate the modification request
        self._bulk_ops.validate_modification(modification, current_sensors)

        # 2. CRITICAL: Rebuild entity index to reflect FINAL state (for event storm protection)
        # This must happen BEFORE any storage or registry changes
        final_sensors = self._bulk_ops.build_final_sensor_list(modification, current_sensors)
        if modification.entity_id_changes:
            final_sensors = self._bulk_ops.apply_entity_id_changes_to_sensors(modification.entity_id_changes, final_sensors)
        final_global_settings = self._global_settings.build_final_global_settings(modification.global_settings)
        self._entity_index_handler.rebuild_entity_index_for_modification(final_sensors, final_global_settings)
        _LOGGER.debug("Pre-updated entity index for storm protection in sensor set %s", self.sensor_set_id)

        # 3. Update global settings if specified (BEFORE entity ID changes to avoid conflicts)
        if modification.global_settings is not None:
            # Cast to GlobalSettingsDict since it's compatible
            typed_global_settings: GlobalSettingsDict = modification.global_settings  # type: ignore[assignment]
            await self._global_settings.update_global_settings_direct(typed_global_settings)
            changes_summary["global_settings_updated"] = True

        # 4. Apply entity ID changes (but don't update HA registry yet - collect changes)
        entity_id_changes_to_apply = {}
        if modification.entity_id_changes:
            entity_id_changes_to_apply = modification.entity_id_changes.copy()
            # Apply changes to storage but defer HA registry updates
            await self._apply_entity_id_changes_deferred(entity_id_changes_to_apply, current_sensors)
            changes_summary["entity_ids_changed"] = len(entity_id_changes_to_apply)

        # 5. Remove sensors (use direct storage operations)
        if modification.remove_sensors:
            for unique_id in modification.remove_sensors:
                await self._remove_sensor_direct(unique_id)
                changes_summary["sensors_removed"] += 1

        # 6. Update existing sensors (use direct storage operations)
        if modification.update_sensors:
            for sensor_config in modification.update_sensors:
                await self._update_sensor_direct(sensor_config)
                changes_summary["sensors_updated"] += 1

        # 7. Add new sensors (use direct storage operations)
        if modification.add_sensors:
            for sensor_config in modification.add_sensors:
                await self._add_sensor_direct(sensor_config)
                changes_summary["sensors_added"] += 1

        # 8. Apply entity ID changes to HA registry in one batch (EntityIndex already reflects new state)
        if entity_id_changes_to_apply:
            await self._apply_entity_registry_changes(entity_id_changes_to_apply)

        _LOGGER.debug(
            "Modified sensor set %s: %d added, %d removed, %d updated, %d entity IDs changed",
            self.sensor_set_id,
            changes_summary["sensors_added"],
            changes_summary["sensors_removed"],
            changes_summary["sensors_updated"],
            changes_summary["entity_ids_changed"],
        )

        return changes_summary

    def _build_final_sensor_list(
        self, modification: SensorSetModification, current_sensors: dict[str, SensorConfig]
    ) -> dict[str, SensorConfig]:
        """Build the final sensor list after applying all modifications."""
        final_sensors = {}

        # Start with current sensors
        for unique_id, sensor in current_sensors.items():
            final_sensors[unique_id] = sensor

        # Remove sensors
        if modification.remove_sensors:
            for unique_id in modification.remove_sensors:
                final_sensors.pop(unique_id, None)

        # Update sensors
        if modification.update_sensors:
            for sensor in modification.update_sensors:
                final_sensors[sensor.unique_id] = sensor

        # Add sensors
        if modification.add_sensors:
            for sensor in modification.add_sensors:
                final_sensors[sensor.unique_id] = sensor

        return final_sensors

    def _apply_entity_id_changes_to_sensors(
        self, entity_id_changes: dict[str, str], sensors: dict[str, SensorConfig]
    ) -> dict[str, SensorConfig]:
        """Apply entity ID changes to sensor configurations."""
        return apply_entity_id_changes_to_sensors_util(entity_id_changes, sensors)

    def _update_formula_variables_for_entity_changes(self, formula: FormulaConfig, entity_id_changes: dict[str, str]) -> None:
        """Update formula variables for entity ID changes."""
        update_formula_variables_for_entity_changes(formula, entity_id_changes)

    def _validate_final_state(self, final_global_settings: dict[str, Any], final_sensors: dict[str, SensorConfig]) -> None:
        """Validate the final state for global settings conflicts."""
        if not final_global_settings:
            return

        final_sensor_list = list(final_sensors.values())
        # Cast to GlobalSettingsDict since it's compatible
        typed_global_settings: GlobalSettingsDict = final_global_settings  # type: ignore[assignment]
        self.storage_manager.validate_no_global_conflicts(final_sensor_list, typed_global_settings)
        self.storage_manager.validate_no_attribute_variable_conflicts(final_sensor_list)

    async def _apply_entity_id_changes_deferred(
        self, entity_id_changes: dict[str, str], current_sensors: dict[str, SensorConfig]
    ) -> None:
        """
        Apply entity ID changes to storage without updating HA registry or entity index.

        This is used during bulk operations to defer registry updates until the end.

        Args:
            entity_id_changes: Map of old_entity_id -> new_entity_id
            current_sensors: Current sensors to update
        """
        # Update our storage (sensor configs) only
        for sensor_config in current_sensors.values():
            updated = False

            # Update sensor entity_id
            if sensor_config.entity_id and sensor_config.entity_id in entity_id_changes:
                old_id = sensor_config.entity_id
                sensor_config.entity_id = entity_id_changes[sensor_config.entity_id]
                updated = True
                _LOGGER.debug("Updated sensor %s entity_id: %s -> %s", sensor_config.unique_id, old_id, sensor_config.entity_id)

            # Update formula variables
            for formula in sensor_config.formulas:
                if formula.variables:
                    for var_name, var_value in formula.variables.items():
                        if isinstance(var_value, str) and var_value in entity_id_changes:
                            old_value = var_value
                            formula.variables[var_name] = entity_id_changes[var_value]
                            updated = True
                            _LOGGER.debug(
                                "Updated sensor %s formula %s variable %s: %s -> %s",
                                sensor_config.unique_id,
                                formula.id,
                                var_name,
                                old_value,
                                formula.variables[var_name],
                            )

            # Save updated sensor directly to storage (bypass entity index updates)
            if updated:
                await self._update_sensor_direct(sensor_config)

    async def _apply_entity_registry_changes(self, entity_id_changes: dict[str, str]) -> None:
        """
        Apply entity ID changes to Home Assistant's entity registry in batch.

        Args:
            entity_id_changes: Map of old_entity_id -> new_entity_id
        """
        from homeassistant.helpers import entity_registry as er  # pylint: disable=import-outside-toplevel

        registry_updates = []
        try:
            entity_registry = er.async_get(self.storage_manager.hass)

            for old_entity_id, new_entity_id in entity_id_changes.items():
                try:
                    # Check if entity exists in HA registry
                    entity_entry = entity_registry.async_get(old_entity_id)
                    if entity_entry:
                        # Update the entity ID in HA's registry
                        entity_registry.async_update_entity(old_entity_id, new_entity_id=new_entity_id)
                        registry_updates.append(f"{old_entity_id} -> {new_entity_id}")
                        _LOGGER.debug("Updated HA entity registry: %s -> %s", old_entity_id, new_entity_id)
                    else:
                        _LOGGER.debug("Entity %s not found in HA registry, skipping registry update", old_entity_id)
                except Exception as e:
                    _LOGGER.debug("Failed to update HA entity registry for %s -> %s: %s", old_entity_id, new_entity_id, e)
        except Exception as e:
            # Entity registry not available (e.g., in tests) - continue without HA registry updates
            _LOGGER.debug("Entity registry not available, skipping HA registry updates: %s", e)

        # Invalidate formula caches for the changed entities using persistent handler
        if registry_updates:
            entity_change_handler = self.storage_manager.entity_change_handler
            for old_entity_id, new_entity_id in entity_id_changes.items():
                entity_change_handler.handle_entity_id_change(old_entity_id, new_entity_id)

            _LOGGER.debug("Applied %d entity ID changes to HA registry: %s", len(registry_updates), ", ".join(registry_updates))

    async def _add_sensor_direct(self, sensor_config: SensorConfig) -> None:
        """Add sensor directly to storage without entity index updates."""
        await self.storage_manager.async_store_sensor(
            sensor_config=sensor_config,
            sensor_set_id=self.sensor_set_id,
            device_identifier=self.metadata.device_identifier if self.metadata else None,
        )

    async def _update_sensor_direct(self, sensor_config: SensorConfig) -> None:
        """Update sensor directly in storage without entity index updates."""
        data = self.storage_manager.data

        if sensor_config.unique_id not in data["sensors"]:
            _LOGGER.warning("Sensor %s not found for direct update", sensor_config.unique_id)
            return

        stored_sensor = data["sensors"][sensor_config.unique_id]
        sensor_set_id = stored_sensor.get("sensor_set_id")

        # Update the sensor config data and timestamp (skip entity index updates)
        stored_sensor["config_data"] = self.storage_manager.serialize_sensor_config(sensor_config)
        stored_sensor["updated_at"] = self.storage_manager.get_current_timestamp()

        # Update sensor set metadata
        if sensor_set_id and sensor_set_id in data["sensor_sets"]:
            data["sensor_sets"][sensor_set_id]["updated_at"] = self.storage_manager.get_current_timestamp()

        await self.storage_manager.async_save()
        _LOGGER.debug("Direct updated sensor: %s", sensor_config.unique_id)

    async def _remove_sensor_direct(self, unique_id: str) -> None:
        """Remove sensor directly from storage without entity index updates."""
        data = self.storage_manager.data

        if unique_id not in data["sensors"]:
            _LOGGER.warning("Sensor %s not found for direct removal", unique_id)
            return

        # Get sensor set ID for cleanup
        stored_sensor = data["sensors"][unique_id]
        sensor_set_id = stored_sensor.get("sensor_set_id")

        # Delete the sensor (skip entity index updates)
        del data["sensors"][unique_id]

        # Update sensor set metadata
        if sensor_set_id and sensor_set_id in data["sensor_sets"]:
            data["sensor_sets"][sensor_set_id]["updated_at"] = self.storage_manager.get_current_timestamp()
            data["sensor_sets"][sensor_set_id]["sensor_count"] = len(
                [s for s in data["sensors"].values() if s.get("sensor_set_id") == sensor_set_id]
            )

        await self.storage_manager.async_save()
        _LOGGER.debug("Direct deleted sensor: %s", unique_id)

    async def _update_global_settings(self, global_settings: dict[str, Any]) -> None:
        """
        Update global settings for this sensor set.

        Args:
            global_settings: New global settings
        """
        data = self.storage_manager.data

        if self.sensor_set_id in data["sensor_sets"]:
            data["sensor_sets"][self.sensor_set_id]["global_settings"] = global_settings
            data["sensor_sets"][self.sensor_set_id]["updated_at"] = self.storage_manager.get_current_timestamp()
            await self.storage_manager.async_save()

    # YAML Operations

    async def async_import_yaml(self, yaml_content: str) -> None:
        """
        Import YAML content to this sensor set, replacing existing sensors.

        Args:
            yaml_content: YAML content to import
        """
        metadata = self.metadata
        device_identifier = metadata.device_identifier if metadata else None

        await self.storage_manager.async_from_yaml(
            yaml_content=yaml_content,
            sensor_set_id=self.sensor_set_id,
            device_identifier=device_identifier,
        )

        _LOGGER.debug("Imported YAML to sensor set: %s", self.sensor_set_id)

    def export_yaml(self) -> str:
        """
        Export this sensor set to YAML format.

        Returns:
            YAML content as string
        """
        self._ensure_exists()

        return self.storage_manager.export_yaml(self.sensor_set_id)

    # Sensor Set Management

    async def async_delete(self) -> bool:
        """
        Delete this entire sensor set.

        Returns:
            True if deleted, False if not found
        """
        success = await self.storage_manager.async_delete_sensor_set(self.sensor_set_id)
        if success:
            _LOGGER.debug("Deleted sensor set: %s", self.sensor_set_id)

        return success

    # Statistics and Info

    @property
    def sensor_count(self) -> int:
        """Get number of sensors in this set."""
        if not self.exists:
            return 0
        return len(self.list_sensors())

    def get_summary(self) -> dict[str, Any]:
        """
        Get summary information for this sensor set.

        Returns:
            Dictionary with sensor set summary
        """
        if not self.exists:
            return {
                "sensor_set_id": self.sensor_set_id,
                "exists": False,
            }

        metadata = self.metadata
        sensors = self.list_sensors()

        return {
            "sensor_set_id": self.sensor_set_id,
            "exists": True,
            "device_identifier": metadata.device_identifier if metadata else None,
            "name": metadata.name if metadata else None,
            "description": metadata.description if metadata else None,
            "sensor_count": len(sensors),
            "created_at": metadata.created_at if metadata else None,
            "updated_at": metadata.updated_at if metadata else None,
            "sensor_unique_ids": [s.unique_id for s in sensors],
        }

    # Enhanced error handling and validation methods

    def validate_sensor_config(self, sensor_config: SensorConfig) -> list[str]:
        """
        Validate a sensor configuration before adding/updating.

        Args:
            sensor_config: Sensor configuration to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Basic validation
        if not sensor_config.unique_id:
            errors.append("Sensor unique_id is required")

        if not sensor_config.formulas:
            errors.append("Sensor must have at least one formula")

        # Check for formula ID uniqueness within sensor
        formula_ids = [f.id for f in sensor_config.formulas]
        if len(formula_ids) != len(set(formula_ids)):
            errors.append("Sensor has duplicate formula IDs")

        # Validate each formula has required fields
        for formula in sensor_config.formulas:
            if not formula.formula:
                errors.append(f"Formula '{formula.id}' missing formula expression")

        return errors

    def get_sensor_errors(self) -> dict[str, list[str]]:
        """
        Get validation errors for all sensors in this sensor set.

        Returns:
            Dictionary mapping sensor unique_id to list of errors
        """
        self._ensure_exists()

        errors = {}
        sensors = self.list_sensors()

        for sensor in sensors:
            sensor_errors = self.validate_sensor_config(sensor)
            if sensor_errors:
                errors[sensor.unique_id] = sensor_errors

        return errors

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
        validation_results: dict[str, Any] = {
            "yaml_errors": [],
            "config_errors": [],
            "sensor_errors": {},
        }

        try:
            # Parse YAML
            yaml_data = yaml_lib.safe_load(yaml_content)
            if not yaml_data:
                validation_results["yaml_errors"].append("Empty YAML content")
                return validation_results

        except yaml_lib.YAMLError as e:
            validation_results["yaml_errors"].append(f"YAML parsing error: {e}")
            return validation_results

        try:
            # Validate configuration structure
            config_manager = ConfigManager(self.storage_manager.hass)
            config = config_manager.load_from_dict(yaml_data)

            # Validate overall config
            config_errors = config.validate()
            validation_results["config_errors"] = config_errors

            # Validate individual sensors
            for sensor in config.sensors:
                sensor_errors = self.validate_sensor_config(sensor)
                if sensor_errors:
                    validation_results["sensor_errors"][sensor.unique_id] = sensor_errors

        except Exception as e:
            validation_results["config_errors"].append(f"Configuration validation error: {e}")

        return validation_results

    def is_valid(self) -> bool:
        """
        Check if this sensor set and all its sensors are valid.

        Returns:
            True if all sensors are valid, False otherwise
        """
        if not self.exists:
            return False

        errors = self.get_sensor_errors()
        return len(errors) == 0

    def is_entity_tracked(self, entity_id: str) -> bool:
        """
        Check if an entity ID is tracked by this sensor set.

        Args:
            entity_id: Entity ID to check

        Returns:
            True if entity ID is tracked by this sensor set
        """
        return self._entity_index_handler.is_entity_tracked(entity_id)

    def get_entity_index_stats(self) -> dict[str, Any]:
        """
        Get entity index statistics for this sensor set.

        Returns:
            Dictionary with entity index statistics
        """
        return self._entity_index_handler.get_entity_index_stats()

    def rebuild_entity_index(self) -> None:
        """Rebuild the entity index from all sensors and global settings in this sensor set."""
        sensors = self.list_sensors()
        self._entity_index_handler.rebuild_entity_index(sensors)
