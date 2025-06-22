"""
Integration Module - Main entry point for Home Assistant integrations.

This module provides the integration layer that connects the synthetic sensor
infrastructure with Home Assistant integrations, enabling YAML-based synthetic
sensor configuration.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .config_manager import ConfigManager
from .evaluator import Evaluator
from .exceptions import IntegrationNotInitializedError, IntegrationSetupError
from .name_resolver import NameResolver
from .sensor_manager import SensorManager, SensorManagerConfig
from .service_layer import ServiceLayer

_LOGGER = logging.getLogger(__name__)


# TypedDicts for integration layer
class IntegrationSetupResult(TypedDict):
    """Result of integration setup operation."""

    success: bool
    error_message: NotRequired[str]
    integration_id: str
    sensors_created: int


class IntegrationStatus(TypedDict):
    """Current status of an integration instance."""

    initialized: bool
    has_config_file: bool
    config_file_path: str | None
    sensors_count: int
    services_registered: bool
    last_error: str | None


class ConfigValidationResult(TypedDict):
    """Result of configuration validation."""

    is_valid: bool
    errors: list[str]
    warnings: list[str]
    sensors_count: int
    formulas_count: int


class AutoConfigDiscovery(TypedDict):
    """Auto-configuration discovery result."""

    found: bool
    file_path: str | None
    load_success: bool
    error_message: NotRequired[str]


class IntegrationCleanupResult(TypedDict):
    """Result of integration cleanup operation."""

    success: bool
    services_unregistered: bool
    sensors_removed: bool
    errors: list[str]


class SyntheticSensorsIntegration:
    """Main integration class for synthetic sensors."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry[Any]):
        """Initialize the synthetic sensors integration."""
        self._hass = hass
        self._config_entry = config_entry

        # Initialize core components
        self._name_resolver = NameResolver(hass, variables={})
        self._config_manager = ConfigManager(hass)
        self._sensor_manager: SensorManager | None = None
        self._service_manager: ServiceLayer | None = None

        # State
        self._initialized = False
        self._auto_config_path: Path | None = None

    async def async_setup(self, add_entities_callback: AddEntitiesCallback) -> bool:
        """Set up the synthetic sensors integration."""
        try:
            _LOGGER.info("Setting up synthetic sensor integration")

            # Initialize sensor manager
            self._sensor_manager = SensorManager(self._hass, self._name_resolver, add_entities_callback)

            # Initialize enhanced evaluator
            evaluator = Evaluator(self._hass)

            # Initialize service manager
            self._service_manager = ServiceLayer(
                self._hass,
                self._config_manager,
                self._sensor_manager,
                self._name_resolver,
                evaluator,
            )

            # Register services
            await self._service_manager.async_setup_services()

            # Look for auto-configuration file
            await self._check_auto_configuration()

            self._initialized = True
            _LOGGER.info("Synthetic sensors integration setup completed successfully")
            return True

        except Exception as err:
            _LOGGER.error(f"Failed to setup synthetic sensors integration: {err}")
            await self._cleanup()
            raise IntegrationSetupError(str(err)) from err

    async def async_unload(self) -> bool:
        """Unload the synthetic sensors integration."""
        _LOGGER.info("Unloading synthetic sensors integration")
        return await self._cleanup()

    async def async_reload(self, add_entities_callback: AddEntitiesCallback) -> bool:
        """Reload the synthetic sensors integration."""
        _LOGGER.info("Reloading synthetic sensors integration")

        # Cleanup existing setup
        await self._cleanup()

        # Re-setup
        return await self.async_setup(add_entities_callback)

    @property
    def is_initialized(self) -> bool:
        """Check if the integration is properly initialized."""
        return self._initialized

    @property
    def config_manager(self) -> ConfigManager:
        """Get the configuration manager."""
        return self._config_manager

    @property
    def sensor_manager(self) -> SensorManager | None:
        """Get the sensor manager."""
        return self._sensor_manager

    @property
    def service_manager(self) -> ServiceLayer | None:
        """Get the service manager."""
        return self._service_manager

    def get_integration_status(self) -> IntegrationStatus:
        """Get the current status of the integration."""
        sensors_count = 0
        if self._sensor_manager:
            try:
                sensors_count = len(self._sensor_manager.get_all_sensor_entities())
            except Exception:
                sensors_count = 0

        return {
            "initialized": self._initialized,
            "has_config_file": self._auto_config_path is not None,
            "config_file_path": (str(self._auto_config_path) if self._auto_config_path else None),
            "sensors_count": sensors_count,
            "services_registered": self._service_manager is not None,
            "last_error": None,  # Could be enhanced to track last error
        }

    async def load_configuration_file(self, config_path: str) -> bool:
        """Load a configuration file and create sensors."""
        if not self._initialized:
            raise IntegrationNotInitializedError()

        if not self._sensor_manager:
            raise IntegrationNotInitializedError("sensor_manager")

        try:
            # Load and validate configuration
            config = self._config_manager.load_from_file(config_path)

            # Load sensors
            await self._sensor_manager.load_configuration(config)

            _LOGGER.info(f"Successfully loaded synthetic sensors configuration from " f"{config_path}")
            return True

        except Exception as err:
            _LOGGER.error(f"Failed to load synthetic sensors configuration from " f"{config_path}: {err}")
            return False

    async def load_configuration_content(self, yaml_content: str) -> bool:
        """Load configuration from YAML content and create sensors."""
        if not self._initialized:
            raise RuntimeError("Synthetic sensors integration not initialized")

        if not self._sensor_manager:
            raise RuntimeError("Sensor manager not initialized")

        try:
            # Load and validate configuration
            config = self._config_manager.load_from_yaml(yaml_content)

            # Load sensors
            await self._sensor_manager.load_configuration(config)

            _LOGGER.info("Successfully loaded synthetic sensors configuration from " "provided content")
            return True

        except Exception as err:
            _LOGGER.error(f"Failed to load synthetic sensors configuration from content: {err}")
            return False

    async def _check_auto_configuration(self) -> None:
        """Check for auto-configuration file and load if present."""
        # Define potential auto-config file locations
        config_dir = Path(self._hass.config.config_dir)
        potential_paths = [
            config_dir / "synthetic_sensors_config.yaml",
            config_dir / "synthetic_sensors.yaml",
            config_dir / "syn2_config.yaml",
            config_dir / "syn2.yaml",
        ]

        for path in potential_paths:
            if path.exists() and path.is_file():
                _LOGGER.info(f"Found auto-configuration file: {path}")
                self._auto_config_path = path

                try:
                    await self.load_configuration_file(str(path))
                    _LOGGER.info(f"Successfully loaded auto-configuration from {path}")
                    break
                except Exception as err:
                    _LOGGER.warning(f"Failed to load auto-configuration from {path}: {err}")
                    continue
        else:
            _LOGGER.debug("No auto-configuration file found")

    async def _cleanup(self) -> bool:
        """Clean up all synthetic sensor resources."""
        result = await self.async_cleanup_detailed()
        return result["success"]

    async def async_cleanup_detailed(self) -> IntegrationCleanupResult:
        """Clean up all synthetic sensor resources with detailed results."""
        errors = []
        services_unregistered = False
        sensors_removed = False

        try:
            # Unregister services
            if self._service_manager:
                await self._service_manager.async_unregister_services()
                self._service_manager = None
                services_unregistered = True

        except Exception as err:
            errors.append(f"Failed to unregister services: {err}")

        try:
            # Clean up sensor manager
            if self._sensor_manager:
                await self._sensor_manager._remove_all_sensors()
                self._sensor_manager = None
                sensors_removed = True

        except Exception as err:
            errors.append(f"Failed to remove sensors: {err}")

        try:
            # Reset state
            self._initialized = False

            if not errors:
                _LOGGER.info("Synthetic sensors integration cleanup completed")

        except Exception as err:
            errors.append(f"Failed to reset state: {err}")

        if errors:
            _LOGGER.error(f"Errors during synthetic sensors cleanup: {errors}")

        return {
            "success": len(errors) == 0,
            "services_unregistered": services_unregistered,
            "sensors_removed": sensors_removed,
            "errors": errors,
        }

    async def create_managed_sensor_manager(
        self,
        add_entities_callback: AddEntitiesCallback,
        device_info: DeviceInfo | None = None,
        lifecycle_managed_externally: bool = True,
        # Additional HA dependencies that parent can provide
        hass_override: HomeAssistant | None = None,
        config_manager_override: ConfigManager | None = None,
        evaluator_override: Evaluator | None = None,
        name_resolver_override: NameResolver | None = None,
    ) -> SensorManager:
        """Create a SensorManager for external integration use.

        This method allows custom integrations to create their own SensorManager
        with their device info and HA dependencies.

        Args:
            add_entities_callback: Callback to add entities to HA
            device_info: Device info for the parent integration
            lifecycle_managed_externally: Whether lifecycle is managed by parent integration
            hass_override: Custom HomeAssistant instance (optional)
            config_manager_override: Custom ConfigManager instance (optional)
            evaluator_override: Custom Evaluator instance (optional)
            name_resolver_override: Custom NameResolver instance (optional)

        Returns:
            SensorManager: Configured sensor manager for external use
        """
        if not self._initialized:
            raise RuntimeError("Synthetic sensors integration not initialized")

        # Use parent-provided HA instance or default
        effective_hass = hass_override or self._hass

        # Create manager config for external integration
        manager_config = SensorManagerConfig(
            device_info=device_info,
            lifecycle_managed_externally=lifecycle_managed_externally,
            hass_instance=effective_hass,
            config_manager=config_manager_override,
            evaluator=evaluator_override,
            name_resolver=name_resolver_override,
        )

        # Create default name resolver if not provided
        default_name_resolver = name_resolver_override or NameResolver(effective_hass, {})

        # Create and return sensor manager
        sensor_manager = SensorManager(
            effective_hass,
            default_name_resolver,
            add_entities_callback,
            manager_config,
        )

        _LOGGER.info("Created managed sensor manager for external integration")
        return sensor_manager


