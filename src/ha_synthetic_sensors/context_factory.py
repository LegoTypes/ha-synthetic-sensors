"""Context Factory with Singleton Pattern to Prevent Context Duplication.

This module implements a singleton pattern to ensure that evaluation contexts
are reused rather than creating new ones, which violates the architecture
principle of "NO NEW CONTEXT CREATION".
"""

from collections.abc import Callable
import threading
import traceback
from typing import Any, Optional

from .evaluation_context import HierarchicalEvaluationContext
from .hierarchical_context_dict import HierarchicalContextDict


class ContextCreationViolationError(Exception):
    """Raised when attempting to create multiple contexts for the same ID."""


class ContextFactory:
    """Singleton factory for managing hierarchical evaluation contexts.

    This factory ensures that contexts are reused rather than creating
    new ones, preventing violations of the "NO NEW CONTEXT CREATION"
    architecture principle.
    """

    _instance: Optional["ContextFactory"] = None
    _lock = threading.Lock()
    _contexts: dict[str, HierarchicalEvaluationContext]
    _context_dicts: dict[str, HierarchicalContextDict]

    def __new__(cls) -> "ContextFactory":
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._contexts = {}
                    cls._instance._context_dicts = {}
        return cls._instance

    def get_or_create_context(
        self, context_id: str, name: str = "sensor", allow_new: bool = False
    ) -> HierarchicalEvaluationContext:
        """Get existing context or create new one if it doesn't exist.

        Args:
            context_id: Unique identifier for the context (e.g., sensor_id)
            name: Name for the context if creating new one
            allow_new: Whether to allow creating new contexts (default False to catch violations)

        Returns:
            Existing or newly created HierarchicalEvaluationContext

        Raises:
            ContextCreationViolationError: If attempting to create when allow_new=False
        """
        if context_id not in self._contexts:
            if not allow_new:
                raise ContextCreationViolationError(
                    f"Attempted to create new context '{context_id}' when allow_new=False. "
                    f"This violates the 'NO NEW CONTEXT CREATION' architecture principle. "
                    f"Existing contexts: {list(self._contexts.keys())}"
                )
            self._contexts[context_id] = HierarchicalEvaluationContext(name)
        return self._contexts[context_id]

    def get_or_create_context_dict(
        self, context_id: str, name: str = "sensor", allow_new: bool = False
    ) -> HierarchicalContextDict:
        """Get existing context dict or create new one if it doesn't exist.

        Args:
            context_id: Unique identifier for the context (e.g., sensor_id)
            name: Name for the context if creating new one
            allow_new: Whether to allow creating new contexts (default False to catch violations)

        Returns:
            Existing or newly created HierarchicalContextDict

        Raises:
            ContextCreationViolationError: If attempting to create when allow_new=False
        """
        if context_id not in self._context_dicts:
            hierarchical_context = self.get_or_create_context(context_id, name, allow_new=allow_new)
            self._context_dicts[context_id] = HierarchicalContextDict(hierarchical_context)
        return self._context_dicts[context_id]

    def register_existing_context(self, context_id: str, context: HierarchicalEvaluationContext) -> None:
        """Register an existing context to prevent duplication.

        Args:
            context_id: Unique identifier for the context
            context: Existing context to register
        """
        self._contexts[context_id] = context

    def register_existing_context_dict(self, context_id: str, context_dict: HierarchicalContextDict) -> None:
        """Register an existing context dict to prevent duplication.

        Args:
            context_id: Unique identifier for the context
            context_dict: Existing context dict to register
        """
        self._context_dicts[context_id] = context_dict
        # Also register the underlying hierarchical context
        self._contexts[context_id] = context_dict.get_hierarchical_context()

    def clear_context(self, context_id: str) -> None:
        """Clear a specific context (for cleanup after evaluation).

        Args:
            context_id: Unique identifier for the context to clear
        """
        self._contexts.pop(context_id, None)
        self._context_dicts.pop(context_id, None)

    def clear_all_contexts(self) -> None:
        """Clear all contexts (for testing or system reset)."""
        self._contexts.clear()
        self._context_dicts.clear()

    def get_active_contexts(self) -> dict[str, str]:
        """Get information about active contexts (for debugging).

        Returns:
            Dict mapping context_id to context name
        """
        return {context_id: context.name for context_id, context in self._contexts.items()}


# Convenience functions for easy access
def get_context_factory() -> ContextFactory:
    """Get the singleton context factory instance."""
    return ContextFactory()


def get_or_create_context(context_id: str, name: str = "sensor", allow_new: bool = False) -> HierarchicalEvaluationContext:
    """Convenience function to get or create a context."""
    return get_context_factory().get_or_create_context(context_id, name, allow_new=allow_new)


def get_or_create_context_dict(context_id: str, name: str = "sensor", allow_new: bool = False) -> HierarchicalContextDict:
    """Convenience function to get or create a context dict."""
    return get_context_factory().get_or_create_context_dict(context_id, name, allow_new=allow_new)


