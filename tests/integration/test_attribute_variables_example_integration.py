"""Integration test for attribute_variables_example.yaml.

This test validates the attribute variables functionality using the comprehensive example
from examples/attribute_variables_example.yaml.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


class TestAttributeVariablesExample:
    """Integration tests for attribute variables example."""

    @pytest.mark.asyncio
    async def test_attribute_variables_example(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_device_registry,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test attribute variables example end-to-end."""

        # =============================================================================
        # CUSTOMIZE THIS SECTION FOR YOUR TEST
        # =============================================================================

        # 1. Set up your required entities (entities your YAML references)
        required_entities = {
            # Energy monitor sensor references
            "sensor.grid_meter_power": {"state": "1500.0", "attributes": {"unit_of_measurement": "W"}},
            "sensor.solar_inverter_power": {"state": "800.0", "attributes": {"unit_of_measurement": "W"}},
            "sensor.battery_percentage": {"state": "75.0", "attributes": {"unit_of_measurement": "%"}},
            "sensor.battery_total_capacity": {"state": "10.0", "attributes": {"unit_of_measurement": "kWh"}},
            "sensor.solar_panel_efficiency": {"state": "0.18", "attributes": {"unit_of_measurement": ""}},
            # Temperature analysis sensor references
            "sensor.living_room_temperature": {"state": "22.5", "attributes": {"unit_of_measurement": "°C"}},
            "sensor.outdoor_temperature": {"state": "15.0", "attributes": {"unit_of_measurement": "°C"}},
            "sensor.living_room_humidity": {"state": "45.0", "attributes": {"unit_of_measurement": "%"}},
            "sensor.weather_station_temperature": {"state": "14.5", "attributes": {"unit_of_measurement": "°C"}},
            "sensor.bedroom_temperature": {"state": "21.0", "attributes": {"unit_of_measurement": "°C"}},
            "sensor.bedroom_humidity": {"state": "50.0", "attributes": {"unit_of_measurement": "%"}},
            # Home automation hub sensor references
            "sensor.total_smart_devices": {"state": "25.0", "attributes": {"unit_of_measurement": "devices"}},
            "sensor.current_power_usage": {"state": "1200.0", "attributes": {"unit_of_measurement": "W"}},
            "sensor.circuit_1_power": {"state": "800.0", "attributes": {"unit_of_measurement": "W"}},
            "sensor.circuit_2_power": {"state": "400.0", "attributes": {"unit_of_measurement": "W"}},
            "sensor.battery_1_level": {"state": "85.0", "attributes": {"unit_of_measurement": "%"}},
            "sensor.battery_2_level": {"state": "90.0", "attributes": {"unit_of_measurement": "%"}},
            # Solar inverter analysis sensor references
            "sensor.solar_irradiance": {"state": "800.0", "attributes": {"unit_of_measurement": "W/m²"}},
            "sensor.solar_panel_temperature": {"state": "35.0", "attributes": {"unit_of_measurement": "°C"}},
            "sensor.days_since_solar_maintenance": {"state": "150.0", "attributes": {"unit_of_measurement": "days"}},
        }

        # 2. Define your YAML file path and expected sensor count
        yaml_file_path = "examples/attribute_variables_example.yaml"  # Use the example directly
        expected_sensor_count = (
            4  # 4 sensors: energy_monitor, temperature_analysis, home_automation_hub, solar_inverter_analysis
        )
        device_identifier = "test_device_attribute_variables"  # Must match your YAML global_settings

        # =============================================================================
        # STANDARD SETUP (DON'T CHANGE UNLESS YOU KNOW WHAT YOU'RE DOING)
        # =============================================================================

        # Save original state for cleanup
        original_entities = dict(mock_entity_registry._entities)
        original_states = dict(mock_states)

        try:
            # Register required entities
            for entity_id, data in required_entities.items():
                mock_entity_registry.register_entity(entity_id, entity_id, "sensor")
                mock_states.register_state(entity_id, data["state"], data["attributes"])

            # Add security devices for the collection function test with unique test-specific names
            test_security_devices = [
                ("sensor.attr_var_test_door_1", "door", "on"),
                ("sensor.attr_var_test_door_2", "door", "off"),
                ("sensor.attr_var_test_window_1", "window", "on"),
                ("sensor.attr_var_test_window_2", "window", "unavailable"),
                ("sensor.attr_var_test_motion_1", "motion", "on"),
                ("sensor.attr_var_test_motion_2", "motion", "unknown"),
            ]

            for entity_id, device_class, state in test_security_devices:
                mock_entity_registry.register_entity(entity_id, entity_id, "binary_sensor", device_class=device_class)
                mock_states.register_state(entity_id, state, {"device_class": device_class})

            # Set up storage manager with standard pattern
            with (
                patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
                patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
                patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
                patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
            ):
                # Standard mock setup
                mock_store = AsyncMock()
                mock_store.async_load.return_value = None
                MockStore.return_value = mock_store
                MockDeviceRegistry.return_value = mock_device_registry

                # Create storage manager
                storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
                storage_manager._store = mock_store
                await storage_manager.async_load()

                # Create sensor set
                sensor_set_id = "test_attribute_variables_sensor_set"
                await storage_manager.async_create_sensor_set(
                    sensor_set_id=sensor_set_id, device_identifier=device_identifier, name="Attribute Variables Test Sensor Set"
                )

                # Load YAML configuration
                with open(yaml_file_path) as f:
                    yaml_content = f.read()

                result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

                # BULLETPROOF ASSERTION 1: YAML import must succeed with exact count
                assert result["sensors_imported"] == expected_sensor_count, (
                    f"YAML import failed: expected {expected_sensor_count} sensors, "
                    f"got {result['sensors_imported']}. Result: {result}"
                )

                # Set up synthetic sensors
                sensor_manager = await async_setup_synthetic_sensors(
                    hass=mock_hass,
                    config_entry=mock_config_entry,
                    async_add_entities=mock_async_add_entities,
                    storage_manager=storage_manager,
                )

                # BULLETPROOF ASSERTION 2: Sensor manager must be created
                assert sensor_manager is not None, "Sensor manager creation failed"

                # BULLETPROOF ASSERTION 3: Entities must be added to HA
                assert mock_async_add_entities.call_args_list, (
                    "async_add_entities was never called - no entities were added to HA"
                )

                # Update sensors to ensure formulas are evaluated
                await sensor_manager.async_update_sensors()

                # Get all created entities
                all_entities = []
                for call in mock_async_add_entities.call_args_list:
                    entities_list = call.args[0] if call.args else []
                    all_entities.extend(entities_list)

                # BULLETPROOF ASSERTION 4: Exact entity count verification
                assert len(all_entities) == expected_sensor_count, (
                    f"Wrong number of entities created: expected {expected_sensor_count}, "
                    f"got {len(all_entities)}. Entities: {[getattr(e, 'unique_id', 'no_id') for e in all_entities]}"
                )

                # Create lookup for easier testing
                entity_lookup = {entity.unique_id: entity for entity in all_entities}

                # Set up entities with proper hass and platform attributes
                mock_platform = Mock()
                mock_platform.platform_name = "sensor"
                mock_platform.logger = Mock()

                for entity in all_entities:
                    entity.hass = mock_hass
                    entity.platform = mock_platform

                # =============================================================================
                # ADD YOUR SPECIFIC ASSERTIONS HERE
                # =============================================================================

                # Test energy_monitor sensor
                energy_monitor = entity_lookup.get("energy_monitor")
                assert energy_monitor is not None, (
                    f"Sensor 'energy_monitor' not found. Available sensors: {list(entity_lookup.keys())}"
                )

                # Test energy_monitor has valid value
                assert energy_monitor.native_value is not None, "Sensor 'energy_monitor' has None value"
                assert str(energy_monitor.native_value) not in ["unknown", "unavailable", ""], (
                    f"Sensor 'energy_monitor' has invalid value: {energy_monitor.native_value}"
                )

                # Test energy_monitor calculation: grid_power + solar_power = 1500 + 800 = 2300
                expected_energy_value = 2300.0
                actual_energy_value = float(energy_monitor.native_value)
                assert abs(actual_energy_value - expected_energy_value) < 0.001, (
                    f"Energy monitor calculation wrong: expected {expected_energy_value}, got {actual_energy_value}"
                )

                # Test energy_monitor attributes
                assert hasattr(energy_monitor, "extra_state_attributes"), "Energy monitor missing extra_state_attributes"
                attrs = energy_monitor.extra_state_attributes or {}

                # Test power_balance attribute: grid_power - solar_power = 1500 - 800 = 700
                assert "power_balance" in attrs, "Energy monitor missing power_balance attribute"
                expected_power_balance = 700.0
                actual_power_balance = float(attrs["power_balance"])
                assert abs(actual_power_balance - expected_power_balance) < 0.001, (
                    f"Power balance calculation wrong: expected {expected_power_balance}, got {actual_power_balance}"
                )

                # Test battery_status attribute: battery_level * battery_capacity / 100 = 75 * 10 / 100 = 7.5
                assert "battery_status" in attrs, "Energy monitor missing battery_status attribute"
                expected_battery_status = 7.5
                actual_battery_status = float(attrs["battery_status"])
                assert abs(actual_battery_status - expected_battery_status) < 0.001, (
                    f"Battery status calculation wrong: expected {expected_battery_status}, got {actual_battery_status}"
                )

                # Test efficiency_analysis attribute: solar_power / (solar_power + grid_power) * panel_efficiency
                # = 800 / (800 + 1500) * 0.18 = 800 / 2300 * 0.18 = 0.0626
                assert "efficiency_analysis" in attrs, "Energy monitor missing efficiency_analysis attribute"
                expected_efficiency = 0.0626
                actual_efficiency = float(attrs["efficiency_analysis"])
                assert abs(actual_efficiency - expected_efficiency) < 0.001, (
                    f"Efficiency analysis calculation wrong: expected {expected_efficiency}, got {actual_efficiency}"
                )

                # Test literal attributes
                assert attrs.get("voltage") == 240, f"Voltage attribute wrong: expected 240, got {attrs.get('voltage')}"
                assert attrs.get("manufacturer") == "EnergyCorp", (
                    f"Manufacturer attribute wrong: expected EnergyCorp, got {attrs.get('manufacturer')}"
                )
                assert attrs.get("is_active") is True, f"is_active attribute wrong: expected True, got {attrs.get('is_active')}"

                # Test temperature_analysis sensor
                temp_analysis = entity_lookup.get("temperature_analysis")
                assert temp_analysis is not None, (
                    f"Sensor 'temperature_analysis' not found. Available sensors: {list(entity_lookup.keys())}"
                )

                # Test temperature_analysis calculation: indoor_temp + outdoor_temp = 22.5 + 15.0 = 37.5
                expected_temp_value = 37.5
                actual_temp_value = float(temp_analysis.native_value)
                assert abs(actual_temp_value - expected_temp_value) < 0.001, (
                    f"Temperature analysis calculation wrong: expected {expected_temp_value}, got {actual_temp_value}"
                )

                # Test temperature_analysis attributes
                temp_attrs = temp_analysis.extra_state_attributes or {}

                # Test average_temp attribute: (indoor_temp + outdoor_temp) / 2 = (22.5 + 15.0) / 2 = 18.75
                assert "average_temp" in temp_attrs, "Temperature analysis missing average_temp attribute"
                expected_avg_temp = 18.75
                actual_avg_temp = float(temp_attrs["average_temp"])
                assert abs(actual_avg_temp - expected_avg_temp) < 0.001, (
                    f"Average temp calculation wrong: expected {expected_avg_temp}, got {actual_avg_temp}"
                )

                # Test temperature_difference attribute: indoor_temp - weather_station_temp = 22.5 - 14.5 = 8.0
                assert "temperature_difference" in temp_attrs, "Temperature analysis missing temperature_difference attribute"
                expected_temp_diff = 8.0
                actual_temp_diff = float(temp_attrs["temperature_difference"])
                assert abs(actual_temp_diff - expected_temp_diff) < 0.001, (
                    f"Temperature difference calculation wrong: expected {expected_temp_diff}, got {actual_temp_diff}"
                )

                # Test comfort_index attribute: if(comfort_temp > 20 and comfort_humidity < 60, 'Comfortable', 'Uncomfortable')
                # comfort_temp = 21.0, comfort_humidity = 50.0, so should be 'Comfortable'
                assert "comfort_index" in temp_attrs, "Temperature analysis missing comfort_index attribute"
                assert temp_attrs["comfort_index"] == "Comfortable", (
                    f"Comfort index wrong: expected 'Comfortable', got {temp_attrs['comfort_index']}"
                )

                # Test literal attributes
                assert temp_attrs.get("sensor_type") == "temperature", (
                    f"Sensor type attribute wrong: expected temperature, got {temp_attrs.get('sensor_type')}"
                )
                assert temp_attrs.get("location") == "Living Room", (
                    f"Location attribute wrong: expected Living Room, got {temp_attrs.get('location')}"
                )
                assert temp_attrs.get("requires_maintenance") is False, (
                    f"Requires maintenance attribute wrong: expected False, got {temp_attrs.get('requires_maintenance')}"
                )

                # Test home_automation_hub sensor
                hub = entity_lookup.get("home_automation_hub")
                assert hub is not None, (
                    f"Sensor 'home_automation_hub' not found. Available sensors: {list(entity_lookup.keys())}"
                )

                # Test hub calculation: total_devices = 25.0
                expected_hub_value = 25.0
                actual_hub_value = float(hub.native_value)
                assert abs(actual_hub_value - expected_hub_value) < 0.001, (
                    f"Hub calculation wrong: expected {expected_hub_value}, got {actual_hub_value}"
                )

                # Test hub attributes
                hub_attrs = hub.extra_state_attributes or {}

                # Test security_status attribute: count(all devices) - count(devices excluding unavailable/unknown/off)
                # Based on the collection function results we observed: 10 - 8 = 2
                assert "security_status" in hub_attrs, "Hub missing security_status attribute"
                expected_security_status = 2.0
                actual_security_status = float(hub_attrs["security_status"])
                assert abs(actual_security_status - expected_security_status) < 0.001, (
                    f"Security status calculation wrong: expected {expected_security_status}, got {actual_security_status}"
                )

                # Test energy_cost_projection attribute: current_usage * rate_per_kwh * hours_per_day * days_per_month
                # = 1200 * 0.12 * 24 * 30 = 103680
                assert "energy_cost_projection" in hub_attrs, "Hub missing energy_cost_projection attribute"
                expected_cost = 103680.0
                actual_cost = float(hub_attrs["energy_cost_projection"])
                assert abs(actual_cost - expected_cost) < 0.001, (
                    f"Energy cost projection calculation wrong: expected {expected_cost}, got {actual_cost}"
                )

                # Test circuit_analysis attribute: sum(circuit_power_1) + sum(circuit_power_2) = 800 + 400 = 1200
                assert "circuit_analysis" in hub_attrs, "Hub missing circuit_analysis attribute"
                expected_circuit = 1200.0
                actual_circuit = float(hub_attrs["circuit_analysis"])
                assert abs(actual_circuit - expected_circuit) < 0.001, (
                    f"Circuit analysis calculation wrong: expected {expected_circuit}, got {actual_circuit}"
                )

                # Test low_battery_alert attribute: battery_sensor_1 + battery_sensor_2 = 85 + 90 = 175
                assert "low_battery_alert" in hub_attrs, "Hub missing low_battery_alert attribute"
                expected_battery_alert = 175.0
                actual_battery_alert = float(hub_attrs["low_battery_alert"])
                assert abs(actual_battery_alert - expected_battery_alert) < 0.001, (
                    f"Low battery alert calculation wrong: expected {expected_battery_alert}, got {actual_battery_alert}"
                )

                # Test literal attributes
                assert hub_attrs.get("hub_version") == "2.1.0", (
                    f"Hub version attribute wrong: expected 2.1.0, got {hub_attrs.get('hub_version')}"
                )
                assert hub_attrs.get("max_devices") == 100, (
                    f"Max devices attribute wrong: expected 100, got {hub_attrs.get('max_devices')}"
                )
                assert hub_attrs.get("auto_update") is True, (
                    f"Auto update attribute wrong: expected True, got {hub_attrs.get('auto_update')}"
                )

                # Test solar_inverter_analysis sensor
                solar = entity_lookup.get("solar_inverter_analysis")
                assert solar is not None, (
                    f"Sensor 'solar_inverter_analysis' not found. Available sensors: {list(entity_lookup.keys())}"
                )

                # Test solar calculation: inverter_power = 800.0
                expected_solar_value = 800.0
                actual_solar_value = float(solar.native_value)
                assert abs(actual_solar_value - expected_solar_value) < 0.001, (
                    f"Solar inverter calculation wrong: expected {expected_solar_value}, got {actual_solar_value}"
                )

                # Test solar attributes
                solar_attrs = solar.extra_state_attributes or {}

                # Test weather_efficiency attribute: inverter_power / (irradiance * panel_area) * 100
                # = 800 / (800 * 50) * 100 = 800 / 40000 * 100 = 2.0
                assert "weather_efficiency" in solar_attrs, "Solar missing weather_efficiency attribute"
                expected_weather_eff = 2.0
                actual_weather_eff = float(solar_attrs["weather_efficiency"])
                assert abs(actual_weather_eff - expected_weather_eff) < 0.001, (
                    f"Weather efficiency calculation wrong: expected {expected_weather_eff}, got {actual_weather_eff}"
                )

                # Test temp_efficiency attribute: if(panel_temp > optimal_temp, 100 - (panel_temp - optimal_temp) * temp_coeff, 100)
                # panel_temp = 35, optimal_temp = 25, temp_coeff = 0.4
                # 35 > 25, so: 100 - (35 - 25) * 0.4 = 100 - 10 * 0.4 = 100 - 4 = 96
                assert "temp_efficiency" in solar_attrs, "Solar missing temp_efficiency attribute"
                expected_temp_eff = 96.0
                actual_temp_eff = float(solar_attrs["temp_efficiency"])
                assert abs(actual_temp_eff - expected_temp_eff) < 0.001, (
                    f"Temp efficiency calculation wrong: expected {expected_temp_eff}, got {actual_temp_eff}"
                )

                # Test maintenance_due attribute: if(days_since_maintenance > maintenance_interval, 'Due', 'OK')
                # days_since_maintenance = 150, maintenance_interval = 180
                # 150 < 180, so should be 'OK'
                assert "maintenance_due" in solar_attrs, "Solar missing maintenance_due attribute"
                assert solar_attrs["maintenance_due"] == "OK", (
                    f"Maintenance due wrong: expected 'OK', got {solar_attrs['maintenance_due']}"
                )

                # Test literal attributes
                assert solar_attrs.get("rated_power") == 5000, (
                    f"Rated power attribute wrong: expected 5000, got {solar_attrs.get('rated_power')}"
                )
                assert solar_attrs.get("efficiency_rating") == 0.95, (
                    f"Efficiency rating attribute wrong: expected 0.95, got {solar_attrs.get('efficiency_rating')}"
                )
                assert solar_attrs.get("grid_compliant") is True, (
                    f"Grid compliant attribute wrong: expected True, got {solar_attrs.get('grid_compliant')}"
                )

                # Test all sensors have valid values (bulletproof check)
                for entity in all_entities:
                    unique_id = getattr(entity, "unique_id", "unknown")
                    value = getattr(entity, "native_value", None)

                    # Every sensor must have a valid value
                    assert value is not None, f"Sensor '{unique_id}' has None value"
                    assert str(value) not in ["unknown", "unavailable", ""], f"Sensor '{unique_id}' has invalid value: {value}"

                    # Every sensor must have basic attributes
                    assert hasattr(entity, "name"), f"Sensor '{unique_id}' missing name attribute"
                    assert hasattr(entity, "unique_id"), f"Sensor '{unique_id}' missing unique_id attribute"

                # Clean up
                await storage_manager.async_delete_sensor_set(sensor_set_id)

        finally:
            # Restore original state
            mock_entity_registry._entities.clear()
            mock_entity_registry._entities.update(original_entities)
            mock_states.clear()
            mock_states.update(original_states)
