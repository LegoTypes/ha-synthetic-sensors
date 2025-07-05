"""Tests for synthetic sensors integration components and workflow."""

from pathlib import Path
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

        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.is_file") as mock_is_file,
        ):
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

        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.is_file") as mock_is_file,
        ):
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
        mock_sensor_manager.cleanup_all_sensors = AsyncMock()
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
        mock_sensor_manager.cleanup_all_sensors = AsyncMock()
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

    @pytest.mark.asyncio
    async def test_check_auto_configuration_skipped_when_storage_exists(self, integration, mock_hass):
        """Test that auto-configuration is skipped when storage-based configuration exists."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # Mock storage manager with existing sensor sets
        mock_storage_manager = MagicMock()
        mock_storage_manager.async_load = AsyncMock()
        mock_storage_manager.list_sensor_sets.return_value = [
            {"sensor_set_id": "existing_set", "device_identifier": "test_device"}
        ]

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_file", return_value=True),
            patch("ha_synthetic_sensors.storage_manager.StorageManager", return_value=mock_storage_manager),
            patch.object(integration, "load_configuration_file") as mock_load,
        ):
            await integration._check_auto_configuration()
            # Verify storage was checked
            mock_storage_manager.async_load.assert_called_once()
            mock_storage_manager.list_sensor_sets.assert_called_once()
            # Verify auto-configuration file was NOT loaded
            mock_load.assert_not_called()
            # Verify auto_config_path was not set
            assert integration._auto_config_path is None

    @pytest.mark.asyncio
    async def test_check_auto_configuration_proceeds_when_storage_empty(self, integration, mock_hass):
        """Test that auto-configuration proceeds when storage has no sensor sets."""
        from pathlib import Path
        from unittest.mock import AsyncMock, MagicMock, patch

        # Mock storage manager with no sensor sets
        mock_storage_manager = MagicMock()
        mock_storage_manager.async_load = AsyncMock()
        mock_storage_manager.list_sensor_sets.return_value = []  # Empty storage

        # Create a fake config file that should be discovered
        config_dir = Path(mock_hass.config.config_dir)
        config_file = config_dir / "synthetic_sensors_config.yaml"

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_file", return_value=True),
            patch("ha_synthetic_sensors.storage_manager.StorageManager", return_value=mock_storage_manager),
            patch.object(integration, "load_configuration_file") as mock_load,
        ):
            await integration._check_auto_configuration()
            # Verify storage was checked
            mock_storage_manager.async_load.assert_called_once()
            mock_storage_manager.list_sensor_sets.assert_called_once()
            # Verify auto-configuration file WAS loaded (since storage is empty)
            mock_load.assert_called_once_with(str(config_file))
            # Verify auto_config_path was set
            assert integration._auto_config_path == config_file

    @pytest.mark.asyncio
    async def test_check_auto_configuration_proceeds_when_storage_check_fails(self, integration, mock_hass):
        """Test that auto-configuration proceeds when storage check fails."""
        from pathlib import Path
        from unittest.mock import AsyncMock, MagicMock, patch

        # Mock storage manager that raises an exception
        mock_storage_manager = MagicMock()
        mock_storage_manager.async_load = AsyncMock(side_effect=Exception("Storage error"))

        # Create a fake config file that should be discovered
        config_dir = Path(mock_hass.config.config_dir)
        config_file = config_dir / "synthetic_sensors_config.yaml"

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_file", return_value=True),
            patch("ha_synthetic_sensors.storage_manager.StorageManager", return_value=mock_storage_manager),
            patch.object(integration, "load_configuration_file") as mock_load,
        ):
            await integration._check_auto_configuration()
            # Verify storage check was attempted
            mock_storage_manager.async_load.assert_called_once()
            # Verify auto-configuration file WAS loaded (fallback behavior)
            mock_load.assert_called_once_with(str(config_file))
            # Verify auto_config_path was set
            assert integration._auto_config_path == config_file


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
        # Load YAML from fixture file
        yaml_fixtures_dir = Path(__file__).parent / "yaml_fixtures"
        with open(yaml_fixtures_dir / "integration_test_basic.yaml", encoding="utf-8") as f:
            yaml_content = f.read()

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
    """Test integration workflow and architecture patterns."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.config = MagicMock()
        hass.config.config_dir = "/config"
        hass.data = {}
        return hass

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        entry.data = {"name": "test_integration"}
        return entry

    def test_service_layer_setup(self, mock_hass, mock_config_entry):
        """Test service layer initialization."""
        from ha_synthetic_sensors.service_layer import ServiceLayer

        # Mock required dependencies
        mock_config_manager = MagicMock()
        mock_sensor_manager = MagicMock()
        mock_name_resolver = MagicMock()
        mock_evaluator = MagicMock()

        service_layer = ServiceLayer(
            hass=mock_hass,
            config_manager=mock_config_manager,
            sensor_manager=mock_sensor_manager,
            name_resolver=mock_name_resolver,
            evaluator=mock_evaluator,
        )
        assert service_layer is not None
        assert service_layer._hass == mock_hass
        assert service_layer._config_manager == mock_config_manager

    def test_yaml_to_entities_workflow(self, mock_hass, mock_config_entry):
        """Test the basic YAML to entities workflow."""
        from ha_synthetic_sensors.config_manager import ConfigManager
        from ha_synthetic_sensors.name_resolver import NameResolver
        from ha_synthetic_sensors.sensor_manager import SensorManager

        # Create config manager
        config_manager = ConfigManager(mock_hass)
        assert config_manager is not None

        # Create sensor manager
        add_entities_callback = MagicMock()
        name_resolver = NameResolver(mock_hass, {})
        sensor_manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=add_entities_callback,
        )
        assert sensor_manager is not None

    def test_config_validation_workflow(self, mock_hass):
        """Test configuration validation workflow."""
        from ha_synthetic_sensors.config_manager import ConfigManager

        config_manager = ConfigManager(mock_hass)

        # Test YAML validation
        valid_yaml = {
            "version": "1.0",
            "sensors": {
                "test_sensor": {
                    "name": "Test Sensor",
                    "formula": "1 + 1",
                    "unit_of_measurement": "units",
                }
            },
        }

        # This should not raise an exception
        config = config_manager.load_from_dict(valid_yaml)
        assert config is not None
        assert len(config.sensors) == 1

    def test_formula_evaluation_workflow(self, mock_hass):
        """Test formula evaluation workflow."""
        from ha_synthetic_sensors.config_manager import FormulaConfig
        from ha_synthetic_sensors.evaluator import Evaluator

        evaluator = Evaluator(mock_hass)
        assert evaluator is not None

        # Test simple evaluation using evaluate_formula
        formula_config = FormulaConfig(
            id="test_formula",
            formula="1 + 1",
        )
        result = evaluator.evaluate_formula(formula_config, {})
        assert result["success"] is True
        assert result["value"] == 2


