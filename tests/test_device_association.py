"""Test device association functionality for synthetic sensors."""

from unittest.mock import MagicMock, patch

import pytest

from ha_synthetic_sensors.config_manager import DOMAIN, FormulaConfig, SensorConfig
from ha_synthetic_sensors.name_resolver import NameResolver
from ha_synthetic_sensors.sensor_manager import SensorManager


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.config = MagicMock()
    hass.config.config_dir = "/config"
    hass.states = MagicMock()
    return hass


@pytest.fixture
def mock_device_registry():
    """Create a mock device registry."""
    registry = MagicMock()

    # Mock an existing device
    existing_device = MagicMock()
    existing_device.name = "Existing Device"
    existing_device.manufacturer = "Existing Manufacturer"
    existing_device.model = "Existing Model"
    existing_device.sw_version = "2.0.0"
    existing_device.hw_version = None

    def mock_async_get_device(identifiers):
        if identifiers == {(DOMAIN, "existing_device_001")}:
            return existing_device
        return None

    registry.async_get_device = mock_async_get_device
    return registry


@pytest.mark.asyncio
async def test_sensor_with_device_association(mock_hass):
    """Test creating a sensor with device association."""

    # Create a sensor config with device association
    formula = FormulaConfig(
        id="main",
        formula="10 + 5",
        unit_of_measurement="W",
        device_class="power",
        state_class="measurement",
    )

    sensor_config = SensorConfig(
        unique_id="test_sensor_with_device",
        name="Test Sensor",
        formulas=[formula],
        device_identifier="test_device_001",
        device_name="Test Device",
        device_manufacturer="Test Manufacturer",
        device_model="Test Model v1",
        device_sw_version="1.0.0",
        suggested_area="Test Area",
    )

    # Mock add entities callback
    added_entities = []

    def mock_add_entities(new_entities, update_before_add=False):
        added_entities.extend(new_entities)

    # Mock device registry in manager
    with patch("ha_synthetic_sensors.sensor_manager.dr.async_get") as mock_dr_get:
        mock_device_registry_instance = MagicMock()
        mock_device_registry_instance.async_get_device.return_value = None  # No existing device
        mock_dr_get.return_value = mock_device_registry_instance

        # Create sensor manager
        variables = {}
        name_resolver = NameResolver(mock_hass, variables)
        manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=mock_add_entities,
        )

        # Create the sensor entity
        sensor = await manager._create_sensor_entity(sensor_config)

        # Verify sensor has device info
        assert sensor._attr_device_info is not None
        assert sensor._attr_device_info["identifiers"] == {(DOMAIN, "test_device_001")}
        assert sensor._attr_device_info["name"] == "Test Device"
        assert sensor._attr_device_info["manufacturer"] == "Test Manufacturer"
        assert sensor._attr_device_info["model"] == "Test Model v1"
        assert sensor._attr_device_info["sw_version"] == "1.0.0"
        assert sensor._attr_device_info["suggested_area"] == "Test Area"


@pytest.mark.asyncio
async def test_sensor_with_existing_device(mock_hass):
    """Test creating a sensor that associates with an existing device."""

    # Create a sensor config that references an existing device
    formula = FormulaConfig(
        id="main",
        formula="20 + 10",
        unit_of_measurement="°C",
        device_class="temperature",
    )

    sensor_config = SensorConfig(
        unique_id="test_sensor_existing_device",
        name="Temperature Sensor",
        formulas=[formula],
        device_identifier="existing_device_001",
    )  # Only device_identifier needed

    # Mock add entities callback
    added_entities = []

    def mock_add_entities(new_entities, update_before_add=False):
        added_entities.extend(new_entities)

    # Mock device registry to return an existing device
    with patch("ha_synthetic_sensors.sensor_manager.dr.async_get") as mock_dr_get:
        mock_device_registry_instance = MagicMock()

        # Mock existing device
        existing_device = MagicMock()
        existing_device.name = "Existing Device"
        existing_device.manufacturer = "Existing Manufacturer"
        existing_device.model = "Existing Model"
        existing_device.sw_version = "2.0.0"
        existing_device.hw_version = None

        def mock_async_get_device(identifiers):
            if identifiers == {(DOMAIN, "existing_device_001")}:
                return existing_device
            return None

        mock_device_registry_instance.async_get_device = mock_async_get_device
        mock_dr_get.return_value = mock_device_registry_instance

        # Create sensor manager
        variables = {}
        name_resolver = NameResolver(mock_hass, variables)
        manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=mock_add_entities,
        )

        # Create the sensor entity
        sensor = await manager._create_sensor_entity(sensor_config)

        # Verify sensor has device info from existing device
        assert sensor._attr_device_info is not None
        assert sensor._attr_device_info["identifiers"] == {(DOMAIN, "existing_device_001")}
        assert sensor._attr_device_info["name"] == "Existing Device"
        assert sensor._attr_device_info["manufacturer"] == "Existing Manufacturer"
        assert sensor._attr_device_info["model"] == "Existing Model"
        assert sensor._attr_device_info["sw_version"] == "2.0.0"


@pytest.mark.asyncio
async def test_sensor_without_device_association(mock_hass):
    """Test creating a sensor without device association."""

    # Create a sensor config without device fields
    formula = FormulaConfig(id="main", formula="5 * 3", unit_of_measurement="kWh", device_class="energy")

    sensor_config = SensorConfig(
        unique_id="test_sensor_no_device",
        name="Energy Sensor",
        formulas=[formula],
        # No device_identifier or other device fields
    )

    # Mock add entities callback
    added_entities = []

    def mock_add_entities(new_entities, update_before_add=False):
        added_entities.extend(new_entities)

    # Mock device registry
    with patch("ha_synthetic_sensors.sensor_manager.dr.async_get") as mock_dr_get:
        mock_device_registry_instance = MagicMock()
        mock_dr_get.return_value = mock_device_registry_instance

        # Create sensor manager
        variables = {}
        name_resolver = NameResolver(mock_hass, variables)
        manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=mock_add_entities,
        )

        # Create the sensor entity
        sensor = await manager._create_sensor_entity(sensor_config)

        # Verify sensor has no device info
        assert sensor._attr_device_info is None
