# Creating New Formula Handlers - Developer Guide

This guide documents the complete process for creating new formula handlers in the ha-synthetic-sensors project, based on
lessons learned from implementing the `metadata()` function handler.

## Overview

Formula handlers are responsible for processing specific types of expressions or functions within synthetic sensor formulas. The
system supports different handler types:

- **String Handler**: String manipulation functions (`split()`, `replace()`, etc.)
- **Numeric Handler**: Mathematical expressions and functions
- **Date Handler**: Datetime functions (`now()`, `today()`, etc.)
- **Boolean Handler**: Boolean operations and logic
- **Metadata Handler**: Home Assistant entity metadata access (`metadata()`)

## Step-by-Step Implementation Process

### 1. Define Function Constants

First, add your new function(s) to the shared constants to make them recognizable throughout the system.

**File**: `src/ha_synthetic_sensors/shared_constants.py`

```python
# Add your function set
METADATA_FUNCTIONS: frozenset[str] = frozenset({"metadata"})

# Or for multiple functions
MY_NEW_FUNCTIONS: frozenset[str] = frozenset({"my_func", "another_func"})
```

### 2. Update Validation Systems

The validation systems need to recognize your functions as valid to prevent "undefined variable" errors.

#### Dependency Parser

**File**: `src/ha_synthetic_sensors/dependency_parser.py`

```python
from .shared_constants import DATETIME_FUNCTIONS, DURATION_FUNCTIONS, METADATA_FUNCTIONS, STRING_FUNCTIONS, MY_NEW_FUNCTIONS

def _build_variable_pattern(self, config_variables: set[str]) -> re.Pattern[str]:
    # ... existing code ...
    excluded_keywords.extend(METADATA_FUNCTIONS)  # Add your functions
    excluded_keywords.extend(MY_NEW_FUNCTIONS)    # Add your functions
```

#### Schema Validator

**File**: `src/ha_synthetic_sensors/schema_validator.py`

```python
from .shared_constants import DATETIME_FUNCTIONS, DURATION_FUNCTIONS, METADATA_FUNCTIONS, STRING_FUNCTIONS, MY_NEW_FUNCTIONS

def _validate_formula_tokens(self, formula: str, available_vars: set[str], sensor_id: str) -> list[str]:
    # ... existing code ...
    metadata_functions = METADATA_FUNCTIONS  # Import your functions
    my_new_functions = MY_NEW_FUNCTIONS       # Import your functions

    # In the validation loop:
    is_valid = (
        # ... existing conditions ...
        or token in metadata_functions    # Add your check
        or token in my_new_functions      # Add your check
    )
```

#### Config Utils (if needed)

**File**: `src/ha_synthetic_sensors/utils_config.py`

```python
from .shared_constants import DATETIME_FUNCTIONS, DURATION_FUNCTIONS, METADATA_FUNCTIONS, STRING_FUNCTIONS, MY_NEW_FUNCTIONS

def validate_computed_variable_references(
    formula: str,
    available_vars: set[str],
    sensor_id: str,
    global_variables: dict[str, Any] | None = None,
) -> list[str]:
    # ... existing code ...
    always_available.update(METADATA_FUNCTIONS)  # Add your functions
    always_available.update(MY_NEW_FUNCTIONS)    # Add your functions
```

### 3. Create the Handler Class

Create your handler following the established patterns.

**File**: `src/ha_synthetic_sensors/evaluator_handlers/my_new_handler.py`

