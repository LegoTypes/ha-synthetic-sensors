"""Service layer for Home Assistant integration of synthetic sensors.

This module provides services for managing synthetic sensor configuration
and provides integration with Home Assistant's service system.
"""

import logging
from typing import Any, TypedDict, cast

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
import voluptuous as vol
import yaml

from .config_manager import ConfigManager
from .config_models import FormulaConfig
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

VALIDATE_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("config_file"): cv.string,
        vol.Optional("config_data"): vol.Any(cv.string, dict),
        vol.Optional("check_entity_availability"): cv.boolean,
    }
)

GET_SENSOR_INFO_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): cv.entity_id,
    }
)


def _create_yaml_validation_error(message: str, path: str = "config_data") -> dict[str, Any]:
    """Create a standardized YAML validation error structure.

    Args:
        message: Error message
        path: Path where error occurred

    Returns:
        Validation error dictionary
    """
    return {
        "valid": False,
        "errors": [
            {
                "message": message,
                "path": path,
                "severity": "error",
                "schema_path": "",
                "suggested_fix": "Check YAML syntax and formatting",
            }
        ],
        "warnings": [],
        "schema_version": "unknown",
    }


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
            schema=VALIDATE_CONFIG_SCHEMA,
        )

        self._hass.services.async_register(
            self._domain,
            "get_sensor_info",
            self._async_get_sensor_info,
            schema=GET_SENSOR_INFO_SCHEMA,
        )

        _LOGGER.debug("Registered %s services", self._domain)

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

        _LOGGER.debug("Unloaded %s services", self._domain)

    async def _async_reload_config(self, call: ServiceCall) -> None:
        """Handle reload config service call."""
        try:
            # Reload configuration
            config = await self._config_manager.async_reload_config()
            if not config:
                _LOGGER.error("Failed to reload configuration")
                return

            # Update name resolver with new variables
            self._name_resolver.clear_mappings()
            variables_dict = self._config_manager.get_variables()
            for name, entity_id in variables_dict.items():
                self._name_resolver.add_entity_mapping(name, entity_id)

            # Update sensors
            await self._sensor_manager.async_update_sensors(self._config_manager.get_sensors())

            # Clear evaluator cache
            self._evaluator.clear_cache()

            _LOGGER.debug("Successfully reloaded synthetic sensors configuration")

        except Exception as e:
            _LOGGER.error("Failed to reload configuration: %s", e)

    async def _async_update_sensor(self, call: ServiceCall) -> None:
        """Handle update sensor service call."""
        try:
            entity_id = call.data["entity_id"]

            # Find the sensor by entity_id and update it
            # Note: This service updates the underlying configuration, not just state
            # For runtime updates, services would typically call sensor methods directly

            _LOGGER.debug("Update sensor service called for entity_id: %s", entity_id)

            # Get the sensor entity directly from HA registry if needed
            # or use the sensor manager to find and update the sensor

            # This is a placeholder - the actual implementation would depend on
            # whether we're updating config or just triggering a sensor update

            # For now, log the request
            for key, value in call.data.items():
                if key != "entity_id":
                    _LOGGER.debug("  %s: %s", key, value)

            # Find the sensor by entity_id and trigger an update
            sensor = self._sensor_manager.get_sensor_by_entity_id(entity_id)
            if sensor:
                # Force a sensor update/re-evaluation
                await sensor.async_update_sensor()
                _LOGGER.debug("Triggered update for sensor: %s", entity_id)

                # Log any additional parameters that were requested
                for key, value in call.data.items():
                    if key != "entity_id":
                        _LOGGER.debug(
                            "  Parameter %s: %s (logging only - formula updates require config changes)",
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
            if self._config_manager.add_variable(variable_config["name"], variable_config["entity_id"]):
                # Save configuration
                await self._config_manager.async_save_config()

                # Add to name resolver
                self._name_resolver.add_entity_mapping(variable_config["name"], variable_config["entity_id"])

                # Clear evaluator cache
                self._evaluator.clear_cache()

                _LOGGER.debug(
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
                await self._config_manager.async_save_config()

                # Remove from name resolver
                self._name_resolver.remove_entity_mapping(name)

                # Clear evaluator cache
                self._evaluator.clear_cache()

                _LOGGER.debug("Successfully removed variable: %s", name)
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

            # Create a temporary formula config for evaluation
            config = FormulaConfig(id="temp_eval", name="temp_eval", formula=formula, dependencies=set())

            # Evaluate formula
            eval_result = self._evaluator.evaluate_formula(config, context)
            result = eval_result["value"] if eval_result["success"] else 0.0

            # Get dependencies (variables and dependencies are the same in this context)
            dependencies = self._evaluator.get_formula_dependencies(formula)
            variables = dependencies  # In this context, they're the same

            _LOGGER.debug("Formula evaluation result: %s = %s", formula, result)
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
            config_file = call.data.get("config_file")
            config_data = call.data.get("config_data")
            check_entity_availability = call.data.get("check_entity_availability", False)

            validation_result = {}

            if config_file:
                validation_result = self._validate_config_file(config_file)
            elif config_data:
                validation_result = self._validate_config_data(config_data)
            else:
                validation_result = self._validate_current_config()

            # Additional entity availability check if requested
            self._add_entity_availability_check(validation_result, check_entity_availability)

            # Log and store validation results
            self._process_validation_results(validation_result)

        except Exception as e:
            _LOGGER.error("Failed to validate configuration: %s", e)
            self._fire_validation_error_event(str(e))

    def _validate_config_file(self, config_file: str) -> dict[str, Any]:
        """Validate a config file."""
        file_result = self._config_manager.validate_config_file(config_file)
        return file_result

    def _validate_config_data(self, config_data: str | dict[str, Any]) -> dict[str, Any]:
        """Validate raw config data."""
        yaml_data = None
        validation_result = {}

        if isinstance(config_data, str):
            try:
                yaml_data = yaml.safe_load(config_data)
            except yaml.YAMLError as exc:
                return _create_yaml_validation_error(f"YAML parsing error: {exc}")
        else:
            yaml_data = config_data

        if yaml_data is not None:
            schema_result = self._config_manager.validate_yaml_data(yaml_data)
            validation_result.update(schema_result)

        return validation_result

    def _validate_current_config(self) -> dict[str, Any]:
        """Validate current configuration."""
        current_issues = self._config_manager.validate_configuration()
        return {
            "valid": len(current_issues["errors"]) == 0,
            "errors": [
                {
                    "message": error,
                    "path": "current_config",
                    "severity": "error",
                    "schema_path": "",
                    "suggested_fix": "",
                }
                for error in current_issues["errors"]
            ],
            "warnings": [
                {
                    "message": warning,
                    "path": "current_config",
                    "severity": "warning",
                    "schema_path": "",
                    "suggested_fix": "",
                }
                for warning in current_issues["warnings"]
            ],
            "schema_version": "current",
        }

    def _add_entity_availability_check(self, validation_result: dict[str, Any], check_entity_availability: bool) -> None:
        """Add entity availability check warning if requested."""
        if check_entity_availability and validation_result.get("valid", False):
            validation_result.setdefault("warnings", []).append(
                {
                    "message": "Entity availability checking not yet implemented",
                    "path": "check_entity_availability",
                    "severity": "warning",
                    "schema_path": "",
                    "suggested_fix": "This feature will be implemented in future",
                }
            )

    def _process_validation_results(self, validation_result: dict[str, Any]) -> None:
        """Log validation results and store them."""
        # Log validation results
        if validation_result["errors"]:
            _LOGGER.error(
                "Configuration validation errors: %s",
                [error["message"] for error in validation_result["errors"]],
            )
        else:
            _LOGGER.debug("Configuration validation passed")

        if validation_result["warnings"]:
            _LOGGER.warning(
                "Configuration validation warnings: %s",
                [warning["message"] for warning in validation_result["warnings"]],
            )

        # Store validation results
        if "synthetic_sensors_validation" not in self._hass.data:
            self._hass.data["synthetic_sensors_validation"] = {}

        self._hass.data["synthetic_sensors_validation"]["last_result"] = validation_result

        # Fire event with validation results
        self._hass.bus.async_fire(
            "synthetic_sensors_config_validated",
            {
                "valid": validation_result["valid"],
                "error_count": len(validation_result["errors"]),
                "warning_count": len(validation_result["warnings"]),
                "schema_version": validation_result.get("schema_version", "unknown"),
            },
        )

    def _fire_validation_error_event(self, error_message: str) -> None:
        """Fire error event for validation failure."""
        self._hass.bus.async_fire(
            "synthetic_sensors_config_validated",
            {
                "valid": False,
                "error_count": 1,
                "warning_count": 0,
                "schema_version": "unknown",
                "validation_error": error_message,
            },
        )

    async def _async_get_sensor_info(self, call: ServiceCall) -> None:
        """Handle get sensor info service call."""
        try:
            entity_id = call.data.get("entity_id")

            if entity_id:
                # Get specific sensor info by entity_id
                sensor = self._sensor_manager.get_sensor_by_entity_id(entity_id)
                if sensor:
                    formula_obj = getattr(
                        sensor,
                        "_formula_config",
                        getattr(sensor, "_main_formula", None),
                    )
                    formula_str = formula_obj.formula if formula_obj else None
                    dependencies = list(getattr(sensor, "_dependencies", []))

                    info = {
                        "entity_id": entity_id,
                        "unique_id": sensor.unique_id,
                        "name": sensor.name,
                        "state": sensor.native_value,
                        "available": sensor.available,
                        "unit_of_measurement": sensor.native_unit_of_measurement,
                        "device_class": sensor.device_class,
                        "attributes": sensor.extra_state_attributes,
                        "formula": formula_str,
                        "dependencies": dependencies,
                    }
                    _LOGGER.debug("Retrieved sensor info for entity_id: %s", entity_id)
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
                    formula_obj = getattr(
                        sensor,
                        "_formula_config",
                        getattr(sensor, "_main_formula", None),
                    )
                    formula_str = formula_obj.formula if formula_obj else None
                    dependencies = list(getattr(sensor, "_dependencies", []))

                    sensor_info = {
                        "entity_id": sensor.entity_id,
                        "unique_id": sensor.unique_id,
                        "name": sensor.name,
                        "state": sensor.native_value,
                        "available": sensor.available,
                        "formula": formula_str,
                        "dependencies": dependencies,
                    }
                    info["sensors"].append(sensor_info)

                info["total_sensors"] = len(all_sensors)

            # Store info for retrieval
            if "synthetic_sensors_info" not in self._hass.data:
                self._hass.data["synthetic_sensors_info"] = {}

            self._hass.data["synthetic_sensors_info"]["last_result"] = info

            _LOGGER.debug("Retrieved sensor info for: %s", entity_id or "all sensors")

        except Exception as e:
            _LOGGER.error("Failed to get sensor info: %s", e)

    def get_last_evaluation_result(self) -> EvaluationResponseData | None:
        """Get the last formula evaluation result.

        Returns:
            Evaluation result data or None if no evaluation performed
        """
        result = self._hass.data.get("synthetic_sensors_eval", {}).get("last_result")
        return cast(EvaluationResponseData, result) if isinstance(result, dict) else None

    def get_last_validation_result(self) -> ValidationResponseData | None:
        """Get the last configuration validation result.

        Returns:
            Validation result data or None if no validation performed
        """
        result = self._hass.data.get("synthetic_sensors_validation", {}).get("last_result")
        return cast(ValidationResponseData, result) if isinstance(result, dict) else None

    def get_last_sensor_info(self) -> SensorInfoData | AllSensorsInfoData | None:
        """Get the last sensor info result.

        Returns:
            Sensor info data or None if no info retrieved
        """
        result = self._hass.data.get("synthetic_sensors_info", {}).get("last_result")
        return cast(SensorInfoData | AllSensorsInfoData, result) if isinstance(result, dict) else None

    async def async_auto_reload_if_needed(self) -> None:
        """Automatically reload configuration if file has been modified."""
        if self._config_manager.is_config_modified():
            _LOGGER.debug("Configuration file modified, automatically reloading")
            # Create a dummy ServiceCall for internal reload
            dummy_call = ServiceCall(self._hass, self._domain, "reload_config", {})
            await self._async_reload_config(dummy_call)

    async def async_unregister_services(self) -> None:
        """Unregister all services from Home Assistant."""
        _LOGGER.debug("Unregistering synthetic sensor services")

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
