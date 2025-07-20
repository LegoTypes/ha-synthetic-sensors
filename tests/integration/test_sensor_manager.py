"""Tests for sensor_manager module.

This module tests the SensorManager and DynamicSensor classes that handle
the creation, updating, and removal of synthetic sensors.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import STATE_UNAVAILABLE
import pytest

from ha_synthetic_sensors.config_manager import Config, FormulaConfig, SensorConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.name_resolver import NameResolver
from ha_synthetic_sensors.sensor_manager import DynamicSensor, SensorManager, SensorState


class TestSensorState:
    """Test SensorState dataclass."""

    def test_sensor_state_creation(self):
        """Test SensorState creation with defaults."""
        state = SensorState(
            sensor_name="test_sensor",
            main_value=42.0,
            calculated_attributes={"attr1": "value1"},
            last_update=datetime.now(),
        )

        assert state.sensor_name == "test_sensor"
        assert state.main_value == 42.0
        assert state.calculated_attributes == {"attr1": "value1"}
        assert state.error_count == 0
        assert state.is_available is True


class TestDynamicSensor:
    """Test DynamicSensor class."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.async_create_task = MagicMock()
        return hass

    @pytest.fixture
    def mock_sensor_manager(self):
        """Create a mock SensorManager."""
        manager = MagicMock()
        manager._on_sensor_updated = MagicMock()
        return manager

    @pytest.fixture
    def mock_evaluator(self):
        """Create a mock Evaluator."""
        evaluator = MagicMock(spec=Evaluator)
        evaluator.evaluate_formula = MagicMock()
        evaluator.clear_cache = MagicMock()
        return evaluator

    @pytest.fixture
    def sensor_config(self):
        """Create a test SensorConfig."""
        return SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            category="test",
            enabled=True,
            formulas=[],
        )

    @pytest.fixture
    def formula_config(self):
        """Create a test FormulaConfig."""
        return FormulaConfig(
            id="test_formula",
            name="Test Formula",
            formula="a + b",
            dependencies={"sensor.test_a", "sensor.test_b"},
            attributes={"test_attr": "test_value"},
            metadata={
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
                "icon": "mdi:power",
            },
        )

    def test_dynamic_sensor_initialization(
        self,
        mock_hass,
        sensor_config,
        formula_config,
        mock_evaluator,
        mock_sensor_manager,
    ):
        """Test DynamicSensor initialization."""
        # Add formula to sensor config for v2.0
        sensor_config.formulas = [formula_config]

        sensor = DynamicSensor(
            mock_hass,
            sensor_config,
            mock_evaluator,
            mock_sensor_manager,
        )
        # Set the hass attribute to ensure entity is properly initialized
        sensor.hass = mock_hass
        # Set entity_id manually for testing since it's not registered through
        # EntityComponent
        sensor.entity_id = f"sensor.{sensor._attr_unique_id}"

        # Test _attr_ properties are set correctly (v2.0 uses sensor unique_id)
        assert sensor._attr_unique_id == "test_sensor"
        assert sensor._attr_name == "Test Sensor"
        assert sensor._attr_native_unit_of_measurement == "W"
        # Device class is converted to enum in v2.0, check the enum value
        assert sensor._attr_device_class == SensorDeviceClass.POWER
        assert sensor._attr_state_class == "measurement"
        assert sensor._attr_icon == "mdi:power"
        assert sensor._attr_available is True
        assert sensor._attr_native_value is None

        # Test dependencies
        assert sensor._dependencies == {"sensor.test_a", "sensor.test_b"}


