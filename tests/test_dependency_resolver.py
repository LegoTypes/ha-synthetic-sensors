"""Tests for DependencyResolver class."""

from ha_synthetic_sensors.evaluator import DependencyResolver


class TestDependencyResolver:
    """Test DependencyResolver class methods."""

    def test_add_sensor_dependencies(self, mock_hass):
        """Test adding sensor dependencies."""
        resolver = DependencyResolver(mock_hass)

        # Add dependencies for sensor1
        deps1 = {"sensor.temp", "sensor.humidity"}
        resolver.add_sensor_dependencies("sensor1", deps1)

        # Verify dependencies were stored
        assert resolver.get_dependencies("sensor1") == deps1

        # Add dependencies for sensor2
        deps2 = {"sensor.power", "sensor.voltage"}
        resolver.add_sensor_dependencies("sensor2", deps2)

        # Verify both sensors have their dependencies
        assert resolver.get_dependencies("sensor1") == deps1
        assert resolver.get_dependencies("sensor2") == deps2

    def test_get_dependencies_nonexistent_sensor(self, mock_hass):
        """Test getting dependencies for non-existent sensor."""
        resolver = DependencyResolver(mock_hass)

        # Non-existent sensor should return empty set
        assert resolver.get_dependencies("nonexistent") == set()

    def test_get_dependent_sensors(self, mock_hass):
        """Test getting sensors that depend on a given entity."""
        resolver = DependencyResolver(mock_hass)

        # Add dependencies
        resolver.add_sensor_dependencies("sensor1", {"sensor.temp", "sensor.humidity"})
        resolver.add_sensor_dependencies("sensor2", {"sensor.temp", "sensor.power"})
        resolver.add_sensor_dependencies("sensor3", {"sensor.voltage"})

        # Check which sensors depend on sensor.temp
        dependent_on_temp = resolver.get_dependent_sensors("sensor.temp")
        assert dependent_on_temp == {"sensor1", "sensor2"}

        # Check which sensors depend on sensor.humidity
        dependent_on_humidity = resolver.get_dependent_sensors("sensor.humidity")
        assert dependent_on_humidity == {"sensor1"}

        # Check which sensors depend on sensor.voltage
        dependent_on_voltage = resolver.get_dependent_sensors("sensor.voltage")
        assert dependent_on_voltage == {"sensor3"}

        # Check non-existent dependency
        dependent_on_nonexistent = resolver.get_dependent_sensors("sensor.nonexistent")
        assert dependent_on_nonexistent == set()

    def test_get_update_order_no_dependencies(self, mock_hass):
        """Test update order with no dependencies between sensors."""
        resolver = DependencyResolver(mock_hass)

        # Add sensors with external dependencies only
        resolver.add_sensor_dependencies("sensor1", {"sensor.external1"})
        resolver.add_sensor_dependencies("sensor2", {"sensor.external2"})
        resolver.add_sensor_dependencies("sensor3", {"sensor.external3"})

        # Get update order
        sensors = {"sensor1", "sensor2", "sensor3"}
        order = resolver.get_update_order(sensors)

        # All sensors should be in the order (exact order may vary)
        assert set(order) == sensors
        assert len(order) == 3

    def test_get_update_order_with_dependencies(self, mock_hass):
        """Test update order with dependencies between sensors."""
        resolver = DependencyResolver(mock_hass)

        # Create dependency chain: sensor3 -> sensor2 -> sensor1
        resolver.add_sensor_dependencies("sensor1", {"sensor.external"})
        resolver.add_sensor_dependencies("sensor2", {"sensor1", "sensor.external"})
        resolver.add_sensor_dependencies("sensor3", {"sensor2", "sensor.external"})

        # Get update order
        sensors = {"sensor1", "sensor2", "sensor3"}
        order = resolver.get_update_order(sensors)

        # sensor1 should come before sensor2, sensor2 before sensor3
        assert order.index("sensor1") < order.index("sensor2")
        assert order.index("sensor2") < order.index("sensor3")
        assert set(order) == sensors

    def test_get_update_order_complex_dependencies(self, mock_hass):
        """Test update order with complex dependency graph."""
        resolver = DependencyResolver(mock_hass)

        # Complex dependency graph:
        # sensor1 -> no synthetic deps
        # sensor2 -> sensor1
        # sensor3 -> sensor1
        # sensor4 -> sensor2, sensor3
        resolver.add_sensor_dependencies("sensor1", {"sensor.external1"})
        resolver.add_sensor_dependencies("sensor2", {"sensor1", "sensor.external2"})
        resolver.add_sensor_dependencies("sensor3", {"sensor1", "sensor.external3"})
        resolver.add_sensor_dependencies("sensor4", {"sensor2", "sensor3", "sensor.external4"})

        # Get update order
        sensors = {"sensor1", "sensor2", "sensor3", "sensor4"}
        order = resolver.get_update_order(sensors)

        # Verify dependencies are respected
        assert order.index("sensor1") < order.index("sensor2")
        assert order.index("sensor1") < order.index("sensor3")
        assert order.index("sensor2") < order.index("sensor4")
        assert order.index("sensor3") < order.index("sensor4")
        assert set(order) == sensors

    def test_get_update_order_circular_dependency(self, mock_hass):
        """Test update order with circular dependency."""
        resolver = DependencyResolver(mock_hass)

        # Create circular dependency: sensor1 -> sensor2 -> sensor1
        resolver.add_sensor_dependencies("sensor1", {"sensor2"})
        resolver.add_sensor_dependencies("sensor2", {"sensor1"})

        # Get update order (should handle circular dependency gracefully)
        sensors = {"sensor1", "sensor2"}
        order = resolver.get_update_order(sensors)

        # Both sensors should be in the result
        assert set(order) == sensors
        assert len(order) == 2

    def test_detect_circular_dependencies_no_cycles(self, mock_hass):
        """Test circular dependency detection with no cycles."""
        resolver = DependencyResolver(mock_hass)

        # Linear dependency chain
        resolver.add_sensor_dependencies("sensor1", {"sensor.external"})
        resolver.add_sensor_dependencies("sensor2", {"sensor1"})
        resolver.add_sensor_dependencies("sensor3", {"sensor2"})

        # Should detect no cycles
        cycles = resolver.detect_circular_dependencies()
        assert cycles == []

    def test_detect_circular_dependencies_simple_cycle(self, mock_hass):
        """Test circular dependency detection with simple cycle."""
        resolver = DependencyResolver(mock_hass)

        # Create simple cycle: sensor1 -> sensor2 -> sensor1
        resolver.add_sensor_dependencies("sensor1", {"sensor2"})
        resolver.add_sensor_dependencies("sensor2", {"sensor1"})

        # Should detect the cycle
        cycles = resolver.detect_circular_dependencies()
        assert len(cycles) == 1

        # The cycle should contain both sensors
        cycle = cycles[0]
        assert set(cycle) == {"sensor1", "sensor2"}

    def test_detect_circular_dependencies_complex_cycle(self, mock_hass):
        """Test circular dependency detection with complex cycle."""
        resolver = DependencyResolver(mock_hass)

        # Create complex cycle: sensor1 -> sensor2 -> sensor3 -> sensor1
        resolver.add_sensor_dependencies("sensor1", {"sensor2"})
        resolver.add_sensor_dependencies("sensor2", {"sensor3"})
        resolver.add_sensor_dependencies("sensor3", {"sensor1"})

        # Should detect the cycle
        cycles = resolver.detect_circular_dependencies()
        assert len(cycles) == 1

        # The cycle should contain all three sensors
        cycle = cycles[0]
        assert set(cycle) == {"sensor1", "sensor2", "sensor3"}

    def test_detect_circular_dependencies_multiple_cycles(self, mock_hass):
        """Test circular dependency detection with multiple cycles."""
        resolver = DependencyResolver(mock_hass)

        # Create two separate cycles:
        # Cycle 1: sensor1 -> sensor2 -> sensor1
        # Cycle 2: sensor3 -> sensor4 -> sensor3
        resolver.add_sensor_dependencies("sensor1", {"sensor2"})
        resolver.add_sensor_dependencies("sensor2", {"sensor1"})
        resolver.add_sensor_dependencies("sensor3", {"sensor4"})
        resolver.add_sensor_dependencies("sensor4", {"sensor3"})

        # Should detect both cycles
        cycles = resolver.detect_circular_dependencies()
        assert len(cycles) == 2

        # Verify both cycles are detected
        cycle_sets = [set(cycle) for cycle in cycles]
        assert {"sensor1", "sensor2"} in cycle_sets
        assert {"sensor3", "sensor4"} in cycle_sets

    def test_clear_dependencies(self, mock_hass):
        """Test clearing dependencies for a sensor."""
        resolver = DependencyResolver(mock_hass)

        # Add dependencies
        resolver.add_sensor_dependencies("sensor1", {"sensor.temp", "sensor.humidity"})
        resolver.add_sensor_dependencies("sensor2", {"sensor.temp", "sensor.power"})

        # Verify dependencies exist
        assert resolver.get_dependencies("sensor1") == {"sensor.temp", "sensor.humidity"}
        assert resolver.get_dependent_sensors("sensor.temp") == {"sensor1", "sensor2"}

        # Clear sensor1 dependencies
        resolver.clear_dependencies("sensor1")

        # Verify sensor1 dependencies are cleared
        assert resolver.get_dependencies("sensor1") == set()

        # Verify reverse dependencies are updated
        assert resolver.get_dependent_sensors("sensor.temp") == {"sensor2"}
        assert resolver.get_dependent_sensors("sensor.humidity") == set()

        # Verify sensor2 dependencies are unchanged
        assert resolver.get_dependencies("sensor2") == {"sensor.temp", "sensor.power"}

    def test_clear_dependencies_nonexistent_sensor(self, mock_hass):
        """Test clearing dependencies for non-existent sensor."""
        resolver = DependencyResolver(mock_hass)

        # Clearing non-existent sensor should not raise error
        resolver.clear_dependencies("nonexistent")

        # Should still return empty set
        assert resolver.get_dependencies("nonexistent") == set()

    def test_evaluate_simple_formula(self, mock_hass):
        """Test evaluating a simple formula."""
        resolver = DependencyResolver(mock_hass)

        # Test simple arithmetic
        result = resolver.evaluate("2 + 3")
        assert result == 5.0

        # Test with context
        result = resolver.evaluate("a + b", {"a": 10, "b": 20})
        assert result == 30.0

    def test_evaluate_complex_formula(self, mock_hass):
        """Test evaluating complex formulas."""
        resolver = DependencyResolver(mock_hass)

        # Test with multiple operations
        result = resolver.evaluate("(a * b) + (c / d)", {"a": 2, "b": 3, "c": 12, "d": 4})
        assert result == 9.0  # (2*3) + (12/4) = 6 + 3 = 9

        # Test with mathematical operations (DependencyResolver doesn't have built-in functions)
        result = resolver.evaluate("a + b * c", {"a": 1, "b": 2, "c": 3})
        assert result == 7.0  # 1 + (2 * 3) = 7

    def test_evaluate_formula_error(self, mock_hass):
        """Test formula evaluation with errors."""
        resolver = DependencyResolver(mock_hass)

        # Test invalid formula (should return 0.0)
        result = resolver.evaluate("invalid_variable")
        assert result == 0.0

        # Test division by zero (should return 0.0)
        result = resolver.evaluate("1 / 0")
        assert result == 0.0

    def test_extract_variables_simple(self, mock_hass):
        """Test extracting variables from simple formulas."""
        resolver = DependencyResolver(mock_hass)

        # Simple variable
        variables = resolver.extract_variables("temperature")
        assert variables == {"temperature"}

        # Multiple variables
        variables = resolver.extract_variables("temp + humidity")
        assert variables == {"temp", "humidity"}

        # Variables with underscores and numbers
        variables = resolver.extract_variables("sensor_1 + device_2_temp")
        assert variables == {"sensor_1", "device_2_temp"}

    def test_extract_variables_with_builtins(self, mock_hass):
        """Test extracting variables excluding built-in functions."""
        resolver = DependencyResolver(mock_hass)

        # Should exclude built-in functions
        variables = resolver.extract_variables("abs(temperature) + max(humidity, 50)")
        assert variables == {"temperature", "humidity"}

        # Should exclude built-ins but include real variables
        variables = resolver.extract_variables("sum(values) + my_variable - min(data)")
        assert variables == {"values", "my_variable", "data"}

    def test_extract_variables_complex_formula(self, mock_hass):
        """Test extracting variables from complex formulas."""
        resolver = DependencyResolver(mock_hass)

        # Complex formula with various patterns
        formula = "sensor_temp * efficiency_factor + round(power_reading / 1000)"
        variables = resolver.extract_variables(formula)
        expected = {"sensor_temp", "efficiency_factor", "power_reading"}
        assert variables == expected

    def test_integration_add_clear_cycle(self, mock_hass):
        """Test integration of adding, checking, and clearing dependencies."""
        resolver = DependencyResolver(mock_hass)

        # Add complex dependency graph
        resolver.add_sensor_dependencies("sensor1", {"sensor.external1"})
        resolver.add_sensor_dependencies("sensor2", {"sensor1", "sensor.external2"})
        resolver.add_sensor_dependencies("sensor3", {"sensor2", "sensor.external3"})

        # Verify update order
        order = resolver.get_update_order({"sensor1", "sensor2", "sensor3"})
        assert order.index("sensor1") < order.index("sensor2")
        assert order.index("sensor2") < order.index("sensor3")

        # Clear middle sensor
        resolver.clear_dependencies("sensor2")

        # Verify sensor2 no longer has dependencies but sensor3 still depends on sensor2
        assert resolver.get_dependencies("sensor2") == set()
        assert resolver.get_dependencies("sensor3") == {"sensor2", "sensor.external3"}

        # Verify reverse dependencies are updated
        assert resolver.get_dependent_sensors("sensor1") == set()  # sensor2 no longer depends on sensor1
        assert resolver.get_dependent_sensors("sensor2") == {"sensor3"}  # sensor3 still depends on sensor2
