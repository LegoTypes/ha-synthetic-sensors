"""
SensorSet - Handle for individual sensor set operations.

This module provides a focused interface for working with individual sensor sets,
including CRUD operations on sensors within the set and metadata management.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any

from .config_manager import SensorConfig
from .entity_index import EntityIndex
from .exceptions import SyntheticSensorsError

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

        # Initialize entity index with current sensors if the sensor set exists
        if self.exists:
            self._rebuild_entity_index()

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
        self._rebuild_entity_index()

        _LOGGER.info("Added sensor %s to set %s", sensor_config.unique_id, self.sensor_set_id)

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
            self._rebuild_entity_index()
            _LOGGER.info("Updated sensor %s in set %s", sensor_config.unique_id, self.sensor_set_id)

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
            self._rebuild_entity_index()
            _LOGGER.info("Removed sensor %s from set %s", unique_id, self.sensor_set_id)

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

        _LOGGER.info("Replaced %d sensors in set %s", len(sensor_configs), self.sensor_set_id)

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
        self._validate_modification(modification, current_sensors)

        # 2. CRITICAL: Rebuild entity index to reflect FINAL state (for event storm protection)
        # This must happen BEFORE any storage or registry changes
        self._rebuild_entity_index_for_modification(modification, current_sensors)
        _LOGGER.debug("Pre-updated entity index for storm protection in sensor set %s", self.sensor_set_id)

        # 3. Update global settings if specified (BEFORE entity ID changes to avoid conflicts)
        if modification.global_settings is not None:
            await self._update_global_settings(modification.global_settings)
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

        _LOGGER.info(
            "Modified sensor set %s: %d added, %d removed, %d updated, %d entity IDs changed",
            self.sensor_set_id,
            changes_summary["sensors_added"],
            changes_summary["sensors_removed"],
            changes_summary["sensors_updated"],
            changes_summary["entity_ids_changed"],
        )

        return changes_summary

    def _validate_modification(self, modification: SensorSetModification, current_sensors: dict[str, SensorConfig]) -> None:
        """
        Validate a modification request before applying changes.

        Args:
            modification: Modification specification
            current_sensors: Current sensors in the set

        Raises:
            SyntheticSensorsError: If validation fails or conflicts occur
        """
        errors = []

        # Validate add_sensors (must be new unique_ids)
        if modification.add_sensors:
            for sensor in modification.add_sensors:
                if sensor.unique_id in current_sensors:
                    errors.append(f"Cannot add sensor {sensor.unique_id}: already exists")

        # Validate remove_sensors (must exist)
        if modification.remove_sensors:
            for unique_id in modification.remove_sensors:
                if unique_id not in current_sensors:
                    errors.append(f"Cannot remove sensor {unique_id}: not found")

        # Validate update_sensors (must exist, cannot change unique_id)
        if modification.update_sensors:
            for sensor in modification.update_sensors:
                if sensor.unique_id not in current_sensors:
                    errors.append(f"Cannot update sensor {sensor.unique_id}: not found")

        # Check for conflicts between operations
        if modification.add_sensors and modification.remove_sensors:
            add_ids = {s.unique_id for s in modification.add_sensors}
            remove_ids = set(modification.remove_sensors)
            conflicts = add_ids & remove_ids
            if conflicts:
                errors.append(f"Cannot add and remove same sensors: {conflicts}")

        if modification.update_sensors and modification.remove_sensors:
            update_ids = {s.unique_id for s in modification.update_sensors}
            remove_ids = set(modification.remove_sensors)
            conflicts = update_ids & remove_ids
            if conflicts:
                errors.append(f"Cannot update and remove same sensors: {conflicts}")

        # Validate global settings conflicts
        if modification.global_settings is not None or modification.entity_id_changes:
            try:
                self._validate_global_settings_conflicts(modification, current_sensors)
            except Exception as e:
                errors.append(str(e))

        if errors:
            raise SyntheticSensorsError(f"Modification validation failed: {'; '.join(errors)}")

    def _validate_global_settings_conflicts(
        self, modification: SensorSetModification, current_sensors: dict[str, SensorConfig]
    ) -> None:
        """
        Validate that the modification won't create global settings conflicts.

        Simulates the final state after all modifications and validates against
        global settings conflicts (device_identifier and variable mismatches).

        Args:
            modification: Modification specification
            current_sensors: Current sensors in the set

        Raises:
            SyntheticSensorsError: If conflicts would be created
        """
        # Get current global settings
        current_metadata = self.metadata
        current_global_settings = {}
        if current_metadata:
            data = self.storage_manager._ensure_loaded()
            if self.sensor_set_id in data["sensor_sets"]:
                current_global_settings = data["sensor_sets"][self.sensor_set_id].get("global_settings", {})

        # Determine final global settings after modification
        final_global_settings = current_global_settings.copy()
        if modification.global_settings is not None:
            final_global_settings.update(modification.global_settings)

        # Apply entity ID changes to global settings variables
        if modification.entity_id_changes and "variables" in final_global_settings:
            updated_variables = {}
            for var_name, var_value in final_global_settings["variables"].items():
                if isinstance(var_value, str) and var_value in modification.entity_id_changes:
                    updated_variables[var_name] = modification.entity_id_changes[var_value]
                else:
                    updated_variables[var_name] = var_value
            final_global_settings["variables"] = updated_variables

        # Build final sensor list after all modifications
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

        # Apply entity ID changes to final sensors
        if modification.entity_id_changes:
            updated_sensors = {}
            for unique_id, sensor in final_sensors.items():
                # Create a copy to avoid modifying the original
                import copy

                updated_sensor = copy.deepcopy(sensor)

                # Update sensor entity_id
                if updated_sensor.entity_id and updated_sensor.entity_id in modification.entity_id_changes:
                    updated_sensor.entity_id = modification.entity_id_changes[updated_sensor.entity_id]

                # Update formula variables
                for formula in updated_sensor.formulas:
                    if formula.variables:
                        for var_name, var_value in formula.variables.items():
                            if isinstance(var_value, str) and var_value in modification.entity_id_changes:
                                formula.variables[var_name] = modification.entity_id_changes[var_value]

                updated_sensors[unique_id] = updated_sensor
            final_sensors = updated_sensors

        # Validate final state for global settings conflicts
        if final_global_settings:
            final_sensor_list = list(final_sensors.values())
            self.storage_manager._validate_no_global_conflicts(final_sensor_list, final_global_settings)

            # Validate attribute variable conflicts
            self.storage_manager._validate_no_attribute_variable_conflicts(final_sensor_list)

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
        from homeassistant.helpers import entity_registry as er

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

        # Invalidate formula caches for the changed entities
        if registry_updates:
            from .entity_change_handler import EntityChangeHandler

            temp_handler = EntityChangeHandler()
            for old_entity_id, new_entity_id in entity_id_changes.items():
                temp_handler.handle_entity_id_change(old_entity_id, new_entity_id)

            _LOGGER.info("Applied %d entity ID changes to HA registry: %s", len(registry_updates), ", ".join(registry_updates))

    async def _add_sensor_direct(self, sensor_config: SensorConfig) -> None:
        """Add sensor directly to storage without entity index updates."""
        await self.storage_manager.async_store_sensor(
            sensor_config=sensor_config,
            sensor_set_id=self.sensor_set_id,
            device_identifier=self.metadata.device_identifier if self.metadata else None,
        )

    async def _update_sensor_direct(self, sensor_config: SensorConfig) -> None:
        """Update sensor directly in storage without entity index updates."""
        data = self.storage_manager._ensure_loaded()

        if sensor_config.unique_id not in data["sensors"]:
            _LOGGER.warning("Sensor %s not found for direct update", sensor_config.unique_id)
            return

        stored_sensor = data["sensors"][sensor_config.unique_id]
        sensor_set_id = stored_sensor.get("sensor_set_id")

        # Update the sensor config data and timestamp (skip entity index updates)
        stored_sensor["config_data"] = self.storage_manager._serialize_sensor_config(sensor_config)
        stored_sensor["updated_at"] = self.storage_manager._get_timestamp()

        # Update sensor set metadata
        if sensor_set_id and sensor_set_id in data["sensor_sets"]:
            data["sensor_sets"][sensor_set_id]["updated_at"] = self.storage_manager._get_timestamp()

        await self.storage_manager.async_save()
        _LOGGER.debug("Direct updated sensor: %s", sensor_config.unique_id)

    async def _remove_sensor_direct(self, unique_id: str) -> None:
        """Remove sensor directly from storage without entity index updates."""
        data = self.storage_manager._ensure_loaded()

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
            data["sensor_sets"][sensor_set_id]["updated_at"] = self.storage_manager._get_timestamp()
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
        data = self.storage_manager._ensure_loaded()

        if self.sensor_set_id in data["sensor_sets"]:
            data["sensor_sets"][self.sensor_set_id]["global_settings"] = global_settings
            data["sensor_sets"][self.sensor_set_id]["updated_at"] = self.storage_manager._get_timestamp()
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

        _LOGGER.info("Imported YAML to sensor set: %s", self.sensor_set_id)

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
            _LOGGER.info("Deleted sensor set: %s", self.sensor_set_id)

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
        import yaml as yaml_lib

        from .config_manager import ConfigManager

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
        return self._entity_index.contains(entity_id)

    def get_entity_index_stats(self) -> dict[str, Any]:
        """
        Get entity index statistics for this sensor set.

        Returns:
            Dictionary with entity index statistics
        """
        return self._entity_index.get_stats()

    def _rebuild_entity_index(self) -> None:
        """Rebuild the entity index from all sensors and global settings in this sensor set."""
        self._entity_index.clear()

        # Add entities from all sensors in this sensor set
        for sensor_config in self.list_sensors():
            self._entity_index.add_sensor_entities(sensor_config)

        # Add entities from global settings
        metadata = self.metadata
        if metadata:
            data = self.storage_manager._ensure_loaded()
            if self.sensor_set_id in data["sensor_sets"]:
                global_settings = data["sensor_sets"][self.sensor_set_id].get("global_settings", {})
                global_variables = global_settings.get("variables", {})
                if global_variables:
                    self._entity_index.add_global_entities(global_variables)

        stats = self._entity_index.get_stats()
        _LOGGER.debug(
            "Rebuilt entity index for sensor set %s: %d total entities",
            self.sensor_set_id,
            stats["total_entities"],
        )

    def _rebuild_entity_index_for_modification(
        self, modification: SensorSetModification, current_sensors: dict[str, SensorConfig]
    ) -> None:
        """
        Rebuild the entity index to reflect the FINAL state after modification.

        This is critical for registry event storm protection - the index must reflect
        the post-modification state BEFORE we start making changes, so that registry
        events triggered by our own changes will be properly filtered out.

        Args:
            modification: The modification being applied
            current_sensors: Current sensors before modification
        """
        self._entity_index.clear()

        # Calculate final sensor list after all modifications
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

        # Apply entity ID changes to final sensors
        if modification.entity_id_changes:
            updated_sensors = {}
            for unique_id, sensor in final_sensors.items():
                # Create a copy to avoid modifying the original
                import copy

                updated_sensor = copy.deepcopy(sensor)

                # Update sensor entity_id
                if updated_sensor.entity_id and updated_sensor.entity_id in modification.entity_id_changes:
                    updated_sensor.entity_id = modification.entity_id_changes[updated_sensor.entity_id]

                # Update formula variables
                for formula in updated_sensor.formulas:
                    if formula.variables:
                        for var_name, var_value in formula.variables.items():
                            if isinstance(var_value, str) and var_value in modification.entity_id_changes:
                                formula.variables[var_name] = modification.entity_id_changes[var_value]

                updated_sensors[unique_id] = updated_sensor
            final_sensors = updated_sensors

        # Add entities from final sensor list to index
        for sensor_config in final_sensors.values():
            self._entity_index.add_sensor_entities(sensor_config)

        # Add entities from final global settings
        metadata = self.metadata
        if metadata:
            data = self.storage_manager._ensure_loaded()
            if self.sensor_set_id in data["sensor_sets"]:
                current_global_settings = data["sensor_sets"][self.sensor_set_id].get("global_settings", {})

                # Apply global settings modifications
                final_global_settings = current_global_settings.copy()
                if modification.global_settings is not None:
                    final_global_settings.update(modification.global_settings)

                # Apply entity ID changes to global settings variables
                if modification.entity_id_changes and "variables" in final_global_settings:
                    updated_variables = {}
                    for var_name, var_value in final_global_settings["variables"].items():
                        if isinstance(var_value, str) and var_value in modification.entity_id_changes:
                            updated_variables[var_name] = modification.entity_id_changes[var_value]
                        else:
                            updated_variables[var_name] = var_value
                    final_global_settings["variables"] = updated_variables

                # Add global variable entities to index
                global_variables = final_global_settings.get("variables", {})
                if global_variables:
                    self._entity_index.add_global_entities(global_variables)

        stats = self._entity_index.get_stats()
        _LOGGER.debug(
            "Pre-built entity index for modification on sensor set %s: %d total entities",
            self.sensor_set_id,
            stats["total_entities"],
        )
