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

if TYPE_CHECKING:
    from .config_manager import ConfigManager
    from .evaluator import Evaluator
    from .name_resolver import NameResolver
    from .storage_manager import StorageManager

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .config_manager import AttributeValue, Config, FormulaConfig, SensorConfig
from .evaluator import Evaluator
from .name_resolver import NameResolver
from .types import DataProviderCallback

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


@dataclass
class SensorManagerConfig:
    """Configuration for SensorManager with device integration support."""

    integration_domain: str = "synthetic_sensors"  # Integration domain for device lookup
    device_info: DeviceInfo | None = None
    unique_id_prefix: str = ""  # Optional prefix for unique IDs (for compatibility)
    lifecycle_managed_externally: bool = False
    # Additional HA dependencies that parent integration can provide
    hass_instance: HomeAssistant | None = None  # Allow parent to override hass
    config_manager: ConfigManager | None = None  # Parent can provide its own config manager
    evaluator: Evaluator | None = None  # Parent can provide custom evaluator
    name_resolver: NameResolver | None = None  # Parent can provide custom name resolver
    data_provider_callback: DataProviderCallback | None = None  # Callback for integration data access


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

        # Set unique ID with optional prefix for compatibility
        if self._manager_config.unique_id_prefix:
            self._attr_unique_id = f"{self._manager_config.unique_id_prefix}_{config.unique_id}"
        else:
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
        self._dependencies: set[str] = set()
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
            self._update_listeners.append(
                async_track_state_change_event(self._hass, list(self._dependencies), self._handle_dependency_change)
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
    async def _handle_dependency_change(self, event: Event[EventStateChangedData]) -> None:
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
                self._sensor_manager.on_sensor_updated(
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
                _LOGGER.debug(
                    "Sensor %s set to unavailable due to unknown dependencies",
                    self.entity_id,
                )
            else:
                self._attr_available = False
                error_msg = main_result.get("error", "Unknown evaluation error")
                # Treat formula evaluation failure as a fatal error
                _LOGGER.error("Formula evaluation failed for %s: %s", self.entity_id, error_msg)
                raise Exception(f"Formula evaluation failed for {self.entity_id}: {error_msg}")

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

    @property
    def config_unique_id(self) -> str:
        """Get the unique ID from the sensor configuration."""
        return self._config.unique_id

    async def async_update_sensor(self) -> None:
        """Update the sensor value and calculated attributes (public method)."""
        await self._async_update_sensor()

    # ...existing code...


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

        # Integration data provider tracking
        self._registered_entities: set[str] = set()  # entity_ids registered by integration

        # Configuration tracking
        self._current_config: Config | None = None

        # Initialize components - use parent-provided instances if available
        self._evaluator = self._manager_config.evaluator or Evaluator(
            self._hass,
            data_provider_callback=self._manager_config.data_provider_callback,
        )
        self._config_manager = self._manager_config.config_manager
        self._logger = _LOGGER.getChild(self.__class__.__name__)

        # Device registry for device association
        self._device_registry = dr.async_get(self._hass)

        _LOGGER.debug("SensorManager initialized with device integration support")

    def _get_existing_device_info(self, device_identifier: str) -> DeviceInfo | None:
        """Get device info for an existing device by identifier."""
        # Look up existing device in registry using integration domain
        integration_domain = self._manager_config.integration_domain
        lookup_identifier = (integration_domain, device_identifier)

        _LOGGER.debug(
            "DEVICE_LOOKUP_DEBUG: Looking for device with identifier %s in integration domain %s",
            device_identifier,
            integration_domain,
        )

        device_entry = self._device_registry.async_get_device(identifiers={lookup_identifier})

        if device_entry:
            _LOGGER.debug(
                "DEVICE_LOOKUP_DEBUG: Found existing device - ID: %s, Name: %s, Identifiers: %s",
                device_entry.id,
                device_entry.name,
                device_entry.identifiers,
            )
            return DeviceInfo(
                identifiers={(integration_domain, device_identifier)},
                name=device_entry.name,
                manufacturer=device_entry.manufacturer,
                model=device_entry.model,
                sw_version=device_entry.sw_version,
                hw_version=device_entry.hw_version,
            )
        else:
            _LOGGER.debug(
                "DEVICE_LOOKUP_DEBUG: No existing device found for identifier %s",
                lookup_identifier,
            )

        return None

    def _create_new_device_info(self, sensor_config: SensorConfig) -> DeviceInfo:
        """Create device info for a new device."""
        if not sensor_config.device_identifier:
            raise ValueError("device_identifier is required to create device info")

        integration_domain = self._manager_config.integration_domain
        return DeviceInfo(
            identifiers={(integration_domain, sensor_config.device_identifier)},
            name=sensor_config.device_name or f"Device {sensor_config.device_identifier}",
            manufacturer=sensor_config.device_manufacturer,
            model=sensor_config.device_model,
            sw_version=sensor_config.device_sw_version,
            hw_version=sensor_config.device_hw_version,
            suggested_area=sensor_config.suggested_area,
        )

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
        _LOGGER.debug("Loading configuration with %d sensors", len(config.sensors))

        old_config = self._current_config
        self._current_config = config

        try:
            # Determine what needs to be updated
            if old_config:
                await self._update_existing_sensors(old_config, config)
            else:
                await self._create_all_sensors(config)

            _LOGGER.debug("Configuration loaded successfully")

        except Exception as err:
            _LOGGER.error(f"Failed to load configuration: {err}")
            # Restore old configuration if possible
            if old_config:
                self._current_config = old_config
            raise

    async def reload_configuration(self, config: Config) -> None:
        """Reload configuration, removing old sensors and creating new ones."""
        _LOGGER.debug("Reloading configuration")

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

        _LOGGER.debug(f"Removed sensor: {sensor_unique_id}")
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

    def on_sensor_updated(
        self,
        sensor_unique_id: str,
        main_value: Any,
        calculated_attributes: dict[str, Any],
    ) -> None:
        """Called when a sensor is successfully updated (public method)."""
        self._on_sensor_updated(sensor_unique_id, main_value, calculated_attributes)

    async def _create_all_sensors(self, config: Config) -> None:
        """Create all sensors from scratch."""
        new_entities: list[DynamicSensor] = []

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
            _LOGGER.debug(f"Created {len(new_entities)} sensor entities")

    async def _create_sensor_entity(self, sensor_config: SensorConfig) -> DynamicSensor:
        """Create a sensor entity from configuration."""
        device_info = None

        if sensor_config.device_identifier:
            _LOGGER.debug(
                "DEVICE_ASSOCIATION_DEBUG: Creating sensor with device_identifier: %s",
                sensor_config.device_identifier,
            )

            # First try to find existing device
            device_info = self._get_existing_device_info(sensor_config.device_identifier)

            # If device doesn't exist and we have device metadata, create it
            if not device_info and any(
                [
                    sensor_config.device_name,
                    sensor_config.device_manufacturer,
                    sensor_config.device_model,
                ]
            ):
                _LOGGER.debug(
                    "DEVICE_ASSOCIATION_DEBUG: Creating new device for identifier %s",
                    sensor_config.device_identifier,
                )
                device_info = self._create_new_device_info(sensor_config)
            elif not device_info:
                _LOGGER.debug(
                    "DEVICE_ASSOCIATION_DEBUG: No existing device found and no device metadata provided for %s. Sensor will be created without device association.",
                    sensor_config.device_identifier,
                )

        # Phase 1: Generate entity_id if not explicitly provided
        if not sensor_config.entity_id:
            try:
                generated_entity_id = self._generate_entity_id(
                    sensor_key=sensor_config.unique_id,
                    device_identifier=sensor_config.device_identifier,
                    explicit_entity_id=sensor_config.entity_id,
                )
                # Create a copy of the sensor config with the generated entity_id
                sensor_config = SensorConfig(
                    unique_id=sensor_config.unique_id,
                    formulas=sensor_config.formulas,
                    name=sensor_config.name,
                    enabled=sensor_config.enabled,
                    update_interval=sensor_config.update_interval,
                    category=sensor_config.category,
                    description=sensor_config.description,
                    entity_id=generated_entity_id,
                    device_identifier=sensor_config.device_identifier,
                    device_name=sensor_config.device_name,
                    device_manufacturer=sensor_config.device_manufacturer,
                    device_model=sensor_config.device_model,
                    device_sw_version=sensor_config.device_sw_version,
                    device_hw_version=sensor_config.device_hw_version,
                    suggested_area=sensor_config.suggested_area,
                )
                _LOGGER.debug(f"Generated entity_id '{generated_entity_id}' for sensor '{sensor_config.unique_id}'")
            except ValueError as e:
                _LOGGER.error(f"Failed to generate entity_id for sensor '{sensor_config.unique_id}': {e}")
                raise

        # Create manager config with device info
        manager_config = SensorManagerConfig(
            device_info=device_info,
            unique_id_prefix=self._manager_config.unique_id_prefix,
            lifecycle_managed_externally=self._manager_config.lifecycle_managed_externally,
            hass_instance=self._manager_config.hass_instance,
            config_manager=self._manager_config.config_manager,
            evaluator=self._manager_config.evaluator,
            name_resolver=self._manager_config.name_resolver,
        )

        return DynamicSensor(self._hass, sensor_config, self._evaluator, self, manager_config)

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
        new_entities: list[DynamicSensor] = []
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
            _LOGGER.debug(f"Added {len(new_entities)} new sensor entities")

    async def _update_sensor_config(self, old_config: SensorConfig, new_config: SensorConfig) -> None:
        """Update an existing sensor with new configuration."""
        # Simplified approach - remove and recreate if changes exist
        existing_sensor = self._sensors_by_unique_id.get(old_config.unique_id)

        if existing_sensor:
            await self.remove_sensor(old_config.unique_id)

            if new_config.enabled:
                new_sensor = await self._create_sensor_entity(new_config)
                self._sensors_by_unique_id[new_sensor.config_unique_id] = new_sensor
                self._sensors_by_entity_id[new_sensor.entity_id] = new_sensor
                self._add_entities_callback([new_sensor])

    async def _remove_all_sensors(self) -> None:
        """Remove all managed sensors."""
        sensor_unique_ids = list(self._sensors_by_unique_id.keys())
        for sensor_unique_id in sensor_unique_ids:
            await self.remove_sensor(sensor_unique_id)

    async def cleanup_all_sensors(self) -> None:
        """Remove all managed sensors - public cleanup method."""
        await self._remove_all_sensors()

    async def create_sensors(self, config: Config) -> list[DynamicSensor]:
        """Create sensors from configuration - public interface for testing."""
        _LOGGER.debug(f"Creating sensors from config with {len(config.sensors)} sensor configs")

        all_created_sensors: list[DynamicSensor] = []

        # Create one entity per sensor
        for sensor_config in config.sensors:
            if sensor_config.enabled:
                sensor = await self._create_sensor_entity(sensor_config)
                all_created_sensors.append(sensor)
                self._sensors_by_unique_id[sensor_config.unique_id] = sensor
                self._sensors_by_entity_id[sensor.entity_id] = sensor

        _LOGGER.debug(f"Created {len(all_created_sensors)} sensor entities")
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
                await sensor.async_update_sensor()
        else:
            # Update specific sensors
            for config in sensor_configs:
                if config.unique_id in self._sensors_by_unique_id:
                    sensor = self._sensors_by_unique_id[config.unique_id]
                    await sensor.async_update_sensor()

        self._logger.debug("Completed async sensor updates")

    # New push-based registration API
    def register_data_provider_entities(self, entity_ids: set[str]) -> None:
        """Register entities that the integration can provide data for.

        This replaces any existing entity list with the new one.

        Args:
            entity_ids: Set of entity IDs that the integration can provide data for
        """
        _LOGGER.debug("Registered %d entities for integration data provider", len(entity_ids))

        # Store the registered entities
        self._registered_entities = entity_ids.copy()

        # Update the evaluator if it has the new registration support
        if hasattr(self._evaluator, "update_integration_entities"):
            self._evaluator.update_integration_entities(entity_ids)

    def update_data_provider_entities(self, entity_ids: set[str]) -> None:
        """Update the registered entity list (replaces existing list).

        Args:
            entity_ids: Updated set of entity IDs the integration can provide data for
        """
        self.register_data_provider_entities(entity_ids)

    def get_registered_entities(self) -> set[str]:
        """
        Get all entities registered with the data provider.

        Returns:
            Set of entity IDs registered for integration data access
        """
        return self._registered_entities.copy()

    def register_with_storage_manager(self, storage_manager: StorageManager) -> None:
        """
        Register this SensorManager and its Evaluator with a StorageManager's entity change handler.

        Args:
            storage_manager: StorageManager instance to register with
        """
        from .storage_manager import StorageManager

        if not isinstance(storage_manager, StorageManager):
            raise ValueError("storage_manager must be a StorageManager instance")

        storage_manager.register_sensor_manager(self)
        storage_manager.register_evaluator(self._evaluator)
        self._logger.debug("Registered SensorManager and Evaluator with StorageManager")

    def unregister_from_storage_manager(self, storage_manager: StorageManager) -> None:
        """
        Unregister this SensorManager and its Evaluator from a StorageManager's entity change handler.

        Args:
            storage_manager: StorageManager instance to unregister from
        """
        from .storage_manager import StorageManager

        if not isinstance(storage_manager, StorageManager):
            raise ValueError("storage_manager must be a StorageManager instance")

        storage_manager.unregister_sensor_manager(self)
        storage_manager.unregister_evaluator(self._evaluator)
        self._logger.debug("Unregistered SensorManager and Evaluator from StorageManager")

    @property
    def evaluator(self) -> Evaluator:
        """Get the evaluator instance used by this SensorManager."""
        return self._evaluator

    def _resolve_device_name_prefix(self, device_identifier: str) -> str | None:
        """Resolve device name to slugified prefix for entity_id generation.

        Args:
            device_identifier: Device identifier to look up

        Returns:
            Slugified device name for use as entity_id prefix, or None if device not found
        """
        integration_domain = self._manager_config.integration_domain
        device_entry = self._device_registry.async_get_device(identifiers={(integration_domain, device_identifier)})

        if device_entry:
            # Use device name (user customizable) for prefix generation
            device_name = device_entry.name
            if device_name:
                # Import slugify function for consistent HA entity_id generation
                from homeassistant.util import slugify

                return slugify(device_name)

        return None

    def _generate_entity_id(
        self, sensor_key: str, device_identifier: str | None = None, explicit_entity_id: str | None = None
    ) -> str:
        """Generate entity_id for a synthetic sensor.

        Args:
            sensor_key: Sensor key from YAML configuration
            device_identifier: Device identifier for prefix resolution
            explicit_entity_id: Explicit entity_id override from configuration

        Returns:
            Generated entity_id following the pattern sensor.{device_prefix}_{sensor_key} or explicit override
        """
        # If explicit entity_id is provided, use it as-is (Phase 1 requirement)
        if explicit_entity_id:
            return explicit_entity_id

        # If device_identifier provided, resolve device prefix
        if device_identifier:
            device_prefix = self._resolve_device_name_prefix(device_identifier)
            if device_prefix:
                return f"sensor.{device_prefix}_{sensor_key}"
            else:
                # Device not found - this should raise an error per Phase 1 requirements
                integration_domain = self._manager_config.integration_domain
                raise ValueError(
                    f"Device not found for identifier '{device_identifier}' in domain '{integration_domain}'. "
                    f"Ensure the device is registered before creating synthetic sensors."
                )

        # Fallback for sensors without device association (legacy behavior)
        return f"sensor.{sensor_key}"
