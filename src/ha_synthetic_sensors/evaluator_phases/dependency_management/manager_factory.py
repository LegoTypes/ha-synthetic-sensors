"""Factory for creating and managing dependency managers."""

import logging
from typing import Any

from .base_manager import DependencyManager
from .circular_reference_detector import CircularReferenceDetector
from .cross_sensor_dependency_manager import CrossSensorDependencyManager
from .dependency_extractor import DependencyExtractor
from .dependency_validator import DependencyValidator

_LOGGER = logging.getLogger(__name__)


class DependencyManagerFactory:
    """Factory for creating and managing dependency managers."""

    def __init__(self) -> None:
        """Initialize the dependency manager factory with default managers."""
        self._managers: list[DependencyManager] = []
        self._register_default_managers()

    def _register_default_managers(self) -> None:
        """Register the default set of managers."""
        self.register_manager(DependencyExtractor())
        self.register_manager(DependencyValidator())
        self.register_manager(CircularReferenceDetector())
        self.register_manager(CrossSensorDependencyManager())

    def register_manager(self, manager: DependencyManager) -> None:
        """Register a manager with the factory."""
        self._managers.append(manager)
        _LOGGER.debug("Registered manager: %s", manager.get_manager_name())

    def get_manager_for_dependency(self, dependency_type: str, context: dict[str, Any]) -> DependencyManager | None:
        """Get the appropriate manager for a given dependency type."""
        for manager in self._managers:
            if manager.can_manage(dependency_type, context):
                return manager
        return None

    def manage_dependency(self, manager_type: str, context: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Manage dependencies using the appropriate manager."""
        # Check if any manager can handle this type
        for manager in self._managers:
            if manager.can_manage(manager_type, context):
                return manager.manage(manager_type, context, **kwargs)
        # No manager found
        return None

    def get_all_managers(self) -> list[DependencyManager]:
        """Get all registered managers."""
        return self._managers.copy()

    def clear_managers(self) -> None:
        """Clear all registered managers."""
        self._managers.clear()
        self._register_default_managers()
