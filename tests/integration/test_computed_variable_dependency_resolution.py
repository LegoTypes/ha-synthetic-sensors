"""Integration test for computed variable dependency resolution.

This test verifies that computed variables can be resolved in proper dependency order
through the complete evaluation pipeline, replacing the unit test that required
full Home Assistant setup.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from ha_synthetic_sensors import (
    async_setup_synthetic_sensors,
    StorageManager,
)


class TestComputedVariableDependencyResolutionIntegration:
    """Integration test for computed variable dependency resolution."""

    @pytest.fixture
    def computed_variables_dependency_yaml_path(self) -> Path:
        """Path to the computed variables dependency resolution YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "computed_variables_dependency_resolution.yaml"

    async def test_computed_variable_dependency_resolution_integration(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_device_registry,
        mock_config_entry,
        mock_async_add_entities,
        computed_variables_dependency_yaml_path,
    ):
        """Test computed variable dependency resolution through complete pipeline.

        This tests the scenario where:
        - intermediate = a + b (10 + 5 = 15.0)
        - final = intermediate * 2 (15.0 * 2 = 30.0)

        The test verifies that computed variables resolve in proper dependency order
        and produce the expected final result of 30.0.
        """
        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock Store to avoid file system access
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None  # Empty storage initially
            MockStore.return_value = mock_store

            # Use the common device registry fixture
            MockDeviceRegistry.return_value = mock_device_registry

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_computed_vars", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "computed_vars_test"
            device_identifier = "test_computed_variables_dependencies"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier=device_identifier,
                name="Computed Variables Dependency Test",
            )

            # Load YAML configuration
            with open(computed_variables_dependency_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

            # Verify YAML import succeeded
            assert result["sensors_imported"] == 1, (
                f"Expected 1 sensor imported, got {result['sensors_imported']}. Import result: {result}"
            )

            # Set up synthetic sensors using public API
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                sensor_set_id=sensor_set_id,
                # No data_provider_callback needed - uses literal values
                # No sensor_to_backing_mapping needed - pure computed variables
            )

            # Verify sensor manager was created
            assert sensor_manager is not None, "SensorManager should be created successfully"

            # Verify entities were added to Home Assistant
            assert mock_async_add_entities.call_args_list, "async_add_entities was never called - no entities were added to HA"

            # Get the created entities
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            # Set hass attribute on entities to avoid warnings
            for entity in all_entities:
                entity.hass = mock_hass

            # Find the dependency test sensor
            entity_lookup = {getattr(entity, "unique_id", None): entity for entity in all_entities}

            dependency_sensor = entity_lookup.get("dependency_test_sensor")
            assert dependency_sensor is not None, (
                f"Sensor 'dependency_test_sensor' not found. Available sensors: {list(entity_lookup.keys())}"
            )

            # Test formula evaluation through complete pipeline
            await sensor_manager.async_update_sensors()

            # Verify the computed variable dependency resolution worked correctly
            # Expected calculation:
            # a = 10, b = 5
            # intermediate = a + b = 10 + 5 = 15.0
            # final = intermediate * 2 = 15.0 * 2 = 30.0
            expected_value = 30.0
            actual_value = float(dependency_sensor.native_value)

            assert abs(actual_value - expected_value) < 0.001, (
                f"Computed variable dependency resolution failed: expected {expected_value}, got {actual_value}. "
                f"Sensor state: {dependency_sensor.native_value}, "
                f"attributes: {getattr(dependency_sensor, 'extra_state_attributes', {})}"
            )

            # Verify sensor metadata
            assert dependency_sensor.name == "Dependency Test Sensor", (
                f"Wrong sensor name: expected 'Dependency Test Sensor', got '{dependency_sensor.name}'"
            )

            assert dependency_sensor.unit_of_measurement == "kWh", (
                f"Wrong unit: expected 'kWh', got '{dependency_sensor.unit_of_measurement}'"
            )

            assert dependency_sensor.device_class == "energy", (
                f"Wrong device class: expected 'energy', got '{dependency_sensor.device_class}'"
            )

            # Test that sensor can be updated multiple times without issues
            await sensor_manager.async_update_sensors()

            # Value should remain consistent
            second_value = float(dependency_sensor.native_value)
            assert abs(second_value - expected_value) < 0.001, (
                f"Second update changed value unexpectedly: expected {expected_value}, got {second_value}"
            )

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
