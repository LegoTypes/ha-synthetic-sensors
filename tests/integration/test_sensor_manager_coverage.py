"""Tests for sensor_manager.py with meaningful coverage scenarios."""

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import pytest

from ha_synthetic_sensors.config_models import Config, FormulaConfig, SensorConfig
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig, SensorState
from ha_synthetic_sensors.name_resolver import NameResolver


class TestSensorManagerDeviceManagement:
    """Test device management functionality in SensorManager."""

    def test_get_existing_device_info_found(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _get_existing_device_info when device is found."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager_config = SensorManagerConfig(integration_domain="test_domain")
        manager = SensorManager(hass, name_resolver, add_entities_callback, manager_config)

        # Mock device registry
        mock_device_entry = MagicMock()
        mock_device_entry.id = "device_123"
        mock_device_entry.name = "Test Device"
        mock_device_entry.manufacturer = "Test Manufacturer"
        mock_device_entry.model = "Test Model"
        mock_device_entry.sw_version = "1.0.0"
        mock_device_entry.hw_version = "v1"
        mock_device_entry.identifiers = {("test_domain", "device_123")}

        manager._device_registry = MagicMock()
        manager._device_registry.async_get_device.return_value = mock_device_entry

        result = manager._get_existing_device_info("device_123")

        assert result is not None
        assert result["identifiers"] == {("test_domain", "device_123")}
        assert result["name"] == "Test Device"
        assert result["manufacturer"] == "Test Manufacturer"
        assert result["model"] == "Test Model"
        assert result["sw_version"] == "1.0.0"
        assert result["hw_version"] == "v1"

    def test_get_existing_device_info_not_found(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _get_existing_device_info when device is not found."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager_config = SensorManagerConfig(integration_domain="test_domain")
        manager = SensorManager(hass, name_resolver, add_entities_callback, manager_config)

        # Mock device registry returning None
        manager._device_registry = MagicMock()
        manager._device_registry.async_get_device.return_value = None

        result = manager._get_existing_device_info("nonexistent_device")

        assert result is None

    def test_create_new_device_info_success(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _create_new_device_info with complete device metadata."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager_config = SensorManagerConfig(integration_domain="test_domain")
        manager = SensorManager(hass, name_resolver, add_entities_callback, manager_config)

        # Create sensor config with device metadata
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            device_identifier="device_123",
            device_name="Custom Device Name",
            device_manufacturer="Custom Manufacturer",
            device_model="Custom Model",
            device_sw_version="2.0.0",
            device_hw_version="v2",
            suggested_area="Living Room",
            formulas=[FormulaConfig(id="main", formula="42")],
        )

        result = manager._create_new_device_info(sensor_config)

        assert result["identifiers"] == {("test_domain", "device_123")}
        assert result["name"] == "Custom Device Name"
        assert result["manufacturer"] == "Custom Manufacturer"
        assert result["model"] == "Custom Model"
        assert result["sw_version"] == "2.0.0"
        assert result["hw_version"] == "v2"
        assert result["suggested_area"] == "Living Room"

    def test_create_new_device_info_fallback_name(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _create_new_device_info with fallback device name."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager_config = SensorManagerConfig(integration_domain="test_domain")
        manager = SensorManager(hass, name_resolver, add_entities_callback, manager_config)

        # Create sensor config without device name
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            device_identifier="device_123",
            formulas=[FormulaConfig(id="main", formula="42")],
        )

        result = manager._create_new_device_info(sensor_config)

        assert result["name"] == "Device device_123"  # Fallback name

    def test_create_new_device_info_missing_identifier(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _create_new_device_info with missing device_identifier."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager_config = SensorManagerConfig(integration_domain="test_domain")
        manager = SensorManager(hass, name_resolver, add_entities_callback, manager_config)

        # Create sensor config without device_identifier
        sensor_config = SensorConfig(
            unique_id="test_sensor", name="Test Sensor", formulas=[FormulaConfig(id="main", formula="42")]
        )

        with pytest.raises(ValueError, match="device_identifier is required"):
            manager._create_new_device_info(sensor_config)


class TestSensorManagerDataProviderManagement:
    """Test data provider entity management functionality."""

    def test_register_data_provider_entities(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test register_data_provider_entities method."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        entity_ids = {"sensor.test1", "sensor.test2"}
        change_notifier = MagicMock()

        manager.register_data_provider_entities(entity_ids, change_notifier)

        assert manager._registered_entities == entity_ids
        assert manager._change_notifier == change_notifier

    def test_update_data_provider_entities(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test update_data_provider_entities method."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        # Initial registration
        initial_entities = {"sensor.test1"}
        manager.register_data_provider_entities(initial_entities)

        # Update with new entities
        updated_entities = {"sensor.test2", "sensor.test3"}
        manager.update_data_provider_entities(updated_entities)

        assert manager._registered_entities == updated_entities

    def test_get_registered_entities(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test get_registered_entities method."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        entity_ids = {"sensor.test1", "sensor.test2"}
        manager._registered_entities = entity_ids

        result = manager.get_registered_entities()

        assert result == entity_ids
        # Ensure it returns a copy, not the original
        assert result is not manager._registered_entities

    def test_extract_backing_entities_from_sensor(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _extract_backing_entities_from_sensor method."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        # Register some entities
        manager._registered_entities = {"sensor.backing1", "sensor.backing2"}

        # Create sensor config with variables that reference registered entities
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            formulas=[
                FormulaConfig(
                    id="main",
                    formula="var1 + var2",
                    variables={
                        "var1": "sensor.backing1",  # Registered entity
                        "var2": "sensor.backing2",  # Registered entity
                        "var3": "sensor.unregistered",  # Not registered
                        "var4": "not_an_entity",  # Not an entity ID
                    },
                )
            ],
        )

        result = manager._extract_backing_entities_from_sensor(sensor_config)

        assert result == {"sensor.backing1", "sensor.backing2"}

    def test_extract_backing_entities_from_sensors(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test _extract_backing_entities_from_sensors method."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        # Register some entities
        manager._registered_entities = {"sensor.backing1", "sensor.backing2", "sensor.backing3"}

        # Create multiple sensor configs
        sensor_configs = [
            SensorConfig(
                unique_id="sensor1",
                name="Sensor 1",
                formulas=[FormulaConfig(id="main", formula="var1", variables={"var1": "sensor.backing1"})],
            ),
            SensorConfig(
                unique_id="sensor2",
                name="Sensor 2",
                formulas=[FormulaConfig(id="main", formula="var2", variables={"var2": "sensor.backing2"})],
            ),
            SensorConfig(
                unique_id="sensor3",
                name="Sensor 3",
                formulas=[FormulaConfig(id="main", formula="var3", variables={"var3": "sensor.backing3"})],
            ),
        ]

        result = manager._extract_backing_entities_from_sensors(sensor_configs)

        assert result == {"sensor.backing1", "sensor.backing2", "sensor.backing3"}

    @pytest.mark.asyncio
    async def test_async_update_sensors_for_entities(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test async_update_sensors_for_entities method."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        # Create mock sensors
        mock_sensor1 = MagicMock()
        mock_sensor1.config = SensorConfig(
            unique_id="sensor1",
            name="Sensor 1",
            formulas=[FormulaConfig(id="main", formula="var1", variables={"var1": "sensor.backing1"})],
        )

        mock_sensor2 = MagicMock()
        mock_sensor2.config = SensorConfig(
            unique_id="sensor2",
            name="Sensor 2",
            formulas=[FormulaConfig(id="main", formula="var2", variables={"var2": "sensor.backing2"})],
        )

        manager._sensors_by_unique_id = {"sensor1": mock_sensor1, "sensor2": mock_sensor2}

        # Register entities
        manager._registered_entities = {"sensor.backing1", "sensor.backing2"}

        # Mock the _update_sensors_in_order method (called by the optimization)
        with patch.object(manager, "_update_sensors_in_order") as mock_update:
            await manager.async_update_sensors_for_entities({"sensor.backing1"})

            # Should call _update_sensors_in_order once with sensor1
            mock_update.assert_called_once()
            # The optimization calls with evaluation order (unique_ids)
            called_evaluation_order = mock_update.call_args[0][0]
            assert "sensor1" in called_evaluation_order

    @pytest.mark.asyncio
    async def test_async_update_sensors_for_entities_no_affected_sensors(
        self, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test async_update_sensors_for_entities when no sensors are affected."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        # Create mock sensor that doesn't use the changed entity
        mock_sensor = MagicMock()
        mock_sensor.config = SensorConfig(
            unique_id="sensor1",
            name="Sensor 1",
            formulas=[FormulaConfig(id="main", formula="var1", variables={"var1": "sensor.backing1"})],
        )

        manager._sensors_by_unique_id = {"sensor1": mock_sensor}
        manager._registered_entities = {"sensor.backing1"}

        # Mock the _update_sensors_in_order method (called by the optimization)
        with patch.object(manager, "_update_sensors_in_order") as mock_update:
            await manager.async_update_sensors_for_entities({"sensor.backing2"})

            # Should not call _update_sensors_in_order since no sensors are affected
            mock_update.assert_not_called()


class TestSensorManagerStateManagement:
    """Test sensor state management functionality."""

    def test_on_sensor_updated_new_sensor(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test on_sensor_updated for a new sensor."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        sensor_unique_id = "test_sensor"
        main_value = 42.5
        calculated_attributes = {"power": 100, "voltage": 240}

        manager.on_sensor_updated(sensor_unique_id, main_value, calculated_attributes)

        assert sensor_unique_id in manager._sensor_states
        state = manager._sensor_states[sensor_unique_id]
        assert state.sensor_name == sensor_unique_id
        assert state.main_value == main_value
        assert state.calculated_attributes == calculated_attributes
        assert state.is_available is True
        assert state.error_count == 0

    def test_on_sensor_updated_existing_sensor(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test on_sensor_updated for an existing sensor."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        sensor_unique_id = "test_sensor"

        # Create initial state
        initial_state = SensorState(
            sensor_name=sensor_unique_id,
            main_value=10.0,
            calculated_attributes={"old": "value"},
            last_update=datetime(2023, 1, 1),
            error_count=5,
            is_available=False,
        )
        manager._sensor_states[sensor_unique_id] = initial_state

        # Update the sensor
        new_main_value = 42.5
        new_calculated_attributes = {"power": 100, "voltage": 240}

        manager.on_sensor_updated(sensor_unique_id, new_main_value, new_calculated_attributes)

        state = manager._sensor_states[sensor_unique_id]
        assert state.main_value == new_main_value
        assert state.calculated_attributes == new_calculated_attributes
        assert state.is_available is True
        # Error count should be preserved
        assert state.error_count == 5

    def test_update_sensor_states(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test update_sensor_states method."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        sensor_unique_id = "test_sensor"
        main_value = 42.5
        calculated_attributes = {"power": 100, "voltage": 240}

        manager.update_sensor_states(sensor_unique_id, main_value, calculated_attributes)

        assert sensor_unique_id in manager._sensor_states
        state = manager._sensor_states[sensor_unique_id]
        assert state.main_value == main_value
        assert state.calculated_attributes == calculated_attributes

    def test_update_sensor_states_no_calculated_attributes(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test update_sensor_states method without calculated attributes."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        sensor_unique_id = "test_sensor"
        main_value = 42.5

        manager.update_sensor_states(sensor_unique_id, main_value)

        assert sensor_unique_id in manager._sensor_states
        state = manager._sensor_states[sensor_unique_id]
        assert state.main_value == main_value
        assert state.calculated_attributes == {}

    def test_get_sensor_statistics(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test get_sensor_statistics method."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        # Create mock sensors
        mock_sensor1 = MagicMock()
        mock_sensor1.available = True

        mock_sensor2 = MagicMock()
        mock_sensor2.available = False

        manager._sensors_by_unique_id = {"sensor1": mock_sensor1, "sensor2": mock_sensor2}

        # Add some sensor states
        manager._sensor_states = {
            "sensor1": SensorState(
                sensor_name="sensor1",
                main_value=42.5,
                calculated_attributes={"power": 100},
                last_update=datetime(2023, 1, 1),
                error_count=0,
                is_available=True,
            ),
            "sensor2": SensorState(
                sensor_name="sensor2",
                main_value=10.0,
                calculated_attributes={"voltage": 240},
                last_update=datetime(2023, 1, 2),
                error_count=5,
                is_available=False,
            ),
        }

        stats = manager.get_sensor_statistics()

        assert stats["total_sensors"] == 2
        assert stats["active_sensors"] == 1
        assert "sensor1" in stats["states"]
        assert "sensor2" in stats["states"]
        assert stats["states"]["sensor1"]["main_value"] == 42.5
        assert stats["states"]["sensor2"]["error_count"] == 5


class TestSensorManagerErrorHandling:
    """Test error handling in sensor manager."""

    @pytest.mark.asyncio
    async def test_load_configuration_error_handling(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test load_configuration error handling and rollback."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        # Set up initial configuration
        old_config = Config(sensors=[])
        manager._current_config = old_config

        # Create a config that will cause an error
        new_config = Config(
            sensors=[
                SensorConfig(unique_id="test_sensor", name="Test Sensor", formulas=[FormulaConfig(id="main", formula="42")])
            ]
        )

        # Mock _update_existing_sensors to raise an exception
        with patch.object(manager, "_update_existing_sensors", side_effect=Exception("Test error")):
            with pytest.raises(Exception, match="Test error"):
                await manager.load_configuration(new_config)

            # Should restore old configuration
            assert manager._current_config == old_config

    @pytest.mark.asyncio
    async def test_remove_sensor_not_found(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test remove_sensor when sensor is not found."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        result = await manager.remove_sensor("nonexistent_sensor")

        assert result is False

    @pytest.mark.asyncio
    async def test_remove_sensor_success(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test remove_sensor when sensor exists."""
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        # Create mock sensor
        mock_sensor = MagicMock()
        mock_sensor.entity_id = "sensor.test"

        manager._sensors_by_unique_id = {"test_sensor": mock_sensor}
        manager._sensors_by_entity_id = {"sensor.test": mock_sensor}
        manager._sensor_states = {"test_sensor": MagicMock()}

        result = await manager.remove_sensor("test_sensor")

        assert result is True
        assert "test_sensor" not in manager._sensors_by_unique_id
        assert "sensor.test" not in manager._sensors_by_entity_id
        assert "test_sensor" not in manager._sensor_states

    async def test_normal_variable_extraction_still_works(self, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test that normal variable extraction still works for formulas with operators."""
        # Create sensor manager
        hass = MagicMock()
        name_resolver = MagicMock(spec=NameResolver)
        add_entities_callback = MagicMock()

        manager = SensorManager(hass, name_resolver, add_entities_callback)

        # Test that normal formulas with variables still extract dependencies correctly
        formula = "temp + humidity * 2"
        dependencies = manager.evaluator.get_formula_dependencies(formula)

        # Should extract variables from formulas with arithmetic operators
        assert "temp" in dependencies, f"Expected 'temp' to be extracted as dependency, got: {dependencies}"
        assert "humidity" in dependencies, f"Expected 'humidity' to be extracted as dependency, got: {dependencies}"
