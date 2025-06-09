"""
Sensor Manager - Dynamic sensor creation and lifecycle management.

This module handles the creation, updating, and removal of synthetic sensors
based on YAML configuration, providing the bridge between configuration
and Home Assistant sensor entities.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .config_manager import AttributeValue, Config, FormulaConfig, SensorConfig
from .evaluator import Evaluator
from .name_resolver import NameResolver

_LOGGER = logging.getLogger(__name__)


@dataclass
class SensorState:
    """Represents the current state of a synthetic sensor."""

    sensor_name: str
    formula_states: dict[str, float | int | str | bool]  # formula_name -> current_value
    last_update: datetime
    error_count: int = 0
    is_available: bool = True


class DynamicSensor(RestoreEntity, SensorEntity):
    """A dynamically created synthetic sensor entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: SensorConfig,
        formula_config: FormulaConfig,
        evaluator: Evaluator,
        sensor_manager: SensorManager,
    ):
        """Initialize the dynamic sensor."""
        self._hass = hass
        self._config = config
        self._formula_config = formula_config
        self._evaluator = evaluator
        self._sensor_manager = sensor_manager

        # Generate unique entity ID and set _attr_ properties
        self._attr_unique_id = f"syn2_{config.unique_id}_{formula_config.id}"

        # Set entity attributes using _attr_ pattern
        formula_display_name = formula_config.name or formula_config.id
        if config.name:
            self._attr_name = f"{config.name} {formula_display_name}"
        else:
            self._attr_name = formula_display_name

        self._attr_native_unit_of_measurement = formula_config.unit_of_measurement
        self._attr_device_class = formula_config.device_class
        self._attr_state_class = formula_config.state_class
        self._attr_icon = formula_config.icon

        # State management
        self._attr_native_value: Any = None
        self._attr_available = True

        # Set extra state attributes using _attr_ pattern
        base_attributes: dict[str, AttributeValue] = formula_config.attributes.copy()
        # Add metadata as AttributeValue types
        base_attributes["formula"] = formula_config.formula
        base_attributes["dependencies"] = list(formula_config.dependencies)
        if config.category:
            base_attributes["sensor_category"] = config.category
        self._attr_extra_state_attributes = base_attributes

        # Tracking
        self._last_update: datetime | None = None
        self._update_listeners: list[Any] = []
        self._dependencies = formula_config.dependencies

    def _update_extra_state_attributes(self) -> None:
        """Update the extra state attributes with current values."""
        base_attributes: dict[str, AttributeValue] = (
            self._formula_config.attributes.copy()
        )
        # Add metadata as AttributeValue types
        base_attributes["formula"] = self._formula_config.formula
        base_attributes["dependencies"] = list(self._dependencies)
        if self._last_update:
            base_attributes["last_update"] = self._last_update.isoformat()
        if self._config.category:
            base_attributes["sensor_category"] = self._config.category
        self._attr_extra_state_attributes = base_attributes

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()

        # Restore previous state
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                self._attr_native_value = float(last_state.state)
            except (ValueError, TypeError):
                self._attr_native_value = last_state.state

        # Set up dependency tracking
        if self._dependencies:
            self._update_listeners.append(
                async_track_state_change_event(
                    self._hass, list(self._dependencies), self._handle_dependency_change
                )
            )

        # Initial evaluation
        await self._async_update_sensor()

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal."""
        # Clean up listeners
        for listener in self._update_listeners:
            listener()
        self._update_listeners.clear()

    @callback
    async def _handle_dependency_change(self, event) -> None:
        """Handle when a dependency entity changes."""
        await self._async_update_sensor()

    async def _async_update_sensor(self) -> None:
        """Update the sensor value by evaluating the formula."""
        try:
            # Evaluate the formula using the evaluator
            evaluation_result = self._evaluator.evaluate_formula(self._formula_config)

            if evaluation_result["success"] and evaluation_result["value"] is not None:
                self._attr_native_value = evaluation_result["value"]
                self._attr_available = True
                self._last_update = dt_util.utcnow()

                # Update extra state attributes with new timestamp
                self._update_extra_state_attributes()

                # Notify sensor manager of successful update
                self._sensor_manager._on_sensor_updated(
                    self._config.unique_id,
                    self._formula_config.id,
                    evaluation_result["value"],
                )
            else:
                self._attr_available = False
                error_msg = evaluation_result.get("error", "Unknown evaluation error")
                _LOGGER.warning(
                    "Formula evaluation failed for %s: %s", self.entity_id, error_msg
                )

            # Schedule entity update
            self.async_write_ha_state()

        except Exception as err:
            self._attr_available = False
            _LOGGER.error("Error updating sensor %s: %s", self.entity_id, err)
            self.async_write_ha_state()

    def force_update_formula(self, new_formula_config: FormulaConfig) -> None:
        """Update the formula configuration and re-evaluate."""
        old_dependencies = self._dependencies.copy()

        # Update configuration
        self._formula_config = new_formula_config
        self._dependencies = new_formula_config.dependencies

        # Update entity attributes
        self._attr_unit_of_measurement = new_formula_config.unit_of_measurement
        self._attr_device_class = new_formula_config.device_class
        self._attr_state_class = new_formula_config.state_class
        self._attr_icon = new_formula_config.icon
        self._extra_attributes = new_formula_config.attributes.copy()

        # Update dependency tracking if needed
        if old_dependencies != self._dependencies:
            # Remove old listeners
            for listener in self._update_listeners:
                listener()
            self._update_listeners.clear()

            # Add new listeners
            if self._dependencies:
                self._update_listeners.append(
                    async_track_state_change_event(
                        self._hass,
                        list(self._dependencies),
                        self._handle_dependency_change,
                    )
                )

        # Clear evaluator cache for this formula
        self._evaluator.clear_cache()

        # Force re-evaluation
        self._hass.async_create_task(self._async_update_sensor())


class SensorManager:
    """Manages the lifecycle of synthetic sensors based on configuration."""

    def __init__(
        self,
        hass: HomeAssistant,
        name_resolver: NameResolver,
        add_entities_callback: AddEntitiesCallback,
    ):
        """Initialize the sensor manager."""
        self._hass = hass
        self._name_resolver = name_resolver
        self._add_entities = add_entities_callback
        self._logger = _LOGGER.getChild(self.__class__.__name__)

        # Initialize components
        self._evaluator = Evaluator(hass)

        # State tracking
        self._sensors: dict[str, list[DynamicSensor]] = (
            {}
        )  # Still keyed by unique_id temporarily
        self._sensors_by_entity_id: dict[str, DynamicSensor] = (
            {}
        )  # New: entity_id lookup
        self._sensor_states: dict[str, SensorState] = {}
        self._current_config: Config | None = None

    @property
    def managed_sensors(self) -> dict[str, list[DynamicSensor]]:
        """Get all managed sensors."""
        return self._sensors.copy()

    @property
    def sensor_states(self) -> dict[str, SensorState]:
        """Get current sensor states."""
        return self._sensor_states.copy()

    def get_sensor_by_entity_id(self, entity_id: str) -> DynamicSensor | None:
        """Get sensor by entity ID - primary method for service operations."""
        return self._sensors_by_entity_id.get(entity_id)

    def get_all_sensor_entities(self) -> list[DynamicSensor]:
        """Get all sensor entities."""
        return list(self._sensors_by_entity_id.values())

    async def load_configuration(self, config: Config) -> None:
        """Load a new configuration and update sensors accordingly."""
        _LOGGER.info("Loading configuration with %d sensors", len(config.sensors))

        old_config = self._current_config
        self._current_config = config

        try:
            # Determine what needs to be updated
            if old_config:
                await self._update_existing_sensors(old_config, config)
            else:
                await self._create_all_sensors(config)

            _LOGGER.info("Configuration loaded successfully")

        except Exception as err:
            _LOGGER.error(f"Failed to load configuration: {err}")
            # Restore old configuration if possible
            if old_config:
                self._current_config = old_config
            raise

    async def reload_configuration(self, config: Config) -> None:
        """Reload configuration, removing old sensors and creating new ones."""
        _LOGGER.info("Reloading configuration")

        # Remove all existing sensors
        await self._remove_all_sensors()

        # Load new configuration
        await self.load_configuration(config)

    async def remove_sensor(self, sensor_name: str) -> bool:
        """Remove a specific sensor and all its formulas."""
        if sensor_name not in self._sensors:
            return False

        # Clean up our tracking
        del self._sensors[sensor_name]
        self._sensor_states.pop(sensor_name, None)

        _LOGGER.info(f"Removed sensor: {sensor_name}")
        return True

    def get_sensor_statistics(self) -> dict[str, Any]:
        """Get statistics about managed sensors.

        Returns:
            dict: Statistics including counts, states, and performance data
        """
        total_sensors = sum(len(sensors) for sensors in self._sensors.values())
        active_sensors = sum(
            1
            for sensors in self._sensors.values()
            for sensor in sensors
            if sensor.available
        )

        return {
            "total_sensors": total_sensors,
            "active_sensors": active_sensors,
            "sensor_configs": len(self._sensors),
            "states": {
                name: {
                    "formula_states": state.formula_states,
                    "last_update": state.last_update.isoformat(),
                    "error_count": state.error_count,
                    "is_available": state.is_available,
                }
                for name, state in self._sensor_states.items()
            },
        }

    def _on_sensor_updated(
        self, sensor_name: str, formula_name: str, value: Any
    ) -> None:
        """Called when a sensor is successfully updated."""
        if sensor_name not in self._sensor_states:
            self._sensor_states[sensor_name] = SensorState(
                sensor_name=sensor_name, formula_states={}, last_update=dt_util.utcnow()
            )

        state = self._sensor_states[sensor_name]
        state.formula_states[formula_name] = value
        state.last_update = dt_util.utcnow()
        state.is_available = True

    async def _create_all_sensors(self, config: Config) -> None:
        """Create all sensors from scratch."""
        new_entities = []

        # Create sensors
        for sensor_config in config.sensors:
            if sensor_config.enabled:
                sensors = await self._create_sensor_entities(sensor_config)
                new_entities.extend(sensors)
                self._sensors[sensor_config.unique_id] = sensors

        # Add entities to Home Assistant
        if new_entities:
            self._add_entities(new_entities)
            _LOGGER.info(f"Created {len(new_entities)} sensor entities")

    async def _create_sensor_entities(
        self, sensor_config: SensorConfig
    ) -> list[DynamicSensor]:
        """Create entities for all formulas in a sensor configuration."""
        entities = []

        for formula_config in sensor_config.formulas:
            entity = DynamicSensor(
                self._hass, sensor_config, formula_config, self._evaluator, self
            )
            entities.append(entity)

            # Add to entity_id lookup for service operations
            self._sensors_by_entity_id[entity.entity_id] = entity

        return entities

    async def _update_existing_sensors(
        self, old_config: Config, new_config: Config
    ) -> None:
        """Update existing sensors based on configuration changes."""
        old_sensors = {s.unique_id: s for s in old_config.sensors}
        new_sensors = {s.unique_id: s for s in new_config.sensors}

        # Find sensors to remove
        to_remove = set(old_sensors.keys()) - set(new_sensors.keys())
        for sensor_name in to_remove:
            await self.remove_sensor(sensor_name)

        # Find sensors to add
        to_add = set(new_sensors.keys()) - set(old_sensors.keys())
        new_entities = []
        for sensor_name in to_add:
            sensor_config = new_sensors[sensor_name]
            if sensor_config.enabled:
                sensors = await self._create_sensor_entities(sensor_config)
                new_entities.extend(sensors)
                self._sensors[sensor_name] = sensors

        # Find sensors to update
        to_update = set(old_sensors.keys()) & set(new_sensors.keys())
        for sensor_name in to_update:
            old_sensor = old_sensors[sensor_name]
            new_sensor = new_sensors[sensor_name]
            await self._update_sensor_config(old_sensor, new_sensor)

        # Add new entities
        if new_entities:
            self._add_entities(new_entities)
            _LOGGER.info(f"Added {len(new_entities)} new sensor entities")

    async def _update_sensor_config(
        self, old_config: SensorConfig, new_config: SensorConfig
    ) -> None:
        """Update an existing sensor with new configuration."""
        # This is a simplified approach - remove and recreate if changes exist
        existing_sensors = self._sensors.get(old_config.name, [])

        # For now, remove and recreate if there are significant changes
        if existing_sensors:
            await self.remove_sensor(old_config.name)

            if new_config.enabled:
                sensors = await self._create_sensor_entities(new_config)
                self._sensors[new_config.name] = sensors
                self._add_entities(sensors)

    async def _remove_all_sensors(self) -> None:
        """Remove all managed sensors."""
        sensor_names = list(self._sensors.keys())
        for sensor_name in sensor_names:
            await self.remove_sensor(sensor_name)

    async def create_sensors(self, config: Config) -> list[DynamicSensor]:
        """Create sensors from configuration - public interface for testing."""
        _LOGGER.info(
            f"Creating sensors from config with {len(config.sensors)} sensor configs"
        )

        all_created_sensors = []

        # Create sensors
        for sensor_config in config.sensors:
            if sensor_config.enabled:
                sensors = await self._create_sensor_entities(sensor_config)
                all_created_sensors.extend(sensors)
                self._sensors[sensor_config.name] = sensors

        _LOGGER.info(f"Created {len(all_created_sensors)} sensor entities")
        return all_created_sensors

    def update_sensor_states(
        self, sensor_name: str, states: dict[str, float | int | str | bool]
    ) -> None:
        """Update the states for a sensor.

        Args:
            sensor_name: Name of the sensor
            states: Dictionary of formula_name -> value
        """
        if sensor_name in self._sensor_states:
            self._sensor_states[sensor_name].formula_states.update(states)
            self._sensor_states[sensor_name].last_update = dt_util.utcnow()
        else:
            self._sensor_states[sensor_name] = SensorState(
                sensor_name=sensor_name,
                formula_states=states,
                last_update=dt_util.utcnow(),
            )

    async def async_update_sensors(
        self, sensor_configs: list[SensorConfig] | None = None
    ) -> None:
        """Asynchronously update sensors based on configurations.

        Args:
            sensor_configs: Optional list of specific sensors to update.
                          If None, updates all managed sensors.
        """
        if sensor_configs is None:
            # Update all managed sensors
            for sensors_list in self._sensors.values():
                for sensor in sensors_list:
                    await sensor._async_update_sensor()
        else:
            # Update specific sensors
            for config in sensor_configs:
                if config.unique_id in self._sensors:
                    sensors = self._sensors[config.unique_id]
                    for sensor in sensors:
                        await sensor._async_update_sensor()

        self._logger.debug("Completed async sensor updates")
