"""Entity index functionality for SensorSet."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config_models import SensorConfig
    from .entity_index import EntityIndex
    from .storage_manager import StorageManager

_LOGGER = logging.getLogger(__name__)


class SensorSetEntityIndex:
    """Handles entity index operations for a sensor set."""

    def __init__(self, storage_manager: StorageManager, sensor_set_id: str, entity_index: EntityIndex) -> None:
        """Initialize entity index handler.

        Args:
            storage_manager: StorageManager instance
            sensor_set_id: Sensor set identifier
            entity_index: EntityIndex instance to manage
        """
        self.storage_manager = storage_manager
        self.sensor_set_id = sensor_set_id
        self._entity_index = entity_index

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

    def rebuild_entity_index(self, sensors: list[SensorConfig]) -> None:
        """
        Rebuild the entity index from all sensors and global settings in this sensor set.

        Args:
            sensors: List of sensors to index
        """
        self._entity_index.clear()

        # Add entities from all sensors in this sensor set
        for sensor_config in sensors:
            self._entity_index.add_sensor_entities(sensor_config)

        # Add entities from global settings
        data = self.storage_manager.data
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

    def rebuild_entity_index_for_modification(
        self, final_sensors: dict[str, SensorConfig], final_global_settings: dict[str, Any]
    ) -> None:
        """
        Rebuild the entity index to reflect the FINAL state after modification.

        This is critical for registry event storm protection - the index must reflect
        the post-modification state BEFORE we start making changes, so that registry
        events triggered by our own changes will be properly filtered out.

        Args:
            final_sensors: Final sensor list after all modifications
            final_global_settings: Final global settings after modifications
        """
        self._entity_index.clear()

        # Add entities from final sensor list to index
        self.populate_entity_index_from_sensors(final_sensors)

        # Add entities from final global settings
        self.populate_entity_index_from_global_settings(final_global_settings)

        self.log_entity_index_stats("modification")

    def populate_entity_index_from_sensors(self, final_sensors: dict[str, SensorConfig]) -> None:
        """Populate entity index from final sensor list."""
        for sensor_config in final_sensors.values():
            self._entity_index.add_sensor_entities(sensor_config)

    def populate_entity_index_from_global_settings(self, final_global_settings: dict[str, Any]) -> None:
        """Populate entity index from final global settings."""
        # Add global variable entities to index
        global_variables = final_global_settings.get("variables", {})
        if global_variables:
            self._entity_index.add_global_entities(global_variables)

    def log_entity_index_stats(self, operation_type: str) -> None:
        """Log entity index statistics."""
        stats = self._entity_index.get_stats()
        _LOGGER.debug(
            "Pre-built entity index for %s on sensor set %s: %d total entities",
            operation_type,
            self.sensor_set_id,
            stats["total_entities"],
        )
