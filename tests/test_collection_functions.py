"""Tests for collection function implementation."""

from unittest.mock import Mock, patch

from ha_synthetic_sensors.collection_resolver import CollectionResolver
from ha_synthetic_sensors.dependency_parser import DependencyParser, DynamicQuery
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.math_functions import MathFunctions


class TestCollectionFunctionParsing:
    """Test collection function pattern recognition and parsing."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = DependencyParser()

    def test_extract_dynamic_queries_regex(self):
        """Test extraction of regex-based dynamic queries."""
        formula = 'sum("regex:sensor\\.circuit_.*_power")'
        parsed = self.parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "sum"
        assert query.query_type == "regex"
        assert query.pattern == "sensor\\.circuit_.*_power"

    def test_extract_dynamic_queries_device_class(self):
        """Test extraction of device_class-based dynamic queries."""
        formula = 'avg("device_class:temperature")'
        parsed = self.parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "avg"
        assert query.query_type == "device_class"
        assert query.pattern == "temperature"

    def test_extract_dynamic_queries_tags(self):
        """Test extraction of tags-based dynamic queries."""
        formula = 'count("tags:critical,important")'
        parsed = self.parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "count"
        assert query.query_type == "tags"
        assert query.pattern == "critical,important"

    def test_extract_dynamic_queries_area(self):
        """Test extraction of area-based dynamic queries."""
        formula = 'max("area:kitchen device_class:power")'
        parsed = self.parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "max"
        assert query.query_type == "area"
        assert query.pattern == "kitchen device_class:power"

    def test_extract_dynamic_queries_attribute(self):
        """Test extraction of attribute-based dynamic queries."""
        formula = 'min("attribute:battery_level<20")'
        parsed = self.parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "min"
        assert query.query_type == "attribute"
        assert query.pattern == "battery_level<20"

    def test_extract_multiple_dynamic_queries(self):
        """Test extraction of multiple collection functions in one formula."""
        formula = 'sum("regex:sensor\\.power_.*") + avg("device_class:temperature")'
        parsed = self.parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 2

        # First query
        assert parsed.dynamic_queries[0].function == "sum"
        assert parsed.dynamic_queries[0].query_type == "regex"
        assert parsed.dynamic_queries[0].pattern == "sensor\\.power_.*"

        # Second query
        assert parsed.dynamic_queries[1].function == "avg"
        assert parsed.dynamic_queries[1].query_type == "device_class"
        assert parsed.dynamic_queries[1].pattern == "temperature"

    def test_extract_unquoted_queries(self):
        """Test extraction of unquoted collection function patterns."""
        formula = "sum(regex:sensor\\.test_.*)"
        parsed = self.parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "sum"
        assert query.query_type == "regex"
        assert query.pattern == "sensor\\.test_.*"

    def test_all_aggregation_functions_supported(self):
        """Test that all aggregation functions are recognized."""
        functions = ["sum", "avg", "count", "min", "max", "std", "var"]

        for func in functions:
            formula = f'{func}("device_class:temperature")'
            parsed = self.parser.parse_formula_dependencies(formula, {})

            assert len(parsed.dynamic_queries) == 1
            query = parsed.dynamic_queries[0]
            assert query.function == func
            assert query.query_type == "device_class"
            assert query.pattern == "temperature"


class TestCollectionResolver:
    """Test collection function resolution logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = Mock()
        self.mock_hass.data = {}

        # Mock states for testing
        self.mock_states = {
            "sensor.circuit_a_power": Mock(state="150.5", entity_id="sensor.circuit_a_power", attributes={"device_class": "power"}),
            "sensor.circuit_b_power": Mock(state="225.3", entity_id="sensor.circuit_b_power", attributes={"device_class": "power"}),
            "sensor.kitchen_temperature": Mock(state="22.5", entity_id="sensor.kitchen_temperature", attributes={"device_class": "temperature"}),
            "sensor.living_room_temperature": Mock(state="21.8", entity_id="sensor.living_room_temperature", attributes={"device_class": "temperature"}),
            "sensor.battery_device": Mock(state="85", entity_id="sensor.battery_device", attributes={"battery_level": 85}),
            "sensor.low_battery_device": Mock(state="15", entity_id="sensor.low_battery_device", attributes={"battery_level": 15}),
        }

        # Set up states mock
        self.mock_hass.states.entity_ids.return_value = list(self.mock_states.keys())
        self.mock_hass.states.get.side_effect = lambda entity_id: self.mock_states.get(entity_id)

        # Create resolver with mocked HA
        with patch("ha_synthetic_sensors.collection_resolver.er.async_get"), patch("ha_synthetic_sensors.collection_resolver.dr.async_get"), patch("ha_synthetic_sensors.collection_resolver.ar.async_get"):
            self.resolver = CollectionResolver(self.mock_hass)

    def test_resolve_regex_pattern(self):
        """Test regex pattern resolution."""
        query = DynamicQuery(query_type="regex", pattern="sensor\\.circuit_.*_power", function="sum")
        entities = self.resolver.resolve_collection(query)

        # Should match both circuit power sensors
        expected = ["sensor.circuit_a_power", "sensor.circuit_b_power"]
        assert set(entities) == set(expected)

    def test_resolve_device_class_pattern(self):
        """Test device class pattern resolution."""
        query = DynamicQuery(query_type="device_class", pattern="temperature", function="avg")
        entities = self.resolver.resolve_collection(query)

        # Should match both temperature sensors
        expected = ["sensor.kitchen_temperature", "sensor.living_room_temperature"]
        assert set(entities) == set(expected)

    def test_resolve_attribute_pattern_less_than(self):
        """Test attribute pattern with less than condition."""
        query = DynamicQuery(query_type="attribute", pattern="battery_level<20", function="count")
        entities = self.resolver.resolve_collection(query)

        # Should match only the low battery device
        expected = ["sensor.low_battery_device"]
        assert entities == expected

    def test_resolve_attribute_pattern_greater_than(self):
        """Test attribute pattern with greater than condition."""
        query = DynamicQuery(query_type="attribute", pattern="battery_level>80", function="count")
        entities = self.resolver.resolve_collection(query)

        # Should match only the high battery device
        expected = ["sensor.battery_device"]
        assert entities == expected

    def test_get_entity_values(self):
        """Test getting numeric values from entity IDs."""
        entity_ids = ["sensor.circuit_a_power", "sensor.circuit_b_power"]
        values = self.resolver.get_entity_values(entity_ids)

        expected = [150.5, 225.3]
        assert values == expected

    def test_get_entity_values_mixed_numeric_non_numeric(self):
        """Test getting values from mixed numeric/non-numeric entities."""
        # Add a non-numeric entity
        self.mock_states["sensor.status"] = Mock(state="ok", entity_id="sensor.status")
        self.mock_hass.states.entity_ids.return_value = list(self.mock_states.keys())

        entity_ids = ["sensor.circuit_a_power", "sensor.status"]
        values = self.resolver.get_entity_values(entity_ids)

        # Should only return numeric values
        expected = [150.5]
        assert values == expected

    def test_unknown_query_type(self):
        """Test handling of unknown query types."""
        query = DynamicQuery(query_type="unknown_type", pattern="test", function="sum")
        entities = self.resolver.resolve_collection(query)

        # Should return empty list for unknown query types
        assert entities == []


