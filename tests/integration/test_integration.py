"""Tests for synthetic sensors integration using public APIs only."""

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from ha_synthetic_sensors import (
    async_reload_integration,
    async_setup_integration,
    async_unload_integration,
    get_example_config,
    validate_yaml_content,
)
from ha_synthetic_sensors.config_manager import FormulaConfig, SensorConfig
from ha_synthetic_sensors.type_definitions import DataProviderResult


def load_yaml_fixture(filename: str) -> str:
    """Load YAML content from test fixtures."""
    # Check if it's an invalid fixture first
    if filename.startswith("integration_test_invalid") or filename.startswith("integration_test_malformed"):
        fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "invalid" / filename
    else:
        fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / filename
    return fixture_path.read_text()


class TestPublicAPIIntegration:
    """Test integration using only public APIs documented in the guide."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.data = {}
        hass.config = MagicMock()
        hass.config.config_dir = "/config"
        hass.states = MagicMock()
        return hass

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = MagicMock()
        entry.entry_id = "test_entry_123"
        entry.domain = "test_integration"
        entry.data = {"name": "test_integration"}
        return entry

    @pytest.fixture
    def mock_add_entities(self):
        """Create a mock add entities callback."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_yaml_based_integration_public_api(self, mock_hass, mock_config_entry, mock_add_entities):
        """Test YAML-based integration using public API only."""
        # Create test YAML content
        yaml_content = """
version: "1.0"
global_settings:
  device_identifier: "device_123"

sensors:
  test_power:
    name: "Test Power"
    entity_id: "sensor.test_power"
    formula: "power_value"
    variables:
      power_value: "test_integration_backing.device_123_power"
    unit_of_measurement: "W"
    device_class: "power"
    state_class: "measurement"
"""

        # Mock file system to provide YAML content
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_file", return_value=True),
            patch("builtins.open", mock_open(read_data=yaml_content)),
        ):
            # Test public API setup
            result = await async_setup_integration(mock_hass, mock_config_entry, mock_add_entities)

            # Should succeed with valid YAML
            assert result is True

    @pytest.mark.asyncio
    async def test_reload_integration_public_api(self, mock_hass, mock_config_entry, mock_add_entities):
        """Test reload integration using public API only."""
        # First setup an integration
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_file", return_value=True),
            patch("builtins.open", mock_open(read_data="version: '1.0'\nsensors: {}")),
        ):
            # Setup
            await async_setup_integration(mock_hass, mock_config_entry, mock_add_entities)

            # Test reload using public API
            result = await async_reload_integration(mock_hass, mock_config_entry, mock_add_entities)

            assert result is True

    @pytest.mark.asyncio
    async def test_unload_integration_public_api(self, mock_config_entry):
        """Test unload integration using public API only."""
        # Test unload using public API
        result = await async_unload_integration(mock_config_entry)

        # Should succeed even if no integration was loaded
        assert result is True

    def test_validate_yaml_content_public_api(self):
        """Test YAML validation using public API only."""
        # Test valid YAML using fixture
        valid_yaml = load_yaml_fixture("integration_test_valid_simple.yaml")
        result = validate_yaml_content(valid_yaml)
        assert result["is_valid"] is True
        assert result["sensors_count"] == 1

        # Test invalid YAML structure using fixture
        invalid_yaml = load_yaml_fixture("integration_test_invalid_missing_formula.yaml")
        result = validate_yaml_content(invalid_yaml)
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

    def test_get_example_config_public_api(self):
        """Test get example config using public API only."""
        config = get_example_config()

        assert isinstance(config, str)
        assert "sensors:" in config
        assert "formula:" in config

    def test_data_provider_callback_pattern(self):
        """Test the data provider callback pattern from the guide."""
        # Mock coordinator similar to integration guide example
        mock_coordinator = MagicMock()
        mock_coordinator.data = MagicMock()

        # Mock device data
        mock_device_data = MagicMock()
        mock_device_data.power = 1500.0
        mock_device_data.voltage = 240.0
        mock_device_data.current = 6.25

        mock_coordinator.data.get_device = MagicMock(return_value=mock_device_data)

        # Create data provider callback as shown in guide
        def create_data_provider_callback(coordinator):
            def data_provider_callback(entity_id: str) -> DataProviderResult:
                try:
                    # Parse backing entity ID format as per guide
                    if not entity_id.startswith("test_integration_backing."):
                        return {"value": None, "exists": False}

                    # Extract the backing entity part
                    backing_part = entity_id.split(".", 1)[1]

                    # Parse device and sensor type
                    parts = backing_part.rsplit("_", 1)
                    if len(parts) == 2:
                        device_id = parts[0].replace("device_", "")
                        sensor_type = parts[1]
                    else:
                        return {"value": None, "exists": False}

                    # Get current data from coordinator
                    device_data = coordinator.data.get_device(device_id)
                    if not device_data:
                        return {"value": None, "exists": False}

                    # Return the requested sensor value
                    value = getattr(device_data, sensor_type, None)
                    return {"value": value, "exists": value is not None}

                except Exception:
                    return {"value": None, "exists": False}

            return data_provider_callback

        # Test the callback
        callback = create_data_provider_callback(mock_coordinator)

        # Test valid entity ID
        result = callback("test_integration_backing.device_123_power")
        assert result["value"] == 1500.0
        assert result["exists"] is True

        # Test invalid entity ID
        result = callback("invalid.entity_id")
        assert result["value"] is None
        assert result["exists"] is False

        # Test non-existent sensor (should return None for unknown attributes)
        mock_device_data.nonexistent = None
        result = callback("test_integration_backing.device_123_nonexistent")
        assert result["value"] is None
        assert result["exists"] is False


