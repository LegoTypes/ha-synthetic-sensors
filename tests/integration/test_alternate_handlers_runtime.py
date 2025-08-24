"""Integration tests for runtime alternate handlers and scoped guard behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors


@pytest.mark.asyncio
async def test_alternate_handlers_and_guard_runtime(
    mock_hass,
    mock_entity_registry,
    mock_states,
    mock_config_entry,
    mock_async_add_entities,
    mock_device_registry,
):
    """Verify literal and object-form alternates at runtime and guard scoping with metadata-only CV."""

    # Save original state for restoration (following test isolation pattern)
    original_entities = dict(mock_entity_registry._entities)
    original_states = dict(mock_states)

    try:
        # Set up YAML entity references (real HA entities that YAML variables reference)
        # These ARE in the HA registry because they're referenced in YAML variables

        # Entity referenced in guard_metadata_sensor formula and within_grace variable
        mock_entity_registry.register_entity("sensor.guard_backing", "sensor.guard_backing", "sensor")
        # Set up the HA entity with proper metadata for the within_grace computation
        mock_states.register_state("sensor.guard_backing", "100.0", {"unit_of_measurement": "W"})

        # Set up additional metadata for the within_grace computation
        # The metadata handler expects these attributes on the state object
        mock_state = mock_states["sensor.guard_backing"]
        mock_state.last_changed = datetime.now(timezone.utc) - timedelta(minutes=1)  # Recent change
        mock_state.last_updated = datetime.now(timezone.utc)

        # Also ensure the state object has the proper structure for metadata access
        if not hasattr(mock_state, "as_dict"):

            def as_dict():
                return {
                    "state": mock_state.state,
                    "attributes": mock_state.attributes,
                    "last_changed": mock_state.last_changed.isoformat()
                    if hasattr(mock_state.last_changed, "isoformat")
                    else str(mock_state.last_changed),
                    "last_updated": mock_state.last_updated.isoformat()
                    if hasattr(mock_state.last_updated, "isoformat")
                    else str(mock_state.last_updated),
                    "entity_id": mock_state.entity_id,
                }

            mock_state.as_dict = as_dict

        # Unused variable with unknown state (should not affect within_grace)
        mock_entity_registry.register_entity("sensor.unused_unknown", "sensor.unused_unknown", "sensor")
        mock_states.register_state("sensor.unused_unknown", "unknown", {})

        # Missing entity used to trigger alternates: represent as UNAVAILABLE so context isn't raw None
        mock_entity_registry.register_entity("sensor.nonexistent_value", "sensor.nonexistent_value", "sensor")
        mock_states.register_state("sensor.nonexistent_value", "unavailable", {})

        # Add missing dependencies referenced in the YAML variables
        mock_entity_registry.register_entity("sensor.multiplier_value", "sensor.multiplier_value", "sensor")
        mock_states.register_state("sensor.multiplier_value", "unavailable", {})  # Make unavailable to trigger alternates

        mock_entity_registry.register_entity("sensor.offset_value", "sensor.offset_value", "sensor")
        mock_states.register_state("sensor.offset_value", "unavailable", {})  # Make unavailable to trigger alternates

        # Register entities used by new literal tests
        # Entity that should be None to trigger NONE handler
        mock_entity_registry.register_entity("sensor.none_value", "sensor.none_value", "sensor")
        mock_states.register_state("sensor.none_value", None, {})

        # Entity that should be unavailable to trigger UNAVAILABLE (and fallback selection)
        mock_entity_registry.register_entity("sensor.fallback_trigger", "sensor.fallback_trigger", "sensor")
        mock_states.register_state("sensor.fallback_trigger", "unavailable", {})
        # Entities for new computed-variable and attribute alternate tests
        mock_entity_registry.register_entity("sensor.missing_for_cv", "sensor.missing_for_cv", "sensor")
        mock_states.register_state("sensor.missing_for_cv", "unavailable", {})

        mock_entity_registry.register_entity("sensor.attr_backing", "sensor.attr_backing", "sensor")
        mock_states.register_state("sensor.attr_backing", "100.0", {})
        mock_entity_registry.register_entity("sensor.missing_attr_var", "sensor.missing_attr_var", "sensor")
        mock_states.register_state("sensor.missing_attr_var", "unavailable", {})

        yaml_path = Path(__file__).parent.parent / "fixtures" / "integration" / "alternate_handlers_runtime.yaml"

        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
            patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            sensor_set_id = "alternate_handlers_runtime"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_alternate_handlers_runtime",
                name="Alternate Handlers Runtime",
            )

            with open(yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 16

            # Set up backing entities for sensors that use the 'state' token
            # These are virtual entities that provide data for sensors with entity_id
            backing_data = {
                "sensor.comprehensive_backing": 100.0,
                "sensor.mixed_backing": 200.0,
                "sensor.fallback_backing": 300.0,
                "sensor.priority_backing": 400.0,
                "sensor.string_backing": "test_value",
                "sensor.boolean_backing": 500.0,
                "sensor.energy_backing": 1000.0,
            }

            def create_data_provider_callback(backing_data: dict[str, any]):
                def data_provider(entity_id: str):
                    return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

                return data_provider

            data_provider = create_data_provider_callback(backing_data)

            # Create sensor-to-backing mapping for sensors that use 'state' token
            sensor_to_backing_mapping = {
                "comprehensive_literal_sensor": "sensor.comprehensive_backing",
                "comprehensive_object_sensor": "sensor.comprehensive_backing",
                "mixed_literal_sensor": "sensor.mixed_backing",
                "mixed_object_sensor": "sensor.mixed_backing",
                "fallback_when_no_specific_handler": "sensor.fallback_backing",
                "final_fallback_priority_order": "sensor.priority_backing",
                "string_alternate_sensor": "sensor.string_backing",
                "boolean_alternate_sensor": "sensor.boolean_backing",
                "energy_alternate_sensor": "sensor.energy_backing",
            }

            def change_notifier_callback(changed_entity_ids: set[str]) -> None:
                pass  # Enable selective updates

            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Collect created entities and set hass
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)
            mock_platform = Mock()
            for entity in all_entities:
                entity.hass = mock_hass
                entity.platform = mock_platform

            await sensor_manager.async_update_sensors()

            entity_lookup = {entity.unique_id: entity for entity in all_entities}

            # Guard + metadata-only CV: ensure unaffected by unused unknown variable
            guard_entity = entity_lookup.get("guard_metadata_sensor")
            assert guard_entity is not None, (
                f"Sensor 'guard_metadata_sensor' not found. Available sensors: {list(entity_lookup.keys())}"
            )

            # (debug prints removed) rely on explicit assertions below instead of printing
            # Assign commonly checked entities for assertions
            literal_entity = entity_lookup.get("literal_alternate_sensor")
            object_entity = entity_lookup.get("object_alternate_sensor")

            # The issue is that the computed variable evaluation is failing and causing
            # the entire sensor to be unavailable. This needs to be fixed properly.

            # For now, let's verify the other sensors work, but we need to come back
            # and fix the metadata evaluation issue
            assert literal_entity.native_value == 11, f"Literal sensor should be 11, got {literal_entity.native_value}"
            assert object_entity.native_value == 6, f"Object sensor should be 6, got {object_entity.native_value}"

            # Guard + metadata-only CV: ensure unaffected by unused unknown variable
            attrs = getattr(guard_entity, "extra_state_attributes", {}) or {}
            assert "grace_period_active" in attrs
            # within_grace should evaluate to True because we set last_changed ~1 minute ago
            # and grace_minutes is 15 in the YAML fixture. Accept truthy values (True or 1).
            val = attrs["grace_period_active"]
            assert bool(val) is True, f"Expected within_grace to be True, got {val!r}"

            # Test comprehensive literal sensor with all handler types
            comprehensive_literal = entity_lookup.get("comprehensive_literal_sensor")
            assert comprehensive_literal is not None
            # Since the backing entity is available, it should use the main formula, not alternates
            # But we can test that the sensor was created correctly
            assert comprehensive_literal.available is True

            # Test comprehensive object sensor
            comprehensive_object = entity_lookup.get("comprehensive_object_sensor")
            assert comprehensive_object is not None
            assert comprehensive_object.available is True

            # Test mixed handlers sensor
            mixed_handlers = entity_lookup.get("mixed_handlers_sensor")
            assert mixed_handlers is not None
            assert mixed_handlers.available is True

            # New tests for literal NONE and FALLBACK sensors
            literal_none = entity_lookup.get("literal_none_sensor")
            assert literal_none is not None
            # Runtime maps Python None to UNKNOWN in this integration flow; expect UNKNOWN handler (22)
            assert literal_none.native_value == 22, f"Literal NONE sensor should be 22, got {literal_none.native_value}"

            literal_fallback = entity_lookup.get("literal_fallback_sensor")
            assert literal_fallback is not None
            # Expect UNAVAILABLE handler to provide 21 when referenced entity is 'unavailable'
            assert literal_fallback.native_value == 21, (
                f"Literal FALLBACK sensor should be 21, got {literal_fallback.native_value}"
            )

            # Test main-level UNAVAILABLE alternate handler for computed main formula
            cv_entity = entity_lookup.get("computed_main_fallback_sensor")
            assert cv_entity is not None
            # primary is unavailable -> UNAVAILABLE handler formula backup_calc + 1 = 56
            assert float(cv_entity.native_value) == 56.0, f"Computed main fallback should be 56, got {cv_entity.native_value}"

            # Test attribute-level object-form alternate handler
            attr_entity = entity_lookup.get("attribute_variable_fallback_sensor")
            assert attr_entity is not None
            attrs = getattr(attr_entity, "extra_state_attributes", {}) or {}
            assert "attr_value" in attrs
            # UNAVAILABLE attribute handler computes alt_base + alt_offset = 9
            assert float(attrs["attr_value"]) == 9.0, f"Attribute fallback should be 9, got {attrs['attr_value']}"

            # Test fallback only sensor
            fallback_only = entity_lookup.get("fallback_only_sensor")
            assert fallback_only is not None
            assert fallback_only.available is True

            # Test fallback object sensor
            fallback_object = entity_lookup.get("fallback_object_sensor")
            assert fallback_object is not None
            assert fallback_object.available is True

            # Test priority test sensor
            priority_test = entity_lookup.get("priority_test_sensor")
            assert priority_test is not None
            assert priority_test.available is True

            # Test string handlers sensor
            string_handlers = entity_lookup.get("string_handlers_sensor")
            assert string_handlers is not None
            assert string_handlers.available is True

            # Test boolean handlers sensor
            boolean_handlers = entity_lookup.get("boolean_handlers_sensor")
            assert boolean_handlers is not None
            assert boolean_handlers.available is True

            # Test energy none sensor
            energy_none = entity_lookup.get("energy_none_sensor")
            assert energy_none is not None
            assert energy_none.available is True

            await storage_manager.async_delete_sensor_set(sensor_set_id)

    finally:
        # Restore original state to avoid affecting other tests
        mock_entity_registry._entities.clear()
        mock_entity_registry._entities.update(original_entities)
        mock_states.clear()
        mock_states.update(original_states)


@pytest.mark.asyncio
async def test_alternate_handlers_with_none_backing_entities(
    mock_hass,
    mock_entity_registry,
    mock_states,
    mock_config_entry,
    mock_async_add_entities,
    mock_device_registry,
):
    """Test alternate handlers when backing entities have None values (integration offline scenario)."""

    # Backing entity that will be set to None (simulating integration offline)
    mock_entity_registry.register_entity("sensor.offline_backing", "sensor.offline_backing", "sensor")
    mock_states.register_state("sensor.offline_backing", None, {})  # This is the key - None value

    yaml_path = Path(__file__).parent.parent / "fixtures" / "integration" / "offline_scenario.yaml"
    with open(yaml_path, "r") as f:
        yaml_content = f.read()

    with (
        patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
        patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
        patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
    ):
        mock_store = AsyncMock()
        mock_store.async_load.return_value = None
        MockStore.return_value = mock_store
        MockDeviceRegistry.return_value = mock_device_registry

        storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
        storage_manager._store = mock_store
        await storage_manager.async_load()

        sensor_set_id = "offline_scenario"
        await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier="test_offline_scenario",
            name="Offline Scenario Test",
        )

        result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
        assert result["sensors_imported"] == 1

        sensor_manager = await async_setup_synthetic_sensors(
            hass=mock_hass,
            config_entry=mock_config_entry,
            async_add_entities=mock_async_add_entities,
            storage_manager=storage_manager,
        )

        # Collect created entities and set hass
        all_entities = []
        for call in mock_async_add_entities.call_args_list:
            entities_list = call.args[0] if call.args else []
            all_entities.extend(entities_list)
        mock_platform = Mock()
        for entity in all_entities:
            entity.hass = mock_hass
            entity.platform = mock_platform

        # Set last_changed to recent time to make within_grace True
        for entity in all_entities:
            if getattr(entity, "unique_id", "") == "offline_sensor":
                mock_state = type(
                    "MockState",
                    (),
                    {
                        "state": None,  # Simulate offline backing entity
                        "attributes": {},
                    },
                )()
                mock_state.entity_id = entity.entity_id
                mock_state.object_id = entity.entity_id.split(".")[-1]
                mock_state.domain = entity.entity_id.split(".")[0]
                mock_state.last_changed = datetime.now(timezone.utc) - timedelta(minutes=1)  # Recent, within grace
                mock_state.last_updated = datetime.now(timezone.utc)
                mock_states[entity.entity_id] = mock_state

        # This should not raise an exception - the alternate handler should work
        await sensor_manager.async_update_sensors()

        entity_lookup = {entity.unique_id: entity for entity in all_entities}

        # The sensor should have a value from the alternate handler, not be unavailable
        offline_entity = entity_lookup.get("offline_sensor")
        assert offline_entity is not None

        # The sensor should be available because the alternate handler should have worked
        # When state=None (converted to "unknown") and within_grace=True,
        # the formula "state if within_grace else 'unknown'" should return a fallback value
        assert offline_entity.available is True  # Sensor should be available
        assert offline_entity.native_value is not None  # Should have a fallback value

        # The alternate handler successfully provided a fallback value instead of failing
        # This demonstrates that the fix allows alternate handlers to work when backing entities are None/unknown

        await storage_manager.async_delete_sensor_set(sensor_set_id)


@pytest.mark.asyncio
async def test_alternate_handlers_with_unavailable_backing_entities(
    mock_hass,
    mock_entity_registry,
    mock_states,
    mock_config_entry,
    mock_async_add_entities,
    mock_device_registry,
):
    """Test alternate handlers when backing entities are unavailable (not None)."""

    # Backing entity that will be set to "unavailable" (different from None)
    mock_entity_registry.register_entity("sensor.unavailable_backing", "sensor.unavailable_backing", "sensor")
    mock_states.register_state("sensor.unavailable_backing", "unavailable", {})  # Explicitly unavailable

    yaml_path = Path(__file__).parent.parent / "fixtures" / "integration" / "unavailable_scenario.yaml"
    with open(yaml_path, "r") as f:
        yaml_content = f.read()

    with (
        patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
        patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
        patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
    ):
        mock_store = AsyncMock()
        mock_store.async_load.return_value = None
        MockStore.return_value = mock_store
        MockDeviceRegistry.return_value = mock_device_registry

        storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
        storage_manager._store = mock_store
        await storage_manager.async_load()

        sensor_set_id = "unavailable_scenario"
        await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier="test_unavailable_scenario",
            name="Unavailable Scenario Test",
        )

        result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
        assert result["sensors_imported"] == 1

        sensor_manager = await async_setup_synthetic_sensors(
            hass=mock_hass,
            config_entry=mock_config_entry,
            async_add_entities=mock_async_add_entities,
            storage_manager=storage_manager,
        )

        # Collect created entities and set hass
        all_entities = []
        for call in mock_async_add_entities.call_args_list:
            entities_list = call.args[0] if call.args else []
            all_entities.extend(entities_list)
        mock_platform = Mock()
        for entity in all_entities:
            entity.hass = mock_hass
            entity.platform = mock_platform

        # Set last_changed to recent time to make within_grace True
        for entity in all_entities:
            if getattr(entity, "unique_id", "") == "unavailable_sensor":
                mock_state = type(
                    "MockState",
                    (),
                    {
                        "state": "unavailable",  # Explicitly unavailable
                        "attributes": {},
                    },
                )()
                mock_state.entity_id = entity.entity_id
                mock_state.object_id = entity.entity_id.split(".")[-1]
                mock_state.domain = entity.entity_id.split(".")[0]
                mock_state.last_changed = datetime.now(timezone.utc) - timedelta(minutes=1)
                mock_state.last_updated = datetime.now(timezone.utc)
                mock_states[entity.entity_id] = mock_state

        # This should not raise an exception - the alternate handler should work
        await sensor_manager.async_update_sensors()

        entity_lookup = {entity.unique_id: entity for entity in all_entities}

        # The sensor should have a value from the alternate handler, not be unavailable
        unavailable_entity = entity_lookup.get("unavailable_sensor")
        assert unavailable_entity is not None

        # The sensor should be available because the alternate handler should have worked
        assert unavailable_entity.available is True  # Sensor should be available
        assert unavailable_entity.native_value is not None  # Should have a fallback value

        # The alternate handler successfully provided a fallback value instead of failing
        # This demonstrates that the fix works for both "unknown" and "unavailable" states

        await storage_manager.async_delete_sensor_set(sensor_set_id)


@pytest.mark.asyncio
async def test_allow_unresolved_states_behavior(
    mock_hass,
    mock_entity_registry,
    mock_states,
    mock_config_entry,
    mock_async_add_entities,
    mock_device_registry,
):
    """Test allow_unresolved_states: true behavior allowing formulas to test for unavailable states."""

    # Add backing entity for the allow_unresolved_states test
    mock_entity_registry.register_entity("sensor.allow_unresolved_backing", "sensor.allow_unresolved_backing", "sensor")
    mock_states.register_state("sensor.allow_unresolved_backing", "unavailable", {})

    yaml_path = Path(__file__).parent.parent / "fixtures" / "integration" / "allow_unresolved_states.yaml"
    with open(yaml_path, "r") as f:
        yaml_content = f.read()

    with (
        patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
        patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
        patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
    ):
        mock_store = AsyncMock()
        mock_store.async_load.return_value = None
        MockStore.return_value = mock_store
        MockDeviceRegistry.return_value = mock_device_registry

        storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
        storage_manager._store = mock_store
        await storage_manager.async_load()

        sensor_set_id = "allow_unresolved_states"
        await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier="test_allow_unresolved_states",
            name="Allow Unresolved States Test",
        )

        result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
        assert result["sensors_imported"] == 1

        sensor_manager = await async_setup_synthetic_sensors(
            hass=mock_hass,
            config_entry=mock_config_entry,
            async_add_entities=mock_async_add_entities,
            storage_manager=storage_manager,
        )

        # Collect created entities and set hass
        all_entities = []
        for call in mock_async_add_entities.call_args_list:
            entities_list = call.args[0] if call.args else []
            all_entities.extend(entities_list)
        for entity in all_entities:
            entity.hass = mock_hass

        # Set last_changed to recent time to make within_grace True
        for entity in all_entities:
            if getattr(entity, "unique_id", "") == "allow_unresolved_sensor":
                mock_state = type(
                    "MockState",
                    (),
                    {
                        "state": "unavailable",  # Explicitly unavailable
                        "attributes": {},
                    },
                )()
                mock_state.entity_id = entity.entity_id
                mock_state.object_id = entity.entity_id.split(".")[-1]
                mock_state.domain = entity.entity_id.split(".")[0]
                mock_state.last_changed = datetime.now(timezone.utc) - timedelta(minutes=1)
                mock_state.last_updated = datetime.now(timezone.utc)
                mock_states[entity.entity_id] = mock_state

        # This should not raise an exception - the allow_unresolved_states should allow the formula to evaluate
        await sensor_manager.async_update_sensors()

        entity_lookup = {entity.unique_id: entity for entity in all_entities}

        # The sensor should have a value from the alternate handler, not be unavailable
        allow_unresolved_entity = entity_lookup.get("allow_unresolved_sensor")
        assert allow_unresolved_entity is not None

        # The sensor should be available because the allow_unresolved_states allowed the formula to evaluate
        # and the alternate handler provided a fallback value
        assert allow_unresolved_entity.available is True  # Sensor should be available
        assert allow_unresolved_entity.native_value is not None  # Should have a fallback value

        # This demonstrates that allow_unresolved_states: true allows the formula to proceed into evaluation
        # where it can test for the sensor being in 'unavailable' state and handle it appropriately

        await storage_manager.async_delete_sensor_set(sensor_set_id)
