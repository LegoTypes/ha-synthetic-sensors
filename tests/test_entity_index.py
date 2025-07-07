"""Tests for entity index functionality."""

from ha_synthetic_sensors.config_manager import FormulaConfig, SensorConfig
from ha_synthetic_sensors.entity_index import EntityIndex


class TestEntityIndex:
    """Test entity index functionality."""

    def test_empty_index(self, mock_hass):
        """Test empty entity index."""
        index = EntityIndex(mock_hass)

        assert not index.contains("sensor.test")
        assert len(index.get_all_entities()) == 0

        stats = index.get_stats()
        assert stats["total_entities"] == 0
        assert stats["tracked_entities"] == 0

    def test_add_sensor_entities(self, mock_hass):
        """Test adding sensor entities to index."""
        index = EntityIndex(mock_hass)

        # Create sensor config with entity_id and formula variables
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            entity_id="sensor.my_custom_sensor",
            formulas=[
                FormulaConfig(
                    id="test_sensor",
                    formula='state("power_var") + state("temp_var")',
                    variables={
                        "power_var": "sensor.power_meter",
                        "temp_var": "sensor.temperature",
                        "not_entity": "some_string_value",  # Should be ignored
                    },
                )
            ],
        )

        index.add_sensor_entities(sensor_config)

        # Check that entity IDs were added
        assert index.contains("sensor.my_custom_sensor")
        assert index.contains("sensor.power_meter")
        assert index.contains("sensor.temperature")
        assert not index.contains("some_string_value")

        all_entities = index.get_all_entities()
        assert len(all_entities) == 3
        assert "sensor.my_custom_sensor" in all_entities
        assert "sensor.power_meter" in all_entities
        assert "sensor.temperature" in all_entities

    def test_remove_sensor_entities(self, mock_hass):
        """Test removing sensor entities from index."""
        index = EntityIndex(mock_hass)

        # Create and add sensor
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            entity_id="sensor.my_custom_sensor",
            formulas=[
                FormulaConfig(id="test_sensor", formula='state("power_var")', variables={"power_var": "sensor.power_meter"})
            ],
        )

        index.add_sensor_entities(sensor_config)
        assert index.contains("sensor.my_custom_sensor")
        assert index.contains("sensor.power_meter")

        # Remove sensor
        index.remove_sensor_entities(sensor_config)
        assert not index.contains("sensor.my_custom_sensor")
        assert not index.contains("sensor.power_meter")
        assert len(index.get_all_entities()) == 0

    def test_add_global_entities(self, mock_hass):
        """Test adding global variable entities to index."""
        index = EntityIndex(mock_hass)

        global_variables = {
            "power": "sensor.global_power",
            "temp": "sensor.global_temp",
            "not_entity": "some_value",  # Should be ignored
        }

        index.add_global_entities(global_variables)

        assert index.contains("sensor.global_power")
        assert index.contains("sensor.global_temp")
        assert not index.contains("some_value")

        all_entities = index.get_all_entities()
        assert len(all_entities) == 2

    def test_remove_global_entities(self, mock_hass):
        """Test removing global variable entities from index."""
        index = EntityIndex(mock_hass)

        global_variables = {"power": "sensor.global_power", "temp": "sensor.global_temp"}

        index.add_global_entities(global_variables)
        assert index.contains("sensor.global_power")
        assert index.contains("sensor.global_temp")

        index.remove_global_entities(global_variables)
        assert not index.contains("sensor.global_power")
        assert not index.contains("sensor.global_temp")
        assert len(index.get_all_entities()) == 0

    def test_entity_id_validation(self, mock_hass):
        """Test entity ID validation logic."""
        index = EntityIndex(mock_hass)

        # Test valid entity IDs
        assert index._is_entity_id("sensor.test")
        assert index._is_entity_id("light.living_room")
        assert index._is_entity_id("switch.kitchen_light")
        assert index._is_entity_id("binary_sensor.door_sensor")
        assert index._is_entity_id("input_select.test_123")

        # Test invalid entity IDs
        assert not index._is_entity_id("not_an_entity")
        assert not index._is_entity_id("sensor.")
        assert not index._is_entity_id(".test")
        assert not index._is_entity_id("sensor.test.extra")
        assert not index._is_entity_id("")
        assert not index._is_entity_id("123")
        assert not index._is_entity_id(None)

    def test_clear_index(self, mock_hass):
        """Test clearing the entity index."""
        index = EntityIndex(mock_hass)

        # Add some entities
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            entity_id="sensor.test",
            formulas=[FormulaConfig(id="test_sensor", formula='state("power_var")', variables={"power_var": "sensor.power"})],
        )

        index.add_sensor_entities(sensor_config)
        assert len(index.get_all_entities()) == 2

        # Clear index
        index.clear()
        assert len(index.get_all_entities()) == 0
        assert not index.contains("sensor.test")
        assert not index.contains("sensor.power")

    def test_stats(self, mock_hass):
        """Test entity index statistics."""
        index = EntityIndex(mock_hass)

        # Add entities
        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            entity_id="sensor.my_power",
            formulas=[
                FormulaConfig(
                    id="test_sensor",
                    formula='state("power_var")',
                    variables={"power_var": "sensor.power_meter"},
                )
            ],
        )

        index.add_sensor_entities(sensor_config)

        stats = index.get_stats()
        assert stats["total_entities"] == 2
        assert stats["tracked_entities"] == 2

    def test_multiple_formulas(self, mock_hass):
        """Test sensor with multiple formulas (main + attributes)."""
        index = EntityIndex(mock_hass)

        sensor_config = SensorConfig(
            unique_id="test_sensor",
            name="Test Sensor",
            formulas=[
                FormulaConfig(id="test_sensor", formula='state("main_var")', variables={"main_var": "sensor.main_power"}),
                FormulaConfig(id="test_sensor_attr1", formula='state("attr_var")', variables={"attr_var": "sensor.attr_power"}),
            ],
        )

        index.add_sensor_entities(sensor_config)

        assert index.contains("sensor.main_power")
        assert index.contains("sensor.attr_power")
        assert len(index.get_all_entities()) == 2
