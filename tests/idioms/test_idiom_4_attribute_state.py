"""Integration tests for Idiom 4: Attribute State References."""

import pytest
from unittest.mock import MagicMock
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig


class TestIdiom4AttributeState:
    """Test Idiom 4: Attribute State References."""

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager with mock HA."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def state_token_yaml(self):
        """Load the state token YAML file."""
        yaml_path = "examples/idiom_4_state_token.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def sensor_key_yaml(self):
        """Load the sensor key YAML file."""
        yaml_path = "examples/idiom_4_sensor_key.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def entity_id_yaml(self):
        """Load the entity ID YAML file."""
        yaml_path = "examples/idiom_4_entity_id.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    @pytest.fixture
    def evaluation_order_yaml(self):
        """Load the evaluation order YAML file."""
        yaml_path = "examples/idiom_4_evaluation_order.yaml"
        with open(yaml_path, "r", encoding="utf-8") as file:
            return file.read()

    def test_state_token_in_attributes(self, mock_hass, mock_entity_registry, mock_states, config_manager, state_token_yaml):
        """Test attribute formula uses state token."""
        config = config_manager.load_from_yaml(state_token_yaml)
        sensor = config.sensors[0]

        # Create sensor manager with data provider
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {"value": 1000.0, "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities(
            {"sensor.span_panel_instantaneous_power"}, allow_ha_lookups=False, change_notifier=None
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"energy_cost_analysis": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 250.0  # state * 0.25 = 1000 * 0.25 = 250

        # Test attribute formula evaluation with context from main result
        if len(sensor.formulas) > 1:
            attribute_formula = sensor.formulas[1]
            context = {"state": main_result["value"]}

            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)
            assert attr_result["success"] is True
            assert attr_result["value"] == 6000.0  # 250 * 24 = 6000

    def test_sensor_key_in_attributes(self, mock_hass, mock_entity_registry, mock_states, config_manager, sensor_key_yaml):
        """Test attribute formula uses sensor key name."""
        config = config_manager.load_from_yaml(sensor_key_yaml)
        sensor = config.sensors[0]

        # Create sensor manager with data provider
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {"value": 1000.0, "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities(
            {"sensor.span_panel_instantaneous_power"}, allow_ha_lookups=False, change_notifier=None
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"sensor_key_attribute_test": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 250.0  # state * 0.25 = 1000 * 0.25 = 250

        # Test attribute formula evaluation with context from main result
        if len(sensor.formulas) > 1:
            attribute_formula = sensor.formulas[1]
            context = {"state": main_result["value"], "sensor_key_attribute_test": main_result["value"]}

            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)
            assert attr_result["success"] is True

    def test_entity_id_in_attributes(self, mock_hass, mock_entity_registry, mock_states, config_manager, entity_id_yaml):
        """Test attribute formula uses entity ID reference."""
        # Test that entity ID self-references are properly replaced with 'state' tokens
        # during the YAML processing phase, according to the design guide

        # Import the YAML through StorageManager to trigger self-reference replacement
        from ha_synthetic_sensors.storage_manager import StorageManager
        from unittest.mock import AsyncMock, patch

        async def run_test():
            # Create storage manager with mocked Store
            with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
                mock_store = AsyncMock()
                mock_store.async_load.return_value = None
                MockStore.return_value = mock_store

                storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
                storage_manager._store = mock_store
                await storage_manager.async_load()

                sensor_set_id = "entity_id_attribute_test"

                if storage_manager.sensor_set_exists(sensor_set_id):
                    await storage_manager.async_delete_sensor_set(sensor_set_id)

                await storage_manager.async_create_sensor_set(sensor_set_id)

                # Import YAML with entity ID self-references - this should trigger state token replacement
                result = await storage_manager.async_from_yaml(yaml_content=entity_id_yaml, sensor_set_id=sensor_set_id)
                assert result["sensors_imported"] == 2  # The YAML contains 2 sensors

                # Get the processed sensors
                sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
                assert len(sensors) == 2

                # Find the first sensor (entity_id_attribute_test)
                sensor = None
                for s in sensors:
                    if s.unique_id == "entity_id_attribute_test":
                        sensor = s
                        break

                assert sensor is not None, "entity_id_attribute_test sensor should exist"

                # Get the processed attributes
                attributes = sensor.formulas[0].attributes

                # Verify that entity ID self-references were replaced with 'state' tokens
                # According to the design guide, both sensor key and entity ID self-references
                # should be replaced with 'state' tokens in attributes
                assert "daily_cost" in attributes
                assert attributes["daily_cost"] == "state * 24"

                assert "weekly_cost" in attributes
                assert attributes["weekly_cost"] == "state * 24 * 7"

                assert "monthly_cost" in attributes
                assert attributes["monthly_cost"] == "state * 24 * 30"

                print(f"✅ Entity ID self-reference replacement test passed!")
                print(f"   Original formula contained: sensor.entity_id_attribute_test * 24")
                print(f"   Processed formula uses: state * 24")

                # Clean up
                await storage_manager.async_delete_sensor_set(sensor_set_id)

        # Run the async test
        import asyncio

        asyncio.run(run_test())

    def test_evaluation_order_validation(
        self, mock_hass, mock_entity_registry, mock_states, config_manager, evaluation_order_yaml
    ):
        """Test that attributes are evaluated in correct order."""
        config = config_manager.load_from_yaml(evaluation_order_yaml)
        sensor = config.sensors[0]

        # Create sensor manager with data provider
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {"value": 1000.0, "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities(
            {"sensor.span_panel_instantaneous_power"}, allow_ha_lookups=False, change_notifier=None
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"evaluation_order_test": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 250.0  # state * 0.25 = 1000 * 0.25 = 250

        # Test attribute formula evaluation with context from main result
        if len(sensor.formulas) > 1:
            attribute_formula = sensor.formulas[1]
            context = {"state": main_result["value"]}

            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)
            assert attr_result["success"] is True
            assert attr_result["value"] == 250.0  # state = 250

    def test_attribute_state_without_context(self, mock_hass, mock_entity_registry, mock_states, config_manager):
        """Test attribute formula without proper context fails."""
        yaml_content = """
version: "1.0"

sensors:
  test_sensor:
    name: "Test Sensor"
    entity_id: sensor.span_panel_instantaneous_power
    formula: state * 2
    attributes:
      test_attr:
        formula: state * 3  # Should fail without context
        metadata:
          unit_of_measurement: W
    metadata:
      unit_of_measurement: W
      device_class: power
      state_class: measurement
      icon: mdi:flash
"""
        config = config_manager.load_from_yaml(yaml_content)
        sensor = config.sensors[0]

        # Create sensor manager with data provider
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {"value": 1000.0, "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities(
            {"sensor.span_panel_instantaneous_power"}, allow_ha_lookups=False, change_notifier=None
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"test_sensor": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 2000.0  # state * 2 = 1000 * 2 = 2000

        # Test attribute formula evaluation without context
        if len(sensor.formulas) > 1:
            attribute_formula = sensor.formulas[1]
            # No context provided

            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, {}, sensor)
            assert attr_result["success"] is False
            assert "state" in attr_result["error"].lower()

    def test_complex_attribute_calculations(self, mock_hass, mock_entity_registry, mock_states, config_manager):
        """Test complex calculations in attribute formulas."""
        yaml_content = """
version: "1.0"

sensors:
  complex_calculation_test:
    name: "Complex Calculation Test"
    entity_id: sensor.span_panel_instantaneous_power
    formula: state * 1.1  # Main result = 1100W
    attributes:
      weekly_kwh:
        formula: (state * 24 * 7) / 1000  # Convert to kWh
        metadata:
          unit_of_measurement: kWh
    metadata:
      unit_of_measurement: W
      device_class: power
      state_class: measurement
      icon: mdi:flash
"""
        config = config_manager.load_from_yaml(yaml_content)
        sensor = config.sensors[0]

        # Create sensor manager with data provider
        def mock_data_provider(entity_id: str):
            if entity_id == "sensor.span_panel_instantaneous_power":
                return {"value": 1000.0, "exists": True}
            return {"value": None, "exists": False}

        mock_add_entities = MagicMock()
        sensor_manager = SensorManager(
            config_manager._hass,
            MagicMock(),  # name_resolver
            mock_add_entities,  # add_entities_callback
            SensorManagerConfig(data_provider_callback=mock_data_provider),
        )

        # Register the backing entity
        sensor_manager.register_data_provider_entities(
            {"sensor.span_panel_instantaneous_power"}, allow_ha_lookups=False, change_notifier=None
        )

        # Register the sensor-to-backing mapping
        sensor_to_backing_mapping = {"complex_calculation_test": "sensor.span_panel_instantaneous_power"}
        sensor_manager.register_sensor_to_backing_mapping(sensor_to_backing_mapping)

        # Test main formula evaluation first
        evaluator = sensor_manager._evaluator
        main_formula = sensor.formulas[0]
        main_result = evaluator.evaluate_formula_with_sensor_config(main_formula, None, sensor)
        assert main_result["success"] is True
        assert main_result["value"] == 1100.0  # state * 1.1 = 1000 * 1.1 = 1100

        # Test attribute formula evaluation with context from main result
        if len(sensor.formulas) > 1:
            attribute_formula = sensor.formulas[1]
            context = {"state": main_result["value"]}

            attr_result = evaluator.evaluate_formula_with_sensor_config(attribute_formula, context, sensor)
            assert attr_result["success"] is True
            # Complex calculation: (state * 24 * 7) / 1000 = (1100 * 24 * 7) / 1000 = 184.8
            assert abs(attr_result["value"] - 184.8) < 0.1
