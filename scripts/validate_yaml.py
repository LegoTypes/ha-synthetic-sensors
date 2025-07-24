#!/usr/bin/env python3
"""
Validation script for YAML examples and test fixtures.

This script validates all YAML files in the examples/ directory and test fixtures
to ensure they are properly formatted and follow the expected schema.
"""

import argparse
import logging
from pathlib import Path
import sys
from typing import List

import yaml

# Add the src directory to the path so we can import the validation functions
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

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

            # Basic YAML structure validation
            if not self._validate_yaml_structure(file_path):
                return False

            self.validated_files.append(str(file_path))
            logger.info(f"✓ {file_path}: Found {self._count_sensors(file_path)} sensors")
            return True

        except Exception as e:
            self.errors.append(f"{file_path}: Unexpected error: {e}")
            return False

    def _validate_yaml_structure(self, file_path: Path) -> bool:
        """Validate basic YAML structure."""
        try:
            with open(file_path, encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f)

            if not yaml_data:
                self.errors.append(f"{file_path}: Empty or invalid YAML file")
                return False

            # Check if it's a sensor configuration file
            if "sensors" in yaml_data:
                if not isinstance(yaml_data["sensors"], dict):
                    self.errors.append(f"{file_path}: 'sensors' must be a dictionary")
                    return False

                # Validate each sensor has required fields
                for sensor_name, sensor_config in yaml_data["sensors"].items():
                    if not isinstance(sensor_config, dict):
                        self.errors.append(f"{file_path}: Sensor '{sensor_name}' must be a dictionary")
                        return False

                    if "name" not in sensor_config:
                        self.errors.append(f"{file_path}: Sensor '{sensor_name}' missing 'name' field")
                        return False

                    if "formula" not in sensor_config:
                        self.errors.append(f"{file_path}: Sensor '{sensor_name}' missing 'formula' field")
                        return False

            return True

        except yaml.YAMLError as e:
            self.errors.append(f"{file_path}: YAML parsing error: {e}")
            return False
        except Exception as e:
            self.errors.append(f"{file_path}: Error reading file: {e}")
            return False

    def _count_sensors(self, file_path: Path) -> int:
        """Count the number of sensors in a YAML file."""
        try:
            with open(file_path, encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f)

            if yaml_data and "sensors" in yaml_data:
                return len(yaml_data["sensors"])
            return 0
        except Exception:
            return 0

    def validate_test_fixtures(self) -> bool:
        """Validate that test fixtures have proper YAML structure."""
        logger.info("Validating test fixtures...")

        fixtures_dir = Path(__file__).parent.parent / "tests" / "yaml_fixtures"
        if not fixtures_dir.exists():
            self.errors.append("Test fixtures directory not found")
            return False

        yaml_files = list(fixtures_dir.glob("*.yaml"))
        if not yaml_files:
            self.errors.append("No YAML files found in test fixtures directory")
            return False

        all_valid = True
        for yaml_file in yaml_files:
            if not self.validate_yaml_file(yaml_file):
                all_valid = False

        return all_valid

    def validate_all_examples(self) -> bool:
        """Validate all YAML files in the examples directory."""
        logger.info("Validating all examples...")

        examples_dir = Path(__file__).parent.parent / "examples"
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
        print("=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)

        if self.errors:
            print(f"\n❌ {len(self.errors)} errors:")
            for error in self.errors:
                print(f"  - {error}")

        if self.warnings:
            print(f"\n⚠ {len(self.warnings)} warnings:")
            for warning in self.warnings:
                print(f"  - {warning}")

        print(f"\nTotal: {len(self.validated_files)} valid, {len(self.warnings)} warnings, {len(self.errors)} errors")

        if not self.errors:
            print("\n✅ All validations passed!")
        else:
            print("\n❌ Validation failed!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate YAML examples and test fixtures")
    parser.add_argument("--examples", action="store_true", help="Validate examples directory")
    parser.add_argument("--fixtures", action="store_true", help="Validate test fixtures")
    parser.add_argument("--all", action="store_true", help="Validate both examples and fixtures")

    args = parser.parse_args()

    validator = YAMLValidator()
    all_valid = True

    if args.fixtures or args.all:
        if not validator.validate_test_fixtures():
            all_valid = False

    if args.examples or args.all:
        if not validator.validate_all_examples():
            all_valid = False

    # If no specific target specified, validate both
    if not (args.examples or args.fixtures or args.all):
        if not validator.validate_test_fixtures():
            all_valid = False
        if not validator.validate_all_examples():
            all_valid = False

    validator.print_summary()

    sys.exit(0 if all_valid else 1)


if __name__ == "__main__":
    main()
