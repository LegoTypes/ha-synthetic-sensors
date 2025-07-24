"""Validation utilities for configuration files."""

from pathlib import Path
from typing import Any

import yaml


def create_file_not_found_error(path: Path) -> dict[str, Any]:
    """Create a standardized file not found error response.

    Args:
        path: Path that was not found

    Returns:
        Validation error dictionary
    """
    return {
        "valid": False,
        "errors": [
            {
                "message": f"Configuration file not found: {path}",
                "path": "file",
                "severity": "error",
                "schema_path": "",
                "suggested_fix": "Check file path and ensure file exists",
            }
        ],
        "warnings": [],
        "schema_version": "unknown",
        "file_path": str(path),
    }


def create_empty_file_error(path: Path) -> dict[str, Any]:
    """Create a standardized empty file error response.

    Args:
        path: Path to the empty file

    Returns:
        Validation error dictionary
    """
    return {
        "valid": False,
        "errors": [
            {
                "message": "Configuration file is empty",
                "path": "file",
                "severity": "error",
                "schema_path": "",
                "suggested_fix": "Add configuration content to the file",
            }
        ],
        "warnings": [],
        "schema_version": "unknown",
        "file_path": str(path),
    }


def load_yaml_file(path: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Load and parse a YAML file.

    Args:
        path: Path to YAML file

    Returns:
        Tuple of (yaml_data, error_response). If successful, error_response is None.
        If failed, yaml_data is None and error_response contains the error.
    """
    if not path.exists():
        return None, create_file_not_found_error(path)

    try:
        with open(path, encoding="utf-8") as file:
            yaml_data = yaml.safe_load(file)

        if not yaml_data:
            return None, create_empty_file_error(path)

        return yaml_data, None

    except yaml.YAMLError as e:
        return None, {
            "valid": False,
            "errors": [
                {
                    "message": f"YAML parsing error: {e}",
                    "path": "file",
                    "severity": "error",
                    "schema_path": "",
                    "suggested_fix": "Fix YAML syntax errors",
                }
            ],
            "warnings": [],
            "schema_version": "unknown",
            "file_path": str(path),
        }
    except Exception as e:
        return None, {
            "valid": False,
            "errors": [
                {
                    "message": f"File reading error: {e}",
                    "path": "file",
                    "severity": "error",
                    "schema_path": "",
                    "suggested_fix": "Check file permissions and encoding",
                }
            ],
            "warnings": [],
            "schema_version": "unknown",
            "file_path": str(path),
        }
