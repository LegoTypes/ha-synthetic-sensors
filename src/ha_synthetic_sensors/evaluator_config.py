"""
Configuration classes for the formula evaluator.

This module contains configuration dataclasses for circuit breaker and retry logic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CircuitBreakerConfig:
    """Configuration for the two-tier circuit breaker pattern."""

    # TIER 1: Fatal Error Circuit Breaker
    max_fatal_errors: int = 5  # Stop trying after this many fatal errors

    # TIER 2: Transitory Error Handling
    max_transitory_errors: int = 20  # Track but don't stop on transitory errors
    track_transitory_errors: bool = True  # Whether to track transitory errors

    # Error Reset Behavior
    reset_on_success: bool = True  # Reset counters on successful evaluation


@dataclass
class RetryConfig:
    """Configuration for handling unavailable dependencies and retry logic."""

    enabled: bool = True
    max_attempts: int = 3
    backoff_seconds: float = 5.0
    exponential_backoff: bool = True
    retry_on_unknown: bool = True
    retry_on_unavailable: bool = True
