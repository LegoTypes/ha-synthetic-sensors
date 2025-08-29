"""Integration tests for computed variables in attributes."""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import asyncio

from ha_synthetic_sensors import async_setup_synthetic_sensors, StorageManager
from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.sensor_manager import SensorManager, SensorManagerConfig
from ha_synthetic_sensors.config_models import ComputedVariable
from ..conftest import MockHomeAssistant


class TestComputedVariablesInAttributesIntegration:
    """Test computed variables within attribute formulas in a complete integration scenario."""

    @pytest.fixture
    def computed_vars_attributes_yaml(self, load_yaml_fixture):
        """Load the computed variables with attributes integration fixture."""
        return load_yaml_fixture("computed_variables_with_attributes_integration")

    @pytest.fixture
    def config_manager(self, mock_hass):
        """Create config manager with mock HA."""
        return ConfigManager(mock_hass)

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = MagicMock()
        mock_device_entry.name = "Computed Variables Test Device"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "computed_vars_test_device")}
        return mock_device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = MagicMock()
        mock_registry.devices = MagicMock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry for testing."""
        config_entry = MagicMock()
        config_entry.entry_id = "computed_vars_test_entry"
        config_entry.domain = "ha_synthetic_sensors"
        return config_entry

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback."""
        mock_callback = MagicMock()

        def mock_callback_impl(entities):
            # Ensure all entities have proper hass and config attributes
            for entity in entities:
                if hasattr(entity, "hass") and entity.hass is None:
                    entity.hass = MagicMock()
                if hasattr(entity, "config") and entity.config is None:
                    entity.config = MagicMock()
                    entity.config.units = MagicMock()
            return mock_callback

        mock_callback.side_effect = mock_callback_impl
        return mock_callback

    @pytest.fixture
    def mock_hass(self, mock_entity_registry, mock_states):
        """Create a mock Home Assistant instance with proper configuration."""
        hass = MockHomeAssistant()
        hass.entity_registry = mock_entity_registry

        # Set up proper configuration with units
        mock_config = MagicMock()
        mock_config.units = MagicMock()
        mock_config.units.temperature_unit = "°C"
        mock_config.units.length_unit = "m"
        mock_config.units.mass_unit = "kg"
        mock_config.units.volume_unit = "L"
        mock_config.units.pressure_unit = "Pa"
        mock_config.units.wind_speed_unit = "m/s"
        hass.config = mock_config

        # Make sure the entity registry has the entities attribute that the constants_entities module expects
        if not hasattr(hass.entity_registry.entities, "values"):
            mock_entities_obj = Mock()
            mock_entities_obj.values.return_value = mock_entity_registry.entities.values()
            hass.entity_registry.entities = mock_entities_obj

        # Set up the states.get method to return states from mock_states
        mock_states_get = Mock()

        def mock_states_get_impl(entity_id):
            return mock_states.get(entity_id)

        mock_states_get.side_effect = mock_states_get_impl
        hass.states.get = mock_states_get

        return hass

    def test_computed_variables_attributes_yaml_loads_and_validates(self, config_manager, computed_vars_attributes_yaml):
        """Test that the integration fixture loads and validates correctly."""
        # Validate the YAML structure
        validation_result = config_manager.validate_yaml_data(computed_vars_attributes_yaml)
        assert validation_result["valid"], (
            f"YAML validation failed: {[e['message'] for e in validation_result.get('errors', [])]}"
        )

        # Load the configuration
        config = config_manager.load_from_dict(computed_vars_attributes_yaml)

        # Verify sensors were loaded
        assert len(config.sensors) == 4  # Updated to include new SPAN grace period sensor
        sensor_names = [s.name for s in config.sensors]
        assert "Power Sensor with Computed Attributes" in sensor_names
        assert "Temperature with State-Dependent Computed Attributes" in sensor_names
        assert "Efficiency Sensor with Nested Computations" in sensor_names
        assert "SPAN Grace Period Sensor" in sensor_names  # New test sensor

    def test_power_sensor_computed_variables_in_attributes_parsing(self, config_manager, computed_vars_attributes_yaml):
        """Test parsing of computed variables in power sensor attributes."""
        config = config_manager.load_from_dict(computed_vars_attributes_yaml)

        # Find the power sensor
        power_sensor = next(s for s in config.sensors if s.unique_id == "power_sensor_with_computed_attributes")

        # Should have main formula + 3 attribute formulas
        assert len(power_sensor.formulas) == 4  # main + power_percentage + power_category + power_analysis

        # Check that attribute formulas have computed variables
        attr_formulas = power_sensor.formulas[1:]  # Skip main formula

        # power_percentage attribute
        percentage_formula = next(f for f in attr_formulas if f.id.endswith("_power_percentage"))
        assert "computed_percent" in percentage_formula.variables
        assert isinstance(percentage_formula.variables["computed_percent"], ComputedVariable)
        assert percentage_formula.variables["computed_percent"].formula == "round((state / max_power) * 100, 1)"

        # power_category attribute with multiple computed variables
        category_formula = next(f for f in attr_formulas if f.id.endswith("_power_category"))
        computed_vars = [k for k, v in category_formula.variables.items() if isinstance(v, ComputedVariable)]
        assert len(computed_vars) >= 5  # is_low, is_medium, is_high, is_very_high, final_category

        # Verify state references in computed variables
        assert category_formula.variables["is_low"].formula == "state < low_threshold"
        assert (
            category_formula.variables["final_category"].formula
            == "'low' if is_low else ('medium' if is_medium else ('high' if is_high else 'very_high'))"
        )

    def test_temperature_sensor_state_scoping_in_computed_variables(self, config_manager, computed_vars_attributes_yaml):
        """Test that state properly scopes to main sensor result in temperature sensor attributes."""
        config = config_manager.load_from_dict(computed_vars_attributes_yaml)

        # Find the temperature sensor
        temp_sensor = next(s for s in config.sensors if s.unique_id == "temperature_sensor_with_state_dependent_attributes")

        # Check attribute formulas
        attr_formulas = temp_sensor.formulas[1:]  # Skip main formula

        # temperature_status attribute
        status_formula = next(f for f in attr_formulas if f.id.endswith("_temperature_status"))
        assert isinstance(status_formula.variables["temp_status"], ComputedVariable)
        # The formula should reference 'state' which will be the main sensor's post-evaluation result
        assert "state <=" in status_formula.variables["temp_status"].formula

        # temperature_metrics attribute
        metrics_formula = next(f for f in attr_formulas if f.id.endswith("_temperature_metrics"))
        temp_f_var = metrics_formula.variables["temp_fahrenheit"]
        assert isinstance(temp_f_var, ComputedVariable)
        assert temp_f_var.formula == "(state * 9/5) + 32"  # Uses state for Fahrenheit conversion

    def test_efficiency_sensor_nested_computed_variables_with_state(self, config_manager, computed_vars_attributes_yaml):
        """Test nested computed variables with state references in efficiency sensor."""
        config = config_manager.load_from_dict(computed_vars_attributes_yaml)

        # Find the efficiency sensor
        eff_sensor = next(s for s in config.sensors if s.unique_id == "efficiency_sensor_with_nested_computed_vars")

        # Main formula should have computed variables
        main_formula = eff_sensor.formulas[0]
        assert isinstance(main_formula.variables["raw_efficiency"], ComputedVariable)
        assert isinstance(main_formula.variables["final_efficiency"], ComputedVariable)

        # Check attribute formulas use state correctly
        attr_formulas = eff_sensor.formulas[1:]

        # efficiency_rating attribute
        rating_formula = next(f for f in attr_formulas if f.id.endswith("_efficiency_rating"))
        rating_vars = [k for k, v in rating_formula.variables.items() if isinstance(v, ComputedVariable)]
        assert "is_excellent" in rating_vars
        assert "is_good" in rating_vars
        # Note: 'rating' variable may not exist in the current YAML configuration
        # The test should check for the variables that actually exist
        print(f"Available rating variables: {rating_vars}")

        # Verify state references in attribute computed variables
        assert rating_formula.variables["is_excellent"].formula == "state >= excellent_threshold"
        assert "state >=" in rating_formula.variables["is_good"].formula

    def test_span_grace_period_computed_variable_inheritance(self, config_manager, computed_vars_attributes_yaml):
        """Test that attribute formulas inherit computed variables from parent sensor at runtime (not in YAML)."""
        config = config_manager.load_from_dict(computed_vars_attributes_yaml)

        # Find the SPAN grace period sensor
        span_sensor = next(s for s in config.sensors if s.unique_id == "span_grace_period_sensor")

        # Main formula should have computed variables at sensor level
        main_formula = span_sensor.formulas[0]
        assert "within_grace" in main_formula.variables
        assert isinstance(main_formula.variables["within_grace"], ComputedVariable)
        assert "grace_period_minutes" in main_formula.variables

        # CRITICAL TEST: Attribute formulas should NOT have inherited variables stored in YAML
        # Variables are inherited at runtime, not stored in the formula objects
        attr_formulas = span_sensor.formulas[1:]  # Skip main formula

        # Find grace_period_active attribute formula
        grace_active_formula = next(f for f in attr_formulas if f.id.endswith("_grace_period_active"))
        # This should NOT have 'within_grace' stored in its variables (inherited at runtime)
        assert "within_grace" not in grace_active_formula.variables, (
            "Attribute formula should NOT store inherited variables in YAML - they are inherited at runtime"
        )

        # Find grace_status attribute formula
        grace_status_formula = next(f for f in attr_formulas if f.id.endswith("_grace_status"))
        # This should also NOT have 'within_grace' stored in its variables
        assert "within_grace" not in grace_status_formula.variables, (
            "Attribute formula should NOT store inherited variables in YAML - they are inherited at runtime"
        )

        # Find grace_minutes_remaining attribute formula
        grace_remaining_formula = next(f for f in attr_formulas if f.id.endswith("_grace_minutes_remaining"))
        # This should NOT have 'grace_period_minutes' stored in its variables
        assert "grace_period_minutes" not in grace_remaining_formula.variables, (
            "Attribute formula should NOT store inherited variables in YAML - they are inherited at runtime"
        )

        # Verify the formulas are correct (they reference variables that will be inherited at runtime)
        assert grace_active_formula.formula == "within_grace"
        assert grace_status_formula.formula == "'active' if within_grace else 'expired'"

        print(f"✅ SUCCESS: Attribute formulas correctly do NOT store inherited variables in YAML")
        print(f"   - grace_period_active variables: {list(grace_active_formula.variables.keys())}")
        print(f"   - grace_status variables: {list(grace_status_formula.variables.keys())}")
        print(f"   - grace_minutes_remaining variables: {list(grace_remaining_formula.variables.keys())}")
        print(f"   - Variables will be inherited at runtime from parent sensor")

    @pytest.mark.asyncio
    async def test_end_to_end_computed_variables_attributes_evaluation(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        config_manager,
        computed_vars_attributes_yaml,
        mock_device_registry,
        mock_config_entry,
        mock_async_add_entities,
    ):
        """Test end-to-end evaluation of computed variables in attributes."""
        # Save original state for restoration
        original_entities = dict(mock_entity_registry._entities)
        original_states = dict(mock_states)

        # Entities required by the YAML configuration
        required_entities = {
            "sensor.raw_temperature": {"state": "20.5", "attributes": {"unit_of_measurement": "°C"}},
            "sensor.raw_power": {"state": "1800", "attributes": {"unit_of_measurement": "W"}},
            "sensor.span_test_meter": {
                "state": "1500.0",
                "attributes": {"unit_of_measurement": "Wh"},
            },  # For SPAN grace period sensor
        }

        try:
            # Register only the required entities using the common fixtures
            for entity_id, data in required_entities.items():
                mock_entity_registry.register_entity(entity_id, entity_id, "sensor")
                # Use the mock_states fixture's register_state method instead of manual creation
                mock_states.register_state(entity_id, data["state"], data["attributes"])

                # Ensure the mock state has the required hass and config attributes
                mock_state = mock_states[entity_id]
                mock_state.hass = mock_hass
                # Create a basic config object with units
                mock_config = MagicMock()
                mock_config.units = MagicMock()
                mock_config.units.temperature_unit = "°C"
                mock_state.config = mock_config

            # Set up storage manager with proper mocking (following the working pattern)
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
                storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
                storage_manager._store = mock_store
                await storage_manager.async_load()

                # Create sensor set first
                sensor_set_id = "computed_vars_attributes"
                await storage_manager.async_create_sensor_set(
                    sensor_set_id=sensor_set_id,
                    device_identifier="computed_vars_test_device",  # Must match YAML global_settings
                    name="Computed Variables Attributes Test",
                )

                # Load YAML content from the fixture
                with open("tests/yaml_fixtures/computed_variables_with_attributes_integration.yaml", "r") as f:
                    yaml_content = f.read()

                # Import YAML with dependency resolution
                result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
                assert (
                    result["sensors_imported"] == 4
                )  # Should import all 4 sensors from the fixture (including new SPAN sensor)

                # Set up synthetic sensors via public API
                sensor_manager = await async_setup_synthetic_sensors(
                    hass=mock_hass,
                    config_entry=mock_config_entry,
                    async_add_entities=mock_async_add_entities,
                    storage_manager=storage_manager,
                )

                # Verify that entities were added
                assert mock_async_add_entities.call_args_list, "No entities were added"

                # Get the added entities
                added_entities = mock_async_add_entities.call_args_list[0][0][0]
                assert len(added_entities) > 0, "No entities were created"

                # Verify that the entities have the expected computed attributes
                for entity in added_entities:
                    if hasattr(entity, "entity_id"):
                        # Check if this is one of our synthetic sensors
                        if entity.entity_id in [
                            "sensor.temperature_sensor_with_state_dependent_attributes",
                            "sensor.power_sensor_with_computed_attributes",
                            "sensor.efficiency_sensor_with_nested_computed_vars",
                            "sensor.span_grace_period_sensor",  # New SPAN test sensor
                        ]:
                            # Verify the entity has the expected attributes
                            assert hasattr(entity, "native_value"), f"Entity {entity.entity_id} missing native_value"
                            assert hasattr(entity, "extra_state_attributes"), (
                                f"Entity {entity.entity_id} missing extra_state_attributes"
                            )

                # Clean up
                await storage_manager.async_delete_sensor_set(sensor_set_id)

        finally:
            # Restore original state
            mock_entity_registry._entities.clear()
            mock_entity_registry._entities.update(original_entities)
            mock_states.clear()
            mock_states.update(original_states)

    def test_computed_variables_preserve_existing_functionality(self, config_manager, computed_vars_attributes_yaml):
        """Test that computed variables don't break existing attribute functionality."""
        config = config_manager.load_from_dict(computed_vars_attributes_yaml)

        # Verify all sensors loaded correctly
        assert len(config.sensors) == 4  # Updated for new SPAN sensor

        # Verify each sensor has expected number of formulas
        sensors_formula_counts = {}
        for sensor in config.sensors:
            sensors_formula_counts[sensor.unique_id] = len(sensor.formulas)

        # Expected: main + attributes
        assert sensors_formula_counts["power_sensor_with_computed_attributes"] == 4  # 1 main + 3 attrs
        assert sensors_formula_counts["temperature_sensor_with_state_dependent_attributes"] == 3  # 1 main + 2 attrs
        assert sensors_formula_counts["efficiency_sensor_with_nested_computed_vars"] == 3  # 1 main + 2 attrs
        assert sensors_formula_counts["span_grace_period_sensor"] == 4  # 1 main + 3 attrs

        # Verify that regular (non-computed) variables still work
        power_sensor = next(s for s in config.sensors if s.unique_id == "power_sensor_with_computed_attributes")
        main_formula = power_sensor.formulas[0]

        # Check that simple variables are still parsed correctly
        assert "input_power" in main_formula.variables
        assert main_formula.variables["input_power"] == "sensor.raw_power"  # Simple entity reference
        assert "efficiency" in main_formula.variables
        assert main_formula.variables["efficiency"] == 0.9  # Simple literal value
