#!/bin/bash

# Check if we should force update (pass --update flag)
FORCE_UPDATE=false
if [[ "$1" == "--update" ]]; then
    FORCE_UPDATE=true
fi

# Ensure dependencies are installed first
if [[ ! -f ".deps-installed" ]] || [[ "pyproject.toml" -nt ".deps-installed" ]] || [[ "$FORCE_UPDATE" == "true" ]]; then
    echo "Installing/updating dependencies..."

    if [[ "$FORCE_UPDATE" == "true" ]]; then
        echo "Forcing update to latest versions..."
        if ! poetry update; then
            echo "Failed to update dependencies. Please check the output above."
            exit 1
        fi
    else
        if ! poetry install --with dev; then
            echo "Failed to install dependencies. Please check the output above."
            exit 1
        fi
    fi

    # Ensure type stubs are properly installed
    echo "Ensuring type stubs are installed..."
    poetry run pip install types-pytz types-PyYAML types-jsonschema types-aiofiles

    touch .deps-installed
fi

# Install pre-commit hooks with explicit hook type to avoid migration mode
poetry run pre-commit install --hook-type pre-commit --overwrite

echo "Git hooks installed successfully!"
