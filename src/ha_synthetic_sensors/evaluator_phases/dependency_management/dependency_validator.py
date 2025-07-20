"""Dependency validator for validating dependency availability."""

import logging
from typing import Any

from .base_manager import DependencyManager

_LOGGER = logging.getLogger(__name__)


class DependencyValidator(DependencyManager):
    """Validator for dependency availability."""

    def can_manage(self, manager_type: str, context: dict[str, Any] | None = None) -> bool:
        """Determine if this manager can handle dependency validation."""
        return manager_type == "validate"

    def manage(
        self, manager_type: str, context: dict[str, Any] | None = None, **kwargs: Any
    ) -> tuple[set[str], set[str], set[str]]:
        """Validate dependencies and return missing, unavailable, and unknown dependencies."""
        if manager_type != "validate" or context is None:
            return set(), set(), set()

        dependencies = context.get("dependencies", set())
        available_entities = context.get("available_entities", set())
        registered_integration_entities = context.get("registered_integration_entities", set())
        hass = context.get("hass")

        missing_deps: set[str] = set()
        unavailable_deps: set[str] = set()
        unknown_deps: set[str] = set()

        for dep in dependencies:
            if dep in available_entities:
                # Dependency is available
                continue
            # Skip if this is a registered integration entity
            if dep in registered_integration_entities:
                continue
            # Check if entity exists in HA
            if hass and hass.states.get(dep):
                continue
            # Entity not found
            missing_deps.add(dep)

        _LOGGER.debug(
            "Dependency validator: missing=%s, unavailable=%s, unknown=%s", missing_deps, unavailable_deps, unknown_deps
        )

        return missing_deps, unavailable_deps, unknown_deps
