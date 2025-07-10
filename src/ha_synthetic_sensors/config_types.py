"""
Configuration type definitions for synthetic sensors.

This module contains TypedDicts and type aliases used for YAML configuration parsing.
"""

from __future__ import annotations

from typing import Any, TypeAlias, TypedDict

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

# Type alias for attribute values (allows complex types for formula metadata)
AttributeValue = str | float | int | bool | list[str] | dict[str, Any]

# Type aliases for Home Assistant constants - use the actual enum types
DeviceClassType: TypeAlias = SensorDeviceClass | str  # str for YAML parsing, enum for runtime
StateClassType: TypeAlias = SensorStateClass | str  # str for YAML parsing, enum for runtime


# TypedDicts for v2.0 YAML config structures
class AttributeConfigDict(TypedDict, total=False):
    """TypedDict for attribute configuration in YAML."""

    formula: str
    metadata: dict[str, Any]
    variables: dict[str, str | int | float]  # Allow attributes to define additional variables


class SensorConfigDict(TypedDict, total=False):
    """TypedDict for sensor configuration in YAML."""

    name: str
    description: str
    enabled: bool
    update_interval: int
    category: str
    entity_id: str  # Optional: Explicit entity ID for the sensor
    # Main formula syntax
    formula: str
    attributes: dict[str, AttributeConfigDict]
    # Common properties
    variables: dict[str, str | int | float]
    metadata: dict[str, Any]
    extra_attributes: dict[str, AttributeValue]
    # Device association fields
    device_identifier: str  # Device identifier to associate with
    device_name: str  # Optional device name override
    device_manufacturer: str
    device_model: str
    device_sw_version: str
    device_hw_version: str
    suggested_area: str


class GlobalSettingsDict(TypedDict, total=False):
    """TypedDict for global settings in YAML."""

    device_identifier: str
    device_name: str
    device_manufacturer: str
    device_model: str
    device_sw_version: str
    device_hw_version: str
    suggested_area: str
    variables: dict[str, str | int | float]
    metadata: dict[str, Any]


class ConfigDict(TypedDict, total=False):
    """TypedDict for complete configuration in YAML."""

    version: str
    global_settings: GlobalSettingsDict
    sensors: dict[str, SensorConfigDict]


# Common error structures for validation
YAML_SYNTAX_ERROR_TEMPLATE = {
    "path": "file",
    "severity": "error",
    "schema_path": "",
    "suggested_fix": "Check YAML syntax and formatting",
}
