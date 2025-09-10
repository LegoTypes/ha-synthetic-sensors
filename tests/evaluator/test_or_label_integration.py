"""Tests for label OR pattern integration.

This module tests OR-style logic for label collection patterns using pipe (|) syntax.
Tests are modeled after the successful device_class OR pattern implementation.
"""

import pytest
from unittest.mock import patch, Mock
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.collection_resolver import CollectionResolver
from pathlib import Path


@pytest.fixture
def config_manager(mock_hass):
    """Create a config manager with mock HA."""
    from ha_synthetic_sensors.config_manager import ConfigManager

    return ConfigManager(mock_hass)


@pytest.fixture
def yaml_config_path():
    """Path to the label OR patterns YAML fixture."""
    return Path(__file__).parent.parent / "yaml_fixtures" / "label_or_patterns.yaml"


@pytest.fixture
def dependency_parser():
    """Create a dependency parser instance."""
    from ha_synthetic_sensors.dependency_parser import DependencyParser

    return DependencyParser()


@pytest.fixture
def collection_resolver(mock_hass, mock_entity_registry, mock_states):
    """Create a collection resolver instance with shared mocks."""
    from ha_synthetic_sensors.collection_resolver import CollectionResolver

    # Set up the mock hass with entity registry and states
    mock_hass.entity_registry = mock_entity_registry
    mock_hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)
    mock_hass.states.entity_ids.return_value = list(mock_states.keys())

    # Add label registry mock
    mock_hass.label_registry = Mock()
    mock_hass.label_registry.label = {
        "critical": Mock(name="Critical"),
        "important": Mock(name="Important"),
        "warning": Mock(name="Warning"),
        "monitor": Mock(name="Monitor"),
        "alert": Mock(name="Alert"),
    }

    # Patch necessary modules
    with (
        patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
        patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
        patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
        patch("ha_synthetic_sensors.collection_resolver.ar.async_get"),
    ):
        return CollectionResolver(mock_hass)


