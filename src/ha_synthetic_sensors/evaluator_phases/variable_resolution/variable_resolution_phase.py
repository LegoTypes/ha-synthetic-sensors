"""Variable resolution phase for handling all formula variable resolution."""

import logging
import re
from typing import Any, Callable

from ...config_models import FormulaConfig, SensorConfig
from ...type_definitions import ContextValue, DataProviderResult
from .resolver_factory import VariableResolverFactory

_LOGGER = logging.getLogger(__name__)


class VariableResolutionPhase:
    """Variable Resolution Engine - Phase 1 of compiler-like formula evaluation."""

    def __init__(
        self,
        sensor_to_backing_mapping: dict[str, str] | None = None,
        data_provider_callback: Callable[[str], DataProviderResult] | None = None,
    ) -> None:
        """Initialize the variable resolution phase."""
        self._resolver_factory = VariableResolverFactory(sensor_to_backing_mapping, data_provider_callback)
        self._sensor_registry_phase: Any = None
        self._formula_preprocessor: Any = None

    def set_formula_preprocessor(self, formula_preprocessor: Any) -> None:
        """Set the formula preprocessor for collection function resolution."""
        self._formula_preprocessor = formula_preprocessor

    def set_sensor_registry_phase(self, sensor_registry_phase: Any) -> None:
        """Set the sensor registry phase for cross-sensor reference resolution."""
        self._sensor_registry_phase = sensor_registry_phase
        # Update the cross-sensor resolver with the registry phase
        self._resolver_factory.set_sensor_registry_phase(sensor_registry_phase)

    def update_sensor_to_backing_mapping(
        self,
        sensor_to_backing_mapping: dict[str, str],
        data_provider_callback: Callable[[str], DataProviderResult] | None = None,
    ) -> None:
        """Update the sensor-to-backing entity mapping and data provider for state resolution."""
        # Update the existing resolver factory instead of recreating it
        self._resolver_factory.update_sensor_to_backing_mapping(sensor_to_backing_mapping, data_provider_callback)

    def set_dependency_handler(self, dependency_handler: Any) -> None:
        """Set the dependency handler to access current data provider callback."""
        self._dependency_handler = dependency_handler

        # Also set the dependency handler on the resolver factory for other resolvers
        self._resolver_factory.set_dependency_handler(dependency_handler)

        # Update the resolver factory with the current data provider callback for StateResolver
        if hasattr(dependency_handler, "data_provider_callback"):
            current_data_provider = dependency_handler.data_provider_callback
            # Update existing resolver factory with current data provider
            self._resolver_factory = VariableResolverFactory(
                self._resolver_factory.sensor_to_backing_mapping, current_data_provider
            )
            if self._sensor_registry_phase is not None:
                self._resolver_factory.set_sensor_registry_phase(self._sensor_registry_phase)
            # Re-set the dependency handler after recreating the factory
            self._resolver_factory.set_dependency_handler(dependency_handler)

    def update_data_provider_callback(self, data_provider_callback: Callable[[str], DataProviderResult] | None) -> None:
        """Update the data provider callback for the StateResolver."""
        # Recreate the resolver factory with the updated data provider
        self._resolver_factory = VariableResolverFactory(
            self._resolver_factory.sensor_to_backing_mapping, data_provider_callback
        )
        if self._sensor_registry_phase is not None:
            self._resolver_factory.set_sensor_registry_phase(self._sensor_registry_phase)
        if hasattr(self, "_dependency_handler"):
            self._resolver_factory.set_dependency_handler(self._dependency_handler)

    def resolve_all_references_in_formula(
        self,
        formula: str,
        sensor_config: SensorConfig | None,
        eval_context: dict[str, ContextValue],
        formula_config: FormulaConfig | None = None,
    ) -> str:
        """
        COMPILER-LIKE APPROACH: Resolve ALL references in formula to actual values.

        This method performs a complete resolution pass, handling:
        1. Collection functions (e.g., sum("device_class:power") -> sum(1000, 500, 200))
        2. state.attribute references (e.g., state.voltage -> 240.0)
        3. state references (e.g., state -> 1000.0)
        4. entity references (e.g., sensor.temperature -> 23.5)
        5. cross-sensor references (e.g., base_power_sensor -> 1000.0)

        After this method, the formula should contain only numeric values and operators.
        """
        resolved_formula = formula

        # STEP 0: Resolve collection functions first (they may contain entity references)
        # Collection functions should be resolved regardless of sensor_config
        if self._formula_preprocessor:
            resolved_formula = self._resolve_collection_functions(resolved_formula, sensor_config, eval_context, formula_config)

        # STEP 1: Resolve entity references (should work even without sensor_config)
        resolved_formula = self._resolve_entity_references(resolved_formula, eval_context)

        # STEP 2: Resolve attribute-to-attribute references (if context contains attribute values)
        resolved_formula = self._resolve_attribute_references(resolved_formula, eval_context)

        # Early return if no sensor config for the remaining steps
        if not sensor_config:
            _LOGGER.debug("Formula resolution (no sensor config): '%s' -> '%s'", formula, resolved_formula)
            return resolved_formula

        # Add sensor_config and formula_config to context for resolvers
        extended_context: dict[str, ContextValue] = eval_context.copy()
        extended_context["sensor_config"] = sensor_config  # type: ignore[assignment]
        if formula_config:
            extended_context["formula_config"] = formula_config  # type: ignore[assignment]

        # STEP 3: Resolve state.attribute references including nested attributes
        resolved_formula = self._resolve_state_attribute_references(resolved_formula, sensor_config)

        # STEP 4: Resolve standalone 'state' references
        resolved_formula = self._resolve_state_references(resolved_formula, sensor_config, extended_context)

        # STEP 5: Resolve cross-sensor references
        resolved_formula = self._resolve_cross_sensor_references(resolved_formula, eval_context)

        _LOGGER.debug("Formula resolution: '%s' -> '%s'", formula, resolved_formula)
        return resolved_formula

    def _resolve_attribute_references(self, formula: str, eval_context: dict[str, ContextValue]) -> str:
        """Resolve attribute-to-attribute references in the formula."""
        # Get the attribute reference resolver
        attribute_resolver = None
        for resolver in self._resolver_factory.get_all_resolvers():
            if resolver.get_resolver_name() == "AttributeReferenceResolver":
                attribute_resolver = resolver
                break
                
        if attribute_resolver and hasattr(attribute_resolver, "resolve_references_in_formula"):
            try:
                resolved_formula = attribute_resolver.resolve_references_in_formula(formula, eval_context)
                return resolved_formula
            except Exception as e:
                _LOGGER.warning("Error resolving attribute references in formula '%s': %s", formula, e)
                return formula
        else:
            # No attribute resolver available, return formula unchanged
            return formula

    def _resolve_collection_functions(
        self, 
        formula: str, 
        sensor_config: SensorConfig, 
        eval_context: dict[str, ContextValue],
        formula_config: FormulaConfig | None = None
    ) -> str:
        """Resolve collection functions using the formula preprocessor."""
        if not self._formula_preprocessor:
            return formula
        
        try:
            # Use the formula preprocessor to resolve collection functions
            resolved_formula = self._formula_preprocessor._resolve_collection_functions(formula)
            _LOGGER.debug("Collection function resolution: '%s' -> '%s'", formula, resolved_formula)
            return resolved_formula
        except Exception as e:
            _LOGGER.warning("Error resolving collection functions in formula '%s': %s", formula, e)
            return formula

    def resolve_config_variables(
        self,
        eval_context: dict[str, ContextValue],
        config: FormulaConfig | None,
        sensor_config: SensorConfig | None = None,
    ) -> None:
        """Resolve config variables using the resolver factory."""
        if not config:
            return

        for var_name, var_value in config.variables.items():
            # Skip if this variable is already set in context (context has higher priority)
            if var_name in eval_context:
                _LOGGER.debug("Skipping config variable %s (already set in context)", var_name)
                continue

            try:
                resolved_value = self._resolver_factory.resolve_variable(var_name, var_value, eval_context)
                if resolved_value is not None:
                    eval_context[var_name] = resolved_value
                    _LOGGER.debug("Added config variable %s=%s", var_name, resolved_value)
                else:
                    _LOGGER.warning("Config variable '%s' in formula '%s' resolved to None", var_name, config.name or config.id)
            except Exception as err:
                _LOGGER.warning("Error resolving config variable %s: %s", var_name, err)

    def _resolve_state_attribute_references(self, formula: str, sensor_config: SensorConfig) -> str:
        """Resolve state.attribute references including nested attributes."""
        attr_pattern = re.compile(r"\bstate\.([a-zA-Z_][a-zA-Z0-9_.]*)\b")

        def replace_attr_ref(match: re.Match[str]) -> str:
            attr_path = match.group(1)  # e.g., "voltage" or "device_info.manufacturer"
            attr_ref = f"state.{attr_path}"

            # Create extended context with sensor_config for the resolver
            extended_context = {"sensor_config": sensor_config}

            # Use the resolver factory to resolve the attribute reference
            resolved_value = self._resolver_factory.resolve_variable(attr_ref, attr_ref, extended_context)

            if resolved_value is not None:
                # Handle string concatenation properly
                if isinstance(resolved_value, str):
                    return f'"{resolved_value}"'  # Wrap strings in quotes for proper evaluation
                return str(resolved_value)
            _LOGGER.warning("Failed to resolve attribute reference '%s' in formula", attr_ref)
            # Return None instead of "unknown" to indicate resolution failure
            return "None"

        return attr_pattern.sub(replace_attr_ref, formula)

    def _resolve_state_references(
        self, formula: str, sensor_config: SensorConfig, eval_context: dict[str, ContextValue]
    ) -> str:
        """Resolve standalone 'state' references."""
        if "state" not in formula:
            return formula

        # Only resolve standalone 'state', not 'state.something' (which we already handled)
        state_pattern = re.compile(r"\bstate\b(?!\.)")

        def replace_state_ref(match: re.Match[str]) -> str:
            # Use the resolver factory to resolve the state reference
            # The StateResolver will handle backing entity validation and throw exceptions if needed
            resolved_value = self._resolver_factory.resolve_variable("state", "state", eval_context)

            if resolved_value is not None:
                return str(resolved_value)
            # This should not happen if StateResolver is working correctly
            _LOGGER.warning("State token resolution returned None unexpectedly")
            return "0.0"

        return state_pattern.sub(replace_state_ref, formula)

    def _resolve_entity_references(self, formula: str, eval_context: dict[str, ContextValue]) -> str:
        """Resolve entity references (e.g., sensor.temperature -> 23.5)."""
        entity_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z0-9_.]+)\b")

        def replace_entity_ref(match: re.Match[str]) -> str:
            entity_id = match.group(1)

            # First check if already resolved in context
            var_name = entity_id.replace(".", "_").replace("-", "_")
            if var_name in eval_context:
                return str(eval_context[var_name])
            if entity_id in eval_context:
                return str(eval_context[entity_id])

            # Use the resolver factory to resolve the entity reference
            resolved_value = self._resolver_factory.resolve_variable(entity_id, entity_id, eval_context)

            if resolved_value is not None:
                return str(resolved_value)

            _LOGGER.warning("Failed to resolve entity reference '%s' in formula", entity_id)
            return "0.0"

        return entity_pattern.sub(replace_entity_ref, formula)

    def _resolve_cross_sensor_references(self, formula: str, eval_context: dict[str, ContextValue]) -> str:
        """Resolve cross-sensor references (e.g., base_power_sensor -> 1000.0)."""
        sensor_pattern = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")

        def replace_sensor_ref(match: re.Match[str]) -> str:
            sensor_name = match.group(1)

            # Skip if this looks like a number, operator, or function
            if sensor_name in ["state", "and", "or", "not", "if", "else", "True", "False", "None"]:
                return sensor_name

            # Use the resolver factory to resolve cross-sensor references
            resolved_value = self._resolver_factory.resolve_variable(sensor_name, sensor_name, eval_context)

            if resolved_value is not None:
                # Handle different data types appropriately
                if isinstance(resolved_value, str):
                    return f'"{resolved_value}"'  # Wrap strings in quotes
                return str(resolved_value)
            # Check if this is a cross-sensor reference
            if self._sensor_registry_phase and self._sensor_registry_phase.is_sensor_registered(sensor_name):
                sensor_value = self._sensor_registry_phase.get_sensor_value(sensor_name)
                if sensor_value is not None:
                    return str(sensor_value)
            # Not a cross-sensor reference, return as-is
            return sensor_name

        return sensor_pattern.sub(replace_sensor_ref, formula)
