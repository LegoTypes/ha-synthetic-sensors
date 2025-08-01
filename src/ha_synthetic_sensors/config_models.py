"""
Configuration data models for synthetic sensors.

This module contains the dataclass models that represent the parsed configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant

from .config_types import AttributeValue, GlobalSettingsDict
from .dependency_parser import DependencyParser

# Default domain constant
DEFAULT_DOMAIN = "synthetic_sensors"


def _default_attributes() -> dict[str, AttributeValue]:
    """Default factory for attributes dictionary."""
    return {}


def _default_dependencies() -> set[str]:
    """Default factory for dependencies set."""
    return set()


def _default_variables() -> dict[str, str | int | float | ComputedVariable]:
    """Default factory for variables dictionary."""
    return {}


def _default_formulas() -> list[FormulaConfig]:
    """Default factory for formulas list."""
    return []


def _default_sensors() -> list[SensorConfig]:
    """Default factory for sensors list."""
    return []


def _default_global_settings() -> GlobalSettingsDict:
    """Default factory for global settings dictionary."""
    return {}


def _default_metadata() -> dict[str, Any]:
    """Default factory for metadata dictionary."""
    return {}


@dataclass
class ExceptionHandler:
    """Exception handler for formulas and variables when entities become unavailable or unknown."""

    unavailable: str | None = None  # Formula to execute when dependencies are unavailable
    unknown: str | None = None  # Formula to execute when dependencies are unknown

    def __post_init__(self) -> None:
        """Validate the exception handler after initialization."""
        if not self.unavailable and not self.unknown:
            raise ValueError("ExceptionHandler must have at least one handler (unavailable or unknown)")
        if self.unavailable and not self.unavailable.strip():
            raise ValueError("ExceptionHandler unavailable formula cannot be whitespace only")
        if self.unknown and not self.unknown.strip():
            raise ValueError("ExceptionHandler unknown formula cannot be whitespace only")


@dataclass
class ComputedVariable:
    """A variable computed from a formula during context building."""

    formula: str
    dependencies: set[str] = field(default_factory=set)
    exception_handler: ExceptionHandler | None = None  # Exception handling for this variable

    def __post_init__(self) -> None:
        """Validate the computed variable after initialization."""
        if not self.formula:
            raise ValueError("ComputedVariable formula cannot be empty")
        if not self.formula.strip():
            raise ValueError("ComputedVariable formula cannot be whitespace only")


@dataclass
class FormulaConfig:
    """Configuration for a single formula within a synthetic sensor."""

    id: str  # REQUIRED: Formula identifier
    formula: str
    name: str | None = None  # OPTIONAL: Display name
    metadata: dict[str, Any] = field(default_factory=_default_metadata)
    attributes: dict[str, AttributeValue] = field(default_factory=_default_attributes)
    dependencies: set[str] = field(default_factory=_default_dependencies)
    variables: dict[str, str | int | float | ComputedVariable] = field(
        default_factory=_default_variables
    )  # Variable name -> entity_id mappings, numeric literals, or computed variables
    exception_handler: ExceptionHandler | None = None  # Exception handling for this formula

    def __post_init__(self) -> None:
        """Extract dependencies from formula after initialization."""
        # Only extract dependencies if not already set (e.g., from deserialization)
        # Note: Dependencies are now extracted at runtime when hass is available
        # This avoids issues with entity registry access during config creation

    def _extract_dependencies(self, hass: HomeAssistant | None = None) -> set[str]:
        """Extract entity dependencies from the formula string and variables."""
        # Use dependency parser that handles:
        # - Variable references
        # - Direct entity_ids
        # - Dot notation (sensor1.battery_level)
        # - Dynamic queries (regex:, label:, device_class:, etc.)
        parser = DependencyParser(hass)

        # Extract static dependencies (direct entity references and variables)
        static_deps = parser.extract_static_dependencies(self.formula, self.variables)

        # Note: Dynamic query patterns are extracted but resolved at runtime by evaluator
        # Dynamic dependencies cannot be pre-computed as they depend on HA state
        return static_deps

    def get_dependencies(self, hass: HomeAssistant | None = None) -> set[str]:
        """Get dependencies for this formula, extracting them at runtime if needed."""
        if not self.dependencies:
            self.dependencies = self._extract_dependencies(hass)
        return self.dependencies


@dataclass
class SensorConfig:
    """Configuration for a complete synthetic sensor with multiple formulas."""

    unique_id: str  # REQUIRED: Unique identifier for HA entity creation
    formulas: list[FormulaConfig] = field(default_factory=_default_formulas)
    name: str | None = None  # OPTIONAL: Display name
    enabled: bool = True
    update_interval: int | None = None
    category: str | None = None
    description: str | None = None
    entity_id: str | None = None  # OPTIONAL: Explicit entity ID
    # New metadata field
    metadata: dict[str, Any] = field(default_factory=_default_metadata)
    # Device association fields
    device_identifier: str | None = None  # Device identifier to associate with
    device_name: str | None = None  # Optional device name override
    device_manufacturer: str | None = None
    device_model: str | None = None
    device_sw_version: str | None = None
    device_hw_version: str | None = None
    suggested_area: str | None = None

    def copy_with_overrides(self, **overrides: Any) -> SensorConfig:
        """Create a copy of this sensor config with optional field overrides.

        Args:
            **overrides: Fields to override in the copy

        Returns:
            New SensorConfig instance with overridden values
        """
        return SensorConfig(
            unique_id=overrides.get("unique_id", self.unique_id),
            formulas=overrides.get("formulas", self.formulas.copy()),
            name=overrides.get("name", self.name),
            enabled=overrides.get("enabled", self.enabled),
            update_interval=overrides.get("update_interval", self.update_interval),
            category=overrides.get("category", self.category),
            description=overrides.get("description", self.description),
            entity_id=overrides.get("entity_id", self.entity_id),
            metadata=overrides.get("metadata", self.metadata.copy()),
            device_identifier=overrides.get("device_identifier", self.device_identifier),
            device_name=overrides.get("device_name", self.device_name),
            device_manufacturer=overrides.get("device_manufacturer", self.device_manufacturer),
            device_model=overrides.get("device_model", self.device_model),
            device_sw_version=overrides.get("device_sw_version", self.device_sw_version),
            device_hw_version=overrides.get("device_hw_version", self.device_hw_version),
            suggested_area=overrides.get("suggested_area", self.suggested_area),
        )

    def get_all_dependencies(self) -> set[str]:
        """Get all entity dependencies across all formulas."""
        deps: set[str] = set()
        for formula in self.formulas:
            deps.update(formula.dependencies)
        return deps

    def validate(self) -> list[str]:
        """Validate sensor configuration and return list of errors."""
        errors: list[str] = []

        if not self.unique_id:
            errors.append("Sensor unique_id is required")

        if not self.formulas:
            errors.append(f"Sensor '{self.unique_id}' must have at least one formula")

        formula_ids = [f.id for f in self.formulas]
        if len(formula_ids) != len(set(formula_ids)):
            errors.append(f"Sensor '{self.unique_id}' has duplicate formula IDs")

        return errors


@dataclass
class Config:
    """Complete configuration containing all synthetic sensors."""

    version: str = "1.0"
    sensors: list[SensorConfig] = field(default_factory=_default_sensors)
    global_settings: GlobalSettingsDict = field(default_factory=_default_global_settings)
    # Cross-sensor reference mapping (Phase 1 of cross-sensor reference system)
    cross_sensor_references: dict[str, set[str]] = field(default_factory=dict)

    def get_sensor_by_unique_id(self, unique_id: str) -> SensorConfig | None:
        """Get a sensor configuration by unique_id."""
        for sensor in self.sensors:
            if sensor.unique_id == unique_id:
                return sensor
        return None

    def get_sensor_by_name(self, name: str) -> SensorConfig | None:
        """Get a sensor configuration by name."""
        for sensor in self.sensors:
            if name in (sensor.name, sensor.unique_id):
                return sensor
        return None

    def get_all_dependencies(self) -> set[str]:
        """Get all entity dependencies across all sensors."""
        deps: set[str] = set()
        for sensor in self.sensors:
            deps.update(sensor.get_all_dependencies())
        return deps

    def validate(self) -> list[str]:
        """Validate the entire configuration and return list of errors."""
        errors: list[str] = []

        # Check for duplicate sensor unique_ids
        sensor_unique_ids = [s.unique_id for s in self.sensors]
        if len(sensor_unique_ids) != len(set(sensor_unique_ids)):
            errors.append("Duplicate sensor unique_ids found")

        # Validate each sensor
        for sensor in self.sensors:
            sensor_errors = sensor.validate()
            errors.extend(sensor_errors)

        return errors
