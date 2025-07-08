"""Entity registry listener for tracking entity ID changes that affect synthetic sensors."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED

if TYPE_CHECKING:
    from .entity_change_handler import EntityChangeHandler
    from .storage_manager import StorageData, StorageManager

_LOGGER = logging.getLogger(__name__)


class EntityRegistryListener:
    """
    Listens for entity registry changes and updates synthetic sensor storage.

    Only processes changes for entity IDs that are tracked in our entity index,
    avoiding expensive operations for unrelated entity changes.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        storage_manager: StorageManager,
        entity_change_handler: EntityChangeHandler,
    ) -> None:
        """
        Initialize the entity registry listener.

        Args:
            hass: Home Assistant instance
            storage_manager: Storage manager with entity index
            entity_change_handler: Handler for coordinating entity ID changes
        """
        self.hass = hass
        self.storage_manager = storage_manager
        self.entity_change_handler = entity_change_handler
        self._logger = _LOGGER.getChild(self.__class__.__name__)
        self._unsub_registry: Callable[[], None] | None = None

    async def async_start(self) -> None:
        """Start listening for entity registry changes."""
        if self._unsub_registry is not None:
            self._logger.warning("Entity registry listener already started")
            return

        self._unsub_registry = self.hass.bus.async_listen(EVENT_ENTITY_REGISTRY_UPDATED, self._handle_entity_registry_updated)

        self._logger.debug("Started entity registry listener")

    async def async_stop(self) -> None:
        """Stop listening for entity registry changes."""
        if self._unsub_registry is not None:
            self._unsub_registry()
            self._unsub_registry = None

        self._logger.debug("Stopped entity registry listener")

    def add_entity_change_callback(self, change_callback: Callable[[str, str], None]) -> None:
        """
        Add a callback to be notified of entity ID changes.

        Args:
            change_callback: Function that takes (old_entity_id, new_entity_id) parameters
        """
        self.entity_change_handler.register_integration_callback(change_callback)

    def remove_entity_change_callback(self, change_callback: Callable[[str, str], None]) -> None:
        """
        Remove an entity change callback.

        Args:
            change_callback: Function to remove from callbacks
        """
        self.entity_change_handler.unregister_integration_callback(change_callback)

    @callback
    def _handle_entity_registry_updated(self, event: Event) -> None:
        """
        Handle entity registry update events.

        Args:
            event: Entity registry update event
        """
        try:
            event_data = event.data
            action = event_data.get("action")

            # We only care about entity updates (not create/remove)
            if action != "update":
                return

            changes = event_data.get("changes", {})

            # Check if entity_id changed
            if "entity_id" not in changes:
                return

            old_entity_id = changes["entity_id"]["old"]
            new_entity_id = changes["entity_id"]["new"]

            # Check if any SensorSet is tracking this entity ID
            is_tracked = False
            for sensor_set_id in self.storage_manager.list_sensor_sets():
                sensor_set = self.storage_manager.get_sensor_set(sensor_set_id.sensor_set_id)
                if sensor_set.is_entity_tracked(old_entity_id):
                    is_tracked = True
                    break

            if not is_tracked:
                self._logger.debug("Ignoring entity ID change %s -> %s (not tracked)", old_entity_id, new_entity_id)
                return

            self._logger.info("Processing entity ID change: %s -> %s", old_entity_id, new_entity_id)

            # Schedule the update in the background
            self.hass.async_create_task(self._async_process_entity_id_change(old_entity_id, new_entity_id))

        except Exception as e:
            self._logger.error("Error handling entity registry update: %s", e)

    async def _async_process_entity_id_change(self, old_entity_id: str, new_entity_id: str) -> None:
        """
        Process an entity ID change by updating storage and notifying callbacks.

        Args:
            old_entity_id: Old entity ID
            new_entity_id: New entity ID
        """
        try:
            # Update storage with new entity ID
            await self._update_storage_entity_ids(old_entity_id, new_entity_id)

            # Notify entity change handler to coordinate all other updates
            self.entity_change_handler.handle_entity_id_change(old_entity_id, new_entity_id)

            self._logger.info("Successfully processed entity ID change: %s -> %s", old_entity_id, new_entity_id)

        except Exception as e:
            self._logger.error("Failed to process entity ID change %s -> %s: %s", old_entity_id, new_entity_id, e)

    async def _update_storage_entity_ids(self, old_entity_id: str, new_entity_id: str) -> None:
        """
        Update all storage references from old entity ID to new entity ID.

        Args:
            old_entity_id: Old entity ID to replace
            new_entity_id: New entity ID to use
        """
        data = self.storage_manager.data

        # Track which sensor sets need entity index rebuilding BEFORE we update storage
        sensor_sets_needing_rebuild = self._get_sensor_sets_needing_rebuild(old_entity_id)

        # Update sensor configurations
        updated_sensors = self._update_sensor_configurations(data, old_entity_id, new_entity_id)

        # Update global settings in sensor sets
        updated_sensor_sets = self._update_global_settings(data, old_entity_id, new_entity_id)

        # Save changes if any updates were made
        await self._save_and_rebuild_if_needed(
            updated_sensors, updated_sensor_sets, sensor_sets_needing_rebuild, old_entity_id, new_entity_id
        )

    def _get_sensor_sets_needing_rebuild(self, old_entity_id: str) -> list[Any]:
        """Get sensor sets that need entity index rebuilding."""
        sensor_sets_needing_rebuild = []
        for sensor_set_metadata in self.storage_manager.list_sensor_sets():
            sensor_set = self.storage_manager.get_sensor_set(sensor_set_metadata.sensor_set_id)
            if sensor_set.is_entity_tracked(old_entity_id):
                sensor_sets_needing_rebuild.append(sensor_set)
        return sensor_sets_needing_rebuild

    def _update_sensor_configurations(self, data: StorageData, old_entity_id: str, new_entity_id: str) -> list[str]:
        """Update sensor configurations with new entity ID."""
        updated_sensors = []

        for unique_id, stored_sensor in data["sensors"].items():
            config_data = stored_sensor.get("config_data")
            if not config_data:
                continue

            sensor_config = self.storage_manager.deserialize_sensor_config(config_data)
            updated = False

            # Update sensor entity_id
            if sensor_config.entity_id == old_entity_id:
                sensor_config.entity_id = new_entity_id
                updated = True
                self._logger.debug("Updated sensor %s entity_id: %s -> %s", unique_id, old_entity_id, new_entity_id)

            # Update formula variables
            updated = self._update_formula_variables(sensor_config, old_entity_id, new_entity_id, unique_id) or updated

            if updated:
                # Update the stored sensor with new config
                stored_sensor["config_data"] = self.storage_manager.serialize_sensor_config(sensor_config)
                stored_sensor["updated_at"] = self.storage_manager.get_current_timestamp()
                updated_sensors.append(unique_id)

        return updated_sensors

    def _update_formula_variables(self, sensor_config: Any, old_entity_id: str, new_entity_id: str, unique_id: str) -> bool:
        """Update formula variables in a sensor configuration."""
        updated = False
        for formula in sensor_config.formulas:
            if formula.variables:
                for var_name, var_value in formula.variables.items():
                    if var_value == old_entity_id:
                        formula.variables[var_name] = new_entity_id
                        updated = True
                        self._logger.debug(
                            "Updated sensor %s formula %s variable %s: %s -> %s",
                            unique_id,
                            formula.id,
                            var_name,
                            old_entity_id,
                            new_entity_id,
                        )
        return updated

    def _update_global_settings(self, data: StorageData, old_entity_id: str, new_entity_id: str) -> list[str]:
        """Update global settings in sensor sets."""
        updated_sensor_sets = []

        for sensor_set_id, sensor_set_data in data["sensor_sets"].items():
            global_settings = sensor_set_data.get("global_settings", {})
            global_variables = global_settings.get("variables", {})

            if global_variables:
                updated = False
                for var_name, var_value in global_variables.items():
                    if var_value == old_entity_id:
                        global_variables[var_name] = new_entity_id
                        updated = True
                        self._logger.debug(
                            "Updated sensor set %s global variable %s: %s -> %s",
                            sensor_set_id,
                            var_name,
                            old_entity_id,
                            new_entity_id,
                        )

                if updated:
                    sensor_set_data["updated_at"] = self.storage_manager.get_current_timestamp()
                    updated_sensor_sets.append(sensor_set_id)

        return updated_sensor_sets

    async def _save_and_rebuild_if_needed(
        self,
        updated_sensors: list[str],
        updated_sensor_sets: list[str],
        sensor_sets_needing_rebuild: list[Any],
        old_entity_id: str,
        new_entity_id: str,
    ) -> None:
        """Save changes and rebuild entity indexes if needed."""
        if updated_sensors or updated_sensor_sets:
            await self.storage_manager.async_save()

            # Rebuild entity indexes for affected sensor sets (using pre-update tracking list)
            for sensor_set in sensor_sets_needing_rebuild:
                self._logger.debug(
                    "Rebuilding entity index for sensor set %s due to entity ID change", sensor_set.sensor_set_id
                )
                sensor_set.rebuild_entity_index()
                self._logger.debug("Rebuilt entity index for sensor set %s", sensor_set.sensor_set_id)

            self._logger.info(
                "Updated entity ID %s -> %s in %d sensors, %d sensor sets, rebuilt %d entity indexes",
                old_entity_id,
                new_entity_id,
                len(updated_sensors),
                len(updated_sensor_sets),
                len(sensor_sets_needing_rebuild),
            )
        else:
            self._logger.debug("No storage updates needed for entity ID change %s -> %s", old_entity_id, new_entity_id)

    def get_stats(self) -> dict[str, Any]:
        """
        Get listener statistics.

        Returns:
            Dictionary with listener statistics
        """
        total_tracked_entities = 0
        for sensor_set_metadata in self.storage_manager.list_sensor_sets():
            sensor_set = self.storage_manager.get_sensor_set(sensor_set_metadata.sensor_set_id)
            stats = sensor_set.get_entity_index_stats()
            total_tracked_entities += stats["total_entities"]

        return {
            "active": self._unsub_registry is not None,
            "tracked_entities": total_tracked_entities,
            "entity_change_handler": self.entity_change_handler.get_stats(),
        }