# Global instance management for integration with existing components
_integrations: dict[str, SyntheticSensorsIntegration] = {}


async def async_setup_integration(
    hass: HomeAssistant,
    config_entry: ConfigEntry[Any],
    add_entities_callback: AddEntitiesCallback,
) -> bool:
    """Set up synthetic sensors integration for a config entry."""
    entry_id = config_entry.entry_id

    if entry_id in _integrations:
        _LOGGER.warning(f"Synthetic sensors integration already exists for entry {entry_id}")
        return True

    integration = SyntheticSensorsIntegration(hass, config_entry)
    success = await integration.async_setup(add_entities_callback)

    if success:
        _integrations[entry_id] = integration

    return success


async def async_unload_integration(config_entry: ConfigEntry[Any]) -> bool:
    """Unload synthetic sensors integration for a config entry."""
    entry_id = config_entry.entry_id

    if entry_id not in _integrations:
        return True

    integration = _integrations[entry_id]
    success = await integration.async_unload()

    if success:
        del _integrations[entry_id]

    return success


async def async_reload_integration(hass: HomeAssistant, config_entry: ConfigEntry[Any], add_entities_callback: AddEntitiesCallback) -> bool:
    """Reload synthetic sensors integration for a config entry."""
    entry_id = config_entry.entry_id

    if entry_id not in _integrations:
        return await async_setup_integration(hass, config_entry, add_entities_callback)

    integration = _integrations[entry_id]
    return await integration.async_reload(add_entities_callback)


