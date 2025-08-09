# Integration Test Guide: Using Synthetic Sensors Public API

This guide explains how to properly set up integration tests that use the `ha-synthetic-sensors` public API.

## 🚀 Quick Start (Copy-Paste Template)

**TL;DR: Copy `tests/integration/TEMPLATE_integration_test.py`, modify the appropriate comented sections, and run.**

### 1. Copy the Template

```bash
cp tests/integration/TEMPLATE_integration_test.py tests/integration/test_your_feature.py
```

### 2. Edit These 7 Key Sections

1. **Class/method names** (lines 10, 14)
2. **Required entities** (lines 24-27) - entities your YAML references
3. **YAML file path** (line 39) - your test YAML file (use `tests/fixtures/integration/`)
4. **Expected sensor count** (line 32) - number of sensors in YAML
5. **Device identifier** (line 33) - must match YAML `global_settings.device_identifier`
6. **Sensor unique IDs** (line 116) - replace with your actual sensor IDs
7. **Expected values** (line 125) - calculate based on your formulas

### 3. Create Your YAML Fixture ⚠️ **IMPORTANT PATH**

**📁 Fixture Location Rules:**

- **Integration tests**: `tests/fixtures/integration/your_test.yaml`
- **Unit tests**: `tests/yaml_fixtures/unit_test_your_feature.yaml`

Put your integration test YAML in `tests/fixtures/integration/your_test.yaml` with:

```yaml
version: "1.0"

global_settings:
  device_identifier: "test_device_your_feature" # Must match step 5 above

sensors:
  your_sensor:
    name: "Your Test Sensor"
    formula: "input_entity + 50"
    variables:
      input_entity: "sensor.input_entity"
```

### 4. Run Your Test

```bash
poetry run python -m pytest tests/integration/test_your_feature.py -v
```

**The template includes bulletproof assertions that will tell you exactly what's wrong if anything fails.**

---

## 🎯 Critical Concepts: Backing Entities vs YAML Entities

**⚠️ MAJOR CONFUSION ALERT:** AI models frequently get these concepts wrong!

### 🚫 **What NEVER Goes in YAML**

```yaml
# ❌ WRONG - backing entities are NEVER defined in YAML
sensors:
  my_sensor:
    formula: "state * 1.1"
    backing_entities: # ❌ This doesn't exist!
      - "sensor.power_meter"
```

### ✅ **What DOES Go in YAML**

```yaml
# ✅ CORRECT - only synthetic sensor definitions
sensors:
  my_sensor:
    name: "My Synthetic Sensor"
    formula: "state * 1.1" # 'state' resolves to backing entity automatically
    variables:
      input_value: "sensor.some_entity" # References to OTHER entities (HA or synthetic)
```

### 🔍 **Understanding Entity Types**

#### 1. **Backing Entities** (Not in YAML)

- **Live HA entities**: `sensor.power_meter`, `switch.living_room_light`
- **Virtual entities**: Provided by integration via `data_provider_callback`
- **How they work**: The `state` token in formulas resolves to these automatically
- **Test setup**: You create these in your test with `mock_states` or `data_provider_callback`

#### 2. **YAML Entity References** (In YAML)

- **Other synthetic sensors**: `my_other_sensor` (references another sensor in the same YAML)
- **External HA entities**: `sensor.temperature` (references real HA entities)
- **Critical rule**: ALL entity references in YAML MUST resolve to real entities during evaluation

#### 3. **Sensor Types in YAML**

```yaml
sensors:
  # Type 1: Has backing entity (state token resolves to backing data)
  power_adjusted:
    formula: "state * 1.1" # 'state' = backing entity value

  # Type 2: Completely computed (no backing entity, only variables)
  total_consumption:
    formula: "power_adjusted + other_sensor" # Only references other entities
    variables:
      other_sensor: "sensor.external_power"

  # Type 3: Mixed (backing entity + other references)
  power_efficiency:
    formula: "state / target_power * 100" # state = backing, target_power = variable
    variables:
      target_power: "sensor.target_setting"
```

### 🧪 **Test Implications**

#### Required Test Setup

