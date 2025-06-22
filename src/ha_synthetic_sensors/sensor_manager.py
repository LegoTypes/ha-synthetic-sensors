"""
Sensor Manager - Dynamic sensor creation and lifecycle management.

This module handles the creation, updating, and removal of synthetic sensors
based on YAML configuration, providing the bridge between configuration
and Home Assistant sensor entities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .config_manager import AttributeValue, Config, FormulaConfig, SensorConfig
from .evaluator import Evaluator
from .name_resolver import NameResolver

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


@dataclass
class SensorManagerConfig:
    """Configuration for SensorManager with device integration support."""

    device_info: DeviceInfo | None = None
    lifecycle_managed_externally: bool = False
    # Additional HA dependencies that parent integration can provide
    hass_instance: HomeAssistant | None = None  # Allow parent to override hass
    config_manager: Any | None = None  # Parent can provide its own config manager
    evaluator: Any | None = None  # Parent can provide custom evaluator
    name_resolver: Any | None = None  # Parent can provide custom name resolver


@dataclass
class SensorState:
    """Represents the current state of a synthetic sensor."""

    sensor_name: str
    main_value: float | int | str | bool | None  # Main sensor state
    calculated_attributes: dict[str, Any]  # attribute_name -> value
    last_update: datetime
    error_count: int = 0
    is_available: bool = True


class DynamicSensor(RestoreEntity, SensorEntity):
    """A synthetic sensor entity with calculated attributes."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: SensorConfig,
        evaluator: Evaluator,
        sensor_manager: SensorManager,
        manager_config: SensorManagerConfig | None = None,
    ) -> None:
        """Initialize the dynamic sensor."""
        self._hass = hass
        self._config = config
        self._evaluator = evaluator
        self._sensor_manager = sensor_manager
        self._manager_config = manager_config or SensorManagerConfig()

        # Set unique ID directly from config
        self._attr_unique_id = config.unique_id
        self._attr_name = config.name or config.unique_id

        # Set entity_id explicitly if provided in config - MUST be set before parent __init__
        if config.entity_id:
            self.entity_id = config.entity_id

        # Set device info if provided by parent integration
        if self._manager_config.device_info:
            self._attr_device_info = self._manager_config.device_info

        # Find the main formula (first formula is always the main state)
        if not config.formulas:
            raise ValueError(f"Sensor '{config.unique_id}' must have at least one formula")

        self._main_formula = config.formulas[0]
        self._attribute_formulas = config.formulas[1:] if len(config.formulas) > 1 else []

        # Set entity attributes from main formula
        self._attr_native_unit_of_measurement = self._main_formula.unit_of_measurement

        # Convert device_class string to enum if needed
        if self._main_formula.device_class:
            try:
                self._attr_device_class = SensorDeviceClass(self._main_formula.device_class)
            except ValueError:
                self._attr_device_class = None
        else:
            self._attr_device_class = None

        self._attr_state_class = self._main_formula.state_class
        self._attr_icon = self._main_formula.icon

        # State management
        self._attr_native_value: Any = None
        self._attr_available = True

        # Initialize calculated attributes storage
        self._calculated_attributes: dict[str, Any] = {}

        # Set base extra state attributes
        base_attributes: dict[str, AttributeValue] = {}
        base_attributes["formula"] = self._main_formula.formula
        base_attributes["dependencies"] = list(self._main_formula.dependencies)
        if config.category:
            base_attributes["sensor_category"] = config.category
        self._attr_extra_state_attributes = base_attributes

        # Tracking
        self._last_update: datetime | None = None
        self._update_listeners: list[Any] = []

        # Collect all dependencies from all formulas
        self._dependencies = set()
        for formula in config.formulas:
            self._dependencies.update(formula.dependencies)

    def _update_extra_state_attributes(self) -> None:
        """Update the extra state attributes with current values."""
        # Start with main formula attributes
        base_attributes: dict[str, AttributeValue] = self._main_formula.attributes.copy()

        # Add calculated attributes from other formulas
        base_attributes.update(self._calculated_attributes)

        # Add metadata
        base_attributes["formula"] = self._main_formula.formula
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
            self._update_listeners.append(async_track_state_change_event(self._hass, list(self._dependencies), self._handle_dependency_change))

        # Initial evaluation
        await self._async_update_sensor()

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal."""
        # Clean up listeners
        for listener in self._update_listeners:
            listener()
        self._update_listeners.clear()

    @callback
    async def _handle_dependency_change(self, event: Any) -> None:
        """Handle when a dependency entity changes."""
        await self._async_update_sensor()

    def _build_variable_context(self, formula_config: FormulaConfig) -> dict[str, Any] | None:
        """Build variable context from formula config for evaluation.

        Args:
            formula_config: Formula configuration with variables

        Returns:
            Dictionary mapping variable names to entity state values, or None if no variables
        """
        if not formula_config.variables:
            return None

        context: dict[str, Any] = {}
        for var_name, entity_id in formula_config.variables.items():
            state = self._hass.states.get(entity_id)
            if state is not None:
                try:
                    # Try to get numeric value
                    numeric_value = float(state.state)
                    context[var_name] = numeric_value
                except (ValueError, TypeError):
                    # Fall back to string value for non-numeric states
                    context[var_name] = state.state
            else:
                # Entity not found - this will cause appropriate evaluation failure
                context[var_name] = None

        return context if context else None

    async def _async_update_sensor(self) -> None:
        """Update the sensor value and calculated attributes by evaluating formulas."""
        try:
            # Build variable context for the main formula
            main_context = self._build_variable_context(self._main_formula)

            # Evaluate the main formula with variable context
            main_result = self._evaluator.evaluate_formula(self._main_formula, main_context)

            if main_result["success"] and main_result["value"] is not None:
                self._attr_native_value = main_result["value"]
                self._attr_available = True
                self._last_update = dt_util.utcnow()

                # Evaluate calculated attributes
                self._calculated_attributes.clear()
                for attr_formula in self._attribute_formulas:
                    # Build variable context for each attribute formula
                    attr_context = self._build_variable_context(attr_formula)
                    attr_result = self._evaluator.evaluate_formula(attr_formula, attr_context)
                    if attr_result["success"] and attr_result["value"] is not None:
                        # Use formula ID as the attribute name
                        attr_name = attr_formula.id
                        self._calculated_attributes[attr_name] = attr_result["value"]

                # Update extra state attributes with calculated values
                self._update_extra_state_attributes()

                # Notify sensor manager of successful update
                self._sensor_manager._on_sensor_updated(
                    self._config.unique_id,
                    main_result["value"],
                    self._calculated_attributes.copy(),
                )
            elif main_result["success"] and main_result.get("state") == "unknown":
                # Handle case where evaluation succeeded but dependencies are unavailable
                # This is not an error - just set sensor to unavailable state until dependencies are ready
                self._attr_native_value = None
                self._attr_available = False
                self._last_update = dt_util.utcnow()
                _LOGGER.debug("Sensor %s set to unavailable due to unknown dependencies", self.entity_id)
            else:
                self._attr_available = False
                error_msg = main_result.get("error", "Unknown evaluation error")
                _LOGGER.warning("Formula evaluation failed for %s: %s", self.entity_id, error_msg)

            # Schedule entity update
            self.async_write_ha_state()

        except Exception as err:
            self._attr_available = False
            _LOGGER.error("Error updating sensor %s: %s", self.entity_id, err)
            self.async_write_ha_state()

    async def force_update_formula(
        self,
        new_main_formula: FormulaConfig,
        new_attr_formulas: list[FormulaConfig] | None = None,
    ) -> None:
        """Update the formula configuration and re-evaluate."""
        old_dependencies = self._dependencies.copy()

        # Update configuration
        self._main_formula = new_main_formula
        self._attribute_formulas = new_attr_formulas or []

        # Recalculate dependencies
        self._dependencies = set()
        all_formulas = [self._main_formula, *self._attribute_formulas]
        for formula in all_formulas:
            self._dependencies.update(formula.dependencies)

        # Update entity attributes from main formula
        self._attr_native_unit_of_measurement = new_main_formula.unit_of_measurement

        # Convert device_class string to enum if needed
        if new_main_formula.device_class:
            try:
                self._attr_device_class = SensorDeviceClass(new_main_formula.device_class)
            except ValueError:
                self._attr_device_class = None
        else:
            self._attr_device_class = None

        self._attr_state_class = new_main_formula.state_class
        self._attr_icon = new_main_formula.icon

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

        # Clear evaluator cache
        self._evaluator.clear_cache()

        # Force re-evaluation
        await self._async_update_sensor()


class SensorManager:
    """Manages the lifecycle of synthetic sensors based on configuration."""

    def __init__(
        self,
        hass: HomeAssistant,
        name_resolver: NameResolver,
        add_entities_callback: AddEntitiesCallback,
        manager_config: SensorManagerConfig | None = None,
    ):
        """Initialize the sensor manager.

        Args:
            hass: Home Assistant instance (can be overridden by manager_config.hass_instance)
            name_resolver: Name resolver for entity dependencies (can be overridden by manager_config.name_resolver)
            add_entities_callback: Callback to add entities to HA
            manager_config: Configuration for device integration support
        """
        self._manager_config = manager_config or SensorManagerConfig()

        # Use dependencies from parent integration if provided, otherwise use defaults
        self._hass = self._manager_config.hass_instance or hass
        self._name_resolver = self._manager_config.name_resolver or name_resolver
        self._add_entities_callback = add_entities_callback

        # Sensor tracking
        self._sensors_by_unique_id: dict[str, DynamicSensor] = {}  # unique_id -> sensor
        self._sensors_by_entity_id: dict[str, DynamicSensor] = {}  # entity_id -> sensor
        self._sensor_states: dict[str, SensorState] = {}  # unique_id -> state

        # Configuration tracking
        self._current_config: Config | None = None

        # Initialize components - use parent-provided instances if available
        self._evaluator = self._manager_config.evaluator or Evaluator(self._hass)
        self._config_manager = self._manager_config.config_manager
        self._logger = _LOGGER.getChild(self.__class__.__name__)

        _LOGGER.debug("SensorManager initialized with device integration support")

    @property
    def managed_sensors(self) -> dict[str, DynamicSensor]:
        """Get all managed sensors."""
        return self._sensors_by_unique_id.copy()

    @property
    def sensor_states(self) -> dict[str, SensorState]:
        """Get current sensor states."""
        return self._sensor_states.copy()

    def get_sensor_by_entity_id(self, entity_id: str) -> DynamicSensor | None:
        """Get sensor by entity ID - primary method for service operations."""
        return self._sensors_by_entity_id.get(entity_id)

    def get_all_sensor_entities(self) -> list[DynamicSensor]:
        """Get all sensor entities."""
        return list(self._sensors_by_unique_id.values())

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

    async def remove_sensor(self, sensor_unique_id: str) -> bool:
        """Remove a specific sensor."""
        if sensor_unique_id not in self._sensors_by_unique_id:
            return False

        sensor = self._sensors_by_unique_id[sensor_unique_id]

        # Clean up our tracking
        del self._sensors_by_unique_id[sensor_unique_id]
        self._sensors_by_entity_id.pop(sensor.entity_id, None)
        self._sensor_states.pop(sensor_unique_id, None)

        _LOGGER.info(f"Removed sensor: {sensor_unique_id}")
        return True

    def get_sensor_statistics(self) -> dict[str, Any]:
        """Get statistics about managed sensors."""
        total_sensors = len(self._sensors_by_unique_id)
        active_sensors = sum(1 for sensor in self._sensors_by_unique_id.values() if sensor.available)

        return {
            "total_sensors": total_sensors,
            "active_sensors": active_sensors,
            "states": {
                unique_id: {
                    "main_value": state.main_value,
                    "calculated_attributes": state.calculated_attributes,
                    "last_update": state.last_update.isoformat(),
                    "error_count": state.error_count,
                    "is_available": state.is_available,
                }
                for unique_id, state in self._sensor_states.items()
            },
        }

    def _on_sensor_updated(
        self,
        sensor_unique_id: str,
        main_value: Any,
        calculated_attributes: dict[str, Any],
    ) -> None:
        """Called when a sensor is successfully updated."""
        if sensor_unique_id not in self._sensor_states:
            self._sensor_states[sensor_unique_id] = SensorState(
                sensor_name=sensor_unique_id,
                main_value=main_value,
                calculated_attributes=calculated_attributes,
                last_update=dt_util.utcnow(),
            )
        else:
            state = self._sensor_states[sensor_unique_id]
            state.main_value = main_value
            state.calculated_attributes = calculated_attributes
            state.last_update = dt_util.utcnow()
            state.is_available = True

    async def _create_all_sensors(self, config: Config) -> None:
        """Create all sensors from scratch."""
        new_entities = []

        # Create one entity per sensor
        for sensor_config in config.sensors:
            if sensor_config.enabled:
                sensor = await self._create_sensor_entity(sensor_config)
                new_entities.append(sensor)
                self._sensors_by_unique_id[sensor_config.unique_id] = sensor
                self._sensors_by_entity_id[sensor.entity_id] = sensor

        # Add entities to Home Assistant
        if new_entities:
            self._add_entities_callback(new_entities)
            _LOGGER.info(f"Created {len(new_entities)} sensor entities")

    async def _create_sensor_entity(self, sensor_config: SensorConfig) -> DynamicSensor:
        """Create a sensor entity from configuration."""
        return DynamicSensor(self._hass, sensor_config, self._evaluator, self, self._manager_config)

    async def _update_existing_sensors(self, old_config: Config, new_config: Config) -> None:
        """Update existing sensors based on configuration changes."""
        old_sensors = {s.unique_id: s for s in old_config.sensors}
        new_sensors = {s.unique_id: s for s in new_config.sensors}

        # Find sensors to remove
        to_remove = set(old_sensors.keys()) - set(new_sensors.keys())
        for sensor_unique_id in to_remove:
            await self.remove_sensor(sensor_unique_id)

        # Find sensors to add
        to_add = set(new_sensors.keys()) - set(old_sensors.keys())
        new_entities = []
        for sensor_unique_id in to_add:
            sensor_config = new_sensors[sensor_unique_id]
            if sensor_config.enabled:
                sensor = await self._create_sensor_entity(sensor_config)
                new_entities.append(sensor)
                self._sensors_by_unique_id[sensor_config.unique_id] = sensor
                self._sensors_by_entity_id[sensor.entity_id] = sensor

        # Find sensors to update
        to_update = set(old_sensors.keys()) & set(new_sensors.keys())
        for sensor_unique_id in to_update:
            old_sensor = old_sensors[sensor_unique_id]
            new_sensor = new_sensors[sensor_unique_id]
            await self._update_sensor_config(old_sensor, new_sensor)

        # Add new entities
        if new_entities:
            self._add_entities_callback(new_entities)
            _LOGGER.info(f"Added {len(new_entities)} new sensor entities")

    async def _update_sensor_config(self, old_config: SensorConfig, new_config: SensorConfig) -> None:
        """Update an existing sensor with new configuration."""
        # Simplified approach - remove and recreate if changes exist
        existing_sensor = self._sensors_by_unique_id.get(old_config.unique_id)

        if existing_sensor:
            await self.remove_sensor(old_config.unique_id)

            if new_config.enabled:
                new_sensor = await self._create_sensor_entity(new_config)
                self._sensors_by_unique_id[new_config.unique_id] = new_sensor
                self._sensors_by_entity_id[new_sensor.entity_id] = new_sensor
                self._add_entities_callback([new_sensor])

    async def _remove_all_sensors(self) -> None:
        """Remove all managed sensors."""
        sensor_unique_ids = list(self._sensors_by_unique_id.keys())
        for sensor_unique_id in sensor_unique_ids:
            await self.remove_sensor(sensor_unique_id)

    async def create_sensors(self, config: Config) -> list[DynamicSensor]:
        """Create sensors from configuration - public interface for testing."""
        _LOGGER.info(f"Creating sensors from config with {len(config.sensors)} sensor configs")

        all_created_sensors = []

        # Create one entity per sensor
        for sensor_config in config.sensors:
            if sensor_config.enabled:
                sensor = await self._create_sensor_entity(sensor_config)
                all_created_sensors.append(sensor)
                self._sensors_by_unique_id[sensor_config.unique_id] = sensor
                self._sensors_by_entity_id[sensor.entity_id] = sensor

        _LOGGER.info(f"Created {len(all_created_sensors)} sensor entities")
        return all_created_sensors

    def update_sensor_states(
        self,
        sensor_unique_id: str,
        main_value: Any,
        calculated_attributes: dict[str, Any] | None = None,
    ) -> None:
        """Update the state for a sensor."""
        calculated_attributes = calculated_attributes or {}

        if sensor_unique_id in self._sensor_states:
            state = self._sensor_states[sensor_unique_id]
            state.main_value = main_value
            state.calculated_attributes.update(calculated_attributes)
            state.last_update = dt_util.utcnow()
        else:
            self._sensor_states[sensor_unique_id] = SensorState(
                sensor_name=sensor_unique_id,
                main_value=main_value,
                calculated_attributes=calculated_attributes,
                last_update=dt_util.utcnow(),
            )

    async def async_update_sensors(self, sensor_configs: list[SensorConfig] | None = None) -> None:
        """Asynchronously update sensors based on configurations."""
        if sensor_configs is None:
            # Update all managed sensors
            for sensor in self._sensors_by_unique_id.values():
                await sensor._async_update_sensor()
        else:
            # Update specific sensors
            for config in sensor_configs:
                if config.unique_id in self._sensors_by_unique_id:
                    sensor = self._sensors_by_unique_id[config.unique_id]
                    await sensor._async_update_sensor()

        self._logger.debug("Completed async sensor updates")