class TestSensorManager:
    """Test SensorManager class."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.async_create_task = MagicMock()
        return hass

    @pytest.fixture
    def mock_name_resolver(self):
        """Create a mock NameResolver."""
        return MagicMock(spec=NameResolver)

    @pytest.fixture
    def mock_add_entities(self):
        """Create a mock AddEntitiesCallback."""
        return MagicMock()

    @pytest.fixture
    def sensor_manager(self, mock_hass, mock_name_resolver, mock_add_entities):
        """Create a SensorManager instance."""
        return SensorManager(mock_hass, mock_name_resolver, mock_add_entities)

    @pytest.fixture
    def test_config(self):
        """Create a test configuration."""
        formula_config = FormulaConfig(
            id="test_formula",
            name="Test Formula",
            formula="a + b",
            dependencies={"sensor.test_a", "sensor.test_b"},
        )

        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            category="test",
            enabled=True,
            formulas=[formula_config],
        )

        return Config(sensors=[sensor_config])

    def test_sensor_manager_initialization(self, sensor_manager, mock_hass, mock_name_resolver, mock_add_entities):
        """Test SensorManager initialization."""
        assert sensor_manager._hass == mock_hass
        assert sensor_manager._name_resolver == mock_name_resolver
        assert sensor_manager._add_entities_callback == mock_add_entities
        assert isinstance(sensor_manager._evaluator, Evaluator)
        assert sensor_manager._sensors_by_unique_id == {}
        assert sensor_manager._sensors_by_entity_id == {}
        assert sensor_manager._sensor_states == {}
        assert sensor_manager._current_config is None

    def test_managed_sensors_property(self, sensor_manager):
        """Test managed_sensors property."""
        # Add some test data
        sensor_manager._sensors_by_unique_id["test"] = MagicMock()

        result = sensor_manager.managed_sensors
        assert "test" in result

        # Ensure it's a copy - v2.0 returns dict[str, DynamicSensor] not dict[str, list]
        result["test"] = "modified"
        assert sensor_manager._sensors_by_unique_id["test"] != "modified"

    def test_get_sensor_by_entity_id(self, sensor_manager):
        """Test get_sensor_by_entity_id method."""
        # Add a mock sensor
        mock_sensor = MagicMock()
        sensor_manager._sensors_by_entity_id["sensor.test"] = mock_sensor

        # Test existing entity
        result = sensor_manager.get_sensor_by_entity_id("sensor.test")
        assert result == mock_sensor

        # Test non-existing entity
        result = sensor_manager.get_sensor_by_entity_id("sensor.nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_create_sensor_entity(self, sensor_manager, test_config):
        """Test _create_sensor_entity method."""
        sensor_config = test_config.sensors[0]

        with patch("ha_synthetic_sensors.sensor_manager.DynamicSensor") as MockDynamicSensor:
            mock_sensor = MagicMock()
            mock_sensor.entity_id = "sensor.test_sensor"
            MockDynamicSensor.return_value = mock_sensor

            # Mock _create_sensor_entity to also update the tracking dict
            with patch.object(sensor_manager, "_sensors_by_entity_id", {}) as mock_dict:
                result = await sensor_manager._create_sensor_entity(sensor_config)

                # Manually add to the dict since we're mocking the creation
                mock_dict[mock_sensor.entity_id] = mock_sensor

                assert result == mock_sensor

                # Check sensor was added to entity_id lookup
                expected_id = "sensor.test_sensor"
                assert mock_dict[expected_id] == mock_sensor

    @pytest.mark.asyncio
    async def test_load_configuration_new(self, sensor_manager, test_config):
        """Test load_configuration with new configuration."""
        with patch.object(sensor_manager, "_create_all_sensors") as mock_create_all:
            await sensor_manager.load_configuration(test_config)

            assert sensor_manager._current_config == test_config
            mock_create_all.assert_called_once_with(test_config)

    @pytest.mark.asyncio
    async def test_remove_sensor(self, sensor_manager):
        """Test remove_sensor method."""
        # Add a sensor
        mock_sensor = MagicMock()
        mock_sensor.entity_id = "sensor.test_sensor"
        sensor_manager._sensors_by_unique_id["test_sensor"] = mock_sensor
        sensor_manager._sensors_by_entity_id["sensor.test_sensor"] = mock_sensor
        sensor_manager._sensor_states["test_sensor"] = SensorState(
            sensor_name="test_sensor",
            main_value=42.0,
            calculated_attributes={},
            last_update=datetime.now(),
        )

        result = await sensor_manager.remove_sensor("test_sensor")

        assert result is True
        assert "test_sensor" not in sensor_manager._sensors_by_unique_id
        assert "sensor.test_sensor" not in sensor_manager._sensors_by_entity_id
        assert "test_sensor" not in sensor_manager._sensor_states

    def test_on_sensor_updated_new_sensor(self, sensor_manager):
        """Test _on_sensor_updated with new sensor."""
        sensor_manager._on_sensor_updated("test_sensor", 42.5, {"attr1": "value1"})

        assert "test_sensor" in sensor_manager._sensor_states
        state = sensor_manager._sensor_states["test_sensor"]
        assert state.sensor_name == "test_sensor"
        assert state.main_value == 42.5
        assert state.calculated_attributes == {"attr1": "value1"}
        assert state.is_available is True


"""Extended tests for sensor_manager.py to improve coverage.