```python
# 1. Create backing entities (for sensors that use 'state' token)
# These are NOT in YAML - they're the data source
mock_states["sensor.power_meter"] = create_mock_state("1000.0")

# 2. Create referenced entities (for YAML variable references)
# These ARE referenced in YAML and must exist
mock_states["sensor.external_power"] = create_mock_state("500.0")
mock_states["sensor.target_setting"] = create_mock_state("800.0")

# 3. Your YAML only defines synthetic sensors
yaml_content = """
sensors:
  power_adjusted:        # Gets backing data from sensor.power_meter (via device mapping)
    formula: "state * 1.1"
  total_consumption:     # Pure computation
    formula: "power_adjusted + external_power"
    variables:
      external_power: "sensor.external_power"  # Must exist in mock_states!
"""
```

### ❌ **Common Mistakes**

1. **Putting backing entities in YAML**

   ```yaml
   # ❌ WRONG - this syntax doesn't exist
   sensors:
     my_sensor:
       backing_entity: "sensor.power" # Not a real field!
   ```

2. **Forgetting to create referenced entities**

   ```python
   # ❌ BAD - YAML references sensor.input but test doesn't create it
   yaml_content = """
   sensors:
     test_sensor:
       formula: "input_value * 2"
       variables:
         input_value: "sensor.input"  # This must exist!
   """
   # Missing: mock_states["sensor.input"] = create_mock_state("100")
   ```

3. **Confusing backing vs referenced entities**

   ```python
   # ❌ CONFUSION - thinking 'state' needs to be in mock_states
   # If sensor uses 'state' token, it gets data from backing entity (device mapping)
   # You don't put the backing entity in YAML variables!
   ```

### 💡 **Key Takeaways**

- **YAML = synthetic sensor definitions only**
- **Backing entities = data sources (not in YAML)**
- **Variable references = other entities (must exist in test)**
- **`state` token = automatic backing entity resolution**
- **All entity references in YAML must resolve to real entities**

---

## 🏗️ Unit Tests vs Integration Tests

**Do you need a unit test template too?** Here's when to use each:

### 🔧 **Unit Tests** - Test Individual Components

- **Use when**: Testing specific handlers, parsers, or isolated logic
- **Fixtures**: `tests/yaml_fixtures/unit_test_your_feature.yaml`
- **Pattern**: Mock everything except the component being tested
- **Example**: Testing formula evaluation, YAML parsing, dependency resolution

### 🌐 **Integration Tests** - Test Complete Workflows

- **Use when**: Testing end-to-end flows through the public API
- **Fixtures**: `tests/fixtures/integration/your_feature.yaml`
- **Pattern**: Use common fixtures, test real workflows
- **Example**: YAML → synthetic sensors → Home Assistant entities

**For most new features, start with integration tests using this template.**

---

## 🛡️ Bulletproof Assertion Principles

**NEVER write useless assertions like these:**

```python
# ❌ BAD - tells you nothing when it fails
assert sensor is not None
assert mock_async_add_entities.called
assert len(entities) > 0

# ❌ WORST - assertions wrapped in 'if' blocks (NEVER DO THIS!)
if sensor is not None:
    assert sensor.native_value == 150.0  # Silently passes if sensor is None!
```

**ALWAYS write bulletproof assertions like these:**

```python
# ✅ GOOD - tells you exactly what went wrong
assert sensor is not None, (
    f"Sensor 'temperature_sensor' not found. Available: {list(entity_lookup.keys())}"
)

assert mock_async_add_entities.call_args_list, (
    "async_add_entities was never called - no entities were added to HA"
)

assert len(entities) == 3, (
    f"Wrong entity count: expected 3, got {len(entities)}. "
    f"Entities: {[getattr(e, 'unique_id', 'no_id') for e in entities]}"
)

# ✅ EXCELLENT - test exact values, not just existence
expected_value = 150.0  # input1 (100) + input2 (50)
actual_value = float(sensor.native_value)
assert abs(actual_value - expected_value) < 0.001, (
    f"Temperature sensor calculation wrong: expected {expected_value}, got {actual_value}"
)

# ✅ BEST PRACTICE - combined existence and value check in one assertion
assert sensor is not None and float(sensor.native_value) == 150.0, (
    f"Sensor test failed: sensor={sensor}, "
    f"value={getattr(sensor, 'native_value', 'N/A')}, "
    f"available={list(entity_lookup.keys())}"
)
```

