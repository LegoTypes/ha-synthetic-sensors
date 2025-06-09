"""Shared fixtures for synthetic sensors infrastructure tests."""

from pathlib import Path

import pytest
import yaml


@pytest.fixture(autouse=True)
def expected_lingering_timers():
    """Fix expected lingering timers for tests."""
    return True


@pytest.fixture
def yaml_fixtures_dir():
    """Get the path to YAML test fixtures directory."""
    return Path(__file__).parent / "yaml_fixtures"


@pytest.fixture
def load_yaml_fixture():
    """Factory for loading YAML test fixtures."""

    def _load_yaml_fixture(fixture_name: str) -> dict:
        """Load a YAML fixture file by name.

        Args:
            fixture_name: Name of the fixture file (without .yaml extension)

        Returns:
            dict: Loaded YAML configuration
        """
        fixtures_dir = Path(__file__).parent / "yaml_fixtures"
        fixture_path = fixtures_dir / f"{fixture_name}.yaml"

        if not fixture_path.exists():
            raise FileNotFoundError(f"YAML fixture not found: {fixture_path}")

        with open(fixture_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    return _load_yaml_fixture


@pytest.fixture
def solar_analytics_yaml(load_yaml_fixture):
    """Load solar analytics YAML configuration from feature planning document."""
    return load_yaml_fixture("solar_analytics")


@pytest.fixture
def hierarchical_calculations_yaml(load_yaml_fixture):
    """Load hierarchical calculations YAML configuration from feature planning."""
    return load_yaml_fixture("hierarchical_calculations")


@pytest.fixture
def cost_analysis_yaml(load_yaml_fixture):
    """Load cost analysis YAML configuration from feature planning document."""
    return load_yaml_fixture("cost_analysis")


@pytest.fixture
def simple_test_yaml(load_yaml_fixture):
    """Load simple test YAML configuration for basic testing."""
    return load_yaml_fixture("simple_test")


@pytest.fixture
def syn2_sample_config():
    """Create a sample synthetic sensors YAML configuration for testing."""
    return {
        "version": "1.0",
        "global_settings": {},
        "sensors": [
            {
                "unique_id": "comfort_index",  # REQUIRED: Unique identifier
                "name": "Comfort Index",  # OPTIONAL: Display name
                "formulas": [
                    {
                        "id": "comfort_formula",  # REQUIRED: Formula identifier
                        "name": "Comfort Level",  # OPTIONAL: Display name
                        "formula": "temp + humidity",
                        "unit_of_measurement": "index",
                        "state_class": "measurement",
                    }
                ],
                "enabled": True,
            },
            {
                "unique_id": "power_status",  # REQUIRED: Unique identifier
                "name": "Power Status",  # OPTIONAL: Display name
                "formulas": [
                    {
                        "id": "power_formula",  # REQUIRED: Formula identifier
                        "name": "Power Level",  # OPTIONAL: Display name
                        "formula": "power * status",
                        "unit_of_measurement": "W",
                        "state_class": "measurement",
                    }
                ],
                "enabled": True,
            },
        ],
    }


@pytest.fixture
def mock_entities_with_dependencies():
    """Create mock entities that match the synthetic sensor configuration."""
    return {
        "sensor.hvac_upstairs": {
            "entity_id": "sensor.hvac_upstairs",
            "state": "1200.0",
            "attributes": {
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
            },
        },
        "sensor.hvac_downstairs": {
            "entity_id": "sensor.hvac_downstairs",
            "state": "800.0",
            "attributes": {
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
            },
        },
        "sensor.kitchen_lights": {
            "entity_id": "sensor.kitchen_lights",
            "state": "150.0",
            "attributes": {
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
            },
        },
        "sensor.kitchen_outlets": {
            "entity_id": "sensor.kitchen_outlets",
            "state": "300.0",
            "attributes": {
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
            },
        },
        "sensor.main_grid_power": {
            "entity_id": "sensor.main_grid_power",
            "state": "2500.0",
            "attributes": {
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
            },
        },
        "sensor.solar_production": {
            "entity_id": "sensor.solar_production",
            "state": "-1000.0",  # Negative indicates production
            "attributes": {
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
            },
        },
    }


@pytest.fixture
def simple_formula_config():
    """Simple formula configuration for basic testing."""
    return {
        "id": "simple_test",  # REQUIRED: Formula identifier
        "name": "Simple Test",  # OPTIONAL: Display name
        "formula": "A + B",
        "unit_of_measurement": "W",
        "device_class": "power",
        "state_class": "measurement",
        "dependencies": ["A", "B"],
    }


@pytest.fixture
def complex_formula_config():
    """Complex formula configuration for advanced testing."""
    return {
        "id": "complex_test",  # REQUIRED: Formula identifier
        "name": "Complex Test",  # OPTIONAL: Display name
        "formula": "max(A, 0) + min(B, 1000) / 2 + abs(C)",
        "unit_of_measurement": "W",
        "device_class": "power",
        "state_class": "measurement",
        "dependencies": ["A", "B", "C"],
    }


@pytest.fixture
def invalid_formula_config():
    """Invalid formula configuration for error testing."""
    return {
        "id": "invalid_test",  # REQUIRED: Formula identifier
        "name": "Invalid Test",  # OPTIONAL: Display name
        "formula": "A + B + )",  # Syntax error
        "unit_of_measurement": "W",
        "device_class": "power",
        "state_class": "measurement",
        "dependencies": ["A", "B"],
    }


@pytest.fixture
def sample_variables():
    """Sample variable mappings for testing."""
    return {
        "HVAC_Upstairs": "sensor.hvac_upstairs",
        "HVAC_Downstairs": "sensor.hvac_downstairs",
        "Kitchen_Lights": "sensor.kitchen_lights",
        "Kitchen_Outlets": "sensor.kitchen_outlets",
        "Main_Grid_Power": "sensor.main_grid_power",
        "Solar_Production": "sensor.solar_production",
        "A": "sensor.test_a",
        "B": "sensor.test_b",
        "C": "sensor.test_c",
    }


@pytest.fixture
def empty_config():
    """Empty configuration for testing edge cases."""
    return {"version": "1.0", "sensors": [], "global_settings": {}}


@pytest.fixture
def invalid_config():
    """Invalid configuration for error testing."""
    return {
        "version": "1.0",
        "sensors": [
            {
                # Missing required unique_id field
                "formulas": [
                    {"id": "test", "formula": "A + B"}  # REQUIRED: Formula identifier
                ]
            }
        ],
    }


# Removed duplicate fixtures - they exist above


@pytest.fixture
def entity_management_test_yaml(load_yaml_fixture):
    """Load entity management test YAML configuration."""
    return load_yaml_fixture("entity_management_test")


@pytest.fixture
def dependency_test_yaml(load_yaml_fixture):
    """Load dependency test YAML configuration."""
    return load_yaml_fixture("dependency_test")


@pytest.fixture
def evaluator_test_yaml(load_yaml_fixture):
    """Load evaluator test YAML configuration."""
    return load_yaml_fixture("evaluator_test")


@pytest.fixture
def service_layer_test_yaml(load_yaml_fixture):
    """Load service layer test YAML configuration."""
    return load_yaml_fixture("service_layer_test")


@pytest.fixture
def formula_evaluation_test_yaml(load_yaml_fixture):
    """Load formula evaluation test YAML configuration."""
    return load_yaml_fixture("formula_evaluation_test")


@pytest.fixture
def syn2_sample_config_yaml(load_yaml_fixture):
    """Load syn2 sample configuration from YAML instead of hardcoded dictionary."""
    return load_yaml_fixture("syn2_sample_config")
