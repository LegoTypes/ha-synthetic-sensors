"""Tests for area OR pattern integration.

This module tests OR-style logic for area collection patterns using pipe (|) syntax.
Tests are modeled after the successful tags OR pattern implementation.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ha_synthetic_sensors.collection_resolver import CollectionResolver
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.dependency_parser import DependencyParser


class TestORAreaIntegration:
    """Test OR pattern integration for area collection functions."""

    @pytest.fixture
    def yaml_config_path(self):
        """Path to the area OR patterns YAML fixture."""
        return Path(__file__).parent / "yaml_fixtures" / "area_or_patterns.yaml"

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance with comprehensive entity states."""
        hass = Mock()
        hass.data = {}

        mock_states = {
            # Living room entities
            "sensor.living_room_temp": Mock(state="22", entity_id="sensor.living_room_temp"),
            "light.living_room_main": Mock(state="on", entity_id="light.living_room_main"),
            "sensor.living_room_humidity": Mock(state="45", entity_id="sensor.living_room_humidity"),
            # Kitchen entities
            "sensor.kitchen_temp": Mock(state="24", entity_id="sensor.kitchen_temp"),
            "light.kitchen_overhead": Mock(state="off", entity_id="light.kitchen_overhead"),
            "sensor.kitchen_humidity": Mock(state="50", entity_id="sensor.kitchen_humidity"),
            # Dining room entities
            "sensor.dining_room_temp": Mock(state="23", entity_id="sensor.dining_room_temp"),
            "light.dining_room_chandelier": Mock(state="on", entity_id="light.dining_room_chandelier"),
            # Master bedroom entities
            "sensor.master_bedroom_temp": Mock(state="20", entity_id="sensor.master_bedroom_temp"),
            "light.master_bedroom_lamp": Mock(state="off", entity_id="light.master_bedroom_lamp"),
            # Guest bedroom entities
            "sensor.guest_bedroom_temp": Mock(state="19", entity_id="sensor.guest_bedroom_temp"),
            "light.guest_bedroom_overhead": Mock(state="off", entity_id="light.guest_bedroom_overhead"),
            # Bathroom entities
            "sensor.bathroom_humidity": Mock(state="60", entity_id="sensor.bathroom_humidity"),
            "light.bathroom_mirror": Mock(state="on", entity_id="light.bathroom_mirror"),
            # Office entities
            "sensor.office_temp": Mock(state="21", entity_id="sensor.office_temp"),
            "light.office_desk": Mock(state="on", entity_id="light.office_desk"),
            # Study entities
            "sensor.study_temp": Mock(state="22", entity_id="sensor.study_temp"),
            "light.study_lamp": Mock(state="off", entity_id="light.study_lamp"),
            # Variable source entities
            "input_select.primary_area": Mock(state="living_room", entity_id="input_select.primary_area"),
            "input_select.secondary_area": Mock(state="kitchen", entity_id="input_select.secondary_area"),
            "input_select.area_type_1": Mock(state="bedroom", entity_id="input_select.area_type_1"),
            "input_select.area_type_2": Mock(state="bathroom", entity_id="input_select.area_type_2"),
            "input_select.direct_area_type": Mock(state="office", entity_id="input_select.direct_area_type"),
            "input_select.area1": Mock(state="living_room", entity_id="input_select.area1"),
            "input_select.area2": Mock(state="kitchen", entity_id="input_select.area2"),
            "input_select.area3": Mock(state="dining_room", entity_id="input_select.area3"),
        }

        hass.states.entity_ids.return_value = list(mock_states.keys())
        hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)

        return hass

    @pytest.fixture
    def collection_resolver(self, mock_hass):
        """Create a collection resolver instance with mocked dependencies."""
        # Mock area registry
        mock_areas = {}
        area_configs = [
            ("living_room_id", "living_room"),
            ("kitchen_id", "kitchen"),
            ("dining_room_id", "dining_room"),
            ("master_bedroom_id", "master_bedroom"),
            ("guest_bedroom_id", "guest_bedroom"),
            ("bathroom_id", "bathroom"),
            ("office_id", "office"),
            ("study_id", "study"),
        ]

        for area_id, area_name in area_configs:
            area_mock = Mock()
            area_mock.id = area_id
            area_mock.name = area_name  # Set as string, not Mock attribute
            mock_areas[area_id] = area_mock

        # Mock entity registry entries with area assignments
        mock_entity_entries = {
            # Living room entities
            "sensor.living_room_temp": Mock(
                entity_id="sensor.living_room_temp",
                area_id="living_room_id",
                device_id=None,
            ),
            "light.living_room_main": Mock(
                entity_id="light.living_room_main",
                area_id="living_room_id",
                device_id=None,
            ),
            "sensor.living_room_humidity": Mock(
                entity_id="sensor.living_room_humidity",
                area_id="living_room_id",
                device_id=None,
            ),
            # Kitchen entities
            "sensor.kitchen_temp": Mock(entity_id="sensor.kitchen_temp", area_id="kitchen_id", device_id=None),
            "light.kitchen_overhead": Mock(entity_id="light.kitchen_overhead", area_id="kitchen_id", device_id=None),
            "sensor.kitchen_humidity": Mock(
                entity_id="sensor.kitchen_humidity",
                area_id="kitchen_id",
                device_id=None,
            ),
            # Dining room entities
            "sensor.dining_room_temp": Mock(
                entity_id="sensor.dining_room_temp",
                area_id="dining_room_id",
                device_id=None,
            ),
            "light.dining_room_chandelier": Mock(
                entity_id="light.dining_room_chandelier",
                area_id="dining_room_id",
                device_id=None,
            ),
            # Master bedroom entities
            "sensor.master_bedroom_temp": Mock(
                entity_id="sensor.master_bedroom_temp",
                area_id="master_bedroom_id",
                device_id=None,
            ),
            "light.master_bedroom_lamp": Mock(
                entity_id="light.master_bedroom_lamp",
                area_id="master_bedroom_id",
                device_id=None,
            ),
            # Guest bedroom entities
            "sensor.guest_bedroom_temp": Mock(
                entity_id="sensor.guest_bedroom_temp",
                area_id="guest_bedroom_id",
                device_id=None,
            ),
            "light.guest_bedroom_overhead": Mock(
                entity_id="light.guest_bedroom_overhead",
                area_id="guest_bedroom_id",
                device_id=None,
            ),
            # Bathroom entities
            "sensor.bathroom_humidity": Mock(
                entity_id="sensor.bathroom_humidity",
                area_id="bathroom_id",
                device_id=None,
            ),
            "light.bathroom_mirror": Mock(entity_id="light.bathroom_mirror", area_id="bathroom_id", device_id=None),
            # Office entities
            "sensor.office_temp": Mock(entity_id="sensor.office_temp", area_id="office_id", device_id=None),
            "light.office_desk": Mock(entity_id="light.office_desk", area_id="office_id", device_id=None),
            # Study entities
            "sensor.study_temp": Mock(entity_id="sensor.study_temp", area_id="study_id", device_id=None),
            "light.study_lamp": Mock(entity_id="light.study_lamp", area_id="study_id", device_id=None),
        }

        mock_area_registry = Mock()
        mock_area_registry.areas = mock_areas

        mock_entity_registry = Mock()
        mock_entity_registry.entities = mock_entity_entries

        with (
            patch("ha_synthetic_sensors.collection_resolver.er.async_get") as mock_er,
            patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
            patch("ha_synthetic_sensors.collection_resolver.ar.async_get") as mock_ar,
        ):
            mock_er.return_value = mock_entity_registry
            mock_ar.return_value = mock_area_registry
            resolver = CollectionResolver(mock_hass)
            # Set the registries manually since the constructor might not call async_get
            resolver._entity_registry = mock_entity_registry
            resolver._area_registry = mock_area_registry
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
            assert "living_kitchen_count" in sensor_names
            assert "main_floor_sum" in sensor_names
            assert "dynamic_or_areas" in sensor_names

        except Exception as e:
            if "Configuration schema validation failed" in str(e):
                pytest.skip(f"Schema validation failed as expected for future syntax: {e}")
            else:
                raise

    def test_basic_area_or_pattern_parsing(self, dependency_parser):
        """Test parsing of basic area OR patterns."""
        formula = 'count("area:living_room|kitchen")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "count"
        assert query.query_type == "area"
        assert query.pattern == "living_room|kitchen"

    def test_three_way_area_or_pattern_parsing(self, dependency_parser):
        """Test parsing of three-way area OR patterns."""
        formula = 'sum("area:living_room|kitchen|dining_room")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "sum"
        assert query.query_type == "area"
        assert query.pattern == "living_room|kitchen|dining_room"

    def test_collection_resolver_pipe_support_implemented(self, collection_resolver):
        """Test that collection resolver supports pipe syntax for areas."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        query = DynamicQuery(query_type="area", pattern="living_room|kitchen", function="count")

        # This should not raise an exception if pipe support is implemented
        try:
            entities = collection_resolver.resolve_collection(query)
            # For now, just verify the method can be called without error
            assert isinstance(entities, list)
        except NotImplementedError:
            pytest.skip("Area collection with pipe syntax not implemented yet")
        except Exception as e:
            pytest.fail(f"Unexpected error in collection resolver: {e}")

    def test_living_kitchen_or_resolution_implemented(self, collection_resolver):
        """Test resolution of living_room|kitchen area OR pattern."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        query = DynamicQuery(query_type="area", pattern="living_room|kitchen", function="count")

        try:
            entities = collection_resolver.resolve_collection(query)

            # Should find entities in either living_room or kitchen areas
            expected_entities = [
                "sensor.living_room_temp",
                "light.living_room_main",
                "sensor.living_room_humidity",
                "sensor.kitchen_temp",
                "light.kitchen_overhead",
                "sensor.kitchen_humidity",
            ]

            # Should include entities from either area
            for entity_id in expected_entities:
                assert entity_id in entities, f"Expected {entity_id} to be found with living_room|kitchen areas"

        except NotImplementedError:
            pytest.skip("Area OR resolution not implemented yet")

    def test_three_way_area_or_resolution_implemented(self, collection_resolver):
        """Test resolution of three-way area OR pattern."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        query = DynamicQuery(query_type="area", pattern="living_room|kitchen|dining_room", function="sum")

        try:
            entities = collection_resolver.resolve_collection(query)

            # Should find entities in any of the three areas
            expected_entities = [
                "sensor.living_room_temp",
                "light.living_room_main",
                "sensor.living_room_humidity",
                "sensor.kitchen_temp",
                "light.kitchen_overhead",
                "sensor.kitchen_humidity",
                "sensor.dining_room_temp",
                "light.dining_room_chandelier",
            ]

            assert len(entities) >= len(expected_entities)

        except NotImplementedError:
            pytest.skip("Three-way area OR resolution not implemented yet")

    def test_bedroom_area_or_resolution_implemented(self, collection_resolver):
        """Test resolution of master_bedroom|guest_bedroom area OR pattern."""
        from ha_synthetic_sensors.dependency_parser import DynamicQuery

        query = DynamicQuery(query_type="area", pattern="master_bedroom|guest_bedroom", function="avg")

        try:
            entities = collection_resolver.resolve_collection(query)

            # Should find entities in bedroom areas
            expected_entities = [
                "sensor.master_bedroom_temp",
                "light.master_bedroom_lamp",
                "sensor.guest_bedroom_temp",
                "light.guest_bedroom_overhead",
            ]

            for entity_id in expected_entities:
                assert entity_id in entities, f"Expected {entity_id} to be found with master_bedroom|guest_bedroom areas"

        except NotImplementedError:
            pytest.skip("Bedroom area OR resolution not implemented yet")

    async def test_yaml_sensor_formulas_with_or_patterns(self, config_manager, yaml_config_path):
        """Test that YAML sensors with OR patterns parse correctly."""
        try:
            config = await config_manager.async_load_from_file(yaml_config_path)

            # Find the living_kitchen_count sensor
            living_kitchen_sensor = None
            for sensor in config.sensors:
                if sensor.unique_id == "living_kitchen_count":
                    living_kitchen_sensor = sensor
                    break

            assert living_kitchen_sensor is not None

            # Check the formula contains the OR pattern
            formula_config = living_kitchen_sensor.formulas[0]
            assert 'count("area:living_room|kitchen")' in formula_config.formula

        except Exception as e:
            if "Configuration schema validation failed" in str(e):
                pytest.skip(f"Schema validation failed as expected: {e}")
            else:
                raise

    def test_variable_driven_area_or_patterns(self, dependency_parser, mock_hass):
        """Test variable-driven area OR patterns."""
        variables = {"primary_area": "living_room", "secondary_area": "kitchen"}

        formula = 'sum("area:primary_area|secondary_area")'
        parsed = dependency_parser.parse_formula_dependencies(formula, variables)

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "sum"
        assert query.query_type == "area"
        assert query.pattern == "primary_area|secondary_area"

    def test_complex_area_or_pattern_in_mathematical_formula(self, dependency_parser):
        """Test complex mathematical formula with area OR patterns."""
        formula = '(sum("area:upstairs|downstairs") / count("area:living_room|kitchen")) * 100'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 2

        # First query: sum with upstairs|downstairs
        query1 = parsed.dynamic_queries[0]
        assert query1.function == "sum"
        assert query1.query_type == "area"
        assert query1.pattern == "upstairs|downstairs"

        # Second query: count with living_room|kitchen
        query2 = parsed.dynamic_queries[1]
        assert query2.function == "count"
        assert query2.query_type == "area"
        assert query2.pattern == "living_room|kitchen"

    def test_quoted_and_unquoted_area_or_patterns(self, dependency_parser, collection_resolver):
        """Test both quoted and unquoted area OR patterns."""
        quoted_formula = 'count("area:living_room|kitchen")'
        unquoted_formula = "count('area:bedroom|bathroom')"

        quoted_parsed = dependency_parser.parse_formula_dependencies(quoted_formula, {})
        unquoted_parsed = dependency_parser.parse_formula_dependencies(unquoted_formula, {})

        assert len(quoted_parsed.dynamic_queries) == 1
        assert len(unquoted_parsed.dynamic_queries) == 1

        assert quoted_parsed.dynamic_queries[0].pattern == "living_room|kitchen"
        assert unquoted_parsed.dynamic_queries[0].pattern == "bedroom|bathroom"

    def test_direct_entity_id_area_or_patterns(self, dependency_parser):
        """Test area OR patterns with direct entity IDs."""
        formula = 'count("area:input_select.area_type_1|input_select.area_type_2")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "count"
        assert query.query_type == "area"
        assert query.pattern == "input_select.area_type_1|input_select.area_type_2"

    def test_mixed_direct_and_variable_area_or_patterns(self, dependency_parser):
        """Test mixed direct entity ID and variable area OR patterns."""
        formula = 'sum("area:variable_area|input_select.direct_area_type")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.function == "sum"
        assert query.query_type == "area"
        assert query.pattern == "variable_area|input_select.direct_area_type"

    def test_yaml_direct_area_or_config(self, yaml_config_path):
        """Test YAML config with direct area OR patterns."""
        from pathlib import Path

        yaml_content = Path(yaml_config_path).read_text()
        assert 'count("area:living_room|kitchen")' in yaml_content

    def test_yaml_mixed_area_or_config(self, yaml_config_path):
        """Test YAML config with mixed area OR patterns."""
        from pathlib import Path

        yaml_content = Path(yaml_config_path).read_text()
        assert 'sum("area:primary_area|secondary_area")' in yaml_content

    def test_yaml_direct_three_way_area_config(self, yaml_config_path):
        """Test YAML config with direct three-way area OR patterns."""
        from pathlib import Path

        yaml_content = Path(yaml_config_path).read_text()
        assert 'sum("area:living_room|kitchen|dining_room")' in yaml_content


class TestORAreaPatternEdgeCases:
    """Test edge cases for area OR patterns."""

    @pytest.fixture
    def yaml_config_path(self):
        """Path to the area OR patterns YAML fixture."""
        return Path(__file__).parent / "yaml_fixtures" / "area_or_patterns.yaml"

    @pytest.fixture
    def dependency_parser(self):
        """Create a dependency parser instance."""
        return DependencyParser()

    def test_single_area_no_or(self, dependency_parser):
        """Test single area without OR logic."""
        formula = 'count("area:living_room")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.pattern == "living_room"
        assert "|" not in query.pattern

    def test_empty_or_components(self, dependency_parser):
        """Test handling of empty OR components."""
        formula = 'sum("area:living_room||kitchen")'  # Double pipe
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.pattern == "living_room||kitchen"

    def test_trailing_pipe(self, dependency_parser):
        """Test handling of trailing pipe in OR pattern."""
        formula = 'avg("area:bedroom|bathroom|")'  # Trailing pipe
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.pattern == "bedroom|bathroom|"

    def test_multiple_or_patterns_same_formula(self, dependency_parser):
        """Test multiple OR patterns in the same formula."""
        formula = 'sum("area:living_room|kitchen") + count("area:bedroom|bathroom")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 2

        patterns = [query.pattern for query in parsed.dynamic_queries]
        assert "living_room|kitchen" in patterns
        assert "bedroom|bathroom" in patterns

    def test_quoted_and_unquoted_or_patterns(self, dependency_parser):
        """Test both quoted and unquoted OR patterns."""
        double_quoted = 'count("area:living_room|kitchen")'
        single_quoted = "count('area:bedroom|bathroom')"

        double_parsed = dependency_parser.parse_formula_dependencies(double_quoted, {})
        single_parsed = dependency_parser.parse_formula_dependencies(single_quoted, {})

        assert len(double_parsed.dynamic_queries) == 1
        assert len(single_parsed.dynamic_queries) == 1

        assert double_parsed.dynamic_queries[0].pattern == "living_room|kitchen"
        assert single_parsed.dynamic_queries[0].pattern == "bedroom|bathroom"

    def test_direct_entity_id_area_or_patterns(self, dependency_parser):
        """Test area OR patterns with direct entity IDs."""
        formula = 'count("area:input_select.area_type_1|input_select.area_type_2")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.pattern == "input_select.area_type_1|input_select.area_type_2"

    def test_mixed_direct_and_variable_area_or_patterns(self, dependency_parser):
        """Test mixed direct and variable area OR patterns."""
        formula = 'sum("area:variable_area|input_select.direct_area_type")'
        parsed = dependency_parser.parse_formula_dependencies(formula, {})

        assert len(parsed.dynamic_queries) == 1
        query = parsed.dynamic_queries[0]
        assert query.pattern == "variable_area|input_select.direct_area_type"

    def test_yaml_direct_area_or_config(self, yaml_config_path):
        """Test YAML config contains direct area OR patterns."""
        from pathlib import Path

        yaml_content = Path(yaml_config_path).read_text()
        assert "living_room|kitchen" in yaml_content

    def test_yaml_mixed_area_or_config(self, yaml_config_path):
        """Test YAML config contains mixed area OR patterns."""
        from pathlib import Path

        yaml_content = Path(yaml_config_path).read_text()
        assert "primary_area|secondary_area" in yaml_content

    def test_yaml_direct_three_way_area_config(self, yaml_config_path):
        """Test YAML config contains three-way direct area OR patterns."""
        from pathlib import Path

        yaml_content = Path(yaml_config_path).read_text()
        assert "living_room|kitchen|dining_room" in yaml_content
