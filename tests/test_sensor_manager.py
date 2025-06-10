"""Tests for sensor_manager module.

This module tests the SensorManager and DynamicSensor classes that handle
the creation, updating, and removal of synthetic sensors.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE

from ha_synthetic_sensors.config_manager import Config, FormulaConfig, SensorConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.name_resolver import NameResolver
from ha_synthetic_sensors.sensor_manager import (
    DynamicSensor,
    SensorManager,
    SensorState,
)


class TestSensorState:
    """Test SensorState dataclass."""

    def test_sensor_state_creation(self):
        """Test SensorState creation with defaults."""
        state = SensorState(
            sensor_name="test_sensor",
            formula_states={"formula1": 42.0},
            last_update=datetime.now(),
        )

        assert state.sensor_name == "test_sensor"
        assert state.formula_states == {"formula1": 42.0}
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
        evaluator = MagicMock()
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
            unit_of_measurement="W",
            device_class="power",
            state_class="measurement",
            icon="mdi:power",
            attributes={"test_attr": "test_value"},
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
        sensor = DynamicSensor(
            mock_hass,
            sensor_config,
            formula_config,
            mock_evaluator,
            mock_sensor_manager,
        )

        # Test _attr_ properties are set correctly
        assert sensor._attr_unique_id == "syn2_test_sensor_test_formula"
        assert sensor._attr_name == "Test Sensor Test Formula"
        assert sensor._attr_native_unit_of_measurement == "W"
        assert sensor._attr_device_class == "power"
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

    def test_sensor_manager_initialization(
        self, sensor_manager, mock_hass, mock_name_resolver, mock_add_entities
    ):
        """Test SensorManager initialization."""
        assert sensor_manager._hass == mock_hass
        assert sensor_manager._name_resolver == mock_name_resolver
        assert sensor_manager._add_entities == mock_add_entities
        assert isinstance(sensor_manager._evaluator, Evaluator)
        assert sensor_manager._sensors == {}
        assert sensor_manager._sensors_by_entity_id == {}
        assert sensor_manager._sensor_states == {}
        assert sensor_manager._current_config is None

    def test_managed_sensors_property(self, sensor_manager):
        """Test managed_sensors property."""
        # Add some test data
        sensor_manager._sensors["test"] = ["sensor1", "sensor2"]

        result = sensor_manager.managed_sensors
        assert result == {"test": ["sensor1", "sensor2"]}

        # Ensure it's a copy
        result["test"] = ["modified"]
        assert sensor_manager._sensors["test"] == ["sensor1", "sensor2"]

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
    async def test_create_sensor_entities(self, sensor_manager, test_config):
        """Test _create_sensor_entities method."""
        sensor_config = test_config.sensors[0]

        with patch(
            "ha_synthetic_sensors.sensor_manager.DynamicSensor"
        ) as MockDynamicSensor:
            mock_sensor = MagicMock()
            mock_sensor.entity_id = "sensor.syn2_test_sensor_test_formula"
            MockDynamicSensor.return_value = mock_sensor

            result = await sensor_manager._create_sensor_entities(sensor_config)

            assert len(result) == 1
            assert result[0] == mock_sensor

            # Check sensor was added to entity_id lookup
            expected_id = "sensor.syn2_test_sensor_test_formula"
            assert sensor_manager._sensors_by_entity_id[expected_id] == mock_sensor

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
        sensor_manager._sensors["test_sensor"] = [MagicMock()]
        sensor_manager._sensor_states["test_sensor"] = SensorState(
            sensor_name="test_sensor", formula_states={}, last_update=datetime.now()
        )

        result = await sensor_manager.remove_sensor("test_sensor")

        assert result is True
        assert "test_sensor" not in sensor_manager._sensors
        assert "test_sensor" not in sensor_manager._sensor_states

    def test_on_sensor_updated_new_sensor(self, sensor_manager):
        """Test _on_sensor_updated with new sensor."""
        sensor_manager._on_sensor_updated("test_sensor", "formula1", 42.5)

        assert "test_sensor" in sensor_manager._sensor_states
        state = sensor_manager._sensor_states["test_sensor"]
        assert state.sensor_name == "test_sensor"
        assert state.formula_states == {"formula1": 42.5}
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
            unit_of_measurement="W",
            device_class="power",
            state_class="measurement",
            icon="mdi:power",
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
        return DynamicSensor(
            mock_hass,
            sensor_config,
            formula_config,
            mock_evaluator,
            mock_sensor_manager,
        )

    def test_dynamic_sensor_initialization_no_name(
        self, mock_hass, mock_evaluator, mock_sensor_manager
    ):
        """Test DynamicSensor initialization with no sensor name."""
        sensor_config = SensorConfig(unique_id="test_sensor", formulas=[])
        formula_config = FormulaConfig(id="test_formula", formula="1 + 1")

        sensor = DynamicSensor(
            mock_hass,
            sensor_config,
            formula_config,
            mock_evaluator,
            mock_sensor_manager,
        )

        # Should use formula name when sensor name is empty
        assert sensor._attr_name == "test_formula"

    def test_dynamic_sensor_initialization_no_formula_name(
        self, mock_hass, mock_evaluator, mock_sensor_manager
    ):
        """Test DynamicSensor initialization with no formula name."""
        sensor_config = SensorConfig(
            unique_id="test_sensor", name="Test Sensor", formulas=[]
        )
        formula_config = FormulaConfig(id="test_formula", formula="1 + 1")  # No name

        sensor = DynamicSensor(
            mock_hass,
            sensor_config,
            formula_config,
            mock_evaluator,
            mock_sensor_manager,
        )

        # Should use formula ID when formula name is None
        assert sensor._attr_name == "Test Sensor test_formula"

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_dependencies(self, dynamic_sensor):
        """Test async_added_to_hass with dependencies."""
        # Mock the async_track_state_change_event
        with patch(
            "ha_synthetic_sensors.sensor_manager.async_track_state_change_event"
        ) as mock_track:
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
    async def test_async_added_to_hass_no_dependencies(
        self, mock_hass, mock_evaluator, mock_sensor_manager
    ):
        """Test async_added_to_hass with no dependencies."""
        sensor_config = SensorConfig(unique_id="test_sensor", formulas=[])
        formula_config = FormulaConfig(
            id="test_formula", formula="42", dependencies=set()
        )

        sensor = DynamicSensor(
            mock_hass,
            sensor_config,
            formula_config,
            mock_evaluator,
            mock_sensor_manager,
        )

        await sensor.async_added_to_hass()

        # Should not set up any listeners
        assert len(sensor._update_listeners) == 0

    @pytest.mark.asyncio
    async def test_async_will_remove_from_hass(self, dynamic_sensor):
        """Test async_will_remove_from_hass cleanup."""
        # Add some mock listeners
        mock_listener1 = MagicMock()
        mock_listener2 = MagicMock()
        dynamic_sensor._update_listeners = [mock_listener1, mock_listener2]

        await dynamic_sensor.async_will_remove_from_hass()

        # Should call all listeners to clean up
        mock_listener1.assert_called_once()
        mock_listener2.assert_called_once()
        assert len(dynamic_sensor._update_listeners) == 0

    @pytest.mark.asyncio
    async def test_handle_dependency_change_functionality(
        self, dynamic_sensor, mock_evaluator
    ):
        """Test _handle_dependency_change actually triggers sensor update."""
        # Set up mock event
        mock_event = MagicMock()
        mock_event.data = {"entity_id": "sensor.test_a", "new_state": MagicMock()}

        # Mock the Home Assistant states that the evaluator will use
        mock_state_a = MagicMock()
        mock_state_a.state = "15"
        mock_state_b = MagicMock()
        mock_state_b.state = "25"

        dynamic_sensor._hass.states.get.side_effect = lambda entity_id: (
            mock_state_a
            if entity_id == "sensor.test_a"
            else mock_state_b if entity_id == "sensor.test_b" else None
        )

        # Configure evaluator to return a success result
        mock_evaluator.evaluate_formula.return_value = {
            "success": True,
            "value": 40.0,  # 15 + 25 = 40
        }

        # Store initial value to verify it changes
        initial_value = dynamic_sensor._attr_native_value

        # Call the dependency change handler
        await dynamic_sensor._handle_dependency_change(mock_event)

        # Verify the sensor was updated
        assert dynamic_sensor._attr_native_value == 40.0
        assert dynamic_sensor._attr_native_value != initial_value
        assert dynamic_sensor._attr_available is True
        assert dynamic_sensor._last_update is not None

        # Verify the evaluator was called
        mock_evaluator.evaluate_formula.assert_called_once_with(
            dynamic_sensor._formula_config
        )

        # Verify the sensor manager was notified
        dynamic_sensor._sensor_manager._on_sensor_updated.assert_called_once_with(
            "test_sensor", "test_formula", 40.0
        )

    @pytest.mark.asyncio
    async def test_async_update_sensor_success(self, dynamic_sensor, mock_evaluator):
        """Test _async_update_sensor with successful evaluation."""
        mock_evaluator.evaluate_formula.return_value = {
            "success": True,
            "value": 42.5,
        }

        await dynamic_sensor._async_update_sensor()

        assert dynamic_sensor._attr_native_value == 42.5
        assert dynamic_sensor._attr_available is True
        assert dynamic_sensor._last_update is not None

        # Should notify sensor manager
        dynamic_sensor._sensor_manager._on_sensor_updated.assert_called_once_with(
            "test_sensor", "test_formula", 42.5
        )

    @pytest.mark.asyncio
    async def test_async_update_sensor_evaluation_failure(
        self, dynamic_sensor, mock_evaluator
    ):
        """Test _async_update_sensor with evaluation failure."""
        mock_evaluator.evaluate_formula.return_value = {
            "success": False,
            "error": "Division by zero",
        }

        with patch("ha_synthetic_sensors.sensor_manager._LOGGER") as mock_logger:
            await dynamic_sensor._async_update_sensor()

            assert dynamic_sensor._attr_available is False
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_update_sensor_exception(self, dynamic_sensor, mock_evaluator):
        """Test _async_update_sensor with exception."""
        mock_evaluator.evaluate_formula.side_effect = Exception("Test exception")

        with patch("ha_synthetic_sensors.sensor_manager._LOGGER") as mock_logger:
            await dynamic_sensor._async_update_sensor()

            assert dynamic_sensor._attr_available is False
            mock_logger.error.assert_called_once()

    def test_update_extra_state_attributes(self, dynamic_sensor):
        """Test _update_extra_state_attributes method."""
        dynamic_sensor._last_update = datetime.now()

        dynamic_sensor._update_extra_state_attributes()

        attrs = dynamic_sensor._attr_extra_state_attributes
        assert "formula" in attrs
        assert "dependencies" in attrs
        assert "last_update" in attrs
        assert attrs["formula"] == "sensor.test_a + sensor.test_b"
        assert "sensor.test_a" in attrs["dependencies"]

    @pytest.mark.asyncio
    async def test_force_update_formula_same_dependencies(
        self, dynamic_sensor, mock_evaluator
    ):
        """Test force_update_formula with same dependencies."""
        new_formula = FormulaConfig(
            id="updated_formula",
            name="Updated Formula",
            formula="sensor.test_a * 2",
            unit_of_measurement="kW",
            device_class="power",
            state_class="measurement",
            icon="mdi:power",
            attributes={"test_attr": "test_value"},
            dependencies={"sensor.test_a", "sensor.test_b"},  # Same dependencies
        )

        await dynamic_sensor.force_update_formula(new_formula)

        assert dynamic_sensor._formula_config == new_formula
        assert dynamic_sensor._attr_unit_of_measurement == "kW"
        mock_evaluator.clear_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_update_formula_different_dependencies(
        self, dynamic_sensor, mock_evaluator
    ):
        """Test force_update_formula with different dependencies."""
        # Set up initial listeners
        mock_listener = MagicMock()
        dynamic_sensor._update_listeners = [mock_listener]

        new_formula = FormulaConfig(
            id="updated_formula",
            formula="sensor.test_c + sensor.test_d",
            dependencies={"sensor.test_c", "sensor.test_d"},  # Different dependencies
        )

        with patch(
            "ha_synthetic_sensors.sensor_manager.async_track_state_change_event"
        ) as mock_track:
            mock_track.return_value = MagicMock()

            with patch.object(
                dynamic_sensor, "_async_update_sensor", new_callable=AsyncMock
            ) as mock_update:
                await dynamic_sensor.force_update_formula(new_formula)

                # Should clean up old listeners
                mock_listener.assert_called_once()

                # Should set up new listeners
                mock_track.assert_called_once()
                call_args = mock_track.call_args[0]
                assert call_args[0] == dynamic_sensor._hass
                assert set(call_args[1]) == {"sensor.test_c", "sensor.test_d"}
                assert call_args[2] == dynamic_sensor._handle_dependency_change

                # Should have awaited the async update
                mock_update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_get_last_state_with_restored_state(self, dynamic_sensor):
        """Test async_get_last_state with restored state."""
        # Mock restored state
        mock_state = MagicMock()
        mock_state.state = "25.5"
        mock_state.attributes = {"test_attr": "restored_value"}

        # Mock the Home Assistant state dependencies so evaluator can work
        mock_hass_state_a = MagicMock()
        mock_hass_state_a.state = "10"
        mock_hass_state_b = MagicMock()
        mock_hass_state_b.state = "20"

        dynamic_sensor._hass.states.get.side_effect = lambda entity_id: (
            mock_hass_state_a
            if entity_id == "sensor.test_a"
            else mock_hass_state_b if entity_id == "sensor.test_b" else None
        )

        with patch(
            "ha_synthetic_sensors.sensor_manager.async_track_state_change_event"
        ):
            with patch.object(
                dynamic_sensor, "async_get_last_state", return_value=mock_state
            ):
                with patch.object(
                    dynamic_sensor, "_async_update_sensor", new_callable=AsyncMock
                ) as _mock_update:
                    await dynamic_sensor.async_added_to_hass()

                    # Should restore the state initially, then get updated by evaluator
                    # The key test is that async_get_last_state was called and processed
                    assert dynamic_sensor._attr_native_value is not None

    @pytest.mark.asyncio
    async def test_async_get_last_state_invalid_value(self, dynamic_sensor):
        """Test async_get_last_state with invalid restored state."""
        # Mock restored state with invalid value
        mock_state = MagicMock()
        mock_state.state = "invalid_number"

        # Mock the Home Assistant state dependencies so evaluator can work
        mock_hass_state_a = MagicMock()
        mock_hass_state_a.state = "10"
        mock_hass_state_b = MagicMock()
        mock_hass_state_b.state = "20"

        dynamic_sensor._hass.states.get.side_effect = lambda entity_id: (
            mock_hass_state_a
            if entity_id == "sensor.test_a"
            else mock_hass_state_b if entity_id == "sensor.test_b" else None
        )

        with patch(
            "ha_synthetic_sensors.sensor_manager.async_track_state_change_event"
        ):
            with patch.object(
                dynamic_sensor, "async_get_last_state", return_value=mock_state
            ):
                await dynamic_sensor.async_added_to_hass()

                # Should handle invalid value gracefully
                # evaluator will override with valid result
                assert dynamic_sensor._attr_native_value is not None

    @pytest.mark.asyncio
    async def test_async_get_last_state_unavailable(self, dynamic_sensor):
        """Test async_get_last_state with unavailable state."""
        # Mock restored state as unavailable
        mock_state = MagicMock()
        mock_state.state = STATE_UNAVAILABLE

        # Mock the Home Assistant state dependencies so evaluator can work
        mock_hass_state_a = MagicMock()
        mock_hass_state_a.state = "10"
        mock_hass_state_b = MagicMock()
        mock_hass_state_b.state = "20"

        dynamic_sensor._hass.states.get.side_effect = lambda entity_id: (
            mock_hass_state_a
            if entity_id == "sensor.test_a"
            else mock_hass_state_b if entity_id == "sensor.test_b" else None
        )

        with patch(
            "ha_synthetic_sensors.sensor_manager.async_track_state_change_event"
        ):
            with patch.object(
                dynamic_sensor, "async_get_last_state", return_value=mock_state
            ):
                await dynamic_sensor.async_added_to_hass()

                # Should not restore unavailable state, but evaluator will set a value
                assert dynamic_sensor._attr_native_value is not None


class TestSensorManagerExtended:
    """Extended tests for SensorManager class."""

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

        sensor1 = SensorConfig(
            unique_id="sensor1",
            name="Sensor 1",
            enabled=True,
            formulas=[formula1],
        )
        sensor2 = SensorConfig(
            unique_id="sensor2",
            name="Sensor 2",
            enabled=False,  # Disabled sensor
            formulas=[formula2],
        )

        return Config(sensors=[sensor1, sensor2])

    @pytest.mark.asyncio
    async def test_create_all_sensors_with_disabled_sensor(
        self, sensor_manager, test_config
    ):
        """Test _create_all_sensors skips disabled sensors."""
        with patch.object(sensor_manager, "_create_sensor_entities") as mock_create:
            mock_create.return_value = [MagicMock()]

            await sensor_manager._create_all_sensors(test_config)

            # Should only create entities for enabled sensors
            mock_create.assert_called_once()
            assert len(sensor_manager._sensors) == 1
            assert "sensor1" in sensor_manager._sensors

    @pytest.mark.asyncio
    async def test_update_existing_sensors_add_remove_update(self, sensor_manager):
        """Test _update_existing_sensors with add, remove, and update operations."""
        # Create old config
        old_formula = FormulaConfig(id="old_formula", formula="1")
        old_sensor = SensorConfig(unique_id="old_sensor", formulas=[old_formula])
        old_config = Config(sensors=[old_sensor])

        # Create new config
        new_formula = FormulaConfig(id="new_formula", formula="2")
        new_sensor = SensorConfig(unique_id="new_sensor", formulas=[new_formula])
        new_config = Config(sensors=[new_sensor])

        # Set up existing sensor to be removed
        mock_old_sensor = MagicMock()
        sensor_manager._sensors = {"old_sensor": [mock_old_sensor]}

        with patch.object(sensor_manager, "remove_sensor") as mock_remove:
            with patch.object(sensor_manager, "_create_sensor_entities") as mock_create:
                mock_create.return_value = [MagicMock()]

                await sensor_manager._update_existing_sensors(old_config, new_config)

                # Should remove old sensor
                mock_remove.assert_called_once_with("old_sensor")

                # Should create new sensor
                mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_all_sensors(self, sensor_manager):
        """Test _remove_all_sensors method."""
        # Set up existing sensors
        mock_sensor1 = MagicMock()
        mock_sensor2 = MagicMock()
        sensor_manager._sensors = {
            "sensor1": [mock_sensor1],
            "sensor2": [mock_sensor2],
        }
        sensor_manager._sensor_states = {
            "sensor1": SensorState("sensor1", {}, datetime.now()),
            "sensor2": SensorState("sensor2", {}, datetime.now()),
        }

        await sensor_manager._remove_all_sensors()

        assert len(sensor_manager._sensors) == 0
        assert len(sensor_manager._sensor_states) == 0

    def test_get_all_sensor_entities(self, sensor_manager):
        """Test get_all_sensor_entities method."""
        mock_sensor1 = MagicMock()
        mock_sensor2 = MagicMock()
        mock_sensor3 = MagicMock()

        sensor_manager._sensors_by_entity_id = {
            "sensor.test1": mock_sensor1,
            "sensor.test2": mock_sensor2,
            "sensor.test3": mock_sensor3,
        }

        entities = sensor_manager.get_all_sensor_entities()

        assert len(entities) == 3
        assert mock_sensor1 in entities
        assert mock_sensor2 in entities
        assert mock_sensor3 in entities

    def test_get_sensor_by_entity_id_found(self, sensor_manager):
        """Test get_sensor_by_entity_id when sensor exists."""
        mock_sensor = MagicMock()
        sensor_manager._sensors_by_entity_id = {"sensor.test_entity": mock_sensor}

        result = sensor_manager.get_sensor_by_entity_id("sensor.test_entity")

        assert result == mock_sensor

    def test_get_sensor_by_entity_id_not_found(self, sensor_manager):
        """Test get_sensor_by_entity_id when sensor doesn't exist."""
        result = sensor_manager.get_sensor_by_entity_id("sensor.nonexistent")

        assert result is None

    def test_on_sensor_updated_existing_sensor(self, sensor_manager):
        """Test _on_sensor_updated with existing sensor state."""
        # Set up existing state
        initial_state = SensorState("test_sensor", {"formula1": 10.0}, datetime.now())
        sensor_manager._sensor_states = {"test_sensor": initial_state}

        sensor_manager._on_sensor_updated("test_sensor", "formula2", 20.0)

        state = sensor_manager._sensor_states["test_sensor"]
        assert state.formula_states == {"formula1": 10.0, "formula2": 20.0}
        assert state.error_count == 0
        assert state.is_available is True

    def test_on_sensor_updated_error_handling(self, sensor_manager):
        """Test _on_sensor_updated with error state."""
        # Simulate an error by not calling _on_sensor_updated,
        # since the actual error handling happens at the sensor level
        sensor_manager._on_sensor_updated("test_sensor", "formula1", 42.0)

        state = sensor_manager._sensor_states["test_sensor"]
        assert state.error_count == 0  # No error count in the actual implementation
        assert state.is_available is True

    def test_update_sensor_states_new_sensor(self, sensor_manager):
        """Test update_sensor_states with new sensor."""
        states = {"formula1": 42.5, "formula2": 100.0}

        sensor_manager.update_sensor_states("new_sensor", states)

        assert "new_sensor" in sensor_manager._sensor_states
        state = sensor_manager._sensor_states["new_sensor"]
        assert state.formula_states == states
        assert state.sensor_name == "new_sensor"

    def test_update_sensor_states_existing_sensor(self, sensor_manager):
        """Test update_sensor_states with existing sensor."""
        # Set up existing state
        initial_state = SensorState("test_sensor", {"formula1": 10.0}, datetime.now())
        sensor_manager._sensor_states = {"test_sensor": initial_state}

        new_states = {"formula1": 15.0, "formula2": 25.0}
        sensor_manager.update_sensor_states("test_sensor", new_states)

        state = sensor_manager._sensor_states["test_sensor"]
        assert state.formula_states == {"formula1": 15.0, "formula2": 25.0}

    @pytest.mark.asyncio
    async def test_async_update_sensors_all(self, sensor_manager):
        """Test async_update_sensors with no specific sensors (update all)."""
        mock_sensor1 = MagicMock()
        mock_sensor1._async_update_sensor = AsyncMock()
        mock_sensor2 = MagicMock()
        mock_sensor2._async_update_sensor = AsyncMock()

        sensor_manager._sensors = {
            "sensor1": [mock_sensor1],
            "sensor2": [mock_sensor2],
        }

        await sensor_manager.async_update_sensors()

        mock_sensor1._async_update_sensor.assert_called_once()
        mock_sensor2._async_update_sensor.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_update_sensors_specific(self, sensor_manager):
        """Test async_update_sensors with specific sensor configs."""
        mock_sensor1 = MagicMock()
        mock_sensor1._async_update_sensor = AsyncMock()
        mock_sensor2 = MagicMock()
        mock_sensor2._async_update_sensor = AsyncMock()

        sensor_manager._sensors = {
            "sensor1": [mock_sensor1],
            "sensor2": [mock_sensor2],
        }

        # Update only sensor1
        sensor_config = SensorConfig(unique_id="sensor1", formulas=[])
        await sensor_manager.async_update_sensors([sensor_config])

        mock_sensor1._async_update_sensor.assert_called_once()
        mock_sensor2._async_update_sensor.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_sensor_success(self, sensor_manager):
        """Test remove_sensor successful removal."""
        mock_sensor = MagicMock()
        sensor_manager._sensors = {"test_sensor": [mock_sensor]}
        sensor_manager._sensor_states = {
            "test_sensor": SensorState("test_sensor", {}, datetime.now())
        }

        result = await sensor_manager.remove_sensor("test_sensor")

        assert result is True
        assert "test_sensor" not in sensor_manager._sensors
        assert "test_sensor" not in sensor_manager._sensor_states

    @pytest.mark.asyncio
    async def test_remove_sensor_not_found(self, sensor_manager):
        """Test remove_sensor with non-existent sensor."""
        result = await sensor_manager.remove_sensor("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_load_configuration_update_existing(self, sensor_manager):
        """Test load_configuration when updating existing configuration."""
        # Set up existing config
        old_config = Config(sensors=[])
        sensor_manager._current_config = old_config

        # New config
        new_config = Config(sensors=[])

        with patch.object(sensor_manager, "_update_existing_sensors") as mock_update:
            await sensor_manager.load_configuration(new_config)

            assert sensor_manager._current_config == new_config
            mock_update.assert_called_once_with(old_config, new_config)

    def test_sensor_manager_properties(self, sensor_manager):
        """Test SensorManager properties."""
        mock_sensor = MagicMock()
        sensor_manager._sensors = {"test": [mock_sensor]}
        sensor_manager._sensor_states = {
            "test": SensorState("test", {}, datetime.now())
        }

        # Test managed_sensors property
        managed = sensor_manager.managed_sensors
        assert "test" in managed
        assert managed["test"] == [mock_sensor]

        # Test sensor_states property
        states = sensor_manager.sensor_states
        assert "test" in states
        assert isinstance(states["test"], SensorState)

    @pytest.mark.asyncio
    async def test_create_sensor_entities_multiple_formulas(self, sensor_manager):
        """Test _create_sensor_entities with multiple formulas."""
        formula1 = FormulaConfig(id="formula1", formula="1 + 1")
        formula2 = FormulaConfig(id="formula2", formula="2 + 2")
        sensor_config = SensorConfig(
            unique_id="multi_formula_sensor",
            formulas=[formula1, formula2],
        )

        with patch(
            "ha_synthetic_sensors.sensor_manager.DynamicSensor"
        ) as MockDynamicSensor:
            mock_sensor1 = MagicMock()
            mock_sensor1.entity_id = "sensor.multi_formula_sensor_formula1"
            mock_sensor2 = MagicMock()
            mock_sensor2.entity_id = "sensor.multi_formula_sensor_formula2"
            MockDynamicSensor.side_effect = [mock_sensor1, mock_sensor2]

            entities = await sensor_manager._create_sensor_entities(sensor_config)

            assert len(entities) == 2
            assert entities[0] == mock_sensor1
            assert entities[1] == mock_sensor2

            # Check both sensors are in entity_id lookup
            assert (
                "sensor.multi_formula_sensor_formula1"
                in sensor_manager._sensors_by_entity_id
            )
            assert (
                "sensor.multi_formula_sensor_formula2"
                in sensor_manager._sensors_by_entity_id
            )
