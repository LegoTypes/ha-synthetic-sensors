#!/usr/bin/env python3
"""Test script to verify the solar sensor grace period fix."""

import yaml
from datetime import datetime, timedelta

def test_solar_sensor_fix():
    """Test that solar sensors have the correct grace period logic."""
    
    print("🧪 Testing Solar Sensor Grace Period Fix")
    print("=" * 50)
    
    # Load the generated config
    try:
        with open('/tmp/test_solar_40_circuit_config.yaml', 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("❌ Generated config not found. Please run the generation script first.")
        return False
    
    # Find solar energy sensors
    solar_energy_sensors = []
    for sensor_key, sensor_config in config.get('sensors', {}).items():
        if 'solar' in sensor_key.lower() and 'energy' in sensor_key.lower():
            solar_energy_sensors.append((sensor_key, sensor_config))
    
    if not solar_energy_sensors:
        print("❌ No solar energy sensors found in config")
        return False
    
    print(f"✅ Found {len(solar_energy_sensors)} solar energy sensors")
    
    # Test each solar energy sensor
    all_passed = True
    for sensor_key, sensor_config in solar_energy_sensors:
        print(f"\n🔍 Testing {sensor_key}:")
        
        # Check FALLBACK formula
        fallback_formula = sensor_config.get('alternate_states', {}).get('FALLBACK', {}).get('formula', '')
        expected_fallback = "state if state != 'unknown' else (last_valid_state if within_grace else 'unknown')"
        
        if fallback_formula == expected_fallback:
            print(f"  ✅ FALLBACK formula: {fallback_formula}")
        else:
            print(f"  ❌ FALLBACK formula mismatch:")
            print(f"     Expected: {expected_fallback}")
            print(f"     Got:      {fallback_formula}")
            all_passed = False
        
        # Check within_grace formula
        within_grace_config = sensor_config.get('variables', {}).get('within_grace', {})
        within_grace_formula = within_grace_config.get('formula', '')
        expected_within_grace = "last_valid_changed != 'unknown' and minutes_between(last_valid_changed, now()) < energy_grace_period_minutes"
        
        if within_grace_formula == expected_within_grace:
            print(f"  ✅ within_grace formula: {within_grace_formula}")
        else:
            print(f"  ❌ within_grace formula mismatch:")
            print(f"     Expected: {expected_within_grace}")
            print(f"     Got:      {within_grace_formula}")
            all_passed = False
        
        # Check within_grace FALLBACK
        within_grace_fallback = within_grace_config.get('alternate_states', {}).get('FALLBACK', '')
        expected_fallback_logic = "last_valid_state is not None and last_valid_state != 'unknown'"
        
        if within_grace_fallback == expected_fallback_logic:
            print(f"  ✅ within_grace FALLBACK: {within_grace_fallback}")
        else:
            print(f"  ❌ within_grace FALLBACK mismatch:")
            print(f"     Expected: {expected_fallback_logic}")
            print(f"     Got:      {within_grace_fallback}")
            all_passed = False
    
    if all_passed:
        print(f"\n🎉 All {len(solar_energy_sensors)} solar energy sensors have correct grace period logic!")
        return True
    else:
        print(f"\n💥 Some solar energy sensors have incorrect grace period logic!")
        return False

if __name__ == "__main__":
    success = test_solar_sensor_fix()
    if not success:
        exit(1)
