#!/usr/bin/env python3
"""
YAML Formula Conversion Script for Enhanced SimpleEval

This script converts YAML formulas to use enhanced SimpleEval patterns where beneficial.
The main conversions are:
1. contains(text, "substr") → "substr" in text  (cleaner syntax)
2. length(text) → len(text)  (native Python function)
3. Updates duration arithmetic to use as_minutes() helpers where needed

Note: Most existing YAML will work as-is since we added the functions to enhanced SimpleEval.
This script only makes syntax improvements where the new patterns are cleaner.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import yaml


class YamlFormulaConverter:
    """Converts YAML formulas to enhanced SimpleEval patterns."""

    def __init__(self):
        self.conversions_made = 0
        self.files_processed = 0
        self.conversion_log: List[str] = []

    def convert_formula(self, formula: str) -> Tuple[str, bool]:
        """Convert a single formula string. Returns (new_formula, changed)."""
        if not isinstance(formula, str):
            return formula, False

        original = formula
        changed = False

        # Conversion 1: contains(text, "substr") → "substr" in text
        # Pattern: contains(anything, "string_literal")
        contains_pattern = r'contains\s*\(\s*([^,]+?)\s*,\s*(["\'][^"\']*["\'])\s*\)'
        def replace_contains(match):
            text, substr = match.groups()
            return f'{substr} in {text}'

        new_formula = re.sub(contains_pattern, replace_contains, formula)
        if new_formula != formula:
            changed = True
            self.conversion_log.append(f"  contains() → in operator: {formula} → {new_formula}")
            formula = new_formula

        # Conversion 2: length(text) → len(text)
        length_pattern = r'\blength\s*\('
        new_formula = re.sub(length_pattern, 'len(', formula)
        if new_formula != formula:
            changed = True
            self.conversion_log.append(f"  length() → len(): {formula} → {new_formula}")
            formula = new_formula

        # Log if any changes were made
        if changed:
            self.conversions_made += 1

        return formula, changed

    def convert_yaml_recursive(self, obj, path=""):
        """Recursively convert formulas in YAML structure."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                if key == "formula" and isinstance(value, str):
                    new_value, changed = self.convert_formula(value)
                    if changed:
                        obj[key] = new_value
                        self.conversion_log.append(f"Formula at {current_path}: {value} → {new_value}")
                else:
                    self.convert_yaml_recursive(value, current_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                self.convert_yaml_recursive(item, f"{path}[{i}]")

    def convert_file(self, file_path: Path, dry_run: bool = False) -> bool:
        """Convert a single YAML file. Returns True if changes were made."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse YAML
            try:
                yaml_data = yaml.safe_load(content)
            except yaml.YAMLError as e:
                print(f"❌ YAML parse error in {file_path}: {e}")
                return False

            if not yaml_data:
                return False

            # Track conversions for this file
            initial_conversions = self.conversions_made
            initial_log_size = len(self.conversion_log)

            # Convert formulas
            self.convert_yaml_recursive(yaml_data)

            # Check if any changes were made
            changes_made = self.conversions_made > initial_conversions

            if changes_made:
                print(f"🔄 Converting {file_path}:")
                # Show conversions for this file
                for log_entry in self.conversion_log[initial_log_size:]:
                    print(f"    {log_entry}")

                if not dry_run:
                    # Write back to file
                    with open(file_path, 'w', encoding='utf-8') as f:
                        yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
                    print(f"    ✅ File updated")
                else:
                    print(f"    🔍 Dry run - no changes written")
            else:
                print(f"✅ No changes needed: {file_path}")

            self.files_processed += 1
            return changes_made

        except Exception as e:
            print(f"❌ Error processing {file_path}: {e}")
            return False

    def convert_directory(self, directory: Path, pattern: str = "*.yaml", dry_run: bool = False):
        """Convert all YAML files in a directory."""
        if not directory.exists():
            print(f"❌ Directory not found: {directory}")
            return

        yaml_files = list(directory.rglob(pattern))
        if not yaml_files:
            print(f"❌ No YAML files found in {directory}")
            return

        print(f"📁 Processing {len(yaml_files)} YAML files in {directory}")
        print(f"🔍 Dry run mode: {dry_run}")
        print()

        files_changed = 0
        for file_path in yaml_files:
            if self.convert_file(file_path, dry_run):
                files_changed += 1

        print(f"\n📊 CONVERSION SUMMARY")
        print(f"Files processed: {self.files_processed}")
        print(f"Files changed: {files_changed}")
        print(f"Total conversions: {self.conversions_made}")

        if dry_run:
            print(f"\n🔍 This was a dry run. Use --apply to make actual changes.")


def main():
    parser = argparse.ArgumentParser(
        description="Convert YAML formulas to enhanced SimpleEval patterns",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run on a single file
  python scripts/convert_yaml_to_enhanced_simpleeval.py tests/fixtures/integration/string_operations_advanced.yaml

  # Dry run on all fixtures
  python scripts/convert_yaml_to_enhanced_simpleeval.py tests/fixtures/

  # Apply conversions to a directory
  python scripts/convert_yaml_to_enhanced_simpleeval.py tests/fixtures/ --apply
        """
    )

    parser.add_argument(
        "path",
        type=Path,
        help="Path to YAML file or directory to convert"
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply changes (default is dry run)"
    )

    parser.add_argument(
        "--pattern",
        default="*.yaml",
        help="File pattern for directory processing (default: *.yaml)"
    )

    args = parser.parse_args()

    converter = YamlFormulaConverter()

    if args.path.is_file():
        # Single file
        print(f"🔧 Converting single file: {args.path}")
        converter.convert_file(args.path, dry_run=not args.apply)
    elif args.path.is_dir():
        # Directory
        converter.convert_directory(args.path, args.pattern, dry_run=not args.apply)
    else:
        print(f"❌ Path not found: {args.path}")
        sys.exit(1)


if __name__ == "__main__":
    main()