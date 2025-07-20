"""Base interface for variable resolvers in the compiler-like evaluation system."""

from typing import Any

from ...type_definitions import ContextValue


class VariableResolver:
    """Base interface for variable resolvers in the compiler-like evaluation system."""

    def can_resolve(self, variable_name: str, variable_value: str | Any) -> bool:
        """Determine if this resolver can handle the variable."""
        return False

    def resolve(self, variable_name: str, variable_value: str | Any, context: dict[str, ContextValue]) -> Any | None:
        """Resolve a variable."""
        return None

    def get_resolver_name(self) -> str:
        """Get the name of this resolver for logging and debugging."""
        return self.__class__.__name__
