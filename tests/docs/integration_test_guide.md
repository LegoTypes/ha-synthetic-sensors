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

## Entity Registry Operations for Test Isolation

When writing integration tests that need to verify specific entity counts or behaviors, you may need to modify the entity
registry to create controlled test environments. The common registry fixtures provide methods for safely adding and removing
entities.

### 🏆 GOLDEN RULE: Use Registry Operations for Isolation

**CRITICAL:** Always use the provided registry methods for entity manipulation. Never directly modify the internal
`_entities` dictionary or mock objects.

**✅ DO:**

```python
# Use the provided methods
mock_entity_registry.register_entity("sensor.test", "test", "sensor", device_class="power")
mock_entity_registry.remove_entity("sensor.test")
```

**❌ DON'T:**

```python
# Never access internal structures directly
mock_entity_registry._entities["sensor.test"] = mock_entity  # This breaks encapsulation
del mock_entity_registry.entities["sensor.test"]  # This fails - entities is a Mock object
```

### Adding Entities for Test Setup

Use `register_entity()` to add entities that your test needs:

```python
# Add a power sensor for testing
mock_entity_registry.register_entity(
    entity_id="sensor.test_power",
    unique_id="test_power",
    domain="sensor",
    device_class="power"
)

# Add a temperature sensor
mock_entity_registry.register_entity(
    entity_id="sensor.test_temp",
    unique_id="test_temp",
    domain="sensor",
    device_class="temperature"
)
```

**Key Points:**

- `entity_id`: The full entity ID (e.g., "sensor.test_power")
- `unique_id`: The unique identifier (e.g., "test_power")
- `domain`: The entity domain (e.g., "sensor", "binary_sensor")
- Additional attributes: Pass as keyword arguments (e.g., `device_class="power"`)

### Removing Entities for Test Isolation

Use `remove_entity()` to remove entities for controlled test environments:

```python
# Remove all power entities to test count('device_class:power') returning 0
original_entities = dict(mock_entity_registry._entities)
original_states = dict(mock_states)

# Identify entities to remove
entities_to_remove = [
    entity_id for entity_id, entity_data in original_entities.items()
    if (hasattr(entity_data, "device_class") and entity_data.device_class == "power")
    or (isinstance(entity_data, dict) and entity_data.get("device_class") == "power")
    or (hasattr(entity_data, "attributes") and entity_data.attributes.get("device_class") == "power")
]

# Remove entities safely
for entity_id in entities_to_remove:
    mock_entity_registry.remove_entity(entity_id)
    if entity_id in mock_states:
        del mock_states[entity_id]

try:
    # Your test code here
    pass
finally:
    # Restore original state to avoid affecting other tests
    mock_entity_registry._entities.clear()
    mock_entity_registry._entities.update(original_entities)
    mock_states.clear()
    mock_states.update(original_states)
```

### Entity Detection Strategies

When identifying entities to remove, use multiple detection strategies to handle different entity storage patterns:

```python
def is_power_entity(entity_data):
    """Check if entity is a power sensor using multiple detection strategies."""
    return (
        # Direct attribute access
        (hasattr(entity_data, "device_class") and entity_data.device_class == "power")
        or
        # Dictionary key access
        (isinstance(entity_data, dict) and entity_data.get("device_class") == "power")
        or
        # Nested attributes access
        (hasattr(entity_data, "attributes") and entity_data.attributes.get("device_class") == "power")
    )

# Use the detection function
entities_to_remove = [
    entity_id for entity_id, entity_data in original_entities.items()
    if is_power_entity(entity_data)
]
```

### Selective Entity Removal

For tests that need specific entities while removing others:

```python
# Keep sensor.panel_power for testing, remove all other power entities
entities_to_remove = [
    entity_id for entity_id, entity_data in original_entities.items()
    if entity_id != "sensor.panel_power" and is_power_entity(entity_data)
]
```

### 🚨 CRITICAL: Collection Resolver Patching

**MOST IMPORTANT:** When testing collection functions like `count('device_class:power')` or `sum('device_class:energy')`, you MUST patch the collection resolver's entity registry access. The `CollectionResolver` gets its entity registry through `er.async_get(hass)` calls, which are NOT automatically mocked.

**❌ WITHOUT PATCHING (WILL FAIL):**
```python
# This will NOT work - CollectionResolver uses different registry instance
with (
    patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
    patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
):
    # Your test code - count() will return wrong values!
```

