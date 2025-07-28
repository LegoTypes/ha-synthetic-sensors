"""Factory for creating and managing context builders."""

import logging
from typing import Any

from .base_builder import ContextBuilder
from .entity_context_builder import EntityContextBuilder
from .sensor_registry_context_builder import SensorRegistryContextBuilder
from .variable_context_builder import VariableContextBuilder

_LOGGER = logging.getLogger(__name__)


class ContextBuilderFactory:
    """Factory for creating and managing context builders."""

    def __init__(self) -> None:
        """Initialize the context builder factory with default builders."""
        self._builders: list[ContextBuilder] = []
        self._register_default_builders()

    def _register_default_builders(self) -> None:
        """Register the default set of builders."""
        self.register_builder(EntityContextBuilder())
        self.register_builder(VariableContextBuilder())
        self.register_builder(SensorRegistryContextBuilder())

    def register_builder(self, builder: ContextBuilder) -> None:
        """Register a builder with the factory."""
        self._builders.append(builder)
        _LOGGER.debug("Registered builder: %s", builder.get_builder_name())

    def get_builder_for_context(self, context_type: str, context: dict[str, Any]) -> ContextBuilder | None:
        """Get the appropriate builder for a given context type."""
        for builder in self._builders:
            if builder.can_build(context_type, context):
                return builder
        return None

    def build_context(self, context_type: str, context: dict[str, Any]) -> dict[str, Any]:
        """Build context using the appropriate builder."""
        builder = self.get_builder_for_context(context_type, context)
        if builder:
            return builder.build(context_type, context)
        _LOGGER.warning("No builder found for context type '%s'", context_type)
        return {}

    def get_all_builders(self) -> list[ContextBuilder]:
        """Get all registered builders."""
        return self._builders.copy()

    def clear_builders(self) -> None:
        """Clear all registered builders."""
        self._builders.clear()
        self._register_default_builders()
