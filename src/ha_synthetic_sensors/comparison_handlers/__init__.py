"""Comparison handlers package for extensible comparison operations."""

# Handler classes (for extension)
from .base_handler import BaseComparisonHandler, ComparisonHandler

# Main API
from .comparison_factory import ComparisonFactory, compare_values, get_comparison_factory, register_user_comparison_handler

# Protocols for extensibility
from .comparison_protocol import ComparisonCapable, ComparisonTypeInfo, UserComparisonType
from .extensible_registry import ExtensibleComparisonRegistry, get_extensible_registry, register_user_comparison_type
from .handler_boolean import BooleanComparisonHandler
from .handler_datetime import DateTimeComparisonHandler
from .handler_numeric import NumericComparisonHandler
from .handler_string import StringComparisonHandler
from .handler_version import VersionComparisonHandler

__all__ = [
    # Handler classes for extension
    "BaseComparisonHandler",
    "BooleanComparisonHandler",
    "ComparisonCapable",
    "ComparisonFactory",
    "ComparisonHandler",
    "ComparisonTypeInfo",
    "DateTimeComparisonHandler",
    "ExtensibleComparisonRegistry",
    "NumericComparisonHandler",
    "StringComparisonHandler",
    "UserComparisonType",
    "VersionComparisonHandler",
    # Main API
    "compare_values",
    "get_comparison_factory",
    "get_extensible_registry",
    "register_user_comparison_handler",
    "register_user_comparison_type",
]