# Monkey patch to intercept direct context creation
class ContextCreationMonitor:
    """Monitor for direct context creation to catch violations."""

    def __init__(self) -> None:
        """Initialize the monitor."""
        self._original_hierarchical_evaluation_context_init: Any = None
        self._original_hierarchical_context_dict_init: Any = None

    def _patched_hierarchical_evaluation_context_init(
        self, self_instance: HierarchicalEvaluationContext, name: str = "root"
    ) -> None:
        """Patched init that throws exception on direct creation."""
        stack_trace = "".join(traceback.format_stack())

        # Allow creation only from the factory or specific allowed locations
        if (
            "context_factory.py" in stack_trace
            or "test_" in stack_trace  # Allow in tests
            or "_test" in stack_trace  # Allow in test fixtures
            or "conftest.py" in stack_trace
        ) and self._original_hierarchical_evaluation_context_init is not None:  # Allow in test configuration
            self._original_hierarchical_evaluation_context_init(self_instance, name)
            return

        raise ContextCreationViolationError(
            f"Direct creation of HierarchicalEvaluationContext('{name}') detected! "
            f"Use ContextFactory.get_or_create_context() instead to prevent context duplication. "
            f"This violates the 'NO NEW CONTEXT CREATION' architecture principle.\n"
            f"Stack trace:\n{stack_trace}"
        )

    def _create_patched_hierarchical_evaluation_context_init(self) -> Callable[[HierarchicalEvaluationContext, str], None]:
        """Create a patched init method with the correct signature."""

        def patched_init(self_instance: HierarchicalEvaluationContext, name: str = "root") -> None:
            """Patched init that throws exception on direct creation."""
            stack_trace = "".join(traceback.format_stack())

            # Allow creation only from the factory or specific allowed locations
            if (
                "context_factory.py" in stack_trace
                or "test_" in stack_trace  # Allow in tests
                or "_test" in stack_trace  # Allow in test fixtures
                or "conftest.py" in stack_trace
            ) and self._original_hierarchical_evaluation_context_init is not None:  # Allow in test configuration
                self._original_hierarchical_evaluation_context_init(self_instance, name)
                return

            raise ContextCreationViolationError(
                f"Direct creation of HierarchicalEvaluationContext('{name}') detected! "
                f"Use ContextFactory.get_or_create_context() instead to prevent context duplication. "
                f"This violates the 'NO NEW CONTEXT CREATION' architecture principle.\n"
                f"Stack trace:\n{stack_trace}"
            )

        return patched_init

    def _patched_hierarchical_context_dict_init(
        self, self_instance: HierarchicalContextDict, hierarchical_context: HierarchicalEvaluationContext
    ) -> None:
        """Patched init that throws exception on direct creation."""
        stack_trace = "".join(traceback.format_stack())

        # Allow creation only from the factory or specific allowed locations
        if (
            "context_factory.py" in stack_trace
            or "test_" in stack_trace  # Allow in tests
            or "_test" in stack_trace  # Allow in test fixtures
            or "conftest.py" in stack_trace
        ) and self._original_hierarchical_context_dict_init is not None:  # Allow in test configuration
            self._original_hierarchical_context_dict_init(self_instance, hierarchical_context)
            return

        raise ContextCreationViolationError(
            f"Direct creation of HierarchicalContextDict detected! "
            f"Use ContextFactory.get_or_create_context_dict() instead to prevent context duplication. "
            f"This violates the 'NO NEW CONTEXT CREATION' architecture principle.\n"
            f"Stack trace:\n{stack_trace}"
        )

    def _create_patched_hierarchical_context_dict_init(
        self,
    ) -> Callable[[HierarchicalContextDict, HierarchicalEvaluationContext], None]:
        """Create a patched init method with the correct signature."""

        def patched_init(self_instance: HierarchicalContextDict, hierarchical_context: HierarchicalEvaluationContext) -> None:
            """Patched init that throws exception on direct creation."""
            stack_trace = "".join(traceback.format_stack())

            # Allow creation only from the factory or specific allowed locations
            if (
                "context_factory.py" in stack_trace
                or "test_" in stack_trace  # Allow in tests
                or "_test" in stack_trace  # Allow in test fixtures
                or "conftest.py" in stack_trace
            ) and self._original_hierarchical_context_dict_init is not None:  # Allow in test configuration
                self._original_hierarchical_context_dict_init(self_instance, hierarchical_context)
                return

            raise ContextCreationViolationError(
                f"Direct creation of HierarchicalContextDict detected! "
                f"Use ContextFactory.get_or_create_context_dict() instead to prevent context duplication. "
                f"This violates the 'NO NEW CONTEXT CREATION' architecture principle.\n"
                f"Stack trace:\n{stack_trace}"
            )

        return patched_init

    def enable_monitoring(self) -> None:
        """Enable monitoring of direct context creation to catch violations."""
        if self._original_hierarchical_evaluation_context_init is None:
            self._original_hierarchical_evaluation_context_init = HierarchicalEvaluationContext.__init__
            HierarchicalEvaluationContext.__init__ = self._create_patched_hierarchical_evaluation_context_init()

        if self._original_hierarchical_context_dict_init is None:
            self._original_hierarchical_context_dict_init = HierarchicalContextDict.__init__
            HierarchicalContextDict.__init__ = self._create_patched_hierarchical_context_dict_init()

    def disable_monitoring(self) -> None:
        """Disable monitoring of direct context creation."""
        if self._original_hierarchical_evaluation_context_init is not None:
            HierarchicalEvaluationContext.__init__ = self._original_hierarchical_evaluation_context_init
            self._original_hierarchical_evaluation_context_init = None

        if self._original_hierarchical_context_dict_init is not None:
            HierarchicalContextDict.__init__ = self._original_hierarchical_context_dict_init
            self._original_hierarchical_context_dict_init = None


# Global monitor instance
_context_monitor = ContextCreationMonitor()


def enable_context_creation_monitoring() -> None:
    """Enable monitoring of direct context creation to catch violations."""
    _context_monitor.enable_monitoring()


def disable_context_creation_monitoring() -> None:
    """Disable monitoring of direct context creation."""
    _context_monitor.disable_monitoring()
