"""Tests for synthetic sensors integration components and workflow."""

from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ha_synthetic_sensors.exceptions import IntegrationNotInitializedError
from ha_synthetic_sensors.integration import (
    SyntheticSensorsIntegration,
    async_reload_integration,
    async_setup_integration,
    async_unload_integration,
    get_example_config,
    get_integration,
    validate_yaml_content,
)
from ha_synthetic_sensors.types import ContextValue


class TestSyntheticSensorsIntegration:
    """Test SyntheticSensorsIntegration class."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.config = MagicMock()
        hass.config.config_dir = "/config"
        return hass

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        entry.data = {"name": "test_integration"}
        return entry

    @pytest.fixture
    def mock_add_entities(self):
        """Create a mock add entities callback."""
        return MagicMock()

    @pytest.fixture
    def integration(self, mock_hass, mock_config_entry):
        """Create a SyntheticSensorsIntegration instance."""
        return SyntheticSensorsIntegration(mock_hass, mock_config_entry)

    def test_initialization(self, integration, mock_hass, mock_config_entry):
        """Test SyntheticSensorsIntegration initialization."""
        assert integration._hass == mock_hass
        assert integration._config_entry == mock_config_entry
        assert integration._sensor_manager is None
        assert integration._service_manager is None
        assert integration._initialized is False
        assert integration._auto_config_path is None

    def test_properties(self, integration):
        """Test integration properties."""
        # Test is_initialized property
        assert integration.is_initialized is False
        integration._initialized = True
        assert integration.is_initialized is True

        # Test config_manager property
        assert integration.config_manager is not None

        # Test sensor_manager property
        assert integration.sensor_manager is None
        mock_manager = MagicMock()
        integration._sensor_manager = mock_manager
        assert integration.sensor_manager == mock_manager

        # Test service_manager property
        assert integration.service_manager is None
        mock_service = MagicMock()
        integration._service_manager = mock_service
        assert integration.service_manager == mock_service

    @pytest.mark.asyncio
    async def test_async_setup_success(self, integration, mock_add_entities):
        """Test successful async_setup."""
        with patch.object(integration, "_check_auto_configuration") as mock_check:
            mock_check.return_value = AsyncMock()

            with patch("ha_synthetic_sensors.integration.SensorManager") as MockSensorManager:
                mock_sensor_manager = MagicMock()
                MockSensorManager.return_value = mock_sensor_manager

                with patch("ha_synthetic_sensors.integration.ServiceLayer") as MockServiceLayer:
                    mock_service_layer = MagicMock()
                    mock_service_layer.async_setup_services = AsyncMock()
                    MockServiceLayer.return_value = mock_service_layer

                    with patch("ha_synthetic_sensors.evaluator.Evaluator") as MockEvaluator:
                        mock_evaluator = MagicMock()
                        MockEvaluator.return_value = mock_evaluator

                        result = await integration.async_setup(mock_add_entities)

                        assert result is True
                        assert integration._initialized is True
                        assert integration._sensor_manager == mock_sensor_manager
                        assert integration._service_manager == mock_service_layer

                        # Check services were set up
                        mock_service_layer.async_setup_services.assert_called_once()

                        # Check auto-configuration was checked
                        mock_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_setup_failure(self, integration, mock_add_entities):
        """Test async_setup with failure."""
        with patch("ha_synthetic_sensors.integration.SensorManager") as MockSensorManager:
            MockSensorManager.side_effect = Exception("Setup failed")

            with patch.object(integration, "_cleanup") as mock_cleanup:
                mock_cleanup.return_value = AsyncMock(return_value=True)

                with pytest.raises((RuntimeError, Exception)):
                    await integration.async_setup(mock_add_entities)

                assert integration._initialized is False
                mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_unload(self, integration):
        """Test async_unload."""
        with patch.object(integration, "_cleanup") as mock_cleanup:
            mock_cleanup.return_value = True

            result = await integration.async_unload()

            assert result is True
            mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_reload(self, integration, mock_add_entities):
        """Test async_reload."""
        with patch.object(integration, "_cleanup") as mock_cleanup:
            mock_cleanup.return_value = AsyncMock()

            with patch.object(integration, "async_setup") as mock_setup:
                mock_setup.return_value = True

                result = await integration.async_reload(mock_add_entities)

                assert result is True
                mock_cleanup.assert_called_once()
                mock_setup.assert_called_once_with(mock_add_entities)

    @pytest.mark.asyncio
    async def test_load_configuration_file_success(self, integration):
        """Test load_configuration_file with success."""
        integration._initialized = True
        mock_sensor_manager = MagicMock()
        mock_sensor_manager.load_configuration = AsyncMock()
        integration._sensor_manager = mock_sensor_manager

        with patch.object(integration._config_manager, "async_load_from_file") as mock_load:
            mock_config = MagicMock()
            mock_load.return_value = mock_config

            result = await integration.load_configuration_file("/test/config.yaml")

            assert result is True
            mock_load.assert_called_once_with("/test/config.yaml")
            mock_sensor_manager.load_configuration.assert_called_once_with(mock_config)

    @pytest.mark.asyncio
    async def test_load_configuration_file_not_initialized(self, integration):
        """Test load_configuration_file when not initialized."""
        with pytest.raises(IntegrationNotInitializedError):
            await integration.load_configuration_file("/test/config.yaml")

    @pytest.mark.asyncio
    async def test_load_configuration_file_no_sensor_manager(self, integration):
        """Test load_configuration_file with no sensor manager."""
        integration._initialized = True
        integration._sensor_manager = None

        with pytest.raises(IntegrationNotInitializedError):
            await integration.load_configuration_file("/test/config.yaml")

    @pytest.mark.asyncio
    async def test_load_configuration_file_failure(self, integration):
        """Test load_configuration_file with failure."""
        integration._initialized = True
        mock_sensor_manager = MagicMock()
        integration._sensor_manager = mock_sensor_manager

        with patch.object(integration._config_manager, "async_load_from_file") as mock_load:
            mock_load.side_effect = Exception("Load failed")

            result = await integration.load_configuration_file("/test/config.yaml")

            assert result is False

    @pytest.mark.asyncio
    async def test_load_configuration_content_success(self, integration):
        """Test load_configuration_content with success."""
        integration._initialized = True
        mock_sensor_manager = MagicMock()
        mock_sensor_manager.load_configuration = AsyncMock()
        integration._sensor_manager = mock_sensor_manager

        yaml_content = "sensors: []"

        with patch.object(integration._config_manager, "load_from_yaml") as mock_load:
            mock_config = MagicMock()
            mock_load.return_value = mock_config

            result = await integration.load_configuration_content(yaml_content)

            assert result is True
            mock_load.assert_called_once_with(yaml_content)
            mock_sensor_manager.load_configuration.assert_called_once_with(mock_config)

    @pytest.mark.asyncio
    async def test_load_configuration_content_failure(self, integration):
        """Test load_configuration_content with failure."""
        integration._initialized = True
        mock_sensor_manager = MagicMock()
        integration._sensor_manager = mock_sensor_manager

        yaml_content = "invalid: yaml: content:"

        with patch.object(integration._config_manager, "load_from_yaml") as mock_load:
            mock_load.side_effect = Exception("Parse failed")

            result = await integration.load_configuration_content(yaml_content)

            assert result is False

    @pytest.mark.asyncio
    async def test_check_auto_configuration_found(self, integration, mock_hass):
        """Test _check_auto_configuration when file is found."""
        mock_hass.config.config_dir = "/config"

        with patch("pathlib.Path.exists") as mock_exists, patch("pathlib.Path.is_file") as mock_is_file:
            mock_exists.side_effect = [True, False, False, False]
            mock_is_file.return_value = True

            with patch.object(integration, "load_configuration_file") as mock_load:
                mock_load.return_value = True

                await integration._check_auto_configuration()

                assert integration._auto_config_path == Path("/config/synthetic_sensors_config.yaml")
                mock_load.assert_called_once_with("/config/synthetic_sensors_config.yaml")

    @pytest.mark.asyncio
    async def test_check_auto_configuration_not_found(self, integration, mock_hass):
        """Test _check_auto_configuration when no file is found."""
        mock_hass.config.config_dir = "/config"

        with patch("pathlib.Path.exists") as mock_exists:
            mock_exists.return_value = False

            await integration._check_auto_configuration()

            assert integration._auto_config_path is None

    @pytest.mark.asyncio
    async def test_check_auto_configuration_load_failure(self, integration, mock_hass):
        """Test _check_auto_configuration when file is found but load fails."""
        mock_hass.config.config_dir = "/config"

        with patch("pathlib.Path.exists") as mock_exists, patch("pathlib.Path.is_file") as mock_is_file:
            mock_exists.side_effect = [True, False, False, False]
            mock_is_file.return_value = True

            with patch.object(integration, "load_configuration_file") as mock_load:
                mock_load.side_effect = Exception("Load failed")

                await integration._check_auto_configuration()

                # Path is still set even when loading fails (as it continues
                # to next file)
                assert integration._auto_config_path == Path("/config/synthetic_sensors_config.yaml")

    @pytest.mark.asyncio
    async def test_cleanup_success(self, integration):
        """Test _cleanup method with success."""
        mock_service_manager = MagicMock()
        mock_service_manager.async_unregister_services = AsyncMock()
        integration._service_manager = mock_service_manager

        mock_sensor_manager = MagicMock()
        mock_sensor_manager._remove_all_sensors = AsyncMock()
        integration._sensor_manager = mock_sensor_manager

        result = await integration._cleanup()

        assert result is True
        mock_service_manager.async_unregister_services.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_with_failure(self, integration):
        """Test _cleanup method with failure."""
        mock_service_manager = MagicMock()
        mock_service_manager.async_unload_services = AsyncMock(side_effect=Exception("Unload failed"))
        integration._service_manager = mock_service_manager

        result = await integration._cleanup()

        assert result is False

    @pytest.mark.asyncio
    async def test_async_cleanup_detailed_success(self, integration):
        """Test async_cleanup_detailed method with success."""
        mock_service_manager = MagicMock()
        mock_service_manager.async_unregister_services = AsyncMock()
        integration._service_manager = mock_service_manager

        mock_sensor_manager = MagicMock()
        mock_sensor_manager._remove_all_sensors = AsyncMock()
        integration._sensor_manager = mock_sensor_manager

        result = await integration.async_cleanup_detailed()

        assert result["success"] is True
        assert result["services_unregistered"] is True
        assert result["sensors_removed"] is True
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_async_cleanup_detailed_with_errors(self, integration):
        """Test async_cleanup_detailed method with errors."""
        mock_service_manager = MagicMock()
        mock_service_manager.async_unload_services = AsyncMock(side_effect=Exception("Service error"))
        integration._service_manager = mock_service_manager

        result = await integration.async_cleanup_detailed()

        assert result["success"] is False
        assert result["services_unregistered"] is False
        assert len(result["errors"]) > 0

    def test_get_integration_status(self, integration):
        """Test get_integration_status method."""
        integration._initialized = True
        integration._auto_config_path = Path("/config/test.yaml")

        mock_sensor_manager = MagicMock()
        mock_sensor_manager.get_all_sensor_entities.return_value = [1, 2, 3, 4, 5]
        integration._sensor_manager = mock_sensor_manager

        # Set service manager to make services_registered True
        mock_service_manager = MagicMock()
        integration._service_manager = mock_service_manager

        result = integration.get_integration_status()

        assert result["initialized"] is True
        assert result["has_config_file"] is True
        assert result["config_file_path"] == "/config/test.yaml"
        assert result["sensors_count"] == 5
        assert result["services_registered"] is True
        assert result["last_error"] is None


class TestIntegrationFunctions:
    """Test integration module functions."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        return MagicMock()

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        entry.hass = MagicMock()
        return entry

    @pytest.fixture
    def mock_add_entities(self):
        """Create a mock add entities callback."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_async_setup_integration_success(self, mock_hass, mock_config_entry, mock_add_entities):
        """Test async_setup_integration with success."""
        with patch("ha_synthetic_sensors.integration.SyntheticSensorsIntegration") as MockIntegration:
            mock_integration = MagicMock()
            mock_integration.async_setup = AsyncMock(return_value=True)
            MockIntegration.return_value = mock_integration

            result = await async_setup_integration(mock_hass, mock_config_entry, mock_add_entities)

            assert result is True
            MockIntegration.assert_called_once_with(mock_hass, mock_config_entry)
            mock_integration.async_setup.assert_called_once_with(mock_add_entities)

    @pytest.mark.asyncio
    async def test_async_setup_integration_already_exists(self, mock_hass, mock_config_entry, mock_add_entities):
        """Test async_setup_integration when integration already exists."""
        # Mock an existing integration
        with patch("ha_synthetic_sensors.integration._integrations") as mock_integrations:
            mock_integrations.__contains__ = MagicMock(return_value=True)

            result = await async_setup_integration(mock_hass, mock_config_entry, mock_add_entities)

            assert result is True

    @pytest.mark.asyncio
    async def test_async_setup_integration_failure(self, mock_hass, mock_config_entry, mock_add_entities):
        """Test async_setup_integration with setup failure."""
        with patch("ha_synthetic_sensors.integration.SyntheticSensorsIntegration") as MockIntegration:
            mock_integration = MagicMock()
            mock_integration.async_setup = AsyncMock(return_value=False)
            MockIntegration.return_value = mock_integration

            # Ensure the integration doesn't already exist
            with patch("ha_synthetic_sensors.integration._integrations") as mock_integrations:
                mock_integrations.__contains__ = MagicMock(return_value=False)

                result = await async_setup_integration(mock_hass, mock_config_entry, mock_add_entities)

                assert result is False

    @pytest.mark.asyncio
    async def test_async_unload_integration_success(self, mock_config_entry):
        """Test async_unload_integration with success."""
        mock_integration = MagicMock()
        mock_integration.async_unload = AsyncMock(return_value=True)

        with patch("ha_synthetic_sensors.integration._integrations") as mock_integrations:
            mock_integrations.__contains__ = MagicMock(return_value=True)
            mock_integrations.__getitem__ = MagicMock(return_value=mock_integration)
            mock_integrations.__delitem__ = MagicMock()

            result = await async_unload_integration(mock_config_entry)

            assert result is True
            mock_integration.async_unload.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_unload_integration_not_found(self, mock_config_entry):
        """Test async_unload_integration when integration not found."""
        with patch("ha_synthetic_sensors.integration._integrations") as mock_integrations:
            mock_integrations.__contains__ = MagicMock(return_value=False)

            result = await async_unload_integration(mock_config_entry)

            assert result is True

    @pytest.mark.asyncio
    async def test_async_reload_integration_existing(self, mock_hass, mock_config_entry, mock_add_entities):
        """Test async_reload_integration with existing integration."""
        mock_integration = MagicMock()
        mock_integration.async_reload = AsyncMock(return_value=True)

        with patch("ha_synthetic_sensors.integration._integrations") as mock_integrations:
            mock_integrations.__contains__ = MagicMock(return_value=True)
            mock_integrations.__getitem__ = MagicMock(return_value=mock_integration)

            result = await async_reload_integration(mock_hass, mock_config_entry, mock_add_entities)

            assert result is True
            mock_integration.async_reload.assert_called_once_with(mock_add_entities)

    @pytest.mark.asyncio
    async def test_async_reload_integration_new(self, mock_hass, mock_config_entry, mock_add_entities):
        """Test async_reload_integration with new integration."""
        with patch("ha_synthetic_sensors.integration._integrations") as mock_integrations:
            mock_integrations.__contains__ = MagicMock(return_value=False)

            with patch("ha_synthetic_sensors.integration.async_setup_integration") as mock_setup:
                mock_setup.return_value = True

                result = await async_reload_integration(mock_hass, mock_config_entry, mock_add_entities)

                assert result is True
                mock_setup.assert_called_once_with(mock_hass, mock_config_entry, mock_add_entities)

    def test_get_integration_found(self, mock_config_entry):
        """Test get_integration when integration is found."""
        mock_integration = MagicMock()

        with patch("ha_synthetic_sensors.integration._integrations") as mock_integrations:
            mock_integrations.get = MagicMock(return_value=mock_integration)

            result = get_integration(mock_config_entry)

            assert result == mock_integration
            mock_integrations.get.assert_called_once_with(mock_config_entry.entry_id)

    def test_get_integration_not_found(self, mock_config_entry):
        """Test get_integration when integration is not found."""
        with patch("ha_synthetic_sensors.integration._integrations") as mock_integrations:
            mock_integrations.get = MagicMock(return_value=None)

            result = get_integration(mock_config_entry)

            assert result is None

    def test_validate_yaml_content_valid(self):
        """Test validate_yaml_content with valid YAML."""
        yaml_content = """
