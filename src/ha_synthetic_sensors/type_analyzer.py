"""Type analysis utilities with consistent Protocol usage and improved architecture."""

from datetime import date, datetime, time
import re
from typing import Optional, Protocol, Union, cast, runtime_checkable

from .constants_types import BUILTIN_VALUE_TYPES, VALUE_ATTRIBUTE_NAMES, BuiltinValueType, MetadataDict, TypeCategory

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
    def attributes(self) -> dict[str, Union[str, int, float, bool, None]]:
        """Get attributes dictionary."""


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

    def can_reduce_to_numeric(self, value: UserType, metadata: MetadataDict) -> bool:
        """Check if this user type can reduce to numeric."""

    def try_reduce_to_numeric(self, value: UserType, metadata: MetadataDict) -> tuple[bool, float]:
        """Try to reduce user type to numeric for formula evaluation."""

    def reduce_same_type_pair(
        self, left: UserType, right: UserType, _left_metadata: MetadataDict, _right_metadata: MetadataDict
    ) -> "ReducedPairType":
        """Reduce two values of the same user type to built-in types."""

    def reduce_with_builtin_type(
        self,
        user_value: UserType,
        builtin_value: BuiltinValueType,
        _user_metadata: MetadataDict,
        _builtin_type: TypeCategory,
        reverse: bool = False,
    ) -> "ReducedPairType":
        """Reduce user type with built-in type to built-in types."""


@runtime_checkable
class UserTypeResolver(Protocol):
    """Protocol for identifying user types from metadata."""

    def can_identify_from_metadata(self, metadata: MetadataDict) -> bool:
        """Check if metadata indicates this user type."""

    def is_user_type_instance(self, value: "OperandType") -> bool:
        """Type guard to check if a value is an instance of this user type."""

    def get_type_name(self) -> str:
        """Get the type name this resolver handles."""


# === Type Definitions ===

# Union type for operands - simplified to avoid redundancy
OperandType = Union[
    BuiltinValueType,  # Built-in types (int, float, str, bool, datetime, etc.)
    UserType,  # User-defined types that implement the protocol
    MetadataProvider,  # Objects that provide metadata via method
    AttributeProvider,  # Objects with attributes (HA entities)
    MetadataAttributeProvider,  # Objects with __metadata__
]

# Type for reduced pairs
ReducedPairType = tuple[BuiltinValueType, BuiltinValueType, TypeCategory]


# === Data Classes ===


class UserTypeIdentification:
    """Result of user type identification from metadata."""

    def __init__(self, type_name: str, metadata: MetadataDict, resolver: UserTypeResolver) -> None:
        self.type_name = type_name
        self.metadata = metadata
        self.resolver = resolver


# === Utility Classes ===


class MetadataExtractor:
    """Handles metadata extraction from various object types."""

    @staticmethod
    def extract_all_metadata(value: OperandType) -> MetadataDict:
        """Extract metadata to determine if user extensions should handle this operand type.

        Metadata is used solely for extension selection:
        - If YAML configures user extensions for these operand types → user extension runs first
        - If no user extensions configured → built-in comparison runs directly

        Built-in comparisons operate directly on operands without requiring metadata.
        """
        metadata: MetadataDict = {}

        # Check if it's a UserType (highest priority)
        if isinstance(value, UserType):
            metadata.update(value.get_metadata())
            metadata["type"] = value.get_type_name()
            return metadata

        # Skip metadata extraction for basic built-in types
        if isinstance(value, (*BUILTIN_VALUE_TYPES, tuple, type(None))):
            return metadata

        # WFF: Future user extension support
        # When user extension registration system is implemented, this method will
        # check if a registered handler should process these operand types.
        # The handler would preprocess operands and return native types for standard comparison.
        #
        # For now, no extension registration exists, so no handlers available.

        return metadata

    # WFF: Future user extension handler extraction
    # @staticmethod
    # def _extract_handler_from_metadata(operand_types: tuple, metadata: MetadataDict) -> ComparisonHandler | None:
    #     """Extract registered handler for these operand types based on metadata.
    #
    #     When extension registration system exists, this will:
    #     1. Check if YAML defines a handler for these operand type combinations
    #     2. Return the registered handler that implements the comparison protocol
    #     3. Handler will preprocess operands and return native types for standard comparison
    #
    #     Returns None when no handler is registered (standard comparison proceeds).
    #     """
    #     return None  # No registration system implemented yet


