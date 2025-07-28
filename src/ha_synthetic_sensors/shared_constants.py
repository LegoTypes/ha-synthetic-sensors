"""Shared constants used across multiple modules."""

# Home Assistant entity domains - lazy loaded to avoid import-time issues
from homeassistant.core import HomeAssistant

from .constants_entities import get_ha_entity_domains

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

# Mathematical and aggregation functions
MATH_FUNCTIONS: frozenset[str] = frozenset(
    {
        "sum",
        "avg",
        "max",
        "min",
        "count",
    }
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
        return PYTHON_KEYWORDS | BUILTIN_TYPES | BOOLEAN_LITERALS | MATH_FUNCTIONS | STATE_KEYWORDS
    return PYTHON_KEYWORDS | BUILTIN_TYPES | BOOLEAN_LITERALS | MATH_FUNCTIONS | STATE_KEYWORDS | get_ha_entity_domains(hass)


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
    "MATH_FUNCTIONS",
    "PYTHON_KEYWORDS",
    "STATE_KEYWORDS",
    "get_ha_domains",
    "get_reserved_words",
]