```python
"""Handler for my new functions."""

from __future__ import annotations

from collections.abc import Callable
import logging
import re
from typing import Any, TYPE_CHECKING

from homeassistant.core import HomeAssistant  # If you need HA access

from ..type_definitions import ContextValue
from .base_handler import FormulaHandler

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class MyNewHandler(FormulaHandler):
    """Handler for my_func() function calls."""

    # Define any constants your handler needs
    VALID_OPTIONS = {"option1", "option2", "option3"}

    def __init__(
        self,
        expression_evaluator: Callable[[str, dict[str, ContextValue] | None], ContextValue] | None = None,
        hass: HomeAssistant | None = None,  # Only if you need HA access
    ) -> None:
        """Initialize the handler.

        Args:
            expression_evaluator: Callback for delegating complex expression evaluation
            hass: Home Assistant instance (only if needed)
        """
        super().__init__(expression_evaluator)
        self._hass = hass  # Only if you need HA access

    def can_handle(self, formula: str) -> bool:
        """Check if this handler can process the given formula.

        Args:
            formula: The formula to check

        Returns:
            True if the formula contains my_func() function calls
        """
        # Simple detection - look for your function name
        return "my_func(" in formula

    def evaluate(self, formula: str, context: dict[str, ContextValue] | None = None) -> ContextValue:
        """Evaluate a formula containing my_func() function calls.

        This handler processes function calls within formulas by replacing them
        with their evaluated results, then returns the processed formula for further
        evaluation by other handlers.

        Args:
            formula: The formula containing function calls
            context: Variable context for evaluation

        Returns:
            The formula with function calls replaced by their results

        Raises:
            ValueError: If function parameters are invalid
        """
        try:
            _LOGGER.debug("Evaluating my_func formula: %s", formula)

            processed_formula = formula

            # Find all function calls and replace them with their results
            def replace_function_call(match: re.Match[str]) -> str:
                full_call = match.group(0)  # Full my_func(...) call
                params_str = match.group(1)  # Content inside parentheses

                _LOGGER.debug("Processing function call: %s", full_call)

                # Parse parameters (adjust based on your function's signature)
                params = [p.strip() for p in params_str.split(',')]
                if len(params) != 2:  # Adjust expected parameter count
                    raise ValueError(f"my_func() requires exactly 2 parameters, got {len(params)}")

                param1 = params[0].strip()
                param2 = params[1].strip().strip('\'"')  # Remove quotes if string parameter

                # Resolve variables from context if needed
                if context and param1 in context:
                    resolved_param1 = str(context[param1])
                else:
                    resolved_param1 = param1

                # Implement your function logic
                result = self._execute_my_func(resolved_param1, param2)

                # Return as quoted string if it's a string value, otherwise as-is
                if isinstance(result, str):
                    return f'"{result}"'
                else:
                    return str(result)

            # Use regex to find and replace function calls
            function_pattern = re.compile(r'my_func\s*\(\s*([^)]+)\s*\)', re.IGNORECASE)
            processed_formula = function_pattern.sub(replace_function_call, processed_formula)

            _LOGGER.debug("Processed formula: %s", processed_formula)
            return processed_formula

        except Exception as e:
            _LOGGER.error("Error evaluating my_func formula '%s': %s", formula, e)
            raise

    def _execute_my_func(self, param1: str, param2: str) -> Any:
        """Execute the actual function logic.

        Args:
            param1: First parameter
            param2: Second parameter

        Returns:
            The function result

        Raises:
            ValueError: If parameters are invalid
        """
        # Implement your function logic here
        if param2 not in self.VALID_OPTIONS:
            raise ValueError(f"Invalid option: {param2}. Valid options: {sorted(self.VALID_OPTIONS)}")

        # Your function implementation
        return f"processed_{param1}_{param2}"

    def get_handler_name(self) -> str:
        """Return the name of this handler."""
        return "my_new_handler"

    def get_supported_functions(self) -> set[str]:
        """Return the set of supported function names."""
        return {"my_func"}

    def get_function_info(self) -> list[dict[str, Any]]:
        """Return information about supported functions."""
        return [
            {
                "name": "my_func",
                "description": "Description of what my_func does.",
                "parameters": [
                    {"name": "param1", "type": "string", "description": "Description of param1."},
                    {"name": "param2", "type": "string", "description": "Description of param2."},
                ],
                "returns": {"type": "string", "description": "Description of return value."},
                "valid_options": sorted(self.VALID_OPTIONS),
            }
        ]
```

### 4. Register the Handler

Register your handler in the handler factory with appropriate priority.

**File**: `src/ha_synthetic_sensors/evaluator_handlers/handler_factory.py`

