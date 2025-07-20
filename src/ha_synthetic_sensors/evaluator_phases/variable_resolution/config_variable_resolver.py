"""Config variable resolver for handling config variables."""

import logging
from typing import Any

from ...type_definitions import ContextValue
from .base_resolver import VariableResolver

_LOGGER = logging.getLogger(__name__)


class ConfigVariableResolver(VariableResolver):
    """Resolver for config variables (direct values or entity references)."""

    def __init__(self) -> None:
        """Initialize the config variable resolver."""
        self._resolver_factory = None

    def set_resolver_factory(self, resolver_factory: Any) -> None:
        """Set the resolver factory for delegating entity references."""
        self._resolver_factory = resolver_factory

    def can_resolve(self, variable_name: str, variable_value: str | Any) -> bool:
        """Determine if this resolver can handle config variables."""
        # Check if other resolvers can handle this first
        if self._resolver_factory:
            for resolver in self._resolver_factory.get_all_resolvers():
                if resolver is not self and resolver.can_resolve(variable_name, variable_value):
                    # Another resolver can handle this, so we shouldn't
                    return False

        # Config variables can be any type (direct values) or entity references
        # This resolver handles cases that aren't handled by other specialized resolvers
        return True

    def resolve(self, variable_name: str, variable_value: str | Any, context: dict[str, ContextValue]) -> Any | None:
        """Resolve a config variable."""
        # Check if the variable is already resolved in the context first
        if variable_name in context:
            resolved_value = context[variable_name]
            _LOGGER.debug("Config variable resolver: context value '%s' = %s", variable_name, resolved_value)
            return resolved_value

        # For direct values (non-strings), return as-is
        if not isinstance(variable_value, str):
            _LOGGER.debug("Config variable resolver: direct value '%s' = %s", variable_name, variable_value)
            return variable_value

        # For string values that don't contain dots, treat as direct values
        if "." not in variable_value:
            _LOGGER.debug("Config variable resolver: direct string value '%s' = %s", variable_name, variable_value)
            return variable_value

        # For entity references, delegate to other resolvers
        if self._resolver_factory:
            # Try to find a more specific resolver for this entity reference
            for resolver in self._resolver_factory.get_all_resolvers():
                if resolver is not self and resolver.can_resolve(variable_name, variable_value):
                    resolved_value = resolver.resolve(variable_name, variable_value, context)
                    if resolved_value is not None:
                        _LOGGER.debug(
                            "Config variable resolver: delegated '%s' = %s to %s, resolved to %s",
                            variable_name,
                            variable_value,
                            resolver.get_resolver_name(),
                            resolved_value,
                        )
                        return resolved_value

        # If no other resolver could handle it, return None
        _LOGGER.debug(
            "Config variable resolver: entity reference '%s' = %s (no resolver found)",
            variable_name,
            variable_value,
        )
        return None
