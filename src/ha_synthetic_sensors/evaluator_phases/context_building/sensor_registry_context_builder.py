"""Sensor registry context builder for handling sensor registry contexts."""

import logging
from typing import Any

from .base_builder import ContextBuilder

_LOGGER = logging.getLogger(__name__)


class SensorRegistryContextBuilder(ContextBuilder):
    """Builder for sensor registry contexts."""

    def can_build(self, builder_type: str, context: dict[str, Any] | None = None) -> bool:
        """Determine if this builder can handle sensor registry context building."""
        return builder_type == "sensor_registry"

    def build(self, builder_type: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build sensor registry context."""
        if builder_type != "sensor_registry" or not context:
            return {}
        return context.copy()
