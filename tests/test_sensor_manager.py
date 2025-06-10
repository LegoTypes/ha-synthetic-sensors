"""Tests for sensor_manager module.

This module tests the SensorManager and DynamicSensor classes that handle
the creation, updating, and removal of synthetic sensors.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

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
