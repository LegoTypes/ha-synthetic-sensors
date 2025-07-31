#!/usr/bin/env python3
"""Verify development setup for ha-synthetic-sensors."""

import sys
import subprocess
from pathlib import Path


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and return success status."""
    print(f"Checking {description}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"  ✅ {description}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ {description} failed:")
        print(f"     Error: {e.stderr}")
        return False


def check_import(module: str, description: str) -> bool:
    """Check if a module can be imported."""
    print(f"Checking {description}...")
    try:
        __import__(module)
        print(f"  ✅ {description}")
        return True
    except ImportError as e:
        print(f"  ❌ {description} failed: {e}")
        return False


def main():
    """Verify the development setup."""
    print("🔍 Verifying ha-synthetic-sensors development setup...\n")

    checks_passed = 0
    total_checks = 0

    # Check Poetry installation
    total_checks += 1
    if run_command(["poetry", "--version"], "Poetry installation"):
        checks_passed += 1

    # Check if we're in a Poetry environment
    total_checks += 1
    if run_command(["poetry", "env", "info"], "Poetry environment"):
        checks_passed += 1

    # Check type stubs by testing mypy on a simple import
    type_stub_tests = [
        ("import pytz", "types-pytz"),
        ("import yaml", "types-PyYAML"),
        ("import jsonschema", "types-jsonschema"),
        ("import aiofiles", "types-aiofiles"),
    ]

    for import_stmt, package in type_stub_tests:
        total_checks += 1
        test_code = f"{import_stmt}\n"
        try:
            result = subprocess.run(
                ["poetry", "run", "mypy", "-c", test_code],
                capture_output=True,
                text=True,
                check=True
            )
            print(f"  ✅ {package} type stubs")
            checks_passed += 1
        except subprocess.CalledProcessError as e:
            if "Library stubs not installed" in e.stderr:
                print(f"  ❌ {package} type stubs failed: Missing stubs")
            else:
                print(f"  ❌ {package} type stubs failed: {e.stderr}")

    # Check core dependencies
    core_deps = [
        ("pytz", "pytz"),
        ("yaml", "PyYAML"),
        ("jsonschema", "jsonschema"),
        ("aiofiles", "aiofiles"),
    ]

    for module, package in core_deps:
        total_checks += 1
        if check_import(module, f"{package} core dependency"):
            checks_passed += 1

    # Check mypy
    total_checks += 1
    if run_command(["poetry", "run", "mypy", "--version"], "mypy installation"):
        checks_passed += 1

    # Check ruff
    total_checks += 1
    if run_command(["poetry", "run", "ruff", "--version"], "ruff installation"):
        checks_passed += 1

    # Check pre-commit
    total_checks += 1
    if run_command(["poetry", "run", "pre-commit", "--version"], "pre-commit installation"):
        checks_passed += 1

    # Check pytest
    total_checks += 1
    if run_command(["poetry", "run", "pytest", "--version"], "pytest installation"):
        checks_passed += 1

    # Check if we can import the main package
    total_checks += 1
    if check_import("ha_synthetic_sensors", "ha-synthetic-sensors package"):
        checks_passed += 1

    # Check if we can import datetime functions
    total_checks += 1
    if check_import("ha_synthetic_sensors.datetime_functions", "datetime functions module"):
        checks_passed += 1

    print(f"\n📊 Setup Verification Results:")
    print(f"   Passed: {checks_passed}/{total_checks}")

    if checks_passed == total_checks:
        print("🎉 All checks passed! Your development environment is ready.")
        return 0
    else:
        print("⚠️  Some checks failed. Please run:")
        print("   poetry install --with dev")
        print("   ./setup-hooks.sh")
        return 1


if __name__ == "__main__":
    sys.exit(main())