```python
def _register_default_handler_types(self) -> None:
    """Register default handler types for lazy instantiation."""
    # pylint: disable=import-outside-toplevel
    from .boolean_handler import BooleanHandler
    from .date_handler import DateHandler
    from .metadata_handler import MetadataHandler
    from .my_new_handler import MyNewHandler  # Import your handler
    from .numeric_handler import NumericHandler
    from .string_handler import StringHandler

    # Register handlers in priority order (earlier = higher priority)
    self.register_handler_type("metadata", MetadataHandler)
    self.register_handler_type("my_new_handler", MyNewHandler)  # Add your handler
    self.register_handler_type("string", StringHandler)
    self.register_handler_type("numeric", NumericHandler)
    self.register_handler_type("boolean", BooleanHandler)
    self.register_handler_type("date", DateHandler)

def _create_handler_instance(self, name: str) -> FormulaHandler | None:
    """Create a handler instance."""
    if name not in self._handler_types:
        return None
    handler_type = self._handler_types[name]

    # Check if your handler needs special parameters
    if name == "metadata":
        return handler_type(expression_evaluator=self._expression_evaluator, hass=self._hass)
    elif name == "my_new_handler":
        # If your handler needs hass:
        return handler_type(expression_evaluator=self._expression_evaluator, hass=self._hass)
        # If it doesn't need hass:
        # return handler_type(expression_evaluator=self._expression_evaluator)

    # All other handlers accept expression_evaluator as a standard parameter
    return handler_type(expression_evaluator=self._expression_evaluator)
```

### 5. Update Handler Module Exports

**File**: `src/ha_synthetic_sensors/evaluator_handlers/__init__.py`

```python
from .handler_factory import HandlerFactory
from .my_new_handler import MyNewHandler  # Add your handler

__all__ = ["HandlerFactory", "MyNewHandler"]  # Add to exports
```

### 6. Create Unit Tests

Create comprehensive unit tests for your handler.

**File**: `tests/unit/evaluator_handlers/test_my_new_handler.py`

```python
"""Unit tests for MyNewHandler."""

from unittest.mock import Mock
import pytest

from ha_synthetic_sensors.evaluator_handlers.my_new_handler import MyNewHandler


class TestMyNewHandler:
    """Test the MyNewHandler in isolation."""

    def test_can_handle_my_func_function(self):
        """Test that can_handle correctly identifies my_func() calls."""
        handler = MyNewHandler()

        # Should handle my_func function calls
        assert handler.can_handle("my_func(param1, 'option1')")
        assert handler.can_handle("some_value + my_func(var, 'option2')")

        # Should not handle other expressions
        assert not handler.can_handle("now()")
        assert not handler.can_handle("split(some_string, ',')")

    def test_my_func_evaluation_basic(self):
        """Test basic my_func() evaluation."""
        handler = MyNewHandler()

        # Test evaluation
        formula = "my_func(test_input, 'option1')"
        result = handler.evaluate(formula)

        # Should return processed result
        expected = '"processed_test_input_option1"'
        assert result == expected

    def test_my_func_with_variable_resolution(self):
        """Test my_func() with variable context."""
        handler = MyNewHandler()

        # Test evaluation with context variable
        formula = "my_func(my_var, 'option2')"
        context = {"my_var": "variable_value"}

        result = handler.evaluate(formula, context)

        # Should resolve variable and process
        expected = '"processed_variable_value_option2"'
        assert result == expected

    def test_my_func_invalid_option(self):
        """Test my_func() with invalid option."""
        handler = MyNewHandler()

        # Test with invalid option
        formula = "my_func(test, 'invalid_option')"

        with pytest.raises(ValueError, match="Invalid option: invalid_option"):
            handler.evaluate(formula)

    def test_my_func_wrong_parameter_count(self):
        """Test my_func() with wrong number of parameters."""
        handler = MyNewHandler()

        # Too few parameters
        formula = "my_func(test)"
        with pytest.raises(ValueError, match="my_func\\(\\) requires exactly 2 parameters, got 1"):
            handler.evaluate(formula)

        # Too many parameters
        formula = "my_func(test, 'option1', 'extra')"
        with pytest.raises(ValueError, match="my_func\\(\\) requires exactly 2 parameters, got 3"):
            handler.evaluate(formula)

    def test_multiple_my_func_calls(self):
        """Test formula with multiple my_func() calls."""
        handler = MyNewHandler()

        # Test formula with multiple function calls
        formula = "my_func(input1, 'option1') + my_func(input2, 'option2')"
        result = handler.evaluate(formula)

        # Should replace both calls
        expected = '"processed_input1_option1" + "processed_input2_option2"'
        assert result == expected

    def test_get_handler_info(self):
        """Test handler information methods."""
        handler = MyNewHandler()

        assert handler.get_handler_name() == "my_new_handler"
        assert handler.get_supported_functions() == {"my_func"}

        function_info = handler.get_function_info()
        assert len(function_info) == 1
        assert function_info[0]["name"] == "my_func"
        assert "option1" in function_info[0]["valid_options"]
```

