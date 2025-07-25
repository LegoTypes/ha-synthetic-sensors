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
from .cross_sensor_reference_manager import CrossSensorReferenceManager
from .evaluator import Evaluator
from .evaluator_phases.dependency_management.generic_dependency_manager import GenericDependencyManager
from .exceptions import CrossSensorResolutionError, DependencyValidationError, FormulaEvaluationError, MissingDependencyError
from .metadata_handler import MetadataHandler
from .name_resolver import NameResolver
from .type_definitions import DataProviderCallback, DataProviderChangeNotifier, EvaluationResult

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

        # Initialize attribute dependency manager for proper evaluation order
        self._attribute_dependency_manager = GenericDependencyManager()

        # Set base extra state attributes
        self._setup_base_attributes()

        # Tracking
        self._last_update: datetime | None = None
        self._update_listeners: list[Any] = []

        # Collect all dependencies from all formulas
        self._dependencies: set[str] = set()
        for formula in config.formulas:
            self._dependencies.update(formula.get_dependencies(hass))

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
        base_attributes["dependencies"] = list(self._main_formula.get_dependencies(self._hass))
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

        # Phase 2: Register actual entity ID for cross-sensor reference resolution
        if hasattr(self, "entity_id") and self.entity_id:
            await self._sensor_manager.register_cross_sensor_entity_id(self._config.unique_id, self.entity_id)

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
        for var_name, var_value in formula_config.variables.items():
            # Check if this is a numeric literal (not a string entity ID)
            if isinstance(var_value, (int, float)):
                context[var_name] = var_value
                continue

            # Check if this is a string that doesn't look like an entity ID
            if isinstance(var_value, str) and "." not in var_value:
                # Try to convert to numeric if possible
                try:
                    numeric_value = float(var_value)
                    context[var_name] = numeric_value
                except ValueError:
                    # Keep as string if not numeric
                    context[var_name] = var_value
                continue

            # Handle entity references (strings with dots)
            if isinstance(var_value, str) and "." in var_value:
                # If HA lookups are allowed or no data provider callback is available,
                # try to get values from HA state registry
                state = self._hass.states.get(var_value)
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

    def _evaluate_attributes(self, main_result: EvaluationResult) -> None:
        """Evaluate calculated attributes using the main result context."""
        if not self._attribute_formulas:
            return

        # Clear previous calculated attributes
        self._calculated_attributes.clear()

        # Evaluate attributes in the order they appear in the config
        for formula in self._attribute_formulas:
            try:
                # Build variable context for this attribute formula
                attr_context = self._build_variable_context(formula)

                # Add the main result value to context if available
                if main_result["success"] and main_result["value"] is not None:
                    if attr_context is None:
                        attr_context = {}
                    attr_context["state"] = main_result["value"]

                # Evaluate the attribute formula
                attr_result = self._evaluator.evaluate_formula_with_sensor_config(formula, attr_context, self._config)

                if attr_result["success"] and attr_result["value"] is not None:
                    # Extract attribute name from formula ID
                    attr_name = self._extract_attribute_name(formula)
                    self._calculated_attributes[attr_name] = attr_result["value"]
                    _LOGGER.debug(
                        "Calculated attribute '%s' for sensor %s: %s",
                        attr_name,
                        self.entity_id,
                        attr_result["value"],
                    )
                else:
                    _LOGGER.warning(
                        "Failed to evaluate attribute formula '%s' for sensor %s: %s",
                        formula.id,
                        self.entity_id,
                        attr_result.get("error", "Unknown error"),
                    )

            except Exception as e:
                _LOGGER.error(
                    "Error evaluating attribute formula '%s' for sensor %s: %s",
                    formula.id,
                    self.entity_id,
                    e,
                )
                # Continue without attributes rather than failing the entire sensor

    def _handle_main_result(self, main_result: EvaluationResult) -> None:
        """Handle the main formula evaluation result."""
        if main_result["success"] and main_result["value"] is not None:
            self._attr_native_value = main_result["value"]
            self._attr_available = True
            self._last_update = dt_util.utcnow()

            # Evaluate calculated attributes
            self._evaluate_attributes(main_result)

            # Update extra state attributes with calculated values
            self._update_extra_state_attributes()

            # Notify sensor manager of successful update
            self._sensor_manager.on_sensor_updated(
                self._config.unique_id,
                main_result["value"],
                self._calculated_attributes.copy(),
            )
            return

        if main_result["success"] and main_result.get("state") == "unknown":
            # Handle case where evaluation succeeded but dependencies are unavailable
            # This is not an error - just set sensor to unavailable state until dependencies are ready
            self._attr_native_value = None
            self._attr_available = False
            self._last_update = dt_util.utcnow()
            _LOGGER.debug(
                "Sensor %s set to unavailable due to unknown dependencies",
                self.entity_id,
            )
            return

        # Handle evaluation failure
        self._attr_available = False
        error_msg = main_result.get("error", "Unknown evaluation error")
        # Treat formula evaluation failure as a fatal error
        _LOGGER.error("Formula evaluation failed for %s: %s", self.entity_id, error_msg)
        raise FormulaEvaluationError(f"Formula evaluation failed for {self.entity_id}: {error_msg}")

    async def _async_update_sensor(self) -> None:
        """Update the sensor value and calculated attributes by evaluating formulas."""
        try:
            # Build variable context for the main formula
            main_context = self._build_variable_context(self._main_formula)

            # Check if this sensor has a backing entity
            has_backing_entity = self._config.entity_id is not None or (
                self._sensor_manager.sensor_to_backing_mapping
                and self._config.unique_id in self._sensor_manager.sensor_to_backing_mapping
            )

            # If no backing entity and we have a previous state, provide it in context
            if not has_backing_entity and self._attr_native_value is not None:
                if main_context is None:
                    main_context = {}
                main_context["state"] = self._attr_native_value
                _LOGGER.debug(
                    "Providing previous state %s for sensor %s without backing entity", self._attr_native_value, self.entity_id
                )

            # Evaluate the main formula with variable context and sensor configuration
            main_result = self._evaluator.evaluate_formula_with_sensor_config(self._main_formula, main_context, self._config)

            # Handle the main result
            self._handle_main_result(main_result)

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
    def native_value(self) -> Any:
        """Get the native value of the sensor."""
        return self._attr_native_value

    @property
    def dependency_management_phase(self) -> Any:
        """Get the dependency management phase from the evaluator."""
        if hasattr(self._evaluator, "dependency_management_phase"):
            return self._evaluator.dependency_management_phase
        return None

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

    def _extract_attribute_name(self, formula: FormulaConfig) -> str:
        """Extract attribute name from formula ID."""
        if formula.id.startswith(f"{self._config.unique_id}_"):
            return formula.id[len(self._config.unique_id) + 1 :]
        # Fallback: use the full formula ID if it doesn't match expected pattern
        return formula.id

    async def async_update(self) -> None:
        """Update the sensor value and calculated attributes (public method)."""
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

        # Integration data provider tracking
        self._registered_entities: set[str] = set()  # entity_ids registered by integration
        self._allow_ha_lookups: bool = False  # Whether backing entities can fall back to HA lookups
        self._change_notifier: DataProviderChangeNotifier | None = None  # Callback for data change notifications
        self._sensor_to_backing_mapping: dict[str, str] = {}  # Mapping from sensor keys to backing entity IDs

        # Configuration tracking
        self._current_config: Config | None = None

        # Initialize components - use parent-provided instances if available
        self._evaluator = self._manager_config.evaluator or Evaluator(
            self._hass,
            data_provider_callback=self._manager_config.data_provider_callback,
            allow_ha_lookups=self._allow_ha_lookups,
        )
        self._config_manager = self._manager_config.config_manager
        self._logger = _LOGGER.getChild(self.__class__.__name__)

        # Device registry for device association
        self._device_registry = dr.async_get(self._hass)

        # Cross-sensor reference manager for Phase 2 of cross-sensor reference system
        self._cross_sensor_ref_manager = CrossSensorReferenceManager(self._hass)

        # Storage manager reference (set via register_with_storage_manager)
        self._storage_manager: StorageManager | None = None

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

    def _log_sensor_variables(self, formula: FormulaConfig) -> None:
        """Log formula variables and their registration status."""
        if not formula.variables:
            return

        _LOGGER.info("      Variables:")
        for var_name, var_value in formula.variables.items():
            _LOGGER.info("        %s: %s", var_name, var_value)

            # Check if this variable references a registered entity
            if isinstance(var_value, str) and var_value.startswith("sensor."):
                if var_value in self._registered_entities:
                    _LOGGER.info("        ✓ %s is registered as backing entity", var_value)
                else:
                    _LOGGER.warning("        ✗ %s is NOT registered as backing entity", var_value)

    def _log_sensor_configuration_details(self, config: Config) -> None:
        """Log detailed sensor configuration information."""
        if not config.sensors:
            _LOGGER.error("No sensors in configuration - this is a fatal error")
            raise ValueError("No sensors found in configuration")

        _LOGGER.info("Sensor configurations:")
        for sensor in config.sensors:
            _LOGGER.info("  Sensor: %s", sensor.unique_id)
            _LOGGER.info("    Entity ID: %s", sensor.entity_id or "None")
            _LOGGER.info("    Name: %s", sensor.name)
            _LOGGER.info("    Enabled: %s", sensor.enabled)
            _LOGGER.info("    Device identifier: %s", sensor.device_identifier or "None")

            if sensor.formulas:
                for formula in sensor.formulas:
                    _LOGGER.info("    Formula '%s': %s", formula.id, formula.formula)
                    self._log_sensor_variables(formula)

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

    async def register_cross_sensor_entity_id(self, sensor_key: str, actual_entity_id: str) -> None:
        """Register entity ID for cross-sensor reference resolution.

        Called by DynamicSensor during async_added_to_hass() to capture actual entity IDs.

        Args:
            sensor_key: Original YAML sensor key (unique_id)
            actual_entity_id: Actual entity ID assigned by HA
        """
        await self._cross_sensor_ref_manager.register_sensor_entity_id(sensor_key, actual_entity_id)

    async def _on_phase_3_complete(self) -> None:
        """Called when Phase 3 formula reference resolution is complete.

        Updates sensor configs with resolved references and persists to storage.
        """
        resolved_config = self._cross_sensor_ref_manager.get_resolved_config()
        if not resolved_config:
            _LOGGER.warning("Phase 3 completion callback called but no resolved config available")
            return

        _LOGGER.info("Phase 3 complete - updating sensor configs with resolved references")

        # Update sensor configs with resolved formulas and entity_id fields
        for resolved_sensor in resolved_config.sensors:
            if resolved_sensor.unique_id in self._sensors_by_unique_id:
                sensor_entity = self._sensors_by_unique_id[resolved_sensor.unique_id]

                # Update the sensor's config with resolved formulas and entity_id
                # Note: This is a protected access but necessary for cross-sensor reference resolution
                sensor_entity._config = resolved_sensor  # pylint: disable=protected-access

                _LOGGER.debug(
                    "Updated sensor '%s' config with resolved cross-sensor references and entity_id: %s",
                    resolved_sensor.unique_id,
                    resolved_sensor.entity_id,
                )

        # Persist resolved configurations to storage if storage manager is available
        if hasattr(self, "_storage_manager") and self._storage_manager:
            await self._persist_resolved_configs_to_storage(resolved_config)

        _LOGGER.info("All sensors updated with resolved cross-sensor references")

    async def _persist_resolved_configs_to_storage(self, resolved_config: Config) -> None:
        """Persist resolved sensor configurations to storage.

        This ensures that entity_id field updates and resolved formulas are persisted
        to storage and will be reflected in YAML exports.

        Args:
            resolved_config: Config with resolved cross-sensor references and updated entity_id fields
        """
        try:
            _LOGGER.debug("Persisting resolved sensor configurations to storage")

            # Update each sensor in storage with the resolved configuration
            if self._storage_manager is not None:
                for resolved_sensor in resolved_config.sensors:
                    # Update the sensor in storage if it exists
                    await self._storage_manager.async_update_sensor(resolved_sensor)

                    _LOGGER.debug(
                        "Persisted resolved config for sensor '%s' with entity_id: %s",
                        resolved_sensor.unique_id,
                        resolved_sensor.entity_id,
                    )

                # Save all changes to storage
                await self._storage_manager.async_save()
            _LOGGER.info("Successfully persisted resolved configurations to storage")

        except Exception as err:
            _LOGGER.error("Failed to persist resolved configurations to storage: %s", err)
            # Don't raise - this shouldn't block the main functionality

    async def load_configuration(self, config: Config) -> None:
        """Load a new configuration and update sensors accordingly."""
        _LOGGER.info("=== LOADING CONFIGURATION ===")
        _LOGGER.info("Loading configuration with %d sensors", len(config.sensors))

        # Log detailed sensor information
        self._log_sensor_configuration_details(config)

        old_config = self._current_config
        self._current_config = config

        try:
            # Determine what needs to be updated
            if old_config:
                _LOGGER.info("Updating existing sensors...")
                await self._update_existing_sensors(old_config, config)
            else:
                _LOGGER.info("Creating all sensors from scratch...")
                await self._create_all_sensors(config)

            _LOGGER.info("Configuration loaded successfully")
            _LOGGER.info("=== END LOADING CONFIGURATION ===")

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

        # CROSS-SENSOR REFERENCE SUPPORT
        # Unregister the sensor from the evaluator's cross-sensor registry
        if self._evaluator:
            self._evaluator.unregister_sensor(sensor_unique_id)

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

        # CROSS-SENSOR REFERENCE SUPPORT
        # Update the sensor's value in the evaluator's cross-sensor registry
        # This enables other sensors to reference this sensor's value
        if self._evaluator:
            # Get the entity_id for this sensor
            sensor = self._sensors_by_unique_id.get(sensor_unique_id)
            if sensor and sensor.entity_id:
                # Register the sensor if not already registered
                if sensor_unique_id not in self._evaluator.get_registered_sensors():
                    self._evaluator.register_sensor(sensor_unique_id, sensor.entity_id, main_value)
                else:
                    # Update the existing sensor's value
                    self._evaluator.update_sensor_value(sensor_unique_id, main_value)

    def on_sensor_updated(
        self,
        sensor_unique_id: str,
        main_value: Any,
        calculated_attributes: dict[str, Any],
    ) -> None:
        """Called when a sensor is successfully updated (public method)."""
        self._on_sensor_updated(sensor_unique_id, main_value, calculated_attributes)

    async def _create_all_sensors(self, config: Config) -> None:
        """Enhanced sensor creation with cross-sensor registry integration."""
        new_entities: list[DynamicSensor] = []

        # Enhanced sensor registration with cross-sensor registry integration
        await self._register_sensors_in_cross_sensor_registry(config.sensors)

        # Create one entity per sensor
        for sensor_config in config.sensors:
            if sensor_config.enabled:
                try:
                    sensor = await self._create_sensor_entity(sensor_config)
                    new_entities.append(sensor)
                    self._sensors_by_unique_id[sensor_config.unique_id] = sensor
                    self._sensors_by_entity_id[sensor.entity_id] = sensor
                except Exception as e:
                    self._logger.error("Failed to create sensor %s: %s", sensor_config.unique_id, e)
                    raise

        # Validate cross-sensor dependencies after registration
        self._validate_cross_sensor_dependencies(config.sensors)

        # Add entities to Home Assistant
        if new_entities:
            self._add_entities_callback(new_entities)
            _LOGGER.debug("Created %d sensor entities with enhanced cross-sensor integration", len(new_entities))
        else:
            _LOGGER.warning("No sensors found in configuration, not creating any entities.")

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

        sensor = DynamicSensor(self._hass, sensor_config, self._evaluator, self, manager_config, global_settings)

        # CROSS-SENSOR REFERENCE SUPPORT
        # Register the sensor in the evaluator's cross-sensor registry
        # This enables other sensors to reference this sensor by name
        if self._evaluator:
            # Register with initial value of 0.0 (will be updated when sensor evaluates)
            self._evaluator.register_sensor(sensor_config.unique_id, sensor.entity_id, 0.0)

        return sensor

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

        # Phase 2: Initialize cross-sensor reference manager with detected references
        if hasattr(config, "cross_sensor_references") and config.cross_sensor_references:
            self._cross_sensor_ref_manager.initialize_from_config(config.cross_sensor_references, config)
            _LOGGER.debug("Cross-sensor reference manager initialized for Phase 2")

            # Add callback to update sensor configs when Phase 3 completes
            self._cross_sensor_ref_manager.add_completion_callback(self._on_phase_3_complete)

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
        """Enhanced evaluation loop with cross-sensor dependency management."""
        if sensor_configs is None:
            # Update all managed sensors with cross-sensor evaluation order
            evaluation_order = self._get_cross_sensor_evaluation_order()
            for sensor_name in evaluation_order:
                if sensor_name in self._sensors_by_unique_id:
                    try:
                        sensor = self._sensors_by_unique_id[sensor_name]
                        await sensor.async_update_sensor()

                        # Update cross-sensor registry immediately after evaluation
                        if self._evaluator and hasattr(sensor, "native_value"):
                            self._evaluator.update_sensor_value(sensor_name, sensor.native_value)

                    except Exception as e:
                        self._handle_cross_sensor_error(sensor_name, e)
        else:
            # Update specific sensors with cross-sensor evaluation order
            evaluation_order = self._get_cross_sensor_evaluation_order_for_sensors(sensor_configs)
            for sensor_name in evaluation_order:
                if sensor_name in self._sensors_by_unique_id:
                    try:
                        sensor = self._sensors_by_unique_id[sensor_name]
                        await sensor.async_update_sensor()

                        # Update cross-sensor registry immediately after evaluation
                        if self._evaluator and hasattr(sensor, "native_value"):
                            self._evaluator.update_sensor_value(sensor_name, sensor.native_value)

                    except Exception as e:
                        self._handle_cross_sensor_error(sensor_name, e)

        self._logger.debug("Completed enhanced async sensor updates")

    def _get_cross_sensor_evaluation_order(self) -> list[str]:
        """Get evaluation order for all sensors considering cross-sensor dependencies.

        Returns:
            List of sensor names in evaluation order
        """
        if not self.dependency_management_phase:
            # Fallback to original order if dependency management not available
            return list(self._sensors_by_unique_id.keys())

        # Get all sensor configurations
        sensor_configs = [sensor.config for sensor in self._sensors_by_unique_id.values()]

        # Analyze cross-sensor dependencies
        dependency_phase = self.dependency_management_phase
        sensor_dependencies = dependency_phase.analyze_cross_sensor_dependencies(sensor_configs)

        # Get evaluation order
        evaluation_order = dependency_phase.get_cross_sensor_evaluation_order(sensor_dependencies)

        # Validate dependencies
        validation_result = dependency_phase.validate_cross_sensor_dependencies(sensor_dependencies)
        if not validation_result.get("valid", True):
            self._logger.warning("Cross-sensor dependency validation issues: %s", validation_result.get("issues", []))

        # Ensure we return a list of strings
        if isinstance(evaluation_order, list):
            return [str(item) for item in evaluation_order]
        return list(self._sensors_by_unique_id.keys())

    def _get_cross_sensor_evaluation_order_for_sensors(self, sensor_configs: list[SensorConfig]) -> list[str]:
        """Get evaluation order for specific sensors considering cross-sensor dependencies.

        Args:
            sensor_configs: List of sensor configurations to evaluate

        Returns:
            List of sensor names in evaluation order
        """
        if not self.dependency_management_phase:
            # Fallback to original order if dependency management not available
            return [config.unique_id for config in sensor_configs]

        # Analyze cross-sensor dependencies for the specified sensors
        dependency_phase = self.dependency_management_phase
        sensor_dependencies = dependency_phase.analyze_cross_sensor_dependencies(sensor_configs)

        # Get evaluation order
        evaluation_order = dependency_phase.get_cross_sensor_evaluation_order(sensor_dependencies)

        # Validate dependencies
        validation_result = dependency_phase.validate_cross_sensor_dependencies(sensor_dependencies)
        if not validation_result.get("valid", True):
            self._logger.warning("Cross-sensor dependency validation issues: %s", validation_result.get("issues", []))

        # Ensure we return a list of strings
        if isinstance(evaluation_order, list):
            return [str(item) for item in evaluation_order]
        return [config.unique_id for config in sensor_configs]

    async def _register_sensors_in_cross_sensor_registry(self, sensor_configs: list[SensorConfig]) -> None:
        """Enhanced sensor registration with cross-sensor registry integration.

        Args:
            sensor_configs: List of sensor configurations to register
        """
        if not self._evaluator:
            self._logger.warning("No evaluator available for cross-sensor registry registration")
            return

        self._logger.debug("Registering %d sensors in cross-sensor registry", len(sensor_configs))

        for config in sensor_configs:
            try:
                # Generate entity_id if not provided
                entity_id = config.entity_id
                if not entity_id:
                    entity_id = self._generate_entity_id(
                        sensor_key=config.unique_id,
                        device_identifier=config.device_identifier,
                        explicit_entity_id=config.entity_id,
                    )

                # Register sensor in cross-sensor registry
                self._evaluator.register_sensor(config.unique_id, entity_id, 0.0)
                self._logger.debug("Registered sensor '%s' in cross-sensor registry", config.unique_id)

            except Exception as e:
                self._logger.error("Failed to register sensor '%s' in cross-sensor registry: %s", config.unique_id, e)
                raise

    def _validate_cross_sensor_dependencies(self, sensor_configs: list[SensorConfig]) -> None:
        """Validate all cross-sensor dependencies across the sensor set.

        Args:
            sensor_configs: List of sensor configurations to validate

        Raises:
            ValueError: If cross-sensor dependency validation fails
        """
        if not self.dependency_management_phase:
            self._logger.debug("Dependency management phase not available, skipping validation")
            return

        try:
            # Analyze cross-sensor dependencies
            dependency_phase = self.dependency_management_phase
            sensor_dependencies = dependency_phase.analyze_cross_sensor_dependencies(sensor_configs)

            # Validate dependencies
            validation_result = dependency_phase.validate_cross_sensor_dependencies(sensor_dependencies)

            if not validation_result.get("valid", True):
                issues = validation_result.get("issues", [])
                circular_refs = validation_result.get("circular_references", [])

                error_msg = f"Cross-sensor dependency validation failed: {issues}"
                if circular_refs:
                    error_msg += f" Circular references: {circular_refs}"

                self._logger.error(error_msg)
                raise ValueError(error_msg)

            self._logger.debug("Cross-sensor dependency validation passed for %d sensors", len(sensor_configs))

        except Exception as e:
            self._logger.error("Cross-sensor dependency validation error: %s", e)
            raise

    def _analyze_sensor_cross_dependencies(self, sensor_config: SensorConfig) -> set[str]:
        """Analyze cross-sensor dependencies for a specific sensor.

        Args:
            sensor_config: Sensor configuration to analyze

        Returns:
            Set of sensor names that this sensor depends on
        """
        if not self.dependency_management_phase:
            return set()

        try:
            # Analyze dependencies for this single sensor
            dependency_phase = self.dependency_management_phase
            sensor_dependencies = dependency_phase.analyze_cross_sensor_dependencies([sensor_config])

            # Return dependencies for this sensor
            dependencies = sensor_dependencies.get(sensor_config.unique_id, set())
            if isinstance(dependencies, set):
                return {str(item) for item in dependencies}
            return set()

        except Exception as e:
            self._logger.error("Failed to analyze cross-sensor dependencies for sensor '%s': %s", sensor_config.unique_id, e)
            return set()

    def _handle_cross_sensor_error(self, sensor_name: str, error: Exception) -> None:
        """Handle cross-sensor resolution errors with appropriate logging.

        Args:
            sensor_name: Name of the sensor that encountered an error
            error: The error that occurred
        """
        if isinstance(error, (MissingDependencyError, CrossSensorResolutionError, DependencyValidationError)):
            self._logger.error("Cross-sensor resolution error for sensor '%s': %s", sensor_name, error)
        else:
            self._logger.error("Unexpected error during cross-sensor resolution for sensor '%s': %s", sensor_name, error)

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

        Raises:
            ValueError: If the entity_ids set contains invalid entries (None values, empty strings, etc.)
        """
        _LOGGER.info("=== REGISTERING DATA PROVIDER ENTITIES ===")
        _LOGGER.info("Registering %d entities for integration data provider", len(entity_ids))
        _LOGGER.info("Allow HA lookups: %s", allow_ha_lookups)
        _LOGGER.info("Change notifier: %s", "Provided" if change_notifier else "None")

        # Validate the entity IDs
        if entity_ids:
            # Check for None values or invalid strings
            invalid_entities = []
            for entity_id in entity_ids:
                if entity_id is None:
                    invalid_entities.append("None entity ID")
                elif not isinstance(entity_id, str) or not entity_id.strip():
                    invalid_entities.append(f"Invalid entity ID: {entity_id!r}")

            if invalid_entities:
                error_msg = f"Invalid entity IDs in registration: {', '.join(invalid_entities)}"
                _LOGGER.error(error_msg)
                raise ValueError(error_msg)

            _LOGGER.info("Entity IDs being registered:")
            for entity_id in sorted(entity_ids):
                _LOGGER.info("  - %s", entity_id)
        else:
            _LOGGER.warning("No entity IDs provided for registration")

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
            _LOGGER.info("Updated evaluator with %d integration entities", len(entity_ids))

        # Update the evaluator's allow_ha_lookups setting
        if hasattr(self._evaluator, "update_allow_ha_lookups"):
            self._evaluator.update_allow_ha_lookups(allow_ha_lookups)
            _LOGGER.info("Updated evaluator allow_ha_lookups setting: %s", allow_ha_lookups)

        _LOGGER.info("=== END REGISTERING DATA PROVIDER ENTITIES ===")

    def register_sensor_to_backing_mapping(self, sensor_to_backing_mapping: dict[str, str]) -> None:
        """Register the mapping from sensor keys to backing entity IDs.

        This mapping is used for state token resolution in formulas.

        Args:
            sensor_to_backing_mapping: Mapping from sensor keys to backing entity IDs

        Raises:
            ValueError: If the mapping contains invalid entries (None values, empty strings, etc.)
                       or if the mapping is empty (which would break state token resolution)
        """
        _LOGGER.info("=== REGISTERING SENSOR-TO-BACKING MAPPING ===")
        _LOGGER.info("Registering %d sensor-to-backing mappings", len(sensor_to_backing_mapping))

        # Validate the mapping
        if not sensor_to_backing_mapping:
            error_msg = (
                "Empty sensor-to-backing mapping provided. At least one mapping entry is required for state token resolution."
            )
            _LOGGER.error(error_msg)
            raise ValueError(error_msg)

        # Check for None values or invalid strings
        invalid_entries = []
        for sensor_key, backing_entity_id in sensor_to_backing_mapping.items():
            if sensor_key is None:
                invalid_entries.append("None sensor key")
            elif not isinstance(sensor_key, str) or not sensor_key.strip():
                invalid_entries.append(f"Invalid sensor key: {sensor_key!r}")
            elif backing_entity_id is None:
                invalid_entries.append(f"None backing entity ID for sensor key: {sensor_key}")
            elif not isinstance(backing_entity_id, str) or not backing_entity_id.strip():
                invalid_entries.append(f"Invalid backing entity ID for sensor key {sensor_key}: {backing_entity_id!r}")

        if invalid_entries:
            error_msg = f"Invalid sensor-to-backing mapping entries: {', '.join(invalid_entries)}"
            _LOGGER.error(error_msg)
            raise ValueError(error_msg)

        _LOGGER.info("Sensor-to-backing mappings:")
        for sensor_key, backing_entity_id in sorted(sensor_to_backing_mapping.items()):
            _LOGGER.info("  %s -> %s", sensor_key, backing_entity_id)

        # Store the mapping
        self._sensor_to_backing_mapping = sensor_to_backing_mapping.copy()

        # Update the evaluator if it supports the mapping
        if hasattr(self._evaluator, "update_sensor_to_backing_mapping"):
            self._evaluator.update_sensor_to_backing_mapping(sensor_to_backing_mapping)
            _LOGGER.info("Updated evaluator with sensor-to-backing mapping")

        _LOGGER.info("=== END REGISTERING SENSOR-TO-BACKING MAPPING ===")

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
        # Store reference for cross-sensor resolution persistence
        self._storage_manager = storage_manager

        storage_manager.register_sensor_manager(self)
        storage_manager.register_evaluator(self._evaluator)
        self._logger.debug("Registered SensorManager and Evaluator with StorageManager")

    def unregister_from_storage_manager(self, storage_manager: StorageManager) -> None:
        """
        Unregister this SensorManager and its Evaluator from a StorageManager's entity change handler.

        Args:
            storage_manager: StorageManager instance to unregister from
        """
        # Clear reference
        self._storage_manager = None

        storage_manager.unregister_sensor_manager(self)
        storage_manager.unregister_evaluator(self._evaluator)
        self._logger.debug("Unregistered SensorManager and Evaluator from StorageManager")

    @property
    def evaluator(self) -> Evaluator:
        """Get the evaluator instance."""
        return self._evaluator

    @property
    def dependency_management_phase(self) -> Any:
        """Get the dependency management phase from the evaluator."""
        if hasattr(self._evaluator, "dependency_management_phase"):
            return self._evaluator.dependency_management_phase
        return None

    @property
    def allow_ha_lookups(self) -> bool:
        """Get the allow_ha_lookups setting."""
        return self._allow_ha_lookups

    @property
    def sensor_to_backing_mapping(self) -> dict[str, str]:
        """Get the sensor-to-backing mapping."""
        return self._sensor_to_backing_mapping

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
