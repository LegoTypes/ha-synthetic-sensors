"""Test device association functionality for synthetic sensors."""

from unittest.mock import MagicMock, patch

import pytest

from ha_synthetic_sensors.config_manager import FormulaConfig, SensorConfig
from ha_synthetic_sensors.name_resolver import NameResolver
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig


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
        # Test for any domain with "existing_device_001" identifier
        for _domain, identifier in identifiers:
            if identifier == "existing_device_001":
                return existing_device
        return None

    registry.async_get_device = mock_async_get_device
    return registry


@pytest.mark.asyncio
async def test_sensor_with_device_association(mock_hass):
    """Test creating a sensor with device association."""

    # Define test integration domain
    test_integration_domain = "test_integration"

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
        # Mock device entry for device lookup with proper attributes
        mock_device_entry = MagicMock()
        mock_device_entry.name = "Test Device"
        mock_device_entry.manufacturer = "Test Manufacturer"
        mock_device_entry.model = "Test Model v1"
        mock_device_entry.sw_version = "1.0.0"
        mock_device_entry.hw_version = None
        mock_device_registry_instance.async_get_device.return_value = mock_device_entry
        mock_dr_get.return_value = mock_device_registry_instance

        # Create sensor manager with proper integration domain
        variables = {}
        name_resolver = NameResolver(mock_hass, variables)
        manager_config = SensorManagerConfig(integration_domain=test_integration_domain)
        manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=mock_add_entities,
            manager_config=manager_config,
        )

        # Create the sensor entity
        sensor = await manager._create_sensor_entity(sensor_config)

        # Verify sensor has device info with correct integration domain
        assert sensor._attr_device_info is not None
        assert sensor._attr_device_info["identifiers"] == {(test_integration_domain, "test_device_001")}
        assert sensor._attr_device_info["name"] == "Test Device"
        assert sensor._attr_device_info["manufacturer"] == "Test Manufacturer"
        assert sensor._attr_device_info["model"] == "Test Model v1"
        assert sensor._attr_device_info["sw_version"] == "1.0.0"
        # Note: suggested_area is not included when using existing device info from registry


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
            # Check for any domain with "existing_device_001" identifier
            for _domain, identifier in identifiers:
                if identifier == "existing_device_001":
                    return existing_device
            return None

        mock_device_registry_instance.async_get_device = mock_async_get_device
        mock_dr_get.return_value = mock_device_registry_instance

        # Create sensor manager with proper integration domain
        test_integration_domain = "test_integration"
        variables = {}
        name_resolver = NameResolver(mock_hass, variables)
        manager_config = SensorManagerConfig(integration_domain=test_integration_domain)
        manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=mock_add_entities,
            manager_config=manager_config,
        )

        # Create the sensor entity
        sensor = await manager._create_sensor_entity(sensor_config)

        # Verify sensor has device info from existing device with correct integration domain
        assert sensor._attr_device_info is not None
        assert sensor._attr_device_info["identifiers"] == {(test_integration_domain, "existing_device_001")}
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


@pytest.mark.asyncio
async def test_sensor_with_explicit_entity_id_and_device_association(mock_hass):
    """Test creating a sensor with explicit entity_id AND device association.

    This test verifies that:
    1. Device lookup and association still happens even with explicit entity_id
    2. The explicit entity_id is used as-is (no device prefix applied)
    3. Device info is still properly populated from the device registry
    """

    # Define test integration domain
    test_integration_domain = "span"

    # Create a sensor config with BOTH explicit entity_id AND device association
    formula = FormulaConfig(
        id="main",
        formula="10 + 5",
        unit_of_measurement="W",
        device_class="power",
        state_class="measurement",
    )

    sensor_config = SensorConfig(
        unique_id="main_power",
        name="Main Power",
        formulas=[formula],
        entity_id="sensor.my_custom_main_power",  # Explicit entity_id from YAML
        device_identifier="main_panel",  # Device association still needed
        device_name="SPAN Panel Main",  # Device metadata (may be ignored if device exists)
        device_manufacturer="SPAN",
        device_model="Panel Gen 1",
        device_sw_version="1.2.3",
    )

    # Mock add entities callback
    added_entities = []

    def mock_add_entities(new_entities, update_before_add=False):
        added_entities.extend(new_entities)

    # Mock device registry - device exists in registry
    with patch("ha_synthetic_sensors.sensor_manager.dr.async_get") as mock_dr_get:
        mock_device_registry_instance = MagicMock()
        # Mock existing device entry
        mock_device_entry = MagicMock()
        mock_device_entry.name = "SPAN Panel Main"
        mock_device_entry.manufacturer = "SPAN"
        mock_device_entry.model = "Panel Gen 1"
        mock_device_entry.sw_version = "1.2.3"
        mock_device_entry.hw_version = None
        mock_device_registry_instance.async_get_device.return_value = mock_device_entry
        mock_dr_get.return_value = mock_device_registry_instance

        # Create sensor manager with SPAN integration domain
        variables = {}
        name_resolver = NameResolver(mock_hass, variables)
        manager_config = SensorManagerConfig(integration_domain=test_integration_domain)
        manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=mock_add_entities,
            manager_config=manager_config,
        )

        # Create the sensor entity
        sensor = await manager._create_sensor_entity(sensor_config)

        # Verify the EXPLICIT entity_id is used (not device prefix generated)
        assert sensor.entity_id == "sensor.my_custom_main_power"

        # Verify device info is STILL populated from device registry
        assert sensor._attr_device_info is not None
        assert sensor._attr_device_info["identifiers"] == {(test_integration_domain, "main_panel")}
        assert sensor._attr_device_info["name"] == "SPAN Panel Main"
        assert sensor._attr_device_info["manufacturer"] == "SPAN"
        assert sensor._attr_device_info["model"] == "Panel Gen 1"
        assert sensor._attr_device_info["sw_version"] == "1.2.3"

        # Verify device registry was called with correct integration domain
        mock_device_registry_instance.async_get_device.assert_called_with(identifiers={(test_integration_domain, "main_panel")})


