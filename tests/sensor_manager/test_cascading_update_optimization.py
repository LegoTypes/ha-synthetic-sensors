"""Tests for cascading update optimization in sensor_manager.py."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ha_synthetic_sensors.config_models import SensorConfig, FormulaConfig
from ha_synthetic_sensors.sensor_manager import SensorManager
from ha_synthetic_sensors.reference_value_manager import ReferenceValueManager


class TestCascadingUpdateOptimization:
    """Test the cascading update optimization that eliminates double sensor processing."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()
        return hass

    @pytest.fixture
    def mock_evaluator(self):
        """Create a mock evaluator with dependency management."""
        evaluator = MagicMock()
        
        # Mock dependency management phase
        dependency_phase = MagicMock()
        dependency_phase.analyze_cross_sensor_dependencies.return_value = {
            "spa_power": set(),  # Direct sensor, no dependencies
            "spa_energy_produced": {"spa_power"},  # Depends on spa_power
            "spa_net_energy": {"spa_power", "spa_energy_produced"},  # Depends on both
        }
        evaluator.dependency_management_phase = dependency_phase
        
        return evaluator

    @pytest.fixture
    def sensor_configs(self):
        """Create test sensor configurations that mirror SPAN panel setup."""
        return [
            SensorConfig(
                unique_id="spa_power",
                entity_id="sensor.spa_power",
                name="Spa Power",
                formulas=[FormulaConfig(
                    id="spa_power_formula",
                    formula="state('sensor.span_backing_spa_power')",
                    name="spa_power_formula"
                )]
            ),
            SensorConfig(
                unique_id="spa_energy_produced",
                entity_id="sensor.spa_energy_produced", 
                name="Spa Energy Produced",
                formulas=[FormulaConfig(
                    id="spa_energy_formula",
                    formula="integrate(state('sensor.spa_power'), 'hour')",
                    name="spa_energy_formula"
                )]
            ),
            SensorConfig(
                unique_id="spa_net_energy",
                entity_id="sensor.spa_net_energy",
                name="Spa Net Energy", 
                formulas=[FormulaConfig(
                    id="spa_net_formula",
                    formula="state('sensor.spa_energy_produced') - state('sensor.spa_energy_consumed')",
                    name="spa_net_formula"
                )]
            ),
        ]

    @pytest.fixture
    def sensor_manager(self, mock_hass, mock_evaluator, sensor_configs):
        """Create a sensor manager with test sensors."""
        mock_name_resolver = MagicMock()
        mock_add_entities_callback = MagicMock()
        
        manager = SensorManager(mock_hass, mock_name_resolver, mock_add_entities_callback)
        manager._evaluator = mock_evaluator
        
        # Add sensors to manager
        for config in sensor_configs:
            mock_sensor = MagicMock()
            mock_sensor.config = config
            mock_sensor.async_update_sensor = AsyncMock()
            manager._sensors_by_unique_id[config.unique_id] = mock_sensor
            
        return manager

    @patch.object(ReferenceValueManager, 'invalidate_entities')
    async def test_optimized_update_only_invalidates_backing_entities(
        self, mock_invalidate, sensor_manager
    ):
        """Test that optimization only invalidates backing entities, not sensor entities."""
        changed_entities = {"sensor.span_backing_spa_power"}
        
        await sensor_manager.async_update_sensors_for_entities(changed_entities)
        
        # Should only invalidate backing entities, not sensor entities
        mock_invalidate.assert_called_once_with(changed_entities)
        
        # Verify sensor entities were NOT added to invalidation
        call_args = mock_invalidate.call_args[0][0]
        assert "sensor.spa_power" not in call_args
        assert "sensor.spa_energy_produced" not in call_args
        assert "sensor.spa_net_energy" not in call_args

    async def test_find_all_affected_sensors_includes_indirect_dependencies(self, sensor_manager):
        """Test that _find_all_affected_sensors finds both direct and indirect dependencies."""
        # Mock the backing entity extraction
        def mock_extract_backing_entities(config):
            if config.unique_id == "spa_power":
                return {"sensor.span_backing_spa_power"}
            return set()
        
        sensor_manager._extract_backing_entities_from_sensor = mock_extract_backing_entities
        
        # Find directly affected sensors
        directly_affected = []
        for sensor in sensor_manager._sensors_by_unique_id.values():
            backing_entities = mock_extract_backing_entities(sensor.config)
            if backing_entities.intersection({"sensor.span_backing_spa_power"}):
                directly_affected.append(sensor.config)
        
        # Should find spa_power as directly affected
        assert len(directly_affected) == 1
        assert directly_affected[0].unique_id == "spa_power"
        
        # Find all affected sensors (including indirect)
        all_affected = sensor_manager._find_all_affected_sensors(directly_affected)
        
        # Should find all three sensors (spa_power + its dependents)
        affected_ids = {sensor.unique_id for sensor in all_affected}
        assert affected_ids == {"spa_power", "spa_energy_produced", "spa_net_energy"}

    @patch.object(ReferenceValueManager, 'invalidate_entities')
    async def test_optimization_prevents_double_processing(
        self, mock_invalidate, sensor_manager
    ):
        """Test that the optimization prevents double processing by batching updates."""
        changed_entities = {"sensor.span_backing_spa_power"}

        # Mock backing entity extraction
        def mock_extract_backing_entities(config):
            if config.unique_id == "spa_power":
                return {"sensor.span_backing_spa_power"}
            return set()

        sensor_manager._extract_backing_entities_from_sensor = mock_extract_backing_entities

        # Mock _update_sensors_in_order to track calls
        sensor_manager._update_sensors_in_order = AsyncMock()

        await sensor_manager.async_update_sensors_for_entities(changed_entities)

        # Should call _update_sensors_in_order exactly once with all affected sensors
        sensor_manager._update_sensors_in_order.assert_called_once()
        
        # Verify the optimization was called (single batch update)
        assert sensor_manager._update_sensors_in_order.call_count == 1

    async def test_fallback_when_dependency_management_unavailable(self, sensor_manager):
        """Test fallback behavior when dependency management phase is not available."""
        # Disable dependency management
        sensor_manager._evaluator.dependency_management_phase = None
        
        # Mock backing entity extraction
        def mock_extract_backing_entities(config):
            if config.unique_id == "spa_power":
                return {"sensor.span_backing_spa_power"}
            return set()
        
        sensor_manager._extract_backing_entities_from_sensor = mock_extract_backing_entities
        
        # Find directly affected sensors
        directly_affected = []
        for sensor in sensor_manager._sensors_by_unique_id.values():
            backing_entities = mock_extract_backing_entities(sensor.config)
            if backing_entities.intersection({"sensor.span_backing_spa_power"}):
                directly_affected.append(sensor.config)
        
        # Should fall back to direct sensors only
        all_affected = sensor_manager._find_all_affected_sensors(directly_affected)
        
        assert len(all_affected) == 1
        assert all_affected[0].unique_id == "spa_power"

    async def test_no_update_when_no_changed_entities(self, sensor_manager):
        """Test that no processing occurs when no entities have changed."""
        sensor_manager.async_update_sensors = AsyncMock()
        
        await sensor_manager.async_update_sensors_for_entities(set())
        
        # Should not call any update methods
        sensor_manager.async_update_sensors.assert_not_called()

    async def test_no_update_when_no_affected_sensors(self, sensor_manager):
        """Test that no processing occurs when no sensors are affected."""
        # Mock backing entity extraction to return no matches
        sensor_manager._extract_backing_entities_from_sensor = lambda config: set()
        sensor_manager.async_update_sensors = AsyncMock()
        
        await sensor_manager.async_update_sensors_for_entities({"sensor.unrelated_entity"})
        
        # Should not call update methods when no sensors are affected
        sensor_manager.async_update_sensors.assert_not_called()
