from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


@pytest.mark.asyncio
async def test_span_simulator_solar_direct_entity_refs(
    mock_hass,
    mock_entity_registry,
    mock_states,
    mock_config_entry,
    mock_async_add_entities,
    mock_device_registry,
):
    """Validate direct entity_id formulas resolve via substitution after metadata.

    YAML references:
      - sensor.span_simulator_unmapped_tab_30_power/_energy_produced/_energy_consumed
      - sensor.span_simulator_unmapped_tab_32_power/_energy_produced/_energy_consumed
    """

    # Seed required HA entities with numeric states
    from unittest.mock import Mock

    mock_states["sensor.span_simulator_unmapped_tab_30_power"] = Mock(
        state="500.0", entity_id="sensor.span_simulator_unmapped_tab_30_power", attributes={}
    )
    mock_states["sensor.span_simulator_unmapped_tab_32_power"] = Mock(
        state="600.0", entity_id="sensor.span_simulator_unmapped_tab_32_power", attributes={}
    )
    mock_states["sensor.span_simulator_unmapped_tab_30_energy_produced"] = Mock(
        state="100.0", entity_id="sensor.span_simulator_unmapped_tab_30_energy_produced", attributes={}
    )
    mock_states["sensor.span_simulator_unmapped_tab_32_energy_produced"] = Mock(
        state="200.0", entity_id="sensor.span_simulator_unmapped_tab_32_energy_produced", attributes={}
    )
    mock_states["sensor.span_simulator_unmapped_tab_30_energy_consumed"] = Mock(
        state="50.0", entity_id="sensor.span_simulator_unmapped_tab_30_energy_consumed", attributes={}
    )
    mock_states["sensor.span_simulator_unmapped_tab_32_energy_consumed"] = Mock(
        state="75.0", entity_id="sensor.span_simulator_unmapped_tab_32_energy_consumed", attributes={}
    )

    # Set up storage manager with proper mocking
    with (
        patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
        patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
    ):
        mock_store = AsyncMock()
        mock_store.async_load.return_value = None
        MockStore.return_value = mock_store
        MockDeviceRegistry.return_value = mock_device_registry

        storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
        storage_manager._store = mock_store
        await storage_manager.async_load()

        sensor_set_id = "span_sim_solar"
        await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id, device_identifier="span-sim-001", name="Span Sim Solar"
        )

        yaml_fixture_path = Path(__file__).parent.parent / "fixtures" / "integration" / "span_simulator_solar.yaml"
        with open(yaml_fixture_path, "r") as f:
            yaml_content = f.read()
        result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
        assert result["sensors_imported"] == 3

        sensor_manager = await async_setup_synthetic_sensors(
            hass=mock_hass,
            config_entry=mock_config_entry,
            async_add_entities=mock_async_add_entities,
            storage_manager=storage_manager,
        )

        # Force an update to evaluate formulas
        await sensor_manager.async_update_sensors()

        # Lookup created sensors by entity_id
        sensors = {s.entity_id: s for s in sensor_manager.get_all_sensor_entities()}
        # Account for entity_id collision suffixes introduced by registry
        produced = sensors.get("sensor.solar_produced_energy") or sensors.get("sensor.solar_produced_energy_2")
        consumed = sensors.get("sensor.solar_consumed_energy") or sensors.get("sensor.solar_consumed_energy_2")
        current = sensors.get("sensor.solar_current_power") or sensors.get("sensor.solar_current_power_2")

        assert produced is not None and consumed is not None and current is not None

        # Validate numerical substitution results (no variables required)
        assert float(current.native_value) == pytest.approx(1100.0)
        assert float(produced.native_value) == pytest.approx(300.0)
        assert float(consumed.native_value) == pytest.approx(125.0)
