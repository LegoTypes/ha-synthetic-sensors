"""Common type definitions and constants used throughout the synthetic sensors package."""

from datetime import date, datetime, time
from enum import Enum
from typing import Union


class TypeCategory(Enum):
    """Type categories for comparison operations."""

    NUMERIC = "numeric"
    STRING = "string"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    VERSION = "version"
    USER_DEFINED = "user_defined"
    UNKNOWN = "unknown"


# Type aliases for cleaner signatures
BuiltinValueType = Union[int, float, str, bool, datetime, date, time, tuple[int, ...]]
MetadataDict = dict[str, Union[str, int, float, bool, None]]

# Builtin type classes for isinstance checks
BUILTIN_VALUE_TYPES = (int, float, str, bool, datetime, date, time)

# Common attribute names for value extraction
VALUE_ATTRIBUTE_NAMES = ("state", "value")

# WFF: Future extension system constants will be defined here
# When YAML-based extension registration is implemented, this will include:
# - Extension handler registry types
# - Handler protocol definitions
# - Extension configuration schemas
