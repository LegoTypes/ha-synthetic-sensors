"""
Friendly name listener for tracking entity friendly name changes that affect synthetic sensors.

Simple implementation that:
1. Detects friendly name changes in Home Assistant
2. Updates storage with new friendly names
3. Updates sensor entities to reflect the changes
"""
# pylint: disable=duplicate-code  # Entity tracking logic intentionally duplicated in EntityRegistryListener

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback

from .entity_change_handler import EntityChangeHandler

if TYPE_CHECKING:
    from .storage_manager import StorageData, StorageManager

_LOGGER = logging.getLogger(__name__)


class FriendlyNameListener:
    """Listens for entity friendly name changes and updates synthetic sensors accordingly."""

    def __init__(
        self,
        hass: HomeAssistant,
        storage_manager: StorageManager,
        entity_change_handler: EntityChangeHandler,
    ) -> None:
        """Initialize the friendly name listener.

        Args:
            hass: Home Assistant instance
            storage_manager: Storage manager for synthetic sensors
            entity_change_handler: Handler for entity changes
        """
        self.hass = hass
        self.storage_manager = storage_manager
        self.entity_change_handler = entity_change_handler
        self._logger = _LOGGER
        self._unsub_state_changed: Callable[[], None] | None = None
        self._entity_friendly_names: dict[str, str] = {}

    async def async_start(self) -> None:
        """Start listening for entity state changes to detect friendly name updates."""
        try:
            # Check if already started
            if self._unsub_state_changed is not None:
                self._logger.warning("Friendly name listener already started")
                return

            # Subscribe to state change events
            self._unsub_state_changed = self.hass.bus.async_listen("state_changed", self._handle_state_changed)

            # Initialize current friendly names cache
            await self._initialize_friendly_names_cache()

            self._logger.debug("Started friendly name listener")

        except Exception as e:
            self._logger.error("Failed to start friendly name listener: %s", e)

    async def async_stop(self) -> None:
        """Stop listening for entity state changes."""
        if self._unsub_state_changed:
            self._unsub_state_changed()
            self._unsub_state_changed = None
            self._logger.debug("Stopped friendly name listener")

    async def _initialize_friendly_names_cache(self) -> None:
        """Initialize the cache of current friendly names for tracked entities."""
        try:
            # Get all currently tracked entities by checking all states
            # Note: This is less efficient but handles initialization properly
            entity_ids = self.hass.states.async_entity_ids()
            if hasattr(entity_ids, "__iter__"):
                for entity_id in entity_ids:
                    if self._is_entity_tracked(entity_id):
                        state = self.hass.states.get(entity_id)
                        if state and "friendly_name" in state.attributes:
                            self._entity_friendly_names[entity_id] = state.attributes["friendly_name"]

        except Exception as e:
            self._logger.warning("Failed to initialize friendly names cache: %s", e)

    @callback
    def _handle_state_changed(self, event: Event[EventStateChangedData]) -> None:
        """
        Handle state change events to detect friendly name updates.

        Args:
            event: State change event
        """
        try:
            # Access the event data as specified in EventStateChangedData
            entity_id = event.data.get("entity_id")
            old_state = event.data.get("old_state")
            new_state = event.data.get("new_state")

            if not entity_id or not self._is_entity_tracked(entity_id):
                return

            # Extract friendly names
            old_friendly_name = self._extract_friendly_name(old_state)
            new_friendly_name = self._extract_friendly_name(new_state)

            # Check if friendly name actually changed
            if old_friendly_name == new_friendly_name:
                return

            self._logger.debug(
                "Detected friendly name change for %s: '%s' -> '%s'", entity_id, old_friendly_name, new_friendly_name
            )

            # Update our cache
            if new_friendly_name:
                self._entity_friendly_names[entity_id] = new_friendly_name
            elif entity_id in self._entity_friendly_names:
                del self._entity_friendly_names[entity_id]

            # Schedule the update in the background
            self.hass.async_create_task(
                self._async_process_friendly_name_change(entity_id, old_friendly_name, new_friendly_name)
            )

        except Exception as e:
            self._logger.error("Error handling state change for friendly name detection: %s", e)

    def _extract_friendly_name(self, state: State | None) -> str | None:
        """Extract friendly name from a state object."""
        if state and hasattr(state, "attributes"):
            friendly_name = state.attributes.get("friendly_name")
            return friendly_name if isinstance(friendly_name, str) else None
        return None

    def _is_entity_tracked(self, entity_id: str) -> bool:  # pylint: disable=duplicate-code
        """Check if the entity is tracked by any sensor set.

        Note: This method is intentionally duplicated in EntityRegistryListener
        because both listeners need identical entity tracking behavior, and the
        sensor set approach correctly handles all entity types (global variables,
        sensor variables, and attribute variables) unlike the storage manager approach.
        """
        for sensor_set_id in self.storage_manager.list_sensor_sets():
            sensor_set = self.storage_manager.get_sensor_set(sensor_set_id.sensor_set_id)
            if sensor_set.is_entity_tracked(entity_id):
                return True
        return False

    async def _async_process_friendly_name_change(  # pylint: disable=duplicate-code
        self, entity_id: str, old_friendly_name: str | None, new_friendly_name: str | None
    ) -> None:
        """
        Process a friendly name change by updating storage and sensors.

        Args:
            entity_id: Entity ID that had its friendly name changed
            old_friendly_name: Previous friendly name
            new_friendly_name: New friendly name
        """
        try:
            # Update storage with new friendly name
            await self._update_storage_friendly_names(entity_id, old_friendly_name, new_friendly_name)

            # Update sensor entities
            await self._update_sensor_entities(entity_id, old_friendly_name, new_friendly_name)

            self._logger.info(
                "Successfully processed friendly name change for %s: '%s' -> '%s'",
                entity_id,
                old_friendly_name,
                new_friendly_name,
            )

        except Exception as e:
            self._logger.error(
                "Failed to process friendly name change for %s: '%s' -> '%s': %s",
                entity_id,
                old_friendly_name,
                new_friendly_name,
                e,
            )

    async def _update_storage_friendly_names(
        self, entity_id: str, old_friendly_name: str | None, new_friendly_name: str | None
    ) -> None:
        """
        Update sensor definitions to reflect friendly name changes in referenced entities.

        Args:
            entity_id: Entity ID that had its friendly name changed
            old_friendly_name: Previous friendly name
            new_friendly_name: New friendly name
        """
        # Work directly with the actual storage data
        data = self.storage_manager.data

        # Update sensor definitions with new friendly names
        updated_sensors = self._update_sensor_definitions(data, entity_id, old_friendly_name, new_friendly_name)

        # Update global settings if needed
        updated_sensor_sets = self._update_global_settings_definitions(data, entity_id, old_friendly_name, new_friendly_name)

        # Save changes if any updates were made
        if updated_sensors or updated_sensor_sets:
            await self.storage_manager.async_save()
            self._logger.info("Updated %d sensor definitions for friendly name change: %s", len(updated_sensors), entity_id)

    def _update_sensor_definitions(
        self, data: StorageData, entity_id: str, old_friendly_name: str | None, new_friendly_name: str | None
    ) -> set[str]:
        """
        Update sensor definitions to use current friendly names in sensor names and metadata.

        Args:
            data: Storage data
            entity_id: Entity ID that had its friendly name changed
            old_friendly_name: Previous friendly name
            new_friendly_name: New friendly name

        Returns:
            Set of sensor unique IDs that were updated
        """
        updated_sensor_ids: set[str] = set()

        # Only proceed if we have both old and new names
        if not old_friendly_name or not new_friendly_name:
            return updated_sensor_ids

        # Iterate through stored sensors
        for unique_id, stored_sensor in data["sensors"].items():
            if not isinstance(stored_sensor, dict) or "config_data" not in stored_sensor:
                continue

            sensor_config = stored_sensor["config_data"]

            # Check if this sensor references the entity
            if not self._sensor_references_entity(sensor_config, entity_id):
                continue

            sensor_updated = False

            # Update sensor name if it contains the old friendly name
            if (
                "name" in sensor_config
                and isinstance(sensor_config["name"], str)
                and old_friendly_name in sensor_config["name"]
            ):
                original_name = sensor_config["name"]
                updated_name = original_name.replace(old_friendly_name, new_friendly_name)
                sensor_config["name"] = updated_name
                sensor_updated = True
                self._logger.debug("Updated sensor name: %s -> %s", original_name, updated_name)

            # Update friendly_name in metadata if present
            if "metadata" in sensor_config and isinstance(sensor_config["metadata"], dict):
                metadata = sensor_config["metadata"]
                if "friendly_name" in metadata and isinstance(metadata["friendly_name"], str):
                    current_friendly_name = metadata["friendly_name"]
                    if old_friendly_name in current_friendly_name:
                        updated_friendly_name = current_friendly_name.replace(old_friendly_name, new_friendly_name)
                        metadata["friendly_name"] = updated_friendly_name
                        sensor_updated = True
                        self._logger.debug(
                            "Updated sensor friendly_name metadata: %s -> %s", current_friendly_name, updated_friendly_name
                        )

            if sensor_updated:
                updated_sensor_ids.add(unique_id)

        return updated_sensor_ids

    def _update_global_settings_definitions(
        self, data: StorageData, entity_id: str, old_friendly_name: str | None, new_friendly_name: str | None
    ) -> list[str]:
        """
        Update global settings definitions to use current friendly names.

        Args:
            data: Storage data
            entity_id: Entity ID that had its friendly name changed
            old_friendly_name: Previous friendly name
            new_friendly_name: New friendly name

        Returns:
            List of sensor set IDs that were updated
        """
        updated_sensor_sets: list[str] = []

        # Only proceed if we have both old and new names
        if not old_friendly_name or not new_friendly_name:
            return updated_sensor_sets

        # Check each sensor set's global settings
        for sensor_set_id, sensor_set_data in data["sensor_sets"].items():
            if not isinstance(sensor_set_data, dict) or "global_settings" not in sensor_set_data:
                continue

            global_settings = sensor_set_data["global_settings"]
            if not isinstance(global_settings, dict):
                continue

            settings_updated = False

            # Update name in global settings if it contains the old friendly name
            if "name" in global_settings and isinstance(global_settings["name"], str):
                current_name = global_settings["name"]
                if old_friendly_name in current_name:
                    updated_name = current_name.replace(old_friendly_name, new_friendly_name)
                    global_settings["name"] = updated_name
                    settings_updated = True
                    self._logger.debug(
                        "Updated global settings name in sensor set '%s': %s -> %s", sensor_set_id, current_name, updated_name
                    )

            if settings_updated:
                updated_sensor_sets.append(sensor_set_id)

        return updated_sensor_sets

    async def _update_sensor_entities(
        self, entity_id: str, old_friendly_name: str | None, new_friendly_name: str | None
    ) -> None:
        """
        Update sensor entities to reflect the friendly name changes.

        This triggers sensor managers to update their entities with new names.

        Args:
            entity_id: Entity ID that had its friendly name changed
            old_friendly_name: Previous friendly name
            new_friendly_name: New friendly name
        """
        try:
            # Use the entity change handler to coordinate updates
            # This will invalidate caches and notify sensor managers
            self.entity_change_handler.handle_entity_id_change(entity_id, entity_id)

            self._logger.debug("Triggered sensor entity updates for friendly name change: %s", entity_id)

        except Exception as e:
            self._logger.error("Error updating sensor entities for friendly name change: %s", e)

    def _sensor_references_entity(self, sensor_config: dict[str, Any], entity_id: str) -> bool:
        """Check if a sensor configuration references the given entity ID."""
        # Check direct entity_id reference
        if sensor_config.get("entity_id") == entity_id:
            return True

        # Check variables section
        variables = sensor_config.get("variables", {})
        if isinstance(variables, dict):
            for _var_name, var_value in variables.items():
                if isinstance(var_value, str) and var_value == entity_id:
                    return True

        # Check attributes section
        attributes = sensor_config.get("attributes", {})
        if not isinstance(attributes, dict):
            return False

        for _attr_name, attr_config in attributes.items():
            if not isinstance(attr_config, dict):
                continue
            attr_variables = attr_config.get("variables", {})
            if not isinstance(attr_variables, dict):
                continue
            for _var_name, var_value in attr_variables.items():
                if isinstance(var_value, str) and var_value == entity_id:
                    return True

        return False

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the friendly name listener."""
        return {
            "is_listening": self._unsub_state_changed is not None,
            "cached_friendly_names_count": len(self._entity_friendly_names),
            "tracked_entities": list(self._entity_friendly_names.keys()),
        }
