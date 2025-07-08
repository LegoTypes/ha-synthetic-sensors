"""Entity ID index for tracking synthetic sensor dependencies."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .config_models import SensorConfig
from .name_resolver import NameResolver

_LOGGER = logging.getLogger(__name__)


class EntityIndex:
    """
    Index of entity IDs used by synthetic sensors for efficient change tracking.

    This tracks:
    - Sensor entity_id fields (our own synthetic sensors)
    - Formula variable values that are entity IDs
    - Global variable values that are entity IDs

    This does NOT track:
    - Dynamic aggregation patterns (device_class:, regex:, tag:)
    - Collection functions that resolve at runtime
    - Attribute access patterns (variable.attribute)
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """
        Initialize the EntityIndex.

        Args:
            hass: Home Assistant instance for entity validation
        """
        self._hass = hass
        self._logger = logging.getLogger(__name__)
        self._entity_ids: set[str] = set()

    def _extract_base_entity_id(self, value: str) -> str | None:
        """
        Extract the base entity ID from a value that might include attribute access.

        Examples:
        - sensor.power_meter -> sensor.power_meter
        - sensor.power_meter.state -> sensor.power_meter
        - sensor.power_meter.attributes.voltage -> sensor.power_meter
        - backup_device.battery_level -> None (invalid domain)

        Args:
            value: String value that might be an entity reference

        Returns:
            Base entity ID if valid, None otherwise
        """
        if not isinstance(value, str):
            return None

        parts = value.split(".")
        if len(parts) < 2:
            return None

        # Base entity ID is always domain.entity_name (first two parts)
        base_entity_id = f"{parts[0]}.{parts[1]}"

        # Validate using our _is_entity_id method
        if self._is_entity_id(base_entity_id):
            return base_entity_id

        return None

    def add_sensor_entities(self, sensor_config: SensorConfig) -> None:
        """
        Add all entity IDs from a sensor configuration to the index.

        Args:
            sensor_config: Sensor configuration to extract entity IDs from
        """
        entities_added = set()

        # Add explicit sensor entity_id if present
        if sensor_config.entity_id:
            base_entity_id = self._extract_base_entity_id(sensor_config.entity_id)
            if base_entity_id:
                self._entity_ids.add(base_entity_id)
                entities_added.add(base_entity_id)

        # Add entity IDs from formula variables using base entity extraction
        for formula in sensor_config.formulas:
            if formula.variables:
                for _var_name, var_value in formula.variables.items():
                    # Extract base entity ID from potentially complex references
                    if isinstance(var_value, str):
                        base_entity_id = self._extract_base_entity_id(var_value)
                        if base_entity_id:
                            self._entity_ids.add(base_entity_id)
                            entities_added.add(base_entity_id)

        if entities_added:
            self._logger.debug(
                "Added %d entity IDs from sensor %s: %s", len(entities_added), sensor_config.unique_id, sorted(entities_added)
            )

    def remove_sensor_entities(self, sensor_config: SensorConfig) -> None:
        """
        Remove all entity IDs from a sensor configuration from the index.

        Args:
            sensor_config: Sensor configuration to remove entity IDs from
        """
        entities_to_remove = set()

        # Remove explicit sensor entity_id if present
        if sensor_config.entity_id:
            base_entity_id = self._extract_base_entity_id(sensor_config.entity_id)
            if base_entity_id:
                entities_to_remove.add(base_entity_id)

        # Remove entity IDs from formula variables using base entity extraction
        for formula in sensor_config.formulas:
            if formula.variables:
                for _var_name, var_value in formula.variables.items():
                    # Extract base entity ID from potentially complex references
                    if isinstance(var_value, str):
                        base_entity_id = self._extract_base_entity_id(var_value)
                        if base_entity_id:
                            entities_to_remove.add(base_entity_id)

        # Remove from index
        for entity_id in entities_to_remove:
            self._entity_ids.discard(entity_id)

        if entities_to_remove:
            self._logger.debug(
                "Removed %d entity IDs from sensor %s: %s",
                len(entities_to_remove),
                sensor_config.unique_id,
                sorted(entities_to_remove),
            )

    def add_global_entities(self, global_variables: dict[str, Any]) -> None:
        """
        Add entity IDs from global variables to the index.

        Args:
            global_variables: Global variables dictionary
        """
        entities_added = set()

        for _var_name, var_value in global_variables.items():
            # Extract base entity ID from potentially complex references
            if isinstance(var_value, str):
                base_entity_id = self._extract_base_entity_id(var_value)
                if base_entity_id:
                    self._entity_ids.add(base_entity_id)
                    entities_added.add(base_entity_id)

        if entities_added:
            self._logger.debug("Added %d entity IDs from global variables: %s", len(entities_added), sorted(entities_added))

    def remove_global_entities(self, global_variables: dict[str, Any]) -> None:
        """
        Remove entity IDs from global variables from the index.

        Args:
            global_variables: Global variables dictionary
        """
        entities_to_remove = set()

        for _var_name, var_value in global_variables.items():
            # Extract base entity ID from potentially complex references
            if isinstance(var_value, str):
                base_entity_id = self._extract_base_entity_id(var_value)
                if base_entity_id:
                    entities_to_remove.add(base_entity_id)

        # Remove from index
        for entity_id in entities_to_remove:
            self._entity_ids.discard(entity_id)

        if entities_to_remove:
            self._logger.debug(
                "Removed %d entity IDs from global variables: %s", len(entities_to_remove), sorted(entities_to_remove)
            )

    def contains(self, entity_id: str) -> bool:
        """
        Check if an entity ID is tracked in the index.

        Args:
            entity_id: Entity ID to check

        Returns:
            True if entity ID is tracked, False otherwise
        """
        return entity_id in self._entity_ids

    def get_all_entities(self) -> set[str]:
        """
        Get all tracked entity IDs.

        Returns:
            Set of all tracked entity IDs
        """
        return self._entity_ids.copy()

    def clear(self) -> None:
        """Clear all tracked entity IDs."""
        count = len(self._entity_ids)
        self._entity_ids.clear()
        self._logger.debug("Cleared %d entity IDs from index", count)

    def get_stats(self) -> dict[str, Any]:
        """
        Get index statistics.

        Returns:
            Dictionary with index statistics
        """
        return {
            "total_entities": len(self._entity_ids),
            "tracked_entities": len(self._entity_ids),  # More descriptive name
        }

    def _is_entity_id(self, value: str) -> bool:
        """
        Check if a string value represents a valid Home Assistant entity ID.

        Uses NameResolver validation for consistency.

        Args:
            value: String value to check

        Returns:
            True if value represents a valid entity ID
        """
        if not isinstance(value, str):
            return False

        # Use NameResolver for validation
        temp_resolver = NameResolver(self._hass, {})
        return temp_resolver.is_valid_entity_id(value)
