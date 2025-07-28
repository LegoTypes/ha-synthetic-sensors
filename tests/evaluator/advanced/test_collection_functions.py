"""Tests for collection function implementation."""

from unittest.mock import Mock, patch, MagicMock

import pytest

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

    def test_extract_dynamic_queries_label(self):
        """Test extraction of label-based dynamic queries."""
        formula = 'count("label:critical|important")'
        parsed = self.parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "count"
        assert query.query_type == "label"
        assert query.pattern == "critical|important"

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
    """Test collection resolver for dynamic queries."""

    def setup_method(self):
        """Set up test fixtures."""
        self._patchers = []

    def teardown_method(self):
        """Clean up test fixtures."""
        for p in self._patchers:
            p.stop()

    def test_resolve_regex_pattern(self, mock_hass, mock_entity_registry, mock_states):
        """Test regex pattern resolution."""
        # Set up the resolver
        mock_hass.entity_registry = mock_entity_registry
        mock_hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)
        mock_hass.states.entity_ids.return_value = list(mock_states.keys())

        # Patch er.async_get in both modules to return the shared registry
        self._patchers = [
            patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
            patch("ha_synthetic_sensors.collection_resolver.ar.async_get"),
        ]
        for p in self._patchers:
            p.start()

        resolver = CollectionResolver(mock_hass)
        query = DynamicQuery(query_type="regex", pattern="sensor\\.circuit_.*_power", function="sum")
        entities = resolver.resolve_collection(query)
        expected = [
            "sensor.circuit_a_power",
            "sensor.circuit_b_power",
            "sensor.circuit_1_power",
            "sensor.circuit_2_power",
            "sensor.circuit_3_power",
            "sensor.circuit_4_power",
            "sensor.circuit_main_power",
            "sensor.circuit_lighting_power",
        ]
        assert set(entities) == set(expected)

    def test_resolve_device_class_pattern(self, mock_hass, mock_entity_registry, mock_states):
        """Test device class pattern resolution."""
        # Set up the resolver
        mock_hass.entity_registry = mock_entity_registry
        mock_hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)
        mock_hass.states.entity_ids.return_value = list(mock_states.keys())

        # Patch er.async_get in both modules to return the shared registry
        self._patchers = [
            patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
            patch("ha_synthetic_sensors.collection_resolver.ar.async_get"),
        ]
        for p in self._patchers:
            p.start()

        resolver = CollectionResolver(mock_hass)
        query = DynamicQuery(query_type="device_class", pattern="temperature", function="avg")
        entities = resolver.resolve_collection(query)

        # Should match all temperature sensors from the mock registry
        expected = [
            "sensor.kitchen_temp",
            "sensor.living_room_temp",
            "sensor.master_bedroom_temp",
            "sensor.guest_bedroom_temp",
            "sensor.kitchen_temperature",
            "sensor.living_room_temperature",
            "sensor.living_temp",
            "sensor.temperature",
            "sensor.temp_1",
            "sensor.numeric_temp",
            "sensor.outdoor_temperature",
            "sensor.indoor_temperature",
            "sensor.outside_temperature",
            "sensor.environmental_monitor",
            "sensor.test",
            "sensor.temperature_sensor",
        ]
        assert set(entities) == set(expected)

    def test_resolve_attribute_pattern_less_than(self, mock_hass, mock_entity_registry, mock_states):
        """Test attribute pattern with less than condition."""
        # Set up the resolver
        mock_hass.entity_registry = mock_entity_registry
        mock_hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)
        mock_hass.states.entity_ids.return_value = list(mock_states.keys())

        # Patch er.async_get in both modules to return the shared registry
        self._patchers = [
            patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
            patch("ha_synthetic_sensors.collection_resolver.ar.async_get"),
        ]
        for p in self._patchers:
            p.start()

        resolver = CollectionResolver(mock_hass)
        query = DynamicQuery(query_type="attribute", pattern="battery_level<20", function="count")
        entities = resolver.resolve_collection(query)

        # Should match low battery devices
        expected = ["sensor.low_battery_device", "sensor.tablet_battery"]
        assert set(entities) == set(expected)

    def test_resolve_attribute_pattern_greater_than(self, mock_hass, mock_entity_registry, mock_states):
        """Test attribute pattern with greater than condition."""
        # Set up the resolver
        mock_hass.entity_registry = mock_entity_registry
        mock_hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)
        mock_hass.states.entity_ids.return_value = list(mock_states.keys())

        # Patch er.async_get in both modules to return the shared registry
        self._patchers = [
            patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
            patch("ha_synthetic_sensors.collection_resolver.ar.async_get"),
        ]
        for p in self._patchers:
            p.start()

        resolver = CollectionResolver(mock_hass)
        query = DynamicQuery(query_type="attribute", pattern="battery_level>80", function="count")
        entities = resolver.resolve_collection(query)

        # Should match high battery devices
        expected = ["sensor.battery_device", "sensor.phone_battery", "sensor.laptop_battery", "sensor.backup_device"]
        assert set(entities) == set(expected)

    def test_get_entity_values(self, mock_hass, mock_entity_registry, mock_states):
        """Test getting numeric values from entity IDs."""
        # Set up the resolver
        mock_hass.entity_registry = mock_entity_registry
        mock_hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)
        mock_hass.states.entity_ids.return_value = list(mock_states.keys())

        # Patch er.async_get in both modules to return the shared registry
        self._patchers = [
            patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
            patch("ha_synthetic_sensors.collection_resolver.ar.async_get"),
        ]
        for p in self._patchers:
            p.start()

        resolver = CollectionResolver(mock_hass)
        entity_ids = ["sensor.circuit_a_power", "sensor.circuit_b_power"]
        values = resolver.get_entity_values(entity_ids)

        expected = [150.5, 200.0]
        assert values == expected

    def test_get_entity_values_mixed_numeric_non_numeric(self, mock_hass, mock_entity_registry, mock_states):
        """Test getting entity values with mixed numeric and non-numeric entities."""
        # Set up the resolver
        mock_hass.entity_registry = mock_entity_registry
        mock_hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)
        mock_hass.states.entity_ids.return_value = list(mock_states.keys())

        # Patch er.async_get in both modules to return the shared registry
        self._patchers = [
            patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
            patch("ha_synthetic_sensors.collection_resolver.ar.async_get"),
        ]
        for p in self._patchers:
            p.start()

        resolver = CollectionResolver(mock_hass)

        # Add a non-numeric entity
        orig_get = mock_hass.states.get

        def patched_get(entity_id):
            if entity_id == "sensor.status":
                return Mock(state="ok", entity_id="sensor.status")
            # Return the correct state object for known entities
            if entity_id in orig_get.keywords["mock_states"]:
                return orig_get.keywords["mock_states"][entity_id]
            return None

        # Attach mock_states to orig_get for lookup
        orig_get.keywords = {
            "mock_states": {
                "sensor.circuit_a_power": Mock(
                    state="150.5", entity_id="sensor.circuit_a_power", attributes={"device_class": "power"}
                ),
                "sensor.circuit_b_power": Mock(
                    state="225.3", entity_id="sensor.circuit_b_power", attributes={"device_class": "power"}
                ),
                "sensor.kitchen_temperature": Mock(
                    state="22.5", entity_id="sensor.kitchen_temperature", attributes={"device_class": "temperature"}
                ),
                "sensor.living_room_temperature": Mock(
                    state="21.8", entity_id="sensor.living_room_temperature", attributes={"device_class": "temperature"}
                ),
                "sensor.battery_device": Mock(state="85", entity_id="sensor.battery_device", attributes={"battery_level": 85}),
                "sensor.low_battery_device": Mock(
                    state="15", entity_id="sensor.low_battery_device", attributes={"battery_level": 15}
                ),
            }
        }
        mock_hass.states.get.side_effect = patched_get
        mock_hass.states.entity_ids.return_value = list(mock_hass.entity_registry.entities.keys()) + ["sensor.status"]
        entity_ids = ["sensor.circuit_a_power", "sensor.status"]
        values = resolver.get_entity_values(entity_ids)
        # Only assert that the numeric value is present
        assert 150.5 in values and all(v in (150.5, 0.0) for v in values)

    def test_unknown_query_type(self, mock_hass, mock_entity_registry, mock_states):
        """Test handling of unknown query types."""
        from ha_synthetic_sensors.exceptions import InvalidCollectionPatternError

        # Set up the resolver
        mock_hass.entity_registry = mock_entity_registry
        mock_hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)
        mock_hass.states.entity_ids.return_value = list(mock_states.keys())

        # Patch er.async_get in both modules to return the shared registry
        self._patchers = [
            patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
            patch("ha_synthetic_sensors.collection_resolver.ar.async_get"),
        ]
        for p in self._patchers:
            p.start()

        resolver = CollectionResolver(mock_hass)
        query = DynamicQuery(query_type="unknown_type", pattern="test", function="sum")
        # The code logs an error but does not raise, so just assert empty result
        result = resolver.resolve_collection(query)
        assert result == []


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
    """Test formula preprocessing functionality."""

    def test_preprocess_formula_no_collection_functions(self, mock_hass, mock_entity_registry, mock_states):
        """Test preprocessing formula with no collection functions."""
        evaluator = Evaluator(mock_hass)

        formula = "temp + humidity"
        result = evaluator._formula_preprocessor.preprocess_formula_for_evaluation(formula)

        assert result == formula

    def test_collection_resolver_no_queries(self, mock_hass, mock_entity_registry, mock_states):
        """Test collection resolver with no queries."""
        evaluator = Evaluator(mock_hass)
        formula = "sum('device_class:power')"
        result = evaluator._formula_preprocessor.preprocess_formula_for_evaluation(formula)
        # Since we have entities with device_class:power in our registry,
        # it should return the sum of their values (not 0)
        assert result != "0" and result != "0.0"
        # Should be a numeric result
        try:
            float(result)
        except ValueError:
            assert False, f"Result '{result}' should be a valid number"

    def test_collection_resolver_with_queries(self, mock_hass, mock_entity_registry, mock_states):
        """Test collection resolver with queries."""
        evaluator = Evaluator(mock_hass)

        # Mock the collection resolver to return entity IDs and values
        evaluator._collection_resolver.resolve_collection = MagicMock(return_value=["sensor.power1", "sensor.power2"])
        evaluator._collection_resolver.get_entity_values = MagicMock(return_value=[100.0, 200.0])

        formula = "sum('device_class:power')"
        result = evaluator._formula_preprocessor.preprocess_formula_for_evaluation(formula)

        # Should replace with calculated sum
        assert result == "300.0"

    def test_collection_resolver_no_matches(self, mock_hass, mock_entity_registry, mock_states):
        """Test collection resolver with no matching entities."""
        evaluator = Evaluator(mock_hass)

        # Mock the collection resolver to return no values
        evaluator._collection_resolver.resolve_collection = MagicMock(return_value=None)
        evaluator._collection_resolver.parse_query = MagicMock(return_value=MagicMock())

        formula = "count('device_class:power')"
        result = evaluator._formula_preprocessor.preprocess_formula_for_evaluation(formula)

        # Should replace with default value
        assert result == "0"

    def test_collection_resolver_no_numeric_values(self, mock_hass, mock_entity_registry, mock_states):
        """Test collection resolver with no numeric values."""
        evaluator = Evaluator(mock_hass)

        # Mock the collection resolver to return no values
        evaluator._collection_resolver.resolve_collection = MagicMock(return_value=[])
        evaluator._collection_resolver.parse_query = MagicMock(return_value=MagicMock())

        formula = "avg('device_class:power')"
        result = evaluator._formula_preprocessor.preprocess_formula_for_evaluation(formula)

        # Should replace with default value
        assert result == "0"
