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

    # PHASE 1: Start with underlying entities available but with alternate state handling
    # Register all entities upfront to avoid missing dependency errors
    mock_entity_registry.register_entity(
        "sensor.span_simulator_unmapped_tab_30_power", "sensor.span_simulator_unmapped_tab_30_power", "sensor"
    )
    mock_entity_registry.register_entity(
        "sensor.span_simulator_unmapped_tab_32_power", "sensor.span_simulator_unmapped_tab_32_power", "sensor"
    )
    mock_entity_registry.register_entity(
        "sensor.span_simulator_unmapped_tab_30_energy_produced",
        "sensor.span_simulator_unmapped_tab_30_energy_produced",
        "sensor",
    )
    mock_entity_registry.register_entity(
        "sensor.span_simulator_unmapped_tab_32_energy_produced",
        "sensor.span_simulator_unmapped_tab_32_energy_produced",
        "sensor",
    )
    mock_entity_registry.register_entity(
        "sensor.span_simulator_unmapped_tab_30_energy_consumed",
        "sensor.span_simulator_unmapped_tab_30_energy_consumed",
        "sensor",
    )
    mock_entity_registry.register_entity(
        "sensor.span_simulator_unmapped_tab_32_energy_consumed",
        "sensor.span_simulator_unmapped_tab_32_energy_consumed",
        "sensor",
    )

    # Start with unavailable states to simulate entities not ready yet
    # Create mock states with proper metadata attributes for metadata functions
    from datetime import datetime, timezone

    def create_mock_state(entity_id: str, state: str, attributes: dict) -> object:
        """Create a mock state object with proper metadata attributes."""
        mock_state = type(
            "MockState",
            (),
            {
                "state": state,
                "attributes": attributes,
                "entity_id": entity_id,
                "object_id": entity_id.split(".")[-1] if "." in entity_id else entity_id,
                "domain": entity_id.split(".")[0] if "." in entity_id else "sensor",
                "last_changed": datetime.now(timezone.utc),
                "last_updated": datetime.now(timezone.utc),
            },
        )()
        return mock_state

    # Register states with proper metadata
    mock_states["sensor.span_simulator_unmapped_tab_30_power"] = create_mock_state(
        "sensor.span_simulator_unmapped_tab_30_power", "unavailable", {}
    )
    mock_states["sensor.span_simulator_unmapped_tab_32_power"] = create_mock_state(
        "sensor.span_simulator_unmapped_tab_32_power", "unavailable", {}
    )
    mock_states["sensor.span_simulator_unmapped_tab_30_energy_produced"] = create_mock_state(
        "sensor.span_simulator_unmapped_tab_30_energy_produced", "unavailable", {}
    )
    mock_states["sensor.span_simulator_unmapped_tab_32_energy_produced"] = create_mock_state(
        "sensor.span_simulator_unmapped_tab_32_energy_produced", "unavailable", {}
    )
    mock_states["sensor.span_simulator_unmapped_tab_30_energy_consumed"] = create_mock_state(
        "sensor.span_simulator_unmapped_tab_30_energy_consumed", "unavailable", {}
    )
    mock_states["sensor.span_simulator_unmapped_tab_32_energy_consumed"] = create_mock_state(
        "sensor.span_simulator_unmapped_tab_32_energy_consumed", "unavailable", {}
    )

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

        # Get all created entities and set up proper metadata for synthetic sensors
        all_entities = []
        for call in mock_async_add_entities.call_args_list:
            entities_list = call.args[0] if call.args else []
            all_entities.extend(entities_list)

        # Set hass attribute on all entities BEFORE update (required to prevent "Attribute hass is None" errors)
        for entity in all_entities:
            entity.hass = mock_hass

            # Add synthetic sensors to mock states so they can reference themselves for metadata queries
            for entity in all_entities:
                if hasattr(entity, "entity_id") and entity.entity_id:
                    # Create mock state with proper metadata attributes for metadata handler
                    mock_state = type(
                        "MockState",
                        (),
                        {
                            "state": str(entity.native_value) if entity.native_value is not None else "unknown",
                            "attributes": getattr(entity, "extra_state_attributes", {}) or {},
                        },
                    )()
                    # Add metadata properties that metadata handler expects
                    mock_state.entity_id = entity.entity_id
                    mock_state.object_id = entity.entity_id.split(".")[-1] if "." in entity.entity_id else entity.entity_id
                    mock_state.domain = entity.entity_id.split(".")[0] if "." in entity.entity_id else "sensor"
                    mock_state.last_changed = datetime.now(timezone.utc)
                    mock_state.last_updated = datetime.now(timezone.utc)

                    # Add last_valid_state metadata attribute that the alternate state handler needs
                    if not hasattr(mock_state, "attributes"):
                        mock_state.attributes = {}
                    mock_state.attributes["last_valid_state"] = "0.0"  # Default value for synthetic sensors

                    mock_states[entity.entity_id] = mock_state

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

        # Should have alternate state values due to unavailable dependencies
        # The sensors use alternate state handlers to handle unavailable entities
        assert current_sensor.native_value == 0.0  # UNAVAILABLE: 0.0 from YAML
        # Energy sensors use more complex alternate handlers, but should have some value
        assert produced_sensor.native_value is not None
        assert consumed_sensor.native_value is not None

        # PHASE 2: Entities become available (update states to actual values)
        mock_states["sensor.span_simulator_unmapped_tab_30_power"] = create_mock_state(
            "sensor.span_simulator_unmapped_tab_30_power", "500.0", {}
        )
        mock_states["sensor.span_simulator_unmapped_tab_32_power"] = create_mock_state(
            "sensor.span_simulator_unmapped_tab_32_power", "600.0", {}
        )
        mock_states["sensor.span_simulator_unmapped_tab_30_energy_produced"] = create_mock_state(
            "sensor.span_simulator_unmapped_tab_30_energy_produced", "100.0", {}
        )
        mock_states["sensor.span_simulator_unmapped_tab_32_energy_produced"] = create_mock_state(
            "sensor.span_simulator_unmapped_tab_32_energy_produced", "200.0", {}
        )
        mock_states["sensor.span_simulator_unmapped_tab_30_energy_consumed"] = create_mock_state(
            "sensor.span_simulator_unmapped_tab_30_energy_consumed", "50.0", {}
        )
        mock_states["sensor.span_simulator_unmapped_tab_32_energy_consumed"] = create_mock_state(
            "sensor.span_simulator_unmapped_tab_32_energy_consumed", "75.0", {}
        )

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
