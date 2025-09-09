"""Sensor evaluation context manager that maintains context throughout the evaluation lifecycle."""

from __future__ import annotations

import logging
from typing import Any
import uuid

from .evaluation_context import HierarchicalEvaluationContext
from .hierarchical_context_dict import HierarchicalContextDict
from .type_definitions import ContextValue, ReferenceValue

_LOGGER = logging.getLogger(__name__)


class SensorEvaluationContext:
    """Manages the evaluation context for a single sensor throughout its evaluation lifecycle.

    This ensures that:
    1. Context is maintained across all evaluation phases
    2. Proper scoping rules are enforced
    3. Variables are never lost between phases
    4. Each phase can access the accumulated context at the right scope
    """

    def __init__(self, sensor_id: str, hass: Any | None = None, entity_id: str | None = None):
        """Initialize context for a sensor evaluation."""

        self.sensor_id = sensor_id
        self.context = HierarchicalEvaluationContext(f"sensor_{sensor_id}")
        self._current_phase = "initialization"

        # Generate unique context ID for tracking
        self._context_uuid = str(uuid.uuid4())

        # Add HASS instance immediately as a system object
        if hass is not None:
            self.context.set_system_object("_hass", hass)
        else:
            raise ValueError("No HASS instance provided during context initialization")

        # Add current sensor entity ID immediately for metadata resolution
        if entity_id is not None:
            try:
                # Create a single ReferenceValue that will be shared and updated when backing entity is resolved
                # State should have None value initially - actual value will be resolved later
                shared_ref_value = ReferenceValue(reference=entity_id, value=None)

                # All three variables point to the same ReferenceValue object
                # When backing entity resolution happens, updating this object updates all three variables
                self.context.set("current_sensor_entity_id", shared_ref_value)
                self.context.set("state", shared_ref_value)
                self.context.set(entity_id, shared_ref_value)
            except Exception as e:
                raise ValueError(f"Failed to set current_sensor_entity_id: {e}") from e
        else:
            raise ValueError("No entity ID provided during context initialization")

    def begin_phase(self, phase_name: str) -> None:
        """Mark the beginning of a new evaluation phase."""
        self._current_phase = phase_name

    def add_global_variables(self, globals_dict: dict[str, ContextValue]) -> None:
        """Add global variables as the base layer."""
        self.begin_phase("global_variables")

        # Add the context UUID to track propagation
        extended_globals = globals_dict.copy()

        self.context.push_layer("globals", extended_globals)
        # Set system object after layer is created
        self.context.set_system_object("_context_uuid", self._context_uuid)

    def add_sensor_variables(self, sensor_vars: dict[str, ContextValue]) -> None:
        """Add sensor-level variables as a new layer."""
        self.begin_phase("sensor_variables")
        self.context.push_layer("sensor_variables", sensor_vars)

        _LOGGER.info("SENSOR_CONTEXT_SENSOR_VARS: Added %d sensor variables for sensor %s", len(sensor_vars), self.sensor_id)

    def add_main_formula_results(self, results: dict[str, ContextValue]) -> None:
        """Add results from main formula evaluation."""
        self.begin_phase("main_formula_results")
        # Don't push a new layer, add to current sensor layer
        # This ensures computed variables are at sensor scope
        for key, value in results.items():
            self.context.set(key, value)

    def begin_attribute_evaluation(self, attribute_name: str) -> None:
        """Begin evaluation of a specific attribute."""
        self.begin_phase(f"attribute_{attribute_name}")
        # Push a new layer for attribute-specific variables
        self.context.push_layer(f"attr_{attribute_name}")

    def add_attribute_variables(self, attr_vars: dict[str, ContextValue]) -> None:
        """Add attribute-specific variables to current attribute layer."""
        for key, value in attr_vars.items():
            self.context.set(key, value)

    def end_attribute_evaluation(self) -> None:
        """End evaluation of current attribute, pop its layer."""
        self.context.pop_layer()

    def get_context_for_evaluation(self) -> HierarchicalContextDict:
        """Get the current context for formula evaluation.

        Returns the SAME hierarchical dictionary instance throughout evaluation.
        The singleton pattern in HierarchicalContextDict ensures this automatically.
        """
        # With singleton pattern, HierarchicalContextDict will return the same instance
        hierarchical_dict = HierarchicalContextDict(self.context)

        # Sync with current hierarchical context state
        hierarchical_dict.update_from_hierarchical_context()

        # Add integrity tracking to the context
        integrity_info = self.context.get_integrity_info()
        hierarchical_dict._hierarchical_context.set("_context_integrity", integrity_info)  # pylint: disable=protected-access

        return hierarchical_dict

    def get_variable(self, key: str) -> ContextValue | None:
        """Get a specific variable respecting scope."""
        try:
            return self.context.get(key)
        except KeyError:
            return None

    def has_variable(self, key: str) -> bool:
        """Check if a variable exists in current scope."""
        return self.context.has(key)

    def debug_dump(self) -> None:
        """Dump the entire context for debugging."""
        self.context.debug_dump()

    def finalize(self) -> dict[str, ContextValue]:
        """Finalize the evaluation and return the complete context (for debugging).

        Collapses the hierarchical context structure into a single flat dictionary
        where inner layer values override outer layer values.

        Example:
            # Hierarchical structure:
            # Layer 1: {"x": 10, "y": 20}
            # Layer 2: {"x": 30, "z": 40}  # x overrides Layer 1's x
            # After flatten():
            # {"x": 30, "y": 20, "z": 40}  # x=30 (from Layer 2), y=20 (from Layer 1), z=40 (from Layer 2)
        """
        self.begin_phase("finalization")
        final_context = self.context.flatten()

        return final_context


class SensorContextManager:
    """Manages sensor evaluation contexts across the system."""

    def __init__(self) -> None:
        """Initialize the context manager."""
        self._active_contexts: dict[str, SensorEvaluationContext] = {}

    def create_context(self, sensor_id: str, hass: Any | None = None, entity_id: str | None = None) -> SensorEvaluationContext:
        """Create a new evaluation context for a sensor."""
        context = SensorEvaluationContext(sensor_id, hass, entity_id)
        self._active_contexts[sensor_id] = context
        return context

    def get_context(self, sensor_id: str) -> SensorEvaluationContext | None:
        """Get the active context for a sensor."""
        return self._active_contexts.get(sensor_id)

    def remove_context(self, sensor_id: str) -> None:
        """Remove a sensor's context after evaluation is complete."""
        if sensor_id in self._active_contexts:
            del self._active_contexts[sensor_id]

    def has_context(self, sensor_id: str) -> bool:
        """Check if a sensor has an active context."""
        return sensor_id in self._active_contexts


# Global context manager instance
_context_manager = SensorContextManager()


def get_context_manager() -> SensorContextManager:
    """Get the global sensor context manager."""
    return _context_manager
