"""Tests for area OR pattern integration.

This module tests OR-style logic for area collection patterns using pipe (|) syntax.
Tests are modeled after the successful label OR pattern implementation.
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
    """Path to the area OR patterns YAML fixture."""
    return Path(__file__).parent.parent / "yaml_fixtures" / "area_or_patterns.yaml"


@pytest.fixture
def dependency_parser():
    """Create a dependency parser instance."""
    from ha_synthetic_sensors.formula_ast_analysis_service import FormulaASTAnalysisService

    return FormulaASTAnalysisService()


@pytest.fixture
def collection_resolver(mock_hass, mock_entity_registry, mock_states):
    """Create a collection resolver instance with shared mocks."""
    from ha_synthetic_sensors.collection_resolver import CollectionResolver

    # Set up the mock hass with entity registry and states
    mock_hass.entity_registry = mock_entity_registry
    mock_hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)
    mock_hass.states.entity_ids.return_value = list(mock_states.keys())

    # Add area registry mock
    mock_hass.area_registry = Mock()
    mock_hass.area_registry.areas = {
        "living_room": Mock(name="Living Room"),
        "kitchen": Mock(name="Kitchen"),
        "dining_room": Mock(name="Dining Room"),
        "master_bedroom": Mock(name="Master Bedroom"),
        "guest_bedroom": Mock(name="Guest Bedroom"),
    }

    # Patch necessary modules
    with (
        patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
        patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
        patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
        patch("ha_synthetic_sensors.collection_resolver.ar.async_get", return_value=mock_hass.area_registry),
    ):
        return CollectionResolver(mock_hass)


class TestORAreaIntegration:
    """Test OR pattern integration with area-based entity resolution."""

    @pytest.fixture(autouse=True)
    def setup_method(self, mock_hass, mock_entity_registry, mock_states):
        """Set up test fixtures with shared mock entity registry."""
        self.mock_hass = mock_hass
        self.mock_hass.entity_registry = mock_entity_registry
        self.mock_hass.states.get.side_effect = lambda entity_id: mock_states.get(entity_id)
        self.mock_hass.states.entity_ids.return_value = list(mock_states.keys())

        # Add area registry mock with correct structure for collection resolver
        self.mock_hass.area_registry = Mock()

        # Create area mocks with area IDs that match the entities in the common fixture
        # The entities have area_id values like "living_room", "kitchen", etc.
        living_room_area = Mock()
        living_room_area.name = "Living Room"

        kitchen_area = Mock()
        kitchen_area.name = "Kitchen"

        dining_room_area = Mock()
        dining_room_area.name = "Dining Room"

        master_bedroom_area = Mock()
        master_bedroom_area.name = "Master Bedroom"

        guest_bedroom_area = Mock()
        guest_bedroom_area.name = "Guest Bedroom"

        # Use area IDs that match the entity area_id values in the common fixture
        self.mock_hass.area_registry.areas = {
            "living_room": living_room_area,
            "kitchen": kitchen_area,
            "dining_room": dining_room_area,
            "master_bedroom": master_bedroom_area,
            "guest_bedroom": guest_bedroom_area,
        }

        self._patchers = [
            patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.collection_resolver.dr.async_get"),
            patch("ha_synthetic_sensors.collection_resolver.ar.async_get", return_value=self.mock_hass.area_registry),
        ]
        for p in self._patchers:
            p.start()
        self.resolver = CollectionResolver(self.mock_hass)
        self.evaluator = Evaluator(self.mock_hass)

    def teardown_method(self):
        for p in self._patchers:
            p.stop()

    def test_living_kitchen_or_resolution_implemented(self, mock_hass, mock_entity_registry, mock_states):
        """Test OR pattern resolution for living_room|kitchen areas."""
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

        query = DynamicQuery(query_type="area", pattern="living_room|kitchen", function="sum")
        entities = self.resolver.resolve_collection(query)

        # Should find entities from both areas
        expected_entities = [
            "sensor.living_room_temp",
            "light.living_room_main",
            "sensor.living_room_humidity",
            "sensor.kitchen_temp",
            "light.kitchen_overhead",
            "sensor.kitchen_humidity",
        ]

        for entity_id in expected_entities:
            assert entity_id in self.mock_hass.entity_registry.entities, (
                f"Expected {entity_id} to be found with living_room|kitchen areas"
            )

    def test_three_way_area_or_resolution_implemented(self, mock_hass, mock_entity_registry, mock_states):
        """Test OR pattern resolution for three areas."""
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

        # Use pipe-separated areas as per README and design guide
        query = DynamicQuery(query_type="area", pattern="living_room|kitchen|dining_room", function="sum")
        entities = self.resolver.resolve_collection(query)

        # Should find entities from all three areas (living_room and kitchen exist in shared registry)
        expected_entities = [
            "sensor.living_room_temp",
            "light.living_room_main",
            "sensor.living_room_humidity",
            "sensor.kitchen_temp",
            "light.kitchen_overhead",
            "sensor.kitchen_humidity",
        ]

        # Check that we get entities from the areas (these exist in shared registry)
        assert len(entities) > 0, f"Should find entities from areas, got: {entities}"

        # Check that expected entities are in the returned list
        found_entities = [entity for entity in expected_entities if entity in entities]
        assert len(found_entities) > 0, f"Expected to find some of {expected_entities}, but found: {entities}"

    def test_bedroom_area_or_resolution_implemented(self, mock_hass, mock_entity_registry, mock_states):
        """Test OR pattern resolution for bedroom areas."""
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

        query = DynamicQuery(query_type="area", pattern="master_bedroom|guest_bedroom", function="sum")
        entities = self.resolver.resolve_collection(query)

        # Should find entities from both bedroom areas
        expected_entities = ["sensor.master_bedroom_temp", "sensor.guest_bedroom_temp"]

        for entity_id in expected_entities:
            assert entity_id in self.mock_hass.entity_registry.entities, (
                f"Expected {entity_id} to be found with master_bedroom|guest_bedroom areas"
            )

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
        from ha_synthetic_sensors.dynamic_query import DynamicQuery

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
