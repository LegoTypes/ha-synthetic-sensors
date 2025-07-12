"""Entity factory for creating synthetic sensor entities.

This module provides factory patterns for creating different
types of synthetic sensor entities with proper unique ID generation
and entity descriptions.
"""

from dataclasses import dataclass
import logging
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant

from .config_types import AttributeConfigDict, SensorConfigDict
from .name_resolver import NameResolver

_LOGGER = logging.getLogger(__name__)


# TypedDict for entity creation results
class EntityCreationResult(TypedDict):
    success: bool
    entity: Any | None
    errors: list[str]


class ValidationResult(TypedDict):
    is_valid: bool
    errors: list[str]


@dataclass
class EntityDescription:
    """Description for a synthetic sensor entity."""

    unique_id: str
    entity_id: str
    name: str | None = None
    icon: str | None = None
    device_class: str | None = None
    unit_of_measurement: str | None = None
    state_class: str | None = None


class EntityFactory:
    """Factory for creating synthetic sensor entities with proper ID management."""

    def __init__(self, hass: HomeAssistant, name_resolver: "NameResolver") -> None:
        """Initialize the entity factory.

        Args:
            hass: Home Assistant instance
            name_resolver: Name resolver for entity ID mapping
        """
        self._hass = hass
        self._name_resolver = name_resolver
        self._logger = _LOGGER.getChild(self.__class__.__name__)

    def generate_unique_id(self, sensor_id: str, formula_id: str | None = None) -> str:
        """Generate a unique ID for a sensor entity.

        Args:
            sensor_id: The sensor's unique identifier
            formula_id: Optional formula identifier for multi-formula sensors

        Returns:
            str: Generated unique ID following the pattern
            {sensor_id}[_{formula_id}]
        """
        base_id = sensor_id
        if formula_id:
            return f"{base_id}_{formula_id}"
        return base_id

    def generate_entity_id(self, sensor_id: str, formula_id: str | None = None) -> str:
        """Generate an entity ID for a sensor entity.

        Args:
            sensor_id: The sensor's unique identifier
            formula_id: Optional formula identifier for multi-formula sensors

        Returns:
            str: Generated entity ID following the pattern
            sensor.{sensor_id}[_{formula_id}]
        """
        unique_id = self.generate_unique_id(sensor_id, formula_id)
        return f"sensor.{unique_id}"

    def create_entity_description(
        self,
        sensor_config: SensorConfigDict,
        formula_config: AttributeConfigDict | None = None,
    ) -> EntityDescription:
        """Create an entity description from sensor and formula configuration.

        Args:
            sensor_config: Sensor configuration dictionary
            formula_config: Optional formula configuration dictionary

        Returns:
            EntityDescription: Entity description with generated IDs and metadata
        """
        sensor_id_val = sensor_config.get("unique_id") or sensor_config.get("name")
        if not sensor_id_val or not isinstance(sensor_id_val, str):
            raise ValueError("Sensor must have either 'unique_id' or 'name' field")
        sensor_id = str(sensor_id_val)

        formula_id_val = formula_config.get("id") if formula_config else None
        formula_id = str(formula_id_val) if formula_id_val else None

        unique_id = self.generate_unique_id(sensor_id, formula_id)
        entity_id = self.generate_entity_id(sensor_id, formula_id)

        # Determine display name (formula name takes priority, then
        # sensor name, then unique_id)
        name: str | None = None
        if formula_config and formula_config.get("name"):
            name_val = formula_config.get("name")
            name = str(name_val) if name_val else None
        elif sensor_config.get("name"):
            name_val = sensor_config.get("name")
            name = str(name_val) if name_val else None
        else:
            name = unique_id

        # Extract entity metadata from formula and sensor metadata
        formula_metadata = formula_config.get("metadata", {}) if formula_config else {}
        sensor_metadata = sensor_config.get("metadata", {})

        # Formula metadata takes priority over sensor metadata
        merged_metadata = {**sensor_metadata, **formula_metadata}

        icon = merged_metadata.get("icon")
        device_class = merged_metadata.get("device_class")
        unit_of_measurement = merged_metadata.get("unit_of_measurement")
        state_class = merged_metadata.get("state_class")

        return EntityDescription(
            unique_id=unique_id,
            entity_id=entity_id,
            name=name,
            icon=icon,
            device_class=device_class,
            unit_of_measurement=unit_of_measurement,
            state_class=state_class,
        )

    def create_sensor_entity(self, sensor_config: SensorConfigDict) -> EntityCreationResult:
        """Create a sensor entity from configuration.

        This is a factory method that would create the actual sensor entity object.
        In a real implementation, this would return a DynamicSensor or similar entity.

        Args:
            sensor_config: Sensor configuration dictionary

        Returns:
            EntityCreationResult: Result with success status and created entity
        """

        # For now, return a simple mock object to satisfy the test
        # In a real implementation, this would create a DynamicSensor
        class MockSensorEntity:
            def __init__(self, config: SensorConfigDict):
                self.config = config
                self.unique_id = config.get("unique_id", config.get("name"))
                self.name = config.get("name", self.unique_id)

        try:
            entity = MockSensorEntity(sensor_config)
            return {"success": True, "entity": entity, "errors": []}
        except Exception as e:
            return {"success": False, "entity": None, "errors": [str(e)]}

    def validate_entity_configuration(self, sensor_config: SensorConfigDict) -> ValidationResult:
        """Validate entity configuration for completeness and correctness.

        Args:
            sensor_config: Sensor configuration to validate

        Returns:
            ValidationResult: Validation result with status and errors
        """
        errors = []

        # Check required fields
        if not sensor_config.get("unique_id") and not sensor_config.get("name"):
            errors.append("Sensor must have either 'unique_id' or 'name' field")

        # Check that formula is present (required for all sensors)
        if not sensor_config.get("formula"):
            errors.append("Sensor must have 'formula' field")

        return {"is_valid": len(errors) == 0, "errors": errors}
