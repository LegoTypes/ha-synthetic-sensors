"""Configuration and statistics utilities for the Evaluator class."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from .enhanced_formula_evaluation import EnhancedSimpleEvalHelper
from .evaluator_cache import EvaluatorCache
from .evaluator_config import CircuitBreakerConfig, RetryConfig
from .evaluator_error_handler import EvaluatorErrorHandler
from .type_definitions import CacheStats

_LOGGER = logging.getLogger(__name__)


class EvaluatorConfigUtils:
    """Configuration and statistics utilities for evaluator."""

    def __init__(
        self, circuit_breaker_config: CircuitBreakerConfig | None = None, retry_config: RetryConfig | None = None
    ) -> None:
        """Initialize configuration utilities."""
        self._circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        self._retry_config = retry_config or RetryConfig()

    def get_circuit_breaker_config(self) -> CircuitBreakerConfig:
        """Get current circuit breaker configuration."""
        return self._circuit_breaker_config

    def get_retry_config(self) -> RetryConfig:
        """Get current retry configuration."""
        return self._retry_config

    def update_circuit_breaker_config(self, config: CircuitBreakerConfig) -> None:
        """Update circuit breaker configuration."""
        self._circuit_breaker_config = config
        # Debug logging removed to reduce verbosity

    def update_retry_config(self, config: RetryConfig) -> None:
        """Update retry configuration."""
        self._retry_config = config
        # Debug logging removed to reduce verbosity

    def get_cache_stats(self, cache_handler: EvaluatorCache, error_handler: EvaluatorErrorHandler) -> CacheStats:
        """Get cache statistics."""
        cache_stats = cache_handler.get_cache_stats()
        # Add error counts from the error handler
        cache_stats["error_counts"] = error_handler.get_error_counts()
        return cache_stats

    def clear_compiled_formulas(self, enhanced_helper: EnhancedSimpleEvalHelper) -> None:
        """Clear all compiled formulas from cache.

        This should be called when formulas change or during configuration reload
        to ensure that formula modifications take effect.
        """
        # Clear compiled formulas in enhanced helper (handles all formulas)
        if hasattr(enhanced_helper, "clear_compiled_formulas"):
            enhanced_helper.clear_compiled_formulas()

    def get_compilation_cache_stats(
        self, build_stats_func: Callable[[EnhancedSimpleEvalHelper], dict[str, Any]], enhanced_helper: EnhancedSimpleEvalHelper
    ) -> dict[str, Any]:
        """Get formula compilation cache statistics.

        Returns:
            Dictionary with compilation cache statistics from enhanced helper
        """
        return build_stats_func(enhanced_helper)

    def get_enhanced_evaluation_stats(
        self, get_stats_func: Callable[[EnhancedSimpleEvalHelper], dict[str, Any]], enhanced_helper: EnhancedSimpleEvalHelper
    ) -> dict[str, Any]:
        """Get enhanced evaluation usage statistics.

        Returns:
            Dictionary with enhanced evaluation usage and cache statistics
        """
        return get_stats_func(enhanced_helper)

    def start_update_cycle(self, cache_handler: EvaluatorCache) -> None:
        """Start new evaluation update cycle."""
        cache_handler.start_update_cycle()

    def end_update_cycle(self, cache_handler: EvaluatorCache) -> None:
        """End current evaluation update cycle."""
        cache_handler.end_update_cycle()

    def clear_cache(self, cache_handler: EvaluatorCache, formula_name: str | None = None) -> None:
        """Clear evaluation cache."""
        cache_handler.clear_cache(formula_name)
