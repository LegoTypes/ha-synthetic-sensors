#!/usr/bin/env python3
"""Test to compare energy vs power sensor FALLBACK behavior."""

import yaml

def test_energy_vs_power_fallback():
    """Test the difference between energy and power sensor FALLBACK logic."""
    
    print("🔍 Comparing Energy vs Power Sensor FALLBACK Logic")
    print("=" * 60)
    
    # Load the generated config
    try:
        with open('/tmp/test_solar_40_circuit_config.yaml', 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("❌ Generated config not found. Please run the generation script first.")
        return False
    
    # Find a power sensor and an energy sensor
    power_sensor = None
    energy_sensor = None
    
    for sensor_key, sensor_config in config.get('sensors', {}).items():
        if 'power' in sensor_key.lower() and 'energy' not in sensor_key.lower():
            power_sensor = (sensor_key, sensor_config)
        elif 'energy' in sensor_key.lower():
            energy_sensor = (sensor_key, sensor_config)
        
        if power_sensor and energy_sensor:
            break
    
    if not power_sensor:
        print("❌ No power sensor found")
        return False
    
    if not energy_sensor:
        print("❌ No energy sensor found")
        return False
    
    print(f"✅ Found power sensor: {power_sensor[0]}")
    print(f"✅ Found energy sensor: {energy_sensor[0]}")
    
    # Compare FALLBACK logic
    print(f"\n🔍 Power Sensor FALLBACK:")
    power_fallback = power_sensor[1].get('alternate_states', {}).get('FALLBACK', {})
    print(f"  Formula: {power_fallback.get('formula', 'None')}")
    print(f"  Variables: {list(power_sensor[1].get('variables', {}).keys())}")
    
    print(f"\n🔍 Energy Sensor FALLBACK:")
    energy_fallback = energy_sensor[1].get('alternate_states', {}).get('FALLBACK', {})
    print(f"  Formula: {energy_fallback.get('formula', 'None')}")
    print(f"  Variables: {list(energy_sensor[1].get('variables', {}).keys())}")
    
    # Check within_grace variable
    within_grace_config = energy_sensor[1].get('variables', {}).get('within_grace', {})
    print(f"\n🔍 Energy Sensor within_grace variable:")
    print(f"  Formula: {within_grace_config.get('formula', 'None')}")
    print(f"  FALLBACK: {within_grace_config.get('alternate_states', {}).get('FALLBACK', 'None')}")
    
    # Analyze the issue
    print(f"\n🔍 Analysis:")
    print(f"  Power sensors: Simple FALLBACK -> 0.0 (always works)")
    print(f"  Energy sensors: Complex FALLBACK -> depends on 'state' and 'within_grace' variables")
    print(f"  Issue: When backing entity is unavailable, 'state' becomes 'unknown'")
    print(f"  Issue: 'within_grace' variable might not be available in FALLBACK context")
    
    return True

if __name__ == "__main__":
    test_energy_vs_power_fallback()