class TestMathFunctions:
    """Test enhanced math functions for collection functions."""

    def test_count_function(self):
        """Test count function."""
        # Test with individual arguments
        assert MathFunctions.count(1, 2, 3, None, 5) == 4

        # Test with iterable
        assert MathFunctions.count([1, 2, 3, None, 5]) == 4

        # Test with empty input
        assert MathFunctions.count() == 0

    def test_std_function(self):
        """Test standard deviation function."""
        # Test with individual arguments
        result = MathFunctions.std(1, 2, 3, 4, 5)
        expected = (2.0) ** 0.5  # Standard deviation of [1,2,3,4,5]
        assert abs(result - expected) < 0.01

        # Test with iterable
        result = MathFunctions.std([1, 2, 3, 4, 5])
        assert abs(result - expected) < 0.01

        # Test with insufficient values
        assert MathFunctions.std(1) == 0.0
        assert MathFunctions.std() == 0.0

    def test_var_function(self):
        """Test variance function."""
        # Test with individual arguments
        result = MathFunctions.var(1, 2, 3, 4, 5)
        expected = 2.0  # Variance of [1,2,3,4,5]
        assert abs(result - expected) < 0.01

        # Test with iterable
        result = MathFunctions.var([1, 2, 3, 4, 5])
        assert abs(result - expected) < 0.01

        # Test with insufficient values
        assert MathFunctions.var(1) == 0.0
        assert MathFunctions.var() == 0.0

    def test_builtin_functions_include_new_functions(self):
        """Test that new functions are included in builtin functions."""
        functions = MathFunctions.get_builtin_functions()

        assert "count" in functions
        assert "std" in functions
        assert "var" in functions
        assert callable(functions["count"])
        assert callable(functions["std"])
        assert callable(functions["var"])


