"""Tests for cross-sensor reference reassignment functionality."""

import pytest

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.cross_sensor_reference_reassignment import (
    BulkYamlReassignment,
    CrossSensorReferenceReassignment,
    CrudReassignment,
)
import os

# Load YAML fixture file paths
REFERENCE_PATTERNS_YAML = os.path.join(os.path.dirname(__file__), "..", "yaml_fixtures", "reference_patterns.yaml")
SIMPLE_TEST_YAML = os.path.join(os.path.dirname(__file__), "..", "yaml_fixtures", "simple_test.yaml")


class TestCrossSensorReferenceReassignment:
    """Test the base cross-sensor reference reassignment functionality."""

    async def test_detect_reassignment_needs_from_fixture(self, mock_hass, mock_entity_registry, mock_states):
        """Test detection of cross-sensor references using the reference patterns fixture."""
        reassignment = CrossSensorReferenceReassignment(mock_hass)
        config_manager = ConfigManager(mock_hass)

        # Load the reference patterns fixture which contains cross-sensor references
        config = await config_manager.async_load_from_file(REFERENCE_PATTERNS_YAML)

        references = reassignment.detect_reassignment_needs(config)

        # The reference_patterns.yaml contains sensors that reference each other
        # energy_cost_analysis is referenced in monthly_projected and annual_projected attributes
        assert len(references) > 0

        # Verify specific cross-sensor references exist
        found_cross_refs = False
        for sensor_key, refs in references.items():
            if refs:  # If this sensor has cross-sensor references
                found_cross_refs = True
                break

        assert found_cross_refs, f"Expected cross-sensor references but found: {dict(references)}"

    async def test_detect_reassignment_needs_no_references(self, mock_hass, mock_entity_registry, mock_states):
        """Test detection when no cross-references exist using simple fixture."""
        reassignment = CrossSensorReferenceReassignment(mock_hass)
        config_manager = ConfigManager(mock_hass)

        # Load the simple test fixture which has no cross-sensor references
        config = await config_manager.async_load_from_file(SIMPLE_TEST_YAML)

        references = reassignment.detect_reassignment_needs(config)

        # Simple test should have no cross-sensor references (only external entity references)
        assert len(references) == 0

    async def test_create_reassignment_plan_with_existing_mappings(self, mock_hass, mock_entity_registry, mock_states):
        """Test reassignment plan filters out already resolved references."""
        reassignment = CrossSensorReferenceReassignment(mock_hass)
        config_manager = ConfigManager(mock_hass)

        config = await config_manager.async_load_from_file(REFERENCE_PATTERNS_YAML)

        # Simulate some already resolved mappings
        existing_mappings = {"energy_cost_analysis": "sensor.energy_cost_analysis_2"}

        plan = reassignment.create_reassignment_plan(config, existing_mappings)

        # Should filter out already resolved references
        for sensor_key, refs in plan.items():
            assert "energy_cost_analysis" not in refs, f"Already resolved reference found in {sensor_key}"

    async def test_execute_reassignment_from_fixture(self, mock_hass, mock_entity_registry, mock_states):
        """Test execution of cross-sensor reference reassignment using fixtures."""
        reassignment = CrossSensorReferenceReassignment(mock_hass)
        config_manager = ConfigManager(mock_hass)

        config = await config_manager.async_load_from_file(REFERENCE_PATTERNS_YAML)

        # Create mock entity mappings for any cross-sensor references
        references = reassignment.detect_reassignment_needs(config)
        entity_mappings = {}

        # Create mappings for all detected cross-sensor references
        for sensor_key, refs in references.items():
            for ref in refs:
                if ref not in entity_mappings:
                    entity_mappings[ref] = f"sensor.{ref}_resolved"

        if entity_mappings:  # Only test if there are actually cross-sensor references
            resolved_config = await reassignment.execute_reassignment(config, entity_mappings)

            # Verify that references were actually resolved
            assert len(resolved_config.sensors) == len(config.sensors)

            # Check that at least one formula was modified
            original_formulas = []
            resolved_formulas = []

            for sensor in config.sensors:
                for formula in sensor.formulas:
                    original_formulas.append(formula.formula)
                    # Also check attributes for formula strings
                    for attr_value in formula.attributes.values():
                        if isinstance(attr_value, dict) and "formula" in attr_value:
                            original_formulas.append(attr_value["formula"])

            for sensor in resolved_config.sensors:
                for formula in sensor.formulas:
                    resolved_formulas.append(formula.formula)
                    # Also check attributes for formula strings
                    for attr_value in formula.attributes.values():
                        if isinstance(attr_value, dict) and "formula" in attr_value:
                            resolved_formulas.append(attr_value["formula"])

            # If there were cross-sensor references, some formulas should have changed
            if references:
                assert original_formulas != resolved_formulas, "Expected formula changes but none found"

    async def test_execute_reassignment_no_mappings(self, mock_hass, mock_entity_registry, mock_states):
        """Test reassignment execution with no entity mappings returns original config."""
        reassignment = CrossSensorReferenceReassignment(mock_hass)
        config_manager = ConfigManager(mock_hass)

        config = await config_manager.async_load_from_file(SIMPLE_TEST_YAML)

        resolved_config = await reassignment.execute_reassignment(config, {})

        assert resolved_config is config

    async def test_validate_reassignment_integrity_success(self, mock_hass, mock_entity_registry, mock_states):
        """Test successful reassignment integrity validation using fixtures."""
        reassignment = CrossSensorReferenceReassignment(mock_hass)
        config_manager = ConfigManager(mock_hass)

        original_config = await config_manager.async_load_from_file(SIMPLE_TEST_YAML)
        resolved_config = await config_manager.async_load_from_file(SIMPLE_TEST_YAML)  # Same config

        entity_mappings = {"test_key": "sensor.test_entity"}

        is_valid = reassignment.validate_reassignment_integrity(original_config, resolved_config, entity_mappings)

        assert is_valid is True


