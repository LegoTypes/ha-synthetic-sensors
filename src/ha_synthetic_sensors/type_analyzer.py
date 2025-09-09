"""Type analysis utilities with consistent Protocol usage and improved architecture."""

from datetime import date, datetime, time
from typing import Protocol, cast, runtime_checkable

from .alternate_state_type_analyzer import AlternateStateTypeReducer, AlternateStateTypeResolver
from .constants_types import (
    BUILTIN_VALUE_TYPES,
    VALUE_ATTRIBUTE_NAMES,
    AttributeProvider,
    BuiltinValueType,
    MetadataAttributeProvider,
    MetadataDict,
    MetadataProvider,
    OperandType,
    TypeCategory,
    UserType,
    UserTypeReducer,
)
from .datetime_functions.duration_functions import Duration
from .regex_helper import (
    extract_numeric_parts_advanced,
    extract_version_numeric_parts,
    is_strict_datetime_string,
    is_strict_version_string,
)

__all__ = [
    "AttributeProvider",
    "BuiltinValueType",
    "MetadataAttributeProvider",
    "MetadataDict",
    "MetadataProvider",
    "OperandType",
    "StringCategorizer",
    "TypeAnalyzer",
    "TypeCategory",
    "UserType",
    "UserTypeReducer",
    "UserTypeResolver",
]

# === Extended Protocols (not in constants_types.py to avoid circular imports) ===


@runtime_checkable
class UserTypeResolver(Protocol):
    """Protocol for identifying user types from metadata."""

    def can_identify_from_metadata(self, metadata: MetadataDict) -> bool:
        """Check if metadata indicates this user type."""

    def is_user_type_instance(self, value: OperandType) -> bool:
        """Type guard to check if a value is an instance of this user type."""

    def get_type_name(self) -> str:
        """Get the type name this resolver handles."""


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
    def extract_comparable_value(obj: OperandType) -> BuiltinValueType | None:
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
    def try_parse_numeric(value: OperandType) -> int | float | None:
        """Try to parse a value as numeric."""
        if isinstance(value, int | float):
            return value
        if isinstance(value, str):
            # Remove common non-numeric suffixes/prefixes

            cleaned = extract_numeric_parts_advanced(value)
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
        # Use a conversion chain to reduce return statements
        result = NumericParser._convert_by_type(value)
        return result

    @staticmethod
    def _convert_by_type(value: OperandType) -> tuple[bool, float]:
        """Convert value to numeric based on type, using structured approach."""
        # Check in order of likelihood/priority
        converters = [
            NumericParser._convert_numeric,
            NumericParser._convert_boolean,
            NumericParser._convert_duration,
            NumericParser._convert_string,
        ]

        for converter in converters:
            success, result = converter(value)
            if success is not None:  # Converter handled this type
                return success, result

        # No converter could handle this type
        return False, 0.0

    @staticmethod
    def _convert_numeric(value: OperandType) -> tuple[bool | None, float]:
        """Convert numeric types. Returns (None, 0.0) if not applicable."""
        if isinstance(value, int | float):
            return True, float(value)
        return None, 0.0

    @staticmethod
    def _convert_boolean(value: OperandType) -> tuple[bool | None, float]:
        """Convert boolean types. Returns (None, 0.0) if not applicable."""
        if isinstance(value, bool):
            return True, float(value)
        return None, 0.0

    @staticmethod
    def _convert_duration(value: OperandType) -> tuple[bool | None, float]:
        """Convert duration types. Returns (None, 0.0) if not applicable."""
        if isinstance(value, Duration):
            # For dimensionless durations (ratios), return the numeric value
            if value.unit == "dimensionless":
                return True, float(value.value)
            # For other durations, return False to indicate they should remain as Duration objects
            return False, 0.0
        return None, 0.0

    @staticmethod
    def _convert_string(value: OperandType) -> tuple[bool | None, float]:
        """Convert string types. Returns (None, 0.0) if not applicable."""
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return False, 0.0

            try:
                # Handle scientific notation, integers, floats
                return True, float(value)
            except ValueError:
                return False, 0.0
        return None, 0.0


