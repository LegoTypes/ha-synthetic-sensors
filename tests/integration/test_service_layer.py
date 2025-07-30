"""Tests for service layer functionality and Home Assistant integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestServiceLayer:
    """Test cases for service layer functionality."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance with services."""
        hass = MagicMock()
        hass.services = MagicMock()
        hass.services.async_register = MagicMock()
        hass.services.async_remove = MagicMock()
        hass.services.has_service = MagicMock(return_value=True)
        return hass

    @pytest.fixture
    def mock_config_manager(self):
        """Create a mock configuration manager."""
        config_manager = MagicMock()
        config_manager.load_config = MagicMock(return_value=True)
        config_manager.async_reload_config = AsyncMock(return_value=True)
        config_manager.async_save_config = AsyncMock(return_value=None)
        config_manager.add_variable = MagicMock(return_value=True)
        config_manager.remove_variable = MagicMock(return_value=True)
        config_manager.get_variables = MagicMock(return_value={})
        config_manager.get_sensors = MagicMock(return_value=[])
        config_manager.get_sensor_by_name = MagicMock(return_value=None)
        config_manager.add_sensor = MagicMock()
        config_manager.update_sensor = MagicMock()
        return config_manager

    @pytest.fixture
    def mock_sensor_manager(self):
        """Create a mock sensor manager."""
        sensor_manager = MagicMock()
        sensor_manager.async_update_sensors = AsyncMock()
        sensor_manager.add_sensor = AsyncMock()
        sensor_manager.update_sensor = AsyncMock()
        sensor_manager.get_sensor_by_entity_id = MagicMock(return_value=None)
        sensor_manager.get_all_sensor_entities = MagicMock(return_value=[])
        return sensor_manager

    @pytest.fixture
    def mock_name_resolver(self):
        """Create a mock name resolver."""
        name_resolver = MagicMock()
        name_resolver.clear_mappings = MagicMock()
        name_resolver.add_entity_mapping = MagicMock()
        return name_resolver

    @pytest.fixture
    def mock_evaluator(self):
        """Create a mock enhanced evaluator."""
        evaluator = MagicMock()
        evaluator.clear_cache = MagicMock()
        evaluator.evaluate_formula = MagicMock(return_value={"success": True, "value": 42.0})
        return evaluator

    @pytest.fixture
    def service_layer(self, mock_hass, mock_config_manager, mock_sensor_manager, mock_name_resolver, mock_evaluator):
        """Create a service layer instance with mocked dependencies."""
        from ha_synthetic_sensors.service_layer import ServiceLayer

        return ServiceLayer(mock_hass, mock_config_manager, mock_sensor_manager, mock_name_resolver, mock_evaluator)

    def test_service_registration(self, service_layer, mock_hass):
        """Test that services are registered correctly."""
        # Test service registration
        import asyncio

        # Patch the problematic method reference that causes warnings
        with patch("ha_synthetic_sensors.service_layer.ServiceLayer._async_update_sensor"):
            asyncio.run(service_layer.async_setup_services())

        # Verify all expected services were registered
        expected_services = [
            "reload_config",
            "update_sensor",
            "add_variable",
            "remove_variable",
            "evaluate_formula",
            "validate_config",
            "get_sensor_info",
        ]

        assert mock_hass.services.async_register.call_count == len(expected_services)

        # Check that each service was registered with correct parameters
        registered_services = []
        for call in mock_hass.services.async_register.call_args_list:
            args, kwargs = call
            domain, service_name = args[0], args[1]
            registered_services.append(service_name)
            assert domain == "synthetic_sensors"

        for service in expected_services:
            assert service in registered_services

    def test_service_unregistration(self, service_layer, mock_hass):
        """Test that services are unregistered correctly."""
        # Test service unregistration
        import asyncio
        from unittest.mock import MagicMock

        # Make async_remove a regular MagicMock since it's synchronous
        mock_hass.services.async_remove = MagicMock()

        asyncio.run(service_layer.async_unload_services())

        # Verify services were removed
        expected_services = [
            "reload_config",
            "update_sensor",
            "add_variable",
            "remove_variable",
            "evaluate_formula",
            "validate_config",
            "get_sensor_info",
        ]

        assert mock_hass.services.async_remove.call_count == len(expected_services)

    async def test_reload_config_service(
        self, service_layer, mock_config_manager, mock_name_resolver, mock_sensor_manager, mock_evaluator
    ):
        """Test reload config service functionality."""
        # Mock service call
        call = MagicMock()
        call.data = {}

        # Test successful reload
        await service_layer._async_reload_config(call)

        # Verify operations were called
        mock_config_manager.async_reload_config.assert_called_once()
        mock_name_resolver.clear_mappings.assert_called_once()
        mock_sensor_manager.async_update_sensors.assert_called_once()
        mock_evaluator.clear_cache.assert_called_once()

    async def test_reload_config_service_failure(self, service_layer, mock_config_manager):
        """Test reload config service handles failures."""
        # Mock service call
        call = MagicMock()
        call.data = {}

        # Mock config loading failure
        mock_config_manager.async_reload_config.return_value = False

        # Test failed reload - should not raise exception
        await service_layer._async_reload_config(call)

        # Verify config loading was attempted
        mock_config_manager.async_reload_config.assert_called_once()

    def test_update_sensor_service(self, service_layer, mock_config_manager, mock_sensor_manager):
        """Test update sensor service functionality."""
        # Mock service call with sensor data (now uses entity_id)
        call = MagicMock()
        call.data = {
            "entity_id": "sensor.test_sensor_test_formula",
            "formula": "A + B",
            "unit_of_measurement": "W",
            "device_class": "power",
        }

        # Mock existing sensor
        mock_sensor = MagicMock()
        mock_sensor._async_update_sensor = AsyncMock()
        mock_sensor_manager.get_sensor_by_entity_id.return_value = mock_sensor

        # Test sensor update
        import asyncio

        asyncio.run(service_layer._async_update_sensor(call))

        # Verify sensor manager was called with entity_id
        mock_sensor_manager.get_sensor_by_entity_id.assert_called_once_with("sensor.test_sensor_test_formula")

    def test_add_variable_service(self, service_layer, mock_config_manager, mock_name_resolver):
        """Test add variable service functionality."""
        # Mock service call
        call = MagicMock()
        call.data = {
            "name": "new_variable",
            "entity_id": "sensor.test_entity",
            "description": "Test variable",
        }

        # Test variable addition
        import asyncio

        asyncio.run(service_layer._async_add_variable(call))

        # Verify name resolver was updated
        mock_name_resolver.add_entity_mapping.assert_called_once_with("new_variable", "sensor.test_entity")

    def test_remove_variable_service(self, service_layer, mock_config_manager, mock_name_resolver):
        """Test remove variable service functionality."""
        # Mock service call
        call = MagicMock()
        call.data = {"name": "variable_to_remove"}

        # Test variable removal
        import asyncio

        asyncio.run(service_layer._async_remove_variable(call))

        # Verify operations were called (specific implementation may vary)
        # This test ensures the service handler runs without error

    def test_evaluate_formula_service(self, service_layer, mock_evaluator):
        """Test evaluate formula service functionality."""
        # Mock service call
        call = MagicMock()
        call.data = {"formula": "A + B", "context": {"A": 10, "B": 20}}

        # Test formula evaluation
        import asyncio

        asyncio.run(service_layer._async_evaluate_formula(call))

        # The actual evaluation may be complex, just ensure no exceptions

    def test_validate_config_service(self, service_layer, mock_config_manager):
        """Test validate config service functionality."""
        # Mock service call
        call = MagicMock()
        call.data = {}

        # Test config validation
        import asyncio

        asyncio.run(service_layer._async_validate_config(call))

        # Ensure service runs without error

    def test_get_sensor_info_service(self, service_layer, mock_sensor_manager):
        """Test get sensor info service functionality."""
        # Mock service call (now uses entity_id)
        call = MagicMock()
        call.data = {"entity_id": "sensor.test_sensor_test_formula"}

        # Mock sensor - the service now calls get_sensor_by_entity_id()
        mock_sensor = MagicMock()
        mock_sensor._attr_unique_id = "test_sensor_test_formula"
        mock_sensor._attr_name = "Test Sensor"
        mock_sensor._attr_native_value = 42.0
        mock_sensor._attr_available = True
        mock_sensor._dependencies = {"A", "B"}
        mock_sensor._attr_extra_state_attributes = {"unit_of_measurement": "W"}
        mock_sensor._formula_config = MagicMock()
        mock_sensor._formula_config.formula = "A + B"

        mock_sensor_manager.get_sensor_by_entity_id.return_value = mock_sensor

        # Test sensor info retrieval
        import asyncio

        asyncio.run(service_layer._async_get_sensor_info(call))

        # Verify sensor manager was called with correct method
        mock_sensor_manager.get_sensor_by_entity_id.assert_called_once_with("sensor.test_sensor_test_formula")

    def test_service_error_responses(self, service_layer, mock_config_manager):
        """Test that service errors are handled gracefully."""
        # Mock service call
        call = MagicMock()
        call.data = {}

        # Mock an exception in config loading
        mock_config_manager.async_reload_config.side_effect = Exception("Test error")

        # Test that error doesn't crash service
        import asyncio

        # Should not raise exception - errors should be logged
        asyncio.run(service_layer._async_reload_config(call))

    def test_service_schema_validation(self, mock_hass):
        """Test that service schemas are properly defined."""
        from ha_synthetic_sensors.service_layer import (
            ADD_VARIABLE_SCHEMA,
            EVALUATE_FORMULA_SCHEMA,
            RELOAD_CONFIG_SCHEMA,
            REMOVE_VARIABLE_SCHEMA,
            UPDATE_SENSOR_SCHEMA,
        )

        # Test reload config schema (should be empty)
        assert RELOAD_CONFIG_SCHEMA is not None

        # Test update sensor schema has required fields
        schema_dict = UPDATE_SENSOR_SCHEMA.schema
        assert "entity_id" in str(schema_dict)  # Required field (changed from 'name')

        # Test add variable schema
        schema_dict = ADD_VARIABLE_SCHEMA.schema
        assert "name" in str(schema_dict)  # Required field
        assert "entity_id" in str(schema_dict)  # Required field

        # Test remove variable schema
        schema_dict = REMOVE_VARIABLE_SCHEMA.schema
        assert "name" in str(schema_dict)  # Required field

        # Test evaluate formula schema
        schema_dict = EVALUATE_FORMULA_SCHEMA.schema
        assert "formula" in str(schema_dict)  # Required field

    def test_service_integration_workflow(self, service_layer, mock_hass, mock_config_manager, mock_sensor_manager):
        """Test complete service workflow from setup to operations."""
        import asyncio

        # Test setup
        asyncio.run(service_layer.async_setup_services())
        assert mock_hass.services.async_register.called

        # Test reload operation
        call = MagicMock()
        call.data = {}
        asyncio.run(service_layer._async_reload_config(call))
        assert mock_config_manager.async_reload_config.called

        # Test cleanup
        asyncio.run(service_layer.async_unload_services())
        assert mock_hass.services.async_remove.called

    def test_service_domain_configuration(
        self, mock_hass, mock_config_manager, mock_sensor_manager, mock_name_resolver, mock_evaluator
    ):
        """Test service layer with custom domain."""
        from ha_synthetic_sensors.service_layer import ServiceLayer

        # Create service layer with custom domain
        custom_service_layer = ServiceLayer(
            mock_hass,
            mock_config_manager,
            mock_sensor_manager,
            mock_name_resolver,
            mock_evaluator,
            domain="custom_synthetic_sensors",
        )

        # Test setup with custom domain
        import asyncio

        asyncio.run(custom_service_layer.async_setup_services())

        # Verify services were registered with custom domain
        for call in mock_hass.services.async_register.call_args_list:
            args, kwargs = call
            domain = args[0]
            assert domain == "custom_synthetic_sensors"
