"""Alternate state type analyzer for early detection in the TypeAnalyzer system."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import ClassVar, cast

from .constants_alternate import ALTERNATE_STATE_NONE, ALTERNATE_STATE_UNAVAILABLE, ALTERNATE_STATE_UNKNOWN
from .constants_types import BuiltinValueType, MetadataDict, OperandType, TypeCategory, UserType


class AlternateStateType:
    """User type representing alternate state values.

    This type wraps alternate state values (None, "unavailable", "unknown", etc.)
    to ensure they are detected early in the TypeAnalyzer priority system.
    """

    def __init__(self, value: OperandType, state_type: str) -> None:
        """Initialize alternate state type.

        Args:
            value: The original alternate state value
            state_type: The normalized state type ("none", "unknown", "unavailable")
        """
        self._value = value
        self._state_type = state_type

    @property
    def value(self) -> OperandType:
        """Get the original value."""
        return self._value

    @property
    def state_type(self) -> str:
        """Get the normalized state type."""
        return self._state_type

    def get_metadata(self) -> MetadataDict:
        """Get metadata for this user type instance."""
        # Adjust dictionary entry types
        return {"alternate_state": True, "state_type": self._state_type, "original_value": cast(str, self._value)}

    def get_type_name(self) -> str:
        """Get the type name for this user type."""
        return "alternate_state"

    def __str__(self) -> str:
        """String representation."""
        return f"AlternateStateType({self._state_type}={self._value})"

    def __repr__(self) -> str:
        """Detailed representation."""
        return f"AlternateStateType(value={self._value!r}, state_type={self._state_type!r})"


class AlternateStateTypeReducer:
    """Reducer for alternate state user types.

    This reducer has the highest priority in the TypeAnalyzer system and
    prevents alternate state values from being converted to numeric.
    """

    def can_reduce_to_numeric(self, value: UserType, metadata: MetadataDict) -> bool:
        """Check if this user type can reduce to numeric.

        Alternate state values should NEVER be reduced to numeric.
        This is the key method that prevents alternate states from being
        processed by downstream numeric conversion logic.
        """
        return False

    def try_reduce_to_numeric(self, value: UserType, metadata: MetadataDict) -> tuple[bool, float]:
        """Try to reduce user type to numeric for formula evaluation.

        For alternate state values, we return False to indicate that
        numeric conversion is not possible. This triggers alternate
        state handling in the evaluation pipeline.
        """
        return False, 0.0

    def reduce_same_type_pair(
        self, _left: UserType, _right: UserType, left_metadata: MetadataDict, right_metadata: MetadataDict
    ) -> tuple[BuiltinValueType, BuiltinValueType, TypeCategory]:
        """Reduce two alternate state values to built-in types.

        For alternate state comparisons, we return the state type strings
        for comparison by the AlternateStateComparisonHandler.
        """
        left_state = left_metadata.get("state_type", ALTERNATE_STATE_UNKNOWN)
        right_state = right_metadata.get("state_type", ALTERNATE_STATE_UNKNOWN)
        # Adjust return types to match expected
        return cast(
            tuple[
                int | float | str | bool | datetime | date | time | tuple[int, ...],
                int | float | str | bool | datetime | date | time | tuple[int, ...],
                TypeCategory,
            ],
            (left_state, right_state, TypeCategory.STRING),
        )

    def reduce_with_builtin_type(
        self,
        _user_value: UserType,
        builtin_value: BuiltinValueType,
        user_metadata: MetadataDict,
        _builtin_type: TypeCategory,
        reverse: bool = False,
    ) -> tuple[BuiltinValueType, BuiltinValueType, TypeCategory]:
        """Reduce alternate state with built-in type.

        When comparing alternate state with non-alternate values,
        we return the state type and the builtin value for comparison.
        """
        state_type = user_metadata.get("state_type", ALTERNATE_STATE_UNKNOWN)

        if reverse:
            return builtin_value, cast(BuiltinValueType, state_type), TypeCategory.STRING
        return cast(BuiltinValueType, state_type), builtin_value, TypeCategory.STRING


class AlternateStateTypeResolver:
    """Resolver for identifying alternate state values.

    This resolver has the highest priority and detects alternate state
    values before any other type analysis occurs.
    """

    # Alternate state string values that should be detected
    ALTERNATE_STATE_STRINGS: ClassVar[set[str]] = {"unavailable", "unknown", "none", "null", "undefined"}

    def can_identify_from_metadata(self, metadata: MetadataDict) -> bool:
        """Check if metadata indicates this user type.

        For alternate states, we don't rely on metadata - we detect
        them directly from the value itself.
        """
        # metadata may contain Any-typed values; coerce to bool for a
        # precise boolean return to satisfy strict mypy rules.
        return bool(metadata.get("alternate_state", False))

    def is_user_type_instance(self, value: OperandType) -> bool:
        """Type guard to check if a value is an instance of this user type.

        This is the CRITICAL method that detects alternate state values
        early in the TypeAnalyzer pipeline.
        """
        return self._is_alternate_state(value)

    def get_type_name(self) -> str:
        """Get the type name this resolver handles."""
        return "alternate_state"

    def _is_alternate_state(self, value: OperandType) -> bool:
        """Check if a value is an alternate state value.

        Detects:
        - Python None
        - String representations: "unavailable", "unknown", "none", "null", "undefined"
        - Case-insensitive matching
        """
        # Python None
        if value is None:
            return True

        # String alternate states (case-insensitive)
        if isinstance(value, str):
            normalized = value.lower().strip()
            return normalized in self.ALTERNATE_STATE_STRINGS

        return False

    def _normalize_alternate_state(self, value: OperandType) -> str:
        """Normalize a value to its alternate state identifier.

        Returns:
            - "none" for Python None
            - "unknown" for unknown state strings
            - "unavailable" for unavailable state strings
        """
        if value is None:
            return ALTERNATE_STATE_NONE

        if isinstance(value, str):
            normalized = value.lower().strip()
            if normalized in {"none", "null"}:
                return ALTERNATE_STATE_NONE
            if normalized in {"unknown", "undefined"}:
                return ALTERNATE_STATE_UNKNOWN
            if normalized == "unavailable":
                return ALTERNATE_STATE_UNAVAILABLE

        return ALTERNATE_STATE_UNKNOWN  # Default fallback

    def create_user_type(self, value: OperandType) -> AlternateStateType:
        """Create an AlternateStateType instance from a value."""
        state_type = self._normalize_alternate_state(value)
        return AlternateStateType(value, state_type)