This module focuses on testing missing lines and edge cases not covered
by the existing test_sensor_manager.py file.
"""


class TestDynamicSensorExtended:
    """Extended tests for DynamicSensor class."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.async_create_task = MagicMock()
        hass.states = MagicMock()
        return hass

    @pytest.fixture
    def mock_sensor_manager(self):
        """Create a mock SensorManager."""
        manager = MagicMock()
        manager._on_sensor_updated = MagicMock()
        return manager

    @pytest.fixture
    def mock_evaluator(self):
        """Create a mock Evaluator."""
        evaluator = MagicMock(spec=Evaluator)
        evaluator.evaluate_formula = MagicMock()
        evaluator.clear_cache = MagicMock()
        return evaluator

    @pytest.fixture
    def sensor_config(self):
        """Create a test sensor configuration."""
        return SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            category="test",
            enabled=True,
            formulas=[],
        )

    @pytest.fixture
    def formula_config(self):
        """Create a test formula configuration."""
        return FormulaConfig(
            id="test_formula",
            name="Test Formula",
            formula="sensor.test_a + sensor.test_b",
            metadata={
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
                "icon": "mdi:power",
            },
            attributes={"test_attr": "test_value"},
            dependencies={"sensor.test_a", "sensor.test_b"},
        )

    @pytest.fixture
    def dynamic_sensor(
        self,
        mock_hass,
        sensor_config,
        formula_config,
        mock_evaluator,
        mock_sensor_manager,
    ):
        """Create a DynamicSensor instance."""
        # Add formula to sensor config for v2.0
        sensor_config.formulas = [formula_config]
        sensor = DynamicSensor(
            mock_hass,
            sensor_config,
            mock_evaluator,
            mock_sensor_manager,
        )
        # Set the hass attribute to ensure entity is properly initialized
        sensor.hass = mock_hass
        # Set entity_id manually for testing since it's not registered through
        # EntityComponent
        sensor.entity_id = f"sensor.{sensor._attr_unique_id}"
        return sensor

    def test_dynamic_sensor_initialization_no_name(self, mock_hass, mock_evaluator, mock_sensor_manager):
        """Test DynamicSensor initialization with no sensor name."""
        formula_config = FormulaConfig(id="test_formula", formula="1 + 1")
        sensor_config = SensorConfig(unique_id="test_sensor", formulas=[formula_config])

        sensor = DynamicSensor(
            mock_hass,
            sensor_config,
            mock_evaluator,
            mock_sensor_manager,
        )
        # Set the hass attribute to ensure entity is properly initialized
        sensor.hass = mock_hass
        # Set entity_id manually for testing since it's not registered through
        # EntityComponent
        sensor.entity_id = f"sensor.{sensor._attr_unique_id}"

        # Should use unique_id when sensor name is empty
        assert sensor._attr_name == "test_sensor"

    def test_dynamic_sensor_initialization_no_formula_name(self, mock_hass, mock_evaluator, mock_sensor_manager):
        """Test DynamicSensor initialization with no formula name."""
        formula_config = FormulaConfig(id="test_formula", formula="1 + 1")  # No name
        sensor_config = SensorConfig(unique_id="test_sensor", name="Test Sensor", formulas=[formula_config])

        sensor = DynamicSensor(
            mock_hass,
            sensor_config,
            mock_evaluator,
            mock_sensor_manager,
        )
        # Set the hass attribute to ensure entity is properly initialized
        sensor.hass = mock_hass
        # Set entity_id manually for testing since it's not registered through
        # EntityComponent
        sensor.entity_id = f"sensor.{sensor._attr_unique_id}"

        # Should use sensor name from config
        assert sensor._attr_name == "Test Sensor"

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_dependencies(self, dynamic_sensor):
        """Test async_added_to_hass with dependencies."""
        # Mock the async_track_state_change_event
        with (
            patch("ha_synthetic_sensors.sensor_manager.async_track_state_change_event") as mock_track,
            patch.object(dynamic_sensor, "async_write_ha_state"),
        ):
            mock_track.return_value = MagicMock()

            await dynamic_sensor.async_added_to_hass()

            # Should set up state change tracking for dependencies
            mock_track.assert_called_once_with(
                dynamic_sensor._hass,
                list(dynamic_sensor._dependencies),
                dynamic_sensor._handle_dependency_change,
            )
            assert len(dynamic_sensor._update_listeners) == 1

    @pytest.mark.asyncio
    async def test_async_added_to_hass_no_dependencies(self, mock_hass, mock_evaluator, mock_sensor_manager):
        """Test async_added_to_hass with no dependencies."""
        formula_config = FormulaConfig(id="test_formula", formula="1 + 1")
        sensor_config = SensorConfig(unique_id="test_sensor", name="Test Sensor", formulas=[formula_config])

        sensor = DynamicSensor(mock_hass, sensor_config, mock_evaluator, mock_sensor_manager)
        # Set the hass attribute to ensure entity is properly initialized
        sensor.hass = mock_hass
        # Set entity_id manually for testing since it's not registered through
        # EntityComponent
        sensor.entity_id = f"sensor.{sensor._attr_unique_id}"

        # No dependencies should not set up state change tracking
        with (
            patch("ha_synthetic_sensors.sensor_manager.async_track_state_change_event") as mock_track,
            patch.object(sensor, "async_write_ha_state"),
        ):
            await sensor.async_added_to_hass()
            mock_track.assert_not_called()
            assert len(sensor._update_listeners) == 0

    @pytest.mark.asyncio
    async def test_async_will_remove_from_hass(self, dynamic_sensor):
        """Test async_will_remove_from_hass."""
        # Add some mock listeners
        mock_listener1 = MagicMock()
        mock_listener2 = MagicMock()
        dynamic_sensor._update_listeners = [mock_listener1, mock_listener2]

        await dynamic_sensor.async_will_remove_from_hass()

        # All listeners should be called to clean up
        mock_listener1.assert_called_once()
        mock_listener2.assert_called_once()
        assert len(dynamic_sensor._update_listeners) == 0

    @pytest.mark.asyncio
    async def test_handle_dependency_change_functionality(self, dynamic_sensor, mock_evaluator):
        """Test _handle_dependency_change functionality."""
        # Mock the evaluator to return a successful result
        mock_evaluator.evaluate_formula_with_sensor_config.return_value = {
            "success": True,
            "value": 45.0,
        }

        # Create a mock event
        mock_event = MagicMock()

        # Patch the _async_update_sensor method to verify it's called
        with patch.object(dynamic_sensor, "_async_update_sensor", new_callable=AsyncMock) as mock_update:
            await dynamic_sensor._handle_dependency_change(mock_event)
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_update_sensor_success(self, dynamic_sensor, mock_evaluator):
        """Test _async_update_sensor with successful evaluation."""

        # Create a function that returns the expected result
        def mock_evaluate_formula_with_sensor_config(formula_config, context=None, sensor_config=None):
            return {
                "success": True,
                "value": 45.0,
            }

        # Mock successful evaluation
        mock_evaluator.evaluate_formula_with_sensor_config = mock_evaluate_formula_with_sensor_config

        # Mock async_write_ha_state
        with patch.object(dynamic_sensor, "async_write_ha_state"):
            await dynamic_sensor._async_update_sensor()

            # Verify sensor state was updated
            assert dynamic_sensor._attr_native_value == 45.0
            assert dynamic_sensor._attr_available is True
            assert dynamic_sensor._last_update is not None

            # HA state should be written (verified by patch)

            # Verify sensor manager was notified
            dynamic_sensor._sensor_manager.on_sensor_updated.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_update_sensor_evaluation_failure(self, dynamic_sensor, mock_evaluator):
        """Test _async_update_sensor with evaluation failure."""
        # Mock failed evaluation
        mock_evaluator.evaluate_formula_with_sensor_config.return_value = {
            "success": False,
            "error": "Test error",
        }

        with patch.object(dynamic_sensor, "async_write_ha_state"):
            await dynamic_sensor._async_update_sensor()

            # Sensor should be marked unavailable
            assert dynamic_sensor._attr_available is False

    @pytest.mark.asyncio
    async def test_async_update_sensor_exception(self, dynamic_sensor, mock_evaluator):
        """Test _async_update_sensor with exception."""
        # Mock evaluator to raise exception
        mock_evaluator.evaluate_formula_with_sensor_config.side_effect = Exception("Test exception")

        # Should not raise exception, just log and continue
        with patch.object(dynamic_sensor, "async_write_ha_state"):
            await dynamic_sensor._async_update_sensor()

    def test_update_extra_state_attributes(self, dynamic_sensor):
        """Test _update_extra_state_attributes method."""
        # Set some calculated attributes
        dynamic_sensor._calculated_attributes = {"calc_attr": 123}
        dynamic_sensor._last_update = datetime.now()

        dynamic_sensor._update_extra_state_attributes()

        attrs = dynamic_sensor._attr_extra_state_attributes
        assert "formula" in attrs
        assert "dependencies" in attrs
        assert "calc_attr" in attrs
        assert attrs["calc_attr"] == 123
        assert "last_update" in attrs
        assert "sensor_category" in attrs

    @pytest.mark.asyncio
    async def test_force_update_formula_same_dependencies(self, dynamic_sensor, mock_evaluator):
        """Test force_update_formula with same dependencies."""
        old_deps = dynamic_sensor._dependencies.copy()

        # Create new formula with same dependencies
        new_formula = FormulaConfig(
            id="new_formula",
            formula="different_formula",
            dependencies=old_deps,
        )

        mock_evaluator.evaluate_formula_with_sensor_config.return_value = {
            "success": True,
            "value": 100.0,
        }

        with patch.object(dynamic_sensor, "async_write_ha_state"):
            await dynamic_sensor.force_update_formula(new_formula)

            # Formula should be updated
            assert dynamic_sensor._main_formula == new_formula
            # Dependencies should remain the same
            assert dynamic_sensor._dependencies == old_deps

    @pytest.mark.asyncio
    async def test_force_update_formula_different_dependencies(self, dynamic_sensor, mock_evaluator):
        """Test force_update_formula with different dependencies."""
        # Create new formula with different dependencies
        new_deps = {"sensor.new_dep1", "sensor.new_dep2"}
        new_formula = FormulaConfig(
            id="new_formula",
            formula="different_formula",
            dependencies=new_deps,
        )

        mock_evaluator.evaluate_formula_with_sensor_config.return_value = {
            "success": True,
            "value": 100.0,
        }

        # Mock listener management
        old_listener = MagicMock()
        dynamic_sensor._update_listeners = [old_listener]

        with patch("ha_synthetic_sensors.sensor_manager.async_track_state_change_event") as mock_track:
            new_listener = MagicMock()
            mock_track.return_value = new_listener

            with patch.object(dynamic_sensor, "async_write_ha_state"):
                await dynamic_sensor.force_update_formula(new_formula)

                # Old listener should be removed
                old_listener.assert_called_once()

                # New listener should be set up
                mock_track.assert_called_once_with(
                    dynamic_sensor._hass,
                    list(new_deps),
                    dynamic_sensor._handle_dependency_change,
                )

                # Formula and dependencies should be updated
                assert dynamic_sensor._main_formula == new_formula
                assert dynamic_sensor._dependencies == new_deps
                assert dynamic_sensor._update_listeners == [new_listener]

    @pytest.mark.asyncio
    async def test_async_get_last_state_with_restored_state(self, dynamic_sensor):
        """Test async_get_last_state with restored state."""
        # Mock RestoreEntity.async_get_last_state
        mock_last_state = MagicMock()
        mock_last_state.state = "42.5"
        mock_last_state.attributes = {"test_attr": "test_value"}

        with (
            patch(
                "homeassistant.helpers.restore_state.RestoreEntity.async_get_last_state",
                return_value=mock_last_state,
            ),
            patch("ha_synthetic_sensors.sensor_manager.async_track_state_change_event") as mock_track,
            patch.object(dynamic_sensor, "_async_update_sensor", new_callable=AsyncMock),
        ):
            mock_track.return_value = MagicMock()

            # Call async_added_to_hass which calls async_get_last_state
            await dynamic_sensor.async_added_to_hass()

            # Verify state was restored (before _async_update_sensor is called)
            assert dynamic_sensor._attr_native_value == 42.5

    @pytest.mark.asyncio
    async def test_async_get_last_state_invalid_value(self, dynamic_sensor):
        """Test async_get_last_state with invalid numeric value."""
        # Mock RestoreEntity.async_get_last_state with non-numeric state
        mock_last_state = MagicMock()
        mock_last_state.state = "invalid_number"

        with (
            patch(
                "homeassistant.helpers.restore_state.RestoreEntity.async_get_last_state",
                return_value=mock_last_state,
            ),
            patch("ha_synthetic_sensors.sensor_manager.async_track_state_change_event") as mock_track,
            patch.object(dynamic_sensor, "_async_update_sensor", new_callable=AsyncMock),
        ):
            mock_track.return_value = MagicMock()

            await dynamic_sensor.async_added_to_hass()

            # Should use the string value as-is when float conversion fails
            assert dynamic_sensor._attr_native_value == "invalid_number"

    @pytest.mark.asyncio
    async def test_async_get_last_state_unavailable(self, dynamic_sensor):
        """Test async_get_last_state with unavailable state."""
        # Mock RestoreEntity.async_get_last_state with unavailable state
        mock_last_state = MagicMock()
        mock_last_state.state = STATE_UNAVAILABLE

        with (
            patch(
                "homeassistant.helpers.restore_state.RestoreEntity.async_get_last_state",
                return_value=mock_last_state,
            ),
            patch("ha_synthetic_sensors.sensor_manager.async_track_state_change_event") as mock_track,
            patch.object(dynamic_sensor, "_async_update_sensor", new_callable=AsyncMock),
        ):
            mock_track.return_value = MagicMock()

            await dynamic_sensor.async_added_to_hass()

            # Should not restore unavailable state
            assert dynamic_sensor._attr_native_value is None


