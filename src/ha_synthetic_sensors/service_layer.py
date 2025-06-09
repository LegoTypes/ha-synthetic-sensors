"""Service layer for Home Assistant integration of synthetic sensors.

This module provides services for managing synthetic sensor configuration
and provides integration with Home Assistant's service system.
"""

import logging
from typing import TypedDict

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .config_manager import ConfigManager
from .evaluator import Evaluator
from .name_resolver import NameResolver
from .sensor_manager import SensorManager

_LOGGER = logging.getLogger(__name__)


# TypedDicts for service call data
class UpdateSensorData(TypedDict, total=False):
    entity_id: str
    formula: str
    unit_of_measurement: str
    device_class: str
    state_class: str
    icon: str
    enabled: bool
    attributes: dict[str, str | float | int | bool]
    availability_formula: str
    update_interval: int
    round_digits: int


class AddVariableData(TypedDict, total=False):
    name: str
    entity_id: str
    description: str


class RemoveVariableData(TypedDict):
    name: str


class EvaluateFormulaData(TypedDict, total=False):
    formula: str
    context: dict[str, str | float | int | bool]


class GetSensorInfoData(TypedDict, total=False):
    entity_id: str


# TypedDicts for service responses
class ServiceResponseData(TypedDict, total=False):
    success: bool
    message: str
    data: dict[str, str | float | int | bool]
    errors: list[str]


class EvaluationResponseData(TypedDict):
    formula: str
    result: float | int | str | bool | None
    variables: list[str]
    dependencies: list[str]
    context: dict[str, str | float | int | bool]


class ValidationResponseData(TypedDict):
    errors: list[str]
    warnings: list[str]


class SensorInfoData(TypedDict, total=False):
    entity_id: str
    unique_id: str
    name: str | None
    state: float | int | str | bool | None
    available: bool
    unit_of_measurement: str | None
    device_class: str | None
    attributes: dict[str, str | float | int | bool | None] | None
    formula: str
    dependencies: list[str]
    error: str


class AllSensorsInfoData(TypedDict):
    sensors: list[SensorInfoData]
    total_sensors: int


# Service schemas
RELOAD_CONFIG_SCHEMA = vol.Schema({})

UPDATE_SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("formula"): cv.string,
        vol.Optional("unit_of_measurement"): cv.string,
        vol.Optional("device_class"): cv.string,
        vol.Optional("state_class"): cv.string,
        vol.Optional("icon"): cv.string,
        vol.Optional("enabled"): cv.boolean,
        vol.Optional("attributes"): dict,
        vol.Optional("availability_formula"): cv.string,
        vol.Optional("update_interval"): cv.positive_int,
        vol.Optional("round_digits"): cv.positive_int,
    }
)

ADD_VARIABLE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("description"): cv.string,
    }
)

REMOVE_VARIABLE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
    }
)

EVALUATE_FORMULA_SCHEMA = vol.Schema(
    {
        vol.Required("formula"): cv.string,
        vol.Optional("context"): dict,
    }
)