class TestSensorSetIntegrationWorkflow:
    """Test the recommended SensorSet-based integration workflow."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.data = {}
        return hass

    @pytest.fixture
    async def storage_manager(self, mock_hass):
        """Create a StorageManager instance for testing."""
        from unittest.mock import AsyncMock, patch

        from ha_synthetic_sensors.storage_manager import StorageManager

        with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            mock_store.async_save = AsyncMock()
            MockStore.return_value = mock_store

            manager = StorageManager(mock_hass, "test_integration_synthetic")
            manager._store = mock_store
            await manager.async_load()
            return manager

    @pytest.mark.asyncio
    async def test_integration_setup_workflow(self, mock_hass, storage_manager):
        """Test the complete integration setup workflow using SensorSet."""
        from ha_synthetic_sensors.config_manager import FormulaConfig, SensorConfig

        # Step 1: Create sensor set for a device
        device_identifier = "test_device_123"
        sensor_set = await storage_manager.async_create_sensor_set(
            sensor_set_id=f"{device_identifier}_config_v1",
            device_identifier=device_identifier,
            name="Test Device Sensors",
            description="Synthetic sensors for test device",
        )

        assert sensor_set.sensor_set_id == f"{device_identifier}_config_v1"
        assert sensor_set.exists is True

        # Step 2: Generate sensor configurations
        sensor_configs = [
            SensorConfig(
                unique_id=f"{device_identifier}_power",
                name="Device Power",
                formulas=[
                    FormulaConfig(
                        id=f"{device_identifier}_power",
                        formula="power_value",
                        variables={"power_value": f"sensor.{device_identifier}_raw_power"},
                        unit_of_measurement="W",
                        device_class="power",
                        state_class="measurement",
                    )
                ],
                device_identifier=device_identifier,
            ),
            SensorConfig(
                unique_id=f"{device_identifier}_energy",
                name="Device Energy",
                formulas=[
                    FormulaConfig(
                        id=f"{device_identifier}_energy",
                        formula="energy_value / 1000",
                        variables={"energy_value": f"sensor.{device_identifier}_raw_energy"},
                        unit_of_measurement="kWh",
                        device_class="energy",
                        state_class="total_increasing",
                    )
                ],
                device_identifier=device_identifier,
            ),
        ]

        # Step 3: Add sensors to the sensor set
        await sensor_set.async_replace_sensors(sensor_configs)

        # Verify sensors were added
        assert sensor_set.sensor_count == 2
        stored_sensors = sensor_set.list_sensors()
        assert len(stored_sensors) == 2

        # Step 4: Individual sensor operations
        power_sensor = sensor_set.get_sensor(f"{device_identifier}_power")
        assert power_sensor is not None
        assert power_sensor.name == "Device Power"

        # Step 5: Export configuration for debugging/backup
        yaml_content = sensor_set.export_yaml()
        assert yaml_content is not None
        assert "sensors:" in yaml_content
        assert f"{device_identifier}_power:" in yaml_content

    @pytest.mark.asyncio
    async def test_yaml_import_workflow(self, mock_hass, storage_manager):
        """Test importing YAML configuration into a sensor set."""
        device_identifier = "yaml_test_device"

        # Create sensor set
        sensor_set = await storage_manager.async_create_sensor_set(
            sensor_set_id=f"{device_identifier}_yaml_config", device_identifier=device_identifier, name="YAML Test Device"
        )

        # YAML configuration to import
        yaml_content = """