**✅ WITH PROPER PATCHING (REQUIRED):**
```python
# This WILL work - CollectionResolver uses the same mock registry
with (
    patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
    patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
    patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
    patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
):
    # Your test code - count() will return correct values!
```

**Why This Matters:**
- The `CollectionResolver` calls `er.async_get(hass)` internally
- This returns a different entity registry instance than `mock_hass.entity_registry`
- Without patching, collection functions use the real registry, not your modified mock
- This causes tests to fail with unexpected values (e.g., `42.0` instead of `0`)

**When to Apply This Patching:**
- ✅ Any test using collection functions: `count()`, `sum()`, `avg()`, etc.
- ✅ Any test using device_class patterns: `device_class:power`, `device_class:energy`
- ✅ Any test using area patterns: `area:living_room`
- ✅ Any test using label patterns: `label:critical`
- ✅ Any test using regex patterns: `regex:sensor.*power`

### Complete Test Isolation Pattern

Here's the complete pattern for tests requiring entity isolation:

```python
async def test_count_function_with_isolation(
    self, mock_hass, mock_entity_registry, mock_states,
    mock_config_entry, mock_async_add_entities, mock_device_registry
):
    """Test that count('device_class:power') returns 0 when no power entities exist."""

    # 1. Save original state for restoration
    original_entities = dict(mock_entity_registry._entities)
    original_states = dict(mock_states)

    # 2. Remove entities for isolation
    entities_to_remove = [
        entity_id for entity_id, entity_data in original_entities.items()
        if (hasattr(entity_data, "device_class") and entity_data.device_class == "power")
        or (isinstance(entity_data, dict) and entity_data.get("device_class") == "power")
        or (hasattr(entity_data, "attributes") and entity_data.attributes.get("device_class") == "power")
    ]

    for entity_id in entities_to_remove:
        mock_entity_registry.remove_entity(entity_id)
        if entity_id in mock_states:
            del mock_states[entity_id]

    try:
        # 3. Your test code here with PROPER PATCHING
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
            patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
            patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
        ):
            # Set up storage manager, load YAML, create sensors, etc.

        # 4. Verify isolation worked
        # count('device_class:power') should return 0
        # sum('device_class:power') should return 0

    finally:
        # 5. Restore original state
        mock_entity_registry._entities.clear()
        mock_entity_registry._entities.update(original_entities)
        mock_states.clear()
        mock_states.update(original_states)
```

### Registry Operation Methods

The `DynamicMockEntityRegistry` provides these methods:

#### `register_entity(entity_id, unique_id, domain, **attrs)`

- **Purpose**: Add an entity to the registry for testing
- **Parameters**:
  - `entity_id`: Full entity ID (e.g., "sensor.test_power")
  - `unique_id`: Unique identifier (e.g., "test_power")
  - `domain`: Entity domain (e.g., "sensor")
  - `**attrs`: Additional attributes (e.g., `device_class="power"`)
- **Returns**: None
- **Logs**: "📝 Manual registry: Added entity {entity_id}"

#### `remove_entity(entity_id)`

- **Purpose**: Remove an entity from the registry for test isolation
- **Parameters**:
  - `entity_id`: Full entity ID to remove
- **Returns**: `True` if entity was removed, `False` if not found
- **Logs**: "🗑️ Manual registry: Removed entity {entity_id}"

### Common Use Cases

#### 1. Testing Collection Functions

```python
# Test count('device_class:power') returning 0
entities_to_remove = [entity_id for entity_id, entity_data in original_entities.items()
                     if is_power_entity(entity_data)]
for entity_id in entities_to_remove:
    mock_entity_registry.remove_entity(entity_id)
```

#### 2. Testing Missing Entity Handling

```python
# Ensure specific entities don't exist
if "sensor.missing_entity" in mock_states:
    del mock_states["sensor.missing_entity"]
mock_entity_registry.remove_entity("sensor.missing_entity")
```

#### 3. Testing Specific Entity Counts

```python
# Remove all but 2 power entities to test count('device_class:power') returning 2
power_entities = [entity_id for entity_id, entity_data in original_entities.items()
                 if is_power_entity(entity_data)]
entities_to_keep = power_entities[:2]
entities_to_remove = power_entities[2:]

for entity_id in entities_to_remove:
    mock_entity_registry.remove_entity(entity_id)
```

### Best Practices for Registry Operations

1. **Always save original state** - Use `dict(mock_entity_registry._entities)` to create a copy
2. **Use try/finally blocks** - Ensure restoration happens even if test fails
3. **Use the provided methods** - Never access `_entities` directly
4. **Remove from both registry and states** - Keep registry and states in sync
5. **Use multiple detection strategies** - Handle different entity storage patterns
6. **Log your operations** - The methods provide helpful logging
7. **Test isolation thoroughly** - Verify your isolation worked as expected
8. **Restore completely** - Clear and update both registry and states

