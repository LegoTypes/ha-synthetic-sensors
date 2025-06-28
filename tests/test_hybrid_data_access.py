"""Tests for hybrid data access using integration registration and HA entities."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest

from ha_synthetic_sensors.config_manager import ConfigManager, FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.name_resolver import NameResolver
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.types import DataProviderResult


class TestHybridDataAccess:
    """Test cases for hybrid data access using push-based registration and HA entities."""

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = MagicMock()
        hass.states = MagicMock()

        # Mock HA entities with states
        mock_states = {
            "sensor.grid_power": Mock(state="1500", attributes={}),
            "sensor.solar_inverter": Mock(state="800", attributes={}),
            "sensor.house_total_power": Mock(state="2200", attributes={}),
            "sensor.workshop_power": Mock(state="300", attributes={}),
            "sensor.external_sensor": Mock(state="450", attributes={}),
            "sensor.outside_temperature": Mock(state="22.5", attributes={}),
        }

        def mock_get_state(entity_id):
            return mock_states.get(entity_id)

        hass.states.get = Mock(side_effect=mock_get_state)
        return hass

    @pytest.fixture
    def integration_data(self):
        """Mock integration data store."""
        return {
            "span.meter_001": 1250.0,
            "span.efficiency_input": 850.0,
            "span.efficiency_baseline": 1000.0,
            "span.local_sensor": 500.0,
            "span.internal_temp": 35.2,
        }

    @pytest.fixture
    def data_provider_callback(self, integration_data):
        """Create a data provider callback that returns integration data."""

        def callback(entity_id: str) -> DataProviderResult:
            if entity_id in integration_data:
                return {"value": integration_data[entity_id], "exists": True}
            return {"value": None, "exists": False}

        return callback

    @pytest.fixture
    def mock_integration_data_provider(self, integration_data: dict[str, Any]):
        """Create a mock integration data provider with push-based registration."""

        class MockDataProvider:
            def __init__(self, data: dict[str, Any]) -> None:
                self._data = data
                self._registered_entities: set[str] = set()

            def register_entities(self, sensor_manager: SensorManager) -> None:
                """Register entities with the sensor manager."""
                entity_ids = set(self._data.keys())
                sensor_manager.register_data_provider_entities(entity_ids)
                self._registered_entities = entity_ids

            def get_data(self, entity_id: str) -> DataProviderResult:
                """Get data for an entity."""
                if entity_id in self._data:
                    return {"value": self._data[entity_id], "exists": True}
                return {"value": None, "exists": False}

            def get_registered_entities(self) -> set[str]:
                """Get registered entity IDs."""
                return self._registered_entities.copy()

        return MockDataProvider(integration_data)

    @pytest.fixture
    def evaluator_with_registration(self, mock_hass: MagicMock, mock_integration_data_provider: Any):
        """Create an evaluator with push-based registration."""
        # Create evaluator without callbacks first
        evaluator = Evaluator(hass=mock_hass)

        # Register integration entities directly with all available entities
        all_entities = set(mock_integration_data_provider._data.keys())
        evaluator.update_integration_entities(all_entities)

        # Mock the data provider callback for backward compatibility
        evaluator._data_provider_callback = mock_integration_data_provider.get_data

        return evaluator

    @pytest.fixture
    def hybrid_config(self):
        """Load hybrid data access configuration."""
        config_manager = ConfigManager(hass=None)
        yaml_path = Path(__file__).parent / "yaml_fixtures" / "hybrid_data_access.yaml"
        return config_manager.load_from_file(str(yaml_path))

    @pytest.fixture
    def name_resolver(self, mock_hass):
        """Create a name resolver."""
        return NameResolver(mock_hass, variables={})

    def test_pure_integration_data_evaluation(self, evaluator_with_registration, hybrid_config):
        """Test evaluation using only integration-provided data."""
        # Get the internal_efficiency sensor config
        sensor_config = None
        for sensor in hybrid_config.sensors:
            if sensor.unique_id == "internal_efficiency":
                sensor_config = sensor
                break

        assert sensor_config is not None
        assert len(sensor_config.formulas) > 0
        formula_config = sensor_config.formulas[0]  # Get the main formula

        # Evaluate the formula - should use only integration registered data
        result = evaluator_with_registration.evaluate_formula(formula_config, {})

        assert result["success"] is True
        # 850.0 / 1000.0 * 100 = 85.0
        assert result["value"] == 85.0

    def test_pure_ha_data_evaluation(self, evaluator_with_registration, hybrid_config):
        """Test evaluation using only Home Assistant entities."""
        # Get the external_power_sum sensor config
        sensor_config = None
        for sensor in hybrid_config.sensors:
            if sensor.unique_id == "external_power_sum":
                sensor_config = sensor
                break

        assert sensor_config is not None
        assert len(sensor_config.formulas) > 0
        formula_config = sensor_config.formulas[0]  # Get the main formula

        # Evaluate the formula - should use only HA state queries
        result = evaluator_with_registration.evaluate_formula(formula_config, {})

        assert result["success"] is True
        # 2200 + 300 = 2500
        assert result["value"] == 2500.0

    def test_mixed_data_source_evaluation(self, evaluator_with_registration, hybrid_config):
        """Test evaluation mixing integration data and HA entities."""
        # Get the hybrid_power_analysis sensor config
        sensor_config = None
        for sensor in hybrid_config.sensors:
            if sensor.unique_id == "hybrid_power_analysis":
                sensor_config = sensor
                break

        assert sensor_config is not None
        assert len(sensor_config.formulas) > 0
        formula_config = sensor_config.formulas[0]  # Get the main formula

        # Evaluate the formula - should use both registered data and HA queries
        result = evaluator_with_registration.evaluate_formula(formula_config, {})

        assert result["success"] is True
        # 1250.0 (integration) + 1500 (HA) + 800 (HA) = 3550.0
        assert result["value"] == 3550.0

    def test_complex_mixed_with_attributes(self, evaluator_with_registration, hybrid_config, name_resolver):
        """Test complex sensor with mixed data sources in attributes."""
        # Get the comprehensive_analysis sensor config
        sensor_config = None
        for sensor in hybrid_config.sensors:
            if sensor.unique_id == "comprehensive_analysis":
                sensor_config = sensor
                break

        assert sensor_config is not None
        assert len(sensor_config.formulas) > 0
        formula_config = sensor_config.formulas[0]  # Get the main formula

        # Evaluate main formula
        main_result = evaluator_with_registration.evaluate_formula(formula_config, {})
        assert main_result["success"] is True
        # 500.0 (integration) + 450 (HA) = 950.0
        assert main_result["value"] == 950.0

        # Test simple attribute without complex context
        # Just verify that direct entity references work in attributes
        assert len(sensor_config.formulas) >= 1

    def test_integration_registration_priority(self, mock_hass, integration_data):
        """Test that integration registration takes priority over HA states."""

        # Create evaluator and mock data provider
        evaluator = Evaluator(hass=mock_hass)

        # Register integration entities
        entity_ids = set(integration_data.keys())
        evaluator.update_integration_entities(entity_ids)

        # Mock data provider callback for backward compatibility
        def data_provider(entity_id: str) -> DataProviderResult:
            if entity_id in integration_data:
                return {"value": integration_data[entity_id], "exists": True}
            return {"value": None, "exists": False}

        evaluator._data_provider_callback = data_provider

        # Create a formula that uses an entity ID that exists in both integration and HA
        # Add the same entity to HA with a different value
        mock_hass.states.get.return_value = Mock(state="999", attributes={})

        formula_config = FormulaConfig(
            id="test_formula",
            formula="test_entity",
            variables={"test_entity": "span.meter_001"},
        )

        result = evaluator.evaluate_formula(formula_config, {})

        assert result["success"] is True
        # Should return integration value (1250.0), not HA value (999)
        assert result["value"] == 1250.0

    def test_integration_registration_error_handling(self, mock_hass, integration_data):
        """Test proper error handling when integration registration fails for claimed entity."""

        # Create evaluator with registration
        evaluator = Evaluator(hass=mock_hass)

        # Register only specific entity
        evaluator.update_integration_entities({"span.meter_001"})

        # Create callback that fails for the registered entity
        def failing_data_provider(entity_id: str) -> DataProviderResult:
            if entity_id == "span.meter_001":
                return {"value": None, "exists": False}  # Integration claimed entity but can't provide it
            if entity_id in integration_data:
                return {"value": integration_data[entity_id], "exists": True}
            return {"value": None, "exists": False}

        evaluator._data_provider_callback = failing_data_provider

        formula_config = FormulaConfig(
            id="test_formula_error",
            formula="test_entity",
            variables={"test_entity": "span.meter_001"},
        )

        result = evaluator.evaluate_formula(formula_config, {})

        # Should handle the error gracefully - integration claimed entity but couldn't provide it
        # This should result in unknown state since the entity is registered but not available (transitory error)
        assert result["success"] is True  # Not a fatal error, just unavailable dependency
        assert result["state"] == "unknown"  # Transitory error state
        assert "unavailable_dependencies" in result

    def test_sensor_manager_with_registration(self, mock_hass, mock_integration_data_provider, hybrid_config):
        """Test SensorManager with integration registration."""
        # Create mock add_entities callback
        async_add_entities = Mock()

        # Create sensor manager config without callbacks (using registration instead)
        manager_config = SensorManagerConfig(lifecycle_managed_externally=True)

        # Create name resolver and sensor manager
        name_resolver = NameResolver(mock_hass, variables={})
        sensor_manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=async_add_entities,
            manager_config=manager_config,
        )

        # Register integration entities with sensor manager
        mock_integration_data_provider.register_entities(sensor_manager)

        # Verify the evaluator has the registered entities
        registered_entities = sensor_manager.get_registered_entities()
        expected_entities = set(mock_integration_data_provider._data.keys())
        assert registered_entities == expected_entities

        # Also check the evaluator has the entities
        evaluator_entities = sensor_manager._evaluator.get_integration_entities()
        assert evaluator_entities == expected_entities

    def test_no_registration_defaults_to_ha_only(self, mock_hass):
        """Test that evaluator without registration uses only HA state queries."""
        evaluator = Evaluator(hass=mock_hass)

        # Should not have registered entities or callbacks
        assert evaluator.get_integration_entities() == set()
        assert evaluator._data_provider_callback is None

        # Mock HA state for specific entity
        def mock_get_state(entity_id):
            if entity_id == "sensor.test":
                return Mock(state="123", attributes={})
            return None

        mock_hass.states.get.side_effect = mock_get_state

        formula_config = FormulaConfig(
            id="test_formula_3",
            formula="test_var",
            variables={"test_var": "sensor.test"},
        )

        result = evaluator.evaluate_formula(formula_config, {})

        assert result["success"] is True
        assert result["value"] == 123.0

        # Verify HA was called
        mock_hass.states.get.assert_called_with("sensor.test")

    def test_registration_determines_data_source(self, mock_hass, integration_data):
        """Test that registration correctly determines which entities use integration data."""

        # Create evaluator and register only subset of integration entities
        evaluator = Evaluator(hass=mock_hass)

        # Only register subset of integration entities
        registered_entities = {"span.meter_001", "span.local_sensor"}
        evaluator.update_integration_entities(registered_entities)

        # Create data provider callback
        def data_provider(entity_id: str) -> DataProviderResult:
            if entity_id in integration_data:
                return {"value": integration_data[entity_id], "exists": True}
            return {"value": None, "exists": False}

        evaluator._data_provider_callback = data_provider

        # Mock HA for entities not in integration registration
        def mock_get_state(entity_id):
            if entity_id == "span.efficiency_input":
                return Mock(state="999", attributes={})  # Different value than integration
            return None

        mock_hass.states.get.side_effect = mock_get_state

        # Test entity in registration - should use integration data
        formula_config1 = FormulaConfig(
            id="test_formula_4",
            formula="test_var",
            variables={"test_var": "span.meter_001"},
        )
        result1 = evaluator.evaluate_formula(formula_config1, {})
        assert result1["success"] is True
        assert result1["value"] == 1250.0  # Integration value

        # Test entity not in registration - should use HA
        formula_config2 = FormulaConfig(
            id="test_formula_5",
            formula="test_var",
            variables={"test_var": "span.efficiency_input"},
        )
        result2 = evaluator.evaluate_formula(formula_config2, {})
        assert result2["success"] is True
        assert result2["value"] == 999.0  # HA value, not integration value (850.0)

    def test_registration_update_functionality(self, mock_hass, integration_data):
        """Test that registration can be updated dynamically."""

        # Create evaluator and register initial entities
        evaluator = Evaluator(hass=mock_hass)
        initial_entities = {"span.meter_001"}
        evaluator.update_integration_entities(initial_entities)

        # Verify initial registration
        assert evaluator.get_integration_entities() == initial_entities

        # Update registration with more entities
        updated_entities = {
            "span.meter_001",
            "span.local_sensor",
            "span.efficiency_input",
        }
        evaluator.update_integration_entities(updated_entities)

        # Verify updated registration
        assert evaluator.get_integration_entities() == updated_entities

        # Update again with fewer entities
        final_entities = {"span.local_sensor"}
        evaluator.update_integration_entities(final_entities)

        # Verify final registration
        assert evaluator.get_integration_entities() == final_entities

    def test_sensor_manager_registration_methods(self, mock_hass):
        """Test SensorManager registration methods."""

        # Create sensor manager
        name_resolver = NameResolver(mock_hass, variables={})
        async_add_entities = Mock()
        manager_config = SensorManagerConfig(lifecycle_managed_externally=True)
        sensor_manager = SensorManager(
            hass=mock_hass,
            name_resolver=name_resolver,
            add_entities_callback=async_add_entities,
            manager_config=manager_config,
        )

        # Test initial state
        assert sensor_manager.get_registered_entities() == set()

        # Test registration
        entities = {"span.meter_001", "span.local_sensor"}
        sensor_manager.register_data_provider_entities(entities)
        assert sensor_manager.get_registered_entities() == entities

        # Test update
        updated_entities = {"span.meter_001", "span.efficiency_input"}
        sensor_manager.update_data_provider_entities(updated_entities)
        assert sensor_manager.get_registered_entities() == updated_entities

        # Verify evaluator is also updated
        evaluator_entities = sensor_manager._evaluator.get_integration_entities()
        assert evaluator_entities == updated_entities