### 7. Create Integration Tests

Create integration tests with YAML fixtures.

**File**: `tests/fixtures/integration/my_new_function_integration.yaml`

```yaml
version: "1.0"

global_settings:
  device_identifier: "test_device_my_new_function"
  variables:
    # Global variable for testing
    global_input: "global_test_value"
  metadata:
    attribution: "My New Function Integration Test"
    entity_registry_enabled_default: true

sensors:
  # Test 1: Basic function call
  my_func_basic_test:
    name: "My Func Basic Test"
    formula: "my_func(test_input, 'option1')"
    variables:
      test_input: "basic_value"
    metadata:
      unit_of_measurement: ""

  # Test 2: Function with variable resolution
  my_func_variable_test:
    name: "My Func Variable Test"
    formula: "my_func(my_var, 'option2')"
    variables:
      my_var: "variable_value"
    metadata:
      unit_of_measurement: ""

  # Test 3: Function with global variable
  my_func_global_test:
    name: "My Func Global Test"
    formula: "my_func(global_input, 'option1')"
    metadata:
      unit_of_measurement: ""
```

**File**: `tests/integration/test_my_new_function_integration.py`

```python
"""Integration tests for my_func() function."""

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ha_synthetic_sensors import async_setup_synthetic_sensors
from ha_synthetic_sensors.storage_manager import StorageManager


class TestMyNewFunctionIntegration:
    """Test my_func() function integration with synthetic sensors."""

    @pytest.fixture
    def my_new_function_yaml_path(self):
        """Path to my_func integration test YAML fixture."""
        return Path(__file__).parent.parent / "fixtures" / "integration" / "my_new_function_integration.yaml"

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device My New Function"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_my_new_function")}
        return mock_device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities callback."""
        return Mock()

    def create_mock_state(self, state_value: str, attributes: dict = None):
        """Create a mock state object."""
        return type("MockState", (), {"state": state_value, "attributes": attributes or {}})()

    async def test_my_new_function_basic_integration(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        my_new_function_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test basic my_func() function integration with synthetic sensors."""

        # Set up test data - external entities for testing
        mock_states["sensor.test_input_entity"] = self.create_mock_state("test_value")

        # Set up storage manager with proper mocking (following the guide)
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
            storage_manager = StorageManager(mock_hass, "test_my_new_function_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load YAML configuration
            sensor_set_id = "my_new_function_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id,
                device_identifier="test_device_my_new_function",  # Must match YAML global_settings
                name="My New Function Test Sensors",
            )

            with open(my_new_function_yaml_path, "r") as f:
                yaml_content = f.read()

            # Import YAML with dependency resolution
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3  # 3 sensors in the fixture

            # Set up synthetic sensors via public API using HA entity lookups
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_my_new_function",
                # No data_provider_callback means HA entity lookups are used automatically
            )

            # Verify setup
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation - both update mechanisms
            await sensor_manager.async_update_sensors()

            # Get the actual sensor entities to verify their computed values
            all_entities = []
            for call in mock_async_add_entities.call_args_list:
                entities_list = call.args[0] if call.args else []
                all_entities.extend(entities_list)

            # Verify we have the expected number of entities
            assert len(all_entities) >= 3, f"Expected at least 3 entities, got {len(all_entities)}"

            # Create a mapping for easy lookup
            sensor_entities = {entity.unique_id: entity for entity in all_entities}

            # Test actual formula evaluation results
            basic_entity = sensor_entities.get("my_func_basic_test")
            if basic_entity and basic_entity.native_value is not None:
                assert "processed_basic_value_option1" in str(basic_entity.native_value)

            variable_entity = sensor_entities.get("my_func_variable_test")
            if variable_entity and variable_entity.native_value is not None:
                assert "processed_variable_value_option2" in str(variable_entity.native_value)

            global_entity = sensor_entities.get("my_func_global_test")
            if global_entity and global_entity.native_value is not None:
                assert "processed_global_test_value_option1" in str(global_entity.native_value)

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_my_new_function_literals_in_variables_and_attributes(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        my_new_function_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test that my_func() functions work as literals in variables and attributes."""

        # Set up storage manager
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_my_new_function_literals", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load configuration
            sensor_set_id = "my_new_function_literals_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_my_new_function", name="My New Function Literals Test"
            )

            with open(my_new_function_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3

            # Get the sensor set to verify literals were processed
            sensor_set = storage_manager.get_sensor_set(sensor_set_id)
            assert sensor_set is not None

            # Get the list of sensors
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Verify the sensors were created successfully - this confirms that
            # function literals in variables and attributes were processed correctly

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)

    async def test_my_new_function_comparison_with_external_entities(
        self,
        mock_hass,
        mock_entity_registry,
        mock_states,
        my_new_function_yaml_path,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test my_func() functions work with external entity values."""

        # Set up external entities with test data
        mock_states["sensor.test_input_entity"] = self.create_mock_state("test_value")
        mock_states["sensor.another_entity"] = self.create_mock_state("another_value")

        # Set up storage manager
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store
            MockDeviceRegistry.return_value = mock_device_registry

            storage_manager = StorageManager(mock_hass, "test_my_new_function_comparison", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Load configuration
            sensor_set_id = "my_new_function_comparison_test"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_my_new_function", name="My Function Comparison Test"
            )

            with open(my_new_function_yaml_path, "r") as f:
                yaml_content = f.read()

            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 3

            # Set up synthetic sensors
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_my_new_function",
                # No data_provider_callback means HA entity lookups are used automatically
            )

            # Test that sensors can be created and evaluated without errors
            assert sensor_manager is not None
            await sensor_manager.async_update_sensors()

            # Verify no exceptions were raised during evaluation
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 3

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
```

