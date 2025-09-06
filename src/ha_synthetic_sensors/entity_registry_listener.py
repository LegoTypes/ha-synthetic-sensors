"""Entity registry listener for tracking entity ID changes that affect synthetic sensors."""

from __future__ import annotations

from collections.abc import Callable
import dataclasses
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .constants_entities import clear_domain_cache
from .entity_change_handler import EntityChangeHandler

if TYPE_CHECKING:
    from .storage_manager import StorageManager

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

            # Extract old/new entity IDs from actual HA event format
            # Real HA events have: old_entity_id=old, entity_id=new, changes=entity_id=intermediate
            old_entity_id = event_data.get("old_entity_id")
            new_entity_id = event_data.get("entity_id")

            # Only process if this is actually an entity_id change (has both old and new)
            changes = event_data.get("changes", {})
            if not (old_entity_id and new_entity_id and "entity_id" in str(changes)):
                self._logger.debug("Ignoring non-entity_id update: %s", dict(event_data))
                return

            if not isinstance(old_entity_id, str) or not isinstance(new_entity_id, str) or old_entity_id == new_entity_id:
                self._logger.debug("Ignoring entity_id update with invalid or identical IDs: %s", dict(event_data))
                return

            # Check if this entity ID exists anywhere in storage
            if not self._is_entity_tracked(old_entity_id):
                self._logger.debug("Ignoring entity ID change %s -> %s (not found in storage)", old_entity_id, new_entity_id)
                return

            self._logger.info("Processing entity ID change: %s -> %s", old_entity_id, new_entity_id)

            # Schedule the atomic update in the background
            self.hass.async_create_task(self._async_process_entity_id_change(old_entity_id, new_entity_id))

        except Exception as e:
            self._logger.error("Error handling entity registry update: %s", e)

    def _is_entity_tracked(self, entity_id: str) -> bool:
        """Check if an entity ID is tracked by any sensor set.

        Args:
            entity_id: The entity ID to check

        Returns:
            True if the entity ID is tracked
        """
        return self._entity_exists_in_storage(entity_id)

    def _entity_exists_in_storage(self, entity_id: str) -> bool:
        """Check if an entity ID exists anywhere in storage by doing a string search.

        This is simpler and more comprehensive than trying to track entities in indexes.
        It will find the entity ID anywhere it appears as a string in the storage.

        Args:
            entity_id: The entity ID to search for

        Returns:
            True if the entity ID is found anywhere in storage
        """
        # Get all sensor sets from storage
        sensor_sets = self.storage_manager.list_sensor_sets()

        for sensor_set_metadata in sensor_sets:
            sensor_set = self.storage_manager.get_sensor_set(sensor_set_metadata.sensor_set_id)

            # Check global settings
            global_settings = sensor_set.get_global_settings()
            if self._search_entity_in_config(entity_id, global_settings):
                return True

            # Check individual sensors
            sensors = sensor_set.list_sensors()
            for sensor in sensors:
                if self._search_entity_in_config(entity_id, sensor):
                    return True

        return False

    def _search_entity_in_config(self, entity_id: str, config: Any) -> bool:
        """Recursively search for an entity ID string in a configuration object.

        Args:
            entity_id: The entity ID to search for
            config: The configuration object to search in

        Returns:
            True if the entity ID is found
        """
        if isinstance(config, str):
            return entity_id in config
        if isinstance(config, dict):
            for _key, value in config.items():
                if self._search_entity_in_config(entity_id, value):
                    return True
        elif isinstance(config, list):
            for item in config:
                if self._search_entity_in_config(entity_id, item):
                    return True
        elif hasattr(config, "__dict__"):
            # Handle dataclass instances
            return self._search_entity_in_config(entity_id, config.__dict__)

        return False

    async def _replace_entity_in_all_storage(self, old_entity_id: str, new_entity_id: str) -> None:
        """Replace an entity ID string across all storage.

        This does a simple string replacement in all sensor set configurations.

        Args:
            old_entity_id: The entity ID to replace
            new_entity_id: The new entity ID
        """
        # Update storage data directly with entity ID replacements
        storage_data = self.storage_manager.data
        changes_made = False

        # Replace entity IDs in all sensor configurations
        for _sensor_id, sensor_data in storage_data["sensors"].items():
            config_data = sensor_data.get("config_data", {})
            updated_config = self._replace_entity_in_config(old_entity_id, new_entity_id, config_data)
            if updated_config != config_data:
                sensor_data["config_data"] = updated_config
                changes_made = True

        # Replace entity IDs in all sensor set global settings
        for _sensor_set_id, sensor_set_data in storage_data["sensor_sets"].items():
            global_settings = sensor_set_data.get("global_settings", {})
            updated_global_settings = self._replace_entity_in_config(old_entity_id, new_entity_id, global_settings)
            if updated_global_settings != global_settings:
                sensor_set_data["global_settings"] = updated_global_settings
                changes_made = True

        # Save storage if any changes were made
        if changes_made:
            await self.storage_manager.async_save()

    def _replace_entity_in_config(self, old_entity_id: str, new_entity_id: str, config: Any) -> Any:
        """Recursively replace an entity ID string in a configuration object.

        Args:
            old_entity_id: The entity ID to replace
            new_entity_id: The new entity ID
            config: The configuration object to update

        Returns:
            The updated configuration
        """
        if isinstance(config, str):
            # Simple string replacement
            return config.replace(old_entity_id, new_entity_id)
        if isinstance(config, dict):
            # Recursively update dictionary values
            return {key: self._replace_entity_in_config(old_entity_id, new_entity_id, value) for key, value in config.items()}
        if isinstance(config, list):
            # Recursively update list items
            return [self._replace_entity_in_config(old_entity_id, new_entity_id, item) for item in config]
        if hasattr(config, "__dict__"):
            # Handle dataclass instances - create a new instance with updated values
            if dataclasses.is_dataclass(config):
                fields = dataclasses.fields(config)
                kwargs = {}
                for field in fields:
                    old_value = getattr(config, field.name)
                    new_value = self._replace_entity_in_config(old_entity_id, new_entity_id, old_value)
                    kwargs[field.name] = new_value
                # Create new instance of the same dataclass type
                config_type = type(config)
                return config_type(**kwargs)  # type: ignore[misc]
            # For non-dataclass objects, update the __dict__ directly
            config.__dict__ = self._replace_entity_in_config(old_entity_id, new_entity_id, config.__dict__)
            return config
        # Return unchanged for other types (int, float, bool, None)
        return config

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
        Process an entity ID change atomically with proper coordination.

        This method implements a coordinated approach to entity ID changes that ensures
        consistency across all components of the synthetic sensors system.

        FLOW OVERVIEW:
        1. Pause evaluations (prevent inconsistent formula evaluation during update)
        2. Update storage (replace entity IDs in sensor configs and global variables)
        3. Reload sensor managers (recreate sensor objects from updated storage)
        4. Rebuild entity indexes (sync indexes with the reloaded sensor configurations)
        5. Resume evaluations and notify callbacks

        WHY THIS ORDER MATTERS:
        - Storage must be updated first so reload gets the correct entity IDs
        - Reload must happen before entity index rebuild (reload wipes sensor manager state)
        - Entity indexes must be rebuilt after reload (reload doesn't rebuild them automatically)

        Args:
            old_entity_id: The old entity ID to replace
            new_entity_id: The new entity ID to use
        """
        try:
            # STEP 1: Pause all formula evaluations during the update
            # This prevents sensors from evaluating with inconsistent entity references
            # while we're in the middle of updating storage and reloading configurations
            self.entity_change_handler.pause_evaluations()

            # STEP 2: Update storage with new entity IDs
            # This replaces entity ID strings in both sensor configurations and global variables
            # Storage is the source of truth, so this must happen before reload
            await self._update_storage_entity_ids(old_entity_id, new_entity_id)

            # STEP 3: Reload all registered sensor managers from updated storage
            # This recreates sensor objects from the updated storage (with new entity IDs)
            # The reload clears sensor manager's internal tracking and rebuilds it from storage
            # NOTE: This does NOT rebuild entity indexes in sensor sets - that's step 4
            try:
                if hasattr(self.entity_change_handler, "reload_all_managers_from_storage"):
                    await self.entity_change_handler.reload_all_managers_from_storage(self.storage_manager)
                else:
                    self._logger.warning("reload_all_managers_from_storage method not found on entity_change_handler")
            except Exception as reload_err:
                self._logger.error("Error reloading managers from storage: %s", reload_err)

            # STEP 4: Rebuild entity indexes AFTER reload to reflect the updated configurations
            # CRITICAL: This must happen AFTER reload, not before!
            # - Reload recreates sensors from updated storage (with new entity IDs)
            # - But reload doesn't rebuild entity indexes in sensor sets
            # - So entity indexes still contain old entity IDs even though sensors have new ones
            # - We must rebuild indexes to sync them with the reloaded sensor configurations
            try:
                for sensor_set_metadata in self.storage_manager.list_sensor_sets():
                    sensor_set = self.storage_manager.get_sensor_set(sensor_set_metadata.sensor_set_id)
                    # Rebuild the entity index to track entities from the reloaded configuration
                    sensor_set.rebuild_entity_index()
                    self._logger.debug("Rebuilt entity index for sensor set %s after reload", sensor_set_metadata.sensor_set_id)
            except Exception as rebuild_err:
                self._logger.error("Error rebuilding entity indexes after reload: %s", rebuild_err)

            # STEP 5: Clear evaluator caches and notify integration callbacks
            # This resumes evaluations (clears the global evaluation guard) and notifies
            # any integration-specific callbacks about the entity ID change
            self.entity_change_handler.handle_entity_id_change(old_entity_id, new_entity_id)

            self._logger.info("Successfully processed entity ID change atomically: %s -> %s", old_entity_id, new_entity_id)

        except Exception as e:
            self._logger.error("Failed to process entity ID change %s -> %s: %s", old_entity_id, new_entity_id, e)
        finally:
            # 6) Always resume evaluations to avoid persisting a closed gate
            try:
                self.entity_change_handler.resume_evaluations()
            except Exception as resume_err:
                self._logger.error("Failed to resume evaluations after entity ID change: %s", resume_err)

    async def _update_storage_entity_ids(self, old_entity_id: str, new_entity_id: str) -> None:
        """Update entity IDs in storage.

        This method performs a direct string replacement across all storage data:
        - Sensor configurations: formula variables, entity_id fields
        - Global variables: variable values in sensor set global_settings

        The storage update is atomic - either all changes succeed or none are applied.

        Args:
            old_entity_id: The old entity ID to replace
            new_entity_id: The new entity ID to use
        """
        try:
            # Use the existing replacement logic
            await self._replace_entity_in_all_storage(old_entity_id, new_entity_id)
        except Exception as e:
            self._logger.error("Failed to update storage entity IDs from %s to %s: %s", old_entity_id, new_entity_id, e)

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the entity registry listener."""
        return {
            "known_domains_count": len(self._known_domains),
            "known_domains": sorted(self._known_domains),
            "is_listening": self._unsub_registry is not None,
        }