class TestBulkYamlReassignment:
    """Test bulk YAML reassignment functionality."""

    async def test_process_bulk_yaml_with_references(self, mock_hass, mock_entity_registry, mock_states):
        """Test bulk YAML processing with cross-sensor references from fixtures."""
        bulk_reassignment = BulkYamlReassignment(mock_hass)
        config_manager = ConfigManager(mock_hass)

        config = await config_manager.async_load_from_file(REFERENCE_PATTERNS_YAML)

        # Detect what cross-sensor references exist
        references = bulk_reassignment.detect_reassignment_needs(config)

        if not references:
            # If no cross-sensor references in this fixture, skip this test
            pytest.skip("No cross-sensor references found in fixture")

        async def mock_collect_entity_ids(config) -> dict[str, str]:
            """Mock callback to simulate entity ID collection."""
            mappings = {}
            for sensor_key, refs in references.items():
                # Create mappings for the sensor itself
                mappings[sensor_key] = f"sensor.{sensor_key}_resolved"
                # Create mappings for referenced sensors
                for ref in refs:
                    if ref not in mappings:
                        mappings[ref] = f"sensor.{ref}_resolved"
            return mappings

        resolved_config = await bulk_reassignment.process_bulk_yaml(config, mock_collect_entity_ids)

        # Verify processing completed
        assert len(resolved_config.sensors) == len(config.sensors)

    async def test_process_bulk_yaml_no_references(self, mock_hass, mock_entity_registry, mock_states):
        """Test bulk YAML processing when no cross-references exist.

        Entity registration still happens even without cross-references because:
        1. Self-references need to be replaced with 'state' tokens
        2. Collision handling may require entity_id updates
        3. Proper entity_id assignment is always needed
        """
        bulk_reassignment = BulkYamlReassignment(mock_hass)
        config_manager = ConfigManager(mock_hass)

        config = await config_manager.async_load_from_file(SIMPLE_TEST_YAML)

        async def mock_collect_entity_ids(config):
            """Mock callback that returns entity mappings."""
            # Return mock entity mappings for the sensors in simple_test.yaml
            return {"simple_test_sensor": "sensor.simple_test_sensor", "complex_test_sensor": "sensor.complex_test_sensor"}

        resolved_config = await bulk_reassignment.process_bulk_yaml(config, mock_collect_entity_ids)

        # Should return the resolved config (may be modified for entity_id updates)
        # In this case, since no cross-references exist and no collisions occur,
        # the config should be effectively unchanged
        assert resolved_config is not None
        assert len(resolved_config.sensors) == len(config.sensors)


class TestCrudReassignment:
    """Test CRUD operation reassignment functionality."""

    async def test_process_crud_operation_with_entity_registry(self, mock_hass, mock_entity_registry, mock_states):
        """Test CRUD operation using common entity registry fixture."""
        crud_reassignment = CrudReassignment(mock_hass)
        config_manager = ConfigManager(mock_hass)

        # Load a config to get a sensor to modify
        config = await config_manager.async_load_from_file(SIMPLE_TEST_YAML)

        # Take the first sensor and modify it to reference an entity from the common registry
        if config.sensors:
            modified_sensor = config.sensors[0]
            # Add a formula that references a common registry entity
            from ha_synthetic_sensors.config_models import FormulaConfig

            # Reference a sensor from the mock entity registry
            new_formula = FormulaConfig(
                id="test_ref",
                formula="sensor.span_panel_instantaneous_power * 2.0",  # From common registry
                name="Test Reference",
            )
            modified_sensor.formulas.append(new_formula)

            existing_entity_mappings = {}  # No existing mappings

            async def mock_collect_new_entity_ids(sensors):
                """Mock callback for new entity ID collection."""
                return {modified_sensor.unique_id: f"sensor.{modified_sensor.unique_id}_new"}

            resolved_sensors = await crud_reassignment.process_crud_operation(
                [modified_sensor], existing_entity_mappings, mock_collect_new_entity_ids
            )

            # Verify processing completed
            assert len(resolved_sensors) == 1
            assert resolved_sensors[0].unique_id == modified_sensor.unique_id

    async def test_process_crud_operation_no_references(self, mock_hass, mock_entity_registry, mock_states):
        """Test CRUD operation when no cross-references exist."""
        crud_reassignment = CrudReassignment(mock_hass)
        config_manager = ConfigManager(mock_hass)

        config = await config_manager.async_load_from_file(SIMPLE_TEST_YAML)

        if config.sensors:
            simple_sensor = config.sensors[0]  # Use existing sensor with no cross-refs

            async def mock_collect_new_entity_ids(sensors):
                """Mock callback - should not be called."""
                pytest.fail("Callback should not be called when no references exist")

            resolved_sensors = await crud_reassignment.process_crud_operation([simple_sensor], {}, mock_collect_new_entity_ids)

            # Should return original sensors unchanged
            assert resolved_sensors == [simple_sensor]
