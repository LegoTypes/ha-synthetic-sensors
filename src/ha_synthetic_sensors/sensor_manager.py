"""Sensor manager for synthetic sensors."""
# pylint: disable=too-many-lines

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import inspect as _inspect
import logging
from typing import TYPE_CHECKING, Any, cast

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify

from .config_models import ComputedVariable, Config, FormulaConfig, SensorConfig
from .config_types import GlobalSettingsDict
from .constants_alternate import STATE_NONE
from .constants_evaluation_results import (
    RESULT_KEY_ERROR,
    RESULT_KEY_STATE,
    RESULT_KEY_SUCCESS,
    RESULT_KEY_VALUE,
    STATE_OK,
    STATE_UNKNOWN as EVAL_STATE_UNKNOWN,
)
from .constants_metadata import (
    METADATA_PROPERTY_DEVICE_CLASS,
    METADATA_PROPERTY_ICON,
    METADATA_PROPERTY_STATE_CLASS,
    METADATA_PROPERTY_UNIT_OF_MEASUREMENT,
)
from .cross_sensor_reference_manager import CrossSensorReferenceManager
from .evaluator import Evaluator
from .evaluator_phases.dependency_management.generic_dependency_manager import GenericDependencyManager
from .evaluator_phases.variable_resolution.state_resolver import StateResolver
from .exceptions import (
    CrossSensorResolutionError,
    DependencyValidationError,
    FormulaEvaluationError,
    MissingDependencyError,
    SyntheticSensorsConfigError,
)
from .formula_utils import extract_attribute_name
from .hierarchical_context_dict import HierarchicalContextDict
from .metadata_handler import MetadataHandler
from .name_resolver import NameResolver
from .reference_value_manager import ReferenceValueManager
from .sensor_evaluation_context import SensorEvaluationContext, get_context_manager
from .shared_constants import LAST_VALID_CHANGED_KEY, LAST_VALID_STATE_KEY
from .type_definitions import ContextValue, DataProviderCallback, DataProviderChangeNotifier, EvaluationResult, ReferenceValue

# dedupe imports

if TYPE_CHECKING:
    from homeassistant.core import EventStateChangedData

    from .config_manager import ConfigManager
    from .storage_manager import StorageManager

_LOGGER = logging.getLogger(__name__)


