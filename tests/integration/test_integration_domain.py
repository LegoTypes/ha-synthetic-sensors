"""Tests for integration_domain parameter functionality."""

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


def test_sensor_manager_config_default_domain():
    """Test SensorManagerConfig uses default integration domain."""
    config = SensorManagerConfig()
    assert config.integration_domain == "synthetic_sensors"


def test_sensor_manager_config_custom_domain():
    """Test SensorManagerConfig accepts custom integration domain."""
    custom_domain = "span_panel"
    config = SensorManagerConfig(integration_domain=custom_domain)
    assert config.integration_domain == custom_domain


@pytest.mark.asyncio
async def test_device_name_slugification_and_entity_id_generation(mock_hass):
    """Test that device names are properly slugified and used in entity ID generation."""

    test_cases = [
        # (device_name, expected_slug, expected_entity_id)
        ("SPAN Panel Main", "span_panel_main", "sensor.span_panel_main_power_consumption"),
        ("Kitchen Counter 120V", "kitchen_counter_120v", "sensor.kitchen_counter_120v_power_consumption"),
        ("Garage-EV Charger", "garage_ev_charger", "sensor.garage_ev_charger_power_consumption"),
        ("Living Room A/C", "living_room_a_c", "sensor.living_room_a_c_power_consumption"),
        ("Test Device #1", "test_device_1", "sensor.test_device_1_power_consumption"),
        (
            "Device With    Multiple   Spaces",
            "device_with_multiple_spaces",
            "sensor.device_with_multiple_spaces_power_consumption",
        ),
    ]

    for device_name, expected_slug, expected_entity_id in test_cases:
        # Mock device registry for each test case
        with patch("ha_synthetic_sensors.sensor_manager.dr.async_get") as mock_dr_get:
            mock_device_registry = MagicMock()

            # Create fresh mock device for each test case
            test_device = MagicMock()
            test_device.name = device_name

            mock_device_registry.async_get_device.return_value = test_device
            mock_dr_get.return_value = mock_device_registry

            # Create sensor manager
            variables = {}
            name_resolver = NameResolver(mock_hass, variables)
            manager_config = SensorManagerConfig(integration_domain="span_panel")
            manager = SensorManager(
                hass=mock_hass,
                name_resolver=name_resolver,
                add_entities_callback=lambda new_entities, update_before_add=False: None,
                manager_config=manager_config,
            )

            # Test device prefix resolution (slugification)
            device_prefix = manager._resolve_device_name_prefix("test_device")
            assert device_prefix == expected_slug, (
                f"Expected '{expected_slug}', got '{device_prefix}' for device name '{device_name}'"
            )

            # Test full entity ID generation
            entity_id = manager._generate_entity_id(sensor_key="power_consumption", device_identifier="test_device")
            assert entity_id == expected_entity_id, (
                f"Expected '{expected_entity_id}', got '{entity_id}' for device name '{device_name}'"
            )


@pytest.mark.asyncio
async def test_integration_domain_isolation(mock_hass):
    """Test that devices from different integration domains are properly isolated."""

    # Create mock devices in different domains
    span_device = MagicMock()
    span_device.name = "SPAN Panel Main"

    other_device = MagicMock()
    other_device.name = "Other Integration Device"

    # Mock device registry
    with patch("ha_synthetic_sensors.sensor_manager.dr.async_get") as mock_dr_get:
        mock_device_registry = MagicMock()

        def mock_async_get_device(identifiers):
            # Check specific domain-identifier combinations
            for domain, identifier in identifiers:
                if domain == "span_panel" and identifier == "main_panel":
                    return span_device
                elif domain == "other_integration" and identifier == "main_panel":
                    return other_device
            return None

        mock_device_registry.async_get_device = mock_async_get_device
        mock_dr_get.return_value = mock_device_registry

        # Test SPAN domain can find SPAN device
        variables = {}
        name_resolver = NameResolver(mock_hass, variables)
        span_manager_config = SensorManagerConfig(integration_domain="span_panel")
        span_manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=lambda new_entities, update_before_add=False: None,
            manager_config=span_manager_config,
        )

        # Should find the SPAN device
        span_prefix = span_manager._resolve_device_name_prefix("main_panel")
        assert span_prefix == "span_panel_main"

        # Test other domain can find other device
        other_manager_config = SensorManagerConfig(integration_domain="other_integration")
        other_manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=lambda new_entities, update_before_add=False: None,
            manager_config=other_manager_config,
        )

        # Should find the other device
        other_prefix = other_manager._resolve_device_name_prefix("main_panel")
        assert other_prefix == "other_integration_device"

        # Test cross-domain isolation: SPAN manager can't find other domain's device
        span_cross_prefix = span_manager._resolve_device_name_prefix("other_device_id")
        assert span_cross_prefix is None

        # Test cross-domain isolation: Other manager can't find SPAN device
        other_cross_prefix = other_manager._resolve_device_name_prefix("span_device_id")
        assert other_cross_prefix is None


