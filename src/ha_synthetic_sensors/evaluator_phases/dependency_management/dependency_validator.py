"""Dependency validator for validating dependency availability."""

import logging
from typing import TYPE_CHECKING, Any

from .base_manager import DependencyManager

if TYPE_CHECKING:
    from ...hierarchical_context_dict import HierarchicalContextDict

_LOGGER = logging.getLogger(__name__)


class DependencyValidator(DependencyManager):
    """Validator for dependency availability."""

    def can_manage(self, manager_type: str, context: "HierarchicalContextDict") -> bool:
        """Determine if this manager can handle dependency validation."""
        return manager_type == "validate"

    def manage(
        self, manager_type: str, context: "HierarchicalContextDict", **kwargs: Any
    ) -> tuple[set[str], set[str], set[str]]:
        """Validate dependencies and return missing, unavailable, and unknown dependencies."""
        if manager_type != "validate":
            return set(), set(), set()

        # Get data from kwargs instead of context for dependency management
        dependencies = kwargs.get("dependencies", set())
        available_entities = kwargs.get("available_entities", set())
        registered_integration_entities = kwargs.get("registered_integration_entities", set())
        hass = kwargs.get("hass")

        missing_deps: set[str] = set()
        unavailable_deps: set[str] = set()
        unknown_deps: set[str] = set()

        # Log if we're seeing unexpected dependencies for power sensors
        formula_name = kwargs.get("formula_name", "unknown")
        if "Power" in formula_name and dependencies:
            suspicious_deps = [
                d
                for d in dependencies
                if d in ("last_valid_changed", "last_valid_state", "panel_offline_minutes", "panel_status")
            ]
            if suspicious_deps:
                _LOGGER.warning(
                    "CROSS_CONTAMINATION: Power sensor '%s' has energy sensor dependencies: %s", formula_name, suspicious_deps
                )

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
            # Check if this looks like a computed variable (not an entity ID pattern)
            # These are variables that will be resolved during evaluation, not entities
            if "." not in dep and not dep.startswith("sensor.") and not dep.startswith("binary_sensor."):
                # This looks like a variable name, not an entity ID
                _LOGGER.debug("Dependency validator: Skipping variable '%s' (will be resolved during evaluation)", dep)
                continue
            # Entity not found
            missing_deps.add(dep)

        _LOGGER.debug(
            "Dependency validator: missing=%s, unavailable=%s, unknown=%s", missing_deps, unavailable_deps, unknown_deps
        )

        return missing_deps, unavailable_deps, unknown_deps