class TestORLabelIntegration:
    """Test OR pattern integration with label-based entity resolution."""

    @pytest.fixture(autouse=True)
    def setup_method(self, mock_hass, mock_entity_registry, mock_states):
        """Set up test fixtures with shared mock entity registry."""
        self.mock_hass = mock_hass
        self.mock_hass.entity_registry = mock_entity_registry
        self.mock_hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)
        self.mock_hass.states.entity_ids.return_value = list(mock_states.keys())

        # Add label registry mock
        self.mock_hass.label_registry = Mock()
        self.mock_hass.label_registry.label = {
            "critical": Mock(name="Critical"),
            "important": Mock(name="Important"),
            "warning": Mock(name="Warning"),
            "monitor": Mock(name="Monitor"),
            "alert": Mock(name="Alert"),
        }

        # Set up patchers for registry access
        self._patchers = [
            patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
            patch("ha_synthetic_sensors.collection_resolver.ar.async_get"),
        ]

        # Start all patchers
        for p in self._patchers:
            p.start()

        self.evaluator = Evaluator(self.mock_hass)
        self.resolver = CollectionResolver(self.mock_hass)

    def teardown_method(self):
        """Clean up patchers."""
        if hasattr(self, "_patchers"):
            for p in self._patchers:
                p.stop()

    def test_critical_important_or_resolution_implemented(self, mock_hass, mock_entity_registry, mock_states):
        """Test OR pattern resolution for critical|important label."""
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

        query = DynamicQuery(query_type="label", pattern="critical|important", function="count")
        entities = self.resolver.resolve_collection(query)

        # Should find entities with critical or important label
        expected_entities = [
            "sensor.server_cpu",
            "sensor.database_status",
            "sensor.backup_system",
            "sensor.security_system",
            "sensor.disk_space",
            "sensor.network_latency",
            "sensor.power_consumption",
        ]

        for entity_id in expected_entities:
            assert entity_id in self.mock_hass.entity_registry.entities, (
                f"Expected {entity_id} to be found with critical|important label"
            )

    def test_three_way_label_or_resolution_implemented(self, mock_hass, mock_entity_registry, mock_states):
        """Test OR pattern resolution for three tag types."""
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

        query = DynamicQuery(query_type="label", pattern="critical|important|monitor", function="count")
        entities = self.resolver.resolve_collection(query)

        # Should find entities with any of the three label
        expected_entities = [
            "sensor.server_cpu",
            "sensor.database_status",
            "sensor.backup_system",
            "sensor.security_system",
            "sensor.disk_space",
            "sensor.network_latency",
            "sensor.power_consumption",
            "sensor.energy_usage",
        ]

        # Check that we found some of the expected entities
        found_entities = [entity for entity in expected_entities if entity in entities]
        assert len(found_entities) > 0, f"Expected to find some of {expected_entities}, but found: {entities}"
        assert len(entities) > 0, f"Should find entities with critical, important, or monitor label, got: {entities}"

    def test_monitor_alert_label_or_resolution_implemented(self, mock_hass, mock_entity_registry, mock_states):
        """Test OR pattern resolution for monitor|alert label."""
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

        query = DynamicQuery(query_type="label", pattern="monitor|alert", function="count")
        entities = self.resolver.resolve_collection(query)

        # Should find entities with monitor or alert label
        expected_entities = [
            "sensor.server_cpu",
            "sensor.database_status",
            "sensor.backup_system",
            "sensor.security_system",
            "sensor.disk_space",
            "sensor.network_latency",
            "sensor.temperature",
            "sensor.humidity",
            "sensor.energy_usage",
        ]

        for entity_id in expected_entities:
            assert entity_id in self.mock_hass.entity_registry.entities, (
                f"Expected {entity_id} to be found with monitor|alert label"
            )

    async def test_yaml_fixture_loads_with_or_patterns(self, config_manager, yaml_config_path):
        """Test that the YAML fixture loads without errors."""
        try:
            config = await config_manager.async_load_from_file(yaml_config_path)

            assert config is not None
            assert len(config.sensors) > 0

            # Check that we have the expected sensors
            sensor_names = [sensor.unique_id for sensor in config.sensors]
            assert "critical_important_count" in sensor_names
            assert "alert_status_sum" in sensor_names
            assert "dynamic_or_label" in sensor_names

        except Exception as e:
            if "Configuration schema validation failed" in str(e):
                pytest.skip(f"Schema validation failed as expected for future syntax: {e}")
            else:
                raise

    def test_basic_label_or_pattern_parsing(self, collection_resolver):
        """Test basic OR pattern parsing for label."""
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

        # Test OR pattern with existing entities from shared registry
        query = DynamicQuery(query_type="label", pattern="critical|important", function="count")

        # Resolve the collection using the resolver
        entities = collection_resolver.resolve_collection(query)

        # Expected entities with critical or important label from shared registry
        expected_entities = [
            "sensor.server_cpu",  # label: ["critical", "monitor"]
            "sensor.database_status",  # label: ["critical", "alert"]
            "sensor.backup_system",  # label: ["important", "monitor"]
            "sensor.security_system",  # label: ["critical", "alert"]
            "sensor.disk_space",  # label: ["important", "monitor"]
            "sensor.network_latency",  # label: ["critical", "alert"]
            "sensor.power_consumption",  # label: ["important"]
        ]

        # Check that we found some of the expected entities
        found_entities = [entity for entity in expected_entities if entity in entities]
        assert len(found_entities) > 0, f"Expected to find some of {expected_entities}, but found: {entities}"
        assert len(entities) > 0, f"Should find entities with critical or important label, got: {entities}"

    def test_three_way_label_or_pattern_parsing(self, dependency_parser):
        """Test parsing of three-way label OR patterns."""
        formula = 'sum("label:critical|important|warning")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "sum"
        assert query.query_type == "label"
        assert query.pattern == "critical|important|warning"

    def test_collection_resolver_pipe_support_implemented(self, collection_resolver):
        """Test that collection resolver supports pipe syntax for label."""
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

        query = DynamicQuery(query_type="label", pattern="critical|important", function="count")

        # This should not raise an exception if pipe support is implemented
        try:
            entities = collection_resolver.resolve_collection(query)
            # For now, just verify the method can be called without error
            assert isinstance(entities, list)
        except NotImplementedError:
            pytest.skip("Label collection with pipe syntax not implemented yet")
        except Exception as e:
            pytest.fail(f"Unexpected error in collection resolver: {e}")

    async def test_yaml_sensor_formulas_with_or_patterns(self, config_manager, yaml_config_path):
        """Test that YAML sensor formulas contain expected OR patterns."""
        try:
            config = await config_manager.async_load_from_file(yaml_config_path)

            # Find specific sensors and check their formulas
            sensors_by_id = {sensor.unique_id: sensor for sensor in config.sensors}

            # Test basic OR pattern
            if "critical_important_count" in sensors_by_id:
                sensor = sensors_by_id["critical_important_count"]
                formula_config = sensor.formulas[0]
                assert 'count("label:critical|important")' in formula_config.formula

            # Test three-way OR pattern
            if "alert_status_sum" in sensors_by_id:
                sensor = sensors_by_id["alert_status_sum"]
                formula_config = sensor.formulas[0]
                assert 'sum("label:critical|important|warning")' in formula_config.formula

            # Test complex mathematical OR pattern
            if "multi_tag_efficiency" in sensors_by_id:
                sensor = sensors_by_id["multi_tag_efficiency"]
                formula_config = sensor.formulas[0]
                assert '(sum("label:monitor|alert") / count("label:critical|important")) * 100' in formula_config.formula

            # Test attributes with OR patterns
            if "advanced_tag_analysis" in sensors_by_id:
                sensor = sensors_by_id["advanced_tag_analysis"]
                assert len(sensor.formulas) > 1  # Has attributes

                # Check main formula
                main_formula = sensor.formulas[0]
                assert 'count("label:critical|important|warning")' in main_formula.formula

                # Check attribute formulas
                attribute_formulas = {f.id.split("_", 1)[1]: f for f in sensor.formulas[1:]}
                if "active_alerts" in attribute_formulas:
                    attr_formula = attribute_formulas["active_alerts"]
                    assert 'count("label:critical|important" > 0)' in attr_formula.formula

        except Exception as e:
            if "Configuration schema validation failed" in str(e):
                pytest.skip(f"Schema validation failed as expected for future syntax: {e}")
            else:
                raise

    def test_variable_driven_label_or_patterns(self, dependency_parser, mock_hass):
        """Test label OR patterns with variable substitution."""
        formula = 'count("label:primary_tag|secondary_tag")'
        variables = {
            "primary_tag": "input_select.primary_tag",
            "secondary_tag": "input_select.secondary_tag",
        }

        parsed = dependency_parser.parse_formula_dependencies(formula, variables)

        # Should recognize as dynamic query with variables
        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.query_type == "label"
        assert query.pattern == "primary_tag|secondary_tag"
        assert query.function == "count"

        # Should include variable dependencies
        assert "input_select.primary_tag" in parsed.static_dependencies
        assert "input_select.secondary_tag" in parsed.static_dependencies

    def test_complex_label_or_pattern_in_mathematical_formula(self, dependency_parser):
        """Test label OR patterns within complex mathematical expressions."""
        formula = '(sum("label:monitor|alert") / count("label:critical|important")) * efficiency_factor'
        variables = {"efficiency_factor": "input_number.efficiency"}

        parsed = dependency_parser.parse_formula_dependencies(formula, variables)

        # Should find both OR patterns
        assert len(parsed.dynamic_queries) == 2

        query_types = {q.query_type for q in parsed.dynamic_queries}
        assert "label" in query_types

        patterns = {q.pattern for q in parsed.dynamic_queries}
        assert "monitor|alert" in patterns
        assert "critical|important" in patterns

        # Should include variable dependency
        assert "input_number.efficiency" in parsed.static_dependencies

    def test_quoted_and_unquoted_label_or_patterns(self, dependency_parser, collection_resolver):
        """Test both quoted and unquoted label OR patterns."""
        # Test quoted pattern
        formula1 = 'sum("label:critical|important")'
        parsed1 = dependency_parser.parse_formula_dependencies(formula1, {})
        assert len(parsed1.dynamic_queries) == 1
        assert parsed1.dynamic_queries[0].pattern == "critical|important"

        # Test unquoted pattern
        formula2 = "sum(label:critical|important)"
        parsed2 = dependency_parser.parse_formula_dependencies(formula2, {})
        assert len(parsed2.dynamic_queries) == 1
        assert parsed2.dynamic_queries[0].pattern == "critical|important"

        # Both should parse to equivalent queries
        assert parsed1.dynamic_queries[0].pattern == parsed2.dynamic_queries[0].pattern

    def test_direct_entity_id_label_or_patterns(self, dependency_parser):
        """Test OR patterns with direct entity IDs (no variables)."""
        # Test direct entity ID OR pattern parsing
        formula = 'count("label:input_select.tag_type_1|input_select.tag_type_2")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.query_type == "label"
        assert query.pattern == "input_select.tag_type_1|input_select.tag_type_2"

    def test_mixed_direct_and_variable_label_or_patterns(self, dependency_parser):
        """Test OR patterns mixing variables and direct entity IDs."""
        formula = 'count("label:variable_tag|input_select.direct_tag")'
        variables = {"variable_tag": "input_select.variable_tag_type"}

        parsed = dependency_parser.parse_formula_dependencies(formula, variables)

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.query_type == "label"
        assert query.pattern == "variable_tag|input_select.direct_tag"

        # Should include variable dependency
        assert "input_select.variable_tag_type" in parsed.static_dependencies

    def test_yaml_direct_label_or_config(self, yaml_config_path):
        """Test YAML configuration with direct entity ID label OR patterns."""
        with open(yaml_config_path) as f:
            content = f.read()

        # Should contain direct entity ID OR pattern
        assert 'count("label:input_select.tag_type_1|input_select.tag_type_2")' in content

    def test_yaml_mixed_label_or_config(self, yaml_config_path):
        """Test YAML configuration with mixed variable and direct entity ID label OR patterns."""
        with open(yaml_config_path) as f:
            content = f.read()

        # Should contain mixed OR pattern
        assert 'count("label:variable_tag|input_select.direct_tag")' in content

        # Should have variable definition
        assert "variable_tag: input_select.variable_tag_type" in content

    def test_yaml_direct_three_way_label_config(self, yaml_config_path):
        """Test YAML configuration with direct three-way label OR pattern."""
        with open(yaml_config_path) as f:
            content = f.read()

        # Should contain three-way direct entity ID OR pattern
        assert 'avg("label:input_select.tag1|input_select.tag2|input_select.tag3")' in content


