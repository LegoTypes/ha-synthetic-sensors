"""
Example: Custom Integration using ha-synthetic-sensors with Device Integration

This example shows how a custom Home Assistant integration can use
ha-synthetic-sensors to create synthetic sensors that appear under
the custom integration's device in the HA UI.
"""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.integration import SyntheticSensorsIntegration
from ha_synthetic_sensors.name_resolver import NameResolver
from ha_synthetic_sensors.sensor_manager import SensorManager


class MyCustomIntegration:
    """Example custom integration using synthetic sensors."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry[dict[str, Any]]):
        self.hass = hass
        self.config_entry = config_entry
        self.sensor_manager: SensorManager | None = None

        # Define device info for this integration
        self.device_info = DeviceInfo(
            identifiers={("my_custom_integration", config_entry.entry_id)},
            name="My Custom Device",
            manufacturer="Custom Manufacturer",
            model="Custom Model v1.0",
            sw_version="1.0.0",
        )

        # Create custom HA dependencies that the parent integration controls
        self.custom_config_manager = ConfigManager(hass)
        self.custom_evaluator = Evaluator(hass)
        self.custom_name_resolver = NameResolver(hass, {})

    async def async_setup(self, add_entities: AddEntitiesCallback) -> bool:
        """Set up the custom integration with synthetic sensors."""

        # Get the synthetic sensors integration instance
        synthetic_integration = SyntheticSensorsIntegration(self.hass, self.config_entry)
        await synthetic_integration.async_setup(add_entities)

        # Create a managed sensor manager with our device info AND our HA dependencies
        self.sensor_manager = await synthetic_integration.create_managed_sensor_manager(
            add_entities_callback=add_entities,
            device_info=self.device_info,
            lifecycle_managed_externally=True,
            # Pass our own HA dependencies for full control
            hass_override=self.hass,  # Use our hass instance
            config_manager_override=self.custom_config_manager,  # Use our config manager
            evaluator_override=self.custom_evaluator,  # Use our evaluator
            name_resolver_override=self.custom_name_resolver,  # Use our name resolver
        )

        # Load synthetic sensor configuration
        yaml_config = """
version: "1.0"

sensors:
  energy_efficiency:
    name: "Energy Efficiency"
    formula: "solar_production / total_consumption * 100"
    variables:
      solar_production: "sensor.solar_inverter_power"
      total_consumption: "sensor.home_total_power"
    unit_of_measurement: "%"
    device_class: "energy"
    state_class: "measurement"
  cost_savings:
    name: "Daily Cost Savings"
    formula: "energy_efficiency * daily_rate / 100"
    attributes:
      monthly_projection:
        formula: "cost_savings * 30"
        unit_of_measurement: "$"
      yearly_projection:
        formula: "cost_savings * 365"
        unit_of_measurement: "$"
    variables:
      energy_efficiency: "sensor.my_custom_energy_efficiency"
      daily_rate: "input_number.electricity_daily_rate"
    unit_of_measurement: "$"
    device_class: "monetary"
    state_class: "total"
"""

        # Parse and load the configuration using our custom config manager
        config = self.custom_config_manager.load_from_yaml(yaml_config)

        # Load sensors into our managed sensor manager
        await self.sensor_manager.load_configuration(config)

        return True

    async def async_unload(self) -> bool:
        """Unload the integration and clean up sensors."""
        if self.sensor_manager:
            # Remove all sensors managed by this integration
            await self.sensor_manager._remove_all_sensors()
            self.sensor_manager = None

        return True

    async def async_reload(self, add_entities: AddEntitiesCallback) -> bool:
        """Reload the integration configuration."""
        await self.async_unload()
        return await self.async_setup(add_entities)

    async def update_sensor_config(self, new_yaml_config: str) -> bool:
        """Update sensor configuration at runtime."""
        if not self.sensor_manager:
            return False

        try:
            # Parse new configuration using our custom config manager
            new_config = self.custom_config_manager.load_from_yaml(new_yaml_config)

            # Reload sensors with new configuration
            await self.sensor_manager.reload_configuration(new_config)

            return True
        except Exception:
            # Log error and return False
            return False

    def add_custom_variables(self, variables: dict[str, str]) -> None:
        """Add custom variables to the name resolver."""
        for var_name, entity_id in variables.items():
            self.custom_name_resolver.add_entity_mapping(var_name, entity_id)

    def configure_custom_evaluator(self, cache_ttl: int = 60) -> None:
        """Configure the custom evaluator with integration-specific settings."""
        # Example: Configure evaluator cache settings
        # In a real implementation, you'd have methods to configure the evaluator
        pass


# Example usage in a Home Assistant integration's sensor platform:


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry[dict[str, Any]],
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Set up custom integration sensors."""

    # Create and set up the custom integration
    integration = MyCustomIntegration(hass, config_entry)

    # Configure custom variables before setup
    integration.add_custom_variables(
        {
            "custom_var1": "sensor.my_special_sensor",
            "custom_var2": "input_number.my_setting",
        }
    )

    # Configure custom evaluator settings
    integration.configure_custom_evaluator(cache_ttl=120)

    success = await integration.async_setup(async_add_entities)

    # Store integration instance for later use
    hass.data.setdefault("my_custom_integration", {})[config_entry.entry_id] = integration

    return bool(success)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry[dict[str, Any]]) -> bool:
    """Unload custom integration sensors."""

    integration = hass.data["my_custom_integration"].get(config_entry.entry_id)
    if integration:
        success: bool = await integration.async_unload()
        del hass.data["my_custom_integration"][config_entry.entry_id]
        return success

    return True


# Benefits of this enhanced approach:

# 1. **Full HA Dependency Control**: Parent integration provides its own hass,
#    config_manager, evaluator, and name_resolver instances.

# 2. **Custom Configuration**: Parent can configure evaluator cache settings,
#    name resolver variables, etc. before creating sensors.

# 3. **Isolated Dependencies**: Each integration has its own set of HA dependencies,
#    preventing conflicts between different integrations using synthetic sensors.

# 4. **Lifecycle Ownership**: Parent integration fully controls the lifecycle of
#    all HA dependencies and synthetic sensors.

# 5. **Runtime Flexibility**: Parent can modify variables, evaluator settings,
#    and configuration at runtime through its own dependency instances.
