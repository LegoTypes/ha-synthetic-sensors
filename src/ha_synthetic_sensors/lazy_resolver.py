"""Lazy value resolver with memoization for binding plan architecture.

This module implements lazy value resolution that works with binding plans
to resolve values only when accessed, with memoization per evaluation cycle.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .hierarchical_context_dict import HierarchicalContextDict
from .type_definitions import ReferenceValue

_LOGGER = logging.getLogger(__name__)


class LazyResolver:
    """Resolves values lazily on first access with cycle-scoped memoization.

    This resolver works with binding plans to resolve values only when needed,
    reducing unnecessary Home Assistant state lookups and improving performance.
    """

    def __init__(self, hass: HomeAssistant, data_provider: Callable[[str], Any] | None = None):
        """Initialize lazy resolver.

        Args:
            hass: Home Assistant instance for state lookups
            data_provider: Optional data provider callback for variable resolution
        """
        self._hass = hass
        self._data_provider = data_provider
        self._cycle_cache: dict[str, Any] = {}
        self._cycle_id = 0
        self._batch_states: dict[str, Any] = {}
        self._batch_loaded = False

    def start_new_cycle(self) -> None:
        """Start a new evaluation cycle, clearing memoization cache."""
        self._cycle_id += 1
        self._cycle_cache.clear()
        self._batch_states.clear()
        self._batch_loaded = False
        _LOGGER.debug("LazyResolver: Started new cycle %d", self._cycle_id)

    def resolve_if_needed(self, ctx: HierarchicalContextDict, name: str) -> Any:
        """Resolve value on first access, memoize for remainder of cycle.

        Args:
            ctx: The hierarchical context containing the ReferenceValue
            name: The name of the variable to resolve

        Returns:
            The resolved value, or None if resolution fails
        """
        # Check if already resolved this cycle
        cache_key = f"{self._cycle_id}:{name}"
        if cache_key in self._cycle_cache:
            _LOGGER.debug("LazyResolver: Cache hit for %s", name)
            return self._cycle_cache[cache_key]

        # Get ReferenceValue from context
        ref_value = ctx.get(name)
        if not isinstance(ref_value, ReferenceValue):
            # Not a ReferenceValue, return as-is
            return ref_value

        # Check if already resolved
        if ref_value.value is not None:
            # Already has a value, cache and return
            self._cycle_cache[cache_key] = ref_value.value
            return ref_value.value

        # Resolve based on strategy
        strategy_value = ctx.get(f"_strategy_{name}")
        strategy = "ha_state" if strategy_value is None else str(strategy_value)
        resolved = self._resolve_by_strategy(name, strategy)

        # Update ReferenceValue in place using property setter if available
        if hasattr(ref_value, "_value"):
            # Access protected member is necessary for lazy resolution
            ref_value._value = resolved  # pylint: disable=protected-access

        # Cache the resolved value
        self._cycle_cache[cache_key] = resolved

        _LOGGER.debug("LazyResolver: Resolved %s = %s (strategy: %s)", name, resolved, strategy)
        return resolved

    def _resolve_by_strategy(self, name: str, strategy: str) -> Any:
        """Resolve value based on resolution strategy.

        Args:
            name: The name to resolve
            strategy: Resolution strategy (ha_state, data_provider, literal, etc.)

        Returns:
            The resolved value
        """
        try:
            # Map strategies to their resolver methods
            resolvers = {
                "ha_state": self._resolve_ha_state,
                "data_provider": self._resolve_data_provider,
                "literal": self._resolve_literal,
            }

            if strategy in resolvers:
                return resolvers[strategy](name)

            if strategy in ("computed", "cross_sensor"):
                # These variables should be resolved elsewhere
                _LOGGER.debug("LazyResolver: %s variable %s not resolved here", strategy.title(), name)
                return None

            _LOGGER.warning("LazyResolver: Unknown strategy %s for %s", strategy, name)
            return None
        except Exception as e:
            _LOGGER.warning("LazyResolver: Failed to resolve %s with strategy %s: %s", name, strategy, e)
            return None

    def _resolve_ha_state(self, entity_id: str) -> Any:
        """Resolve Home Assistant entity state.

        Args:
            entity_id: The entity ID to resolve

        Returns:
            The entity state value
        """
        # Use batch loading if available
        if not self._batch_loaded:
            self._load_batch_states()

        if entity_id in self._batch_states:
            return self._batch_states[entity_id]

        # Fallback to individual lookup
        state = self._hass.states.get(entity_id)
        if state is None:
            _LOGGER.debug("LazyResolver: Entity %s not found", entity_id)
            return None

        return state.state

    def _resolve_data_provider(self, name: str) -> Any:
        """Resolve value via data provider callback.

        Args:
            name: The variable name to resolve

        Returns:
            The resolved value from data provider
        """
        if self._data_provider is None:
            _LOGGER.debug("LazyResolver: No data provider for %s", name)
            return None

        try:
            result = self._data_provider(name)
            return result.value if hasattr(result, "value") else result
        except Exception as e:
            _LOGGER.debug("LazyResolver: Data provider failed for %s: %s", name, e)
            return None

    def _resolve_literal(self, name: str) -> Any:
        """Resolve literal value.

        Args:
            name: The literal name

        Returns:
            The literal value
        """
        # For now, return the name as the value
        # This could be enhanced to parse actual literal values from AST
        return name

    def _load_batch_states(self) -> None:
        """Load batch of HA states for efficient lookup.

        This method could be enhanced to pre-load states based on
        binding plan requirements to reduce individual lookups.
        """
        # For now, mark as loaded to prevent repeated calls
        self._batch_loaded = True
        _LOGGER.debug("LazyResolver: Batch states loaded for cycle %d", self._cycle_id)

    def prepare_batch_entities(self, entity_ids: set[str]) -> None:
        """Prepare batch loading for specific entity IDs.

        Args:
            entity_ids: Set of entity IDs to pre-load
        """
        if not entity_ids:
            return

        _LOGGER.debug("LazyResolver: Preparing batch for %d entities", len(entity_ids))

        # Pre-load states for batch access
        for entity_id in entity_ids:
            state = self._hass.states.get(entity_id)
            if state is not None:
                self._batch_states[entity_id] = state.state

        self._batch_loaded = True

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics for performance monitoring.

        Returns:
            Dictionary with cache hit/miss statistics
        """
        return {
            "cycle_id": self._cycle_id,
            "cache_size": len(self._cycle_cache),
            "batch_size": len(self._batch_states),
            "batch_loaded": self._batch_loaded,
        }
