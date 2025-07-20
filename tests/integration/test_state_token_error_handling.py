"""Integration tests for state token error handling and actionable feedback."""

import pytest
from unittest.mock import MagicMock
import yaml

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.exceptions import BackingEntityResolutionError, SensorMappingError


class TestStateTokenErrorHandling:
    """Test specific error handling for state token resolution issues."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()

        # Mock states.get to return None for backing entities (simulating not registered)
        def mock_states_get(entity_id):
            return None

        hass.states.get.side_effect = mock_states_get
        return hass

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager with mock HA."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def state_token_yaml_without_setup(self):
        """YAML config with state token but no backing entity setup."""
        return {
            "sensors": {
                "test_current_power": {
                    "name": "Test Current Power",
                    "entity_id": "sensor.current_power",  # Backing entity
                    "formula": "state",  # Uses state token
                    "attributes": {"amperage": {"formula": "state / 240"}},
                }
            }
        }

    def test_state_token_without_backing_entity_registration(self, config_manager, state_token_yaml_without_setup):
        """Test that state token fails with specific error when backing entity not registered."""
        config = config_manager._parse_yaml_config(state_token_yaml_without_setup)

        # Find the sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_current_power")

        # Create sensor manager WITHOUT registering the backing entity
        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(),
        )

        # Try to evaluate the formula - should fail with specific error
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should raise SensorMappingError for missing backing entity
        with pytest.raises(SensorMappingError) as exc_info:
            evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Check the error message
        error_msg = str(exc_info.value)
        assert "backing entity" in error_msg.lower()
        assert "test_current_power" in error_msg  # Now uses sensor key instead of backing entity ID
        assert "not registered" in error_msg.lower()

    def test_state_token_without_data_provider_callback(self, config_manager, state_token_yaml_without_setup):
        """Test that state token fails with specific error when no data provider callback is set."""
        config = config_manager._parse_yaml_config(state_token_yaml_without_setup)

        # Find the sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_current_power")

        # Create sensor manager and register backing entity but DON'T set data provider callback
        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(),
        )

        # Register the backing entity but don't set data provider callback
        sensor_manager.register_data_provider_entities({"sensor.current_power"}, allow_ha_lookups=False, change_notifier=None)

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"test_current_power": "sensor.current_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Try to evaluate the formula - should fail with specific error
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Should fail with backing entity resolution error since no data provider is available
        assert result["success"] is False
        assert "backing entity" in result["error"].lower()
        assert "cannot be resolved" in result["error"].lower()
        assert "no data provider available" in result["error"].lower()

    def test_state_token_with_ha_lookups_disabled_and_no_data(self, config_manager, state_token_yaml_without_setup):
        """Test that state token fails with specific error when HA lookups disabled and no data available."""
        config = config_manager._parse_yaml_config(state_token_yaml_without_setup)

        # Find the sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_current_power")

        # Create sensor manager with data provider that returns no data
        def mock_data_provider_no_data(entity_id: str):
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider_no_data),
        )

        # Register the backing entity with HA lookups disabled
        sensor_manager.register_data_provider_entities(
            {"sensor.current_power"},
            allow_ha_lookups=False,  # Disable HA lookups
            change_notifier=None,
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"test_current_power": "sensor.current_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Try to evaluate the formula - should fail with specific error
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Should fail with backing entity resolution error since data provider says entity doesn't exist
        assert result["success"] is False
        assert "backing entity" in result["error"].lower()
        assert "cannot be resolved" in result["error"].lower()
        assert "entity does not exist" in result["error"].lower()

    def test_state_token_with_ha_lookups_enabled_but_entity_not_in_ha(self, config_manager, state_token_yaml_without_setup):
        """Test that state token fails with specific error when HA lookups enabled but entity not in HA."""
        config = config_manager._parse_yaml_config(state_token_yaml_without_setup)

        # Find the sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_current_power")

        # Create sensor manager with data provider that returns no data
        def mock_data_provider_no_data(entity_id: str):
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider_no_data),
        )

        # Register the backing entity with HA lookups enabled
        sensor_manager.register_data_provider_entities(
            {"sensor.current_power"},
            allow_ha_lookups=True,  # Enable HA lookups
            change_notifier=None,
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"test_current_power": "sensor.current_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Try to evaluate the formula - should fail with specific error
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Should fail with backing entity resolution error since data provider says entity doesn't exist
        assert result["success"] is False
        assert "backing entity" in result["error"].lower()
        assert "cannot be resolved" in result["error"].lower()
        assert "entity does not exist" in result["error"].lower()

    def test_state_token_with_missing_entity_id_field(self, config_manager):
        """Test that state token fails with specific error when sensor has no entity_id field."""
        yaml_without_entity_id = {
            "sensors": {
                "test_current_power": {
                    "name": "Test Current Power",
                    "formula": "state",  # Uses state token but no entity_id
                    "attributes": {"amperage": {"formula": "state / 240"}},
                }
            }
        }

        config = config_manager._parse_yaml_config(yaml_without_entity_id)

        # Find the sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_current_power")

        # Create sensor manager
        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(),
        )

        # Try to evaluate the formula - should fail with specific error
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should fail with "state not defined" error since no context is provided
        result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Should fail with specific error about state token resolution
        assert result["success"] is False
        assert "state" in result["error"].lower()
        assert "cannot be resolved" in result["error"].lower()
        assert "no backing entity mapping" in result["error"].lower()

    def test_state_token_with_invalid_entity_id_format(self, config_manager):
        """Test that state token fails with specific error when entity_id format is invalid."""
        yaml_with_invalid_entity_id = {
            "sensors": {
                "test_current_power": {
                    "name": "Test Current Power",
                    "entity_id": "invalid_entity_format",  # Invalid format (no domain)
                    "formula": "state",
                    "attributes": {"amperage": {"formula": "state / 240"}},
                }
            }
        }

        config = config_manager._parse_yaml_config(yaml_with_invalid_entity_id)

        # Find the sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_current_power")

        # Create sensor manager
        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(),
        )

        # Try to evaluate the formula - should fail with specific error
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]

        # Should raise SensorMappingError for invalid entity format
        with pytest.raises(SensorMappingError) as exc_info:
            evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)

        # Check the error message
        error_msg = str(exc_info.value)
        assert "backing entity" in error_msg.lower()
        assert "test_current_power" in error_msg  # Now uses sensor key instead of backing entity ID
        assert "not registered" in error_msg.lower()

    def test_state_token_in_attribute_without_backing_entity_registration(self, config_manager):
        """Test that state token in attributes fails with specific error when no context is provided."""
        yaml_with_state_token_in_attribute = {
            "sensors": {
                "test_current_power": {
                    "name": "Test Current Power",
                    "entity_id": "sensor.current_power",  # Backing entity
                    "formula": "1000",  # Main formula doesn't use state token
                    "attributes": {
                        "amperage": {
                            "formula": "state / 240"  # Attribute uses state token
                        }
                    },
                }
            }
        }

        config = config_manager._parse_yaml_config(yaml_with_state_token_in_attribute)

        # Find the sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_current_power")

        # Create sensor manager WITHOUT registering the backing entity
        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(),
        )

        # Try to evaluate the attribute formula - should fail with specific error
        evaluator = sensor_manager._evaluator
        attribute_formula = sensor.formulas[1]  # Second formula is the attribute

        result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, None, sensor)

        # Should fail with specific error about state token resolution (no context provided)
        assert result["success"] is False
        assert "state" in result["error"].lower()
        assert "cannot be resolved" in result["error"].lower()
        assert "no backing entity mapping" in result["error"].lower()

    def test_state_token_in_attribute_with_missing_entity_id_field(self, config_manager):
        """Test that state token in attributes fails with specific error when sensor has no entity_id field."""
        yaml_without_entity_id = {
            "sensors": {
                "test_current_power": {
                    "name": "Test Current Power",
                    "formula": "1000",  # Main formula doesn't use state token
                    "attributes": {
                        "amperage": {
                            "formula": "state / 240"  # Attribute uses state token but no entity_id
                        }
                    },
                }
            }
        }

        config = config_manager._parse_yaml_config(yaml_without_entity_id)

        # Find the sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_current_power")

        # Create sensor manager
        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(),
        )

        # Try to evaluate the attribute formula - should fail with specific error
        evaluator = sensor_manager._evaluator
        attribute_formula = sensor.formulas[1]  # Second formula is the attribute

        result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, None, sensor)

        # Should fail with specific error about state token resolution (no context provided)
        assert result["success"] is False
        assert "state" in result["error"].lower()
        assert "cannot be resolved" in result["error"].lower()
        assert "no backing entity mapping" in result["error"].lower()

    def test_state_token_in_attribute_works_when_properly_setup(self, config_manager):
        """Test that state token in attributes works correctly when backing entity is properly set up."""
        yaml_with_state_token_in_attribute = {
            "sensors": {
                "test_current_power": {
                    "name": "Test Current Power",
                    "entity_id": "sensor.current_power",  # Backing entity
                    "formula": "1000",  # Main formula doesn't use state token
                    "attributes": {
                        "amperage": {
                            "formula": "state / 240"  # Attribute uses state token
                        }
                    },
                }
            }
        }

        config = config_manager._parse_yaml_config(yaml_with_state_token_in_attribute)

        # Find the sensor
        sensor = next(s for s in config.sensors if s.unique_id == "test_current_power")

        # Create sensor manager with data provider that returns data
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.current_power":
                return {"value": 1200.0, "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities({"sensor.current_power"}, allow_ha_lookups=False, change_notifier=None)

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"test_current_power": "sensor.current_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Try to evaluate the attribute formula - should succeed
        evaluator = sensor_manager._evaluator
        attribute_formula = sensor.formulas[1]  # Second formula is the attribute

        # Provide context with state value (simulating how sensor manager provides it)
        context = {"state": 1200.0}  # This would be the main sensor's result

        result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)

        # Should succeed and calculate the amperage correctly
        assert result["success"] is True
        assert result["value"] == 5.0  # 1200.0 / 240 = 5.0
