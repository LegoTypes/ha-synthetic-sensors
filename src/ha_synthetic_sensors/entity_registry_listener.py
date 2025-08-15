"""Entity registry listener for tracking entity ID changes that affect synthetic sensors."""
# pylint: disable=duplicate-code  # Entity tracking logic intentionally duplicated in FriendlyNameListener

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .constants_entities import clear_domain_cache
from .entity_change_handler import EntityChangeHandler

if TYPE_CHECKING:
    from .storage_manager import StorageData, StorageManager

_LOGGER = logging.getLogger(__name__)


class EntityRegistryListener:
    """Listens for entity registry changes and updates synthetic sensors accordingly."""

    def __init__(
        self,
        hass: HomeAssistant,
        storage_manager: StorageManager,
        entity_change_handler: EntityChangeHandler,
    ) -> None:
        """Initialize the entity registry listener.

        Args:
            hass: Home Assistant instance
            storage_manager: Storage manager for synthetic sensors
            entity_change_handler: Handler for entity changes
        """
        self.hass = hass
        self.storage_manager = storage_manager
        self.entity_change_handler = entity_change_handler
        self._logger = _LOGGER
        self._known_domains: set[str] = set()
        self._unsub_registry: Callable[[], None] | None = None

    async def async_start(self) -> None:
        """Start listening for entity registry changes."""
        try:
            # Check if already started
            if self._unsub_registry is not None:
                self._logger.warning("Synthetic sensors: Entity registry listener already started")
                return

            # Get initial set of known domains
            await self._update_known_domains()

            # Subscribe to entity registry updates
            self._unsub_registry = self.hass.bus.async_listen("entity_registry_updated", self._handle_entity_registry_updated)

            self._logger.info("Entity registry listener started")

        except Exception as e:
            self._logger.error("Failed to start entity registry listener: %s", e)

    async def async_stop(self) -> None:
        """Stop listening for entity registry changes."""
        if self._unsub_registry:
            self._unsub_registry()
            self._unsub_registry = None
            self._logger.info("Entity registry listener stopped")

    async def _update_known_domains(self) -> None:
        """Update the set of known domains from the entity registry."""
        try:
            registry = er.async_get(self.hass)
            self._known_domains = {entity.domain for entity in registry.entities.values()}
        except Exception as e:
            self._logger.warning("Failed to update known domains: %s", e)

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
    def _handle_entity_registry_updated(self, event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        """
        Handle entity registry update events.

        Args:
            event: Entity registry update event
        """
        try:
            event_data = event.data
            action = event_data.get("action")

            # Handle domain changes for create/remove actions
            if action in ("create", "remove"):
                self._handle_domain_change(dict(event_data))
                return

            # We only care about entity updates (not create/remove)
            if action != "update":
                return

            # Check if entity_id changed - get old and new entity IDs
            old_entity_id = event_data.get("old_entity_id")
            if not old_entity_id or not isinstance(old_entity_id, str):
                return
            new_entity_id = event_data.get("entity_id")
            if not new_entity_id or not isinstance(new_entity_id, str):
                return

            # Check if any SensorSet is tracking this entity ID
            if not self._is_entity_tracked(old_entity_id):
                self._logger.debug("Ignoring entity ID change %s -> %s (not tracked)", old_entity_id, new_entity_id)
                return

            self._logger.info("Processing entity ID change: %s -> %s", old_entity_id, new_entity_id)

            # Schedule the update in the background
            self.hass.async_create_task(self._async_process_entity_id_change(old_entity_id, new_entity_id))

        except Exception as e:
            self._logger.error("Error handling entity registry update: %s", e)

    def _is_entity_tracked(self, entity_id: str) -> bool:  # pylint: disable=duplicate-code
        """Check if any SensorSet is tracking this entity ID.

        Note: This method is intentionally duplicated in FriendlyNameListener
        because both listeners need identical entity tracking behavior, and the
        sensor set approach correctly handles all entity types (global variables,
        sensor variables, and attribute variables) unlike the storage manager approach.
        """
        for sensor_set_id in self.storage_manager.list_sensor_sets():
            sensor_set = self.storage_manager.get_sensor_set(sensor_set_id.sensor_set_id)
            if sensor_set.is_entity_tracked(entity_id):
                return True
        return False

    @callback
    def _handle_domain_change(self, event_data: dict[str, Any]) -> None:
        """
        Handle domain changes when entities are created or removed.

        This method detects when new domains are added to the registry and
        invalidates domain caches to ensure they include the new domains.

        Args:
            event_data: Entity registry event data
        """
        try:
            action = event_data.get("action")
            entity_id = event_data.get("entity_id")

            if not entity_id:
                return

            # Extract domain from entity ID
            domain = entity_id.split(".")[0] if "." in entity_id else None
            if not domain:
                return

            if action == "create" and domain not in self._known_domains:
                self._logger.info("New domain detected: %s", domain)
                self._known_domains.add(domain)
                self._invalidate_domain_caches()
            elif action == "remove":
                # Schedule domain removal check
                self.hass.async_create_task(self._check_domain_removal(domain))

        except Exception as e:
            self._logger.error("Error handling domain change: %s", e)

    def _invalidate_domain_caches(self) -> None:
        """Invalidate all domain caches to ensure they include new domains.

        Uses the centralized cache invalidation system from constants_entities.
        """
        try:
            # Clear centralized domain cache
            clear_domain_cache(self.hass)

            # Clear collection resolver pattern cache if it exists
            if hasattr(self.storage_manager, "collection_resolver"):
                self.storage_manager.collection_resolver.invalidate_domain_cache()

            self._logger.debug("Domain caches invalidated via centralized system")

        except Exception as e:
            self._logger.warning("Failed to invalidate domain caches: %s", e)

    async def _check_domain_removal(self, domain: str) -> None:
        """Check if a domain should be removed from known domains.

        Args:
            domain: Domain to check for removal
        """
        try:
            registry = er.async_get(self.hass)

            # Check if any entities of this domain still exist
            domain_entities = [e for e in registry.entities.values() if e.domain == domain]

            if not domain_entities and domain in self._known_domains:
                self._logger.info("Domain removed: %s", domain)
                self._known_domains.remove(domain)
                # Note: We don't invalidate caches for domain removal as it's less critical

        except Exception as e:
            self._logger.warning("Failed to check domain removal: %s", e)

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
        # Work directly with the actual storage data, not a copy
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
        """Get sensor sets that need to be rebuilt due to entity ID change."""
        sensor_sets_needing_rebuild: list[Any] = []
        for sensor_set_metadata in self.storage_manager.list_sensor_sets():
            sensor_set = self.storage_manager.get_sensor_set(sensor_set_metadata.sensor_set_id)
            if sensor_set.is_entity_tracked(old_entity_id):
                sensor_sets_needing_rebuild.append(sensor_set)
        return sensor_sets_needing_rebuild

    def _update_sensor_configurations(self, data: StorageData, old_entity_id: str, new_entity_id: str) -> list[str]:
        """
        Update sensor configurations with new entity ID.

        Args:
            data: Storage data
            old_entity_id: Old entity ID to replace
            new_entity_id: New entity ID to use

        Returns:
            List of sensor set IDs that were updated
        """
        updated_sensor_sets: list[str] = []

        # Iterate through stored sensors directly (they're at the top level)
        for unique_id, stored_sensor in data["sensors"].items():
            if not isinstance(stored_sensor, dict) or "config_data" not in stored_sensor:
                continue

            sensor_config = stored_sensor["config_data"]
            sensor_set_id = stored_sensor.get("sensor_set_id", "unknown")

            sensors_updated = self._update_sensors_in_set(
                {unique_id: sensor_config}, old_entity_id, new_entity_id, sensor_set_id
            )
            if sensors_updated and sensor_set_id not in updated_sensor_sets:
                updated_sensor_sets.append(sensor_set_id)

        return updated_sensor_sets

    def _update_sensors_in_set(
        self, sensors: dict[Any, Any], old_entity_id: str, new_entity_id: str, sensor_set_id: str
    ) -> bool:
        """Update sensors in a sensor set."""
        sensors_updated = False

        for sensor_key, sensor_config in sensors.items():
            if not isinstance(sensor_config, dict):
                continue

            # Update entity_id field and collect all formula updates
            if self._update_sensor_entity_id(sensor_config, old_entity_id, new_entity_id):
                sensors_updated = True

            if self._update_sensor_formulas(sensor_config, old_entity_id, new_entity_id, sensor_key):
                sensors_updated = True

            if self._update_sensor_attributes(sensor_config, old_entity_id, new_entity_id, sensor_key):
                sensors_updated = True

        return sensors_updated

    def _update_sensor_entity_id(self, sensor_config: dict[Any, Any], old_entity_id: str, new_entity_id: str) -> bool:
        """Update entity_id field if present."""
        if "entity_id" in sensor_config and sensor_config["entity_id"] == old_entity_id:
            sensor_config["entity_id"] = new_entity_id
            return True
        return False

    def _update_sensor_formulas(
        self, sensor_config: dict[Any, Any], old_entity_id: str, new_entity_id: str, sensor_key: Any
    ) -> bool:
        """Update formulas in sensor configuration."""
        formulas_updated = False

        # Update formulas list (current format)
        if "formulas" in sensor_config and isinstance(sensor_config["formulas"], list):
            for formula_config in sensor_config["formulas"]:
                if isinstance(formula_config, dict) and self._update_formula_variables(
                    formula_config, old_entity_id, new_entity_id, sensor_key
                ):
                    formulas_updated = True

        # Update legacy format variables and formula
        for key in ("variables", "formula"):
            if key in sensor_config and self._update_formula_variables(sensor_config, old_entity_id, new_entity_id, sensor_key):
                formulas_updated = True

        return formulas_updated

    def _update_sensor_attributes(
        self, sensor_config: dict[Any, Any], old_entity_id: str, new_entity_id: str, sensor_key: Any
    ) -> bool:
        """Update attributes in sensor configuration."""
        if "attributes" not in sensor_config:
            return False

        attributes_updated = False
        for attr_config in sensor_config["attributes"].values():
            if (
                isinstance(attr_config, dict)
                and "formula" in attr_config
                and self._update_formula_variables(attr_config, old_entity_id, new_entity_id, sensor_key)
            ):
                attributes_updated = True

        return attributes_updated

    def _update_formula_variables(self, sensor_config: Any, old_entity_id: str, new_entity_id: str, unique_id: str) -> bool:
        """
        Update entity ID references in formula variables.

        Args:
            sensor_config: Sensor configuration
            old_entity_id: Old entity ID to replace
            new_entity_id: New entity ID to use
            unique_id: Sensor unique ID for logging

        Returns:
            True if any updates were made
        """
        updated = False

        # Update variables
        if "variables" in sensor_config:
            for var_name, var_value in sensor_config["variables"].items():
                if isinstance(var_value, str) and var_value == old_entity_id:
                    sensor_config["variables"][var_name] = new_entity_id
                    updated = True
                    self._logger.debug(
                        "Updated variable '%s' in sensor '%s': %s -> %s", var_name, unique_id, old_entity_id, new_entity_id
                    )

        # Update formula
        if "formula" in sensor_config:
            formula = sensor_config["formula"]
            if isinstance(formula, str) and old_entity_id in formula:
                sensor_config["formula"] = formula.replace(old_entity_id, new_entity_id)
                updated = True
                self._logger.debug("Updated formula in sensor '%s': %s -> %s", unique_id, old_entity_id, new_entity_id)

        return updated

    def _update_global_settings(self, data: StorageData, old_entity_id: str, new_entity_id: str) -> list[str]:
        """
        Update global settings with new entity ID.

        Args:
            data: Storage data
            old_entity_id: Old entity ID to replace
            new_entity_id: New entity ID to use

        Returns:
            List of sensor set IDs that were updated
        """
        updated_sensor_sets: list[str] = []

        for sensor_set_id, sensor_set_data in data["sensor_sets"].items():
            if "global_settings" not in sensor_set_data:
                continue

            global_settings = sensor_set_data["global_settings"]
            settings_updated = False

            # Update variables in global settings
            if "variables" in global_settings:
                for var_name, var_value in global_settings["variables"].items():
                    if isinstance(var_value, str) and var_value == old_entity_id:
                        global_settings["variables"][var_name] = new_entity_id
                        settings_updated = True
                        self._logger.debug(
                            "Updated global variable '%s' in sensor set '%s': %s -> %s",
                            var_name,
                            sensor_set_id,
                            old_entity_id,
                            new_entity_id,
                        )

            # Update device_identifier if present
            if "device_identifier" in global_settings and global_settings["device_identifier"] == old_entity_id:
                global_settings["device_identifier"] = new_entity_id
                settings_updated = True
                self._logger.debug(
                    "Updated device_identifier in sensor set '%s': %s -> %s", sensor_set_id, old_entity_id, new_entity_id
                )

            if settings_updated:
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
        """
        Save changes and rebuild entity indexes if needed.

        Args:
            updated_sensors: List of sensor set IDs with updated sensors
            updated_sensor_sets: List of sensor set IDs with updated global settings
            sensor_sets_needing_rebuild: List of sensor sets needing entity index rebuild
            old_entity_id: Old entity ID that was changed
            new_entity_id: New entity ID
        """
        try:
            # Save changes if any updates were made
            if updated_sensors or updated_sensor_sets:
                await self.storage_manager.async_save()
                self._logger.info("Saved storage changes for entity ID change: %s -> %s", old_entity_id, new_entity_id)

            # Rebuild entity indexes for affected sensor sets
            for sensor_set in sensor_sets_needing_rebuild:
                try:
                    await sensor_set.async_rebuild_entity_index()
                    self._logger.debug("Rebuilt entity index for sensor set: %s", sensor_set.sensor_set_id)
                except Exception as e:
                    self._logger.warning("Failed to rebuild entity index for sensor set %s: %s", sensor_set.sensor_set_id, e)

        except Exception as e:
            self._logger.error("Failed to save changes for entity ID change %s -> %s: %s", old_entity_id, new_entity_id, e)

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the entity registry listener."""
        return {
            "known_domains_count": len(self._known_domains),
            "known_domains": sorted(self._known_domains),
            "is_listening": self._unsub_registry is not None,
        }
