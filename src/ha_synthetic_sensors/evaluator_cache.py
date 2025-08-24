"""Cache management functionality for formula evaluation."""

from __future__ import annotations

import logging
from typing import cast

from .cache import CacheConfig, FormulaCache
from .config_models import FormulaConfig
from .constants_evaluation_results import RESULT_KEY_CACHED, RESULT_KEY_STATE, RESULT_KEY_SUCCESS, RESULT_KEY_VALUE, STATE_OK
from .type_definitions import CacheStats, ContextValue, EvaluationResult, ReferenceValue

_LOGGER = logging.getLogger(__name__)


class EvaluatorCache:
    """Handles caching operations for formula evaluation."""

    def __init__(self, cache_config: CacheConfig | None = None) -> None:
        """Initialize cache manager.

        Args:
            cache_config: Optional cache configuration
        """
        self._cache = FormulaCache(cache_config)

    def check_cache(
        self, config: FormulaConfig, context: dict[str, ContextValue] | None, cache_key_id: str
    ) -> EvaluationResult | None:
        """Check if result is cached and return it if found.

        Args:
            config: Formula configuration
            context: Evaluation context
            cache_key_id: Cache key identifier

        Returns:
            Cached result if found, None otherwise
        """
        filtered_context = self.filter_context_for_cache(context)
        # Include formula variables in cache key to distinguish same formula with different variables
        variables = cast(dict[str, str | int | float | None] | None, config.variables if hasattr(config, "variables") else None)
        cached_result = self._cache.get_result(config.formula, filtered_context, cache_key_id, variables)
        if cached_result is not None:
            # Build result using constants
            base_fields = {
                RESULT_KEY_SUCCESS: True,
                RESULT_KEY_VALUE: cached_result,
                RESULT_KEY_CACHED: True,
                RESULT_KEY_STATE: STATE_OK,
            }
            return cast(EvaluationResult, base_fields)
        return None

    def cache_result(
        self, config: FormulaConfig, context: dict[str, ContextValue] | None, cache_key_id: str, result: float
    ) -> None:
        """Cache a formula evaluation result.

        Args:
            config: Formula configuration
            context: Evaluation context
            cache_key_id: Cache key identifier
            result: Result to cache
        """
        filtered_context = self.filter_context_for_cache(context)
        # Include formula variables in cache key to distinguish same formula with different variables
        variables = cast(dict[str, str | int | float | None] | None, config.variables if hasattr(config, "variables") else None)
        self._cache.store_result(config.formula, result, filtered_context, cache_key_id, variables)

    def clear_cache(self, formula_name: str | None = None) -> None:
        """Clear cached results.

        Args:
            formula_name: Optional formula name to clear specific cache,
                         None to clear all caches
        """
        if formula_name:
            self._cache.invalidate_formula(formula_name)
            _LOGGER.debug("Cleared cache for formula: %s", formula_name)
        else:
            self._cache.clear_all()
            _LOGGER.debug("Cleared all formula caches")

    def get_cache_stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            Cache statistics including hit rate, total size, etc.
        """
        stats = self._cache.get_statistics()
        # Convert CacheStatistics to CacheStats format
        return {
            "total_cached_formulas": stats.get("dependency_entries", 0),
            "total_cached_evaluations": stats["total_entries"],
            "valid_cached_evaluations": stats["valid_entries"],
            "error_counts": {},  # Not tracked in current implementation
            "cache_ttl_seconds": stats["ttl_seconds"],
        }

    def filter_context_for_cache(self, context: dict[str, ContextValue] | None) -> dict[str, str | float | int | bool] | None:
        """Filter context to only include cacheable values.

        Args:
            context: Full evaluation context

        Returns:
            Filtered context with only cacheable values
        """
        if not context:
            return None

        filtered = {}
        for key, value in context.items():
            # Skip internal keys that start with underscore
            if key.startswith("_"):
                continue
            # Only cache simple, serializable values
            if isinstance(value, str | int | float | bool):
                filtered[key] = value
            elif isinstance(value, ReferenceValue):
                # Handle ReferenceValue objects by extracting their resolved value
                resolved_value = value.value
                if isinstance(resolved_value, str | int | float | bool):
                    filtered[key] = resolved_value
                    # Note: Cache key now includes entity_id implicitly through the value
                    # Entity ID renames will cause cache misses, which is correct behavior
            elif hasattr(value, "state") and value is not None:
                # Handle Home Assistant State objects
                state_value = value.state
                if isinstance(state_value, str | int | float):
                    filtered[key] = state_value

        return filtered if filtered else None

    def invalidate_cache_for_entity(self, entity_id: str) -> None:
        """Invalidate cache entries that depend on a specific entity.

        Args:
            entity_id: Entity ID that changed
        """
        # This would require the cache to track entity dependencies
        # For now, we'll clear all caches when an entity changes
        # A more sophisticated implementation would track dependencies per cache entry
        self._cache.clear_all()
        _LOGGER.debug("Invalidated all caches due to entity change: %s", entity_id)

    def get_cache_size(self) -> int:
        """Get the current number of cached entries.

        Returns:
            Number of cached entries
        """
        stats = self._cache.get_statistics()
        return stats.get("total_entries", 0)

    def get_cache_hit_rate(self) -> float:
        """Get the cache hit rate.

        Returns:
            Cache hit rate as a percentage (0.0 to 100.0)
        """
        stats = self._cache.get_statistics()
        hits = stats.get("hits", 0)
        total = hits + stats.get("misses", 0)

        if total == 0:
            return 0.0

        return (hits / total) * 100.0

    def start_update_cycle(self) -> None:
        """Start a new evaluation update cycle."""
        self._cache.start_update_cycle()

    def end_update_cycle(self) -> None:
        """End current evaluation update cycle."""
        self._cache.end_update_cycle()
