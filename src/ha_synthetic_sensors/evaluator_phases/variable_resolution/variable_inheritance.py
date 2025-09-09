"""Variable inheritance functionality for attribute formulas."""

import logging
from typing import TYPE_CHECKING, Any

from ha_synthetic_sensors.config_models import ComputedVariable, FormulaConfig, SensorConfig
from ha_synthetic_sensors.exceptions import DataValidationError
from ha_synthetic_sensors.reference_value_manager import ReferenceValueManager

from .resolution_helpers import ResolutionHelpers

if TYPE_CHECKING:
    from ha_synthetic_sensors.hierarchical_context_dict import HierarchicalContextDict


_LOGGER = logging.getLogger(__name__)


class VariableInheritanceHandler:
    """Handles variable inheritance for attribute formulas."""

    def __init__(self, global_settings: dict[str, Any] | None = None):
        """Initialize the variable inheritance handler."""
        self._global_settings = global_settings

    def build_inherited_variables(
        self, formula_config: FormulaConfig, sensor_config: SensorConfig | None
    ) -> dict[str, str | int | float | ComputedVariable]:
        """Build the complete set of variables including inheritance."""
        inherited_variables: dict[str, str | int | float | ComputedVariable] = {}

        # Add inherited variables for attribute formulas
        if sensor_config and self._is_attribute_formula(formula_config):
            self._add_global_variables(inherited_variables, formula_config)
            self._add_parent_sensor_variables(inherited_variables, sensor_config, formula_config)

        # Add formula-specific variables (these override inherited ones)
        inherited_variables.update(formula_config.variables)

        return inherited_variables

    def _add_global_variables(
        self, inherited_variables: dict[str, str | int | float | ComputedVariable], formula_config: FormulaConfig
    ) -> None:
        """Add global variables to inherited variables."""
        if self._global_settings:
            global_vars = self._global_settings.get("variables", {})
            if global_vars:
                inherited_variables.update(global_vars)
                _LOGGER.debug("Inherited %d global variables for attribute '%s'", len(global_vars), formula_config.id)

    def _add_parent_sensor_variables(
        self,
        inherited_variables: dict[str, str | int | float | ComputedVariable],
        sensor_config: SensorConfig,
        formula_config: FormulaConfig,
    ) -> None:
        """Add parent sensor variables to inherited variables."""
        main_formula = self._get_main_formula(sensor_config)
        if main_formula:
            inherited_variables.update(main_formula.variables)
            _LOGGER.debug(
                "Inherited %d variables from parent sensor for attribute '%s'",
                len(main_formula.variables),
                formula_config.id,
            )

    def _is_attribute_formula(self, formula_config: FormulaConfig) -> bool:
        """Check if this is an attribute formula (not the main sensor formula)."""
        return "_" in formula_config.id

    def _get_main_formula(self, sensor_config: SensorConfig) -> FormulaConfig | None:
        """Get the main formula (the one with ID matching sensor unique_id)."""
        for formula in sensor_config.formulas:
            if formula.id == sensor_config.unique_id:
                return formula
        return None

    def process_single_variable(
        self,
        var_name: str,
        var_value: str | int | float | ComputedVariable,
        eval_context: "HierarchicalContextDict",
        formula_config: FormulaConfig,
        variables_needing_entity_ids: set[str],
        resolver_factory: Any,
    ) -> None:
        """Process a single variable with all the necessary checks and resolution."""
        # Skip ComputedVariable instances - they are handled by resolve_config_variables
        if isinstance(var_value, ComputedVariable):
            _LOGGER.debug("INHERITANCE_DEBUG: Skipping ComputedVariable '%s'", var_name)
            return

        # If this variable is used in .attribute patterns, override with entity ID
        if var_name in variables_needing_entity_ids:
            _LOGGER.debug("Overriding variable '%s' with entity ID (used in .attribute pattern): %s", var_name, var_value)
            # Use centralized ReferenceValueManager for type safety
            ReferenceValueManager.set_variable_with_reference_value(
                eval_context,
                var_name,
                var_value,
                var_value,  # For attribute patterns, value IS the reference
            )
            return

        # Skip if this variable is already set in context (context has higher priority)
        if var_name in eval_context:
            _LOGGER.debug("Skipping config variable %s (already set in context)", var_name)
            return

        # Otherwise, resolve normally
        self._resolve_variable_safely(var_name, var_value, eval_context, formula_config, resolver_factory)

    def _resolve_variable_safely(
        self,
        var_name: str,
        var_value: Any,
        eval_context: "HierarchicalContextDict",
        formula_config: FormulaConfig,
        resolver_factory: Any,
    ) -> None:
        """Safely resolve a variable with proper error handling."""
        try:
            resolved_value = resolver_factory.resolve_variable(var_name, var_value, eval_context)
            if resolved_value is not None:
                # Use centralized ReferenceValueManager for type safety
                ResolutionHelpers.log_and_set_resolved_variable(
                    eval_context, var_name, var_value, resolved_value, "VARIABLE_INHERITANCE"
                )
            else:
                _LOGGER.warning(
                    "Config variable '%s' in formula '%s' resolved to None",
                    var_name,
                    formula_config.name or formula_config.id,
                )
        except DataValidationError:
            # Re-raise fatal data validation errors - these should not be suppressed
            raise
        except Exception as err:
            _LOGGER.warning("Error resolving config variable %s: %s", var_name, err)
