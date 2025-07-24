"""Constants and utilities for entity management in synthetic sensors."""

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .ha_constants import get_ha_constant

_LOGGER = logging.getLogger(__name__)

# Device class constants for categorization
NUMERIC_DEVICE_CLASSES = {
    "temperature",
    "humidity",
    "pressure",
    "power",
    "energy",
    "voltage",
    "current",
    "frequency",
    "illuminance",
    "signal_strength",
    "battery",
    "gas",
    "pm25",
    "pm10",
    "co2",
    "tvoc",
    "distance",
    "duration",
    "timestamp",
}

BOOLEAN_DEVICE_CLASSES = {
    "opening",
    "light",
    "lock",
    "plug",
    "switch",
    "presence",
    "occupancy",
    "motion",
    "smoke",
    "gas",
    "moisture",
    "sound",
    "vibration",
    "connectivity",
    "update",
    "problem",
}

STRING_DEVICE_CLASSES = {
    "connectivity",
    "update",
    "problem",
    "enum",
}

# Cache for domain lists to avoid repeated registry lookups
_domain_cache: dict[str, frozenset[str]] = {}


def _get_domains_from_registry(hass: HomeAssistant) -> set[str]:
    """Get all entity domains from the entity registry.

    Args:
        hass: Home Assistant instance

    Returns:
        Set of domain names
    """
    try:
        registry = er.async_get(hass)
        return {entity.domain for entity in registry.entities.values()}
    except Exception as e:
        _LOGGER.warning("Failed to get domains from registry: %s", e)
        return set()


def _get_ha_domain_constant(domain_name: str) -> str:
    """Get the HA domain constant for a domain name.

    Args:
        domain_name: Domain name to get constant for

    Returns:
        Domain constant or domain name if not found
    """
    try:
        # Try to get from HA component module
        module_path = f"homeassistant.components.{domain_name}"
        result = get_ha_constant("DOMAIN", module_path)
        return str(result) if result is not None else domain_name
    except (ImportError, AttributeError):
        # Fallback to domain name itself if module not available
        return domain_name


def _discover_domain_characteristics(domain: str) -> set[str]:
    """Dynamically discover characteristics of a domain.

    Args:
        domain: Domain name to analyze

    Returns:
        Set of characteristics (numeric, boolean, string, valid)
    """
    characteristics = set()

    # Handle custom integrations that don't exist in HA components
    if domain == "span_panel":
        return {"numeric", "valid"}

    try:
        # Try to get domain constant from HA
        ha_domain = _get_ha_domain_constant(domain)

        # Check if we got a mock object (happens in tests)
        actual_domain = domain if hasattr(ha_domain, "_mock_name") or str(type(ha_domain)).find("Mock") != -1 else ha_domain

        # Analyze domain characteristics by examining HA component structure
        try:
            component_module = __import__(f"homeassistant.components.{actual_domain}", fromlist=[""])

            # Check for numeric characteristics by looking for numeric state classes
            if (
                hasattr(component_module, "STATE_CLASS_MEASUREMENT")
                or hasattr(component_module, "STATE_CLASS_TOTAL")
                or hasattr(component_module, "STATE_CLASS_TOTAL_INCREASING")
                or hasattr(component_module, "ATTR_UNIT_OF_MEASUREMENT")
            ):
                characteristics.add("numeric")

            # Check for boolean characteristics by looking for on/off states
            if (
                hasattr(component_module, "STATE_ON")
                or hasattr(component_module, "STATE_OFF")
                or hasattr(component_module, "ATTR_ASSUMED_STATE")
                or hasattr(component_module, "SERVICE_TURN_ON")
                or hasattr(component_module, "SERVICE_TURN_OFF")
            ):
                characteristics.add("boolean")

            # Check for string characteristics by looking for text-based attributes
            if (
                hasattr(component_module, "ATTR_OPTIONS")
                or hasattr(component_module, "ATTR_PATTERN")
                or hasattr(component_module, "ATTR_MODE")
                or hasattr(component_module, "ATTR_ICON")
            ):
                characteristics.add("string")

            # If we can examine the component, it's likely valid for formulas
            characteristics.add("valid")

        except (ImportError, AttributeError):
            # If we can't examine the component, we can't determine characteristics
            # This is better than using hardcoded lists - we just don't know
            pass

    except Exception as e:
        _LOGGER.debug("Failed to discover characteristics for domain %s: %s", domain, e)

    return characteristics


