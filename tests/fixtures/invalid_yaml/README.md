# Invalid YAML Test Fixtures

This directory contains YAML files that are intentionally invalid to test the reserved word validation feature.

## Reserved Word Validation

The synthetic sensors integration validates that YAML variable names do not use reserved words. Reserved words include:

- Python keywords: `if`, `else`, `for`, `while`, `def`, `class`, `import`, etc.
- Built-in types: `str`, `int`, `float`, `bool`, `list`, `dict`, etc.
- Boolean literals: `True`, `False`, `None`
- Math functions: `sum`, `avg`, `max`, `min`, `count`, etc.
- String functions: `str`, `trim`, `lower`, `upper`, etc.
- State-related keywords: `state`
- Home Assistant entity domains: `sensor`, `binary_sensor`, `switch`, etc.

## Test Files

### Invalid Configurations

- `reserved_word_state.yaml` - Uses 'state' as a variable name
- `reserved_word_if.yaml` - Uses 'if' as a variable name
- `reserved_word_str.yaml` - Uses 'str' as a global variable name
- `reserved_word_for.yaml` - Uses 'for' as a variable name
- `reserved_word_while.yaml` - Uses 'while' as a variable name
- `reserved_word_def.yaml` - Uses 'def' as an attribute variable name
- `reserved_word_state_attribute.yaml` - Uses 'state' as an attribute name

### Valid Configuration

- `valid_variable_names.yaml` - Uses only valid variable names for comparison, including partial matches of reserved words
  (e.g., `the_state`, `my_if_condition`)

## Validation Scope

The reserved word validation applies to:

1. **Global variables** (`global_settings.variables.*`)
2. **Sensor variables** (`sensors.*.variables.*`)
3. **Attribute variables** (`sensors.*.attributes.*.variables.*`)
4. **Attribute names** (`sensors.*.attributes.*`)

**Important**: The validation only checks for exact matches of reserved words. Variable names that contain reserved words as
substrings (like `the_state`, `my_if_condition`, `string_value`) are allowed and will not trigger validation errors.

## Error Messages

When a reserved word is used as a variable name, the validation will produce an error with:

- **Message**: "Variable name '{name}' is a reserved word and cannot be used as a variable name"
- **Path**: The exact YAML path where the violation occurred
- **Severity**: ERROR
- **Suggested Fix**: Instructions to rename the variable to avoid collision

## Testing

Run the tests with:

```bash
python tests/test_reserved_word_validation_fixtures.py
```

This will validate each individual YAML file and ensure that:

- Invalid configurations with reserved words are properly rejected
- Valid configurations with proper variable names are accepted
- Error messages and paths are accurate
- Multiple reserved words in a single file are all caught
