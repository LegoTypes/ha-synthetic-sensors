"""Sensor manager for synthetic sensors."""
# pylint: disable=too-many-lines

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util, slugify

from .config_models import Config, FormulaConfig, SensorConfig
from .config_types import GlobalSettingsDict
from .evaluator import Evaluator
from .exceptions import FormulaEvaluationError
from .metadata_handler import MetadataHandler
from .name_resolver import NameResolver
from .type_definitions import DataProviderCallback, DataProviderChangeNotifier

if TYPE_CHECKING:
    from homeassistant.core import EventStateChangedData

    from .config_manager import ConfigManager
    from .storage_manager import StorageManager

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
    """Dynamic sensor that evaluates formulas and updates state."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: SensorConfig,
        evaluator: Evaluator,
        sensor_manager: SensorManager,
        manager_config: SensorManagerConfig | None = None,
        global_settings: GlobalSettingsDict | None = None,
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

        # Initialize metadata and apply to sensor
        self._setup_metadata_properties(global_settings)

        # State management
        self._attr_native_value: Any = None
        self._attr_available = True

        # Initialize calculated attributes storage
        self._calculated_attributes: dict[str, Any] = {}

        # Set base extra state attributes
        self._setup_base_attributes()

        # Tracking
        self._last_update: datetime | None = None
        self._update_listeners: list[Any] = []

        # Collect all dependencies from all formulas
        self._dependencies: set[str] = set()
        for formula in config.formulas:
            self._dependencies.update(formula.dependencies)

        # IMPORTANT: When using data provider callbacks, we still need to listen to state changes
        # to trigger re-evaluation. Add variable entity IDs to dependencies for state tracking.
        if self._evaluator.data_provider_callback:
            for formula in config.formulas:
                if formula.variables:
                    for _var_name, var_value in formula.variables.items():
                        if isinstance(var_value, str) and "." in var_value:
                            # This looks like an entity_id, add it to dependencies for state tracking
                            self._dependencies.add(var_value)
                            _LOGGER.debug(
                                "Added variable entity %s to dependencies for sensor %s (data provider mode)",
                                var_value,
                                self._attr_unique_id,
                            )

    def _setup_metadata_properties(self, global_settings: GlobalSettingsDict | None) -> None:
        """Set up metadata properties for the sensor."""
        metadata_handler = MetadataHandler()

        # Get global metadata from global_settings (if available)
        global_metadata = {}
        if global_settings:
            global_metadata = global_settings.get("metadata", {})

        # Merge metadata: global -> sensor -> formula (main formula)
        sensor_metadata = metadata_handler.merge_sensor_metadata(global_metadata, self._config)
        # For main formula (sensor entity), use the merged sensor metadata directly
        final_metadata = sensor_metadata.copy()

        # Apply any formula-level metadata overrides
        formula_metadata = getattr(self._main_formula, "metadata", {})
        final_metadata.update(formula_metadata)

        # Apply metadata properties to sensor
        self._apply_metadata_to_sensor(final_metadata)

    def _apply_metadata_to_sensor(self, metadata: dict[str, Any]) -> None:
        """Apply metadata properties to the sensor entity."""
        # Apply core metadata properties to sensor entity
        self._attr_native_unit_of_measurement = metadata.get("unit_of_measurement")
        self._attr_state_class = metadata.get("state_class")
        self._attr_icon = metadata.get("icon")

        # Convert device_class string to enum if needed
        device_class = metadata.get("device_class")
        if device_class:
            try:
                self._attr_device_class = SensorDeviceClass(device_class)
            except ValueError:
                self._attr_device_class = None
        else:
            self._attr_device_class = None

        # Apply additional metadata properties as HA sensor attributes
        # Skip the ones we've already handled above
        handled_keys = {"unit_of_measurement", "state_class", "icon", "device_class"}
        for key, value in metadata.items():
            if key not in handled_keys:
                attr_name = f"_attr_{key}"
                setattr(self, attr_name, value)

    def _setup_base_attributes(self) -> None:
        """Set up base extra state attributes."""
        base_attributes: dict[str, Any] = {}
        base_attributes["formula"] = self._main_formula.formula
        base_attributes["dependencies"] = list(self._main_formula.dependencies)
        if self._config.category:
            base_attributes["sensor_category"] = self._config.category
        self._attr_extra_state_attributes = base_attributes

    def _update_extra_state_attributes(self) -> None:
        """Update the extra state attributes with current values."""
        # Start with main formula attributes
        base_attributes: dict[str, Any] = self._main_formula.attributes.copy()

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
            or if data provider callback is available and HA lookups are disabled
        """
        if not formula_config.variables:
            return None

        # If data provider callback is available and HA lookups are disabled,
        # let the evaluator handle variable resolution through IntegrationResolutionStrategy
        if self._evaluator.data_provider_callback and not self._sensor_manager.allow_ha_lookups:
            return None

        context: dict[str, Any] = {}
        for var_name, entity_id in formula_config.variables.items():
            # If HA lookups are allowed or no data provider callback is available,
            # try to get values from HA state registry
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
                raise FormulaEvaluationError(f"Formula evaluation failed for {self.entity_id}: {error_msg}")

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

        # Update entity attributes from formula metadata
        formula_metadata = new_main_formula.metadata or {}
        self._apply_metadata_to_sensor(formula_metadata)

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

    @property
    def config(self) -> SensorConfig:
        """Get the sensor configuration."""
        return self._config

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
        self._allow_ha_lookups: bool = False  # Whether backing entities can fall back to HA lookups
        self._change_notifier: DataProviderChangeNotifier | None = None  # Callback for data change notifications

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
            _LOGGER.error("Failed to load configuration: %s", err)
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

        _LOGGER.debug("Removed sensor: %s", sensor_unique_id)
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
            _LOGGER.debug("Created %d sensor entities", len(new_entities))

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
                _LOGGER.debug("Generated entity_id '%s' for sensor '%s'", generated_entity_id, sensor_config.unique_id)
            except ValueError as e:
                _LOGGER.error("Failed to generate entity_id for sensor '%s': %s", sensor_config.unique_id, e)
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

        # Get global settings from current config
        global_settings: GlobalSettingsDict | None = None
        if self._current_config and self._current_config.global_settings:
            global_settings = self._current_config.global_settings

        return DynamicSensor(self._hass, sensor_config, self._evaluator, self, manager_config, global_settings)

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
            _LOGGER.debug("Added %d new sensor entities", len(new_entities))

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
        _LOGGER.debug("Creating sensors from config with %d sensor configs", len(config.sensors))

        # Store the config temporarily for global settings access
        old_config = self._current_config
        self._current_config = config

        all_created_sensors: list[DynamicSensor] = []

        try:
            # Create one entity per sensor
            for sensor_config in config.sensors:
                if sensor_config.enabled:
                    sensor = await self._create_sensor_entity(sensor_config)
                    all_created_sensors.append(sensor)
                    self._sensors_by_unique_id[sensor_config.unique_id] = sensor
                    self._sensors_by_entity_id[sensor.entity_id] = sensor

            _LOGGER.debug("Created %d sensor entities", len(all_created_sensors))
            return all_created_sensors
        finally:
            # Restore the old config
            self._current_config = old_config

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
    def register_data_provider_entities(
        self, entity_ids: set[str], allow_ha_lookups: bool = False, change_notifier: DataProviderChangeNotifier | None = None
    ) -> None:
        """Register entities that the integration can provide data for.

        This replaces any existing entity list with the new one.

        Args:
            entity_ids: Set of entity IDs that the integration can provide data for
            allow_ha_lookups: If True, backing entities can fall back to HA state lookups
                            when not found in data provider. If False (default), backing
                            entities are always virtual and only use data provider callback.
            change_notifier: Optional callback that the integration can call when backing
                           entity data changes to trigger selective sensor updates.
        """
        _LOGGER.debug(
            "Registered %d entities for integration data provider (allow_ha_lookups=%s, change_notifier=%s)",
            len(entity_ids),
            allow_ha_lookups,
            change_notifier is not None,
        )

        # Store the registered entities and lookup preference
        self._registered_entities = entity_ids.copy()
        self._allow_ha_lookups = allow_ha_lookups
        self._change_notifier = change_notifier

        # Update the evaluator if it has the new registration support
        if hasattr(self._evaluator, "update_integration_entities"):
            self._evaluator.update_integration_entities(entity_ids)

    def update_data_provider_entities(
        self, entity_ids: set[str], allow_ha_lookups: bool = False, change_notifier: DataProviderChangeNotifier | None = None
    ) -> None:
        """Update the registered entity list (replaces existing list).

        Args:
            entity_ids: Updated set of entity IDs the integration can provide data for
            allow_ha_lookups: If True, backing entities can fall back to HA state lookups
                            when not found in data provider. If False (default), backing
                            entities are always virtual and only use data provider callback.
            change_notifier: Optional callback that the integration can call when backing
                           entity data changes to trigger selective sensor updates.
        """
        self.register_data_provider_entities(entity_ids, allow_ha_lookups, change_notifier)

    def get_registered_entities(self) -> set[str]:
        """
        Get all entities registered with the data provider.

        Returns:
            Set of entity IDs registered for integration data access
        """
        return self._registered_entities.copy()

    async def async_update_sensors_for_entities(self, changed_entity_ids: set[str]) -> None:
        """Update only sensors that use the specified backing entities.

        This method provides selective sensor updates based on which backing entities
        have changed, improving efficiency over updating all sensors.

        Args:
            changed_entity_ids: Set of backing entity IDs that have changed
        """
        if not changed_entity_ids:
            return

        # Find sensors that use any of the changed backing entities
        affected_sensor_configs = []
        for sensor in self._sensors_by_unique_id.values():
            sensor_backing_entities = self._extract_backing_entities_from_sensor(sensor.config)
            if sensor_backing_entities.intersection(changed_entity_ids):
                affected_sensor_configs.append(sensor.config)

        if affected_sensor_configs:
            await self.async_update_sensors(affected_sensor_configs)
            _LOGGER.debug(
                "Updated %d sensors affected by changes to backing entities: %s",
                len(affected_sensor_configs),
                changed_entity_ids,
            )
        else:
            _LOGGER.debug("No sensors affected by changes to backing entities: %s", changed_entity_ids)

    def _extract_backing_entities_from_sensor(self, sensor_config: SensorConfig) -> set[str]:
        """Extract backing entity IDs from a sensor configuration.

        This analyzes the sensor's formulas and variables to find entity IDs that
        would be resolved by the IntegrationResolutionStrategy (i.e., backing entities).

        Args:
            sensor_config: The sensor configuration to analyze

        Returns:
            Set of entity IDs that are backing entities for this sensor
        """
        backing_entities = set()

        for formula in sensor_config.formulas:
            if formula.variables:
                for _var_name, var_value in formula.variables.items():
                    # Check if this looks like an entity ID that would use integration data provider
                    if (
                        isinstance(var_value, str)
                        and var_value.startswith("sensor.")
                        and var_value in self._registered_entities
                    ):
                        backing_entities.add(var_value)
                        _LOGGER.debug("Found backing entity %s for sensor %s", var_value, sensor_config.unique_id)

        return backing_entities

    def _extract_backing_entities_from_sensors(self, sensor_configs: list[SensorConfig]) -> set[str]:
        """Extract all backing entity IDs from a list of sensor configurations.

        Args:
            sensor_configs: List of sensor configurations to analyze

        Returns:
            Set of all entity IDs that are backing entities for these sensors
        """
        all_backing_entities = set()
        for sensor_config in sensor_configs:
            backing_entities = self._extract_backing_entities_from_sensor(sensor_config)
            all_backing_entities.update(backing_entities)

        return all_backing_entities

    async def add_sensor_with_backing_entities(self, sensor_config: SensorConfig, allow_ha_lookups: bool | None = None) -> bool:
        """Add a sensor and automatically register its backing entities.

        This is the enhanced CRUD method that makes backing entity management invisible.

        Args:
            sensor_config: The sensor configuration to add
            allow_ha_lookups: If specified, overrides the current HA lookup setting for backing entities.
                            If None, uses the current setting.

        Returns:
            True if sensor was added successfully
        """
        try:
            # Extract backing entities from this sensor
            backing_entities = self._extract_backing_entities_from_sensor(sensor_config)

            # Add backing entities to our registered entities
            if backing_entities:
                updated_entities = self._registered_entities.union(backing_entities)
                # Use provided allow_ha_lookups or keep current setting
                lookup_setting = allow_ha_lookups if allow_ha_lookups is not None else self._allow_ha_lookups
                self.register_data_provider_entities(updated_entities, lookup_setting)
                _LOGGER.debug(
                    "Auto-registered %d backing entities for sensor %s: %s (allow_ha_lookups=%s)",
                    len(backing_entities),
                    sensor_config.unique_id,
                    backing_entities,
                    lookup_setting,
                )

            # Create the sensor entity
            if sensor_config.enabled:
                sensor = await self._create_sensor_entity(sensor_config)
                self._sensors_by_unique_id[sensor_config.unique_id] = sensor
                self._sensors_by_entity_id[sensor.entity_id] = sensor
                self._add_entities_callback([sensor])
                _LOGGER.debug("Added sensor %s with automatic backing entity registration", sensor_config.unique_id)
                return True

            _LOGGER.debug("Sensor %s is disabled, not creating entity", sensor_config.unique_id)
            return True

        except Exception as e:
            _LOGGER.error("Failed to add sensor %s: %s", sensor_config.unique_id, e)
            return False

    async def remove_sensor_with_backing_entities(
        self, sensor_unique_id: str, cleanup_orphaned_backing_entities: bool = True
    ) -> bool:
        """Remove a sensor and optionally clean up orphaned backing entities.

        This is the enhanced CRUD method that makes backing entity management invisible.

        Args:
            sensor_unique_id: The unique ID of the sensor to remove
            cleanup_orphaned_backing_entities: Whether to remove backing entities that are no longer used

        Returns:
            True if sensor was removed successfully
        """
        if sensor_unique_id not in self._sensors_by_unique_id:
            return False

        sensor = self._sensors_by_unique_id[sensor_unique_id]

        # Get the sensor's configuration to find its backing entities
        sensor_config = sensor.config

        # Clean up our tracking
        del self._sensors_by_unique_id[sensor_unique_id]
        self._sensors_by_entity_id.pop(sensor.entity_id, None)
        self._sensor_states.pop(sensor_unique_id, None)

        # If requested, clean up orphaned backing entities
        if cleanup_orphaned_backing_entities and sensor_config:
            # Find backing entities that were used by this sensor
            removed_sensor_backing_entities = self._extract_backing_entities_from_sensor(sensor_config)

            if removed_sensor_backing_entities:
                # Find which backing entities are still needed by remaining sensors
                remaining_sensor_configs = []
                for remaining_sensor in self._sensors_by_unique_id.values():
                    if hasattr(remaining_sensor, "config"):
                        remaining_sensor_configs.append(remaining_sensor.config)

                still_needed_backing_entities = self._extract_backing_entities_from_sensors(remaining_sensor_configs)

                # Find orphaned backing entities (used by removed sensor but not by any remaining sensor)
                orphaned_backing_entities = removed_sensor_backing_entities - still_needed_backing_entities

                if orphaned_backing_entities:
                    # Remove orphaned backing entities from registered entities
                    updated_entities = self._registered_entities - orphaned_backing_entities
                    self.register_data_provider_entities(updated_entities, self._allow_ha_lookups)
                    _LOGGER.debug(
                        "Auto-removed %d orphaned backing entities after removing sensor %s: %s",
                        len(orphaned_backing_entities),
                        sensor_unique_id,
                        orphaned_backing_entities,
                    )

        _LOGGER.debug("Removed sensor: %s", sensor_unique_id)
        return True

    def register_with_storage_manager(self, storage_manager: StorageManager) -> None:
        """
        Register this SensorManager and its Evaluator with a StorageManager's entity change handler.

        Args:
            storage_manager: StorageManager instance to register with
        """
        storage_manager.register_sensor_manager(self)
        storage_manager.register_evaluator(self._evaluator)
        self._logger.debug("Registered SensorManager and Evaluator with StorageManager")

    def unregister_from_storage_manager(self, storage_manager: StorageManager) -> None:
        """
        Unregister this SensorManager and its Evaluator from a StorageManager's entity change handler.

        Args:
            storage_manager: StorageManager instance to unregister from
        """
        storage_manager.unregister_sensor_manager(self)
        storage_manager.unregister_evaluator(self._evaluator)
        self._logger.debug("Unregistered SensorManager and Evaluator from StorageManager")

    @property
    def evaluator(self) -> Evaluator:
        """Get the evaluator instance used by this SensorManager."""
        return self._evaluator

    @property
    def allow_ha_lookups(self) -> bool:
        """Get whether backing entities can fall back to HA state lookups."""
        return self._allow_ha_lookups

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
            # Device not found - this should raise an error per Phase 1 requirements
            integration_domain = self._manager_config.integration_domain
            raise ValueError(
                f"Device not found for identifier '{device_identifier}' in domain '{integration_domain}'. "
                f"Ensure the device is registered before creating synthetic sensors."
            )

        # Fallback for sensors without device association (legacy behavior)
        return f"sensor.{sensor_key}"