def _get_numeric_entity_types(hass: HomeAssistant) -> set[str]:
    """Get entity types that support numeric values.

    Args:
        hass: Home Assistant instance

    Returns:
        Set of numeric entity types
    """
    try:
        registry = er.async_get(hass)
        numeric_types = set()

        for entity in registry.entities.values():
            if entity.device_class in NUMERIC_DEVICE_CLASSES:
                numeric_types.add(entity.domain)

        return numeric_types
    except Exception as e:
        _LOGGER.warning("Failed to get numeric entity types: %s", e)
        return set()


def _get_boolean_entity_types(hass: HomeAssistant) -> set[str]:
    """Get entity types that support boolean values.

    Args:
        hass: Home Assistant instance

    Returns:
        Set of boolean entity types
    """
    try:
        registry = er.async_get(hass)
        boolean_types = set()

        for entity in registry.entities.values():
            if entity.device_class in BOOLEAN_DEVICE_CLASSES:
                boolean_types.add(entity.domain)

        return boolean_types
    except Exception as e:
        _LOGGER.warning("Failed to get boolean entity types: %s", e)
        return set()


def _get_string_entity_types(hass: HomeAssistant) -> set[str]:
    """Get entity types that support string values.

    Args:
        hass: Home Assistant instance

    Returns:
        Set of string entity types
    """
    try:
        registry = er.async_get(hass)
        string_types = set()

        for entity in registry.entities.values():
            if entity.device_class in STRING_DEVICE_CLASSES:
                string_types.add(entity.domain)

        return string_types
    except Exception as e:
        _LOGGER.warning("Failed to get string entity types: %s", e)
        return set()


def _get_valid_entity_types(hass: HomeAssistant) -> set[str]:
    """Get all valid entity types for formulas.

    Args:
        hass: Home Assistant instance

    Returns:
        Set of valid entity types
    """
    try:
        registry = er.async_get(hass)
        return {entity.domain for entity in registry.entities.values()}
    except Exception as e:
        _LOGGER.warning("Failed to get valid entity types: %s", e)
        return set()


def _get_cache_key(hass: HomeAssistant | None = None) -> str:
    """Get cache key for domain lists.

    Args:
        hass: Home Assistant instance or None

    Returns:
        Cache key string
    """
    if hass is None:
        return "default"
    return str(id(hass))


def _get_cached_domains(hass: HomeAssistant | None = None) -> frozenset[str] | None:
    """Get cached domain list.

    Args:
        hass: Home Assistant instance or None

    Returns:
        Cached domain list or None if not cached
    """
    cache_key = _get_cache_key(hass)
    return _domain_cache.get(cache_key)


def _set_cached_domains(hass: HomeAssistant | None = None, domains: frozenset[str] | None = None) -> None:
    """Set cached domain list.

    Args:
        hass: Home Assistant instance or None
        domains: Domain list to cache or None to clear cache
    """
    cache_key = _get_cache_key(hass)
    if domains is None:
        _domain_cache.pop(cache_key, None)
    else:
        _domain_cache[cache_key] = domains


def clear_domain_cache(hass: HomeAssistant | None = None) -> None:
    """Clear the domain cache.

    Args:
        hass: Home Assistant instance or None to clear all caches
    """
    if hass is None:
        _domain_cache.clear()
    else:
        cache_key = _get_cache_key(hass)
        _domain_cache.pop(cache_key, None)