class DateTimeParser:
    """Handles datetime parsing and conversion."""

    @staticmethod
    def normalize_iso_timezone(value: str) -> str:
        """Normalize ISO datetime string by replacing Z with +00:00."""
        return value.replace("Z", "+00:00")

    @staticmethod
    def parse_datetime(value: OperandType) -> datetime | None:
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
            # Try ISO format with timezone normalization
            try:
                normalized_value = DateTimeParser.normalize_iso_timezone(value)
                return datetime.fromisoformat(normalized_value)
            except ValueError:
                pass
        return None

    @staticmethod
    def try_reduce_to_datetime(value: OperandType) -> tuple[bool, datetime]:
        """Try to reduce a value to datetime."""
        # Already datetime
        if isinstance(value, datetime):
            return True, value

        # Numeric timestamp
        if isinstance(value, int | float):
            try:
                return True, datetime.fromtimestamp(value)
            except (ValueError, OSError):
                return False, datetime.min

        # String to datetime
        if isinstance(value, str):
            try:
                # Handle common ISO formats with timezone normalization
                normalized_value = DateTimeParser.normalize_iso_timezone(value)
                dt = datetime.fromisoformat(normalized_value)
                return True, dt
            except ValueError:
                return False, datetime.min

        # Cannot reduce other types to datetime
        return False, datetime.min

    @staticmethod
    def try_reduce_to_date_string(value: OperandType) -> tuple[bool, str]:
        """Try to reduce a value to ISO date string (date-only, no time)."""
        try:
            # Handle datetime objects
            if isinstance(value, datetime):
                return True, value.date().isoformat()

            if isinstance(value, date):
                return True, value.isoformat()

            # Handle numeric timestamps
            if isinstance(value, int | float):
                dt = datetime.fromtimestamp(value)
                return True, dt.date().isoformat()

            # Handle string values
            if isinstance(value, str):
                # Check if it contains time information
                if "T" in value or " " in value:
                    # Full datetime - convert to date only
                    normalized_value = DateTimeParser.normalize_iso_timezone(value)
                    dt = datetime.fromisoformat(normalized_value)
                    return True, dt.date().isoformat()
                # Validate as date-only and return as-is
                datetime.fromisoformat(value)  # Validation
                return True, value

        except (ValueError, OSError):
            pass

        # Cannot convert other types or conversion failed
        return False, ""

    @staticmethod
    def convert_datetime_to_date_string(datetime_string: str) -> str:
        """Convert a datetime string to date-only string, handling timezone normalization.

        This is a convenience method for the common pattern of converting datetime
        function results (which return full datetimes) to date-only strings.
        """
        if "T" in datetime_string:
            normalized_value = DateTimeParser.normalize_iso_timezone(datetime_string)
            dt = datetime.fromisoformat(normalized_value)
            return dt.date().isoformat()
        return datetime_string


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

                parts = extract_version_numeric_parts(clean_version)
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
        """Categorize string types."""
        # Default to string category
        category = TypeCategory.STRING

        if not value:  # Empty string
            return category

        # Test for datetime first (more specific pattern)
        is_datetime = StringCategorizer._is_datetime_string(value)
        is_version = StringCategorizer._is_version_string(value)

        # No ambiguity between datetime and version patterns
        if is_datetime:
            category = TypeCategory.DATETIME
        elif is_version:
            category = TypeCategory.VERSION

        return category

    @staticmethod
    def _is_datetime_string(value: str) -> bool:
        """Check if string represents a datetime (permissive)."""
        try:
            # Use centralized timezone normalization
            normalized_value = DateTimeParser.normalize_iso_timezone(value)
            datetime.fromisoformat(normalized_value)
            return True
        except ValueError:
            return False

    @staticmethod
    def _is_strict_datetime_string(value: str) -> bool:
        """Check if string is definitely a datetime (strict validation)."""

        return is_strict_datetime_string(value)

    @staticmethod
    def _is_version_string(value: str) -> bool:
        """Check if string is definitely a version (requires 'v' prefix)."""

        return is_strict_version_string(value)


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

    def get_reducer(self, type_name: str) -> UserTypeReducer | None:
        """Get reducer for a type name."""
        return self._user_type_reducers.get(type_name)

    def identify_user_type(self, value: OperandType) -> UserTypeIdentification | None:
        """Identify user type from metadata."""
        return self.metadata_resolver.identify_type_from_metadata(value)


