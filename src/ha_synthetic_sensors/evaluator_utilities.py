"""Utility methods for the Evaluator class."""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import StateType

from .config_models import FormulaConfig
from .constants_evaluation_results import RESULT_KEY_SUCCESS, RESULT_KEY_VALUE
from .type_definitions import ContextValue

_LOGGER = logging.getLogger(__name__)


class EvaluatorUtilities:
    """Utility methods for evaluator functionality."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize evaluator utilities.

        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        self._sensor_to_backing_mapping: dict[str, str] = {}

    def update_sensor_to_backing_mapping(
        self,
        sensor_to_backing_mapping: dict[str, str],
        variable_resolution_phase: Any,
        pre_evaluation_phase: Any,
        context_building_phase: Any,
        dependency_management_phase: Any,
        data_provider_callback: Any,
        dependency_handler: Any,
        cache_handler: Any,
        error_handler: Any,
    ) -> None:
        """Update the sensor-to-backing entity mapping for state token resolution."""
        self._sensor_to_backing_mapping = sensor_to_backing_mapping.copy()

        # Update the Variable Resolution Phase (Phase 1) - this is where state token resolution happens
        variable_resolution_phase.update_sensor_to_backing_mapping(self._sensor_to_backing_mapping, data_provider_callback)

        # Update all other phases that depend on this mapping
        pre_evaluation_phase.set_evaluator_dependencies(
            self._hass,
            data_provider_callback,
            dependency_handler,
            cache_handler,
            error_handler,
            self._sensor_to_backing_mapping,
            variable_resolution_phase,
            dependency_management_phase,
            context_building_phase,
        )

        context_building_phase.set_evaluator_dependencies(
            self._hass, data_provider_callback, dependency_handler, self._sensor_to_backing_mapping
        )

        dependency_management_phase.set_evaluator_dependencies(
            dependency_handler,
            self._sensor_to_backing_mapping,
        )
        _LOGGER.debug("Updated sensor-to-backing mapping: %d mappings", len(sensor_to_backing_mapping))

    def evaluate_expression_callback(
        self, expression: str, context: dict[str, ContextValue] | None, evaluate_formula_func: Any
    ) -> ContextValue:
        """
        Expression evaluator callback for handlers that need to delegate complex expressions.

        This allows handlers like DateHandler to delegate complex expression evaluation
        back to the main evaluator while maintaining separation of concerns.

        Args:
            expression: The expression to evaluate
            context: Variable context for evaluation
            evaluate_formula_func: The main evaluate_formula function to use

        Returns:
            The evaluated result
        """
        # Create a temporary FormulaConfig for the expression
        temp_config = FormulaConfig(id=f"temp_expression_{hash(expression)}", name="Temporary Expression", formula=expression)

        # Evaluate the expression using the main evaluation pipeline
        result = evaluate_formula_func(temp_config, context)

        result_dict = cast(dict[str, Any], result)
        if result_dict[RESULT_KEY_SUCCESS]:
            return cast(StateType, result_dict[RESULT_KEY_VALUE])
        raise ValueError(f"Failed to evaluate expression '{expression}': {result.get('error', 'Unknown error')}")


class EvaluatorSensorRegistry:
    """Manages cross-sensor reference registry operations."""

    def __init__(self, sensor_registry: Any, sensor_registry_phase: Any) -> None:
        """Initialize sensor registry utilities.

        Args:
            sensor_registry: The sensor registry instance
            sensor_registry_phase: The sensor registry phase instance
        """
        self._sensor_registry = sensor_registry
        self._sensor_registry_phase = sensor_registry_phase

    def register_sensor(self, sensor_name: str, entity_id: str, initial_value: float | str | bool = 0.0) -> None:
        """Register a sensor in the cross-sensor reference registry."""
        self._sensor_registry.register_sensor(sensor_name, entity_id, initial_value)
        self._sensor_registry_phase.register_sensor(sensor_name, entity_id, initial_value)

    def update_sensor_value(self, sensor_name: str, value: float | str | bool) -> None:
        """Update a sensor's value in the cross-sensor reference registry."""
        self._sensor_registry.update_sensor_value(sensor_name, value)
        self._sensor_registry_phase.update_sensor_value(sensor_name, value)

    def get_sensor_value(self, sensor_name: str) -> float | str | bool | None:
        """Get a sensor's current value from the cross-sensor reference registry."""
        return cast(float | str | bool | None, self._sensor_registry.get_sensor_value(sensor_name))

    def unregister_sensor(self, sensor_name: str) -> None:
        """Unregister a sensor from the cross-sensor reference registry."""
        self._sensor_registry.unregister_sensor(sensor_name)
        self._sensor_registry_phase.unregister_sensor(sensor_name)

    def get_registered_sensors(self) -> set[str]:
        """Get all registered sensor names."""
        return cast(set[str], self._sensor_registry.get_registered_sensors())