def get_ha_entity_domains(hass: HomeAssistant) -> frozenset[str]:
    """Get all entity domains from Home Assistant.

    Args:
        hass: Home Assistant instance

    Returns:
        Frozen set of domain names
    """
    # Check cache first
    cached = _get_cached_domains(hass)
    if cached is not None:
        return cached

    # Get from registry
    domains = _get_domains_from_registry(hass)
    result = frozenset(domains)

    # Cache the result
    _set_cached_domains(hass, result)

    return result


def get_valid_entity_types(hass: HomeAssistant) -> frozenset[str]:
    """Get all valid entity types for formulas.

    Args:
        hass: Home Assistant instance

    Returns:
        Frozen set of valid entity types
    """
    domains = _get_valid_entity_types(hass)
    return frozenset(domains)


def get_numeric_entity_types(hass: HomeAssistant) -> frozenset[str]:
    """Get entity types that support numeric values.

    Args:
        hass: Home Assistant instance

    Returns:
        Frozen set of numeric entity types
    """
    domains = _get_numeric_entity_types(hass)
    return frozenset(domains)


def get_boolean_entity_types(hass: HomeAssistant) -> frozenset[str]:
    """Get entity types that support boolean values.

    Args:
        hass: Home Assistant instance

    Returns:
        Frozen set of boolean entity types
    """
    domains = _get_boolean_entity_types(hass)
    return frozenset(domains)


def get_string_entity_types(hass: HomeAssistant) -> frozenset[str]:
    """Get entity types that support string values.

    Args:
        hass: Home Assistant instance

    Returns:
        Frozen set of string entity types
    """
    domains = _get_string_entity_types(hass)
    return frozenset(domains)


def is_valid_entity_type(entity_type: str, hass: HomeAssistant) -> bool:
    """Check if an entity type is valid for formulas.

    Args:
        entity_type: Entity type to check
        hass: Home Assistant instance

    Returns:
        True if valid, False otherwise
    """
    valid_types = get_valid_entity_types(hass)
    return entity_type in valid_types


def is_ha_entity_domain(domain: str, hass: HomeAssistant) -> bool:
    """Check if a domain is a valid HA entity domain.

    Args:
        domain: Domain to check
        hass: Home Assistant instance

    Returns:
        True if valid, False otherwise
    """
    ha_domains = get_ha_entity_domains(hass)
    return domain in ha_domains


def is_numeric_entity_type(entity_type: str, hass: HomeAssistant) -> bool:
    """Check if an entity type supports numeric values.

    Args:
        entity_type: Entity type to check
        hass: Home Assistant instance

    Returns:
        True if numeric, False otherwise
    """
    numeric_types = get_numeric_entity_types(hass)
    return entity_type in numeric_types


def is_boolean_entity_type(entity_type: str, hass: HomeAssistant) -> bool:
    """Check if an entity type supports boolean values.

    Args:
        entity_type: Entity type to check
        hass: Home Assistant instance

    Returns:
        True if boolean, False otherwise
    """
    boolean_types = get_boolean_entity_types(hass)
    return entity_type in boolean_types


def is_string_entity_type(entity_type: str, hass: HomeAssistant) -> bool:
    """Check if an entity type supports string values.

    Args:
        entity_type: Entity type to check
        hass: Home Assistant instance

    Returns:
        True if string, False otherwise
    """
    string_types = get_string_entity_types(hass)
    return entity_type in string_types


def get_entity_type_from_id(entity_id: str) -> str | None:
    """Extract entity type from entity ID.

    Args:
        entity_id: Entity ID to parse

    Returns:
        Entity type or None if invalid
    """
    if not entity_id or "." not in entity_id:
        return None

    return entity_id.split(".", 1)[0]


def is_valid_entity_id(entity_id: str, hass: HomeAssistant) -> bool:
    """Check if an entity ID is valid and exists.

    Args:
        entity_id: Entity ID to check
        hass: Home Assistant instance

    Returns:
        True if valid and exists, False otherwise
    """
    if not entity_id or "." not in entity_id:
        return False

    try:
        registry = er.async_get(hass)
        return entity_id in registry.entities
    except Exception:
        return False