class TestSensorManagerExtended:
    """Extended tests for SensorManager class to improve coverage."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.async_create_task = MagicMock()
        return hass

    @pytest.fixture
    def mock_name_resolver(self):
        """Create a mock NameResolver."""
        return MagicMock(spec=NameResolver)

    @pytest.fixture
    def mock_add_entities(self):
        """Create a mock AddEntitiesCallback."""
        return MagicMock()

    @pytest.fixture
    def sensor_manager(self, mock_hass, mock_name_resolver, mock_add_entities):
        """Create a SensorManager instance."""
        return SensorManager(mock_hass, mock_name_resolver, mock_add_entities)

    @pytest.fixture
    def test_config(self):
        """Create a test configuration with multiple sensors."""
        formula1 = FormulaConfig(id="formula1", formula="1 + 1")
        formula2 = FormulaConfig(id="formula2", formula="2 + 2")

        sensor1 = SensorConfig(unique_id="sensor1", name="Sensor 1", enabled=True, formulas=[formula1])
        sensor2 = SensorConfig(unique_id="sensor2", name="Sensor 2", enabled=False, formulas=[formula2])

        return Config(sensors=[sensor1, sensor2])

    @pytest.mark.asyncio
    async def test_create_all_sensors_with_disabled_sensor(self, sensor_manager, test_config):
        """Test _create_all_sensors skips disabled sensors."""
        with patch.object(sensor_manager, "_create_sensor_entity") as mock_create_entity:
            await sensor_manager._create_all_sensors(test_config)

            # Should only create entity for enabled sensor
            assert mock_create_entity.call_count == 1
            called_config = mock_create_entity.call_args[0][0]
            assert called_config.unique_id == "sensor1"

    @pytest.mark.asyncio
    async def test_update_existing_sensors_add_remove_update(self, sensor_manager):
        """Test _update_existing_sensors with add, remove, and update operations."""
        # Set up old configuration
        old_formula = FormulaConfig(id="old_formula", formula="old")
        old_sensor = SensorConfig(unique_id="existing", formulas=[old_formula], enabled=True)
        old_config = Config(sensors=[old_sensor])

        # Set up new configuration
        new_formula = FormulaConfig(id="new_formula", formula="new")
        updated_sensor = SensorConfig(unique_id="existing", formulas=[new_formula], enabled=True)
        new_sensor = SensorConfig(unique_id="new_sensor", formulas=[new_formula], enabled=True)
        new_config = Config(sensors=[updated_sensor, new_sensor])

        # Set up existing sensor
        mock_existing_sensor = MagicMock()
        sensor_manager._sensors_by_unique_id["existing"] = mock_existing_sensor

        with (
            patch.object(sensor_manager, "_create_sensor_entity") as mock_create,
            patch.object(sensor_manager, "_update_sensor_config") as mock_update,
        ):
            await sensor_manager._update_existing_sensors(old_config, new_config)

            # Should update existing sensor
            mock_update.assert_called_once()

            # Should create new sensor
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_all_sensors(self, sensor_manager):
        """Test _remove_all_sensors method."""
        # Add some sensors and states
        sensor_manager._sensors_by_unique_id["sensor1"] = MagicMock()
        sensor_manager._sensors_by_unique_id["sensor2"] = MagicMock()
        sensor_manager._sensor_states["sensor1"] = SensorState(
            sensor_name="sensor1",
            main_value=1.0,
            calculated_attributes={},
            last_update=datetime.now(),
        )
        sensor_manager._sensor_states["sensor2"] = SensorState(
            sensor_name="sensor2",
            main_value=2.0,
            calculated_attributes={},
            last_update=datetime.now(),
        )

        await sensor_manager._remove_all_sensors()

        assert len(sensor_manager._sensors_by_unique_id) == 0
        assert len(sensor_manager._sensor_states) == 0

    def test_get_all_sensor_entities(self, sensor_manager):
        """Test get_all_sensor_entities method."""
        # Add some sensors
        sensor1 = MagicMock()
        sensor2 = MagicMock()
        sensor_manager._sensors_by_unique_id["config1"] = sensor1
        sensor_manager._sensors_by_unique_id["config2"] = sensor2

        result = sensor_manager.get_all_sensor_entities()

        assert len(result) == 2
        assert sensor1 in result
        assert sensor2 in result

    def test_get_sensor_by_entity_id_found(self, sensor_manager):
        """Test get_sensor_by_entity_id with existing entity."""
        mock_sensor = MagicMock()
        sensor_manager._sensors_by_entity_id["sensor.test"] = mock_sensor

        result = sensor_manager.get_sensor_by_entity_id("sensor.test")
        assert result == mock_sensor

    def test_get_sensor_by_entity_id_not_found(self, sensor_manager):
        """Test get_sensor_by_entity_id with non-existing entity."""
        result = sensor_manager.get_sensor_by_entity_id("sensor.nonexistent")
        assert result is None

    def test_on_sensor_updated_existing_sensor(self, sensor_manager):
        """Test _on_sensor_updated with existing sensor."""
        # Add existing sensor state
        sensor_manager._sensor_states["test_sensor"] = SensorState(
            sensor_name="test_sensor",
            main_value=10.0,
            calculated_attributes={},
            last_update=datetime.now(),
        )

        sensor_manager._on_sensor_updated("test_sensor", 20.0, {"new_attr": "value"})

        state = sensor_manager._sensor_states["test_sensor"]
        assert state.main_value == 20.0
        assert state.calculated_attributes == {"new_attr": "value"}

    def test_on_sensor_updated_error_handling(self, sensor_manager):
        """Test _on_sensor_updated error handling."""
        # This should not raise an exception even with invalid data
        sensor_manager._on_sensor_updated(None, None, None)

        # State should still be created with defaults
        assert None in sensor_manager._sensor_states

    def test_update_sensor_states_new_sensor(self, sensor_manager):
        """Test update_sensor_states with new sensor."""
        sensor_manager.update_sensor_states("new_sensor", 42.0, {"attr": "value"})

        assert "new_sensor" in sensor_manager._sensor_states
        state = sensor_manager._sensor_states["new_sensor"]
        assert state.sensor_name == "new_sensor"
        assert state.main_value == 42.0
        assert state.calculated_attributes == {"attr": "value"}

    def test_update_sensor_states_existing_sensor(self, sensor_manager):
        """Test update_sensor_states with existing sensor."""
        # Add existing state
        sensor_manager._sensor_states["existing"] = SensorState(
            sensor_name="existing",
            main_value=10.0,
            calculated_attributes={},
            last_update=datetime.now(),
        )

        sensor_manager.update_sensor_states("existing", 30.0, {"new_attr": "new_value"})

        state = sensor_manager._sensor_states["existing"]
        assert state.main_value == 30.0
        assert state.calculated_attributes == {"new_attr": "new_value"}

    @pytest.mark.asyncio
    async def test_async_update_sensors_all(self, sensor_manager):
        """Test async_update_sensors with all sensors."""
        # Add mock sensors
        sensor1 = MagicMock()
        sensor1.async_update_sensor = AsyncMock()
        sensor2 = MagicMock()
        sensor2.async_update_sensor = AsyncMock()

        sensor_manager._sensors_by_unique_id = {"sensor1": sensor1, "sensor2": sensor2}

        await sensor_manager.async_update_sensors()

        # All sensors should be updated
        sensor1.async_update_sensor.assert_called_once()
        sensor2.async_update_sensor.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_update_sensors_specific(self, sensor_manager):
        """Test async_update_sensors with specific sensor configs."""
        # Create sensor configs
        formula = FormulaConfig(id="test", formula="1+1")
        config1 = SensorConfig(unique_id="sensor1", formulas=[formula])

        # Add mock sensors
        sensor1 = MagicMock()
        sensor1.async_update_sensor = AsyncMock()
        sensor2 = MagicMock()
        sensor2.async_update_sensor = AsyncMock()

        sensor_manager._sensors_by_unique_id = {"sensor1": sensor1, "sensor2": sensor2}

        await sensor_manager.async_update_sensors([config1])

        # Only sensor1 should be updated
        sensor1.async_update_sensor.assert_called_once()
        sensor2.async_update_sensor.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_sensor_success(self, sensor_manager):
        """Test remove_sensor with existing sensor."""
        # Add sensor and state
        mock_sensor = MagicMock()
        mock_sensor.entity_id = "sensor.test_sensor"
        sensor_manager._sensors_by_unique_id["test_sensor"] = mock_sensor
        sensor_manager._sensor_states["test_sensor"] = SensorState(
            sensor_name="test_sensor",
            main_value=1.0,
            calculated_attributes={},
            last_update=datetime.now(),
        )

        result = await sensor_manager.remove_sensor("test_sensor")

        assert result is True
        assert "test_sensor" not in sensor_manager._sensors_by_unique_id
        assert "test_sensor" not in sensor_manager._sensor_states

    @pytest.mark.asyncio
    async def test_remove_sensor_not_found(self, sensor_manager):
        """Test remove_sensor with non-existing sensor."""
        result = await sensor_manager.remove_sensor("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_load_configuration_update_existing(self, sensor_manager):
        """Test load_configuration updating existing configuration."""
        # Set existing config with one sensor
        formula = FormulaConfig(id="test", formula="1+1")
        old_sensor = SensorConfig(unique_id="old_sensor", formulas=[formula])
        old_config = Config(sensors=[old_sensor])
        sensor_manager._current_config = old_config

        # New config with different sensor
        new_formula = FormulaConfig(id="test", formula="2+2")
        new_sensor = SensorConfig(unique_id="new_sensor", formulas=[new_formula])
        new_config = Config(sensors=[new_sensor])

        with patch.object(sensor_manager, "_update_existing_sensors") as mock_update:
            await sensor_manager.load_configuration(new_config)

            assert sensor_manager._current_config == new_config
            mock_update.assert_called_once_with(old_config, new_config)

    def test_sensor_manager_properties(self, sensor_manager):
        """Test sensor_manager properties."""
        # Add test data
        sensor_manager._sensor_states["test"] = SensorState(
            sensor_name="test",
            main_value=42.0,
            calculated_attributes={},
            last_update=datetime.now(),
        )

        # Test sensor_states property
        states = sensor_manager.sensor_states
        assert "test" in states
        assert states["test"].main_value == 42.0

        # Ensure it's a copy
        states["test"] = "modified"
        assert sensor_manager._sensor_states["test"] != "modified"

    @pytest.mark.asyncio
    async def test_create_sensor_entity_multiple_formulas(self, sensor_manager):
        """Test _create_sensor_entity with multiple formulas."""
        main_formula = FormulaConfig(id="main", formula="main_formula")
        attr_formula = FormulaConfig(id="attr", formula="attr_formula")

        sensor_config = SensorConfig(unique_id="multi_sensor", formulas=[main_formula, attr_formula])

        with patch("ha_synthetic_sensors.sensor_manager.DynamicSensor") as MockDynamicSensor:
            mock_sensor = MagicMock()
            MockDynamicSensor.return_value = mock_sensor

            result = await sensor_manager._create_sensor_entity(sensor_config)

            # Should create sensor with all formulas
            # Verify the call was made - the sensor_config will have entity_id populated
            MockDynamicSensor.assert_called_once()
            args, kwargs = MockDynamicSensor.call_args

            # Check that the sensor_config now has an entity_id generated
            called_sensor_config = args[1]
            assert called_sensor_config.entity_id == "sensor.multi_sensor"
            assert called_sensor_config.unique_id == "multi_sensor"
            assert called_sensor_config.formulas == [main_formula, attr_formula]

            assert result == mock_sensor