### 🚨 Troubleshooting Collection Function Issues

If your tests are failing with unexpected collection function results, check these common issues:

#### **Symptom: Collection functions return wrong values**

**Example:** `count('device_class:power')` returns `42.0` instead of expected `0`

**Root Cause:** Collection resolver not using the same mock registry as your test

**Solution:** Add the required patches:
```python
patch("ha_synthetic_sensors.collection_resolver.er.async_get", return_value=mock_entity_registry),
patch("ha_synthetic_sensors.constants_entities.er.async_get", return_value=mock_entity_registry),
```

#### **Symptom: Tests pass individually but fail in sequence**

**Example:** Test A passes, Test B passes, but running both together fails

**Root Cause:** Entity registry state not properly restored between tests

**Solution:** Always use try/finally blocks for state restoration:
```python
try:
    # Your test code
    pass
finally:
    # Restore original state
    mock_entity_registry._entities.clear()
    mock_entity_registry._entities.update(original_entities)
    mock_states.clear()
    mock_states.update(original_states)
```

#### **Symptom: Entity removal not working**

**Example:** `remove_entity()` called but `count()` still returns old values

**Root Cause:** Using direct dictionary access instead of provided methods

**Solution:** Use the registry's `remove_entity()` method:
```python
# ✅ CORRECT
mock_entity_registry.remove_entity(entity_id)

# ❌ INCORRECT  
del mock_entity_registry._entities[entity_id]
```

#### **Symptom: "Attribute hass is None" errors**

**Example:** `Attribute hass is None for <entity unknown.unknown=unknown>`

**Root Cause:** Mock entity objects not properly initialized

**Solution:** Ensure mock entities have proper hass attribute or use proper mocking patterns

### Debugging Collection Function Issues

To debug collection function problems:

1. **Check what entities are in the registry:**
```python
print(f"Entities in registry: {list(mock_entity_registry._entities.keys())}")
```

2. **Verify entity removal worked:**
```python
power_entities = [
    entity_id for entity_id, entity_data in mock_entity_registry._entities.items()
    if hasattr(entity_data, "device_class") and entity_data.device_class == "power"
]
print(f"Power entities remaining: {power_entities}")
```

3. **Test collection resolver directly:**
```python
from ha_synthetic_sensors.collection_resolver import CollectionResolver
resolver = CollectionResolver(mock_hass)
entities = resolver.resolve_collection(DynamicQuery("device_class", "power", "count"))
print(f"Collection resolver found: {entities}")
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

### 📚 What Was Missing from the Original Guide

The original integration test guide was missing several critical insights that led to test failures:

#### **1. Collection Resolver Architecture Understanding**
- **Missing:** Understanding that `CollectionResolver` uses `er.async_get(hass)` internally
- **Impact:** Tests were modifying one registry instance while collection functions used another
- **Solution:** Added explicit patching for collection resolver registry access

#### **2. Test Isolation Patterns**
- **Missing:** Proper patterns for entity registry isolation
- **Impact:** Tests interfered with each other, causing flaky results
- **Solution:** Added `remove_entity()` method and proper state restoration patterns

#### **3. Debugging Collection Function Issues**
- **Missing:** Tools and techniques for debugging collection function problems
- **Impact:** Difficult to diagnose why `count()` returned `42.0` instead of `0`
- **Solution:** Added debugging techniques and troubleshooting guide

#### **4. Registry Operation Best Practices**
- **Missing:** Clear guidance on when and how to modify entity registries
- **Impact:** Tests used inconsistent approaches to entity manipulation
- **Solution:** Added comprehensive registry operation documentation

#### **5. Symptom-Based Troubleshooting**
- **Missing:** Clear mapping between test failures and their root causes
- **Impact:** Developers struggled to understand why tests failed
- **Solution:** Added symptom-based troubleshooting section

### 🎯 Key Lessons Learned

1. **Collection functions require special attention** - They access registries differently than other components
2. **Test isolation is multi-layered** - Must isolate both registry and collection resolver
3. **Proper patching is essential** - Not all components use the same mock instances
4. **State restoration is critical** - Tests must clean up after themselves
5. **Debugging tools are invaluable** - Need ways to inspect registry state during tests

These insights ensure that future tests avoid the same pitfalls and can properly test collection function behavior.
