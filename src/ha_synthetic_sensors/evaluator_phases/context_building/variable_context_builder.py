"""Variable context builder for handling variable-based contexts."""

import logging
from typing import Any

from .base_builder import ContextBuilder

_LOGGER = logging.getLogger(__name__)


class VariableContextBuilder(ContextBuilder):
    """Builder for variable-based contexts."""

    def can_build(self, builder_type: str, context: dict[str, Any] | None = None) -> bool:
        """Determine if this builder can handle variable context building."""
        return builder_type == "variable"

    def build(self, builder_type: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build variable context."""
        if builder_type != "variable" or not context:
            return {}
        return context.copy()
