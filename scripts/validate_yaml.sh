#!/bin/bash

# Validation script for YAML examples and test fixtures
# This script runs the validate_yaml.py script with proper Python environment

set -e  # Exit on any error

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to the project root directory
cd "$PROJECT_ROOT"

# Check if we're in a poetry environment
if command -v poetry &> /dev/null; then
    echo "Running validation with Poetry..."
    poetry run python scripts/validate_yaml.py "$@"
else
    echo "Poetry not found, trying direct Python execution..."
    python scripts/validate_yaml.py "$@"
fi
