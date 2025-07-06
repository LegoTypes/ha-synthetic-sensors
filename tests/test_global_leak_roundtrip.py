"""Test to detect if global variables incorrectly leak into individual sensor storage."""

import yaml


class TestGlobalVariableLeakRoundtrip:
    """Test that global variables don't leak into individual sensor storage during roundtrip."""

    def load_yaml_fixture(self, fixture_name: str) -> str:
        """Load a YAML fixture file and return its contents."""
        import os

        fixture_path = os.path.join("tests", "yaml_fixtures", fixture_name)
        with open(fixture_path) as f:
            return f.read()

    async def test_global_variables_dont_leak_to_sensors(self, storage_manager_real):
        """Test that global variables stay in global_settings and don't leak to individual sensors."""
        await storage_manager_real.async_load()

        # Load YAML with global variables used in formulas but not defined locally
        yaml_content = self.load_yaml_fixture("roundtrip_test_global_leak.yaml")

        # Parse original YAML to know what we expect
        original_data = yaml.safe_load(yaml_content)
        global_variables = original_data["global_settings"]["variables"]

        # Import YAML
        sensor_set_id = await storage_manager_real.async_from_yaml(
            yaml_content=yaml_content,
            sensor_set_id="global_leak_test",
            device_identifier=None,  # Should use global device_identifier
        )

        # Export YAML back out
        exported_yaml = storage_manager_real.export_yaml(sensor_set_id)
        exported_data = yaml.safe_load(exported_yaml)

        # CRITICAL TEST: Global variables should NOT appear in individual sensors

        # Test pure_global_sensor (uses only globals)
        pure_global = exported_data["sensors"]["pure_global_sensor"]
        if "variables" in pure_global:
            # If variables exist, they should NOT contain global variables
            assert "shared_power_meter" not in pure_global["variables"], (
                "Global variable 'shared_power_meter' leaked into pure_global_sensor"
            )
            assert "global_efficiency" not in pure_global["variables"], (
                "Global variable 'global_efficiency' leaked into pure_global_sensor"
            )
            assert "base_voltage" not in pure_global["variables"], (
                "Global variable 'base_voltage' leaked into pure_global_sensor"
            )

        # Test mixed_usage_sensor (uses globals + locals)
        mixed_usage = exported_data["sensors"]["mixed_usage_sensor"]
        if "variables" in mixed_usage:
            # Should only have local variables, not globals
            assert "local_offset" in mixed_usage["variables"], "Local variable 'local_offset' should be preserved"
            assert mixed_usage["variables"]["local_offset"] == "sensor.local_adjustment", (
                "Local variable value should be preserved"
            )

            # Global variables should NOT be present
            assert "shared_power_meter" not in mixed_usage["variables"], (
                "Global variable 'shared_power_meter' leaked into mixed_usage_sensor"
            )
            assert "global_efficiency" not in mixed_usage["variables"], (
                "Global variable 'global_efficiency' leaked into mixed_usage_sensor"
            )
            assert "base_voltage" not in mixed_usage["variables"], (
                "Global variable 'base_voltage' leaked into mixed_usage_sensor"
            )

        # Test complex_global_sensor (uses multiple globals)
        complex_global = exported_data["sensors"]["complex_global_sensor"]
        if "variables" in complex_global:
            # Should have NO variables since it uses only globals
            assert "shared_power_meter" not in complex_global["variables"], (
                "Global variable 'shared_power_meter' leaked into complex_global_sensor"
            )
            assert "global_efficiency" not in complex_global["variables"], (
                "Global variable 'global_efficiency' leaked into complex_global_sensor"
            )
            assert "base_voltage" not in complex_global["variables"], (
                "Global variable 'base_voltage' leaked into complex_global_sensor"
            )

        # Test pure_local_sensor (control case - uses only locals)
        pure_local = exported_data["sensors"]["pure_local_sensor"]
        assert "variables" in pure_local, "Pure local sensor should have its local variables"
        assert "local_temp" in pure_local["variables"], "Local variable 'local_temp' should be preserved"
        assert pure_local["variables"]["local_temp"] == "sensor.room_temperature", "Local variable value should be preserved"

        # Globals should NOT be in pure_local_sensor
        assert "shared_power_meter" not in pure_local["variables"], (
            "Global variable 'shared_power_meter' leaked into pure_local_sensor"
        )
        assert "global_efficiency" not in pure_local["variables"], (
            "Global variable 'global_efficiency' leaked into pure_local_sensor"
        )
        assert "base_voltage" not in pure_local["variables"], "Global variable 'base_voltage' leaked into pure_local_sensor"

        # VERIFY: Global settings should be preserved correctly
        assert "global_settings" in exported_data, "Global settings should be preserved in export"
        assert exported_data["global_settings"]["variables"] == global_variables, (
            "Global variables should be preserved exactly in global_settings"
        )

        # VERIFY: Device identifier inheritance works
        assert exported_data["global_settings"]["device_identifier"] == "test_device:roundtrip_123"

        # Individual sensors should NOT have device_identifier since it's global
        for sensor_name, sensor_data in exported_data["sensors"].items():
            assert "device_identifier" not in sensor_data, (
                f"Sensor '{sensor_name}' should not have device_identifier since it's global"
            )

    async def test_storage_manager_internal_state(self, storage_manager_real):
        """Test that storage manager internal state correctly separates global and local variables."""
        await storage_manager_real.async_load()

        # Load YAML with global variables
        yaml_content = self.load_yaml_fixture("roundtrip_test_global_leak.yaml")

        sensor_set_id = await storage_manager_real.async_from_yaml(
            yaml_content=yaml_content, sensor_set_id="internal_state_test", device_identifier=None
        )

        # Get sensors from storage manager
        sensors = storage_manager_real.list_sensors(sensor_set_id=sensor_set_id)

        # Find specific sensors
        pure_global_sensor = None
        mixed_usage_sensor = None

        for sensor in sensors:
            if sensor.unique_id == "pure_global_sensor":
                pure_global_sensor = sensor
            elif sensor.unique_id == "mixed_usage_sensor":
                mixed_usage_sensor = sensor

        assert pure_global_sensor is not None
        assert mixed_usage_sensor is not None

        # Check pure_global_sensor internal state
        pure_global_formula = pure_global_sensor.formulas[0]
        if pure_global_formula.variables:
            # Should NOT contain global variables
            assert "shared_power_meter" not in pure_global_formula.variables
            assert "global_efficiency" not in pure_global_formula.variables
            assert "base_voltage" not in pure_global_formula.variables

        # Check mixed_usage_sensor internal state
        mixed_usage_formula = mixed_usage_sensor.formulas[0]
        assert mixed_usage_formula.variables is not None

        # Should have local variable
        assert "local_offset" in mixed_usage_formula.variables
        assert mixed_usage_formula.variables["local_offset"] == "sensor.local_adjustment"

        # Should NOT have global variables
        assert "shared_power_meter" not in mixed_usage_formula.variables
        assert "global_efficiency" not in mixed_usage_formula.variables
        assert "base_voltage" not in mixed_usage_formula.variables