@pytest.mark.asyncio
async def test_end_to_end_sensor_creation_with_device_prefix(mock_hass):
    """Test end-to-end sensor creation with proper device prefix in entity ID."""

    # Mock device registry with a realistic SPAN device
    with patch("ha_synthetic_sensors.sensor_manager.dr.async_get") as mock_dr_get:
        mock_device_registry = MagicMock()

        # Create realistic device entry
        span_device = MagicMock()
        span_device.name = "SPAN Panel - Main"
        span_device.manufacturer = "SPAN"
        span_device.model = "Gen 2"
        span_device.sw_version = "1.2.3"
        span_device.hw_version = None

        def mock_async_get_device(identifiers):
            for domain, identifier in identifiers:
                if domain == "span_panel" and identifier == "main_panel":
                    return span_device
            return None

        mock_device_registry.async_get_device = mock_async_get_device
        mock_dr_get.return_value = mock_device_registry

        # Create sensor config
        formula = FormulaConfig(
            id="main",
            formula="{{ circuits.main_breaker.instant_power_w }}",
            metadata={
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
            },
        )

        sensor_config = SensorConfig(
            unique_id="main_power",
            name="Main Power",
            formulas=[formula],
            device_identifier="main_panel",
        )

        # Mock add entities callback
        created_sensors = []

        def mock_add_entities(new_entities, update_before_add=False):
            created_sensors.extend(new_entities)

        # Create sensor manager
        variables = {}
        name_resolver = NameResolver(mock_hass, variables)
        manager_config = SensorManagerConfig(integration_domain="span_panel")
        manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=mock_add_entities,
            manager_config=manager_config,
        )

        # Create sensor
        sensor = await manager._create_sensor_entity(sensor_config)

        # Verify entity ID follows the expected pattern: sensor.{device_prefix}_{sensor_key}
        expected_entity_id = "sensor.span_panel_main_main_power"
        assert sensor.entity_id == expected_entity_id

        # Verify device info is properly set with correct domain
        assert sensor._attr_device_info is not None
        assert sensor._attr_device_info["identifiers"] == {("span_panel", "main_panel")}
        assert sensor._attr_device_info["name"] == "SPAN Panel - Main"
        assert sensor._attr_device_info["manufacturer"] == "SPAN"


@pytest.mark.asyncio
async def test_device_resolution_wrong_domain_fails(mock_hass):
    """Test that device resolution fails when using wrong integration domain."""

    # Define test integration domain
    test_integration_domain = "span_panel"
    wrong_domain = "other_integration"

    # Mock add entities callback
    def mock_add_entities(new_entities, update_before_add=False):
        pass

    # Mock device registry
    with patch("ha_synthetic_sensors.sensor_manager.dr.async_get") as mock_dr_get:
        mock_device_registry = MagicMock()

        # Mock device that only exists in wrong domain
        mock_device = MagicMock()
        mock_device.name = "Test Device"

        def mock_async_get_device(identifiers):
            # Device exists in wrong_domain, not in test_integration_domain
            wrong_identifiers = {(wrong_domain, "device_123")}
            if identifiers == wrong_identifiers:
                return mock_device
            return None

        mock_device_registry.async_get_device = mock_async_get_device
        mock_dr_get.return_value = mock_device_registry

        # Create sensor manager with test integration domain
        variables = {}
        name_resolver = NameResolver(mock_hass, variables)
        manager_config = SensorManagerConfig(integration_domain=test_integration_domain)
        manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=mock_add_entities,
            manager_config=manager_config,
        )

        # This should fail - device not found with our domain
        device_prefix = manager._resolve_device_name_prefix("device_123")
        assert device_prefix is None


@pytest.mark.asyncio
async def test_error_message_includes_integration_domain(mock_hass):
    """Test that error messages include the integration domain for debugging."""

    test_integration_domain = "span_panel"

    # Create sensor config with non-existent device
    formula = FormulaConfig(
        id="main",
        formula="10 + 5",
        metadata={"unit_of_measurement": "W"},
    )

    sensor_config = SensorConfig(
        unique_id="test_sensor",
        name="Test Sensor",
        formulas=[formula],
        device_identifier="nonexistent_device",
    )

    # Mock add entities callback
    def mock_add_entities(new_entities, update_before_add=False):
        pass

    # Mock device registry to return None (device not found)
    with patch("ha_synthetic_sensors.sensor_manager.dr.async_get") as mock_dr_get:
        mock_device_registry = MagicMock()
        mock_device_registry.async_get_device.return_value = None
        mock_dr_get.return_value = mock_device_registry

        # Create sensor manager with custom integration domain
        variables = {}
        name_resolver = NameResolver(mock_hass, variables)
        manager_config = SensorManagerConfig(integration_domain=test_integration_domain)
        manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=mock_add_entities,
            manager_config=manager_config,
        )

        # This should raise ValueError with integration domain in message
        with pytest.raises(ValueError) as exc_info:
            await manager._create_sensor_entity(sensor_config)

        error_message = str(exc_info.value)
        assert test_integration_domain in error_message
        assert "nonexistent_device" in error_message
        assert "Device not found for identifier" in error_message


def test_integration_domain_usage_in_real_scenario():
    """Test realistic usage pattern for integration developers."""

    # This simulates how SPAN Panel integration would use it
    span_domain = "span_panel"

    # Create SensorManagerConfig as documented in Integration Guide
    manager_config = SensorManagerConfig(
        device_info=None,  # Not needed for this test
        unique_id_prefix="",
        lifecycle_managed_externally=True,
        data_provider_callback=lambda entity_id: {"value": None, "exists": False},
        integration_domain=span_domain,  # This is the key Phase 1 parameter
    )

    assert manager_config.integration_domain == span_domain

    # This shows the pattern documented in the Integration Guide works
    assert manager_config.lifecycle_managed_externally is True
    assert manager_config.unique_id_prefix == ""
    assert manager_config.integration_domain == "span_panel"
