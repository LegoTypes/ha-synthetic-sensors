"""Common type definitions and constants used throughout the synthetic sensors package."""

from datetime import date, datetime, time
from enum import Enum
from typing import Protocol, runtime_checkable


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
BuiltinValueType = int | float | str | bool | datetime | date | time | tuple[int, ...]
MetadataDict = dict[str, str | int | float | bool | None]


# === Core Protocols ===


@runtime_checkable
class MetadataProvider(Protocol):
    """Protocol for objects that can provide metadata."""

    def get_metadata(self) -> MetadataDict:
        """Get metadata dictionary from this object."""


@runtime_checkable
class AttributeProvider(Protocol):
    """Protocol for objects with attributes (like HA entities)."""

    @property
    def attributes(self) -> dict[str, str | int | float | bool | None]:
        """Get attributes from this object."""


@runtime_checkable
class MetadataAttributeProvider(Protocol):
    """Protocol for objects with __metadata__ attribute."""

    @property
    def __metadata__(self) -> MetadataDict:
        """Get metadata from __metadata__ attribute."""


@runtime_checkable
class UserType(Protocol):
    """Protocol for user-defined types."""

    def get_metadata(self) -> MetadataDict:
        """Get metadata for this user type instance."""

    def get_type_name(self) -> str:
        """Get the type name for this user type."""


@runtime_checkable
class UserTypeReducer(Protocol):
    """Protocol for user-defined type reducers."""

    def can_reduce_to_numeric(self, value: "UserType", metadata: MetadataDict) -> bool:
        """Check if value can be reduced to numeric type."""

    def try_reduce_to_numeric(self, value: "UserType", metadata: MetadataDict) -> tuple[bool, float]:
        """Try to reduce user type to numeric for formula evaluation."""

    def reduce_same_type_pair(
        self, _left: "UserType", _right: "UserType", left_metadata: MetadataDict, right_metadata: MetadataDict
    ) -> tuple[BuiltinValueType, BuiltinValueType, TypeCategory]:
        """Reduce two values of the same user type to built-in types."""

    def reduce_with_builtin_type(
        self,
        _user_value: "UserType",
        builtin_value: BuiltinValueType,
        user_metadata: MetadataDict,
        _builtin_type: TypeCategory,
        reverse: bool = False,
    ) -> tuple[BuiltinValueType, BuiltinValueType, TypeCategory]:
        """Reduce user-defined value with built-in type."""


# Union type for operands - simplified to avoid redundancy
OperandType = (
    BuiltinValueType
    | UserType  # User-defined types that implement the protocol
    | MetadataProvider  # Objects that provide metadata via method
    | AttributeProvider  # Objects with attributes (HA entities)
    | MetadataAttributeProvider  # Objects with __metadata__
)

# Builtin type classes for isinstance checks
BUILTIN_VALUE_TYPES = (int, float, str, bool, datetime, date, time)

# Common attribute names for value extraction
VALUE_ATTRIBUTE_NAMES = ("state", "value")

# WFF: Future extension system constants will be defined here
# When YAML-based extension registration is implemented, this will include:
# - Extension handler registry types
# - Handler protocol definitions
# - Extension configuration schemas