### 8. Run Tests

Execute your tests to ensure everything works:

```bash
# Run unit tests
poetry run python -m pytest tests/unit/evaluator_handlers/test_my_new_handler.py -xvs

# Run integration tests
poetry run python -m pytest tests/integration/test_my_new_function_integration.py -xvs

# Run existing tests to ensure no regressions
poetry run python -m pytest tests/integration/test_datetime_functions_integration.py -v
```

## Important Design Considerations

### Handler Registration Priority

**Critical**: Register your handler **before** the `StringHandler` if your functions take string parameters. The string handler
uses `FormulaRouter` which detects string literals and claims the formula for string processing.

```python
# CORRECT order - metadata before string
self.register_handler_type("metadata", MetadataHandler)
self.register_handler_type("my_new_handler", MyNewHandler)
self.register_handler_type("string", StringHandler)

# WRONG order - string would claim metadata formulas
self.register_handler_type("string", StringHandler)
self.register_handler_type("metadata", MetadataHandler)  # Too late!
```

**Why This Matters**: During the metadata handler implementation, the initial test failures were caused by the `StringHandler`
claiming formulas like `metadata(1000.0, 'last_changed')` because the router detected the string literal `'last_changed'` and
routed the entire formula to string processing. This prevented the metadata handler from ever being tested.

### Function Detection Patterns

Use simple string detection in `can_handle()` rather than complex regex:

```python
# GOOD - simple and reliable
def can_handle(self, formula: str) -> bool:
    return "my_func(" in formula

# AVOID - complex regex that may fail after variable resolution
def can_handle(self, formula: str) -> bool:
    pattern = r'my_func\s*\(\s*[^,]+\s*,\s*[^)]+\s*\)'
    return bool(re.search(pattern, formula))
```

**Critical Insight**: The `can_handle()` method is called **after variable resolution**. This means a formula like
`metadata(power_entity, 'last_changed')` becomes `metadata(1000.0, 'last_changed')` before your handler sees it. Complex regex
patterns that expect specific variable names will fail, while simple string detection works reliably.

### Parameter Parsing

For simple cases, use string splitting. For complex nested parameters, consider using a proper parser:

```python
# Simple case - comma-separated parameters
params = [p.strip() for p in params_str.split(',')]

# Complex case - handle nested parentheses and quotes
# (Implement or use a more sophisticated parser)
```

### Error Handling

Provide clear, actionable error messages:

```python
if len(params) != 2:
    raise ValueError(f"my_func() requires exactly 2 parameters, got {len(params)}")

if option not in VALID_OPTIONS:
    raise ValueError(f"Invalid option: {option}. Valid options: {sorted(VALID_OPTIONS)}")
```

### Home Assistant Access

Only request `hass` parameter if you actually need to access Home Assistant state:

