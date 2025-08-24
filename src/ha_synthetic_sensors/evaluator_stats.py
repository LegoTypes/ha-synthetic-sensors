"""Evaluator stats helpers extracted from Evaluator."""

from __future__ import annotations

from typing import Any, cast


def build_compilation_cache_stats(enhanced_helper: Any) -> dict[str, Any]:
    """Aggregate compilation cache stats from enhanced helper.

    Note: NumericHandler has been removed as it duplicated the AST cache functionality
    that EnhancedSimpleEvalHelper already provides.
    """
    stats: dict[str, Any] = {
        "enhanced_helper": {},
        "total_entries": 0,
        "total_hits": 0,
        "total_misses": 0,
        "combined_hit_rate": 0.0,
    }

    if hasattr(enhanced_helper, "get_compilation_cache_stats"):
        enhanced_stats = enhanced_helper.get_compilation_cache_stats()
        stats["enhanced_helper"] = enhanced_stats
        stats["total_entries"] += enhanced_stats.get("total_entries", 0)
        stats["total_hits"] += enhanced_stats.get("hits", 0)
        stats["total_misses"] += enhanced_stats.get("misses", 0)

    total_hits: int = stats["total_hits"]
    total_misses: int = stats["total_misses"]
    total_requests = total_hits + total_misses
    if total_requests > 0:
        stats["combined_hit_rate"] = (total_hits / total_requests) * 100

    return stats


def get_enhanced_evaluation_stats(enhanced_helper: Any) -> dict[str, Any]:
    """Get enhanced evaluation stats in a stable shape."""
    if hasattr(enhanced_helper, "get_enhancement_stats"):
        stats = enhanced_helper.get_enhancement_stats()
        # Ensure a concrete dict[str, Any] is returned
        return cast(dict[str, Any], stats)
    return {
        "enhanced_eval_count": 0,
        "fallback_count": 0,
        "total_evaluations": 0,
        "compilation_cache": {
            "total_entries": 0,
            "hits": 0,
            "misses": 0,
            "hit_rate": 0.0,
            "max_entries": 0,
        },
    }