@pytest.mark.asyncio
async def test_sensor_without_entity_id_generates_device_prefix(mock_hass):
    """Test creating a sensor WITHOUT explicit entity_id - device prefix should be generated.

    This test verifies that:
    1. Device lookup happens and device name is slugified for entity_id prefix
    2. Entity ID follows pattern: sensor.{device_prefix}_{sensor_key}
    3. Device info is properly populated
    """

    # Define test integration domain
    test_integration_domain = "span"

    # Create a sensor config WITHOUT explicit entity_id but WITH device association
    formula = FormulaConfig(
        id="main",
        formula="20 + 10",
        unit_of_measurement="A",
        device_class="current",
        state_class="measurement",
    )

    sensor_config = SensorConfig(
        unique_id="main_current",
        name="Main Current",
        formulas=[formula],
        # NO entity_id - should be generated with device prefix
        device_identifier="main_panel",  # Device association
    )

    # Mock add entities callback
    added_entities = []

    def mock_add_entities(new_entities, update_before_add=False):
        added_entities.extend(new_entities)

    # Mock device registry - device exists with complex name that needs slugification
    with patch("ha_synthetic_sensors.sensor_manager.dr.async_get") as mock_dr_get:
        mock_device_registry_instance = MagicMock()
        # Mock device with complex name that needs slugification
        mock_device_entry = MagicMock()
        mock_device_entry.name = "SPAN Panel - Main Circuit Board"  # Complex name
        mock_device_entry.manufacturer = "SPAN"
        mock_device_entry.model = "Panel Gen 2"
        mock_device_entry.sw_version = "2.0.0"
        mock_device_entry.hw_version = None
        mock_device_registry_instance.async_get_device.return_value = mock_device_entry
        mock_dr_get.return_value = mock_device_registry_instance

        # Create sensor manager
        variables = {}
        name_resolver = NameResolver(mock_hass, variables)
        manager_config = SensorManagerConfig(integration_domain=test_integration_domain)
        manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=mock_add_entities,
            manager_config=manager_config,
        )

        # Create the sensor entity
        sensor = await manager._create_sensor_entity(sensor_config)

        # Verify entity_id was GENERATED with device prefix
        # "SPAN Panel - Main Circuit Board" should become "span_panel_main_circuit_board"
        expected_entity_id = "sensor.span_panel_main_circuit_board_main_current"
        assert sensor.entity_id == expected_entity_id

        # Verify device info is properly populated
        assert sensor._attr_device_info is not None
        assert sensor._attr_device_info["identifiers"] == {(test_integration_domain, "main_panel")}
        assert sensor._attr_device_info["name"] == "SPAN Panel - Main Circuit Board"
        assert sensor._attr_device_info["manufacturer"] == "SPAN"
        assert sensor._attr_device_info["model"] == "Panel Gen 2"


@pytest.mark.asyncio
async def test_device_lookup_fails_with_explicit_entity_id(mock_hass):
    """Test that device lookup failure affects device association even with explicit entity_id.

    This test verifies that:
    1. Even with explicit entity_id, device lookup still happens
    2. If device is not found, sensor creation should still work but without device info
    3. The explicit entity_id is still used
    """

    # Define test integration domain
    test_integration_domain = "span"

    # Create a sensor config with explicit entity_id but non-existent device
    formula = FormulaConfig(id="main", formula="100", unit_of_measurement="W")

    sensor_config = SensorConfig(
        unique_id="phantom_power",
        name="Phantom Power",
        formulas=[formula],
        entity_id="sensor.my_phantom_power_sensor",  # Explicit entity_id
        device_identifier="non_existent_device",  # Device that doesn't exist
    )

    # Mock add entities callback
    added_entities = []

    def mock_add_entities(new_entities, update_before_add=False):
        added_entities.extend(new_entities)

    # Mock device registry - device NOT found
    with patch("ha_synthetic_sensors.sensor_manager.dr.async_get") as mock_dr_get:
        mock_device_registry_instance = MagicMock()
        mock_device_registry_instance.async_get_device.return_value = None  # Device not found
        mock_dr_get.return_value = mock_device_registry_instance

        # Create sensor manager
        variables = {}
        name_resolver = NameResolver(mock_hass, variables)
        manager_config = SensorManagerConfig(integration_domain=test_integration_domain)
        manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=mock_add_entities,
            manager_config=manager_config,
        )

        # Create the sensor entity
        sensor = await manager._create_sensor_entity(sensor_config)

        # Verify explicit entity_id is STILL used
        assert sensor.entity_id == "sensor.my_phantom_power_sensor"

        # Verify NO device info (since device not found and no device metadata provided)
        assert sensor._attr_device_info is None

        # Verify device registry was called with correct parameters
        mock_device_registry_instance.async_get_device.assert_called_with(
            identifiers={(test_integration_domain, "non_existent_device")}
        )
