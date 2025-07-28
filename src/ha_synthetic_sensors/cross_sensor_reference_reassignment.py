"""Cross-sensor reference reassignment manager.

Handles order-independent resolution of cross-sensor references for both bulk YAML
processing and CRUD operations. When sensors reference each other by YAML keys,
this module coordinates the reassignment to actual Home Assistant entity IDs
regardless of definition order.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import TYPE_CHECKING

from .config_models import Config, SensorConfig
from .cross_sensor_reference_detector import CrossSensorReferenceDetector
from .formula_reference_resolver import FormulaReferenceResolver

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class CrossSensorReferenceReassignment:
    """Manages cross-sensor reference reassignment for bulk and CRUD operations.

    This class handles the coordination of cross-sensor references when:
    1. Bulk YAML contains forward/backward references (sensors defined in any order)
    2. CRUD operations modify existing sensors to reference different sensors
    3. CRUD operations create new sensors that reference existing or new sensors

    The key insight is that HA handles entity ID assignment and collision avoidance,
    so this module focuses on the reassignment coordination once entity IDs are known.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the reassignment manager."""
        self._hass = hass
        self._logger = _LOGGER.getChild(self.__class__.__name__)
        self._detector = CrossSensorReferenceDetector()
        self._resolver = FormulaReferenceResolver()

    def detect_reassignment_needs(self, config: Config) -> dict[str, set[str]]:
        """Detect which sensors need cross-sensor reference reassignment.

        Args:
            config: Configuration containing sensors to analyze

        Returns:
            Dictionary mapping sensor keys to sets of referenced sensor keys
        """
        return self._detector.scan_config_references(config)

    def create_reassignment_plan(
        self, config: Config, existing_entity_mappings: dict[str, str] | None = None
    ) -> dict[str, set[str]]:
        """Create a plan for reassigning cross-sensor references.

        Args:
            config: Configuration to analyze
            existing_entity_mappings: Known sensor_key -> entity_id mappings

        Returns:
            Dictionary of sensor keys that need their references reassigned
        """
        cross_references = self.detect_reassignment_needs(config)

        if not cross_references:
            self._logger.debug("No cross-sensor references detected - no reassignment needed")
            return {}

        self._logger.info("Detected cross-sensor references requiring reassignment: %s", dict(cross_references))

        # Filter out references that are already resolved
        if existing_entity_mappings:
            unresolved_references = {}
            for sensor_key, refs in cross_references.items():
                unresolved_refs = refs - set(existing_entity_mappings.keys())
                if unresolved_refs:
                    unresolved_references[sensor_key] = unresolved_refs

            if unresolved_references:
                self._logger.debug("Found unresolved references requiring reassignment: %s", dict(unresolved_references))

            return unresolved_references

        return cross_references

    async def execute_reassignment(self, config: Config, entity_mappings: dict[str, str]) -> Config:
        """Execute cross-sensor reference reassignment.

        Args:
            config: Original configuration with sensor key references
            entity_mappings: Complete mapping of sensor_key -> entity_id

        Returns:
            Updated configuration with resolved entity ID references
        """
        if not entity_mappings:
            self._logger.debug("No entity mappings provided - returning original config")
            return config

        self._logger.info("Executing cross-sensor reference reassignment with %d entity mappings", len(entity_mappings))

        # Create enhanced entity mappings that include original entity ID -> final entity ID mappings
        # This is critical for handling cross-sensor references to collision-handled entities
        enhanced_entity_mappings = self._create_enhanced_entity_mappings(config, entity_mappings)

        # Use existing formula resolver for the actual reassignment
        resolved_config = self._resolver.resolve_all_references_in_config(config, enhanced_entity_mappings)

        self._logger.info("Cross-sensor reference reassignment complete")
        return resolved_config

    def _create_enhanced_entity_mappings(self, config: Config, entity_mappings: dict[str, str]) -> dict[str, str]:
        """Create enhanced entity mappings that include both sensor keys and entity ID mappings.

        This method creates additional mappings for original entity IDs to their final entity IDs,
        which is essential for cross-sensor reference resolution when entity IDs have been
        collision-handled.

        Args:
            config: Original configuration (before entity registration)
            entity_mappings: Sensor key -> final entity ID mappings from entity registry

        Returns:
            Enhanced mappings that include both sensor key and entity ID mappings
        """
        enhanced_mappings = entity_mappings.copy()

        # For each sensor, create comprehensive mappings for cross-sensor references
        for sensor_config in config.sensors:
            sensor_key = sensor_config.unique_id
            original_entity_id = sensor_config.entity_id
            final_entity_id = entity_mappings.get(sensor_key)

            if final_entity_id:
                # Map sensor unique_id to final entity_id (for cross-sensor variables like "sensor.base_sensor_cache")
                if sensor_key.startswith("sensor."):
                    # If unique_id looks like an entity_id, map it directly
                    enhanced_mappings[sensor_key] = final_entity_id
                else:
                    # Map constructed entity_id from unique_id
                    constructed_entity_id = f"sensor.{sensor_key}"
                    enhanced_mappings[constructed_entity_id] = final_entity_id

                # If sensor had an original entity_id and it differs from the final entity_id,
                # add mapping for cross-sensor references to find the updated entity_id
                if original_entity_id and original_entity_id != final_entity_id:
                    enhanced_mappings[original_entity_id] = final_entity_id

        self._logger.debug("Enhanced entity mappings: %s", enhanced_mappings)
        return enhanced_mappings

    def validate_reassignment_integrity(
        self, original_config: Config, resolved_config: Config, entity_mappings: dict[str, str]
    ) -> bool:
        """Validate that reassignment maintained referential integrity.

        Args:
            original_config: Configuration before reassignment
            resolved_config: Configuration after reassignment
            entity_mappings: Mappings used for reassignment

        Returns:
            True if integrity is maintained, False otherwise
        """
        try:
            # Verify sensor count unchanged
            if len(original_config.sensors) != len(resolved_config.sensors):
                self._logger.error(
                    "Sensor count mismatch after reassignment: %d -> %d",
                    len(original_config.sensors),
                    len(resolved_config.sensors),
                )
                return False

            # Verify all sensors still present
            original_keys = {s.unique_id for s in original_config.sensors}
            resolved_keys = {s.unique_id for s in resolved_config.sensors}

            if original_keys != resolved_keys:
                missing = original_keys - resolved_keys
                extra = resolved_keys - original_keys
                self._logger.error("Sensor key mismatch after reassignment. Missing: %s, Extra: %s", missing, extra)
                return False

            self._logger.debug("Cross-sensor reference reassignment integrity validated")
            return True

        except Exception as e:
            self._logger.error("Error validating reassignment integrity: %s", e)
            return False


class BulkYamlReassignment(CrossSensorReferenceReassignment):
    """Specialized reassignment for bulk YAML operations with full sensor set context."""

    async def process_bulk_yaml(
        self, config: Config, collect_entity_ids_callback: Callable[[Config], Awaitable[dict[str, str]]]
    ) -> Config:
        """Process bulk YAML with cross-sensor reference reassignment.

        Args:
            config: Full YAML configuration (sensor set)
            collect_entity_ids_callback: Function to collect actual entity IDs

        Returns:
            Configuration with all cross-sensor references resolved
        """
        # Step 1: Always collect actual entity IDs for all sensors
        # This is critical for collision handling - we need to register with HA
        # even if no cross-sensor references are detected, because collisions
        # can cause entity_id changes that require reference updates
        entity_mappings = await collect_entity_ids_callback(config)

        # Step 2: Execute reassignment if we have entity mappings
        # This handles both collision-induced changes and cross-sensor references
        if entity_mappings:
            resolved_config = await self.execute_reassignment(config, entity_mappings)
        else:
            self._logger.debug("No entity mappings returned from callback")
            resolved_config = config

        # Step 3: Validate integrity
        if entity_mappings and not self.validate_reassignment_integrity(config, resolved_config, entity_mappings):
            raise ValueError("Cross-sensor reference reassignment failed integrity validation")

        return resolved_config


class CrudReassignment(CrossSensorReferenceReassignment):
    """Specialized reassignment for CRUD operations affecting individual sensors."""

    async def process_crud_operation(
        self,
        modified_sensors: list[SensorConfig],
        existing_entity_mappings: dict[str, str],
        collect_new_entity_ids_callback: Callable[[list[SensorConfig]], Awaitable[dict[str, str]]],
    ) -> list[SensorConfig]:
        """Process CRUD operation with cross-sensor reference reassignment.

        Args:
            modified_sensors: Sensors being created/updated
            existing_entity_mappings: Known sensor_key -> entity_id mappings
            collect_new_entity_ids_callback: Function to get entity IDs for new sensors

        Returns:
            Updated sensors with resolved cross-sensor references
        """
        # Create temporary config for analysis
        temp_config = Config(sensors=modified_sensors)

        # Step 1: Detect reassignment needs
        reassignment_plan = self.create_reassignment_plan(temp_config, existing_entity_mappings)

        if not reassignment_plan:
            self._logger.debug("No reassignment needed for CRUD operation")
            return modified_sensors

        # Step 2: Collect any new entity IDs needed
        new_entity_mappings = await collect_new_entity_ids_callback(modified_sensors)

        # Step 3: Combine existing and new mappings
        all_entity_mappings = {**existing_entity_mappings, **new_entity_mappings}

        # Step 4: Execute reassignment
        resolved_config = await self.execute_reassignment(temp_config, all_entity_mappings)

        return resolved_config.sensors
