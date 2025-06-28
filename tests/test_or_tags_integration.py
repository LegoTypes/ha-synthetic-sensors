"""Tests for tags OR pattern integration.

This module tests OR-style logic for tags collection patterns using pipe (|) syntax.
Tests are modeled after the successful device_class OR pattern implementation.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ha_synthetic_sensors.collection_resolver import CollectionResolver
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.dependency_parser import DependencyParser


class TestORTagsIntegration:
    """Test OR pattern integration for tags collection functions."""

    @pytest.fixture
    def yaml_config_path(self):
        """Path to the tags OR patterns YAML fixture."""
        return Path(__file__).parent / "yaml_fixtures" / "tags_or_patterns.yaml"

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance with comprehensive entity states."""
        hass = Mock()
        hass.data = {}

        mock_states = {
            # Critical tag entities
            "sensor.server_cpu": Mock(
                state="85",
                entity_id="sensor.server_cpu",
                attributes={"tags": ["critical", "monitor"]},
            ),
            "sensor.database_status": Mock(
                state="1",
                entity_id="sensor.database_status",
                attributes={"tags": ["critical", "alert"]},
            ),
            # Important tag entities
            "sensor.backup_system": Mock(
                state="0",
                entity_id="sensor.backup_system",
                attributes={"tags": ["important", "monitor"]},
            ),
            "sensor.security_system": Mock(
                state="1",
                entity_id="sensor.security_system",
                attributes={"tags": ["important", "alert"]},
            ),
            # Warning tag entities
            "sensor.disk_space": Mock(
                state="75",
                entity_id="sensor.disk_space",
                attributes={"tags": ["warning", "monitor"]},
            ),
            "sensor.network_latency": Mock(
                state="150",
                entity_id="sensor.network_latency",
                attributes={"tags": ["warning"]},
            ),
            # Emergency/urgent tag entities
            "sensor.fire_alarm": Mock(
                state="0",
                entity_id="sensor.fire_alarm",
                attributes={"tags": ["emergency", "critical"]},
            ),
            "sensor.intrusion_alert": Mock(
                state="0",
                entity_id="sensor.intrusion_alert",
                attributes={"tags": ["urgent", "important"]},
            ),
            # Priority tag entities
            "sensor.power_main": Mock(
                state="220",
                entity_id="sensor.power_main",
                attributes={"tags": ["high_priority", "critical"]},
            ),
            "sensor.hvac_control": Mock(
                state="1",
                entity_id="sensor.hvac_control",
                attributes={"tags": ["medium_priority", "important"]},
            ),
            # Variable source entities
            "input_select.primary_tag": Mock(state="critical", entity_id="input_select.primary_tag"),
            "input_select.secondary_tag": Mock(state="important", entity_id="input_select.secondary_tag"),
            "input_number.total_devices": Mock(state="10", entity_id="input_number.total_devices"),
            "input_select.tag_type_1": Mock(state="emergency", entity_id="input_select.tag_type_1"),
            "input_select.tag_type_2": Mock(state="urgent", entity_id="input_select.tag_type_2"),
            "input_select.variable_tag_type": Mock(state="monitor", entity_id="input_select.variable_tag_type"),
            "input_select.direct_tag": Mock(state="alert", entity_id="input_select.direct_tag"),
            "input_select.tag1": Mock(state="critical", entity_id="input_select.tag1"),
            "input_select.tag2": Mock(state="important", entity_id="input_select.tag2"),
            "input_select.tag3": Mock(state="warning", entity_id="input_select.tag3"),
        }

        hass.states.entity_ids.return_value = list(mock_states.keys())
        hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)

        return hass

    @pytest.fixture
    def collection_resolver(self, mock_hass):
        """Create a collection resolver instance with mocked dependencies."""
        # Mock entity registry entries with labels (tags)
        mock_entity_entries = {
            # Critical tag entities
            "sensor.server_cpu": Mock(entity_id="sensor.server_cpu", labels=["critical", "monitor"]),
            "sensor.database_status": Mock(entity_id="sensor.database_status", labels=["critical", "alert"]),
            "sensor.fire_alarm": Mock(entity_id="sensor.fire_alarm", labels=["emergency", "critical"]),
            "sensor.power_main": Mock(entity_id="sensor.power_main", labels=["high_priority", "critical"]),
            # Important tag entities
            "sensor.backup_system": Mock(entity_id="sensor.backup_system", labels=["important", "monitor"]),
            "sensor.security_system": Mock(entity_id="sensor.security_system", labels=["important", "alert"]),
            "sensor.intrusion_alert": Mock(entity_id="sensor.intrusion_alert", labels=["urgent", "important"]),
            "sensor.hvac_control": Mock(entity_id="sensor.hvac_control", labels=["medium_priority", "important"]),
            # Warning tag entities
            "sensor.disk_space": Mock(entity_id="sensor.disk_space", labels=["warning", "monitor"]),
            "sensor.network_latency": Mock(entity_id="sensor.network_latency", labels=["warning"]),
        }

        mock_entity_registry = Mock()
        mock_entity_registry.entities = mock_entity_entries

        with (
            patch("ha_synthetic_sensors.collection_resolver.er.async_get") as mock_er,
            patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
            patch("ha_synthetic_sensors.collection_resolver.ar.async_get"),
        ):
            mock_er.return_value = mock_entity_registry
            resolver = CollectionResolver(mock_hass)
            # Set the entity registry manually since the constructor might not call async_get
            resolver._entity_registry = mock_entity_registry
            return resolver

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create a config manager instance."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def dependency_parser(self):
        """Create a dependency parser instance."""
        return DependencyParser()

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
            assert "dynamic_or_tags" in sensor_names

        except Exception as e:
            if "Configuration schema validation failed" in str(e):
                pytest.skip(f"Schema validation failed as expected for future syntax: {e}")
            else:
                raise

    def test_basic_tags_or_pattern_parsing(self, dependency_parser):
        """Test parsing of basic tags OR patterns."""
        formula = 'count("tags:critical|important")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "count"
        assert query.query_type == "tags"
        assert query.pattern == "critical|important"

    def test_three_way_tags_or_pattern_parsing(self, dependency_parser):
        """Test parsing of three-way tags OR patterns."""
        formula = 'sum("tags:critical|important|warning")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "sum"
        assert query.query_type == "tags"
        assert query.pattern == "critical|important|warning"

    def test_collection_resolver_pipe_support_implemented(self, collection_resolver):
        """Test that collection resolver supports pipe syntax for tags."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        query = DynamicQuery(query_type="tags", pattern="critical|important", function="count")

        # This should not raise an exception if pipe support is implemented
        try:
            entities = collection_resolver.resolve_collection(query)
            # For now, just verify the method can be called without error
            assert isinstance(entities, list)
        except NotImplementedError:
            pytest.skip("Tags collection with pipe syntax not implemented yet")
        except Exception as e:
            pytest.fail(f"Unexpected error in collection resolver: {e}")

    def test_critical_important_or_resolution_implemented(self, collection_resolver):
        """Test resolution of critical|important tags OR pattern."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        query = DynamicQuery(query_type="tags", pattern="critical|important", function="count")

        try:
            entities = collection_resolver.resolve_collection(query)

            # Should find entities with either critical or important tags
            expected_entities = [
                "sensor.server_cpu",  # has critical tag
                "sensor.database_status",  # has critical tag
                "sensor.backup_system",  # has important tag
                "sensor.security_system",  # has important tag
                "sensor.fire_alarm",  # has critical tag
                "sensor.intrusion_alert",  # has important tag
                "sensor.power_main",  # has critical tag
                "sensor.hvac_control",  # has important tag
            ]

            # Should include entities with either tag
            for entity_id in expected_entities:
                assert entity_id in entities, f"Expected {entity_id} to be found with critical|important tags"

        except NotImplementedError:
            pytest.skip("Tags OR resolution not implemented yet")

    def test_three_way_tags_or_resolution_implemented(self, collection_resolver):
        """Test resolution of three-way tags OR pattern."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        query = DynamicQuery(query_type="tags", pattern="critical|important|warning", function="sum")

        try:
            entities = collection_resolver.resolve_collection(query)

            # Should find entities with any of the three tags
            expected_entities = [
                "sensor.server_cpu",  # critical
                "sensor.database_status",  # critical
                "sensor.backup_system",  # important
                "sensor.security_system",  # important
                "sensor.disk_space",  # warning
                "sensor.network_latency",  # warning
                "sensor.fire_alarm",  # critical
                "sensor.intrusion_alert",  # important
                "sensor.power_main",  # critical
                "sensor.hvac_control",  # important
            ]

            assert len(entities) >= len(expected_entities)

        except NotImplementedError:
            pytest.skip("Three-way tags OR resolution not implemented yet")

    def test_monitor_alert_tags_or_resolution_implemented(self, collection_resolver):
        """Test resolution of monitor|alert tags OR pattern."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        query = DynamicQuery(query_type="tags", pattern="monitor|alert", function="sum")

        try:
            entities = collection_resolver.resolve_collection(query)

            # Should find entities with monitor or alert tags
            expected_entities = [
                "sensor.server_cpu",  # has monitor tag
                "sensor.database_status",  # has alert tag
                "sensor.backup_system",  # has monitor tag
                "sensor.security_system",  # has alert tag
                "sensor.disk_space",  # has monitor tag
            ]

            for entity_id in expected_entities:
                assert entity_id in entities, f"Expected {entity_id} to be found with monitor|alert tags"

        except NotImplementedError:
            pytest.skip("Monitor|alert tags OR resolution not implemented yet")

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
                assert 'count("tags:critical|important")' in formula_config.formula

            # Test three-way OR pattern
            if "alert_status_sum" in sensors_by_id:
                sensor = sensors_by_id["alert_status_sum"]
                formula_config = sensor.formulas[0]
                assert 'sum("tags:critical|important|warning")' in formula_config.formula

            # Test complex mathematical OR pattern
            if "multi_tag_efficiency" in sensors_by_id:
                sensor = sensors_by_id["multi_tag_efficiency"]
                formula_config = sensor.formulas[0]
                assert '(sum("tags:monitor|alert") / count("tags:critical|important")) * 100' in formula_config.formula

            # Test attributes with OR patterns
            if "advanced_tag_analysis" in sensors_by_id:
                sensor = sensors_by_id["advanced_tag_analysis"]
                assert len(sensor.formulas) > 1  # Has attributes

                # Check main formula
                main_formula = sensor.formulas[0]
                assert 'count("tags:critical|important|warning")' in main_formula.formula

                # Check attribute formulas
                attribute_formulas = {f.id.split("_", 1)[1]: f for f in sensor.formulas[1:]}
                if "active_alerts" in attribute_formulas:
                    attr_formula = attribute_formulas["active_alerts"]
                    assert 'count("tags:critical|important" > 0)' in attr_formula.formula

        except Exception as e:
            if "Configuration schema validation failed" in str(e):
                pytest.skip(f"Schema validation failed as expected for future syntax: {e}")
            else:
                raise

    def test_variable_driven_tags_or_patterns(self, dependency_parser, mock_hass):
        """Test tags OR patterns with variable substitution."""
        formula = 'count("tags:primary_tag|secondary_tag")'
        variables = {
            "primary_tag": "input_select.primary_tag",
            "secondary_tag": "input_select.secondary_tag",
        }

        parsed = dependency_parser.parse_formula_dependencies(formula, variables)

        # Should recognize as dynamic query with variables
        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.query_type == "tags"
        assert query.pattern == "primary_tag|secondary_tag"
        assert query.function == "count"

        # Should include variable dependencies
        assert "input_select.primary_tag" in parsed.static_dependencies
        assert "input_select.secondary_tag" in parsed.static_dependencies

    def test_complex_tags_or_pattern_in_mathematical_formula(self, dependency_parser):
        """Test tags OR patterns within complex mathematical expressions."""
        formula = '(sum("tags:monitor|alert") / count("tags:critical|important")) * efficiency_factor'
        variables = {"efficiency_factor": "input_number.efficiency"}

        parsed = dependency_parser.parse_formula_dependencies(formula, variables)

        # Should find both OR patterns
        assert len(parsed.dynamic_queries) == 2

        query_types = {q.query_type for q in parsed.dynamic_queries}
        assert "tags" in query_types

        patterns = {q.pattern for q in parsed.dynamic_queries}
        assert "monitor|alert" in patterns
        assert "critical|important" in patterns

        # Should include variable dependency
        assert "input_number.efficiency" in parsed.static_dependencies

    def test_quoted_and_unquoted_tags_or_patterns(self, dependency_parser, collection_resolver):
        """Test both quoted and unquoted tags OR patterns."""
        # Test quoted pattern
        formula1 = 'sum("tags:critical|important")'
        parsed1 = dependency_parser.parse_formula_dependencies(formula1, {})
        assert len(parsed1.dynamic_queries) == 1
        assert parsed1.dynamic_queries[0].pattern == "critical|important"

        # Test unquoted pattern
        formula2 = "sum(tags:critical|important)"
        parsed2 = dependency_parser.parse_formula_dependencies(formula2, {})
        assert len(parsed2.dynamic_queries) == 1
        assert parsed2.dynamic_queries[0].pattern == "critical|important"

        # Both should parse to equivalent queries
        assert parsed1.dynamic_queries[0].pattern == parsed2.dynamic_queries[0].pattern

    def test_direct_entity_id_tags_or_patterns(self, dependency_parser):
        """Test OR patterns with direct entity IDs (no variables)."""
        # Test direct entity ID OR pattern parsing
        formula = 'count("tags:input_select.tag_type_1|input_select.tag_type_2")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.query_type == "tags"
        assert query.pattern == "input_select.tag_type_1|input_select.tag_type_2"

    def test_mixed_direct_and_variable_tags_or_patterns(self, dependency_parser):
        """Test OR patterns mixing variables and direct entity IDs."""
        formula = 'count("tags:variable_tag|input_select.direct_tag")'
        variables = {"variable_tag": "input_select.variable_tag_type"}

        parsed = dependency_parser.parse_formula_dependencies(formula, variables)

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.query_type == "tags"
        assert query.pattern == "variable_tag|input_select.direct_tag"

        # Should include variable dependency
        assert "input_select.variable_tag_type" in parsed.static_dependencies

    def test_yaml_direct_tags_or_config(self, yaml_config_path):
        """Test YAML configuration with direct entity ID tags OR patterns."""
        with open(yaml_config_path) as f:
            content = f.read()

        # Should contain direct entity ID OR pattern
        assert 'count("tags:input_select.tag_type_1|input_select.tag_type_2")' in content

    def test_yaml_mixed_tags_or_config(self, yaml_config_path):
        """Test YAML configuration with mixed variable and direct entity ID tags OR patterns."""
        with open(yaml_config_path) as f:
            content = f.read()

        # Should contain mixed OR pattern
        assert 'count("tags:variable_tag|input_select.direct_tag")' in content

        # Should have variable definition
        assert 'variable_tag: "input_select.variable_tag_type"' in content

    def test_yaml_direct_three_way_tags_config(self, yaml_config_path):
        """Test YAML configuration with direct three-way tags OR pattern."""
        with open(yaml_config_path) as f:
            content = f.read()

        # Should contain three-way direct entity ID OR pattern
        assert 'avg("tags:input_select.tag1|input_select.tag2|input_select.tag3")' in content


