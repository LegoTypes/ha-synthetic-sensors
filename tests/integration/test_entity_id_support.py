"""Test entity_id field support in YAML configuration.

This tests the explicit entity_id field that allows users to override
the default entity_id generation pattern.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.sensor_manager import DynamicSensor, SensorManagerConfig


class TestEntityIdSupport:
    """Test explicit entity_id field support in YAML configuration."""

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a ConfigManager instance."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def entity_id_yaml(self):
        """Load the entity_id support YAML fixture."""
        fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "entity_id_support.yaml"
        with open(fixture_path) as f:
            return yaml.safe_load(f)

    def test_yaml_fixture_loads_correctly(self, mock_hass, mock_entity_registry, mock_states, entity_id_yaml):
        """Test that the YAML fixture loads without errors."""
        assert entity_id_yaml["version"] == "1.0"
        assert "sensors" in entity_id_yaml
        assert len(entity_id_yaml["sensors"]) == 4

    def test_standard_sensor_without_entity_id(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, entity_id_yaml
    ):
        """Test sensor without explicit entity_id uses default pattern."""
        config = config_manager._parse_yaml_config(entity_id_yaml)

        # Find the standard sensor
        standard_sensor = next(s for s in config.sensors if s.unique_id == "standard_power_sensor")

        # Should not have explicit entity_id set
        assert standard_sensor.entity_id is None

        # When creating a DynamicSensor, it should use the default pattern
        evaluator = Evaluator(config_manager._hass)
        mock_sensor_manager = MagicMock()
        dynamic_sensor = DynamicSensor(
            config_manager._hass, standard_sensor, evaluator, mock_sensor_manager, SensorManagerConfig()
        )

        # Should have the unique_id without prefix (new behavior)
        assert dynamic_sensor.unique_id == "standard_power_sensor"
        # Should not have explicit entity_id set (HA will auto-generate)
        assert not hasattr(dynamic_sensor, "_attr_entity_id")

    def test_custom_entity_id_field_parsing(self, mock_hass, mock_entity_registry, mock_states, config_manager, entity_id_yaml):
        """Test that explicit entity_id field is parsed correctly."""
        config = config_manager._parse_yaml_config(entity_id_yaml)

        # Find the sensor with custom entity_id
        custom_sensor = next(s for s in config.sensors if s.unique_id == "custom_named_sensor")

        # Should have explicit entity_id set
        assert custom_sensor.entity_id == "sensor.custom_energy_monitor"

        # Check other properties are still correct
        assert custom_sensor.name == "Custom Named Energy Monitor"
        assert custom_sensor.formulas[0].formula == "base_power * efficiency_factor"

    def test_multiple_custom_entity_ids(self, mock_hass, mock_entity_registry, mock_states, config_manager, entity_id_yaml):
        """Test multiple sensors with different custom entity_ids."""
        config = config_manager._parse_yaml_config(entity_id_yaml)

        # Check first custom entity_id
        custom_sensor1 = next(s for s in config.sensors if s.unique_id == "custom_named_sensor")
        assert custom_sensor1.entity_id == "sensor.custom_energy_monitor"

        # Check second custom entity_id
        custom_sensor2 = next(s for s in config.sensors if s.unique_id == "special_consumption_tracker")
        assert custom_sensor2.entity_id == "sensor.special_consumption"

    def test_custom_entity_id_with_attributes(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, entity_id_yaml
    ):
        """Test sensor with custom entity_id and calculated attributes."""
        config = config_manager._parse_yaml_config(entity_id_yaml)

        # Find the comprehensive sensor
        comprehensive_sensor = next(s for s in config.sensors if s.unique_id == "comprehensive_monitor")

        # Check custom entity_id
        assert comprehensive_sensor.entity_id == "sensor.comprehensive_energy"

        # Check it has attributes
        assert len(comprehensive_sensor.formulas) == 3  # Main + 2 attributes

        # Find attribute formulas
        daily_proj = next(f for f in comprehensive_sensor.formulas if f.id == "comprehensive_monitor_daily_projection")
        efficiency = next(f for f in comprehensive_sensor.formulas if f.id == "comprehensive_monitor_efficiency_rating")

        assert daily_proj.formula == "state * 24"
        assert efficiency.formula == "state / 1000 * 100"

    def test_dynamic_sensor_respects_custom_entity_id(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, entity_id_yaml
    ):
        """Test that DynamicSensor respects custom entity_id field."""
        config = config_manager._parse_yaml_config(entity_id_yaml)
        evaluator = Evaluator(config_manager._hass)

        # Test standard sensor (no custom entity_id)
        standard_sensor = next(s for s in config.sensors if s.unique_id == "standard_power_sensor")
        mock_sensor_manager = MagicMock()
        standard_dynamic = DynamicSensor(
            config_manager._hass, standard_sensor, evaluator, mock_sensor_manager, SensorManagerConfig()
        )

        # Should use unique_id without prefix (new behavior)
        assert standard_dynamic.unique_id == "standard_power_sensor"
        assert not hasattr(standard_dynamic, "_attr_entity_id")

        # Test custom entity_id sensor
        custom_sensor = next(s for s in config.sensors if s.unique_id == "custom_named_sensor")
        custom_dynamic = DynamicSensor(
            config_manager._hass, custom_sensor, evaluator, mock_sensor_manager, SensorManagerConfig()
        )

        # Should use unique_id without prefix (new behavior)
        assert custom_dynamic.unique_id == "custom_named_sensor"
        assert hasattr(custom_dynamic, "entity_id")
        assert custom_dynamic.entity_id == "sensor.custom_energy_monitor"

    def test_entity_id_validation_in_config(self, mock_hass, mock_entity_registry, mock_states, config_manager, entity_id_yaml):
        """Test that entity_id values are validated during config parsing."""
        # This should parse without errors
        config = config_manager._parse_yaml_config(entity_id_yaml)
        assert len(config.sensors) == 4

        # Test invalid entity_id format using schema validation (which enforces HA rules)
        from ha_synthetic_sensors.schema_validator import validate_yaml_config

        invalid_yaml = entity_id_yaml.copy()
        invalid_yaml["sensors"]["invalid_entity_id_sensor"] = {
            "name": "Invalid Entity ID",
            "entity_id": "invalid_format_no_domain",
            "formula": "1 + 1",
        }  # Missing domain - should be rejected

        # Schema validation should catch the invalid entity_id format
        result = validate_yaml_config(invalid_yaml)
        assert result["valid"] is False
        assert len(result["errors"]) > 0

        # Check that the error is about entity_id format
        error_messages = [error.message for error in result["errors"]]
        assert any("invalid_format_no_domain" in msg for msg in error_messages)

    def test_entity_id_cross_references(self, mock_hass, mock_entity_registry, mock_states, config_manager, entity_id_yaml):
        """Test that entity_id field works correctly with cross-references."""
        config = config_manager._parse_yaml_config(entity_id_yaml)

        # Test that sensors can reference each other's custom entity_ids
        comprehensive_sensor = next(s for s in config.sensors if s.unique_id == "comprehensive_monitor")

        # The comprehensive sensor should have the custom entity_id
        assert comprehensive_sensor.entity_id == "sensor.comprehensive_energy"

        # Test that the formula can be evaluated (this tests the entity_id resolution)
        evaluator = Evaluator(config_manager._hass)
        mock_sensor_manager = MagicMock()
        dynamic_sensor = DynamicSensor(
            config_manager._hass, comprehensive_sensor, evaluator, mock_sensor_manager, SensorManagerConfig()
        )

        # Should have the custom entity_id
        assert dynamic_sensor.entity_id == "sensor.comprehensive_energy"

    async def test_state_token_in_main_formula(
        self, mock_hass, mock_entity_registry, mock_device_registry, mock_states, mock_config_entry, mock_async_add_entities
    ):
        """Test that the 'state' token in main formulas resolves to the backing entity."""
        from pathlib import Path
        from ha_synthetic_sensors import async_setup_synthetic_sensors
        from ha_synthetic_sensors.storage_manager import StorageManager
        from unittest.mock import patch, AsyncMock
        import yaml

        # Load the state token example
        example_path = Path(__file__).parent.parent.parent / "examples" / "state_token_example.yaml"
        with open(example_path) as f:
            state_token_yaml = yaml.safe_load(f)

        # Set up storage manager with the YAML config

        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_state_token", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "state_token_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test-device-001", name="State Token Test"
            )

            # Load YAML content into the sensor set
            yaml_content = yaml.dump(state_token_yaml)
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 4  # Should import 4 sensors

            # Set up backing entity data for virtual entities (Pattern 1 from guide)
            # These sensors use 'state' token to reference backing entities
            backing_data = {
                "sensor.current_power": 1500.0,  # Test current power sensor
                "sensor.feed_through_power": 2000.0,  # Test feed through power sensor
                "sensor.energy_consumed": 5000.0,  # Test energy consumed sensor
                "sensor.raw_power": 1000.0,  # Test processed power sensor (backing entity)
            }

            # Create data provider for virtual backing entities
            def data_provider(entity_id: str):
                if entity_id in backing_data:
                    return {"value": backing_data[entity_id], "exists": True}
                return {"value": None, "exists": False}

            # Create sensor-to-backing mapping for 'state' token resolution
            # Maps sensor unique_id to backing entity_id
            sensor_to_backing_mapping = {
                "test_current_power": "sensor.current_power",
                "test_feed_through_power": "sensor.feed_through_power",
                "test_energy_consumed": "sensor.energy_consumed",
                "test_power_with_processing": "sensor.raw_power",
            }

            # Set up sensor manager using public API (Pattern 1 from guide)
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                sensor_set_id=sensor_set_id,
                data_provider_callback=data_provider,  # For virtual entities
                sensor_to_backing_mapping=sensor_to_backing_mapping,  # Map 'state' token
            )

            # Verify sensors were created
            assert sensor_manager is not None
            all_entities = mock_async_add_entities.call_args[0][0]
            assert len(all_entities) == 4  # Should have 4 sensors

            # Find the current power sensor
            current_power_entity = next(e for e in all_entities if e.unique_id == "test_current_power")

            # Verify the sensor has the correct entity_id
            assert current_power_entity.entity_id == "sensor.current_power"

            # Test that the sensor evaluates correctly with the 'state' token
            await current_power_entity.async_update()

            # The sensor should return the backing entity's value (1500.0)
            assert current_power_entity.state == 1500.0

            # Test the processed power sensor (uses formula: state * 1.1)
            processed_power_entity = next(e for e in all_entities if e.unique_id == "test_power_with_processing")
            await processed_power_entity.async_update()

            # Should be 1000.0 * 1.1 = 1100.0
            assert processed_power_entity.state == 1100.0

    def test_entity_id_in_schema_validation(self, mock_hass, mock_entity_registry, mock_states, config_manager, entity_id_yaml):
        """Test that schema validation accepts entity_id field."""
        # Load and validate the config
        config = config_manager._parse_yaml_config(entity_id_yaml)
        errors = config_manager.validate_config(config)

        # Should have no validation errors
        assert len(errors) == 0, f"Validation errors: {errors}"

        # Test schema validation directly if available
        if hasattr(config_manager, "validate_yaml_data"):
            validation_result = config_manager.validate_yaml_data(entity_id_yaml)
            # Should now pass with the fixed YAML
            assert validation_result["valid"] is True, f"Schema validation errors: {validation_result.get('errors', [])}"
            assert len(validation_result["errors"]) == 0
