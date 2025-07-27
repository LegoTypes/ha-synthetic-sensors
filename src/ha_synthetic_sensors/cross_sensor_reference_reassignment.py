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

        # Use existing formula resolver for the actual reassignment
        resolved_config = self._resolver.resolve_all_references_in_config(config, entity_mappings)

        self._logger.info("Cross-sensor reference reassignment complete")
        return resolved_config

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
        # Step 1: Detect what needs reassignment
        reassignment_plan = self.create_reassignment_plan(config)

        if not reassignment_plan:
            self._logger.debug("No reassignment needed for bulk YAML")
            return config

        # Step 2: Collect actual entity IDs for all sensors
        # This callback will typically register sensors with HA and capture entity IDs
        entity_mappings = await collect_entity_ids_callback(config)

        # Step 3: Execute reassignment
        resolved_config = await self.execute_reassignment(config, entity_mappings)

        # Step 4: Validate integrity
        if not self.validate_reassignment_integrity(config, resolved_config, entity_mappings):
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