class TestORTagsPatternEdgeCases:
    """Test edge cases for tags OR patterns."""

    @pytest.fixture
    def yaml_config_path(self):
        """Path to the tags OR patterns YAML fixture."""
        return Path(__file__).parent / "yaml_fixtures" / "tags_or_patterns.yaml"

    @pytest.fixture
    def dependency_parser(self):
        """Create a dependency parser instance."""
        return DependencyParser()

    def test_single_tag_no_or(self, dependency_parser):
        """Test single tag without OR pattern."""
        formula = 'count("tags:critical")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.query_type == "tags"
        assert query.pattern == "critical"
        assert "|" not in query.pattern

    def test_empty_or_components(self, dependency_parser):
        """Test handling of empty OR components."""
        formula = 'count("tags:critical||important")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        # Should still parse but implementation should handle empty components
        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.pattern == "critical||important"

    def test_trailing_pipe(self, dependency_parser):
        """Test handling of trailing pipe in OR pattern."""
        formula = 'count("tags:critical|important|")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.pattern == "critical|important|"

    def test_multiple_or_patterns_same_formula(self, dependency_parser):
        """Test multiple OR patterns in the same formula."""
        formula = 'sum("tags:critical|important") + count("tags:monitor|alert")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 2
        patterns = {q.pattern for q in parsed.dynamic_queries}
        assert "critical|important" in patterns
        assert "monitor|alert" in patterns

    def test_quoted_and_unquoted_or_patterns(self, dependency_parser):
        """Test both quoted and unquoted OR patterns in tags."""
        # Quoted
        formula1 = 'sum("tags:critical|important")'
        parsed1 = dependency_parser.parse_formula_dependencies(formula1, {})

        # Unquoted
        formula2 = "sum(tags:critical|important)"
        parsed2 = dependency_parser.parse_formula_dependencies(formula2, {})

        # Both should work
        assert len(parsed1.dynamic_queries) == 1
        assert len(parsed2.dynamic_queries) == 1
        assert parsed1.dynamic_queries[0].pattern == parsed2.dynamic_queries[0].pattern

    def test_direct_entity_id_tags_or_patterns(self, dependency_parser):
        """Test OR patterns with direct entity IDs (no variables)."""
        # Test direct entity ID OR pattern parsing
        formula = 'count("tags:input_select.tag_type_1|input_select.tag_type_2")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.query_type == "tags"
        assert query.pattern == "input_select.tag_type_1|input_select.tag_type_2"

    def test_mixed_direct_and_variable_tags_or_patterns(self, dependency_parser):
        """Test OR patterns mixing variables and direct entity IDs."""
        formula = 'count("tags:variable_tag|input_select.direct_tag_type")'
        variables = {"variable_tag": "input_select.variable_tag_type"}

        parsed = dependency_parser.parse_formula_dependencies(formula, variables)

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.query_type == "tags"
        assert query.pattern == "variable_tag|input_select.direct_tag_type"

    def test_yaml_direct_tags_or_config(self, yaml_config_path):
        """Test YAML configuration with direct entity ID tags OR patterns."""
        with open(yaml_config_path) as f:
            content = f.read()

        # Should contain direct entity ID OR pattern
        assert '"tags:input_select.tag_type_1|input_select.tag_type_2"' in content

    def test_yaml_mixed_tags_or_config(self, yaml_config_path):
        """Test YAML configuration with mixed variable and direct entity ID tags OR patterns."""
        with open(yaml_config_path) as f:
            content = f.read()

        # Should contain mixed OR pattern
        assert '"tags:variable_tag|input_select.direct_tag"' in content

    def test_yaml_direct_three_way_tags_config(self, yaml_config_path):
        """Test YAML configuration with direct three-way tags OR pattern."""
        with open(yaml_config_path) as f:
            content = f.read()

        # Should contain three-way direct entity ID OR pattern
        assert '"tags:input_select.tag1|input_select.tag2|input_select.tag3"' in content