**Key Rules:**

1. **Always include what you expected vs what you got**
2. **Always show available options when something is missing**
3. **Test exact values, not just "not None"**
4. **Explain the calculation in comments**
5. **Never wrap assertions in "if exists" checks**

---

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

### 2. Standard Common Fixtures (Already Available)

The following fixtures are already available in `conftest.py` - just include them in your test method signature:

```python
async def test_your_feature(
    self,
    mock_hass,                    # ✅ Ready to use - HA instance with proper config
    mock_entity_registry,         # ✅ Ready to use - Entity registry with test entities
    mock_states,                  # ✅ Ready to use - State manager for entity states
    mock_device_registry,         # ✅ Ready to use - Device registry (NEW!)
    mock_config_entry,            # ✅ Ready to use - Config entry for integration (NEW!)
    mock_async_add_entities,      # ✅ Ready to use - Entity addition callback (NEW!)
):
```

**That's it!** No more boilerplate fixture creation in every test class.

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

**MOST IMPORTANT:** When testing collection functions like `count('device_class:power')` or `sum('device_class:energy')`, you
MUST patch the collection resolver's entity registry access. The `CollectionResolver` gets its entity registry through
`er.async_get(hass)` calls, which are NOT automatically mocked.

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

**Root Cause:** Mock entity objects not properly initialized with Home Assistant instance

**Solution:** Set the hass attribute on entities after creation:

```python
# After getting entities from mock_async_add_entities
all_entities = []
for call in mock_async_add_entities.call_args_list:
    entities_list = call.args[0] if call.args else []
    all_entities.extend(entities_list)

# Set hass attribute on all entities
for entity in all_entities:
    entity.hass = mock_hass
```

#### **Symptom: "Frame helper not set up" warnings**

**Example:**
`WARNING Entity sensor.my_sensor (<class 'ha_synthetic_sensors.sensor_manager.DynamicSensor'>) does not have a platform`

**Root Cause:** Entities are not properly associated with a platform in the test environment

**Solution:** Set both hass and platform attributes on entities after creation:

```python
# Create mock platform
mock_platform = Mock()
mock_platform.platform_name = "sensor"
mock_platform.logger = Mock()

# Set both hass and platform attributes
for entity in all_entities:
    entity.hass = mock_hass
    entity.platform = mock_platform
```

### Debugging Collection Function Issues

To debug collection function problems:

**Check what entities are in the registry:**

```python
print(f"Entities in registry: {list(mock_entity_registry._entities.keys())}")
```

**Verify entity removal worked:**

```python
power_entities = [
    entity_id for entity_id, entity_data in mock_entity_registry._entities.items()
    if hasattr(entity_data, "device_class") and entity_data.device_class == "power"
]
print(f"Power entities remaining: {power_entities}")
```

**Test collection resolver directly:**

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
11. **Properly initialize entities** - Set both `hass` and `platform` attributes on entities to prevent warnings:

    ```python
    # Create mock platform
    mock_platform = Mock()
    mock_platform.platform_name = "sensor"
    mock_platform.logger = Mock()

    # Set attributes on all entities
    for entity in all_entities:
        entity.hass = mock_hass
        entity.platform = mock_platform
    ```

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

---

## 🚨 STOP! Common AI/Developer Mistakes

**Before you write your test, avoid these repeated mistakes:**

### ❌ Mistake 1: "Just checking it doesn't crash"

```python
# BAD - tells you nothing useful
assert sensor_manager is not None
assert len(entities) > 0
```

**✅ Fix:** Test exact expected values and provide detailed error messages.

### ❌ Mistake 2: "Wrapping assertions in 'if' blocks" ⚠️ **BIGGEST OFFENSE**

```python
# BAD - makes assertions completely useless!
if sensor is not None:
    assert sensor.native_value == 150.0  # Never fails if sensor is None!

if entity.native_value is not None:
    assert entity.native_value == 200.0  # Never fails if value is None!

if len(entities) > 0:
    assert entities[0].unique_id == "test_sensor"  # Never fails if entities is empty!
```

