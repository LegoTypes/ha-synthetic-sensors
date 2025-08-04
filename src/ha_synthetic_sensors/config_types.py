"""
Configuration type definitions for synthetic sensors.

This module contains TypedDicts and type aliases used for YAML configuration parsing.
"""

from __future__ import annotations

from typing import Any, TypedDict

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

# Type alias for attribute values (allows complex types for formula metadata)
AttributeValue = str | float | int | bool | list[str] | dict[str, Any]

# Type aliases for Home Assistant constants - use the actual enum types
type DeviceClassType = SensorDeviceClass | str  # str for YAML parsing, enum for runtime
type StateClassType = SensorStateClass | str  # str for YAML parsing, enum for runtime


# TypedDicts for metadata structures
class EntityMetadataDict(TypedDict, total=False):
    """TypedDict for entity metadata with all possible properties."""

    # String properties
    unit_of_measurement: str
    device_class: str
    state_class: str
    icon: str

    # Integer properties
    suggested_display_precision: int

    # Boolean properties
    entity_registry_enabled_default: bool
    entity_registry_visible_default: bool
    assumed_state: bool

    # List properties
    options: list[str]

    # Enumerated properties
    entity_category: str  # One of: "config", "diagnostic", "system"


class AttributeMetadataDict(TypedDict, total=False):
    """TypedDict for attribute metadata with only allowed properties."""

    # String properties
    unit_of_measurement: str
    icon: str

    # Integer properties
    suggested_display_precision: int

    # Custom properties (any string key with any value)
    # Note: This is handled by the total=False and allowing additional properties


# Type alias for metadata that can be either entity or attribute metadata
# Use dict[str, Any] for runtime flexibility while maintaining type hints
MetadataDict = dict[str, Any]


# TypedDicts for storage and internal data structures
class GlobalSettingsStorageDict(TypedDict, total=False):
    """TypedDict for global settings as stored in the data structure."""

    device_identifier: str
    device_name: str
    device_manufacturer: str
    device_model: str
    device_sw_version: str
    device_hw_version: str
    suggested_area: str
    variables: dict[str, str | int | float]
    metadata: dict[str, Any]


class SensorSetDataDict(TypedDict, total=False):
    """TypedDict for sensor set data as stored in the data structure."""

    global_settings: GlobalSettingsStorageDict
    sensors: dict[str, dict[str, Any]]  # Serialized sensor configs
    metadata: dict[str, str]  # Sensor set metadata
    created_at: str
    updated_at: str
    sensor_count: int


class StorageDataDict(TypedDict):
    """TypedDict for the complete storage data structure."""

    sensor_sets: dict[str, SensorSetDataDict]
    version: str


# TypedDicts for v2.0 YAML config structures
class AttributeConfigDict(TypedDict, total=False):
    """TypedDict for attribute configuration in YAML."""

    formula: str
    metadata: dict[str, Any]
    variables: dict[str, str | int | float]  # Allow attributes to define additional variables


# Type alias for attribute configuration that can be either formula object or literal value
type AttributeConfig = AttributeConfigDict | str | int | float


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
    attributes: dict[str, AttributeConfig]
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
YAML_SYNTAX_ERROR_TEMPLATE = "YAML syntax error: {error}"
