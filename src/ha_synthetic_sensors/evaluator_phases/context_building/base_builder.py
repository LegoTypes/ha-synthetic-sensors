"""Base interface for context builders in the compiler-like evaluation system."""

from typing import Any


class ContextBuilder:
    """Base interface for context builders in the compiler-like evaluation system."""

    def can_build(self, builder_type: str, context: dict[str, Any] | None = None) -> bool:
        """Determine if this builder can handle the given type."""
        return False

    def build(self, builder_type: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build context for the given type."""
        return {}

    def get_builder_name(self) -> str:
        """Get the name of this builder for logging and debugging."""
        return self.__class__.__name__