version: "1.0"
sensors:
  yaml_test_device_total_power:
    name: "Total Power"
    formula: "power_input"
    variables:
      power_input: "sensor.yaml_test_device_raw_power"
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"

  yaml_test_device_efficiency:
    name: "Power Efficiency"
    formula: "output_power / input_power * 100"
    variables:
      output_power: "sensor.yaml_test_device_output"
      input_power: "sensor.yaml_test_device_input"
    unit_of_measurement: "%"
    device_class: "power_factor"
    state_class: "measurement"
"""

        # Import YAML
        await sensor_set.async_import_yaml(yaml_content)

        # Verify import
        assert sensor_set.sensor_count == 2

        total_power = sensor_set.get_sensor("yaml_test_device_total_power")
        assert total_power is not None
        assert total_power.name == "Total Power"

        efficiency = sensor_set.get_sensor("yaml_test_device_efficiency")
        assert efficiency is not None
        assert efficiency.name == "Power Efficiency"

    @pytest.mark.asyncio
    async def test_sensor_set_validation(self, mock_hass, storage_manager):
        """Test sensor set validation capabilities."""
        from ha_synthetic_sensors.config_manager import FormulaConfig, SensorConfig

        device_identifier = "validation_device"
        sensor_set = await storage_manager.async_create_sensor_set(
            sensor_set_id=f"{device_identifier}_validation", device_identifier=device_identifier, name="Validation Test"
        )

        # Add a valid sensor
        valid_sensor = SensorConfig(
            unique_id=f"{device_identifier}_valid",
            name="Valid Sensor",
            formulas=[
                FormulaConfig(
                    id=f"{device_identifier}_valid",
                    formula="test_value",
                    variables={"test_value": "sensor.test"},
                    unit_of_measurement="units",
                )
            ],
            device_identifier=device_identifier,
        )

        # Add an invalid sensor (missing formula)
        invalid_sensor = SensorConfig(
            unique_id=f"{device_identifier}_invalid",
            name="Invalid Sensor",
            formulas=[],  # No formulas - invalid
            device_identifier=device_identifier,
        )

        await sensor_set.async_add_sensor(valid_sensor)
        await sensor_set.async_add_sensor(invalid_sensor)

        # Test validation
        errors = sensor_set.get_sensor_errors()
        assert len(errors) == 1  # Only invalid sensor should have errors
        assert f"{device_identifier}_invalid" in errors
        assert "must have at least one formula" in errors[f"{device_identifier}_invalid"][0]

        # Test overall validity
        assert sensor_set.is_valid() is False  # Has errors

        # Remove invalid sensor
        await sensor_set.async_remove_sensor(f"{device_identifier}_invalid")

        # Now should be valid
        assert sensor_set.is_valid() is True
        assert len(sensor_set.get_sensor_errors()) == 0
