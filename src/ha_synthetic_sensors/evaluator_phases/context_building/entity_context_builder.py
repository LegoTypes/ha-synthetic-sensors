"""Entity context builder for handling entity-based contexts."""

import logging
from typing import Any

from .base_builder import ContextBuilder

_LOGGER = logging.getLogger(__name__)


class EntityContextBuilder(ContextBuilder):
    """Builder for entity-based contexts."""

    def can_build(self, builder_type: str, context: dict[str, Any] | None = None) -> bool:
        """Determine if this builder can handle entity context building."""
        return builder_type == "entity"

    def build(self, builder_type: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build entity context."""
        if builder_type != "entity" or not context:
            return {}
        return context.copy()