class ValueExtractor:
    """Handles value extraction from complex objects."""

    @staticmethod
    def extract_comparable_value(obj: OperandType) -> Union[BuiltinValueType, None]:
        """Extract a comparable value from an object."""
        # Handle None
        if obj is None:
            return None

        # Handle built-in types directly
        if isinstance(obj, BUILTIN_VALUE_TYPES):
            return obj

        # Handle objects with extractable values (e.g., HA entity-like objects)
        for attr_name in VALUE_ATTRIBUTE_NAMES:
            if hasattr(obj, attr_name):
                attr_value = getattr(obj, attr_name)
                if attr_value is not None and isinstance(attr_value, BUILTIN_VALUE_TYPES):
                    return cast(BuiltinValueType, attr_value)

        # No extractable comparable value found
        return None


class NumericParser:
    """Handles numeric parsing and conversion."""

    @staticmethod
    def try_parse_numeric(value: OperandType) -> Optional[Union[int, float]]:
        """Try to parse a value as numeric."""
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            # Remove common non-numeric suffixes/prefixes
            cleaned = re.sub(r"[^\d.-]", "", value)
            if cleaned:
                try:
                    if "." in cleaned:
                        return float(cleaned)
                    return int(cleaned)
                except ValueError:
                    pass
        return None

    @staticmethod
    def try_reduce_to_numeric(value: OperandType) -> tuple[bool, float]:
        """Try to reduce a value to numeric (float).

        Args:
            value: Value to reduce

        Returns:
            Tuple of (success: bool, numeric_value: float)
        """
        # Already numeric
        if isinstance(value, (int, float)):
            return True, float(value)

        # Boolean to numeric (formula-friendly: True=1.0, False=0.0)
        if isinstance(value, bool):
            return True, float(value)

        # String to numeric (common in formula inputs)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return False, 0.0

            try:
                # Handle scientific notation, integers, floats
                return True, float(value)
            except ValueError:
                return False, 0.0

        # Cannot reduce other types to numeric
        return False, 0.0


