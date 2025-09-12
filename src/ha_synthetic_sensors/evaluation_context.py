"""Hierarchical evaluation context for managing variable scoping."""

from __future__ import annotations

from collections.abc import Iterator
import hashlib
import logging
import traceback
from typing import Any

from .type_definitions import ContextValue, ReferenceValue

_LOGGER = logging.getLogger(__name__)


class HierarchicalEvaluationContext:
    """Hierarchical context that respects variable scoping rules.

    Maintains a stack of context layers where inner scopes can shadow
    outer scope variables while preserving the full context chain.

    Scope hierarchy (from outer to inner):
    1. Global variables
    2. Sensor variables
    3. Main formula evaluation results
    4. Attribute variables
    5. Individual attribute formula results
    """

    def __init__(self, name: str = "root"):
        """Initialize a new evaluation context."""
        self.name = name
        self._layers: list[dict[str, ContextValue]] = []
        self._layer_names: list[str] = []

        # Context integrity tracking
        self._instance_id = id(self)  # Memory address for instance tracking
        self._item_count = 0  # Total unique items across all layers
        self._generation = 0  # Increments on each modification

        # State resolver flags
        self._updating_main_result: bool = False  # Flag for main result updates

    @property
    def updating_main_result(self) -> bool:
        """Get the updating main result flag."""
        return self._updating_main_result

    @updating_main_result.setter
    def updating_main_result(self, value: bool) -> None:
        """Set the updating main result flag."""
        self._updating_main_result = value

    def push_layer(self, name: str, variables: dict[str, ContextValue] | None = None) -> None:
        """Push a new context layer onto the stack."""
        layer = variables.copy() if variables else {}
        self._layers.append(layer)
        self._layer_names.append(name)

        # Update tracking
        self._update_tracking()

        _LOGGER.debug(
            "CONTEXT_PUSH: Pushed layer '%s' with %d variables. Stack depth: %d, Total items: %d, Gen: %d",
            name,
            len(layer),
            len(self._layers),
            self._item_count,
            self._generation,
        )

    def pop_layer(self) -> dict[str, ContextValue] | None:
        """Pop the most recent context layer from the stack."""
        if not self._layers:
            return None

        layer = self._layers.pop()
        name = self._layer_names.pop()

        _LOGGER.debug("CONTEXT_POP: Popped layer '%s' with %d variables. Stack depth: %d", name, len(layer), len(self._layers))

        return layer

    def set(self, key: str, value: ContextValue) -> None:
        """Set variable in current layer - ONLY way to modify context.

        This method enforces the ReferenceValue architecture by preventing raw values
        from being stored in context. All variables must be ReferenceValue objects.

        Infrastructure keys (prefixed with _) can store raw values as they are
        part of the evaluation infrastructure, not entity values.

        Args:
            key: The key to set
            value: The value to set (must be ReferenceValue or allowed type)

        Raises:
            RuntimeError: If attempting to store raw entity values in context
        """
        # Allow infrastructure metadata as first-class elements
        if key.startswith("_"):
            # Infrastructure keys: _strategy_*, _binding_plan, _lazy_resolver, etc.
            # These are allowed to be raw values as they're part of the evaluation infrastructure
            if not self._layers:
                # Create first layer if none exists
                self.push_layer("root")
            self._layers[-1][key] = value
            return

        # Enforce ReferenceValue architecture for entity values
        if not isinstance(value, ReferenceValue) and not (callable(value) or isinstance(value, dict) or value is None):
            # This is a raw value being stored in context - this violates the architecture
            stack_trace = "".join(traceback.format_stack())

            raise ValueError(
                f"Attempted to store raw value '{value}' (type: {type(value).__name__}) "
                f"for key '{key}' in HierarchicalEvaluationContext. All entity values must be ReferenceValue objects "
                f"to track their origin. StateType and State objects must be wrapped in ReferenceValue. "
                f"Only Callables, dict[str, Any], and None are allowed as raw values. "
                f"This indicates a critical bug in the variable resolution system.\n"
                f"Stack trace:\n{stack_trace}"
            )

        if not self._layers:
            # Create first layer if none exists
            self.push_layer("root")

        # Set in current layer
        current_layer = self._layers[-1]
        current_layer[key] = value

        # Update tracking
        self._update_tracking()

    def set_system_object(self, key: str, value: Any) -> None:
        """Set system objects like _hass that are needed for evaluation infrastructure.

        This method bypasses ReferenceValue enforcement for specific system objects
        that are part of the evaluation infrastructure, not user variables.

        Args:
            key: The system key (should start with underscore)
            value: The system object

        Raises:
            ValueError: If key doesn't start with underscore (not a system key)
        """
        if not key.startswith("_"):
            raise ValueError(f"set_system_object() can only be used for system keys starting with '_', got: {key}")

        if not self._layers:
            # Create first layer if none exists
            self.push_layer("root")

        # Set system object directly without ReferenceValue enforcement
        current_layer = self._layers[-1]
        current_layer[key] = value

        # Update tracking
        self._update_tracking()

    def get(self, key: str) -> ContextValue:
        """Get a variable by searching from innermost to outermost layer."""
        # Search from innermost (last) to outermost (first) layer
        for i in range(len(self._layers) - 1, -1, -1):
            if key in self._layers[i]:
                value = self._layers[i][key]
                return value

        raise KeyError(f"Key '{key}' not found in any context layer")

    def has(self, key: str) -> bool:
        """Check if a variable exists in any layer."""
        return any(key in layer for layer in self._layers)

    def flatten(self) -> dict[str, ContextValue]:
        """Get a flattened view of all variables (inner shadows outer)."""
        result = {}

        # Start from outermost and work inward so inner values override
        for layer in self._layers:
            result.update(layer)

        return result

    def get_current_layer(self) -> dict[str, ContextValue]:
        """Get the current (innermost) layer."""
        if not self._layers:
            return {}
        return self._layers[-1].copy()

    def keys(self) -> Iterator[str]:
        """Get all unique keys across all layers."""
        seen = set()
        # Search from inner to outer to respect shadowing
        for i in range(len(self._layers) - 1, -1, -1):
            for key in self._layers[i]:
                if key not in seen:
                    seen.add(key)
                    yield key

    def items(self) -> Iterator[tuple[str, ContextValue]]:
        """Get all key-value pairs respecting shadowing."""
        seen = set()
        # Search from inner to outer to respect shadowing
        for i in range(len(self._layers) - 1, -1, -1):
            for key, value in self._layers[i].items():
                if key not in seen:
                    seen.add(key)
                    yield key, value

    def __contains__(self, key: str) -> bool:
        """Check if key exists in context."""
        return self.has(key)

    def __getitem__(self, key: str) -> ContextValue:
        """Get item using bracket notation."""
        return self.get(key)

    def __setitem__(self, key: str, value: ContextValue) -> None:
        """Set item using bracket notation."""
        self.set(key, value)

    def __len__(self) -> int:
        """Get total number of unique variables."""
        return len({key for layer in self._layers for key in layer})

    def debug_dump(self) -> None:
        """Dump the entire context structure for debugging."""

    def _update_tracking(self) -> None:
        """Update context integrity tracking."""
        self._generation += 1
        self._item_count = len({key for layer in self._layers for key in layer})

    def _get_checksum(self) -> str:
        """Get a checksum of all keys for integrity checking."""
        all_keys = sorted({key for layer in self._layers for key in layer})
        key_string = "|".join(all_keys)
        return hashlib.md5(key_string.encode(), usedforsecurity=False).hexdigest()[:8]

    def get_integrity_info(self) -> dict[str, Any]:
        """Get context integrity information for tracking."""
        return {
            "instance_id": self._instance_id,
            "item_count": self._item_count,
            "generation": self._generation,
            "checksum": self._get_checksum(),
            "layer_count": len(self._layers),
        }

    def verify_integrity(self, expected_info: dict[str, Any]) -> tuple[bool, str]:
        """Verify context integrity against expected values."""
        current = self.get_integrity_info()

        # Check instance ID (most important)
        if current["instance_id"] != expected_info["instance_id"]:
            return False, f"Instance changed: {expected_info['instance_id']} -> {current['instance_id']}"

        # Check item count (should only grow)
        if current["item_count"] < expected_info["item_count"]:
            return False, f"Items decreased: {expected_info['item_count']} -> {current['item_count']}"

        # Check generation (should only increase)
        if current["generation"] < expected_info["generation"]:
            return False, f"Generation decreased: {expected_info['generation']} -> {current['generation']}"

        return True, "OK"

    def copy(self) -> HierarchicalEvaluationContext:
        """Create a deep copy of the context."""
        raise RuntimeError("Copying HierarchicalEvaluationContext is not allowed")