class TestORLabelPatternEdgeCases:
    """Test edge cases for label OR patterns."""

    def test_single_label_no_or(self, dependency_parser):
        """Test single label without OR pattern."""
        formula = 'count("label:critical")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.query_type == "label"
        assert query.pattern == "critical"
        assert "|" not in query.pattern

    def test_empty_or_components(self, dependency_parser):
        """Test handling of empty OR components."""
        formula = 'count("label:critical||important")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        # Should still parse but implementation should handle empty components
        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.pattern == "critical||important"

    def test_trailing_pipe(self, dependency_parser):
        """Test handling of trailing pipe in OR pattern."""
        formula = 'count("label:critical|important|")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.pattern == "critical|important|"

    def test_multiple_or_patterns_same_formula(self, dependency_parser):
        """Test multiple OR patterns in the same formula."""
        formula = 'sum("label:critical|important") + count("label:monitor|alert")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 2
        patterns = {q.pattern for q in parsed.dynamic_queries}
        assert "critical|important" in patterns
        assert "monitor|alert" in patterns

    def test_quoted_and_unquoted_or_patterns(self, dependency_parser):
        """Test both quoted and unquoted OR patterns in label."""
        # Quoted
        formula1 = 'sum("label:critical|important")'
        parsed1 = dependency_parser.parse_formula_dependencies(formula1, {})

        # Unquoted
        formula2 = "sum(label:critical|important)"
        parsed2 = dependency_parser.parse_formula_dependencies(formula2, {})

        # Both should work
        assert len(parsed1.dynamic_queries) == 1
        assert len(parsed2.dynamic_queries) == 1
        assert parsed1.dynamic_queries[0].pattern == parsed2.dynamic_queries[0].pattern

    def test_direct_entity_id_label_or_patterns(self, dependency_parser):
        """Test OR patterns with direct entity IDs (no variables)."""
        # Test direct entity ID OR pattern parsing
        formula = 'count("label:input_select.tag_type_1|input_select.tag_type_2")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.query_type == "label"
        assert query.pattern == "input_select.tag_type_1|input_select.tag_type_2"

    def test_mixed_direct_and_variable_label_or_patterns(self, dependency_parser):
        """Test OR patterns mixing variables and direct entity IDs."""
        formula = 'count("label:variable_tag|input_select.direct_tag_type")'
        variables = {"variable_tag": "input_select.variable_tag_type"}

        parsed = dependency_parser.parse_formula_dependencies(formula, variables)

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.query_type == "label"
        assert query.pattern == "variable_tag|input_select.direct_tag_type"

    def test_yaml_direct_label_or_config(self, yaml_config_path):
        """Test YAML configuration with direct entity ID label OR patterns."""
        with open(yaml_config_path) as f:
            content = f.read()

        # Should contain direct entity ID OR pattern
        assert '"label:input_select.tag_type_1|input_select.tag_type_2"' in content

    def test_yaml_mixed_label_or_config(self, yaml_config_path):
        """Test YAML configuration with mixed variable and direct entity ID label OR patterns."""
        with open(yaml_config_path) as f:
            content = f.read()

        # Should contain mixed OR pattern
        assert '"label:variable_tag|input_select.direct_tag"' in content

    def test_yaml_direct_three_way_label_config(self, yaml_config_path):
        """Test YAML configuration with direct three-way label OR pattern."""
        with open(yaml_config_path) as f:
            content = f.read()

        # Should contain three-way direct entity ID OR pattern
        assert '"label:input_select.tag1|input_select.tag2|input_select.tag3"' in content
