#!/usr/bin/env python3
"""Validation script for hybrid test migration.

This script checks if a test file has been properly migrated to use the hybrid testing pattern.
Usage: python tests/validate_hybrid_migration.py tests/integration/test_file.py
"""

import sys
import ast
import re
from pathlib import Path


class HybridMigrationValidator:
    """Validates that test files follow the hybrid testing pattern."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.content = self.file_path.read_text()
        self.issues: list[str] = []
        self.warnings: list[str] = []

    def validate(self) -> bool:
        """Validate the test file against hybrid testing patterns.

        Returns:
            True if validation passes, False if there are issues
        """
        print(f"🔍 Validating {self.file_path.name} for hybrid pattern compliance...")

        self._check_imports()
        self._check_test_signatures()
        self._check_yaml_patterns()
        self._check_component_instantiation()
        self._check_hybrid_usage()

        self._report_results()
        return len(self.issues) == 0

    def _check_imports(self) -> None:
        """Check for proper imports and removal of old imports."""
        # Check for required import
        if "from tests.hybrid_test_base import BooleanLogicHybridTest" not in self.content:
            self.issues.append("❌ Missing required import: from tests.hybrid_test_base import BooleanLogicHybridTest")

        # Check for old imports that should be removed
        old_imports = [
            "from ha_synthetic_sensors.config_manager import ConfigManager",
            "from ha_synthetic_sensors.sensor_manager import SensorManager",
            "from ha_synthetic_sensors.name_resolver import NameResolver",
            "from ha_synthetic_sensors.evaluator import Evaluator",
        ]

        for old_import in old_imports:
            if old_import in self.content:
                self.warnings.append(f"⚠️  Consider removing old import: {old_import}")

    def _check_test_signatures(self) -> None:
        """Check test method signatures for proper hybrid pattern."""
        # Find async test methods
        test_method_pattern = r"async def (test_\w+)\(self,([^)]+)\) -> None:"
        matches = re.findall(test_method_pattern, self.content)

        for method_name, params in matches:
            params = params.strip()

            # Check if using hybrid fixture
            if "hybrid_boolean_test: BooleanLogicHybridTest" in params:
                print(f"  ✅ {method_name}: Correct hybrid signature")
            elif any(old_param in params for old_param in ["mock_hass", "mock_entity_registry", "mock_states"]):
                self.issues.append(f"❌ {method_name}: Still using old fixtures instead of hybrid_boolean_test")
            else:
                self.warnings.append(f"⚠️  {method_name}: Unusual parameter signature")

    def _check_yaml_patterns(self) -> None:
        """Check YAML configurations for proper backing entity usage."""
        # Look for YAML strings
        yaml_pattern = r'config_yaml\s*=\s*["\'\s]*"""([^"]+)"""'
        yaml_matches = re.findall(yaml_pattern, self.content, re.DOTALL)

        for yaml_content in yaml_matches:
            # Check for direct HA entity references (bad pattern)
            ha_entity_pattern = r"(binary_sensor\.|sensor\.)[a-zA-Z_]+"
            ha_entities = re.findall(ha_entity_pattern, yaml_content)

            if ha_entities:
                self.issues.append(f"❌ YAML contains direct HA entity references: {set(ha_entities)}")

            # Check for backing entities (good pattern)
            backing_entity_pattern = r"backing_[a-zA-Z_]+"
            backing_entities = re.findall(backing_entity_pattern, yaml_content)

            if backing_entities:
                print(f"  ✅ YAML uses backing entities: {set(backing_entities)}")
            else:
                self.warnings.append("⚠️  No backing entities found in YAML")

            # Check for required sections
            if "variables:" not in yaml_content:
                self.issues.append("❌ YAML missing variables: section")
            if "metadata:" not in yaml_content:
                self.issues.append("❌ YAML missing metadata: section")
            if "name:" not in yaml_content:
                self.warnings.append("⚠️  YAML missing name: field (recommended)")

    def _check_component_instantiation(self) -> None:
        """Check for manual component instantiation (should be avoided)."""
        bad_patterns = [r"ConfigManager\(", r"SensorManager\(", r"NameResolver\(", r"Evaluator\("]

        for pattern in bad_patterns:
            if re.search(pattern, self.content):
                component = pattern.replace("\\(", "").replace('r"', "")
                self.issues.append(
                    f"❌ Manual {component} instantiation found - use hybrid_boolean_test.{component.lower()} instead"
                )

    def _check_hybrid_usage(self) -> None:
        """Check for proper usage of hybrid test methods."""
        required_patterns = [
            "register_boolean_backing_entities()",
            "load_config_from_yaml(",
            "create_sensors_from_config(",
            "assert_entity_exists(",
        ]

        for pattern in required_patterns:
            if pattern not in self.content:
                self.issues.append(f"❌ Missing hybrid test method: {pattern}")

        # Check for old assertion patterns
        old_assertion_pattern = r'mock_hass\.states\.get\(["\']sensor\.[^"\']+["\']\)'
        if re.search(old_assertion_pattern, self.content):
            self.issues.append(
                "❌ Using old assertion pattern (mock_hass.states.get) - use hybrid_boolean_test.assert_entity_exists() instead"
            )

    def _report_results(self) -> None:
        """Report validation results."""
        print("\n📊 Validation Results:")

        if self.issues:
            print(f"\n❌ {len(self.issues)} Issues Found:")
            for issue in self.issues:
                print(f"  {issue}")

        if self.warnings:
            print(f"\n⚠️  {len(self.warnings)} Warnings:")
            for warning in self.warnings:
                print(f"  {warning}")

        if not self.issues and not self.warnings:
            print("✅ All checks passed! File appears to be properly migrated.")
        elif not self.issues:
            print("✅ No critical issues found, but please review warnings.")
        else:
            print("❌ Migration incomplete - please address the issues above.")


def main():
    """Main entry point for the validation script."""
    if len(sys.argv) != 2:
        print("Usage: python tests/validate_hybrid_migration.py tests/integration/test_file.py")
        sys.exit(1)

    file_path = sys.argv[1]

    if not Path(file_path).exists():
        print(f"❌ File not found: {file_path}")
        sys.exit(1)

    validator = HybridMigrationValidator(file_path)
    success = validator.validate()

    if success:
        print(f"\n🎉 {Path(file_path).name} is ready for testing!")
        print(f"Run: poetry run python -m pytest {file_path} -v")
        sys.exit(0)
    else:
        print(f"\n🔧 Please fix the issues above before testing {Path(file_path).name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
