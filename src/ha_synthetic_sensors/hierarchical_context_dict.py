"""Hierarchical context dictionary that enforces unified setter usage."""

from __future__ import annotations

from collections.abc import Iterator
import logging
import traceback
from typing import ClassVar

from .evaluation_context import HierarchicalEvaluationContext
from .type_definitions import ContextValue, ReferenceValue

_LOGGER = logging.getLogger(__name__)


class HierarchicalContextDict:
    """Dictionary that redirects assignments to hierarchical context unified setter.

    This prevents direct context assignments (context[key] = value) and ensures
    all modifications go through the hierarchical context's unified setter.

    Each evaluation gets its own unique context instance to prevent pollution across sensors and update cycles.
    """

    # Class-level registry for cleanup purposes only (not for singleton behavior)
    _instances: ClassVar[dict[str, HierarchicalContextDict]] = {}

    def __new__(cls, hierarchical_context: HierarchicalEvaluationContext) -> HierarchicalContextDict:
        """Create a new instance for each evaluation to prevent context pollution."""
        instance = super().__new__(cls)

        # Register for cleanup purposes but don't enforce singleton behavior
        context_id = hierarchical_context.name
        # Use a unique key that includes object id to avoid collisions
        unique_key = f"{context_id}_{id(instance)}"
        cls._instances[unique_key] = instance

        _LOGGER.debug("HIERARCHICAL_DICT_CREATE: Created new context instance %s for context %s", unique_key, context_id)
        return instance

    def __init__(self, hierarchical_context: HierarchicalEvaluationContext) -> None:
        """Initialize with reference to hierarchical context."""
        self._internal_dict: dict[str, ContextValue] = {}
        self._hierarchical_context = hierarchical_context
        self._allow_direct_assignment = False

        _LOGGER.debug("HIERARCHICAL_DICT_INIT: Initialized hierarchical dictionary for context %s", hierarchical_context.name)

    def __setitem__(self, key: str, value: ContextValue) -> None:
        """Override assignment to use hierarchical context unified setter."""
        # CRITICAL: Enforce ReferenceValue architecture at the earliest point
        if not isinstance(value, ReferenceValue):
            # This is a raw value being stored in context - this violates the architecture
            stack_trace = "".join(traceback.format_stack())

            raise ValueError(
                f"Attempted to store raw value '{value}' (type: {type(value).__name__}) "
                f"for key '{key}' in HierarchicalContextDict. All variables must be ReferenceValue objects. "
                f"This indicates a critical bug in the variable resolution system where raw values "
                f"are reaching the context instead of being properly wrapped in ReferenceValue objects.\n"
                f"Stack trace:\n{stack_trace}"
            )

        _LOGGER.warning(
            "HIERARCHICAL_DICT_SETITEM: Assignment %s = %s (bypass=%s)",
            key,
            type(value).__name__,
            self._allow_direct_assignment,
        )

        if self._allow_direct_assignment:
            # Temporary bypass for internal operations
            self._internal_dict[key] = value
            return

        # BULLETPROOF: Throw exception on direct assignment to catch violations
        stack_trace = "".join(traceback.format_stack())

        raise RuntimeError(
            f"DIRECT_ASSIGNMENT_VIOLATION: Attempted direct assignment {key} = {value} "
            f"bypasses hierarchical context unified setter!\n"
            f"Use context.set('{key}', value) instead of context['{key}'] = value\n"
            f"Stack trace:\n{stack_trace}"
        )

    def _temporary_direct_assignment(self) -> DirectAssignmentContext:
        """Context manager to temporarily allow direct assignment."""
        return DirectAssignmentContext(self)

    def clear(self) -> None:
        """Clear internal dictionary."""
        self._internal_dict.clear()

    def update_from_hierarchical_context(self) -> None:
        """Sync our internal dict with the hierarchical context."""
        flattened = self._hierarchical_context.flatten()

        with self._temporary_direct_assignment():
            self.clear()
            self._internal_dict.update(flattened)

        _LOGGER.debug("HIERARCHICAL_DICT_SYNC: Synced %d items from hierarchical context", len(flattened))

    def __getitem__(self, key: str) -> ContextValue:
        """Get item, ensuring we have latest from hierarchical context."""
        # Check hierarchical context first for most up-to-date value
        if self._hierarchical_context.has(key):
            return self._hierarchical_context.get(key)
        return self._internal_dict[key]

    def get(self, key: str, default: ContextValue | None = None) -> ContextValue | None:
        """Get value, checking hierarchical context first."""
        if self._hierarchical_context.has(key):
            try:
                return self._hierarchical_context.get(key)
            except AttributeError:
                # HierarchicalEvaluationContext doesn't have a get method, use has + __getitem__
                if self._hierarchical_context.has(key):
                    return self._hierarchical_context[key]
                return default
        if key in self._internal_dict:
            return self._internal_dict[key]
        return default

    def __contains__(self, key: object) -> bool:
        """Check if key exists in hierarchical context or internal dict."""
        if not isinstance(key, str):
            return False
        return self._hierarchical_context.has(key) or key in self._internal_dict

    def keys(self) -> Iterator[str]:
        """Return keys from hierarchical context."""
        # Get keys from hierarchical context first
        hierarchical_keys = set(self._hierarchical_context.keys())
        # Add any additional keys from our internal dict
        internal_keys = set(self._internal_dict.keys())
        return iter(hierarchical_keys | internal_keys)

    def values(self) -> Iterator[ContextValue]:
        """Return values from hierarchical context."""
        # This is a simplified implementation - in practice, you might want to
        # ensure consistency with the keys() method
        for _, value in self.items():
            yield value

    def items(self) -> Iterator[tuple[str, ContextValue]]:
        """Return items from hierarchical context."""
        # Get all unique keys and their values respecting hierarchical scoping
        seen_keys = set()

        # First get items from hierarchical context (respects scoping)
        if hasattr(self._hierarchical_context, "items"):
            for key, value in self._hierarchical_context.items():
                if key not in seen_keys:
                    seen_keys.add(key)
                    yield key, value

        # Then add any additional items from internal dict
        for key, value in self._internal_dict.items():
            if key not in seen_keys:
                seen_keys.add(key)
                yield key, value

    def __iter__(self) -> Iterator[str]:
        """Iterate over keys."""
        return self.keys()

    def __len__(self) -> int:
        """Get length from hierarchical context."""
        hierarchical_keys = set(self._hierarchical_context.keys())
        internal_keys = set(self._internal_dict.keys())
        return len(hierarchical_keys | internal_keys)

    def copy(self) -> HierarchicalContextDict:
        """Create a copy of this dictionary."""
        raise RuntimeError("Copying HierarchicalContextDict is not allowed - it's a singleton")

    def update(self, other: dict[str, ContextValue]) -> None:
        """Update the context with values from another dict."""
        # Use the hierarchical context's set method to maintain architecture
        for key, value in other.items():
            self._hierarchical_context.set(key, value)

        # Update our internal dict as well
        with self._temporary_direct_assignment():
            self._internal_dict.update(other)

    def get_hierarchical_context(self) -> HierarchicalEvaluationContext:
        """Get the underlying hierarchical evaluation context."""
        return self._hierarchical_context

    def __reduce__(self) -> tuple[type[HierarchicalContextDict], tuple[HierarchicalEvaluationContext]]:
        """Support for pickling."""
        # Return a tuple that can be used to reconstruct the object
        return (HierarchicalContextDict, (self._hierarchical_context,))

    def __setstate__(self, state: dict[str, object]) -> None:
        """Support for unpickling."""
        # Reconstruct the object state
        # Implementation would go here if needed

    @classmethod
    def cleanup_singleton(cls, hierarchical_context: HierarchicalEvaluationContext) -> None:
        """Clean up singleton instance for a specific context when evaluation is complete."""
        context_id = hierarchical_context.name
        if context_id in cls._instances:
            del cls._instances[context_id]
            _LOGGER.warning("HIERARCHICAL_DICT_CLEANUP: Removed singleton instance for context %s", context_id)

    @classmethod
    def clear_all_singletons(cls) -> None:
        """Clear all singleton instances - for testing purposes."""
        cls._instances.clear()
        _LOGGER.warning("HIERARCHICAL_DICT_CLEANUP: Cleared all singleton instances")


class DirectAssignmentContext:
    """Context manager for temporarily allowing direct assignment."""

    def __init__(self, parent: HierarchicalContextDict) -> None:
        self.parent = parent

    def __enter__(self) -> DirectAssignmentContext:
        self.parent._allow_direct_assignment = True
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object) -> None:
        self.parent._allow_direct_assignment = False
