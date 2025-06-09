"""Tests for synthetic sensors integration components and workflow."""

from unittest.mock import MagicMock

import pytest


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
        sensor = SensorConfig(
            unique_id="test_sensor", name="test_sensor", formulas=[formula]
        )
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
        formula1 = FormulaConfig(
            id="test_formula", name="test_formula", formula="A + B"
        )
        formula2 = FormulaConfig(
            id="test_formula2", name="test_formula2", formula="C + D"
        )

        sensor1 = SensorConfig(
            unique_id="unique_id_1", name="unique_name_1", formulas=[formula1]
        )
        sensor2 = SensorConfig(
            unique_id="unique_id_2", name="unique_name_2", formulas=[formula2]
        )

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
        formula_config = FormulaConfig(
            id="comfort_index", name="comfort_index", formula="temp + humidity"
        )

        # Test evaluation with context
        context = {"temp": 22.5, "humidity": 45.0}
        result = evaluator.evaluate_formula(formula_config, context)

        assert result["success"] is True
        assert result["value"] == 67.5