class TestFormulaPreprocessing:
    """Test formula preprocessing with collection functions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_hass = Mock()
        self.mock_hass.data = {}

        # Mock successful registry initialization
        with patch("ha_synthetic_sensors.collection_resolver.er.async_get"), patch("ha_synthetic_sensors.collection_resolver.dr.async_get"), patch("ha_synthetic_sensors.collection_resolver.ar.async_get"):
            self.evaluator = Evaluator(self.mock_hass)

    def test_preprocess_formula_no_collection_functions(self):
        """Test formula preprocessing without collection functions."""
        formula = "sensor.power_meter + 10"
        result = self.evaluator._preprocess_formula_for_evaluation(formula)

        # Should normalize entity IDs but otherwise leave formula unchanged
        assert "sensor_power_meter" in result
        assert "sensor.power_meter" not in result

    def test_resolve_collection_functions_no_queries(self):
        """Test collection function resolution with no queries."""
        formula = "sensor.power_meter + 10"
        result = self.evaluator._resolve_collection_functions(formula)

        # Should return formula unchanged
        assert result == formula

    def test_resolve_collection_functions_with_queries(self):
        """Test collection function resolution with actual queries."""
        # Mock the collection resolver directly on the instance
        mock_resolver = Mock()
        mock_resolver.resolve_collection.return_value = ["sensor.test1", "sensor.test2"]
        mock_resolver.get_entity_values.return_value = [10.0, 20.0]
        self.evaluator._collection_resolver = mock_resolver

        formula = 'sum("regex:sensor\\.test.*")'
        result = self.evaluator._resolve_collection_functions(formula)

        # Should replace collection function with calculated result (new behavior)
        expected = "30.0"
        assert result == expected

    def test_resolve_collection_functions_no_matches(self):
        """Test collection function resolution when no entities match."""
        # Mock the collection resolver directly on the instance
        mock_resolver = Mock()
        mock_resolver.resolve_collection.return_value = []
        self.evaluator._collection_resolver = mock_resolver

        formula = 'sum("regex:sensor\\.nonexistent.*")'
        result = self.evaluator._resolve_collection_functions(formula)

        # Should replace with default value for sum (new behavior)
        expected = "0"
        assert result == expected

    def test_resolve_collection_functions_no_numeric_values(self):
        """Test collection function resolution when no numeric values found."""
        # Mock the collection resolver directly on the instance
        mock_resolver = Mock()
        mock_resolver.resolve_collection.return_value = ["sensor.test1"]
        mock_resolver.get_entity_values.return_value = []
        self.evaluator._collection_resolver = mock_resolver

        formula = 'sum("regex:sensor\\.test.*")'
        result = self.evaluator._resolve_collection_functions(formula)

        # Should replace with default value for sum (new behavior)
        expected = "0"
        assert result == expected
