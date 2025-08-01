# Integration Test Guide: Using Synthetic Sensors Public API

This guide explains how to properly set up integration tests that use the `ha-synthetic-sensors` public API, based on lessons
learned from implementing `test_dependency_resolution_with_missing_entities`.

## Overview

Integration tests for synthetic sensors should test the complete flow from YAML configuration through formula evaluation
using the public API methods. This guide covers the essential patterns and common pitfalls.

## 🏆 GOLDEN RULE: Use Common Registry Fixtures

**CRITICAL:** Always use the common registry fixtures from `conftest.py`. The most common test failures occur when developers
try to create custom registry mocks instead of using the established fixtures.

**✅ DO:**

```python
async def test_your_integration_test(
    self, mock_hass, mock_entity_registry, mock_states,  # Use common fixtures
    your_yaml_fixture_path, mock_config_entry, mock_async_add_entities
):
```

**❌ DON'T:**

```python
# Never create custom registry mocks
mock_entity_registry = Mock()  # This will cause failures
mock_states = {}  # This will cause failures
```

**Why:** The common fixtures provide a complete, tested HA environment. Custom mocks are incomplete and cause dependency
resolution failures.

## Required Fixtures and Setup

### 1. Use the Common Registry Fixtures (GOLDEN RULE)

**ALWAYS use these standard fixtures from `conftest.py` - DO NOT create your own registry mocks:**

```python
async def test_your_integration_test(
    self, mock_hass, mock_entity_registry, mock_states,
    your_yaml_fixture_path, mock_config_entry, mock_async_add_entities
):
```

**Key Points:**

- `mock_entity_registry` contains all the domain data (`sensor`, `binary_sensor`, etc.) needed for entity ID recognition
- `mock_states` provides the HA state lookup mechanism
- `mock_hass` provides the core HA instance mock
- **NEVER create custom registry mocks** - the common fixtures provide the complete HA environment
- **ONLY add what's missing** - if you need additional entities, add them to the existing fixtures, don't replace them

### 2. Common Device Registry Fixture

Add this fixture to your test class for proper device registration:

```python
@pytest.fixture
def mock_device_entry(self):
    """Create a mock device entry for testing."""
    mock_device_entry = Mock()
    mock_device_entry.name = "Test Device"  # Will be slugified for entity IDs
    mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
    return mock_device_entry

@pytest.fixture
def mock_device_registry(self, mock_device_entry):
    """Create a mock device registry that returns the test device."""
    mock_registry = Mock()
    mock_registry.devices = Mock()
    mock_registry.async_get_device.return_value = mock_device_entry
    return mock_registry
```

**Important:** This device registry fixture is **additional** to the common registry fixtures - it doesn't replace them.

### 3. Essential Imports

```python
from unittest.mock import AsyncMock, Mock, patch
from ha_synthetic_sensors import (
    async_setup_synthetic_sensors,
    StorageManager,
    DataProviderCallback,
)
```

## Storage Manager Setup Pattern

### Problem: Storage Manager File System Issues

The `StorageManager` uses HA's Store class which tries to access the file system. In tests, this causes issues.

### Solution: Mock the Store Class

```python
# Create storage manager using public API with mocked Store
with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore, \
     patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry:

    # Mock Store to avoid file system access
    mock_store = AsyncMock()
    mock_store.async_load.return_value = None  # Empty storage initially
    MockStore.return_value = mock_store

    # Use the common device registry fixture
    MockDeviceRegistry.return_value = mock_device_registry

    storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
    storage_manager._store = mock_store
    await storage_manager.async_load()

    # Rest of your test code goes here...
```

**Critical Details:**

- Always use `enable_entity_listener=False` to avoid entity registry listener issues unless you test is testing event
  listening (for entity_id changes, etc.)
- Mock both Store and DeviceRegistry in the same context manager
- Set `async_load.return_value = None` for empty initial storage

## YAML Configuration Patterns

### 1. Include Device Identifier in YAML

Your YAML fixtures must include the device identifier in global settings:

```yaml
version: "1.0"

global_settings:
  device_identifier: "test_device_123" # Must match the device_identifier in your test

sensors:
  your_sensor:
    name: "Your Test Sensor"
    formula: "state + sensor.external_entity"
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
```

**Why:** The `async_setup_synthetic_sensors` function filters sensors by `device_identifier`, so sensors must be associated
with the right device.

### 2. Load YAML into Storage Manager

```python
# Create sensor set first
sensor_set_id = "your_test_id"
await storage_manager.async_create_sensor_set(
    sensor_set_id=sensor_set_id,
    device_identifier="test_device_123",  # Must match YAML global_settings
    name="Your Test Sensors"
)

# Load YAML content
with open(your_yaml_fixture_path, 'r') as f:
    yaml_content = f.read()

# Import YAML with dependency resolution
result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)

# Verify import succeeded
assert result["sensors_imported"] == expected_count
```