sensors:
  - unique_id: test_sensor
    name: Test Sensor
    formulas:
      - id: test_formula
        formula: "1 + 1"
"""

        with patch("ha_synthetic_sensors.integration.ConfigManager") as MockConfigManager:
            mock_manager = MagicMock()
            mock_manager.load_from_yaml.return_value = MagicMock()
            MockConfigManager.return_value = mock_manager

            result = validate_yaml_content(yaml_content)

            assert result["is_valid"] is True
            assert len(result["errors"]) == 0

    def test_validate_yaml_content_invalid(self):
        """Test validate_yaml_content with invalid YAML."""
        yaml_content = "invalid: yaml: content:"

        with patch("ha_synthetic_sensors.integration.ConfigManager") as MockConfigManager:
            mock_manager = MagicMock()
            mock_manager.load_from_yaml.side_effect = Exception("Parse error")
            MockConfigManager.return_value = mock_manager

            result = validate_yaml_content(yaml_content)

            assert result["is_valid"] is False
            assert len(result["errors"]) > 0

    def test_get_example_config(self):
        """Test get_example_config function."""
        result = get_example_config()

        assert isinstance(result, str)
        assert "sensors:" in result
        assert "formulas:" in result
        assert "cost_analysis" in result


class TestIntegration:
    """Test cases for integration workflow."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()
        return hass

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        config_entry = MagicMock()
        config_entry.entry_id = "test_entry_id"
        return config_entry

    def test_service_layer_setup(self, mock_hass, mock_config_entry):
        """Test that service layer sets up properly."""
        from ha_synthetic_sensors.integration import SyntheticSensorsIntegration

        # Create integration instance
        integration = SyntheticSensorsIntegration(mock_hass, mock_config_entry)

        # Test that integration initializes
        assert integration is not None
        assert hasattr(integration, "config_manager")
        assert hasattr(integration, "_config_manager")

    def test_yaml_to_entities_workflow(self, mock_hass, mock_config_entry):
        """Test the complete workflow from YAML config to entity processing."""
        from ha_synthetic_sensors.config_manager import (
            ConfigManager,
            FormulaConfig,
            SensorConfig,
        )
        from ha_synthetic_sensors.integration import SyntheticSensorsIntegration

        # Create integration instance
        SyntheticSensorsIntegration(mock_hass, mock_config_entry)

        # Test that configuration can be loaded and processed
        config_manager = ConfigManager(mock_hass)
        config = config_manager.load_config()  # Load empty config

        # Add test sensor
        formula = FormulaConfig(
            id="total_power",
            name="total_power",
            formula="hvac_upstairs + hvac_downstairs",
        )
        sensor = SensorConfig(unique_id="test_sensor", name="test_sensor", formulas=[formula])
        config.sensors.append(sensor)

        # Verify sensor was added
        assert len(config.sensors) == 1
        assert config.sensors[0].name == "test_sensor"

    def test_config_validation_workflow(self, mock_hass):
        """Test configuration validation workflow."""
        from ha_synthetic_sensors.config_manager import (
            Config,
            ConfigManager,
            FormulaConfig,
            SensorConfig,
        )

        ConfigManager(mock_hass)
        config = Config()

        # Test invalid configuration (duplicate sensor names)
        formula1 = FormulaConfig(id="test_formula", name="test_formula", formula="A + B")
        formula2 = FormulaConfig(id="test_formula2", name="test_formula2", formula="C + D")

        sensor1 = SensorConfig(unique_id="unique_id_1", name="unique_name_1", formulas=[formula1])
        sensor2 = SensorConfig(unique_id="unique_id_2", name="unique_name_2", formulas=[formula2])

        config.sensors = [sensor1, sensor2]

        # Validate configuration
        errors = config.validate()
        assert len(errors) == 0

    def test_formula_evaluation_workflow(self, mock_hass):
        """Test formula evaluation integration workflow."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator
        from ha_synthetic_sensors.name_resolver import NameResolver

        # Create components
        variables = {"temp": "sensor.temperature", "humidity": "sensor.humidity"}
        evaluator = Evaluator(mock_hass)
        NameResolver(mock_hass, variables)

        # Test integrated workflow
        formula_config = FormulaConfig(id="comfort_index", name="comfort_index", formula="temp + humidity")

        # Test evaluation with context
        context = cast(dict[str, ContextValue], {"temp": 22.5, "humidity": 45.0})
        result = evaluator.evaluate_formula(formula_config, context)

        assert result["success"] is True
        assert result["value"] == 67.5
