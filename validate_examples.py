#!/usr/bin/env python3
"""
Validation script for YAML examples and test fixtures.

This script validates all YAML files in the examples/ directory and test fixtures
to ensure they are properly formatted and contain the expected sensors that tests
are looking for.
"""

import argparse
import logging
from pathlib import Path
import sys
from typing import List

import yaml

# Add the src directory to the path so we can import the validation functions
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ha_synthetic_sensors.config_manager import ConfigManager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class YAMLValidator:
    """Validator for YAML examples and test fixtures."""

    def __init__(self):
        """Initialize the validator."""
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.validated_files: List[str] = []
        # Create a config manager instance for validation
        self.config_manager = ConfigManager(hass=None)

    def validate_yaml_file(self, file_path: Path) -> bool:
        """Validate a single YAML file using the actual implementation's validation."""
        logger.info(f"Validating {file_path}")

        try:
            # Use the config manager's validation method
            result = self.config_manager.validate_config_file(file_path)

            if not result["valid"]:
                for error in result["errors"]:
                    self.errors.append(f"{file_path}: {error['message']}")
                return False

            # Add warnings
            for warning in result["warnings"]:
                self.warnings.append(f"{file_path}: {warning['message']}")

            # Additional validation: check if sensors exist (for test fixtures)
            if not self._validate_sensors_exist(file_path):
                return False

            self.validated_files.append(str(file_path))
            logger.info(f"✓ {file_path} is valid")
            return True

        except Exception as e:
            self.errors.append(f"{file_path}: Unexpected error: {e}")
            return False

    def _validate_sensors_exist(self, file_path: Path) -> bool:
        """Validate that test fixtures contain expected sensors."""
        # Only validate test fixtures, not all examples
        if not file_path.name.startswith("edge_") and not file_path.name.startswith("test_"):
            return True

        try:
            with open(file_path, encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f)

            if not yaml_data or "sensors" not in yaml_data:
                return True  # Not a test fixture

            # Define expected sensors from failing tests
            expected_sensors = {
                "edge_deep_chain.yaml": ["deep_chain_test", "complex_deep_chain"],
                "edge_variable_conflicts.yaml": [
                    "variable_conflict_test",
                    "attr_variable_conflict",
                    "sensor_key_conflict",
                    "complex_variable_conflict",
                ],
                "edge_variable_inheritance.yaml": [
                    "complex_inheritance_test",
                    "inheritance_override_test",
                    "deep_inheritance_test",
                    "conditional_inheritance_test",
                ],
                "edge_multiple_circular.yaml": ["multiple_circular_test"],
            }

            if file_path.name not in expected_sensors:
                return True  # Not a test fixture we need to validate

            actual_sensors = set(yaml_data["sensors"].keys())
            expected_sensors_set = set(expected_sensors[file_path.name])

            missing_sensors = expected_sensors_set - actual_sensors
            if missing_sensors:
                self.errors.append(f"{file_path}: Missing expected sensors: {missing_sensors}")
                return False

            logger.info(f"✓ {file_path}: Found {len(actual_sensors)} sensors")
            return True

        except Exception as e:
            self.errors.append(f"{file_path}: Error reading test fixture: {e}")
            return False

    def validate_test_fixtures(self) -> bool:
        """Validate that test fixtures contain expected sensors."""
        logger.info("Validating test fixtures...")

        # Define expected sensors from failing tests
        expected_sensors = {
            "examples/edge_deep_chain.yaml": ["deep_chain_test", "complex_deep_chain"],
            "examples/edge_variable_conflicts.yaml": [
                "variable_conflict_test",
                "attr_variable_conflict",
                "sensor_key_conflict",
                "complex_variable_conflict",
            ],
            "examples/edge_variable_inheritance.yaml": [
                "complex_inheritance_test",
                "inheritance_override_test",
                "deep_inheritance_test",
                "conditional_inheritance_test",
            ],
            "examples/edge_multiple_circular.yaml": ["multiple_circular_test"],
        }

        all_valid = True

        for yaml_file, expected_sensor_list in expected_sensors.items():
            yaml_path = Path(yaml_file)
            if not yaml_path.exists():
                self.errors.append(f"Test fixture {yaml_file} not found")
                all_valid = False
                continue

            try:
                with open(yaml_path, encoding="utf-8") as f:
                    yaml_data = yaml.safe_load(f)

                if not yaml_data or "sensors" not in yaml_data:
                    self.errors.append(f"{yaml_file}: Invalid structure for test fixture")
                    all_valid = False
                    continue

                actual_sensors = set(yaml_data["sensors"].keys())
                expected_sensors_set = set(expected_sensor_list)

                missing_sensors = expected_sensors_set - actual_sensors
                if missing_sensors:
                    self.errors.append(f"{yaml_file}: Missing expected sensors: {missing_sensors}")
                    all_valid = False

                extra_sensors = actual_sensors - expected_sensors_set
                if extra_sensors:
                    self.warnings.append(f"{yaml_file}: Extra sensors found: {extra_sensors}")

                logger.info(f"✓ {yaml_file}: Found {len(actual_sensors)} sensors")

            except Exception as e:
                self.errors.append(f"{yaml_file}: Error reading test fixture: {e}")
                all_valid = False

        return all_valid

    def validate_all_examples(self) -> bool:
        """Validate all YAML files in the examples directory."""
        logger.info("Validating all examples...")

        examples_dir = Path("examples")
        if not examples_dir.exists():
            self.errors.append("Examples directory not found")
            return False

        yaml_files = list(examples_dir.glob("*.yaml"))
        if not yaml_files:
            self.errors.append("No YAML files found in examples directory")
            return False

        all_valid = True
        for yaml_file in yaml_files:
            if not self.validate_yaml_file(yaml_file):
                all_valid = False

        return all_valid

    def print_summary(self):
        """Print validation summary."""
        print("\n" + "=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)

        if self.validated_files:
            print(f"\n✓ Validated {len(self.validated_files)} files:")
            for file_path in sorted(self.validated_files):
                print(f"  - {file_path}")

        if self.warnings:
            print(f"\n⚠ {len(self.warnings)} warnings:")
            for warning in self.warnings:
                print(f"  - {warning}")

        if self.errors:
            print(f"\n✗ {len(self.errors)} errors:")
            for error in self.errors:
                print(f"  - {error}")

        print(f"\nTotal: {len(self.validated_files)} valid, {len(self.warnings)} warnings, {len(self.errors)} errors")

        if self.errors:
            print("\n❌ Validation failed!")
            return False
        else:
            print("\n✅ All validations passed!")
            return True


def main():
    """Main validation function."""
    parser = argparse.ArgumentParser(description="Validate YAML examples and test fixtures")
    parser.add_argument("--examples", action="store_true", help="Validate all examples")
    parser.add_argument("--fixtures", action="store_true", help="Validate test fixtures")
    parser.add_argument("--all", action="store_true", help="Validate everything (default)")
    parser.add_argument("--file", type=str, help="Validate specific YAML file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    validator = YAMLValidator()

    if args.file:
        # Validate specific file
        file_path = Path(args.file)
        if not file_path.exists():
            logger.error(f"File not found: {args.file}")
            sys.exit(1)

        success = validator.validate_yaml_file(file_path)
        validator.print_summary()
        sys.exit(0 if success else 1)

    # Default behavior: validate everything
    if args.all or (not args.examples and not args.fixtures):
        examples_success = validator.validate_all_examples()
        fixtures_success = validator.validate_test_fixtures()
        success = examples_success and fixtures_success
    elif args.examples:
        success = validator.validate_all_examples()
    elif args.fixtures:
        success = validator.validate_test_fixtures()
    else:
        logger.error("No validation targets specified")
        sys.exit(1)

    validator.print_summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
