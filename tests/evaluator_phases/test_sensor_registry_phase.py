"""Tests for the sensor registry phase."""

import pytest

from ha_synthetic_sensors.evaluator_phases.sensor_registry import SensorRegistryPhase


class TestSensorRegistryPhase:
    """Test cases for the SensorRegistryPhase."""

    def test_register_sensor(self) -> None:
        """Test registering a sensor."""
        phase = SensorRegistryPhase()

        # Register a sensor
        phase.register_sensor("test_sensor", "sensor.test_sensor", 100.0)

        # Verify registration
        assert phase.is_sensor_registered("test_sensor")
        assert phase.get_sensor_value("test_sensor") == 100.0
        assert phase.get_sensor_entity_id("test_sensor") == "sensor.test_sensor"
        assert "test_sensor" in phase.get_registered_sensors()

    def test_register_sensor_with_string_value(self) -> None:
        """Test registering a sensor with string value."""
        phase = SensorRegistryPhase()

        # Register a sensor with string value
        phase.register_sensor("status_sensor", "sensor.status_sensor", "online")

        # Verify registration
        assert phase.is_sensor_registered("status_sensor")
        assert phase.get_sensor_value("status_sensor") == "online"
        assert phase.get_sensor_entity_id("status_sensor") == "sensor.status_sensor"

    def test_register_sensor_with_boolean_value(self) -> None:
        """Test registering a sensor with boolean value."""
        phase = SensorRegistryPhase()

        # Register a sensor with boolean value
        phase.register_sensor("alarm_sensor", "binary_sensor.alarm", True)

        # Verify registration
        assert phase.is_sensor_registered("alarm_sensor")
        assert phase.get_sensor_value("alarm_sensor") is True
        assert phase.get_sensor_entity_id("alarm_sensor") == "binary_sensor.alarm"

    def test_register_sensor_with_default_value(self) -> None:
        """Test registering a sensor with default value."""
        phase = SensorRegistryPhase()

        # Register a sensor without specifying initial value
        phase.register_sensor("default_sensor", "sensor.default_sensor")

        # Verify registration with default value
        assert phase.is_sensor_registered("default_sensor")
        assert phase.get_sensor_value("default_sensor") == 0.0
        assert phase.get_sensor_entity_id("default_sensor") == "sensor.default_sensor"

    def test_update_sensor_value(self) -> None:
        """Test updating a sensor's value."""
        phase = SensorRegistryPhase()

        # Register a sensor
        phase.register_sensor("test_sensor", "sensor.test_sensor", 100.0)

        # Update the value
        phase.update_sensor_value("test_sensor", 200.0)

        # Verify update
        assert phase.get_sensor_value("test_sensor") == 200.0

    def test_update_unregistered_sensor(self) -> None:
        """Test updating an unregistered sensor."""
        phase = SensorRegistryPhase()

        # Try to update an unregistered sensor
        phase.update_sensor_value("unregistered_sensor", 100.0)

        # Verify sensor is still not registered
        assert not phase.is_sensor_registered("unregistered_sensor")
        assert phase.get_sensor_value("unregistered_sensor") is None

    def test_get_sensor_value_unregistered(self) -> None:
        """Test getting value of unregistered sensor."""
        phase = SensorRegistryPhase()

        # Try to get value of unregistered sensor
        value = phase.get_sensor_value("unregistered_sensor")

        # Verify None is returned
        assert value is None

    def test_unregister_sensor(self) -> None:
        """Test unregistering a sensor."""
        phase = SensorRegistryPhase()

        # Register a sensor
        phase.register_sensor("test_sensor", "sensor.test_sensor", 100.0)

        # Verify it's registered
        assert phase.is_sensor_registered("test_sensor")

        # Unregister the sensor
        phase.unregister_sensor("test_sensor")

        # Verify it's no longer registered
        assert not phase.is_sensor_registered("test_sensor")
        assert phase.get_sensor_value("test_sensor") is None
        assert phase.get_sensor_entity_id("test_sensor") is None
        assert "test_sensor" not in phase.get_registered_sensors()

    def test_unregister_unregistered_sensor(self) -> None:
        """Test unregistering an unregistered sensor."""
        phase = SensorRegistryPhase()

        # Try to unregister an unregistered sensor
        phase.unregister_sensor("unregistered_sensor")

        # Verify no error occurs and sensor remains unregistered
        assert not phase.is_sensor_registered("unregistered_sensor")

    def test_get_registered_sensors(self) -> None:
        """Test getting all registered sensor names."""
        phase = SensorRegistryPhase()

        # Initially no sensors
        assert phase.get_registered_sensors() == set()

        # Register multiple sensors
        phase.register_sensor("sensor1", "sensor.sensor1", 100.0)
        phase.register_sensor("sensor2", "sensor.sensor2", 200.0)
        phase.register_sensor("sensor3", "sensor.sensor3", 300.0)

        # Verify all sensors are returned
        registered_sensors = phase.get_registered_sensors()
        assert registered_sensors == {"sensor1", "sensor2", "sensor3"}

        # Unregister one sensor
        phase.unregister_sensor("sensor2")

        # Verify updated list
        registered_sensors = phase.get_registered_sensors()
        assert registered_sensors == {"sensor1", "sensor3"}

    def test_get_sensor_entity_id(self) -> None:
        """Test getting entity ID for registered sensor."""
        phase = SensorRegistryPhase()

        # Register a sensor
        phase.register_sensor("test_sensor", "sensor.test_sensor", 100.0)

        # Get entity ID
        entity_id = phase.get_sensor_entity_id("test_sensor")
        assert entity_id == "sensor.test_sensor"

    def test_get_sensor_entity_id_unregistered(self) -> None:
        """Test getting entity ID for unregistered sensor."""
        phase = SensorRegistryPhase()

        # Try to get entity ID for unregistered sensor
        entity_id = phase.get_sensor_entity_id("unregistered_sensor")
        assert entity_id is None

    def test_get_sensor_registry(self) -> None:
        """Test getting the complete sensor registry."""
        phase = SensorRegistryPhase()

        # Register multiple sensors
        phase.register_sensor("sensor1", "sensor.sensor1", 100.0)
        phase.register_sensor("sensor2", "sensor.sensor2", "online")
        phase.register_sensor("sensor3", "binary_sensor.sensor3", True)

        # Get registry
        registry = phase.get_sensor_registry()

        # Verify registry contents
        expected_registry = {
            "sensor1": 100.0,
            "sensor2": "online",
            "sensor3": True,
        }
        assert registry == expected_registry

        # Verify it's a copy (modifying shouldn't affect original)
        registry["sensor1"] = 999.0
        assert phase.get_sensor_value("sensor1") == 100.0

    def test_get_sensor_entity_id_mapping(self) -> None:
        """Test getting the complete entity ID mapping."""
        phase = SensorRegistryPhase()

        # Register multiple sensors
        phase.register_sensor("sensor1", "sensor.sensor1", 100.0)
        phase.register_sensor("sensor2", "sensor.sensor2", 200.0)
        phase.register_sensor("sensor3", "binary_sensor.sensor3", True)

        # Get mapping
        mapping = phase.get_sensor_entity_id_mapping()

        # Verify mapping contents
        expected_mapping = {
            "sensor1": "sensor.sensor1",
            "sensor2": "sensor.sensor2",
            "sensor3": "binary_sensor.sensor3",
        }
        assert mapping == expected_mapping

        # Verify it's a copy (modifying shouldn't affect original)
        mapping["sensor1"] = "sensor.modified"
        assert phase.get_sensor_entity_id("sensor1") == "sensor.sensor1"

    def test_clear_registry(self) -> None:
        """Test clearing the entire registry."""
        phase = SensorRegistryPhase()

        # Register multiple sensors
        phase.register_sensor("sensor1", "sensor.sensor1", 100.0)
        phase.register_sensor("sensor2", "sensor.sensor2", 200.0)
        phase.register_sensor("sensor3", "sensor.sensor3", 300.0)

        # Verify sensors are registered
        assert len(phase.get_registered_sensors()) == 3

        # Clear registry
        phase.clear_registry()

        # Verify all sensors are unregistered
        assert phase.get_registered_sensors() == set()
        assert phase.get_sensor_value("sensor1") is None
        assert phase.get_sensor_value("sensor2") is None
        assert phase.get_sensor_value("sensor3") is None
        assert phase.get_sensor_entity_id("sensor1") is None
        assert phase.get_sensor_entity_id("sensor2") is None
        assert phase.get_sensor_entity_id("sensor3") is None

    def test_is_sensor_registered(self) -> None:
        """Test checking if a sensor is registered."""
        phase = SensorRegistryPhase()

        # Initially not registered
        assert not phase.is_sensor_registered("test_sensor")

        # Register sensor
        phase.register_sensor("test_sensor", "sensor.test_sensor", 100.0)

        # Now registered
        assert phase.is_sensor_registered("test_sensor")

        # Unregister sensor
        phase.unregister_sensor("test_sensor")

        # No longer registered
        assert not phase.is_sensor_registered("test_sensor")

    def test_get_registry_stats(self) -> None:
        """Test getting registry statistics."""
        phase = SensorRegistryPhase()

        # Initially empty
        stats = phase.get_registry_stats()
        assert stats["total_sensors"] == 0
        assert stats["registered_sensors"] == []
        assert stats["entity_id_mappings"] == 0

        # Register sensors
        phase.register_sensor("sensor1", "sensor.sensor1", 100.0)
        phase.register_sensor("sensor2", "sensor.sensor2", 200.0)
        phase.register_sensor("sensor3", "binary_sensor.sensor3", True)

        # Get updated stats
        stats = phase.get_registry_stats()
        assert stats["total_sensors"] == 3
        assert set(stats["registered_sensors"]) == {"sensor1", "sensor2", "sensor3"}
        assert stats["entity_id_mappings"] == 3

        # Unregister one sensor
        phase.unregister_sensor("sensor2")

        # Get updated stats
        stats = phase.get_registry_stats()
        assert stats["total_sensors"] == 2
        assert set(stats["registered_sensors"]) == {"sensor1", "sensor3"}
        assert stats["entity_id_mappings"] == 2

    def test_multiple_sensor_types(self) -> None:
        """Test handling multiple sensor types and values."""
        phase = SensorRegistryPhase()

        # Register different types of sensors
        phase.register_sensor("numeric_sensor", "sensor.numeric", 42.5)
        phase.register_sensor("string_sensor", "sensor.string", "active")
        phase.register_sensor("boolean_sensor", "binary_sensor.boolean", False)

        # Verify all values are stored correctly
        assert phase.get_sensor_value("numeric_sensor") == 42.5
        assert phase.get_sensor_value("string_sensor") == "active"
        assert phase.get_sensor_value("boolean_sensor") is False

        # Update values
        phase.update_sensor_value("numeric_sensor", 99.9)
        phase.update_sensor_value("string_sensor", "inactive")
        phase.update_sensor_value("boolean_sensor", True)

        # Verify updates
        assert phase.get_sensor_value("numeric_sensor") == 99.9
        assert phase.get_sensor_value("string_sensor") == "inactive"
        assert phase.get_sensor_value("boolean_sensor") is True