class TestPublicAPIConfiguration:
    """Test configuration-related public APIs."""

    def test_sensor_config_public_api(self):
        """Test SensorConfig using public API only."""
        # Test creating sensor config as shown in guide
        config = SensorConfig(
            unique_id="device_123_current_power",
            name="Test Device Current Power",
            entity_id="sensor.device_123_current_power",
            device_identifier="device_123",
            formulas=[
                FormulaConfig(
                    id="main",
                    formula="power_watts",
                    variables={"power_watts": "test_integration_backing.device_123_power"},
                    unit_of_measurement="W",
                    device_class="power",
                    state_class="measurement",
                )
            ],
        )

        # Test public properties
        assert config.unique_id == "device_123_current_power"
        assert config.name == "Test Device Current Power"
        assert config.entity_id == "sensor.device_123_current_power"
        assert config.device_identifier == "device_123"
        assert len(config.formulas) == 1
        assert config.formulas[0].id == "main"
        assert config.formulas[0].formula == "power_watts"
        assert config.formulas[0].unit_of_measurement == "W"
        assert config.formulas[0].device_class == "power"
        assert config.formulas[0].state_class == "measurement"

    def test_formula_config_public_api(self):
        """Test FormulaConfig using public API only."""
        # Test creating formula config as shown in guide
        formula = FormulaConfig(
            id="main",
            formula="power_watts * 24 / 1000",
            variables={"power_watts": "test_integration_backing.device_123_power"},
            unit_of_measurement="kWh",
            device_class="energy",
            state_class="total_increasing",
        )

        # Test public properties
        assert formula.id == "main"
        assert formula.formula == "power_watts * 24 / 1000"
        assert formula.variables == {"power_watts": "test_integration_backing.device_123_power"}
        assert formula.unit_of_measurement == "kWh"
        assert formula.device_class == "energy"
        assert formula.state_class == "total_increasing"

    def test_yaml_validation_scenarios(self):
        """Test various YAML validation scenarios using public API."""
        # Test minimal valid YAML
        minimal_yaml = load_yaml_fixture("integration_test_minimal_valid.yaml")
        result = validate_yaml_content(minimal_yaml)
        assert result["is_valid"] is True
        assert result["sensors_count"] == 1

        # Test complex valid YAML
        complex_yaml = load_yaml_fixture("integration_test_complex_valid.yaml")
        result = validate_yaml_content(complex_yaml)
        assert result["is_valid"] is True
        assert result["sensors_count"] == 2

        # Test invalid YAML structure
        invalid_yaml = load_yaml_fixture("integration_test_invalid_missing_formula.yaml")
        result = validate_yaml_content(invalid_yaml)
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

        # Test malformed YAML
        malformed_yaml = load_yaml_fixture("integration_test_malformed.yaml")
        result = validate_yaml_content(malformed_yaml)
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0
