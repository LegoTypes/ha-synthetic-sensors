"""Shared constants used across multiple modules."""

# Home Assistant entity domains - lazy loaded to avoid import-time issues
from homeassistant.core import HomeAssistant

from .constants_entities import get_ha_entity_domains

# Entity domain constants
SENSOR_DOMAIN = "sensor"
BINARY_SENSOR_DOMAIN = "binary_sensor"
DOMAIN_SEPARATOR = "."

# Computed constants for entity ID prefixes
SENSOR_PREFIX = f"{SENSOR_DOMAIN}{DOMAIN_SEPARATOR}"
BINARY_SENSOR_PREFIX = f"{BINARY_SENSOR_DOMAIN}{DOMAIN_SEPARATOR}"
SENSOR_PREFIX_LENGTH = len(SENSOR_PREFIX)
BINARY_SENSOR_PREFIX_LENGTH = len(BINARY_SENSOR_PREFIX)


def extract_entity_key_from_domain(entity_id: str, domain: str) -> str | None:
    """Extract the key part from a domain.key entity ID.

    Args:
        entity_id: The full entity ID (e.g., "sensor.my_sensor")
        domain: The domain to check for (e.g., "sensor")

    Returns:
        The key part if the entity_id matches the domain, None otherwise

    Examples:
        >>> extract_entity_key_from_domain("sensor.my_sensor", "sensor")
        "my_sensor"
        >>> extract_entity_key_from_domain("binary_sensor.door", "binary_sensor")
        "door"
        >>> extract_entity_key_from_domain("sensor.temp", "binary_sensor")
        None
    """
    prefix = f"{domain}{DOMAIN_SEPARATOR}"
    if entity_id.startswith(prefix):
        return entity_id[len(prefix) :]
    return None


def is_entity_from_domain(entity_id: str, domain: str) -> bool:
    """Check if an entity ID belongs to a specific domain.

    Args:
        entity_id: The full entity ID (e.g., "sensor.my_sensor")
        domain: The domain to check for (e.g., "sensor")

    Returns:
        True if the entity_id belongs to the domain, False otherwise
    """
    return entity_id.startswith(f"{domain}{DOMAIN_SEPARATOR}")


# Python keywords that should be excluded from variable extraction
PYTHON_KEYWORDS: frozenset[str] = frozenset(
    {
        "if",
        "else",
        "elif",
        "for",
        "while",
        "def",
        "class",
        "import",
        "from",
        "as",
        "in",
        "is",
        "try",
        "except",
        "finally",
        "with",
        "return",
        "yield",
        "break",
        "continue",
        "pass",
        "raise",
        "assert",
        "and",
        "or",
        "not",
    }
)

# Built-in types that should be excluded from variable extraction
BUILTIN_TYPES: frozenset[str] = frozenset(
    {
        "str",
        "int",
        "float",
        "bool",
        "list",
        "dict",
        "set",
        "tuple",
    }
)

# Boolean literals
BOOLEAN_LITERALS: frozenset[str] = frozenset(
    {
        "True",
        "False",
        "None",
    }
)

# Datetime functions
DATETIME_FUNCTIONS: frozenset[str] = frozenset(
    {
        "now",
        "local_now",
        "utc_now",
        "today",
        "yesterday",
        "tomorrow",
        "utc_today",
        "utc_yesterday",
    }
)

# Duration helper functions for explicit date arithmetic
DURATION_FUNCTIONS: frozenset[str] = frozenset(
    {
        "days",
        "weeks",
        "months",
        "hours",
        "minutes",
        "seconds",
        # Unit conversion functions for timedelta results
        "as_minutes",
        "as_seconds",
        "as_hours",
        "as_days",
    }
)

# String manipulation functions
STRING_FUNCTIONS: frozenset[str] = frozenset(
    {
        "str",
        "trim",
        "lower",
        "upper",
        "title",
        "contains",
        "startswith",
        "endswith",
        "length",
        "replace",
        "replace_all",
        "normalize",
        "clean",
        "sanitize",
        "isalpha",
        "isdigit",
        "isnumeric",
        "isalnum",
        "split",
        "join",
        "pad_left",
        "pad_right",
        "center",
    }
)

# Metadata access functions
METADATA_FUNCTIONS: frozenset[str] = frozenset(
    {
        "metadata",
    }
)

# Collection pattern prefixes used in formula parsing
COLLECTION_PREFIXES: frozenset[str] = frozenset(
    {
        "device_class:",
        "state:",
        "attribute:",
        "entity_id:",
        "domain:",
        "area:",
        "integration:",
        "platform:",
    }
)

# Mathematical and aggregation functions
MATH_FUNCTIONS: frozenset[str] = frozenset(
    {
        "sum",
        "avg",
        "max",
        "min",
        "count",
    }
    | DATETIME_FUNCTIONS
    | DURATION_FUNCTIONS
)

# State-related keywords
STATE_KEYWORDS: frozenset[str] = frozenset(
    {
        "state",
    }
)


# Lazy-loaded function to get all reserved words
def get_reserved_words(hass: HomeAssistant | None = None) -> frozenset[str]:
    """Get all reserved words including HA domains (lazy loaded).

    Args:
        hass: Home Assistant instance (optional, for registry access)

    Returns:
        Frozenset of all reserved words
    """
    if hass is None:
        return PYTHON_KEYWORDS | BUILTIN_TYPES | BOOLEAN_LITERALS | MATH_FUNCTIONS | STRING_FUNCTIONS | STATE_KEYWORDS
    return (
        PYTHON_KEYWORDS
        | BUILTIN_TYPES
        | BOOLEAN_LITERALS
        | MATH_FUNCTIONS
        | STRING_FUNCTIONS
        | STATE_KEYWORDS
        | get_ha_entity_domains(hass)
    )


# Legacy constant for backward compatibility (lazy loaded)
def get_ha_domains(hass: HomeAssistant | None = None) -> frozenset[str]:
    """Get HA entity domains (lazy loaded).

    Args:
        hass: Home Assistant instance (optional, for registry access)

    Returns:
        Frozenset of HA entity domains
    """
    if hass is None:
        return frozenset()
    return get_ha_entity_domains(hass)


__all__ = [
    "BOOLEAN_LITERALS",
    "BUILTIN_TYPES",
    "COLLECTION_PREFIXES",
    "DATETIME_FUNCTIONS",
    "DURATION_FUNCTIONS",
    "MATH_FUNCTIONS",
    "PYTHON_KEYWORDS",
    "STATE_KEYWORDS",
    "STRING_FUNCTIONS",
    "get_ha_domains",
    "get_reserved_words",
]

# Last-good attribute names exposed on entities (engine-managed)
LAST_VALID_STATE_KEY = "last_valid_state"
LAST_VALID_CHANGED_KEY = "last_valid_changed"

# Base extra state attribute names used by the engine for every sensor
ENGINE_BASE_RESERVED_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "formula",
        "dependencies",
        "last_update",
        "sensor_category",
    }
)

__all__ += [
    "ENGINE_BASE_RESERVED_ATTRIBUTES",
    "LAST_VALID_CHANGED_KEY",
    "LAST_VALID_STATE_KEY",
]
