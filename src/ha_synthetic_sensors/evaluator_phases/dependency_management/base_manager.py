"""Base interface for dependency managers in the compiler-like evaluation system."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...hierarchical_context_dict import HierarchicalContextDict


class DependencyManager:
    """Base interface for dependency managers in the compiler-like evaluation system."""

    def can_manage(self, manager_type: str, context: "HierarchicalContextDict") -> bool:
        """Determine if this manager can handle the given type."""
        return False

    def manage(self, manager_type: str, context: "HierarchicalContextDict", **kwargs: Any) -> Any:
        """Manage the given type."""
        return None

    def get_manager_name(self) -> str:
        """Get the name of this manager for logging and debugging."""
        return self.__class__.__name__
