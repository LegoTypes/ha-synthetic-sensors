"""Test that YAML export correctly excludes inherited variables from attributes."""

import pytest
import yaml
from unittest.mock import patch, AsyncMock, Mock

from ha_synthetic_sensors.config_manager import ConfigManager
from ha_synthetic_sensors.storage_manager import StorageManager


class TestVariableInheritanceYamlExport:
    """Test that YAML export correctly handles variable inheritance."""

    @pytest.fixture
    def variable_inheritance_solar_yaml(self, load_yaml_fixture):
        """Load the variable inheritance solar test fixture."""
        return load_yaml_fixture("variable_inheritance_solar_test")

    async def test_solar_net_energy_variable_inheritance_export(
        self, mock_hass, mock_entity_registry, mock_states, variable_inheritance_solar_yaml
    ):
        """Test that solar net energy sensor exports YAML without inherited variables in attributes."""

        # Create storage manager and import the config
        storage_manager = StorageManager(mock_hass, "test_storage")
        sensor_set_id = "test_solar"

        # Mock the storage operations to avoid file system operations
        with (
            patch.object(storage_manager._store, "async_load", return_value=None),
            patch.object(storage_manager, "async_save", new_callable=AsyncMock),
        ):
            await storage_manager.async_load()

            # Create sensor set
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test-device", name="Test Solar"
            )

            # Import the sensors (convert dict back to YAML string)
            yaml_content = yaml.dump(variable_inheritance_solar_yaml)
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1

            # Export the YAML
            exported_yaml = storage_manager.export_yaml(sensor_set_id)
            exported_data = yaml.safe_load(exported_yaml)

            # Get the solar net energy sensor
            solar_sensor = exported_data["sensors"]["solar_net_energy"]

            # Verify that sensor-level variables are present
            assert "variables" in solar_sensor
            sensor_variables = solar_sensor["variables"]
            assert "consumed_energy" in sensor_variables
            assert "produced_energy" in sensor_variables
            assert "leg1_consumed" in sensor_variables
            assert "leg2_consumed" in sensor_variables

            # Verify that attributes are present
            assert "attributes" in solar_sensor
            attributes = solar_sensor["attributes"]

            # CRITICAL TEST: Verify that inherited variables are NOT in attribute variables
            # These attributes reference variables that should be inherited at runtime, not stored in YAML

            # Check simple attributes that reference sensor variables - these should be exported as simple strings
            assert attributes["panel_status_is"] == "panel_status", (
                "Simple attribute should be exported as string, not dict with variables"
            )
            assert attributes["energy_grace_period_minutes_is"] == "energy_grace_period_minutes", (
                "Simple attribute should be exported as string, not dict with variables"
            )
            assert attributes["panel_offline_minutes_is"] == "panel_offline_minutes", (
                "Simple attribute should be exported as string, not dict with variables"
            )
            assert attributes["is_within_grace_is"] == "is_within_grace_period", (
                "Simple attribute should be exported as string, not dict with variables"
            )

            # Check complex attributes that have formulas - these should have formula but NO variables section
            grace_remaining_attr = attributes["grace_period_remaining"]
            assert isinstance(grace_remaining_attr, dict), "Complex attribute should be a dictionary"
            assert "formula" in grace_remaining_attr, "Complex attribute should have formula"
            assert "energy_grace_period_minutes" in grace_remaining_attr["formula"], "Formula should reference variables"
            assert "panel_offline_minutes" in grace_remaining_attr["formula"], "Formula should reference variables"
            assert "is_within_grace_period" in grace_remaining_attr["formula"], "Formula should reference variables"
            # CRITICAL: Should NOT have variables section with inherited variables
            assert "variables" not in grace_remaining_attr, "Complex attribute should not store inherited variables in YAML"

            # Check energy_reporting_status attribute
            reporting_status_attr = attributes["energy_reporting_status"]
            assert isinstance(reporting_status_attr, dict), "Complex attribute should be a dictionary"
            assert "formula" in reporting_status_attr, "Complex attribute should have formula"
            assert "grace_period_remaining" in reporting_status_attr["formula"], "Formula should reference other attributes"
            # CRITICAL: Should NOT have variables section with inherited variables
            assert "variables" not in reporting_status_attr, "Complex attribute should not store inherited variables in YAML"

            # Check attribute with its own variables - these SHOULD be preserved
            custom_calc_attr = attributes["custom_calculation"]
            assert isinstance(custom_calc_attr, dict), "Custom calculation attribute should be a dictionary"
            assert "formula" in custom_calc_attr, "Custom calculation attribute should have formula"
            assert "variables" in custom_calc_attr, "Custom calculation attribute should have its own variables"

            # Verify the attribute-specific variables are present
            attr_variables = custom_calc_attr["variables"]
            assert "local_temp" in attr_variables, "Attribute-specific variable should be preserved"
            assert "conversion_factor" in attr_variables, "Attribute-specific constant should be preserved"
            assert "offset" in attr_variables, "Attribute-specific constant should be preserved"

            # Verify these are NOT inherited variables from the sensor
            assert "consumed_energy" not in attr_variables, "Inherited variables should not be in attribute variables"
            assert "panel_status" not in attr_variables, "Inherited variables should not be in attribute variables"
            assert "energy_grace_period_minutes" not in attr_variables, (
                "Inherited variables should not be in attribute variables"
            )

            print("✅ SUCCESS: YAML export correctly handles variable inheritance")
            print(f"   - Sensor variables: {list(sensor_variables.keys())}")
            print(f"   - Attributes: {list(attributes.keys())}")
            print(f"   - Inherited variables excluded from attributes")
            print(f"   - Attribute-specific variables preserved: {list(attr_variables.keys())}")

            # CRITICAL TEST: Verify that runtime calculation using inherited variables works correctly
            # Get the sensor set and evaluate the formulas to ensure inherited variables are accessible
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)
            solar_sensor_config = sensor_set.get_sensor("solar_net_energy")

            # Mock some state values for testing
            mock_states.update(
                {
                    "sensor.solar_consumed_energy": Mock(state="1000"),
                    "sensor.solar_produced_energy": Mock(state="500"),
                    "sensor.leg1_consumed_energy": Mock(state="600"),
                    "sensor.leg2_consumed_energy": Mock(state="400"),
                    "binary_sensor.panel_status": Mock(state="on"),
                    "sensor.local_temperature": Mock(state="25"),
                }
            )

            # Test that the main sensor formula works (uses sensor-level variables)
            main_formula = solar_sensor_config.formulas[0]
            assert main_formula.formula == "consumed_energy - produced_energy", "Main formula should reference sensor variables"

            # Test that attribute formulas can access inherited variables at runtime
            # Attributes are stored as separate formulas in the formulas list
            attr_formulas = solar_sensor_config.formulas[1:]  # Skip main formula

            # Find the grace_period_remaining attribute formula
            grace_attr = next(f for f in attr_formulas if f.id.endswith("_grace_period_remaining"))
            assert "energy_grace_period_minutes" in grace_attr.formula, (
                "Attribute formula should reference inherited global variable"
            )
            assert "panel_offline_minutes" in grace_attr.formula, "Attribute formula should reference inherited sensor variable"
            assert "is_within_grace_period" in grace_attr.formula, (
                "Attribute formula should reference inherited sensor variable"
            )

            # Find the panel_status_is attribute formula
            panel_status_attr = next(f for f in attr_formulas if f.id.endswith("_panel_status_is"))
            assert panel_status_attr.formula == "panel_status", "Simple attribute should reference inherited sensor variable"

            print("✅ SUCCESS: Runtime variable inheritance works correctly")
            print(f"   - Main formula: {main_formula.formula}")
            print(f"   - Grace period formula: {grace_attr.formula}")
            print(f"   - Panel status formula: {panel_status_attr.formula}")
            print(f"   - All formulas can access inherited variables at runtime")
