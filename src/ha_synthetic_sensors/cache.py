"""Optimized caching system for formula evaluation results.

This module provides an efficient caching layer that separates caching concerns
from evaluation logic, improving maintainability and performance.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, TypedDict

_LOGGER = logging.getLogger(__name__)


class CacheEntry(TypedDict):
    """Single cache entry with metadata."""

    value: Any
    timestamp: datetime
    hit_count: int
    formula_hash: str


@dataclass
class CacheConfig:
    """Configuration for cache behavior."""

    ttl_seconds: float = 30.0
    max_entries: int = 1000
    enable_metrics: bool = True


class FormulaCache:
    """High-performance cache for formula evaluation results."""

    def __init__(self, config: CacheConfig | None = None):
        """Initialize the cache with configuration.

        Args:
            config: Cache configuration, uses defaults if None
        """
        self._config = config or CacheConfig()
        self._cache: dict[str, CacheEntry] = {}
        self._dependency_cache: dict[str, set[str]] = {}

        # Performance metrics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get_result(
        self,
        formula: str,
        context: dict[str, Any] | None = None,
        formula_id: str | None = None,
    ) -> Any | None:
        """Get cached result if valid.

        Args:
            formula: Formula string
            context: Evaluation context
            formula_id: Optional formula identifier for better cache keys

        Returns:
            Cached result if valid, None otherwise
        """
        cache_key = self._generate_cache_key(formula, context, formula_id)

        if cache_key not in self._cache:
            self._misses += 1
            return None

        entry = self._cache[cache_key]

        # Check if entry is still valid
        if self._is_entry_expired(entry):
            del self._cache[cache_key]
            self._misses += 1
            return None

        # Update hit count and return value
        entry["hit_count"] += 1
        self._hits += 1
        return entry["value"]

    def store_result(
        self,
        formula: str,
        result: Any,
        context: dict[str, Any] | None = None,
        formula_id: str | None = None,
    ) -> None:
        """Store evaluation result in cache.

        Args:
            formula: Formula string
            result: Evaluation result
            context: Evaluation context
            formula_id: Optional formula identifier
        """
        # Ensure we don't exceed max entries
        self._evict_if_needed()

        cache_key = self._generate_cache_key(formula, context, formula_id)
        formula_hash = self._hash_formula(formula)

        self._cache[cache_key] = {
            "value": result,
            "timestamp": datetime.now(),
            "hit_count": 0,
            "formula_hash": formula_hash,
        }

    def store_dependencies(self, formula: str, dependencies: set[str]) -> None:
        """Store formula dependencies in cache.

        Args:
            formula: Formula string
            dependencies: Set of dependency names
        """
        formula_hash = self._hash_formula(formula)
        self._dependency_cache[formula_hash] = dependencies.copy()

    def get_dependencies(self, formula: str) -> set[str] | None:
        """Get cached dependencies for formula.

        Args:
            formula: Formula string

        Returns:
            Set of dependencies if cached, None otherwise
        """
        formula_hash = self._hash_formula(formula)
        return self._dependency_cache.get(formula_hash)

    def invalidate_formula(self, formula: str) -> None:
        """Invalidate all cache entries for a specific formula.

        Args:
            formula: Formula string to invalidate
        """
        formula_hash = self._hash_formula(formula)

        # Remove evaluation results
        keys_to_remove = [
            key
            for key, entry in self._cache.items()
            if entry["formula_hash"] == formula_hash
        ]

        for key in keys_to_remove:
            del self._cache[key]

        # Remove dependencies
        self._dependency_cache.pop(formula_hash, None)

    def clear_all(self) -> None:
        """Clear all cached data."""
        self._cache.clear()
        self._dependency_cache.clear()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get_statistics(self) -> dict[str, Any]:
        """Get cache performance statistics.

        Returns:
            Dictionary with cache metrics
        """
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests) if total_requests > 0 else 0.0

        now = datetime.now()
        valid_entries = sum(
            1
            for entry in self._cache.values()
            if not self._is_entry_expired(entry, now)
        )

        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "dependency_entries": len(self._dependency_cache),
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate": hit_rate,
            "ttl_seconds": self._config.ttl_seconds,
            "max_entries": self._config.max_entries,
        }

    def _generate_cache_key(
        self,
        formula: str,
        context: dict[str, Any] | None,
        formula_id: str | None,
    ) -> str:
        """Generate optimized cache key.

        Args:
            formula: Formula string
            context: Evaluation context
            formula_id: Optional formula identifier

        Returns:
            Cache key string
        """
        # Use formula_id if available for better key readability
        base_key = formula_id or self._hash_formula(formula)

        if not context:
            return base_key

        # Create stable context hash
        context_items = sorted(context.items())
        context_str = "&".join(f"{k}={v}" for k, v in context_items)
        context_hash = hashlib.md5(
            context_str.encode(), usedforsecurity=False
        ).hexdigest()[:8]

        return f"{base_key}:{context_hash}"

    def _hash_formula(self, formula: str) -> str:
        """Create consistent hash for formula.

        Args:
            formula: Formula string

        Returns:
            Hash string
        """
        return hashlib.md5(formula.encode(), usedforsecurity=False).hexdigest()[:12]

    def _is_entry_expired(
        self,
        entry: CacheEntry,
        now: datetime | None = None,
    ) -> bool:
        """Check if cache entry has expired.

        Args:
            entry: Cache entry to check
            now: Current time (defaults to datetime.now())

        Returns:
            True if entry is expired
        """
        if now is None:
            now = datetime.now()

        ttl = timedelta(seconds=self._config.ttl_seconds)
        return now - entry["timestamp"] > ttl

    def _evict_if_needed(self) -> None:
        """Evict entries if cache is at capacity."""
        if len(self._cache) < self._config.max_entries:
            return

        # Simple LRU eviction: remove oldest entries
        now = datetime.now()

        # First, remove any expired entries
        expired_keys = [
            key
            for key, entry in self._cache.items()
            if self._is_entry_expired(entry, now)
        ]

        for key in expired_keys:
            del self._cache[key]
            self._evictions += 1

        # If still at capacity, remove least recently used
        if len(self._cache) >= self._config.max_entries:
            # Sort by timestamp (oldest first)
            sorted_entries = sorted(
                self._cache.items(), key=lambda x: x[1]["timestamp"]
            )

            # Remove the oldest 10% of entries
            num_to_remove = max(1, len(sorted_entries) // 10)
            for key, _ in sorted_entries[:num_to_remove]:
                del self._cache[key]
                self._evictions += 1