**⚠️ Why This Is So Bad:**

- Test **silently passes** when sensor/entity/value is None
- You think your test is working but it's testing **nothing**
- Bugs go undetected because assertions never run

**✅ Fix:** Assert the sensor exists AND has the right value in one bulletproof assertion:

```python
# GOOD - fails with clear message if anything is wrong
assert sensor is not None, f"Sensor not found. Available: {list(entity_lookup.keys())}"
assert sensor.native_value == 150.0, f"Wrong value: expected 150.0, got {sensor.native_value}"

# EVEN BETTER - combine into one bulletproof assertion
assert sensor is not None and sensor.native_value == 150.0, (
    f"Sensor test failed: sensor={sensor}, value={getattr(sensor, 'native_value', 'N/A')}, "
    f"available_sensors={list(entity_lookup.keys())}"
)
```

### ❌ Mistake 3: "Wrong API parameters"

```python
# BAD - sensor_set_id doesn't exist
await async_setup_synthetic_sensors(sensor_set_id="test")
```

**✅ Fix:** Use `device_identifier` parameter as shown in the template.

### ❌ Mistake 4: "Missing required entities"

```python
# BAD - YAML references sensor.input but test doesn't create it
required_entities = {"sensor.wrong_name": {"state": "100"}}
```

**✅ Fix:** Create ALL entities that your YAML variables reference.

### ❌ Mistake 5: "Device identifier mismatch"

```python
# BAD - YAML has device_identifier: "device_a" but test uses "device_b"
device_identifier = "device_b"  # Doesn't match YAML
```

**✅ Fix:** Ensure exact match between YAML `global_settings.device_identifier` and test.

### ❌ Mistake 6: "Putting backing entities in YAML" ⚠️ **FUNDAMENTAL CONFUSION**

```yaml
# ❌ WRONG - backing entities are NEVER in YAML!
sensors:
  my_sensor:
    formula: "state * 1.1"
    backing_entity: "sensor.power_meter" # This field doesn't exist!
    backing_entities: # This also doesn't exist!
      - "sensor.power_meter"
```

**✅ Fix:** Backing entities are handled via device mapping or data_provider_callback, never in YAML.

### ❌ Mistake 7: "Missing entities that YAML references"

```python
# ❌ BAD - YAML references entities that don't exist in test
yaml_content = """
sensors:
  test_sensor:
    formula: "input_value + other_value"
    variables:
      input_value: "sensor.missing_entity"    # Must exist!
      other_value: "sensor.another_missing"   # Must exist!
"""
# Missing: mock_states["sensor.missing_entity"] = create_mock_state("100")
# Missing: mock_states["sensor.another_missing"] = create_mock_state("200")
```

**✅ Fix:** Create ALL entities that your YAML variables reference in your test setup.

### ✅ The Solution: Use the Template

Copy `tests/integration/TEMPLATE_integration_test.py` and follow the comments. The template prevents all these mistakes
and provides bulletproof assertions that tell you exactly what went wrong.

---

## 📚 Related Documentation

### YAML Syntax and API References

- **[📖 Cookbook](../../docs/cookbook.md)** - Real-world YAML examples and patterns for all features
- **[🔧 Integration Guide](../../docs/Synthetic_Sensors_Integration_Guide.md)** - Complete public API documentation and usage
  patterns
- **[🏗️ Creating New Handlers Guide](../../docs/Dev/creating_new_handlers_guide.md)** - For developing custom function
  handlers

### Advanced References

- [Cache Behavior Guide](../../docs/Cache_Behavior_and_Data_Lifecycle.md) - Understanding caching in tests
- [Comparison Handler Design](../../docs/Dev/comparison_handler_design.md) - For collection pattern testing
- [Reference Value Architecture](../../docs/Dev/reference_value_architecture.md) - Advanced evaluation concepts

### Testing Resources

- [Integration Test Template](../integration/TEMPLATE_integration_test.py) - Copy-paste starting point
- [Common Test Fixtures](../conftest.py) - Available test utilities
- [Example Integration Tests](../integration/) - Working test examples

**📌 Pro Tip:** When your YAML syntax doesn't work, check the **Cookbook** first for working examples, then refer to the
**Integration Guide** for API details.
