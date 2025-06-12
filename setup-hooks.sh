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
    touch .deps-installed
fi

# Install pre-commit hooks
poetry run pre-commit install

echo "Git hooks installed successfully!"