class DateTimeParser:
    """Handles datetime parsing and conversion."""

    @staticmethod
    def parse_datetime(value: OperandType) -> Optional[datetime]:
        """Try to parse a value as datetime."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time.min)
        if isinstance(value, str):
            # Try common datetime formats
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
            # Try ISO format
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
        return None

    @staticmethod
    def try_reduce_to_datetime(value: OperandType) -> tuple[bool, datetime]:
        """Try to reduce a value to datetime."""
        # Already datetime
        if isinstance(value, datetime):
            return True, value

        # String to datetime
        if isinstance(value, str):
            try:
                # Handle common ISO formats
                test_value = value.replace("Z", "+00:00")
                dt = datetime.fromisoformat(test_value)
                return True, dt
            except ValueError:
                return False, datetime.min

        # Cannot reduce other types to datetime
        return False, datetime.min


class VersionParser:
    """Handles version parsing and conversion."""

    @staticmethod
    def try_reduce_to_version(value: OperandType) -> tuple[bool, tuple[int, ...]]:
        """Try to reduce a value to version tuple."""
        if isinstance(value, str):
            try:
                # Remove 'v' prefix if present
                clean_version = value.lower().lstrip("v")

                # Extract numeric parts
                parts = re.findall(r"\d+", clean_version)
                if not parts:
                    return False, ()

                return True, tuple(int(part) for part in parts)
            except ValueError:
                return False, ()

        # Cannot reduce other types to version
        return False, ()


class StringCategorizer:
    """Handles string type categorization."""

    @staticmethod
    def categorize_string(value: str) -> TypeCategory:
        """Categorize string types with conflict resolution."""
        # Default to string category
        category = TypeCategory.STRING

        if not value:  # Empty string
            return category

        # Test for datetime first (more specific pattern)
        is_datetime = StringCategorizer._is_datetime_string(value)
        is_version = StringCategorizer._is_version_string(value)

        # Handle conflicts: A string that matches both patterns
        if is_datetime and is_version:
            # Prioritize datetime over version for ambiguous cases
            if StringCategorizer._is_strict_datetime_string(value):
                category = TypeCategory.DATETIME
            elif StringCategorizer._is_strict_version_string(value):
                category = TypeCategory.VERSION
        elif is_datetime:
            category = TypeCategory.DATETIME
        elif is_version:
            category = TypeCategory.VERSION

        return category

    @staticmethod
    def _is_datetime_string(value: str) -> bool:
        """Check if string represents a datetime (permissive)."""
        try:
            # Handle common ISO formats
            test_value = value.replace("Z", "+00:00")
            datetime.fromisoformat(test_value)
            return True
        except ValueError:
            return False

    @staticmethod
    def _is_strict_datetime_string(value: str) -> bool:
        """Check if string is definitely a datetime (strict validation)."""
        datetime_pattern = (
            r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:[T\s]\d{1,2}:\d{1,2}(?::\d{1,2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
        )
        return bool(re.match(datetime_pattern, value))

    @staticmethod
    def _is_version_string(value: str) -> bool:
        """Check if string represents a semantic version (permissive)."""
        return bool(re.match(r"^v?\d+\.\d+(?:\.\d+)?", value))

    @staticmethod
    def _is_strict_version_string(value: str) -> bool:
        """Check if string is definitely a version (strict validation)."""
        strict_pattern = r"^v?\d+\.\d+\.\d+(?:[-+].+)?$"
        return bool(re.match(strict_pattern, value))


# === Management Classes ===


class UserTypeManager:
    """Manages user type registration and resolution."""

    def __init__(self) -> None:
        self.metadata_resolver = MetadataTypeResolver()
        self._user_type_reducers: dict[str, UserTypeReducer] = {}

    def register_user_type_reducer(self, type_name: str, reducer: UserTypeReducer) -> None:
        """Register a user-defined type reducer."""
        self._user_type_reducers[type_name] = reducer

    def register_user_type_resolver(self, type_name: str, resolver: UserTypeResolver) -> None:
        """Register a user-defined type resolver."""
        self.metadata_resolver.register_user_type_resolver(type_name, resolver)

    def get_reducer(self, type_name: str) -> Optional[UserTypeReducer]:
        """Get reducer for a type name."""
        return self._user_type_reducers.get(type_name)

    def identify_user_type(self, value: OperandType) -> Optional[UserTypeIdentification]:
        """Identify user type from metadata."""
        return self.metadata_resolver.identify_type_from_metadata(value)


class MetadataTypeResolver:
    """Resolves types based on metadata before built-in type detection."""

    def __init__(self) -> None:
        self._user_type_resolvers: dict[str, UserTypeResolver] = {}

    def register_user_type_resolver(self, type_name: str, resolver: UserTypeResolver) -> None:
        """Register a user-defined type resolver."""
        self._user_type_resolvers[type_name] = resolver

    def identify_type_from_metadata(self, value: OperandType) -> Optional[UserTypeIdentification]:
        """Identify user-defined type from metadata."""
        metadata = MetadataExtractor.extract_all_metadata(value)

        if not metadata:
            return None

        # Check for explicit type declaration
        declared_type = metadata.get("type")
        if declared_type and isinstance(declared_type, str) and declared_type in self._user_type_resolvers:
            resolver = self._user_type_resolvers[declared_type]
            if resolver.is_user_type_instance(value):
                return UserTypeIdentification(type_name=declared_type, metadata=metadata, resolver=resolver)

        # Check for implicit type identification
        for type_name, resolver in self._user_type_resolvers.items():
            if resolver.can_identify_from_metadata(metadata) and resolver.is_user_type_instance(value):
                return UserTypeIdentification(type_name=type_name, metadata=metadata, resolver=resolver)

        return None


# === Main Type System Classes ===


class TypeReducer:
    """Reduces values to the most appropriate type for formula-based evaluation."""

    def __init__(self, user_type_manager: Optional[UserTypeManager] = None) -> None:
        self.user_type_manager = user_type_manager or UserTypeManager()

    def register_user_type_reducer(self, type_name: str, reducer: UserTypeReducer) -> None:
        """Register a user-defined type reducer."""
        self.user_type_manager.register_user_type_reducer(type_name, reducer)

    def register_user_type_resolver(self, type_name: str, resolver: UserTypeResolver) -> None:
        """Register a user-defined type resolver."""
        self.user_type_manager.register_user_type_resolver(type_name, resolver)

    def can_reduce_to_numeric(self, value: OperandType) -> bool:
        """Check if a value can be reduced to numeric for formula evaluation."""
        # Check for user types first
        user_type = self.user_type_manager.identify_user_type(value)
        if user_type:
            reducer = self.user_type_manager.get_reducer(user_type.type_name)
            if reducer and isinstance(value, UserType):
                return reducer.can_reduce_to_numeric(value, user_type.metadata)

        # Check built-in types
        extracted = ValueExtractor.extract_comparable_value(value)
        if isinstance(extracted, (int, float, bool)):
            return True
        if isinstance(extracted, str):
            return NumericParser.try_parse_numeric(extracted) is not None
        return False

    def try_reduce_to_numeric(self, value: OperandType) -> tuple[bool, float]:
        """Try to reduce a value to numeric for formula evaluation."""
        # Check for user types first
        user_type = self.user_type_manager.identify_user_type(value)
        if user_type:
            reducer = self.user_type_manager.get_reducer(user_type.type_name)
            if reducer and isinstance(value, UserType):
                return reducer.try_reduce_to_numeric(value, user_type.metadata)

        # Handle built-in types using centralized logic
        return NumericParser.try_reduce_to_numeric(value)

    def reduce_pair_for_comparison(self, left: OperandType, right: OperandType) -> ReducedPairType:
        """Reduce a pair of values to the best common type for comparison."""
        # Check for user types
        left_user_type = self.user_type_manager.identify_user_type(left)
        right_user_type = self.user_type_manager.identify_user_type(right)

        # If either is a user type, delegate to user type reduction
        if left_user_type or right_user_type:
            return self._reduce_with_user_types(left, right, left_user_type, right_user_type)

        # Both are built-in types
        return self._reduce_builtin_pair(left, right)

    def _reduce_with_user_types(
        self,
        left: OperandType,
        right: OperandType,
        left_user_type: Optional[UserTypeIdentification],
        right_user_type: Optional[UserTypeIdentification],
    ) -> ReducedPairType:
        """Handle reduction when user types are involved."""
        # Both are user types
        if left_user_type and right_user_type:
            return self._reduce_user_type_pair(left, right, left_user_type, right_user_type)

        # One user type, one built-in
        if left_user_type:
            return self._reduce_user_with_builtin(left, right, left_user_type, reverse=False)

        if right_user_type:
            return self._reduce_user_with_builtin(right, left, right_user_type, reverse=True)

        # Should not reach here
        return (str(left), str(right), TypeCategory.STRING)

    def _reduce_user_type_pair(
        self,
        left: OperandType,
        right: OperandType,
        left_user_type: UserTypeIdentification,
        right_user_type: UserTypeIdentification,
    ) -> ReducedPairType:
        """Reduce two user types."""
        if left_user_type.type_name == right_user_type.type_name:
            # Same user type - delegate to specialized reducer
            reducer = self.user_type_manager.get_reducer(left_user_type.type_name)
            if reducer and isinstance(left, UserType) and isinstance(right, UserType):
                return reducer.reduce_same_type_pair(left, right, left_user_type.metadata, right_user_type.metadata)

        # Different user types or no reducer - convert to strings
        return (str(left), str(right), TypeCategory.STRING)

    def _reduce_user_with_builtin(
        self, user_value: OperandType, builtin_value: OperandType, user_type: UserTypeIdentification, reverse: bool
    ) -> ReducedPairType:
        """Reduce user type with built-in type."""
        builtin_type_category = self._classify_builtin_type(builtin_value)
        reducer = self.user_type_manager.get_reducer(user_type.type_name)

        if reducer and isinstance(user_value, UserType):
            extracted_builtin = ValueExtractor.extract_comparable_value(builtin_value)
            if extracted_builtin is not None:
                return reducer.reduce_with_builtin_type(
                    user_value, extracted_builtin, user_type.metadata, builtin_type_category, reverse=reverse
                )

        # Fallback
        return (str(user_value), str(builtin_value), TypeCategory.STRING)

    def _reduce_builtin_pair(self, left: OperandType, right: OperandType) -> ReducedPairType:
        """Reduce two built-in type values to a common type."""
        # Strategy 1: Try numeric reduction (formula-friendly priority)
        left_numeric_ok, left_numeric = NumericParser.try_reduce_to_numeric(left)
        right_numeric_ok, right_numeric = NumericParser.try_reduce_to_numeric(right)

        if left_numeric_ok and right_numeric_ok:
            return left_numeric, right_numeric, TypeCategory.NUMERIC

        # Strategy 2: Try datetime reduction
        left_dt_ok, left_dt = DateTimeParser.try_reduce_to_datetime(left)
        right_dt_ok, right_dt = DateTimeParser.try_reduce_to_datetime(right)

        if left_dt_ok and right_dt_ok:
            return left_dt, right_dt, TypeCategory.DATETIME

        # Strategy 3: Try version reduction
        left_ver_ok, left_ver = VersionParser.try_reduce_to_version(left)
        right_ver_ok, right_ver = VersionParser.try_reduce_to_version(right)

        if left_ver_ok and right_ver_ok:
            return left_ver, right_ver, TypeCategory.VERSION

        # Strategy 4: String fallback
        return str(left), str(right), TypeCategory.STRING

    @staticmethod
    def _classify_builtin_type(value: OperandType) -> TypeCategory:
        """Classify a built-in type."""
        if isinstance(value, bool):
            return TypeCategory.BOOLEAN
        if isinstance(value, (int, float)):
            return TypeCategory.NUMERIC
        if isinstance(value, (datetime, date, time)):
            return TypeCategory.DATETIME
        return TypeCategory.STRING


# === Type Analyzer Class ===


class TypeAnalyzer:
    """Main type analysis class that coordinates type reduction and comparison."""

    def __init__(self) -> None:
        self.type_reducer = TypeReducer()

    def register_user_type_reducer(self, type_name: str, reducer: UserTypeReducer) -> None:
        """Register a user-defined type reducer."""
        self.type_reducer.register_user_type_reducer(type_name, reducer)

    def register_user_type_resolver(self, type_name: str, resolver: UserTypeResolver) -> None:
        """Register a user-defined type resolver."""
        self.type_reducer.register_user_type_resolver(type_name, resolver)

    def reduce_for_comparison(self, left: OperandType, right: OperandType) -> ReducedPairType:
        """Reduce two values for comparison operations."""
        return self.type_reducer.reduce_pair_for_comparison(left, right)

    def can_reduce_to_numeric(self, value: OperandType) -> bool:
        """Check if a value can be reduced to numeric for formula evaluation."""
        return self.type_reducer.can_reduce_to_numeric(value)

    def try_reduce_to_numeric(self, value: OperandType) -> tuple[bool, float]:
        """Try to reduce a value to numeric for formula evaluation."""
        return self.type_reducer.try_reduce_to_numeric(value)

    @staticmethod
    def categorize_type(value: OperandType) -> TypeCategory:
        """Determine the primary type category for a value."""
        # Handle None values explicitly
        if value is None:
            raise ValueError("Cannot categorize None values for comparison")

        # Check for user-defined types first
        if isinstance(value, UserType):
            return TypeCategory.USER_DEFINED

        # Check bool before int (bool is subclass of int in Python)
        if isinstance(value, bool):
            return TypeCategory.BOOLEAN
        if isinstance(value, (int, float)):
            return TypeCategory.NUMERIC
        if isinstance(value, str):
            return StringCategorizer.categorize_string(value)
        if isinstance(value, (datetime, date, time)):
            return TypeCategory.DATETIME
        return TypeCategory.UNKNOWN