## Data Provider and Change Notification Patterns

### Pattern 1: Virtual Backing Entities (Recommended for Device Integrations)

Use when you have custom data that doesn't exist as real HA entities:

```python
# Set up virtual backing entity data
backing_data = {
    "sensor.virtual_backing_entity": 1000.0
}

# Create data provider for virtual backing entities
def create_data_provider_callback(backing_data: dict[str, any]) -> DataProviderCallback:
    def data_provider(entity_id: str):
        return {
            "value": backing_data.get(entity_id),
            "exists": entity_id in backing_data
        }
    return data_provider

data_provider = create_data_provider_callback(backing_data)

# Create change notifier callback for selective updates
def change_notifier_callback(changed_entity_ids: set[str]) -> None:
    # This enables real-time selective sensor updates
    pass

# Create sensor-to-backing mapping for 'state' token resolution
sensor_to_backing_mapping = {
    "your_sensor_unique_id": "sensor.virtual_backing_entity"
}

# Use public API with virtual backing entities
sensor_manager = await async_setup_synthetic_sensors(
    hass=mock_hass,
    config_entry=mock_config_entry,
    async_add_entities=mock_async_add_entities,
    storage_manager=storage_manager,
    device_identifier="test_device_123",
    data_provider_callback=data_provider,  # For virtual entities
    change_notifier=change_notifier_callback,  # Enable selective updates
    sensor_to_backing_mapping=sensor_to_backing_mapping,  # Map 'state' token
)
```

### Pattern 2: HA Entity References (For Cross-Integration Tests)

Use when testing with existing HA entities. **Note:** The system automatically falls back to HA entity lookups when entities
are not found in the data provider or backing mappings.

```python
# Add entities to mock_states for HA lookup
mock_states["sensor.external_entity"] = type("MockState", (), {
    "state": "500.0",
    "attributes": {}
})()

# Use public API with HA entity lookups only
sensor_manager = await async_setup_synthetic_sensors(
    hass=mock_hass,
    config_entry=mock_config_entry,
    async_add_entities=mock_async_add_entities,
    storage_manager=storage_manager,
    device_identifier="test_device_123",
    # No data_provider_callback - uses HA entity lookups
    # No change_notifier - automatic via HA state tracking
    # No sensor_to_backing_mapping - entities from YAML variables
)
```

### Pattern 3: Hybrid (Virtual + HA Entities) - For Complex Tests

Use when you need both virtual backing entities and references to existing HA entities. **Entity Resolution Order:** The
system first checks the data provider and backing mappings, then automatically falls back to HA entity lookups if not found.

```python
# Set up virtual backing entities
backing_data = {
    "sensor.virtual_backing": 1000.0
}

# Set up mock HA entities (for fallback lookup)
mock_states["sensor.external_entity"] = type("MockState", (), {
    "state": "500.0",
    "attributes": {}
})()

# Ensure missing entities are NOT in mock_states to test missing entity handling
if "sensor.missing_entity" in mock_states:
    del mock_states["sensor.missing_entity"]

data_provider = create_data_provider_callback(backing_data)

# Hybrid setup - virtual backing with HA entity fallback
sensor_manager = await async_setup_synthetic_sensors(
    hass=mock_hass,
    config_entry=mock_config_entry,
    async_add_entities=mock_async_add_entities,
    storage_manager=storage_manager,
    device_identifier="test_device_123",
    data_provider_callback=data_provider,  # For virtual entities
    change_notifier=change_notifier_callback,  # For virtual updates
    sensor_to_backing_mapping=sensor_to_backing_mapping,  # Map virtual entities
    # System automatically falls back to HA lookups for entities not in data provider
)
```

## Testing Formula Evaluation

### Exercise Both Update Mechanisms

Test both selective and general update methods:

```python
# Test selective updates via change notification
changed_entities = {"sensor.virtual_backing"}
await sensor_manager.async_update_sensors_for_entities(changed_entities)

# Test general update mechanism
await sensor_manager.async_update_sensors()

# Verify sensors were created and handle missing dependencies gracefully
sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
assert len(sensors) == expected_count

```

## Common Issues and Solutions

### 1. "No sensors found in configuration"

**Problem:** The `device_identifier` in your test doesn't match the device identifier in the YAML or sensor set.

**Solution:**

- Add `device_identifier` to YAML `global_settings`
- Ensure `device_identifier` matches in `async_create_sensor_set()` and `async_setup_synthetic_sensors()`

### 2. "DeviceRegistry object has no attribute 'devices'"

**Problem:** The device registry mock is incomplete.

**Solution:** Always patch the device registry:

```python
with patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry:
    mock_device_registry = Mock()
    mock_device_registry.devices = Mock()
    mock_device_registry.async_get_device.return_value = None
    MockDeviceRegistry.return_value = mock_device_registry
```

### 3. "Entity registry or state lookup failures"

**Problem:** Not using the common registry fixtures or trying to create custom mocks.

**Solution:**

- **ALWAYS use the common fixtures** (`mock_hass`, `mock_entity_registry`, `mock_states`)
- **NEVER create custom entity registry mocks** - the common fixtures provide complete HA environment
- **ONLY add missing entities** to the existing fixtures, don't replace them

### 4. "Storage failed to load"

**Problem:** StorageManager trying to access file system.

**Solution:** Always patch the Store class:

```python
with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore:
    mock_store = AsyncMock()
    mock_store.async_load.return_value = None
    MockStore.return_value = mock_store
    storage_manager._store = mock_store
```

### 5. Missing Entity Warnings

**Expected Behavior:** When testing missing entities, you should see warnings like:

```text
WARNING: sensor.missing_reference is NOT registered as backing entity
```

This is correct - the system should detect missing entities but remain stable.

## Test Structure Template

```python
async def test_your_feature(
    self, mock_hass, mock_entity_registry, mock_states,
    your_yaml_fixture_path, mock_config_entry, mock_async_add_entities,
    mock_device_registry  # Add the device registry fixture
):
    """Test description following the public API pattern."""

    # 1. Set up test data
    backing_data = {"sensor.backing": 1000.0}
    mock_states["sensor.external"] = create_mock_state("500.0")

    # 2. Create data provider
    data_provider = self.create_data_provider_callback(backing_data)

    # 3. Set up storage manager with proper mocking
    with patch("ha_synthetic_sensors.storage_manager.Store") as MockStore, \
         patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry:

        # Mock setup
        mock_store = AsyncMock()
        mock_store.async_load.return_value = None
        MockStore.return_value = mock_store

        # Use common device registry fixture
        MockDeviceRegistry.return_value = mock_device_registry

        # Create storage manager
        storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
        storage_manager._store = mock_store
        await storage_manager.async_load()

        # 4. Load YAML configuration
        sensor_set_id = "test_id"
        await storage_manager.async_create_sensor_set(
            sensor_set_id=sensor_set_id,
            device_identifier="test_device_123",
            name="Test Sensors"
        )

        with open(your_yaml_fixture_path, 'r') as f:
            yaml_content = f.read()

        result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
        assert result["sensors_imported"] == expected_count

        # 5. Set up synthetic sensors via public API
        sensor_to_backing_mapping = {"sensor_key": "sensor.backing"}

        def change_notifier_callback(changed_entity_ids: set[str]) -> None:
            pass  # Your change notification logic

        sensor_manager = await async_setup_synthetic_sensors(
            hass=mock_hass,
            config_entry=mock_config_entry,
            async_add_entities=mock_async_add_entities,
            storage_manager=storage_manager,
            device_identifier="test_device_123",
            data_provider_callback=data_provider,
            change_notifier=change_notifier_callback,
            sensor_to_backing_mapping=sensor_to_backing_mapping,
            # System automatically falls back to HA lookups for entities not in data provider
        )

        # 6. Test the functionality
        assert sensor_manager is not None
        assert mock_async_add_entities.called

        # Test formula evaluation
        await sensor_manager.async_update_sensors_for_entities({"sensor.backing"})
        await sensor_manager.async_update_sensors()

        # 7. Verify results
        sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
        assert len(sensors) == expected_count

        # Clean up
        await storage_manager.async_delete_sensor_set(sensor_set_id)
```

## Best Practices

1. **ALWAYS use the common fixtures** - The golden rule: use `mock_hass`, `mock_entity_registry`, `mock_states` from
   `conftest.py`
2. **NEVER create custom registry mocks** - The common fixtures provide the complete HA environment
3. **ONLY add what's missing** - If you need additional entities, add them to existing fixtures, don't replace them
4. **Patch both Store and DeviceRegistry** - These are the two main sources of test failures
5. **Match device identifiers** - YAML, sensor set, and public API must all use the same identifier
6. **Use appropriate patterns** - Choose Pattern 1, 2, or 3 based on your test needs
7. **Test both update mechanisms** - Exercise both selective and general updates
8. **Write tests without warnings** - Properly configured tests should not generate warnings
9. **Clean up after tests** - Delete sensor sets to avoid test pollution
10. **Use Mock(), not AsyncMock() for async_add_entities** - Home Assistant's AddEntitiesCallback is synchronous, not a
    coroutine

This guide provides the foundation for writing robust integration tests that properly exercise the synthetic sensors public
API while avoiding common pitfalls.
