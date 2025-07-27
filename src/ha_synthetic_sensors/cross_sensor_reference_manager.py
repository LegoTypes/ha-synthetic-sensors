"""Cross-Sensor Reference Manager for Phase 2 of cross-sensor reference resolution.

This module implements the second phase of the cross-sensor reference system as described
in the design reference guide. It captures actual HA-assigned entity IDs during sensor
registration and maintains mappings for later reference resolution.

Key Features:
- Captures actual HA entity IDs during async_added_to_hass() lifecycle
- Maintains mapping between YAML sensor keys and actual entity IDs
- Coordinates with SensorManager for entity registration events
- Prepares for Phase 3 formula reference resolution
"""

from collections.abc import Awaitable, Callable
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .config_models import Config
from .formula_reference_resolver import FormulaReferenceResolver

_LOGGER = logging.getLogger(__name__)


class CrossSensorReferenceManager:
    """Manages cross-sensor reference resolution during entity registration.

    This manager handles Phase 2 of the cross-sensor reference system:
    - Capturing actual HA-assigned entity IDs during registration
    - Maintaining mappings between YAML sensor keys and entity IDs
    - Coordinating entity registration events
    - Preparing for formula reference resolution in Phase 3
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the cross-sensor reference manager.

        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        self._logger = _LOGGER.getChild(self.__class__.__name__)

        # Phase 1 data: Cross-sensor reference mapping from detector
        self._cross_sensor_references: dict[str, set[str]] = {}

        # Phase 2 data: Entity ID mappings
        self._sensor_key_to_entity_id: dict[str, str] = {}  # sensor_key -> actual_entity_id
        self._entity_id_to_sensor_key: dict[str, str] = {}  # actual_entity_id -> sensor_key

        # Registration tracking
        self._pending_registrations: set[str] = set()  # sensor_keys awaiting registration
        self._completed_registrations: set[str] = set()  # sensor_keys with captured entity_ids

        # Callbacks for when all registrations are complete
        self._completion_callbacks: list[Callable[[], Awaitable[None]]] = []

        # Phase 3: Formula reference resolver
        self._formula_resolver = FormulaReferenceResolver()
        self._original_config: Config | None = None
        self._resolved_config: Config | None = None

    def initialize_from_config(
        self, cross_sensor_references: dict[str, set[str]], original_config: Config | None = None
    ) -> None:
        """Initialize with cross-sensor references from Phase 1 detection.

        Args:
            cross_sensor_references: Mapping from Phase 1 detector
            original_config: Original config to store for Phase 3 reference resolution
        """
        self._cross_sensor_references = cross_sensor_references.copy()

        # Determine which sensors need entity ID registration
        sensors_needing_registration = set()
        for sensor_key, references in cross_sensor_references.items():
            sensors_needing_registration.add(sensor_key)
            sensors_needing_registration.update(references)

        self._pending_registrations = sensors_needing_registration.copy()

        # Store original config for Phase 3
        self._original_config = original_config

        self._logger.debug(
            "Initialized cross-sensor reference manager with %d sensors needing registration: %s",
            len(sensors_needing_registration),
            list(sensors_needing_registration),
        )

    async def register_sensor_entity_id(self, sensor_key: str, actual_entity_id: str) -> None:
        """Register the actual entity ID assigned by HA for a sensor key.

        This method is called from DynamicSensor.async_added_to_hass() when HA
        has assigned the final entity ID.

        Args:
            sensor_key: Original YAML sensor key (unique_id)
            actual_entity_id: Actual entity ID assigned by HA
        """
        self._logger.debug("Registering entity ID mapping: %s -> %s", sensor_key, actual_entity_id)

        # Store the mapping
        self._sensor_key_to_entity_id[sensor_key] = actual_entity_id
        self._entity_id_to_sensor_key[actual_entity_id] = sensor_key

        # Mark as completed
        if sensor_key in self._pending_registrations:
            self._pending_registrations.remove(sensor_key)
            self._completed_registrations.add(sensor_key)

            self._logger.debug(
                "Entity ID registration complete for %s. Pending: %d, Completed: %d",
                sensor_key,
                len(self._pending_registrations),
                len(self._completed_registrations),
            )

            # Check if all registrations are complete
            if not self._pending_registrations:
                await self._on_all_registrations_complete()

    async def _on_all_registrations_complete(self) -> None:
        """Called when all sensor entity IDs have been captured."""
        self._logger.info(
            "All cross-sensor entity ID registrations complete. Captured %d mappings.", len(self._sensor_key_to_entity_id)
        )

        # Log the complete mapping for debugging
        for sensor_key, entity_id in self._sensor_key_to_entity_id.items():
            self._logger.debug("  %s -> %s", sensor_key, entity_id)

        # Phase 3: Resolve formula references if we have the original config
        if self._original_config:
            await self._resolve_formula_references()

        # Execute completion callbacks (for Phase 3 initiation)
        for callback in self._completion_callbacks:
            try:
                await callback()
            except Exception as e:
                self._logger.error("Error in completion callback: %s", e)

    async def _resolve_formula_references(self) -> None:
        """Execute Phase 3: Formula reference resolution."""
        if not self._original_config:
            self._logger.warning("No original config available for formula reference resolution")
            return

        self._logger.info("Starting Phase 3: Formula reference resolution")

        try:
            # Resolve all references in the config
            self._resolved_config = self._formula_resolver.resolve_all_references_in_config(
                self._original_config, self._sensor_key_to_entity_id
            )

            self._logger.info("Phase 3 formula reference resolution complete")

            # Log replacement summary for debugging
            replacement_summary: dict[str, dict[str, dict[str, str]]] = self._formula_resolver.get_replacement_summary(
                self._original_config, self._sensor_key_to_entity_id
            )

            if replacement_summary:
                self._logger.debug("Formula reference replacements made:")
                for sensor_key, formula_replacements in replacement_summary.items():
                    for formula_id, replacement_info in formula_replacements.items():
                        self._logger.debug(
                            "  %s.%s: '%s' with replacements %s",
                            sensor_key,
                            formula_id,
                            replacement_info["original_formula"],
                            replacement_info["replacements"],
                        )

        except Exception as e:
            self._logger.error("Error during Phase 3 formula reference resolution: %s", e)
            raise

    def add_completion_callback(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Add a callback to be executed when all registrations are complete.

        Args:
            callback: Async function to call when Phase 2 is complete
        """
        self._completion_callbacks.append(callback)

    def get_entity_id_for_sensor_key(self, sensor_key: str) -> str | None:
        """Get the actual entity ID for a sensor key.

        Args:
            sensor_key: Original YAML sensor key

        Returns:
            Actual entity ID assigned by HA, or None if not registered
        """
        return self._sensor_key_to_entity_id.get(sensor_key)

    def get_sensor_key_for_entity_id(self, entity_id: str) -> str | None:
        """Get the sensor key for an actual entity ID.

        Args:
            entity_id: Actual HA entity ID

        Returns:
            Original YAML sensor key, or None if not found
        """
        return self._entity_id_to_sensor_key.get(entity_id)

    def get_all_entity_mappings(self) -> dict[str, str]:
        """Get all sensor key to entity ID mappings.

        Returns:
            Dict mapping sensor_key -> actual_entity_id
        """
        return self._sensor_key_to_entity_id.copy()

    def has_cross_sensor_references(self) -> bool:
        """Check if any cross-sensor references were detected.

        Returns:
            True if there are cross-sensor references to resolve
        """
        return bool(self._cross_sensor_references)

    def is_registration_pending(self, sensor_key: str) -> bool:
        """Check if a sensor key is still pending registration.

        Args:
            sensor_key: Sensor key to check

        Returns:
            True if registration is still pending
        """
        return sensor_key in self._pending_registrations

    def is_registration_complete(self, sensor_key: str) -> bool:
        """Check if a sensor key has completed registration.

        Args:
            sensor_key: Sensor key to check

        Returns:
            True if registration is complete
        """
        return sensor_key in self._completed_registrations

    def are_all_registrations_complete(self) -> bool:
        """Check if all required registrations are complete.

        Returns:
            True if all sensor entity IDs have been captured
        """
        return len(self._pending_registrations) == 0

    def get_cross_sensor_references(self) -> dict[str, set[str]]:
        """Get the cross-sensor references from Phase 1.

        Returns:
            Dict mapping sensor_key -> set of referenced sensor keys
        """
        return self._cross_sensor_references.copy()

    def get_resolved_config(self) -> Config | None:
        """Get the resolved config from Phase 3.

        Returns:
            Config with resolved formula references, or None if not completed
        """
        return self._resolved_config

    def is_phase_3_complete(self) -> bool:
        """Check if Phase 3 formula reference resolution is complete.

        Returns:
            True if Phase 3 is complete and resolved config is available
        """
        return self._resolved_config is not None

    def get_registration_status(self) -> dict[str, Any]:
        """Get the current registration status for debugging.

        Returns:
            Dict with registration status information
        """
        return {
            "pending_count": len(self._pending_registrations),
            "completed_count": len(self._completed_registrations),
            "pending_sensors": list(self._pending_registrations),
            "completed_sensors": list(self._completed_registrations),
            "entity_mappings": self._sensor_key_to_entity_id.copy(),
        }