class MetadataTypeResolver:
    """Resolves types based on metadata before built-in type detection."""

    def __init__(self) -> None:
        self._user_type_resolvers: dict[str, UserTypeResolver] = {}

    def register_user_type_resolver(self, type_name: str, resolver: UserTypeResolver) -> None:
        """Register a user-defined type resolver."""
        self._user_type_resolvers[type_name] = resolver

    def identify_type_from_metadata(self, value: OperandType) -> UserTypeIdentification | None:
        """Identify user-defined type from metadata."""
        # PRIORITY CHECK: Check high-priority resolvers directly (e.g., alternate states)
        # This allows detection of values like None, "unavailable" without requiring metadata
        high_priority_types = ["alternate_state"]
        for type_name in high_priority_types:
            if type_name in self._user_type_resolvers:
                resolver = self._user_type_resolvers[type_name]
                if resolver.is_user_type_instance(value):
                    # Create minimal metadata for alternate state detection
                    metadata = MetadataExtractor.extract_all_metadata(value) or {}
                    return UserTypeIdentification(type_name=type_name, metadata=metadata, resolver=resolver)

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

    def __init__(self, user_type_manager: UserTypeManager | None = None) -> None:
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
        if isinstance(extracted, int | float | bool):
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
        left_user_type: UserTypeIdentification | None,
        right_user_type: UserTypeIdentification | None,
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
        if isinstance(value, int | float):
            return TypeCategory.NUMERIC
        if isinstance(value, datetime | date | time):
            return TypeCategory.DATETIME
        return TypeCategory.STRING


# === Type Analyzer Class ===


class TypeAnalyzer:
    """Main type analysis class that coordinates type reduction and comparison."""

    def __init__(self) -> None:
        self.type_reducer = TypeReducer()
        self._register_builtin_user_types()

    def _register_builtin_user_types(self) -> None:
        """Register built-in user types with highest priority."""
        # Register alternate state type with highest priority
        alternate_state_reducer = AlternateStateTypeReducer()
        alternate_state_resolver = AlternateStateTypeResolver()

        self.register_user_type_reducer("alternate_state", alternate_state_reducer)
        self.register_user_type_resolver("alternate_state", alternate_state_resolver)

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
        if isinstance(value, int | float):
            return TypeCategory.NUMERIC
        if isinstance(value, str):
            return StringCategorizer.categorize_string(value)
        if isinstance(value, datetime | date | time):
            return TypeCategory.DATETIME
        return TypeCategory.UNKNOWN

    @staticmethod
    def categorize_expression_type(expression: str, context: dict[str, OperandType] | None = None) -> TypeCategory:
        """
        Determine the type category for an expression that may contain quoted literals or variables.

        This method is designed for date arithmetic expressions where we need to handle:
        - Quoted date literals: "'2025-01-01'"
        - Context variables: "start_date"
        - Mixed expressions where type depends on resolved values

        Args:
            expression: The expression string to analyze
            context: Optional context for variable resolution

        Returns:
            TypeCategory based on the resolved expression value
        """
        if not isinstance(expression, str):
            return TypeAnalyzer.categorize_type(expression)

        # Handle quoted literals by analyzing the inner content
        if expression.startswith("'") and expression.endswith("'"):
            inner_content = expression[1:-1]
            return TypeAnalyzer.categorize_type(inner_content)

        # Handle context variable lookup
        if context and expression in context:
            resolved_value = context[expression]
            return TypeAnalyzer.categorize_type(resolved_value)

        # Fall back to standard string categorization
        return StringCategorizer.categorize_string(expression)
