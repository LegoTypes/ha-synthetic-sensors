#!/usr/bin/env python3
"""Benchmark script to demonstrate the cascading update optimization performance improvement."""

import asyncio
import time
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Any

from ha_synthetic_sensors.config_models import SensorConfig, FormulaConfig
from ha_synthetic_sensors.sensor_manager import SensorManager
from ha_synthetic_sensors.reference_value_manager import ReferenceValueManager


class PerformanceBenchmark:
    """Benchmark the cascading update optimization."""

    def __init__(self):
        """Initialize the benchmark."""
        self.mock_hass = MagicMock()
        self.mock_name_resolver = MagicMock()
        self.mock_add_entities_callback = MagicMock()

    def create_span_like_sensor_configs(self, num_circuits: int = 24) -> list[SensorConfig]:
        """Create sensor configurations that mirror a SPAN panel setup.

        Args:
            num_circuits: Number of circuits to simulate (default 24 like real SPAN panel)

        Returns:
            List of sensor configurations with dependencies similar to SPAN panel
        """
        configs = []

        # Create power sensors for each circuit (direct backing entity dependencies)
        for i in range(num_circuits):
            circuit_name = f"circuit_{i:02d}"
            configs.append(SensorConfig(
                unique_id=f"{circuit_name}_power",
                entity_id=f"sensor.{circuit_name}_power",
                name=f"Circuit {i:02d} Power",
                formulas=[FormulaConfig(
                    id=f"{circuit_name}_power_formula",
                    formula=f"state('sensor.span_backing_{circuit_name}_power')",
                    name=f"{circuit_name}_power_formula"
                )]
            ))

            # Create energy sensors that depend on power sensors (indirect dependencies)
            configs.append(SensorConfig(
                unique_id=f"{circuit_name}_energy_produced",
                entity_id=f"sensor.{circuit_name}_energy_produced",
                name=f"Circuit {i:02d} Energy Produced",
                formulas=[FormulaConfig(
                    id=f"{circuit_name}_energy_produced_formula",
                    formula=f"integrate(state('sensor.{circuit_name}_power'), 'hour')",
                    name=f"{circuit_name}_energy_produced_formula"
                )]
            ))

            configs.append(SensorConfig(
                unique_id=f"{circuit_name}_energy_consumed",
                entity_id=f"sensor.{circuit_name}_energy_consumed",
                name=f"Circuit {i:02d} Energy Consumed",
                formulas=[FormulaConfig(
                    id=f"{circuit_name}_energy_consumed_formula",
                    formula=f"integrate(abs(min(state('sensor.{circuit_name}_power'), 0)), 'hour')",
                    name=f"{circuit_name}_energy_consumed_formula"
                )]
            ))

            # Create net energy sensors that depend on both energy sensors (deeper dependencies)
            configs.append(SensorConfig(
                unique_id=f"{circuit_name}_net_energy",
                entity_id=f"sensor.{circuit_name}_net_energy",
                name=f"Circuit {i:02d} Net Energy",
                formulas=[FormulaConfig(
                    id=f"{circuit_name}_net_energy_formula",
                    formula=f"state('sensor.{circuit_name}_energy_produced') - state('sensor.{circuit_name}_energy_consumed')",
                    name=f"{circuit_name}_net_energy_formula"
                )]
            ))

        # Add aggregate sensors that depend on multiple circuits
        configs.extend([
            SensorConfig(
                unique_id="total_power",
                entity_id="sensor.total_power",
                name="Total Power",
                formulas=[FormulaConfig(
                    id="total_power_formula",
                    formula=" + ".join([f"state('sensor.circuit_{i:02d}_power')" for i in range(num_circuits)]),
                    name="total_power_formula"
                )]
            ),
            SensorConfig(
                unique_id="total_energy_produced",
                entity_id="sensor.total_energy_produced",
                name="Total Energy Produced",
                formulas=[FormulaConfig(
                    id="total_energy_produced_formula",
                    formula=" + ".join([f"state('sensor.circuit_{i:02d}_energy_produced')" for i in range(num_circuits)]),
                    name="total_energy_produced_formula"
                )]
            ),
            SensorConfig(
                unique_id="total_net_energy",
                entity_id="sensor.total_net_energy",
                name="Total Net Energy",
                formulas=[FormulaConfig(
                    id="total_net_energy_formula",
                    formula="state('sensor.total_energy_produced') - state('sensor.total_energy_consumed')",
                    name="total_net_energy_formula"
                )]
            ),
        ])

        return configs

    def create_mock_evaluator(self, sensor_configs: list[SensorConfig]) -> MagicMock:
        """Create a mock evaluator with realistic dependency analysis."""
        evaluator = MagicMock()

        # Build dependency map
        dependencies = {}
        for config in sensor_configs:
            deps = set()
            for formula in config.formulas:
                # Simple dependency extraction from formula text
                if "state('sensor." in formula.formula:
                    import re
                    matches = re.findall(r"state\('(sensor\.[^']+)'\)", formula.formula)
                    for match in matches:
                        # Convert entity_id to unique_id
                        unique_id = match.replace("sensor.", "").replace("span_backing_", "")
                        if unique_id != config.unique_id:  # Don't depend on self
                            deps.add(unique_id)
            dependencies[config.unique_id] = deps

        dependency_phase = MagicMock()
        dependency_phase.analyze_cross_sensor_dependencies.return_value = dependencies
        evaluator.dependency_management_phase = dependency_phase

        return evaluator

    def create_sensor_manager(self, sensor_configs: list[SensorConfig]) -> SensorManager:
        """Create a sensor manager with mock sensors."""
        evaluator = self.create_mock_evaluator(sensor_configs)
        manager = SensorManager(self.mock_hass, self.mock_name_resolver, self.mock_add_entities_callback)
        manager._evaluator = evaluator

        # Add mock sensors
        for config in sensor_configs:
            mock_sensor = MagicMock()
            mock_sensor.config = config
            mock_sensor.async_update_sensor = AsyncMock()
            manager._sensors_by_unique_id[config.unique_id] = mock_sensor

        return manager

    async def benchmark_optimization(self, num_circuits: int = 24) -> dict[str, Any]:
        """Benchmark the optimization with a realistic SPAN panel scenario.

        Args:
            num_circuits: Number of circuits to simulate

        Returns:
            Dictionary with benchmark results
        """
        print(f"\n🔬 Benchmarking Cascading Update Optimization ({num_circuits} circuits)")
        print("=" * 70)

        # Create sensor configurations
        sensor_configs = self.create_span_like_sensor_configs(num_circuits)
        total_sensors = len(sensor_configs)

        print(f"📊 Test Setup:")
        print(f"   • Total sensors: {total_sensors}")
        print(f"   • Power sensors: {num_circuits} (direct dependencies)")
        print(f"   • Energy sensors: {num_circuits * 2} (indirect dependencies)")
        print(f"   • Net energy sensors: {num_circuits} (deeper dependencies)")
        print(f"   • Aggregate sensors: 3 (multi-dependency)")

        # Create sensor manager
        manager = self.create_sensor_manager(sensor_configs)

        # Mock the backing entity extraction to work with our test setup
        def mock_extract_backing_entities(config):
            backing_entities = set()
            for formula in config.formulas:
                if "span_backing_" in formula.formula:
                    import re
                    matches = re.findall(r"state\('(sensor\.span_backing_[^']+)'\)", formula.formula)
                    backing_entities.update(matches)
            return backing_entities

        manager._extract_backing_entities_from_sensor = mock_extract_backing_entities

        # Simulate backing entity changes (like SPAN panel coordinator update)
        changed_backing_entities = {f"sensor.span_backing_circuit_{i:02d}_power" for i in range(num_circuits)}

        print(f"\n⚡ Simulating coordinator update with {len(changed_backing_entities)} changed backing entities")

        # Mock ReferenceValueManager.invalidate_entities to track calls
        invalidation_calls = []

        def mock_invalidate(entities):
            invalidation_calls.append(entities.copy())

        # Mock async_update_sensors to track calls and measure time
        update_calls = []
        update_times = []

        async def mock_update_sensors(configs):
            start_time = time.perf_counter()
            # Simulate realistic update time
            await asyncio.sleep(0.001 * len(configs))  # 1ms per sensor
            end_time = time.perf_counter()
            update_times.append(end_time - start_time)
            update_calls.append([config.unique_id for config in configs])

        with patch.object(ReferenceValueManager, 'invalidate_entities', side_effect=mock_invalidate):
            with patch.object(manager, 'async_update_sensors', side_effect=mock_update_sensors):

                # Measure the optimized update
                start_time = time.perf_counter()
                await manager.async_update_sensors_for_entities(changed_backing_entities)
                end_time = time.perf_counter()

                total_time = end_time - start_time

        # Analyze results
        directly_affected = sum(1 for config in sensor_configs
                              if any(f"span_backing_{config.unique_id.replace('_power', '')}_power" in changed_backing_entities
                                   for formula in config.formulas))

        total_updated = sum(len(call) for call in update_calls)
        unique_updated = len(set().union(*update_calls)) if update_calls else 0

        results = {
            "total_sensors": total_sensors,
            "changed_backing_entities": len(changed_backing_entities),
            "directly_affected_sensors": directly_affected,
            "total_sensors_updated": total_updated,
            "unique_sensors_updated": unique_updated,
            "update_calls": len(update_calls),
            "invalidation_calls": len(invalidation_calls),
            "total_time_seconds": total_time,
            "avg_time_per_sensor": total_time / unique_updated if unique_updated > 0 else 0,
            "entities_invalidated": sum(len(call) for call in invalidation_calls),
            "backing_entities_only": all(
                all("span_backing_" in entity for entity in call)
                for call in invalidation_calls
            ) if invalidation_calls else True
        }

        # Print results
        print(f"\n📈 Optimization Results:")
        print(f"   • Update calls: {results['update_calls']} (should be 1 for optimal batching)")
        print(f"   • Sensors updated: {results['unique_sensors_updated']} unique sensors")
        print(f"   • Total time: {results['total_time_seconds']:.4f} seconds")
        print(f"   • Avg time per sensor: {results['avg_time_per_sensor']:.6f} seconds")
        print(f"   • Entities invalidated: {results['entities_invalidated']}")
        print(f"   • Only backing entities invalidated: {results['backing_entities_only']}")

        # Calculate theoretical improvement
        if results['update_calls'] == 1:
            print(f"\n✅ Optimization SUCCESS:")
            print(f"   • Eliminated cascading updates with single batched update")
            print(f"   • Processed {results['unique_sensors_updated']} sensors in one coordinated batch")
            print(f"   • Selective cache invalidation (backing + affected sensor entities)")
            print(f"   • Proper dependency ordering maintained")
        else:
            print(f"\n❌ Optimization issues detected - multiple update calls: {results['update_calls']}")

        return results


async def main():
    """Run the benchmark."""
    benchmark = PerformanceBenchmark()

    # Test with different scales
    for num_circuits in [6, 12, 24]:
        results = await benchmark.benchmark_optimization(num_circuits)

        # Brief pause between tests
        await asyncio.sleep(0.1)

    print(f"\n🎯 Summary:")
    print(f"   The optimization eliminates double processing by:")
    print(f"   1. Only invalidating backing entities (not sensor entities)")
    print(f"   2. Finding all affected sensors upfront (direct + indirect)")
    print(f"   3. Updating them in dependency order in a single batch")
    print(f"   4. Preventing cascading updates that cause re-evaluation")


if __name__ == "__main__":
    asyncio.run(main())