def get_integration(config_entry: ConfigEntry[Any]) -> SyntheticSensorsIntegration | None:
    """Get the synthetic sensors integration instance for a config entry."""
    return _integrations.get(config_entry.entry_id)


# Configuration validation helpers
def validate_yaml_content(yaml_content: str) -> ConfigValidationResult:
    """Validate synthetic sensors YAML content without loading it into HA."""
    try:
        # Create a temporary manager for validation
        # Note: This is for validation only, not for actual use
        temp_hass: Any = type("TempHass", (), {"config": type("Config", (), {"config_dir": "."})()})()
        manager = ConfigManager(temp_hass)

        config = manager.load_from_yaml(yaml_content)
        errors = manager.validate_config(config)

        # Count sensors and formulas
        sensors_count = len(config.sensors) if config else 0
        formulas_count = sum(len(sensor.formulas) for sensor in config.sensors) if config else 0

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": [],  # Could be enhanced with warnings
            "sensors_count": sensors_count,
            "formulas_count": formulas_count,
        }

    except Exception as err:
        return {
            "is_valid": False,
            "errors": [str(err)],
            "warnings": [],
            "sensors_count": 0,
            "formulas_count": 0,
        }


def get_example_config() -> str:
    """Get an example synthetic sensors configuration for documentation/testing."""
    return """
version: "1.0"

sensors:
  - name: "cost_analysis"
    friendly_name: "Energy Cost Analysis"
    description: "Real-time energy cost calculations"
    category: "energy"
    formulas:
      - name: "current_cost_rate"
        formula: >-
          entity('sensor.electricity_rate') *
          entity('sensor.span_panel_instantaneous_power') / 1000
        unit_of_measurement: "$/h"
        device_class: "monetary"
        icon: "mdi:currency-usd"

      - name: "daily_projected_cost"
        formula: "entity('sensor.cost_analysis_current_cost_rate') * 24"
        unit_of_measurement: "$"
        device_class: "monetary"

  - name: "solar_analytics"
    friendly_name: "Solar Analytics"
    description: "Advanced solar energy analysis"
    category: "solar"
    formulas:
      - name: "efficiency_ratio"
        formula: >-
          entity('sensor.solar_production') /
          max(entity('sensor.solar_irradiance'), 1) * 100
        unit_of_measurement: "%"
        device_class: "energy"

      - name: "net_energy_flow"
        formula: >-
          entity('sensor.solar_production') -
          entity('sensor.span_panel_instantaneous_power')
        unit_of_measurement: "W"
        device_class: "power"
        state_class: "measurement"

global_settings:
  default_update_interval: 30
  cache_ttl: 60
"""
