"""Test delayed entity availability and dependency re-evaluation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


@pytest.mark.asyncio
async def test_delayed_entity_availability_with_dependency_tracking(
    mock_hass,
    mock_entity_registry,
    mock_states,
    mock_config_entry,
    mock_async_add_entities,
    mock_device_registry,
):
    """Test that sensors with missing dependencies re-evaluate when entities become available.

    This test simulates the real-world scenario where:
    1. Solar sensors are created but unmapped tab entities don't exist yet
    2. Later, the unmapped tab entities become available
    3. The solar sensors should re-evaluate and get numeric values
    """

    # PHASE 1: Start with NO underlying entities available
    # (This simulates the real runtime condition)

    # Set up storage manager
    with (
        patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
        patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
    ):
        mock_store = AsyncMock()
        mock_store.async_load.return_value = None
        MockStore.return_value = mock_store
        MockDeviceRegistry.return_value = mock_device_registry

        storage_manager = StorageManager(mock_hass, "test_delayed", enable_entity_listener=False)
        storage_manager._store = mock_store
        await storage_manager.async_load()

        sensor_set_id = "span_sim_delayed"
        await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id, device_identifier="span-sim-001", name="Span Sim Delayed"
        )

        # Load solar sensor configuration
        yaml_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "span_simulator_solar.yaml"
        with open(yaml_fixture_path, "r") as f:
            yaml_content = f.read()
        result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
        assert result["sensors_imported"] == 3

        # Set up sensor manager with missing dependencies
        sensor_manager = await async_setup_synthetic_sensors(
            hass=mock_hass,
            config_entry=mock_config_entry,
            async_add_entities=mock_async_add_entities,
            storage_manager=storage_manager,
        )

        # PHASE 1 VERIFICATION: Initial update with missing entities
        await sensor_manager.async_update_sensors()

        # Get sensors
        sensors = {s.entity_id: s for s in sensor_manager.get_all_sensor_entities()}
        produced_sensor = sensors.get("sensor.solar_produced_energy")
        consumed_sensor = sensors.get("sensor.solar_consumed_energy")
        current_sensor = sensors.get("sensor.solar_current_power")

        assert produced_sensor is not None
        assert consumed_sensor is not None
        assert current_sensor is not None

        # Should have None state due to missing dependencies (first evaluation failed)
        # This confirms the dependency tracking is working - sensors detect missing entities
        assert produced_sensor.state is None
        assert consumed_sensor.state is None
        assert current_sensor.state is None

        # PHASE 2: Entities become available (simulate HA registering them)
        mock_states["sensor.span_simulator_unmapped_tab_30_power"] = type("S", (), {"state": "500.0", "attributes": {}})()
        mock_states["sensor.span_simulator_unmapped_tab_32_power"] = type("S", (), {"state": "600.0", "attributes": {}})()
        mock_states["sensor.span_simulator_unmapped_tab_30_energy_produced"] = type(
            "S", (), {"state": "100.0", "attributes": {}}
        )()
        mock_states["sensor.span_simulator_unmapped_tab_32_energy_produced"] = type(
            "S", (), {"state": "200.0", "attributes": {}}
        )()
        mock_states["sensor.span_simulator_unmapped_tab_30_energy_consumed"] = type(
            "S", (), {"state": "50.0", "attributes": {}}
        )()
        mock_states["sensor.span_simulator_unmapped_tab_32_energy_consumed"] = type(
            "S", (), {"state": "75.0", "attributes": {}}
        )()

        # Simulate dependency change notification (entities now available)
        changed_entity_ids = {
            "sensor.span_simulator_unmapped_tab_30_power",
            "sensor.span_simulator_unmapped_tab_32_power",
            "sensor.span_simulator_unmapped_tab_30_energy_produced",
            "sensor.span_simulator_unmapped_tab_32_energy_produced",
            "sensor.span_simulator_unmapped_tab_30_energy_consumed",
            "sensor.span_simulator_unmapped_tab_32_energy_consumed",
        }

        # Trigger sensor update (this should re-evaluate formulas with now-available entities)
        await sensor_manager.async_update_sensors()

        # PHASE 2 VERIFICATION: Should now have numeric values
        assert float(current_sensor.native_value) == pytest.approx(1100.0)
        assert float(produced_sensor.native_value) == pytest.approx(300.0)
        assert float(consumed_sensor.native_value) == pytest.approx(125.0)

        # Verify states are now "ok"
        assert current_sensor.state == "ok" or isinstance(current_sensor.native_value, (int, float))
        assert produced_sensor.state == "ok" or isinstance(produced_sensor.native_value, (int, float))
        assert consumed_sensor.state == "ok" or isinstance(consumed_sensor.native_value, (int, float))
