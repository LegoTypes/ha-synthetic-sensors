"""Test dependency isolation for span panel sensors."""

import pytest
from ha_synthetic_sensors.formula_ast_analysis_service import FormulaASTAnalysisService
from ha_synthetic_sensors.evaluator_phases.dependency_management.dependency_extractor import DependencyExtractor
from ha_synthetic_sensors.config_models import FormulaConfig, ComputedVariable


def test_power_sensor_dependencies():
    """Test that power sensors have correct minimal dependencies."""
    ast_service = FormulaASTAnalysisService()
    extractor = DependencyExtractor()
    extractor._ast_service = ast_service  # Set the AST service directly

    # Power sensor configuration (like spa_power)
    power_config = FormulaConfig(
        id="spa_power", formula="state", name="Spa Power", metadata={"unit_of_measurement": "W", "device_class": "power"}
    )

    # Extract dependencies using the manage method
    context = {}  # Empty context for testing
    dependencies = extractor.manage("extract", context, config=power_config)
    print(f"Power sensor dependencies: {dependencies}")

    # Should have no dependencies (state is handled by state resolver)
    assert len(dependencies) == 0, f"Power sensor should have no dependencies, got: {dependencies}"


def test_energy_sensor_dependencies():
    """Test that energy sensors have correct computed variable dependencies."""
    ast_service = FormulaASTAnalysisService()
    extractor = DependencyExtractor()
    extractor._ast_service = ast_service

    # Energy sensor configuration (with computed variables)
    energy_config = FormulaConfig(
        id="feed_through_produced_energy",
        formula="last_valid_state if is_within_grace_period else 'unknown'",
        name="Feed Through Produced Energy",
        variables={
            "last_valid_state": ComputedVariable(formula="metadata(state, 'last_valid_state')"),
            "last_valid_changed": ComputedVariable(formula="metadata(state, 'last_valid_changed')"),
            "panel_status": ComputedVariable(formula="binary_sensor.panel_status"),
            "panel_offline_minutes": ComputedVariable(
                formula="minutes_between(metadata('binary_sensor.panel_status', 'last_changed'), utc_now()) if not panel_status else 0"
            ),
            "is_within_grace_period": ComputedVariable(
                formula="last_valid_state is not None and last_valid_state != 'unknown' and last_valid_changed != 'unknown' and not panel_status and panel_offline_minutes < energy_grace_period_minutes"
            ),
            "energy_grace_period_minutes": 15.0,
        },
        metadata={"unit_of_measurement": "kWh", "device_class": "energy"},
    )

    # Extract dependencies using the manage method
    context = {}  # Empty context for testing
    dependencies = extractor.manage("extract", context, config=energy_config)
    print(f"Energy sensor dependencies: {dependencies}")

    # Should have dependencies from the formula and computed variables
    assert "last_valid_state" in dependencies
    assert "is_within_grace_period" in dependencies
    # But NOT 'state' as that's handled by state resolver
    assert "state" not in dependencies


def test_dependency_isolation_between_sensors():
    """Test that dependencies are isolated between different sensor configurations."""
    ast_service = FormulaASTAnalysisService()
    extractor = DependencyExtractor()
    extractor._ast_service = ast_service

    # First: Power sensor
    power_config = FormulaConfig(id="spa_power", formula="state", name="Spa Power")
    context = {}  # Empty context for testing
    power_deps = extractor.manage("extract", context, config=power_config)

    # Second: Energy sensor with computed variables
    energy_config = FormulaConfig(
        id="feed_through_produced_energy",
        formula="last_valid_state if is_within_grace_period else 'unknown'",
        name="Feed Through Produced Energy",
        variables={
            "last_valid_state": ComputedVariable(formula="metadata(state, 'last_valid_state')"),
            "is_within_grace_period": ComputedVariable(formula="panel_offline_minutes < 15"),
            "panel_offline_minutes": ComputedVariable(
                formula="minutes_between(metadata('binary_sensor.panel_status', 'last_changed'), utc_now())"
            ),
        },
    )
    energy_deps = extractor.manage("extract", context, config=energy_config)

    # Third: Another power sensor
    another_power_config = FormulaConfig(id="furnace_power", formula="state", name="Furnace Power")
    another_power_deps = extractor.manage("extract", context, config=another_power_config)

    print(f"Spa Power dependencies: {power_deps}")
    print(f"Energy sensor dependencies: {energy_deps}")
    print(f"Furnace Power dependencies: {another_power_deps}")

    # Verify isolation
    assert power_deps == another_power_deps, "Power sensors should have same dependencies"
    assert len(power_deps) == 0, "Power sensors should have no dependencies"
    assert len(energy_deps) > 0, "Energy sensor should have dependencies"

    # Energy dependencies should not leak to power sensors
    assert "last_valid_state" not in power_deps
    assert "panel_offline_minutes" not in power_deps
    assert "is_within_grace_period" not in power_deps


def test_metadata_function_with_state_token():
    """Test that metadata functions with state token are handled correctly."""
    ast_service = FormulaASTAnalysisService()

    # Test various metadata uses with state
    formulas = ["metadata(state, 'last_changed')", "metadata(state, 'last_valid_state')", "metadata(state, 'friendly_name')"]

    for formula in formulas:
        analysis = ast_service.get_formula_analysis(formula)
        print(f"Formula: {formula}")
        print(f"  Dependencies: {analysis.dependencies}")
        assert "state" not in analysis.dependencies, f"'state' should not be a dependency in {formula}"
        assert analysis.has_state_token is True, f"Should detect state token in {formula}"


if __name__ == "__main__":
    print("Testing span panel dependency isolation...")
    print("=" * 60)
    test_power_sensor_dependencies()
    print("=" * 60)
    test_energy_sensor_dependencies()
    print("=" * 60)
    test_dependency_isolation_between_sensors()
    print("=" * 60)
    test_metadata_function_with_state_token()
    print("=" * 60)
    print("All tests passed!")
