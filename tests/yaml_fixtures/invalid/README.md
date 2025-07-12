# Invalid YAML Fixtures

This directory contains YAML fixtures that are intentionally invalid for testing purposes.

## Purpose

These fixtures are used to test the YAML validation functionality and ensure that the integration properly handles
and reports errors for:

- Malformed YAML syntax
- Missing required fields
- Invalid formula syntax
- Incorrect YAML structure

## Pre-commit Exclusion

These files are excluded from pre-commit YAML validation checks in `.pre-commit-config.yaml` because they are intentionally invalid.

## Files

- `integration_test_invalid_missing_formula.yaml` - Tests missing required fields and undefined variables
- `integration_test_invalid_structure.yaml` - Tests incorrect YAML structure and duplicate keys
- `integration_test_invalid_syntax.yaml` - Tests invalid mathematical formulas and YAML syntax errors
- `integration_test_malformed_yaml.yaml` - Tests malformed YAML syntax (unclosed quotes, bad indentation)
- `integration_test_malformed.yaml` - Additional malformed YAML test case

## Usage

These fixtures are loaded in test files using the `load_yaml_fixture()` function, which automatically detects invalid fixtures
by filename prefix and loads them from this directory.