class ServiceLayer:
    """Service layer for synthetic sensors integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_manager: "ConfigManager",
        sensor_manager: "SensorManager",
        name_resolver: "NameResolver",
        evaluator: "Evaluator",
        domain: str = "synthetic_sensors",
    ) -> None:
        """Initialize the service layer.

        Args:
            hass: Home Assistant instance
            config_manager: Configuration manager
            sensor_manager: Sensor manager
            name_resolver: Name resolver
            evaluator: Enhanced evaluator
            domain: Service domain name
        """
        self._hass = hass
        self._config_manager = config_manager
        self._sensor_manager = sensor_manager
        self._name_resolver = name_resolver
        self._evaluator = evaluator
        self._domain = domain

    async def async_setup_services(self) -> None:
        """Set up Home Assistant services."""
        # Register services
        self._hass.services.async_register(
            self._domain,
            "reload_config",
            self._async_reload_config,
            schema=RELOAD_CONFIG_SCHEMA,
        )

        self._hass.services.async_register(
            self._domain,
            "update_sensor",
            self._async_update_sensor,
            schema=UPDATE_SENSOR_SCHEMA,
        )

        self._hass.services.async_register(
            self._domain,
            "add_variable",
            self._async_add_variable,
            schema=ADD_VARIABLE_SCHEMA,
        )

        self._hass.services.async_register(
            self._domain,
            "remove_variable",
            self._async_remove_variable,
            schema=REMOVE_VARIABLE_SCHEMA,
        )

        self._hass.services.async_register(
            self._domain,
            "evaluate_formula",
            self._async_evaluate_formula,
            schema=EVALUATE_FORMULA_SCHEMA,
        )

        self._hass.services.async_register(
            self._domain,
            "validate_config",
            self._async_validate_config,
            schema=RELOAD_CONFIG_SCHEMA,
        )

        self._hass.services.async_register(
            self._domain,
            "get_sensor_info",
            self._async_get_sensor_info,
            schema=vol.Schema(
                {
                    vol.Optional("entity_id"): cv.entity_id,
                }
            ),
        )

        _LOGGER.info("Registered %s services", self._domain)

    async def async_unload_services(self) -> None:
        """Unload Home Assistant services."""
        services = [
            "reload_config",
            "update_sensor",
            "add_variable",
            "remove_variable",
            "evaluate_formula",
            "validate_config",
            "get_sensor_info",
        ]

        for service in services:
            if self._hass.services.has_service(self._domain, service):
                self._hass.services.async_remove(self._domain, service)

        _LOGGER.info("Unloaded %s services", self._domain)

    async def _async_reload_config(self, call: ServiceCall) -> None:
        """Handle reload config service call."""
        try:
            # Reload configuration
            if not self._config_manager.load_config():
                _LOGGER.error("Failed to reload configuration")
                return

            # Update name resolver with new variables
            self._name_resolver.clear_mappings()
            variables_dict = self._config_manager.get_variables()
            for name, entity_id in variables_dict.items():
                self._name_resolver.add_entity_mapping(name, entity_id)

            # Update sensors
            await self._sensor_manager.async_update_sensors(
                self._config_manager.get_sensors()
            )

            # Clear evaluator cache
            self._evaluator.clear_cache()

            _LOGGER.info("Successfully reloaded synthetic sensors configuration")

        except Exception as e:
            _LOGGER.error("Failed to reload configuration: %s", e)

    async def _async_update_sensor(self, call: ServiceCall) -> None:
        """Handle update sensor service call."""
        try:
            entity_id = call.data["entity_id"]

            # Find the sensor by entity_id and update it
            # Note: This service updates the underlying configuration, not just state
            # For runtime updates, services would typically call sensor methods directly

            _LOGGER.info("Update sensor service called for entity_id: %s", entity_id)

            # Get the sensor entity directly from HA registry if needed
            # or use the sensor manager to find and update the sensor

            # This is a placeholder - the actual implementation would depend on
            # whether we're updating config or just triggering a sensor update

            # For now, log the request
            for key, value in call.data.items():
                if key != "entity_id":
                    _LOGGER.info("  %s: %s", key, value)

            # Find the sensor by entity_id and trigger an update
            sensor = self._sensor_manager.get_sensor_by_entity_id(entity_id)
            if sensor:
                # Force a sensor update/re-evaluation
                await sensor._async_update_sensor()
                _LOGGER.info("Triggered update for sensor: %s", entity_id)

                # Log any additional parameters that were requested
                for key, value in call.data.items():
                    if key != "entity_id":
                        _LOGGER.info(
                            "  Parameter %s: %s (logging only - formula updates "
                            "require config changes)",
                            key,
                            value,
                        )
            else:
                _LOGGER.error("Sensor not found for entity_id: %s", entity_id)

        except Exception as e:
            _LOGGER.error("Failed to update sensor: %s", e)

    async def _async_add_variable(self, call: ServiceCall) -> None:
        """Handle add variable service call."""
        try:
            variable_config = dict(call.data)

            # Add to configuration
            if self._config_manager.add_variable(
                variable_config["name"], variable_config["entity_id"]
            ):
                # Save configuration
                self._config_manager.save_config()

                # Add to name resolver
                self._name_resolver.add_entity_mapping(
                    variable_config["name"], variable_config["entity_id"]
                )

                # Clear evaluator cache
                self._evaluator.clear_cache()

                _LOGGER.info(
                    "Successfully added variable: %s -> %s",
                    variable_config["name"],
                    variable_config["entity_id"],
                )
            else:
                _LOGGER.error("Failed to add variable: %s", variable_config["name"])

        except Exception as e:
            _LOGGER.error("Failed to add variable: %s", e)

    async def _async_remove_variable(self, call: ServiceCall) -> None:
        """Handle remove variable service call."""
        try:
            name = call.data["name"]

            # Remove from configuration
            if self._config_manager.remove_variable(name):
                # Save configuration
                self._config_manager.save_config()

                # Remove from name resolver
                self._name_resolver.remove_entity_mapping(name)

                # Clear evaluator cache
                self._evaluator.clear_cache()

                _LOGGER.info("Successfully removed variable: %s", name)
            else:
                _LOGGER.error("Failed to remove variable: %s", name)

        except Exception as e:
            _LOGGER.error("Failed to remove variable: %s", e)

    async def _async_evaluate_formula(self, call: ServiceCall) -> None:
        """Handle evaluate formula service call."""
        formula = None
        try:
            formula = call.data["formula"]
            context = call.data.get("context", {})

            # Evaluate formula
            result = self._evaluator.evaluate(formula, context)

            # Get variables and dependencies
            variables = self._evaluator.extract_variables(formula)
            dependencies = self._evaluator.get_dependencies(formula)

            _LOGGER.info("Formula evaluation result: %s = %s", formula, result)
            _LOGGER.debug("Variables: %s, Dependencies: %s", variables, dependencies)

            # Store result in hass data for potential retrieval
            if "synthetic_sensors_eval" not in self._hass.data:
                self._hass.data["synthetic_sensors_eval"] = {}

            self._hass.data["synthetic_sensors_eval"]["last_result"] = {
                "formula": formula,
                "result": result,
                "variables": list(variables),
                "dependencies": list(dependencies),
                "context": context,
            }

        except Exception as e:
            formula_str = formula or "unknown"
            _LOGGER.error("Failed to evaluate formula '%s': %s", formula_str, e)

    async def _async_validate_config(self, call: ServiceCall) -> None:
        """Handle validate config service call."""
        try:
            # Validate current configuration
            issues = self._config_manager.validate_configuration()

            if issues["errors"]:
                _LOGGER.error("Configuration validation errors: %s", issues["errors"])
            else:
                _LOGGER.info("Configuration validation passed")

            if issues["warnings"]:
                _LOGGER.warning(
                    "Configuration validation warnings: %s", issues["warnings"]
                )

            # Store validation results
            if "synthetic_sensors_validation" not in self._hass.data:
                self._hass.data["synthetic_sensors_validation"] = {}

            self._hass.data["synthetic_sensors_validation"]["last_result"] = issues

        except Exception as e:
            _LOGGER.error("Failed to validate configuration: %s", e)

    async def _async_get_sensor_info(self, call: ServiceCall) -> None:
        """Handle get sensor info service call."""
        try:
            entity_id = call.data.get("entity_id")

            if entity_id:
                # Get specific sensor info by entity_id
                sensor = self._sensor_manager.get_sensor_by_entity_id(entity_id)
                if sensor:
                    info = {
                        "entity_id": entity_id,
                        "unique_id": sensor._attr_unique_id,
                        "name": sensor._attr_name,
                        "state": sensor._attr_native_value,
                        "available": sensor._attr_available,
                        "unit_of_measurement": sensor._attr_native_unit_of_measurement,
                        "device_class": sensor._attr_device_class,
                        "attributes": sensor._attr_extra_state_attributes,
                        "formula": sensor._formula_config.formula,
                        "dependencies": list(sensor._dependencies),
                    }
                    _LOGGER.info("Retrieved sensor info for entity_id: %s", entity_id)
                else:
                    info = {"error": f"Sensor not found: {entity_id}"}
                    _LOGGER.warning("Sensor not found for entity_id: %s", entity_id)
            else:
                # Get all sensors info
                info = {
                    "sensors": [],
                    "total_sensors": 0,
                }

                all_sensors = self._sensor_manager.get_all_sensor_entities()
                for sensor in all_sensors:
                    sensor_info = {
                        "entity_id": sensor.entity_id,
                        "unique_id": sensor._attr_unique_id,
                        "name": sensor._attr_name,
                        "state": sensor._attr_native_value,
                        "available": sensor._attr_available,
                        "formula": sensor._formula_config.formula,
                        "dependencies": list(sensor._dependencies),
                    }
                    info["sensors"].append(sensor_info)

                info["total_sensors"] = len(all_sensors)

            # Store info for retrieval
            if "synthetic_sensors_info" not in self._hass.data:
                self._hass.data["synthetic_sensors_info"] = {}

            self._hass.data["synthetic_sensors_info"]["last_result"] = info

            _LOGGER.info("Retrieved sensor info for: %s", entity_id or "all sensors")

        except Exception as e:
            _LOGGER.error("Failed to get sensor info: %s", e)

    def get_last_evaluation_result(self) -> EvaluationResponseData | None:
        """Get the last formula evaluation result.

        Returns:
            Evaluation result data or None if no evaluation performed
        """
        return self._hass.data.get("synthetic_sensors_eval", {}).get("last_result")

    def get_last_validation_result(self) -> ValidationResponseData | None:
        """Get the last configuration validation result.

        Returns:
            Validation result data or None if no validation performed
        """
        return self._hass.data.get("synthetic_sensors_validation", {}).get(
            "last_result"
        )

    def get_last_sensor_info(self) -> SensorInfoData | AllSensorsInfoData | None:
        """Get the last sensor info result.

        Returns:
            Sensor info data or None if no info retrieved
        """
        return self._hass.data.get("synthetic_sensors_info", {}).get("last_result")

    async def async_auto_reload_if_needed(self) -> None:
        """Automatically reload configuration if file has been modified."""
        if self._config_manager.is_config_modified():
            _LOGGER.info("Configuration file modified, automatically reloading")
            await self._async_reload_config(None)

    async def async_unregister_services(self) -> None:
        """Unregister all services from Home Assistant."""
        _LOGGER.info("Unregistering synthetic sensor services")

        # Remove services
        for service_name in [
            "create_sensor",
            "remove_sensor",
            "evaluate_formula",
            "add_variable",
            "remove_variable",
            "get_sensor_info",
            "reload_config",
        ]:
            if self._hass.services.has_service(self._domain, service_name):
                self._hass.services.async_remove(self._domain, service_name)
                _LOGGER.debug("Removed service: %s.%s", self._domain, service_name)
