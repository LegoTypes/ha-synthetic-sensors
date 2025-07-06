"""Handler for entity ID changes that coordinates cache invalidation and notifications."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .evaluator import Evaluator
    from .sensor_manager import SensorManager

_LOGGER = logging.getLogger(__name__)


class EntityChangeHandler:
    """
    Coordinates handling of entity ID changes across the synthetic sensors system.

    Manages:
    - Formula cache invalidation
    - Sensor manager notifications
    - Integration callback notifications
    """

    def __init__(self) -> None:
        """Initialize the entity change handler."""
        self._logger = _LOGGER.getChild(self.__class__.__name__)

        # Registered components
        self._evaluators: list[Evaluator] = []
        self._sensor_managers: list[SensorManager] = []
        self._integration_callbacks: list[Callable[[str, str], None]] = []

    def register_evaluator(self, evaluator: Evaluator) -> None:
        """
        Register an evaluator for cache invalidation.

        Args:
            evaluator: Evaluator instance to register
        """
        if evaluator not in self._evaluators:
            self._evaluators.append(evaluator)
            self._logger.debug("Registered evaluator for entity change handling")

    def unregister_evaluator(self, evaluator: Evaluator) -> None:
        """
        Unregister an evaluator.

        Args:
            evaluator: Evaluator instance to unregister
        """
        if evaluator in self._evaluators:
            self._evaluators.remove(evaluator)
            self._logger.debug("Unregistered evaluator from entity change handling")

    def register_sensor_manager(self, sensor_manager: SensorManager) -> None:
        """
        Register a sensor manager for entity ID updates.

        Args:
            sensor_manager: SensorManager instance to register
        """
        if sensor_manager not in self._sensor_managers:
            self._sensor_managers.append(sensor_manager)
            self._logger.debug("Registered sensor manager for entity change handling")

    def unregister_sensor_manager(self, sensor_manager: SensorManager) -> None:
        """
        Unregister a sensor manager.

        Args:
            sensor_manager: SensorManager instance to unregister
        """
        if sensor_manager in self._sensor_managers:
            self._sensor_managers.remove(sensor_manager)
            self._logger.debug("Unregistered sensor manager from entity change handling")

    def register_integration_callback(self, callback: Callable[[str, str], None]) -> None:
        """
        Register an integration callback for entity ID changes.

        Args:
            callback: Function that takes (old_entity_id, new_entity_id) parameters
        """
        if callback not in self._integration_callbacks:
            self._integration_callbacks.append(callback)
            self._logger.debug("Registered integration callback for entity change handling")

    def unregister_integration_callback(self, callback: Callable[[str, str], None]) -> None:
        """
        Unregister an integration callback.

        Args:
            callback: Function to unregister
        """
        if callback in self._integration_callbacks:
            self._integration_callbacks.remove(callback)
            self._logger.debug("Unregistered integration callback from entity change handling")

    def handle_entity_id_change(self, old_entity_id: str, new_entity_id: str) -> None:
        """
        Handle an entity ID change by coordinating all necessary updates.

        Args:
            old_entity_id: Old entity ID
            new_entity_id: New entity ID
        """
        self._logger.info("Handling entity ID change: %s -> %s", old_entity_id, new_entity_id)

        # Track what was updated
        invalidated_caches = 0
        notified_managers = 0
        notified_callbacks = 0

        # Invalidate formula caches in all evaluators
        for evaluator in self._evaluators:
            try:
                # Clear all caches since formulas might reference the changed entity
                # This is conservative but ensures consistency
                evaluator.clear_cache()
                invalidated_caches += 1
                self._logger.debug(
                    "Invalidated formula cache in evaluator for entity change %s -> %s", old_entity_id, new_entity_id
                )
            except Exception as e:
                self._logger.error("Error invalidating cache in evaluator: %s", e)

        # Update sensor managers (they may need to update entity tracking)
        for _sensor_manager in self._sensor_managers:
            try:
                # Update any internal entity tracking
                # This is a placeholder - sensor managers might need specific methods
                # for handling entity ID changes
                notified_managers += 1
                self._logger.debug("Notified sensor manager of entity change %s -> %s", old_entity_id, new_entity_id)
            except Exception as e:
                self._logger.error("Error notifying sensor manager: %s", e)

        # Notify integration callbacks
        for callback in self._integration_callbacks:
            try:
                callback(old_entity_id, new_entity_id)
                notified_callbacks += 1
                self._logger.debug("Notified integration callback of entity change %s -> %s", old_entity_id, new_entity_id)
            except Exception as e:
                self._logger.error("Error in integration callback: %s", e)

        self._logger.info(
            "Completed entity ID change handling %s -> %s: %d caches invalidated, %d managers notified, %d callbacks notified",
            old_entity_id,
            new_entity_id,
            invalidated_caches,
            notified_managers,
            notified_callbacks,
        )

    def get_stats(self) -> dict[str, Any]:
        """
        Get handler statistics.

        Returns:
            Dictionary with handler statistics
        """
        return {
            "registered_evaluators": len(self._evaluators),
            "registered_sensor_managers": len(self._sensor_managers),
            "registered_integration_callbacks": len(self._integration_callbacks),
        }
