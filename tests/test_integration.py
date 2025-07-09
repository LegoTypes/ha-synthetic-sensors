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
from ha_synthetic_sensors.types import DataProviderResult


def load_yaml_fixture(filename: str) -> str:
    """Load YAML content from test fixtures."""
    # Check if it's an invalid fixture first
    if filename.startswith("integration_test_invalid") or filename.startswith("integration_test_malformed"):
        fixture_path = Path(__file__).parent / "yaml_fixtures" / "invalid" / filename
    else:
        fixture_path = Path(__file__).parent / "yaml_fixtures" / filename
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
        # Use realistic YAML fixture
        yaml_content = load_yaml_fixture("integration_test_valid_simple.yaml")

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
        yaml_content = load_yaml_fixture("integration_test_valid_simple.yaml")

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_file", return_value=True),
            patch("builtins.open", mock_open(read_data=yaml_content)),
        ):
            # Setup
            await async_setup_integration(mock_hass, mock_config_entry, mock_add_entities)

            # Reload
            result = await async_reload_integration(mock_hass, mock_config_entry, mock_add_entities)

            # Should succeed
            assert result is True

    @pytest.mark.asyncio
    async def test_unload_integration_public_api(self, mock_hass, mock_config_entry, mock_add_entities):
        """Test unload integration using public API only."""
        # First setup an integration
        yaml_content = load_yaml_fixture("integration_test_valid_simple.yaml")

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_file", return_value=True),
            patch("builtins.open", mock_open(read_data=yaml_content)),
        ):
            # Setup
            await async_setup_integration(mock_hass, mock_config_entry, mock_add_entities)

            # Unload
            result = await async_unload_integration(mock_hass, mock_config_entry)

            # Should succeed
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
        # Test getting example config
        config = get_example_config()
        assert isinstance(config, str)
        assert "version:" in config
        assert "sensors:" in config

    def test_realistic_yaml_fixtures_validation(self):
        """Test validation with realistic YAML fixtures that match documented schema."""
        # Test complex valid YAML with attributes and device association
        complex_yaml = load_yaml_fixture("integration_test_complex_sensors.yaml")
        result = validate_yaml_content(complex_yaml)
        assert result["is_valid"] is True
        assert result["sensors_count"] == 3  # Should have 3 sensors

        # Test invalid YAML structure
        invalid_yaml = load_yaml_fixture("integration_test_invalid_missing_formula.yaml")
        result = validate_yaml_content(invalid_yaml)
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

        # Test invalid YAML structure
        invalid_structure_yaml = load_yaml_fixture("integration_test_invalid_structure.yaml")
        result = validate_yaml_content(invalid_structure_yaml)
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

    def test_yaml_validation_error_scenarios(self):
        """Test various YAML validation error scenarios."""
        # Test invalid YAML structure
        invalid_yaml = load_yaml_fixture("integration_test_invalid_missing_formula.yaml")
        result = validate_yaml_content(invalid_yaml)
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

        # Test malformed YAML
        malformed_yaml = load_yaml_fixture("integration_test_malformed_yaml.yaml")
        result = validate_yaml_content(malformed_yaml)
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0


class TestPublicAPIConfiguration:
    """Test configuration management using public APIs only."""

    def test_formula_config_public_api(self):
        """Test FormulaConfig creation using public API."""
        config = FormulaConfig(
            formula="power_a + power_b",
            variables={"power_a": "sensor.power_a", "power_b": "sensor.power_b"},
            unit_of_measurement="W",
            device_class="power",
            state_class="measurement",
        )
        assert config.formula == "power_a + power_b"
        assert config.variables["power_a"] == "sensor.power_a"
        assert config.unit_of_measurement == "W"

    def test_sensor_config_public_api(self):
        """Test SensorConfig creation using public API."""
        config = SensorConfig(
            name="Test Sensor",
            formula="power_value * 2",
            variables={"power_value": "sensor.power"},
            unit_of_measurement="W",
            device_class="power",
            state_class="measurement",
        )
        assert config.name == "Test Sensor"
        assert config.formula == "power_value * 2"
        assert config.variables["power_value"] == "sensor.power"

    def test_data_provider_result_public_api(self):
        """Test DataProviderResult type using public API."""
        result = DataProviderResult(
            success=True,
            data={"sensor.power": 100.0},
            errors=[],
        )
        assert result.success is True
        assert result.data["sensor.power"] == 100.0
        assert result.errors == []