@dataclass
class SensorManagerConfig:
    """Configuration for SensorManager with device integration support."""

    integration_domain: str = "synthetic_sensors"  # Integration domain for device lookup
    device_identifier: str | None = None  # Device identifier for global settings lookup
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

        # Store resolved variables from main formula evaluation for attribute use
        # Removed _resolved_variables - hierarchical context is the single source of truth

        # Set base extra state attributes
        self._setup_base_attributes()

        # Tracking
        self._last_update: datetime | None = None
        self._update_listeners: list[Any] = []
        # No persistent preseed object - we will create canonical ReferenceValue
        # instances from the entity's extra state attributes when building eval contexts.

        # Collect all dependencies from all formulas
        # NOTE: This is initial static extraction - dependencies will be dynamically updated during evaluation
        # to capture ALL entity references (including those in attributes, metadata, etc.)
        self._dependencies: set[str] = set()
        for formula in config.formulas:
            self._dependencies.update(formula.get_dependencies(hass))

        # Track if we've discovered new dependencies during evaluation
        self._discovered_dependencies: set[str] = set()
        # Internal control to temporarily suppress dependency listener refresh during controlled updates
        self._suppress_dependency_refresh: bool = False

        # Note: Dependency tracking for data provider entities removed
        # Integration change notifier handles all updates when backing data changes

    @property
    def hass_instance(self) -> HomeAssistant:
        """Return the Home Assistant instance."""
        return self._hass

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
        self._attr_native_unit_of_measurement = metadata.get(METADATA_PROPERTY_UNIT_OF_MEASUREMENT)
        self._attr_state_class = metadata.get(METADATA_PROPERTY_STATE_CLASS)
        self._attr_icon = metadata.get(METADATA_PROPERTY_ICON)

        # Convert device_class string to enum if needed
        device_class = metadata.get(METADATA_PROPERTY_DEVICE_CLASS)
        if device_class:
            try:
                self._attr_device_class = SensorDeviceClass(device_class)
            except ValueError:
                self._attr_device_class = None
        else:
            self._attr_device_class = None

        # Apply additional metadata properties as HA sensor attributes
        # Skip the ones we've already handled above
        handled_keys = {
            METADATA_PROPERTY_UNIT_OF_MEASUREMENT,
            METADATA_PROPERTY_STATE_CLASS,
            METADATA_PROPERTY_ICON,
            METADATA_PROPERTY_DEVICE_CLASS,
        }
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

    def _update_extra_state_attributes(self, sensor_context: SensorEvaluationContext | None = None) -> None:
        """Update the extra state attributes with current values."""
        # Start with main formula attributes
        base_attributes: dict[str, Any] = self._main_formula.attributes.copy()

        # Variable resolution for calculated attributes is handled separately below.

        # Add calculated attributes from other formulas
        base_attributes.update(self._calculated_attributes)

        # Resolve ALL attributes that reference context variables
        # This handles both calculated attributes AND simple string attributes from main formula
        if sensor_context is not None:
            current_context = sensor_context.get_context_for_evaluation()

            # Process calculated attributes (from formula evaluation)
            for attr_name, attr_value in self._calculated_attributes.items():
                if isinstance(attr_value, str):
                    _LOGGER.debug(
                        "ATTR_RESOLUTION_DEBUG: Processing calculated attribute %s with string value '%s'",
                        attr_name,
                        attr_value,
                    )
                    # Try to resolve from hierarchical context
                    if attr_value in current_context:
                        context_value = current_context[attr_value]
                        resolved_value = context_value.value if isinstance(context_value, ReferenceValue) else context_value
                        base_attributes[attr_name] = resolved_value
                        _LOGGER.info(
                            "CALCULATED_ATTR_RESOLVED: Attribute %s = %s (from context variable %s)",
                            attr_name,
                            resolved_value,
                            attr_value,
                        )
                    else:
                        _LOGGER.warning(
                            "CALCULATED_ATTR_MISSING: Calculated attribute %s references variable %s but it's not in context. Available: %s",
                            attr_name,
                            attr_value,
                            [k for k in current_context if not k.startswith("_")],
                        )

            # Also process simple string attributes from main formula
            for attr_name, attr_value in self._main_formula.attributes.items():
                # Skip re-evaluation of attributes that are already calculated
                # This prevents double evaluation which causes string concatenation corruption
                if attr_name in self._calculated_attributes:
                    continue
                if isinstance(attr_value, str):
                    # Try to resolve from hierarchical context
                    if attr_value in current_context:
                        context_value = current_context[attr_value]
                        resolved_value = context_value.value if isinstance(context_value, ReferenceValue) else context_value
                        base_attributes[attr_name] = resolved_value
                elif isinstance(attr_value, dict) and "formula" in attr_value:
                    # INFINITE LOOP FIX: Formula attributes should already be calculated during evaluation phase
                    # Do NOT call _evaluate_cv_via_pipeline here as it causes infinite loops by triggering
                    # the full evaluation pipeline which can cause other sensors to update recursively
                    # Use fallback value if the attribute wasn't pre-calculated
                    fallback_value = attr_value.get("alternate_states", {}).get("FALLBACK", "unknown")
                    base_attributes[attr_name] = fallback_value
                    _LOGGER.debug("FORMULA_ATTR_FALLBACK: Using fallback for %s = %s", attr_name, fallback_value)

        # Unwrap ReferenceValue instances so HA sees plain types
        def _unwrap(value: Any) -> Any:
            if isinstance(value, ReferenceValue):
                return value.value
            if isinstance(value, dict):
                return {k: _unwrap(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_unwrap(v) for v in value]
            if isinstance(value, tuple):
                return tuple(_unwrap(v) for v in value)
            return value

        base_attributes = {k: _unwrap(v) for k, v in base_attributes.items()}

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

        # Note: State change tracking removed - integration change notifier handles all updates
        # Dependencies are resolved during evaluation, not through HA state tracking

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity removal."""
        # Clean up listeners
        for listener in self._update_listeners:
            listener()
        self._update_listeners.clear()

    @callback
    @callback
    def _handle_dependency_change(self, event: Event[EventStateChangedData]) -> None:
        """Handle when a dependency entity changes.

        Note: Individual sensor dependency tracking is disabled to prevent infinite loops.
        The integration should handle updates via sensor_manager.async_update_sensors_for_entities()
        when backing entities change.
        """
        # Do nothing - let the integration handle updates via async_update_sensors_for_entities

    def _add_variables_to_sensor_context(self, formula_config: FormulaConfig, sensor_context: SensorEvaluationContext) -> None:
        """Add variables from formula config directly to the existing sensor context.

        This method adds variables directly to the existing hierarchical context
        instead of creating a new one. This maintains the single context architecture.

        Args:
            formula_config: Formula configuration with variables
            sensor_context: The existing sensor evaluation context to add variables to
        """
        # Early returns for cases where we don't need to build context
        if not self._should_build_variable_context(formula_config):
            return

        # Get the hierarchical context dict from the sensor context
        context_dict = sensor_context.get_context_for_evaluation()

        # Add variables layer to the existing hierarchical context
        sensor_context.context.push_layer("sensor_variables")

        # Build context from variables directly into the existing context
        for var_name, var_value in formula_config.variables.items():
            self._process_variable(context_dict, var_name, var_value)

        # Inject canonical state reference
        self._inject_canonical_state_reference(context_dict)

    def _should_build_variable_context(self, formula_config: FormulaConfig) -> bool:
        """Determine if we should build variable context or delegate to evaluator."""
        if not formula_config.variables:
            return False

        # If data provider callback is available, let evaluator handle resolution
        if self._evaluator.data_provider_callback:
            return False

        # If any computed variables are present, let evaluator handle all resolution
        return not any(isinstance(var_value, ComputedVariable) for var_value in formula_config.variables.values())

    def _process_variable(self, context: HierarchicalContextDict, var_name: str, var_value: Any) -> None:
        """Process a single variable and add it to the context."""
        # Handle numeric literals
        if isinstance(var_value, int | float):
            ReferenceValueManager.set_variable_with_reference_value(context, var_name, var_name, var_value)
            return

        # Handle string values
        if isinstance(var_value, str):
            if "." not in var_value:
                self._process_string_literal(context, var_name, var_value)
            else:
                self._process_entity_reference(context, var_name, var_value)

    def _process_string_literal(self, context: HierarchicalContextDict, var_name: str, var_value: str) -> None:
        """Process a string literal variable (no dots, not an entity ID)."""
        try:
            # Try to convert to numeric if possible
            numeric_value = float(var_value)
            ReferenceValueManager.set_variable_with_reference_value(context, var_name, var_name, numeric_value)
        except ValueError:
            # Create ReferenceValue for string literal
            ReferenceValueManager.set_variable_with_reference_value(context, var_name, var_name, var_value)

    def _process_entity_reference(self, context: HierarchicalContextDict, var_name: str, var_value: str) -> None:
        """Process an entity reference variable (contains dots)."""
        state = self._hass.states.get(var_value)
        if state is None:
            raise MissingDependencyError(f"Entity '{var_value}' not found")

        try:
            # Try to get numeric value
            numeric_value = float(state.state)
            ReferenceValueManager.set_variable_with_reference_value(context, var_name, var_value, numeric_value)
        except (ValueError, TypeError):
            # Fall back to string value
            ReferenceValueManager.set_variable_with_reference_value(context, var_name, var_value, state.state)

    def _inject_canonical_state_reference(self, context: HierarchicalContextDict) -> None:
        """Inject canonical ReferenceValue for 'state' after processing all other variables."""
        # Debug logging removed to reduce verbosity

        try:
            if hasattr(self, "_attr_extra_state_attributes") and self._attr_extra_state_attributes:
                attrs_local = dict(self._attr_extra_state_attributes)
                last_val = attrs_local.get(LAST_VALID_STATE_KEY)
                last_changed = attrs_local.get(LAST_VALID_CHANGED_KEY)
                ref = self.entity_id or "state"

                rv = ReferenceValue(
                    reference=ref,
                    value=last_val if last_val is not None else None,
                    last_valid_state=last_val,
                    last_valid_changed=last_changed,
                )
                ReferenceValueManager.set_variable_with_reference_value(context, "state", ref, rv)
                # Debug logging removed to reduce verbosity
        except Exception as e:
            # Log the error for debugging but don't fail the function
            _LOGGER.debug("Error in _seed_last_valid_state: %s", e)

    def _attempt_seed_last_valid(self, backing_entity_id: str | None = None) -> None:
        """Try to seed LAST_VALID_STATE_KEY/ LAST_VALID_CHANGED_KEY from backing data.

        Uses the existing resolver infrastructure to avoid duplicating backing entity lookup logic.
        """
        try:
            attrs = dict(self._attr_extra_state_attributes or {})
            if LAST_VALID_STATE_KEY in attrs:
                return

            if not backing_entity_id:
                return

            # Use the existing self-reference resolver to get backing entity value
            # This reuses all the well-tested lookup logic instead of duplicating it
            resolver_factory = getattr(self._evaluator, "_variable_resolution_phase", None)
            if not resolver_factory:
                # Debug logging removed to reduce verbosity
                return

            resolver_factory = getattr(resolver_factory, "_resolver_factory", None)
            if not resolver_factory:
                # Debug logging removed to reduce verbosity
                return

            # Get the self-reference resolver
            self_ref_resolver = None
            for resolver in resolver_factory.get_all_resolvers():
                if hasattr(resolver, "resolve_backing_entity_value"):
                    self_ref_resolver = resolver
                    break

            if not self_ref_resolver:
                # Debug logging removed to reduce verbosity
                return

            # Use the existing backing entity resolution logic
            backing_value = self_ref_resolver.resolve_backing_entity_value(backing_entity_id, f"seed_{backing_entity_id}")
            # Debug logging removed to reduce verbosity

            if backing_value is not None:
                attrs[LAST_VALID_STATE_KEY] = backing_value
                attrs[LAST_VALID_CHANGED_KEY] = datetime.now().isoformat()
                self._attr_extra_state_attributes = attrs
                # Debug logging removed to reduce verbosity
            else:
                pass  # Debug logging removed to reduce verbosity
        except Exception:
            _LOGGER.debug("Seeding attempt failed for %s", getattr(self, "entity_id", None), exc_info=True)

    def _evaluate_attributes(self, main_result: EvaluationResult, sensor_context: SensorEvaluationContext) -> None:
        """Evaluate calculated attributes using the main result context and inherited sensor context."""
        _LOGGER.warning("ATTR_EVAL_CALL_DEBUG: _evaluate_attributes called for %s", self.entity_id)
        if not self._attribute_formulas:
            return

        # Clear previous calculated attributes
        self._calculated_attributes.clear()

        # Process attributes in two phases: computed variables first, then remaining formulas
        remaining_formulas = self._evaluate_computed_variable_attributes(sensor_context)
        self._evaluate_remaining_attributes(remaining_formulas, main_result, sensor_context)

    def _evaluate_attributes_with_context(self, sensor_context: SensorEvaluationContext) -> None:
        """Evaluate calculated attributes using the hierarchical context."""
        _LOGGER.warning("ATTR_EVAL_CALL_DEBUG: _evaluate_attributes_with_context called for %s", self.entity_id)
        if not self._attribute_formulas:
            return

        # Clear previous calculated attributes
        self._calculated_attributes.clear()

        # Get the accumulated context for attribute evaluation
        eval_context = sensor_context.get_context_for_evaluation()

        # Process each attribute formula
        for formula in self._attribute_formulas:
            attr_name = self._extract_attribute_name(formula)

            # Begin attribute-specific context
            sensor_context.begin_attribute_evaluation(attr_name)

            try:
                # Check if it's a simple reference to a computed variable
                token = formula.formula.strip()
                if token in eval_context:
                    # Direct reference to an existing variable
                    value = eval_context[token]
                    if isinstance(value, ReferenceValue):
                        self._calculated_attributes[attr_name] = value.value
                    else:
                        self._calculated_attributes[attr_name] = value
                else:
                    # Evaluate the formula with the accumulated context
                    current_context = sensor_context.get_context_for_evaluation()
                    result = self._evaluator.evaluate_formula_with_sensor_config(formula, current_context, self._config)

                    result_dict = cast(dict[str, Any], result)
                    if result_dict[RESULT_KEY_SUCCESS]:
                        # Store the value even if it's None, False, or 0
                        attr_result_value = result_dict[RESULT_KEY_VALUE]
                        _LOGGER.debug(
                            "DIRECT_EVAL_ATTR_DEBUG: Storing attribute %s = %s (type: %s)",
                            attr_name,
                            attr_result_value,
                            type(attr_result_value).__name__,
                        )
                        self._calculated_attributes[attr_name] = attr_result_value
            finally:
                # End attribute evaluation, pop the attribute layer
                sensor_context.end_attribute_evaluation()

    def _evaluate_computed_variable_attributes(self, sensor_context: SensorEvaluationContext) -> list[FormulaConfig]:
        """Evaluate attribute formulas that are simple references to computed variables."""
        remaining_formulas: list[FormulaConfig] = []

        for formula in self._attribute_formulas:
            computed_var = self._get_computed_variable_for_formula(formula)
            if computed_var is not None and self._try_evaluate_computed_variable_attribute(
                formula, computed_var, sensor_context
            ):
                continue
            # Not a simple computed-var attribute, keep for later processing
            remaining_formulas.append(formula)

        return remaining_formulas

    def _get_computed_variable_for_formula(self, formula: FormulaConfig) -> ComputedVariable | None:
        """Get the computed variable if the formula is a simple reference to one."""
        token = formula.formula.strip()
        if token in self._main_formula.variables:
            maybe_cv = self._main_formula.variables[token]
            if isinstance(maybe_cv, ComputedVariable):
                return maybe_cv
        return None

    def _try_evaluate_computed_variable_attribute(
        self, formula: FormulaConfig, computed_var: ComputedVariable, sensor_context: SensorEvaluationContext
    ) -> bool:
        """Try to evaluate a computed variable attribute using inherited sensor context. Returns True if successful."""
        try:
            # Include alternate_state_handler from ComputedVariable in temporary FormulaConfig
            # This ensures that alternate state handlers work correctly for computed variables
            temp_cfg = FormulaConfig(
                id=f"{self._config.unique_id}_{formula.formula.strip()}",
                formula=computed_var.formula,
                alternate_state_handler=computed_var.alternate_state_handler,
            )

            # Use the sensor's accumulated context instead of creating new context
            # This ensures proper hierarchical context inheritance for attribute evaluation
            inherited_context = sensor_context.get_context_for_evaluation()

            eval_result = self._evaluator.evaluate_formula_with_sensor_config(temp_cfg, inherited_context, self._config)
            eval_result_dict = cast(dict[str, Any], eval_result)

            if eval_result_dict[RESULT_KEY_SUCCESS]:
                attr_name = self._extract_attribute_name(formula)
                # Store the value even if it's None, False, or 0
                self._calculated_attributes[attr_name] = eval_result_dict[RESULT_KEY_VALUE]
                return True
        except Exception as e:
            _LOGGER.debug("Computed variable attribute eval failed for %s: %s", formula.formula.strip(), e)

        return False

    def _evaluate_remaining_attributes(
        self, remaining_formulas: list[FormulaConfig], main_result: EvaluationResult, sensor_context: SensorEvaluationContext
    ) -> None:
        """Evaluate remaining attribute formulas using dependency manager or individual evaluation with inherited context."""
        if not remaining_formulas:
            return

        try:
            # Try dependency manager approach first
            if self._try_evaluate_with_dependency_manager(remaining_formulas, main_result, sensor_context):
                return

            # Fallback to individual evaluation
            self._evaluate_attributes_individually(remaining_formulas, main_result, sensor_context)

        except Exception as e:
            _LOGGER.error("Error evaluating attributes for sensor %s: %s", self.entity_id, e)

    def _try_evaluate_with_dependency_manager(
        self, formulas: list[FormulaConfig], main_result: EvaluationResult, sensor_context: SensorEvaluationContext
    ) -> bool:
        """Try to evaluate attributes using the dependency manager with inherited context. Returns True if successful."""

        adm = getattr(self, "_attribute_dependency_manager", None)
        if adm is None:
            return False

        main_result_dict = cast(dict[str, Any], main_result)
        base_ctx = self._build_base_context_from_main_result(main_result_dict, sensor_context)

        complete_ctx = adm.build_evaluation_context(self._config, self._evaluator, base_ctx)
        for formula in formulas:
            attr_name = self._extract_attribute_name(formula)
            if attr_name in complete_ctx and complete_ctx[attr_name] is not None:
                attr_value = complete_ctx[attr_name]
                self._calculated_attributes[attr_name] = attr_value

                # Store attribute result in hierarchical context for downstream evaluations
                # This ensures attributes can be referenced by other attributes or alternate states

                if isinstance(attr_value, ReferenceValue):
                    # Already a ReferenceValue, store directly
                    sensor_context.context.set(attr_name, attr_value)
                else:
                    # Wrap in ReferenceValue
                    attr_reference_value = ReferenceValue(reference=f"attr.{attr_name}", value=attr_value)
                    sensor_context.context.set(attr_name, attr_reference_value)
        return True

    def _evaluate_attributes_individually(
        self, formulas: list[FormulaConfig], main_result: EvaluationResult, sensor_context: SensorEvaluationContext
    ) -> None:
        """Evaluate attributes individually as fallback using inherited context."""

        main_result_dict = cast(dict[str, Any], main_result)

        for formula in formulas:
            try:
                attr_ctx = self._build_base_context_from_main_result(main_result_dict, sensor_context)
                attr_result = self._evaluator.evaluate_formula(formula, attr_ctx)
                attr_result_dict = cast(dict[str, Any], attr_result)

                if attr_result_dict[RESULT_KEY_SUCCESS]:
                    attr_name = self._extract_attribute_name(formula)
                    attr_value = attr_result_dict[RESULT_KEY_VALUE]

                    # Store the value even if it's None, False, or 0
                    self._calculated_attributes[attr_name] = attr_value

                    # Store attribute result in hierarchical context for downstream evaluations
                    # This ensures attributes can be referenced by other attributes or alternate states

                    attr_reference_value = ReferenceValue(reference=f"attr.{attr_name}", value=attr_value)
                    sensor_context.context.set(attr_name, attr_reference_value)
                else:
                    raise RuntimeError(f"Attribute evaluation failed for {formula.id}")
            except Exception as e:
                _LOGGER.error(
                    "Error evaluating attribute formula '%s' for sensor %s: %s",
                    formula.id,
                    self.entity_id,
                    e,
                )
                continue

    def _build_base_context_from_main_result(
        self, main_result_dict: dict[str, Any], sensor_context: SensorEvaluationContext
    ) -> HierarchicalContextDict:
        """Build base context from main result for attribute evaluation by inheriting sensor's context.

        This method should inherit from the sensor's accumulated context, not create a new one.
        """
        # Get the sensor's accumulated context as the base
        inherited_context = sensor_context.get_context_for_evaluation()

        # Ensure we have a HierarchicalContextDict
        if not isinstance(inherited_context, HierarchicalContextDict):
            raise TypeError(f"Expected HierarchicalContextDict, got {type(inherited_context)}")

        # Update the state value based on main result
        if main_result_dict[RESULT_KEY_SUCCESS] and main_result_dict[RESULT_KEY_VALUE] is not None:
            # Main evaluation succeeded - update the state value in the inherited context
            ReferenceValueManager.set_variable_with_reference_value(
                inherited_context, "state", self.entity_id or "state", main_result_dict[RESULT_KEY_VALUE]
            )
        else:
            # Main evaluation failed - provide STATE_UNKNOWN as state value
            # This allows attribute formulas to evaluate and potentially trigger their own alternate state handlers
            ReferenceValueManager.set_variable_with_reference_value(
                inherited_context, "state", self.entity_id or "state", STATE_UNKNOWN
            )

        return inherited_context

    # Removed _capture_resolved_variables_from_evaluator method
    # The hierarchical context is the single source of truth for all resolved variables

    def _setup_initial_state_in_context(self, sensor_context: SensorEvaluationContext, has_backing_entity: bool) -> None:
        """Set up initial state reference in context BEFORE building evaluation context.

        This method uses the StateResolver to properly set up the state reference
        with backing entity values, avoiding evaluation pipeline issues.

        Args:
            sensor_context: The sensor evaluation context to set state in
            has_backing_entity: Whether this sensor has a backing entity
        """
        try:
            # Create a StateResolver with the sensor manager's configuration
            state_resolver = StateResolver(
                sensor_to_backing_mapping=self._sensor_manager.sensor_to_backing_mapping,
                data_provider_callback=self._sensor_manager.manager_config.data_provider_callback,
                hass=self._hass,
            )

            # Use StateResolver to get the prior state reference
            # Create HierarchicalContextDict wrapper for the evaluation context
            context_dict = HierarchicalContextDict(sensor_context.context)
            state_ref = state_resolver.resolve_prior_state_reference(self._config, context_dict)

            if state_ref:
                # Set the resolved state in the sensor context
                sensor_context.context.set("state", state_ref)
            else:
                # Fallback to basic state reference
                fallback_state_ref = ReferenceValue(reference=self.entity_id or "state", value=None)
                sensor_context.context.set("state", fallback_state_ref)

        except Exception as e:
            _LOGGER.error(
                "Sensor manager: Failed to set up initial state using StateResolver for %s: %s", self._config.unique_id, e
            )
            # Ensure we always have some state reference
            fallback_state_ref = ReferenceValue(reference=self.entity_id or "state", value=None)
            sensor_context.context.set("state", fallback_state_ref)

    def _handle_main_result(self, main_result: EvaluationResult, sensor_context: SensorEvaluationContext) -> None:
        """Handle the main formula evaluation result with sensor context for attribute evaluation."""
        main_result_dict = cast(dict[str, Any], main_result)

        if main_result_dict[RESULT_KEY_SUCCESS] and main_result_dict[RESULT_KEY_VALUE] is not None:
            self._handle_successful_result(main_result_dict, sensor_context)
            return

        if main_result_dict[RESULT_KEY_SUCCESS] and main_result_dict.get(RESULT_KEY_STATE) == EVAL_STATE_UNKNOWN:
            self._handle_unknown_state_result(main_result_dict)
            return

        if main_result_dict[RESULT_KEY_SUCCESS] and self._is_alternate_state_none(main_result_dict):
            self._handle_alternate_state_result(main_result_dict, sensor_context)
            return

        self._handle_evaluation_failure(main_result)

    def _handle_successful_result(self, main_result_dict: dict[str, Any], sensor_context: SensorEvaluationContext) -> None:
        """Handle successful formula evaluation result."""
        # Unwrap ReferenceValue if present
        value = main_result_dict[RESULT_KEY_VALUE]
        if isinstance(value, dict) and RESULT_KEY_SUCCESS in value:
            # Nested EvaluationResult - prefer its value
            value = value.get(RESULT_KEY_VALUE)
        self._attr_native_value = value
        self._attr_available = True
        self._last_update = datetime.now()

        # Evaluate calculated attributes with inherited sensor context
        self._evaluate_attributes(cast(EvaluationResult, main_result_dict), sensor_context)

        # Update extra state attributes with calculated values using hierarchical context
        self._update_extra_state_attributes(sensor_context)

        # Update last-good attributes on successful (non-alternate) results
        self._update_last_valid_attributes(main_result_dict)

        # Notify sensor manager of successful update
        self._sensor_manager.on_sensor_updated(
            self._config.unique_id,
            main_result_dict[RESULT_KEY_VALUE],
            self._calculated_attributes.copy(),
        )

    def _handle_unknown_state_result(self, main_result_dict: dict[str, Any]) -> None:
        """Handle case where evaluation succeeded but dependencies are unknown."""
        # Keep sensor available but with unknown state - this allows the sensor to show as "unknown" in Home Assistant UI
        # Only fatal errors (like MissingDependencyError) should make sensors unavailable
        # Set native_value to None to properly represent unknown state
        self._attr_native_value = None
        self._attr_available = True  # Keep sensor available but with unknown state
        self._last_update = datetime.now()
        _LOGGER.debug(
            "Sensor %s set to unknown state but kept available - result: %s",
            self.entity_id,
            main_result_dict,
        )

    def _is_alternate_state_none(self, main_result_dict: dict[str, Any]) -> bool:
        """Check if result represents alternate state with STATE_NONE."""
        return main_result_dict.get(RESULT_KEY_STATE) == STATE_NONE or main_result_dict.get(RESULT_KEY_STATE) == "STATE_NONE"

    def _handle_alternate_state_result(self, main_result_dict: dict[str, Any], sensor_context: SensorEvaluationContext) -> None:
        """Handle successful alternate state handler result."""
        self._attr_native_value = main_result_dict[RESULT_KEY_VALUE]
        self._attr_available = True
        self._last_update = datetime.now()

        # RECURSION FIX: Don't re-evaluate attributes in alternate state path
        # Attributes should have already been evaluated in the main success path
        # Re-evaluating them here causes context pollution and string reference issues
        _LOGGER.debug(
            "ALTERNATE_STATE_DEBUG: Skipping attribute re-evaluation for %s (attributes already evaluated)", self.entity_id
        )

        # Preserve and restore last-valid attributes during alternate state processing
        preserved_attributes = self._preserve_last_valid_attributes()
        self._update_extra_state_attributes(sensor_context)
        self._restore_last_valid_attributes(preserved_attributes)

    def _preserve_last_valid_attributes(self) -> tuple[str | None, str | None]:
        """Preserve existing last_valid_state attributes before processing."""
        preserved_last_valid_state = None
        preserved_last_valid_changed = None
        try:
            if hasattr(self, "_attr_extra_state_attributes") and self._attr_extra_state_attributes:
                preserved_last_valid_state = self._attr_extra_state_attributes.get(LAST_VALID_STATE_KEY)
                preserved_last_valid_changed = self._attr_extra_state_attributes.get(LAST_VALID_CHANGED_KEY)
                _LOGGER.debug(
                    "Alternate state preservation: Found existing attributes for %s: last_valid_state=%s, last_valid_changed=%s",
                    self.entity_id,
                    preserved_last_valid_state,
                    preserved_last_valid_changed,
                )
            else:
                _LOGGER.debug(
                    "Alternate state preservation: No existing attributes to preserve for %s (hasattr=%s, attrs=%s)",
                    self.entity_id,
                    hasattr(self, "_attr_extra_state_attributes"),
                    getattr(self, "_attr_extra_state_attributes", None),
                )
        except Exception:
            _LOGGER.debug("Failed to preserve existing last_valid_* attributes for %s", self.entity_id, exc_info=True)
        return preserved_last_valid_state, preserved_last_valid_changed

    def _restore_last_valid_attributes(self, preserved_attributes: tuple[str | None, str | None]) -> None:
        """Restore preserved last-valid attributes after processing."""
        preserved_last_valid_state, preserved_last_valid_changed = preserved_attributes
        try:
            if preserved_last_valid_state is not None or preserved_last_valid_changed is not None:
                attrs = dict(self._attr_extra_state_attributes or {})

                if preserved_last_valid_state is not None:
                    attrs[LAST_VALID_STATE_KEY] = preserved_last_valid_state
                if preserved_last_valid_changed is not None:
                    attrs[LAST_VALID_CHANGED_KEY] = preserved_last_valid_changed

                self._attr_extra_state_attributes = attrs
        except Exception:  # defensive - should never fail
            _LOGGER.debug(
                "Failed to restore last_valid_* attributes during alternate state for %s", self.entity_id, exc_info=True
            )

    def _update_last_valid_attributes(self, main_result_dict: dict[str, Any]) -> None:
        """Update last-good attributes on successful (non-alternate) results."""
        try:
            # Only record last-good when evaluator state is STATE_OK
            if main_result_dict.get(RESULT_KEY_STATE) == STATE_OK:
                attrs = dict(self._attr_extra_state_attributes or {})

                # Expose only the public (non-underscored) last-valid keys.
                # Historically we wrote double-underscore keys; remove those to avoid collisions.
                attrs[LAST_VALID_STATE_KEY] = main_result_dict[RESULT_KEY_VALUE]
                attrs[LAST_VALID_CHANGED_KEY] = (
                    self._last_update.isoformat() if self._last_update else datetime.now().isoformat()
                )

                self._attr_extra_state_attributes = attrs
        except Exception:  # defensive - should never fail
            _LOGGER.debug("Failed to update __last_valid_* attributes for %s", self.entity_id, exc_info=True)

    def _handle_evaluation_failure(self, main_result: EvaluationResult) -> None:
        """Handle evaluation failure."""
        self._attr_available = False
        error_msg = main_result.get(RESULT_KEY_ERROR, "Unknown evaluation error")
        # Treat formula evaluation failure as a fatal error
        _LOGGER.error("Formula evaluation failed for %s: %s", self.entity_id, error_msg)
        raise FormulaEvaluationError(f"Formula evaluation failed for {self.entity_id}: {error_msg}")

    async def _update_dependencies_from_evaluation(self) -> None:
        """Update dependency tracking based on entities discovered during evaluation.

        DISABLED: Synthetic sensors should not listen to HA state changes.
        The integration handles all updates via async_update_sensors_for_entities()
        using virtual backing entities, not real HA entities.

        Setting up HA listeners creates recursion loops when synthetic sensors
        trigger updates of other synthetic sensors through HA state changes.
        """
        # DISABLED: No HA state change listeners for synthetic sensors
        # Virtual backing entities are managed by the integration, not HA
        return

    async def _async_update_sensor(self) -> None:
        """Update the sensor value and calculated attributes by evaluating formulas."""
        # Global evaluation barrier: wait until evaluations are allowed
        if not await self._wait_for_evaluation_gate():
            return

        # Create evaluation context for this sensor
        context_manager = get_context_manager()
        entity_id = getattr(self, "entity_id", None) or f"sensor.{self._config.unique_id}"
        sensor_context = context_manager.create_context(self._config.unique_id, self._hass, entity_id)

        try:
            self._setup_sensor_context(sensor_context)
            has_backing_entity = self._check_backing_entity()
            self._initialize_last_valid_attributes(has_backing_entity)
            self._setup_initial_state_in_context(sensor_context, has_backing_entity)

            # Get the accumulated context for evaluation (now includes proper state)
            eval_context = sensor_context.get_context_for_evaluation()

            # Evaluate the main formula with the hierarchical context
            main_result = self._evaluator.evaluate_formula_with_sensor_config(self._main_formula, eval_context, self._config)

            # Update the state value in context immediately after main evaluation
            self._update_context_with_main_result(main_result, eval_context)

            # Handle the main result with sensor context for proper attribute inheritance
            self._handle_main_result(main_result, sensor_context)

            # Extract discovered entities from evaluation and update dependencies if needed
            await self._update_dependencies_from_evaluation()

            # Schedule entity update; be defensive if platform hooks are unavailable
            self._write_ha_state_safely()

        except Exception as err:
            self._handle_sensor_update_error(err)
        finally:
            # Clean up the sensor context
            context_manager.remove_context(self._config.unique_id)

    async def _wait_for_evaluation_gate(self) -> bool:
        """Wait for evaluations to be allowed. Returns False if gate wait fails."""
        try:
            gate_result = self._sensor_manager.wait_for_evaluations_allowed()
            # Await if the result is awaitable; otherwise proceed
            if _inspect.isawaitable(gate_result):
                await gate_result
            return True
        except Exception as err:
            self._attr_available = False
            _LOGGER.error("Evaluation gate wait failed for %s: %s", self.entity_id, err)
            return False

    def _setup_sensor_context(self, sensor_context: SensorEvaluationContext) -> None:
        """Set up the sensor context with global variables and formula variables."""
        # Add global variables as ReferenceValues (from evaluator's context building phase)
        self._add_global_variables_to_context(sensor_context)
        # Add variables from the main formula directly to the sensor context
        # This maintains the single context architecture instead of creating separate contexts
        self._add_variables_to_sensor_context(self._main_formula, sensor_context)

    def _add_global_variables_to_context(self, sensor_context: SensorEvaluationContext) -> None:
        """Add global variables from evaluator to sensor context."""
        context_building_phase = getattr(self._evaluator, "_context_building_phase", None)
        if not (context_building_phase and hasattr(context_building_phase, "_global_settings")):
            return

        global_settings = context_building_phase._global_settings  # pylint: disable=protected-access
        if not (global_settings and "variables" in global_settings):
            return

        # Convert global variables to ReferenceValues
        global_refs = {}
        for var_name, var_value in global_settings["variables"].items():
            # Create ReferenceValue for each global variable
            ref_value = ReferenceValue(
                reference=f"global.{var_name}",  # Mark as global variable
                value=var_value,
                last_valid_state=var_value,
                last_valid_changed=None,
            )
            global_refs[var_name] = ref_value

        # Convert ReferenceValue objects to ContextValue for the sensor context
        global_context_values: dict[str, ContextValue] = {}
        for var_name, ref_value in global_refs.items():
            global_context_values[var_name] = ref_value
        sensor_context.add_global_variables(global_context_values)

    def _check_backing_entity(self) -> bool:
        """Check if this sensor has a backing entity."""
        return self._config.entity_id is not None or (
            bool(self._sensor_manager.sensor_to_backing_mapping)
            and self._config.unique_id in self._sensor_manager.sensor_to_backing_mapping
        )

    def _initialize_last_valid_attributes(self, has_backing_entity: bool) -> None:
        """Initialize last_valid_state and last_valid_changed attributes."""
        attrs = dict(self._attr_extra_state_attributes or {})
        if LAST_VALID_STATE_KEY not in attrs:
            # If we have a backing entity, try to seed from it first
            if has_backing_entity:
                backing_entity_id: str | None = self._config.entity_id
                if not backing_entity_id and self._sensor_manager.sensor_to_backing_mapping:
                    backing_entity_id = self._sensor_manager.sensor_to_backing_mapping.get(self._config.unique_id)

                if backing_entity_id:
                    self._attempt_seed_last_valid(backing_entity_id)

            # If still not set (no backing entity or seeding failed), use defaults
            attrs = dict(self._attr_extra_state_attributes or {})
            if LAST_VALID_STATE_KEY not in attrs:
                attrs[LAST_VALID_STATE_KEY] = "unknown"
                attrs[LAST_VALID_CHANGED_KEY] = datetime.now(UTC).isoformat()
                self._attr_extra_state_attributes = attrs

    def _update_context_with_main_result(self, main_result: EvaluationResult, eval_context: HierarchicalContextDict) -> None:
        """Update the state value in context immediately after main evaluation."""
        main_result_dict = cast(dict[str, Any], main_result)
        if main_result_dict[RESULT_KEY_SUCCESS] and main_result_dict[RESULT_KEY_VALUE] is not None:
            # Use StateResolver to properly update the state reference with unified logic
            # This ensures both 'state' token and entity_id reference the same ReferenceValue
            StateResolver.update_context_with_main_result(
                context=eval_context,
                sensor_config=self._config,
                main_result_value=main_result_dict[RESULT_KEY_VALUE],
                sensor_to_backing_mapping=self._sensor_manager.sensor_to_backing_mapping,
                data_provider_callback=self._sensor_manager.manager_config.data_provider_callback,
                hass=self._hass,
            )

    def _write_ha_state_safely(self) -> None:
        """Write HA state with defensive error handling."""
        try:
            self.async_write_ha_state()
        except Exception as write_err:  # pragma: no cover - defensive
            _LOGGER.debug("async_write_ha_state unavailable: %s", write_err)

    def _handle_sensor_update_error(self, err: Exception) -> None:
        """Handle general sensor update errors."""
        # General exception: make sensor unknown but keep previous state
        self._attr_available = False
        _LOGGER.error("Error updating sensor %s: %s", self.entity_id, err)
        try:
            self.async_write_ha_state()
        except Exception as write_err:  # pragma: no cover - defensive
            _LOGGER.debug("async_write_ha_state unavailable in error path: %s", write_err)

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

        # Force re-evaluation without refreshing dependency listeners in this cycle
        self._suppress_dependency_refresh = True
        try:
            await self._async_update_sensor()
        finally:
            self._suppress_dependency_refresh = False

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
        return extract_attribute_name(formula, self._config.unique_id)

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
        self._change_notifier: DataProviderChangeNotifier | None = None  # Callback for data change notifications
        self._sensor_to_backing_mapping: dict[str, str] = {}  # Mapping from sensor keys to backing entity IDs

        # Configuration tracking
        self._current_config: Config | None = None
        self._setup_complete: bool = False  # Guard against multiple initial setups

        # Initialize components - use parent-provided instances if available
        self._evaluator = self._manager_config.evaluator or Evaluator(
            self._hass,
            data_provider_callback=self._manager_config.data_provider_callback,
        )
        self._config_manager = self._manager_config.config_manager
        self._logger = _LOGGER.getChild(self.__class__.__name__)

        # Device registry for device association
        self._device_registry = dr.async_get(self._hass)

        # Cross-sensor reference manager for Phase 2 of cross-sensor reference system
        self._cross_sensor_ref_manager = CrossSensorReferenceManager(self._hass)

        # Storage manager reference (set via register_with_storage_manager)
        self._storage_manager: StorageManager | None = None

        # Evaluation barrier gate (default open)
        self._eval_gate: asyncio.Event = asyncio.Event()
        self._eval_gate.set()

        # Debug logging removed to reduce verbosity

    @property
    def manager_config(self) -> Any:
        """Return the manager configuration."""
        return self._manager_config

    def _get_existing_device_info(self, device_identifier: str) -> DeviceInfo | None:
        """Get device info for an existing device by identifier."""
        # Look up existing device in registry using integration domain
        integration_domain = self._manager_config.integration_domain
        lookup_identifier = (integration_domain, device_identifier)

        device_entry = self._device_registry.async_get_device(identifiers={lookup_identifier})

        if device_entry:
            return DeviceInfo(
                identifiers={(integration_domain, device_identifier)},
                name=device_entry.name,
                manufacturer=device_entry.manufacturer,
                model=device_entry.model,
                sw_version=device_entry.sw_version,
                hw_version=device_entry.hw_version,
            )

        # Debug logging removed to reduce verbosity
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
        # Debug logging removed to reduce verbosity

    def _log_sensor_configuration_details(self, config: Config) -> None:
        """Log detailed sensor configuration information."""
        if not config.sensors:
            _LOGGER.error("No sensors in configuration - this is a fatal error")
            raise ValueError("No sensors found in configuration")

        # Debug logging removed to reduce verbosity
        _LOGGER.info("Configuration contains %d sensors", len(config.sensors))

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
            raise ValueError("Phase 3 completion callback called but no resolved config available")

        # Debug logging removed to reduce verbosity

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

        _LOGGER.debug("All sensors updated with resolved cross-sensor references")

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
            _LOGGER.debug("Successfully persisted resolved configurations to storage")

        except Exception as err:
            _LOGGER.error("Failed to persist resolved configurations to storage: %s", err)
            # Don't raise - this shouldn't block the main functionality

    async def load_configuration(self, config: Config) -> None:
        """Load a new configuration and update sensors accordingly."""

        # Guard against multiple initial setups on fresh instances
        if self._setup_complete and not self._current_config:
            _LOGGER.warning(
                "Multiple setup attempts detected without existing configuration. "
                "This suggests improper multiple initialization calls. Ignoring duplicate setup."
            )
            return

        # If we have sensors already and same config, this is likely a duplicate call
        if (
            self._setup_complete
            and self._current_config
            and len(self._sensors_by_unique_id) > 0
            and self._is_same_configuration(self._current_config, config)
        ):
            _LOGGER.info(
                "Configuration already loaded with %d sensors. Ignoring duplicate load_configuration call.",
                len(self._sensors_by_unique_id),
            )
            return

        # Log detailed sensor information
        self._log_sensor_configuration_details(config)

        old_config = self._current_config
        self._current_config = config

        # Set global settings before sensor creation to fix boot-time evaluation
        # This ensures global variables are available during the first evaluation in async_added_to_hass
        if config.global_settings:
            # Update global settings on the evaluator's variable resolution phase
            variable_resolution_phase = getattr(self._evaluator, "_variable_resolution_phase", None)
            if variable_resolution_phase and hasattr(variable_resolution_phase, "set_global_settings"):
                variable_resolution_phase.set_global_settings(config.global_settings)

            # Also update global settings on the context building phase
            # This ensures global variables are available BEFORE computed variables are evaluated
            context_building_phase = getattr(self._evaluator, "_context_building_phase", None)
            if context_building_phase and hasattr(context_building_phase, "set_global_settings"):
                context_building_phase.set_global_settings(config.global_settings)
                self._logger.debug(
                    "Set global settings at boot: %s",
                    list(config.global_settings.get("variables", {}).keys()),
                )

        try:
            # Determine what needs to be updated
            if old_config:
                _LOGGER.debug("Updating existing sensors...")
                await self._update_existing_sensors(old_config, config)
            else:
                _LOGGER.debug("Creating all sensors from scratch...")
                await self._create_all_sensors(config)
                self._setup_complete = True  # Mark initial setup as complete

            _LOGGER.debug("Configuration loaded successfully")
            # Debug logging removed to reduce verbosity

        except Exception as err:
            _LOGGER.error("Failed to load configuration: %s", err)
            # Restore old configuration if possible
            if old_config:
                self._current_config = old_config
            else:
                self._setup_complete = False  # Reset if initial setup failed
            raise

    def _is_same_configuration(self, config1: Config, config2: Config) -> bool:
        """Check if two configurations are essentially the same to detect duplicate loads."""
        if len(config1.sensors) != len(config2.sensors):
            return False

        # Compare sensor unique IDs and entity IDs
        config1_sensors = {(s.unique_id, s.entity_id) for s in config1.sensors}
        config2_sensors = {(s.unique_id, s.entity_id) for s in config2.sensors}

        return config1_sensors == config2_sensors

    async def reload_configuration(self, config: Config) -> None:
        """Reload configuration, removing old sensors and creating new ones."""
        _LOGGER.debug("Reloading configuration")

        # Ensure evaluations are not blocked after reload
        self.resume_evaluations()

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
                last_update=datetime.now(),
            )
        else:
            state = self._sensor_states[sensor_unique_id]
            state.main_value = main_value
            state.calculated_attributes = calculated_attributes
            state.last_update = datetime.now()
            state.is_available = True

        # INFINITE LOOP FIX: Removed problematic cross-sensor reference update
        # The evaluator.update_sensor_value() call was causing infinite loops
        # Cross-sensor references should be resolved during evaluation, not here

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
                # Check if sensor already exists to prevent duplicate registration
                if sensor_config.unique_id in self._sensors_by_unique_id:
                    continue

                try:
                    sensor = await self._create_sensor_entity(sensor_config)

                    # Check for entity_id collision
                    if sensor.entity_id in self._sensors_by_entity_id:
                        existing_sensor = self._sensors_by_entity_id[sensor.entity_id]
                        _LOGGER.warning(
                            "ENTITY_ID COLLISION: new sensor %s wants entity_id %s, already used by %s",
                            sensor_config.unique_id,
                            sensor.entity_id,
                            existing_sensor.config_unique_id,
                        )

                    new_entities.append(sensor)
                    self._sensors_by_unique_id[sensor_config.unique_id] = sensor
                    self._sensors_by_entity_id[sensor.entity_id] = sensor
                except Exception as e:
                    self._logger.error("Failed to create sensor %s: %s", sensor_config.unique_id, e)
                    raise

        # Validate cross-sensor dependencies after registration
        self._logger.debug("About to validate cross-sensor dependencies after registration")
        self._validate_cross_sensor_dependencies(config.sensors)

        # Add entities to Home Assistant
        if new_entities:
            self._add_entities_callback(new_entities)
        else:
            # Only raise error if no sensors exist at all, not if all were already created
            if not self._sensors_by_unique_id:
                raise SyntheticSensorsConfigError("No sensors found in configuration - at least one sensor is required")

    async def _create_sensor_entity(self, sensor_config: SensorConfig) -> DynamicSensor:
        """Create a sensor entity from configuration."""
        device_info = None

        if sensor_config.device_identifier:
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
                sensor_config = sensor_config.copy_with_overrides(entity_id=generated_entity_id)
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
                # Check if sensor already exists to prevent duplicate registration
                if sensor_config.unique_id in self._sensors_by_unique_id:
                    _LOGGER.debug("Sensor %s already exists in update, skipping creation", sensor_config.unique_id)
                    continue

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

    async def _update_sensor_config(self, old_config: SensorConfig, new_config: SensorConfig) -> None:
        """Update an existing sensor with new configuration."""
        # Simplified approach - remove and recreate if changes exist
        existing_sensor = self._sensors_by_unique_id.get(old_config.unique_id)

        if existing_sensor:
            await self.remove_sensor(old_config.unique_id)

            if new_config.enabled:
                # Check if sensor already exists to prevent duplicate registration
                if new_config.unique_id in self._sensors_by_unique_id:
                    _LOGGER.debug("Sensor %s already exists during update, skipping creation", new_config.unique_id)
                    return

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
            state.last_update = datetime.now()
        else:
            self._sensor_states[sensor_unique_id] = SensorState(
                sensor_name=sensor_unique_id,
                main_value=main_value,
                calculated_attributes=calculated_attributes,
                last_update=datetime.now(),
            )

    async def async_update_sensors(self, sensor_configs: list[SensorConfig] | None = None) -> None:
        """Enhanced evaluation loop with cross-sensor dependency management."""
        # Update global settings on evaluator before starting evaluation
        self._update_global_settings_on_evaluator()

        # Start new update cycle - clears cache for fresh data
        self._evaluator.start_update_cycle()

        try:
            if sensor_configs is None:
                # For full sensor updates, invalidate sensor entity caches to prevent
                # state variable from resolving to sensor's own calculated result instead of backing entity
                sensor_entity_ids = set()
                for sensor in self._sensors_by_unique_id.values():
                    if sensor.config.entity_id:
                        sensor_entity_ids.add(sensor.config.entity_id)

                if sensor_entity_ids:
                    ReferenceValueManager.invalidate_entities(sensor_entity_ids)
                    _LOGGER.debug("SensorManager: Invalidated sensor entity caches for full update: %s", sensor_entity_ids)

                # Update all managed sensors with cross-sensor evaluation order
                evaluation_order = self._get_cross_sensor_evaluation_order()
                await self._update_sensors_in_order(evaluation_order)
            else:
                # Update specific sensors with cross-sensor evaluation order
                evaluation_order = self._get_cross_sensor_evaluation_order_for_sensors(sensor_configs)
                await self._update_sensors_in_order(evaluation_order)
                self._logger.debug("Completed enhanced async sensor updates")
        finally:
            # End update cycle - ensures cache is cleared for next update
            self._evaluator.end_update_cycle()

    async def _update_sensors_in_order(self, evaluation_order: list[str]) -> None:
        """Update sensors in the specified evaluation order.

        Args:
            evaluation_order: List of sensor names in evaluation order
        """
        for sensor_name in evaluation_order:
            if sensor_name not in self._sensors_by_unique_id:
                continue

            try:
                sensor = self._sensors_by_unique_id[sensor_name]
                await sensor.async_update_sensor()
                self._update_cross_sensor_registry(sensor_name, sensor)
            except Exception as e:
                self._handle_cross_sensor_error(sensor_name, e)

    def _update_cross_sensor_registry(self, sensor_name: str, sensor: DynamicSensor) -> None:
        """Update cross-sensor registry with sensor value.

        Args:
            sensor_name: Name of the sensor
            sensor: The sensor instance
        """
        if self._evaluator and hasattr(sensor, "native_value"):
            self._evaluator.update_sensor_value(sensor_name, sensor.native_value)

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
            issues = validation_result.get("issues", [])
            raise DependencyValidationError("cross_sensor_dependencies", f"Cross-sensor dependency validation issues: {issues}")

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
            issues = validation_result.get("issues", [])
            raise DependencyValidationError("cross_sensor_dependencies", f"Cross-sensor dependency validation issues: {issues}")

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
            self._logger.debug("Evaluator not available, skipping cross-sensor registry registration")
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
        self._logger.debug("Validating cross-sensor dependencies for %d sensors", len(sensor_configs))
        if not self.dependency_management_phase:
            self._logger.debug("Dependency management phase not available, skipping validation")
            return

        try:
            # Analyze cross-sensor dependencies
            dependency_phase = self.dependency_management_phase
            sensor_dependencies = dependency_phase.analyze_cross_sensor_dependencies(sensor_configs)

            # Validate dependencies
            validation_result = dependency_phase.validate_cross_sensor_dependencies(sensor_dependencies)

            # Check for circular references and log warning
            circular_refs = validation_result.get("circular_references", [])
            if circular_refs:
                self._logger.warning("Circular cross-sensor dependency detected among: %s", sorted(set(circular_refs)))

            if not validation_result.get("valid", True):
                issues = validation_result.get("issues", [])
                error_msg = f"Cross-sensor dependency validation failed: {issues}"
                if circular_refs:
                    error_msg += f" Circular references: {circular_refs}"
                self._logger.error(error_msg)
                raise ValueError(error_msg)

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
        if isinstance(error, MissingDependencyError | CrossSensorResolutionError | DependencyValidationError):
            self._logger.error("Cross-sensor resolution error for sensor '%s': %s", sensor_name, error)
        else:
            self._logger.error("Unexpected error during cross-sensor resolution for sensor '%s': %s", sensor_name, error)

    # New push-based registration API
    def register_data_provider_entities(
        self, entity_ids: set[str], change_notifier: DataProviderChangeNotifier | None = None
    ) -> None:
        """Register entities that the integration can provide data for.

        This replaces any existing entity list with the new one. Variables will
        automatically try registered backing entities first, then fall back to
        HA entity lookups for unregistered entities.

        Args:
            entity_ids: Set of entity IDs that the integration can provide data for
            change_notifier: Optional callback that the integration can call when backing
                           entity data changes to trigger selective sensor updates.

        Raises:
            ValueError: If the entity_ids set contains invalid entries (None values, empty strings, etc.)
        """
        # Debug logging removed to reduce verbosity
        # Debug logging removed to reduce verbosity

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

            # Debug logging removed to reduce verbosity

            # Debug logging removed to reduce verbosity
        else:
            # Empty set provided directly - this is an error
            raise SyntheticSensorsConfigError(
                "Empty backing entity set provided explicitly. "
                "Use None or omit the parameter for HA-only mode, or provide actual backing entities."
            )

        # Store the registered entities
        self._registered_entities = entity_ids.copy()
        self._change_notifier = change_notifier

        # Update the evaluator if it has the new registration support
        if hasattr(self._evaluator, "update_integration_entities"):
            self._evaluator.update_integration_entities(entity_ids)
            # Debug logging removed to reduce verbosity

        # Debug logging removed to reduce verbosity

    def register_sensor_to_backing_mapping(self, sensor_to_backing_mapping: dict[str, str]) -> None:
        """Register the mapping from sensor keys to backing entity IDs.

        This mapping is used for state token resolution in formulas.

        Args:
            sensor_to_backing_mapping: Mapping from sensor keys to backing entity IDs

        Raises:
            ValueError: If the mapping contains invalid entries (None values, empty strings, etc.)
                       or if the mapping is empty (which would break state token resolution)
        """
        # Debug logging removed to reduce verbosity
        # Debug logging removed to reduce verbosity

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

        # Debug logging removed to reduce verbosity

        # Store the mapping
        self._sensor_to_backing_mapping = sensor_to_backing_mapping.copy()

        # Update the evaluator if it supports the mapping
        if hasattr(self._evaluator, "update_sensor_to_backing_mapping"):
            self._evaluator.update_sensor_to_backing_mapping(sensor_to_backing_mapping)

    def update_data_provider_entities(
        self, entity_ids: set[str], change_notifier: DataProviderChangeNotifier | None = None
    ) -> None:
        """Update the registered entity list (replaces existing list).

        Args:
            entity_ids: Updated set of entity IDs the integration can provide data for
            change_notifier: Optional callback that the integration can call when backing
                           entity data changes to trigger selective sensor updates.
        """
        self.register_data_provider_entities(entity_ids, change_notifier)

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

        # Invalidate cached ReferenceValues for changed entities
        # This ensures that fresh values are read from the data provider instead of using stale cached values

        # Find all sensor entity IDs that depend on the changed backing entities
        # We need to invalidate both the backing entities AND the sensors that depend on them
        entities_to_invalidate = set(changed_entity_ids)

        for sensor in self._sensors_by_unique_id.values():
            sensor_backing_entities = self._extract_backing_entities_from_sensor(sensor.config)
            if sensor_backing_entities.intersection(changed_entity_ids) and sensor.config.entity_id:
                # This sensor depends on a changed backing entity, so invalidate its cache too
                entities_to_invalidate.add(sensor.config.entity_id)

        ReferenceValueManager.invalidate_entities(entities_to_invalidate)
        _LOGGER.debug(
            "SensorManager: Invalidated ReferenceValue cache for entities: %s (changed: %s)",
            entities_to_invalidate,
            changed_entity_ids,
        )

        # Find sensors that use any of the changed backing entities
        affected_sensor_configs = []
        for sensor in self._sensors_by_unique_id.values():
            sensor_backing_entities = self._extract_backing_entities_from_sensor(sensor.config)
            if sensor_backing_entities.intersection(changed_entity_ids):
                affected_sensor_configs.append(sensor.config)

        if affected_sensor_configs:
            await self.async_update_sensors(affected_sensor_configs)

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
            # Check explicit variables for backing entity references
            if formula.variables:
                for var_value in formula.variables.values():
                    # Check if this looks like an entity ID that would use integration data provider
                    if (
                        isinstance(var_value, str)
                        and var_value.startswith("sensor.")
                        and var_value in self._registered_entities
                    ):
                        backing_entities.add(var_value)

            # Check for 'state' token that gets resolved to backing entities
            if (
                "state" in formula.formula
                and self._sensor_to_backing_mapping
                and sensor_config.unique_id in self._sensor_to_backing_mapping
            ):
                backing_entity_id = self._sensor_to_backing_mapping[sensor_config.unique_id]
                backing_entities.add(backing_entity_id)

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

    async def add_sensor_with_backing_entities(self, sensor_config: SensorConfig) -> bool:
        """Add a sensor and automatically register its backing entities.

        This is the enhanced CRUD method that makes backing entity management invisible.

        Args:
            sensor_config: The sensor configuration to add

        Returns:
            True if sensor was added successfully
        """
        try:
            # Extract backing entities from this sensor
            backing_entities = self._extract_backing_entities_from_sensor(sensor_config)

            # Add backing entities to our registered entities
            if backing_entities:
                updated_entities = self._registered_entities.union(backing_entities)
                self.register_data_provider_entities(updated_entities)
                _LOGGER.debug(
                    "Auto-registered %d backing entities for sensor %s: %s",
                    len(backing_entities),
                    sensor_config.unique_id,
                    backing_entities,
                )

            # Create the sensor entity
            if sensor_config.enabled:
                # Check if sensor already exists to prevent duplicate registration
                if sensor_config.unique_id in self._sensors_by_unique_id:
                    _LOGGER.debug("Sensor %s already exists, skipping individual creation", sensor_config.unique_id)
                    return True

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
                    self.register_data_provider_entities(updated_entities)
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

    async def reload_from_storage(self, storage_manager: StorageManager) -> None:
        """Reload this manager's configuration from storage based on its device identifier.

        This ensures runtime state reflects storage after structural changes (e.g., entity_id rename).
        """
        device_id = self._get_current_device_identifier()
        config = storage_manager.to_config(device_identifier=device_id) if device_id else storage_manager.to_config()
        await self.reload_configuration(config)

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

        # No device_identifier provided - use default format
        return f"sensor.{sensor_key}"

    def _update_global_settings_on_evaluator(self) -> None:
        """Update global settings on the evaluator before evaluation starts.

        This ensures that global variables are available during formula evaluation,
        fixing the runtime execution issue for computed variables referencing globals.
        """

        if not self._storage_manager:
            return

        try:
            # Get current global settings from storage manager
            # We need to get the sensor set that this manager is associated with
            # For now, we'll iterate through sensor sets to find the one with our device_identifier
            device_id = self._get_current_device_identifier()
            if not device_id:
                return

            # Find the sensor set with matching device identifier
            sensor_sets_metadata = self._storage_manager.list_sensor_sets()
            target_sensor_set = None

            for sensor_set_metadata in sensor_sets_metadata:
                # sensor_set_metadata is a SensorSetMetadata object
                if sensor_set_metadata.device_identifier == device_id:
                    target_sensor_set = self._storage_manager.get_sensor_set(sensor_set_metadata.sensor_set_id)
                    break

            if target_sensor_set:
                global_settings = target_sensor_set.get_global_settings()

                # Update global settings on the evaluator's variable resolution phase
                variable_resolution_phase = getattr(self._evaluator, "_variable_resolution_phase", None)
                if variable_resolution_phase and hasattr(variable_resolution_phase, "set_global_settings"):
                    variable_resolution_phase.set_global_settings(global_settings)

                # Also update global settings on the context building phase
                # This ensures global variables are available BEFORE computed variables are evaluated
                context_building_phase = getattr(self._evaluator, "_context_building_phase", None)
                if context_building_phase and hasattr(context_building_phase, "set_global_settings"):
                    context_building_phase.set_global_settings(global_settings)
                    self._logger.info(
                        list(global_settings.get("variables", {}).keys()),
                    )
                else:
                    self._logger.warning("❌ Context building phase not available for global settings update")
            else:
                self._logger.debug("No sensor set found with device identifier: %s", device_id)

        except Exception as e:
            self._logger.warning("Failed to update global settings on evaluator: %s", e)

    def _get_current_device_identifier(self) -> str | None:
        """Get the device identifier for the current sensor manager."""
        # Check if we have sensors and can get device identifier from them
        if self._sensors_by_unique_id:
            # Get device identifier from first sensor's device info
            first_sensor = next(iter(self._sensors_by_unique_id.values()))
            if hasattr(first_sensor, "_device_identifier"):
                device_id = getattr(first_sensor, "_device_identifier", None)
                if isinstance(device_id, str):
                    return device_id

        # Check manager config
        if hasattr(self._manager_config, "device_identifier"):
            return self._manager_config.device_identifier

        return None

    # Evaluation barrier control
    def pause_evaluations(self) -> None:
        """Pause evaluations by closing the gate (idempotent)."""
        if self._eval_gate.is_set():
            self._eval_gate.clear()

    def resume_evaluations(self) -> None:
        """Resume evaluations by opening the gate (idempotent)."""
        if not self._eval_gate.is_set():
            self._eval_gate.set()

    async def _wait_for_evaluations_allowed(self) -> None:
        """Wait until evaluations are allowed by the gate."""
        await self._eval_gate.wait()

    async def wait_for_evaluations_allowed(self) -> None:
        """Public method to wait until evaluations are allowed by the gate."""
        await self._wait_for_evaluations_allowed()