```python
# If you need HA access
def __init__(self, expression_evaluator=None, hass=None):
    self._hass = hass

# If you don't need HA access
def __init__(self, expression_evaluator=None):
    # No hass parameter needed
```

## Common Pitfalls and Solutions

### 1. Handler Not Being Called

- **Problem**: Formula being claimed by another handler
- **Solution**: Check registration order in `HandlerFactory`
- **Real Example**: `metadata(1000.0, 'last_changed')` was claimed by `StringHandler` before `MetadataHandler` could process it

### 2. "Undefined Variable" Errors

- **Problem**: Function name not recognized by validation
- **Solution**: Add to shared constants and update validation systems
- **Files to Update**: `shared_constants.py`, `dependency_parser.py`, `schema_validator.py`, `utils_config.py`

### 3. Variable Resolution Issues

- **Problem**: Variables not being resolved from context
- **Solution**: Check context parameter usage and variable inheritance
- **Debug Tip**: Add logging to see what context variables are available during evaluation

### 4. Test Failures Due to Timing

- **Problem**: Integration tests fail intermittently
- **Solution**: Use proper async/await patterns and mock setup
- **Critical**: Always use the common registry fixtures from `conftest.py` - never create custom mocks

### 5. String Parameter Handling

- **Problem**: String parameters not being parsed correctly
- **Solution**: Strip quotes properly and handle both single and double quotes
- **Example**: `params[1].strip().strip('\'"')` handles both `'key'` and `"key"`

### 6. Integration Test "hass is None" Errors

- **Problem**: Mock entities returning `None` for hass attribute
- **Solution**: Follow the integration test guide patterns exactly - use proper mock state creation
- **Pattern**: `type("MockState", (), {"state": value, "entity_id": entity_id})()`

### 7. Formula Returned as Literal String

- **Problem**: Handler processes formula but result is still the formula text
- **Solution**: Check if handler is being called at all (add debug logging to `can_handle()`)
- **Common Cause**: Another handler claimed the formula first due to registration order

## Integration Testing Specific Insights

Beyond the comprehensive guidance in the integration test guide, here are handler-specific lessons learned:

### Test Structure Requirements

**Follow the Three-Test Pattern**: Every handler should have these three integration tests:

1. **Basic Integration**: Core functionality with formula evaluation
2. **Literals in Variables**: Testing function calls within YAML variable definitions
3. **External Entity Interaction**: Testing with mock external entities

**Why Three Tests**: This pattern from the datetime tests catches different failure modes - evaluation issues, YAML processing
problems, and entity resolution bugs.

### Mock State Creation for Handlers

```python
def create_mock_state(self, state_value: str, **kwargs):
    """Create a mock state object with handler-specific metadata."""
    return type("MockState", (), {
        "state": state_value,
        "attributes": {},
        **kwargs  # Add handler-specific properties like last_changed, entity_id
    })()
```

**Handler-Specific Properties**: Add the metadata your handler needs (e.g., `last_changed`, `entity_id` for metadata handler).

### Debug Integration Test Failures

When integration tests fail with your handler:

1. **Add debug logging to `can_handle()`** to see if your handler is being tested
2. **Check the exact formula** your handler receives (it's post-variable-resolution)
3. **Verify registration order** in `HandlerFactory` - string literals can hijack your formulas
4. **Use the datetime test as reference** - copy its structure exactly

### Handler-Specific Test Assertions

```python
# Test the actual function output, not just that it doesn't crash
if entity and entity.native_value is not None:
    assert str(expected_value) in str(entity.native_value), (
        f"Handler failed: expected '{expected_value}', got '{entity.native_value}'"
    )
```

**Defensive Assertions**: Check that your handler actually processed the formula, not just that something was returned.

## Best Practices

1. **Follow Existing Patterns**: Model your handler after successful implementations (like `MetadataHandler`)
2. **Comprehensive Testing**: Write both unit and integration tests following the three-test pattern
3. **Clear Documentation**: Document all parameters, return values, and error conditions
4. **Error Handling**: Provide helpful error messages with context
5. **Logging**: Add debug logging for troubleshooting, especially in `can_handle()`
6. **Type Safety**: Use proper type hints and handle edge cases

## Conclusion

Creating a new handler involves multiple files and systems, but following this guide ensures proper integration with the
ha-synthetic-sensors framework. The key is understanding the handler lifecycle, registration priority, and the validation
systems that need to recognize your new functions.
