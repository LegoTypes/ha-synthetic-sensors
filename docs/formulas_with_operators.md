# Formula Operators Guide

This guide provides examples of Python operators and constructs available in synthetic sensor formulas, focusing on practical
energy monitoring and power management scenarios.

## Overview

The synthetic sensor formula engine uses the `simpleeval` library, which supports a subset of Python syntax including:

- **Conditional expressions** (ternary operator)
- **Logical operators** (`and`, `or`, `not`)
- **Comparison operators** (`==`, `!=`, `<`, `>`, `<=`, `>=`)
- **Membership testing** (`in`, `not in`)
- **Mathematical operators** (all standard Python math operations)
- **Boolean values** (`True`, `False`)

## Conditional Expressions (Ternary Operator)

The ternary operator allows inline conditional logic using the syntax: `value_if_true if condition else value_if_false`

### Basic Conditional Logic

```yaml
sensors:
  # Power direction detection (1=importing, -1=exporting, 0=balanced)
  power_flow_direction:
    name: "Power Flow Direction"
    formula: "1 if grid_power > 100 else -1 if grid_power < -100 else 0"
    variables:
      grid_power: "sensor.grid_power"
    metadata:
      unit_of_measurement: "direction"
      icon: "mdi:transmission-tower"

  # Battery charge recommendation (1=charge, 0=hold, -1=discharge)
  battery_action:
    name: "Battery Action"
    formula: "1 if battery_level < 20 else -1 if battery_level > 95 else 0"
    variables:
      battery_level: "sensor.battery_level"
    metadata:
      unit_of_measurement: "action"
      icon: "mdi:battery"

  # Load status (2=high, 1=normal, 0=low)
  load_status:
    name: "Load Status"
    formula: "2 if total_load > 5000 else 1 if total_load > 2000 else 0"
    variables:
      total_load: "sensor.total_house_load"
    metadata:
      unit_of_measurement: "level"
      icon: "mdi:gauge"
```

### Nested Conditional Logic

```yaml
sensors:
  # Multi-tier energy pricing (3=peak, 2=mid, 1=off_peak)
  energy_rate_tier:
    name: "Energy Rate Tier"
    formula: "3 if usage > 2000 else 2 if usage > 1000 else 1"
    variables:
      usage: "sensor.current_power_usage"
    metadata:
      unit_of_measurement: "tier"
      icon: "mdi:currency-usd"

  # Battery status scale (4=full, 3=good, 2=low, 1=critical)
  battery_status:
    name: "Battery Status"
    formula: "1 if level < 10 else 2 if level < 25 else 3 if level < 80 else 4"
    variables:
      level: "sensor.battery_level"
    metadata:
      unit_of_measurement: "status"
      icon: "mdi:battery"

  # HVAC efficiency rating (4=excellent, 3=good, 2=fair, 1=poor)
  hvac_efficiency_rating:
    name: "HVAC Efficiency Rating"
    formula: "4 if efficiency > 90 else 3 if efficiency > 75 else 2 if efficiency > 50 else 1"
    variables:
      efficiency: "sensor.hvac_efficiency_percent"
    metadata:
      unit_of_measurement: "rating"
      icon: "mdi:air-conditioner"
```

### Conditional Calculations

```yaml
sensors:
  # Dynamic electricity pricing
  current_electricity_cost:
    name: "Current Electricity Cost"
    formula: "usage * (peak_rate if is_peak_time else off_peak_rate)"
    variables:
      usage: "sensor.current_power_usage"
      peak_rate: "input_number.peak_electricity_rate"
      off_peak_rate: "input_number.off_peak_electricity_rate"
      is_peak_time: "binary_sensor.peak_hours"
    metadata:
      unit_of_measurement: "¢/h"
      device_class: "monetary"

  # Solar charging optimization
  solar_charge_rate:
    name: "Solar Charge Rate"
    formula: "max_charge_rate if solar_excess > 2000 else normal_charge_rate if solar_excess > 500 else 0"
    variables:
      solar_excess: "sensor.solar_excess_power"
      max_charge_rate: 7200 # 7.2kW
      normal_charge_rate: 3300 # 3.3kW
    metadata:
      unit_of_measurement: "W"
      device_class: "power"
```

## Logical Operators

Logical operators combine boolean expressions and are essential for energy management decisions.

### AND Operator - All Conditions Must Be True

```yaml
sensors:
  # Optimal battery charging conditions
  optimal_charging_conditions:
    name: "Optimal Charging Conditions"
    formula: "solar_available and battery_low and not peak_hours and grid_stable"
    variables:
      solar_available: "binary_sensor.solar_producing"
      battery_low: "binary_sensor.battery_below_threshold"
      peak_hours: "binary_sensor.peak_electricity_hours"
      grid_stable: "binary_sensor.grid_connection_stable"
    metadata:
      icon: "mdi:battery-charging"

  # Safe appliance operation
  safe_to_run_appliances:
    name: "Safe Appliance Operation"
    formula: "grid_connected and voltage_stable and not overload_risk"
    variables:
      grid_connected: "binary_sensor.grid_connection"
      voltage_stable: "binary_sensor.voltage_within_range"
      overload_risk: "binary_sensor.circuit_overload_risk"
    metadata:
      icon: "mdi:home-lightning-bolt"

  # Energy storage decision
  should_store_energy:
    name: "Should Store Energy"
    formula: "excess_solar and battery_not_full and storage_efficient"
    variables:
      excess_solar: "solar_production > house_consumption + 1000"
      battery_not_full: "battery_level < 95"
      storage_efficient: "battery_temperature > 5 and battery_temperature < 35"
      solar_production: "sensor.solar_current_power"
      house_consumption: "sensor.house_current_load"
      battery_level: "sensor.battery_level"
      battery_temperature: "sensor.battery_temperature"
    metadata:
      icon: "mdi:battery-plus"
```

### OR Operator - Any Condition Can Be True

```yaml
sensors:
  # Backup power needed
  backup_power_required:
    name: "Backup Power Required"
    formula: "grid_outage or high_demand or critical_load_active or low_grid_voltage"
    variables:
      grid_outage: "binary_sensor.grid_outage"
      high_demand: "total_load > 8000"
      critical_load_active: "binary_sensor.critical_systems_running"
      low_grid_voltage: "grid_voltage < 220"
      total_load: "sensor.total_house_load"
      grid_voltage: "sensor.grid_voltage"
    metadata:
      icon: "mdi:battery-alert"

  # Energy saving opportunity
  energy_saving_opportunity:
    name: "Energy Saving Opportunity"
    formula: "high_rates or peak_demand or battery_full or solar_excess"
    variables:
      high_rates: "current_rate > 0.25"
      peak_demand: "binary_sensor.utility_peak_demand"
      battery_full: "battery_level > 90"
      solar_excess: "solar_power > house_load + 2000"
      current_rate: "sensor.current_electricity_rate"
      battery_level: "sensor.battery_level"
      solar_power: "sensor.solar_current_power"
      house_load: "sensor.house_current_load"
    metadata:
      icon: "mdi:leaf"

  # Maintenance alert
  maintenance_required:
    name: "Maintenance Required"
    formula: "inverter_fault or battery_degraded or panel_efficiency_low or grid_instability"
    variables:
      inverter_fault: "binary_sensor.inverter_fault"
      battery_degraded: "battery_health < 80"
      panel_efficiency_low: "solar_efficiency < 15"
      grid_instability: "voltage_variance > 10"
      battery_health: "sensor.battery_health_percent"
      solar_efficiency: "sensor.solar_panel_efficiency"
      voltage_variance: "sensor.grid_voltage_variance"
    metadata:
      icon: "mdi:wrench"
```

### NOT Operator - Negation

```yaml
sensors:
  # System ready for high load
  ready_for_high_load:
    name: "Ready for High Load"
    formula: "not maintenance_mode and not battery_critical and not grid_unstable"
    variables:
      maintenance_mode: "binary_sensor.system_maintenance_mode"
      battery_critical: "battery_level < 15"
      grid_unstable: "binary_sensor.grid_voltage_unstable"
      battery_level: "sensor.battery_level"
    metadata:
      icon: "mdi:check-circle"

  # Off-peak opportunities
  off_peak_operations:
    name: "Off-Peak Operations Available"
    formula: "not peak_hours and not high_demand_period and grid_stable"
    variables:
      peak_hours: "binary_sensor.peak_electricity_hours"
      high_demand_period: "binary_sensor.utility_high_demand"
      grid_stable: "not binary_sensor.grid_voltage_unstable"
    metadata:
      icon: "mdi:clock-outline"
```

### Complex Logical Combinations

```yaml
sensors:
  # Smart EV charging decision (3=fast_charge, 2=normal_charge, 1=hold, 0=stop_charge)
  ev_charging_recommendation:
    name: "EV Charging Recommendation"
    formula: |
      3 if (battery_very_low and (solar_excess or grid_very_cheap)) else
      2 if (battery_low and (solar_available or not peak_hours)) else
      0 if (battery_sufficient or (peak_hours and grid_expensive)) else
      1
    variables:
      battery_very_low: "ev_battery < 20"
      battery_low: "ev_battery < 50"
      battery_sufficient: "ev_battery > 80"
      solar_excess: "solar_power > house_load + 3000"
      solar_available: "solar_power > house_load"
      grid_very_cheap: "electricity_rate < 0.08"
      grid_expensive: "electricity_rate > 0.20"
      peak_hours: "binary_sensor.peak_electricity_hours"
      ev_battery: "sensor.ev_battery_level"
      solar_power: "sensor.solar_current_power"
      house_load: "sensor.house_current_load"
      electricity_rate: "sensor.current_electricity_rate"
          metadata:
        unit_of_measurement: "mode"
        icon: "mdi:car-electric"

  # Comprehensive energy management (4=emergency, 3=conservation, 2=optimization, 1=standard)
  energy_management_mode:
    name: "Energy Management Mode"
    formula: |
      4 if (grid_outage or battery_critical) else
      3 if (peak_hours and (high_rates or low_battery)) else
      2 if (solar_available and battery_healthy) else
      1
    variables:
      grid_outage: "binary_sensor.grid_outage"
      battery_critical: "battery_level < 10"
      peak_hours: "binary_sensor.peak_electricity_hours"
      high_rates: "electricity_rate > 0.25"
      low_battery: "battery_level < 30"
      solar_available: "solar_power > 1000"
      battery_healthy: "battery_health > 85"
      battery_level: "sensor.battery_level"
      electricity_rate: "sensor.current_electricity_rate"
      solar_power: "sensor.solar_current_power"
      battery_health: "sensor.battery_health_percent"
          metadata:
        unit_of_measurement: "mode"
        icon: "mdi:home-battery"
```

## Membership Testing with 'in' Operator

The `in` operator tests whether a value exists in a collection (list, tuple, or string).

### Range and List Testing

```yaml
sensors:
  # Voltage quality assessment (3=excellent, 2=good, 1=poor)
  voltage_status:
    name: "Voltage Status"
    formula: "3 if voltage in [238, 240, 242] else 2 if voltage in normal_range else 1"
    variables:
      voltage: "sensor.main_voltage"
      normal_range: [230, 232, 234, 236, 244, 246, 248, 250]
    metadata:
      unit_of_measurement: "quality"
      icon: "mdi:sine-wave"

  # Power level categorization (1=low, 2=medium, 3=high)
  power_category:
    name: "Power Category"
    formula: "1 if current_power in low_range else 2 if current_power in medium_range else 3"
    variables:
      current_power: "sensor.main_panel_power"
      low_range: [0, 500, 1000, 1500]
      medium_range: [2000, 2500, 3000, 3500, 4000]
    metadata:
      unit_of_measurement: "category"
      icon: "mdi:gauge"

  # Optimal charging times (1=optimal, 0=not optimal)
  optimal_charging_time:
    name: "Optimal Charging Time"
    formula: "1 if current_hour in optimal_hours else 0"
    variables:
      current_hour: "now().hour"
      optimal_hours: [1, 2, 3, 4, 5, 22, 23] # Late night/early morning
    metadata:
      unit_of_measurement: "binary"
      icon: "mdi:clock-check"
```

### State-Based Testing

```yaml
sensors:
  # System health check (1=healthy, 0=degraded)
  system_health:
    name: "System Health"
    formula: "1 if system_status_value > 75 else 0"
    variables:
      system_status_value: "sensor.overall_system_status_percent"
    metadata:
      unit_of_measurement: "binary"
      icon: "mdi:heart-pulse"

  # Alert severity level (3=critical, 2=warning, 1=info, 0=none)
  alert_level:
    name: "Alert Level"
    formula: "3 if error_count > 5 else 2 if error_count > 2 else 1 if error_count > 0 else 0"
    variables:
      error_count: "sensor.system_error_count"
    metadata:
      unit_of_measurement: "severity"
      icon: "mdi:alert"

  # Maintenance schedule (1=due, 0=not due)
  maintenance_due:
    name: "Maintenance Due"
    formula: "1 if current_month in maintenance_months else 0"
    variables:
      current_month: "now().month"
      maintenance_months: [3, 6, 9, 12] # Quarterly maintenance
    metadata:
      unit_of_measurement: "binary"
      icon: "mdi:calendar-check"
```

### Negated Membership Testing

```yaml
sensors:
  # Safe operating conditions (1=safe, 0=unsafe)
  safe_operation:
    name: "Safe Operation"
    formula: "1 if voltage not in danger_range and temperature not in extreme_temps else 0"
    variables:
      voltage: "sensor.main_voltage"
      temperature: "sensor.inverter_temperature"
      danger_range: [200, 210, 270, 280] # Dangerous voltage levels
      extreme_temps: [60, 65, 70, 75, 80] # Extreme temperatures
    metadata:
      unit_of_measurement: "binary"
      icon: "mdi:shield-check"

  # Non-peak operations (1=available, 0=unavailable)
  non_peak_opportunity:
    name: "Non-Peak Opportunity"
    formula: "1 if current_hour not in peak_hours else 0"
    variables:
      current_hour: "now().hour"
      peak_hours: [16, 17, 18, 19, 20, 21] # Peak demand hours
    metadata:
      unit_of_measurement: "binary"
      icon: "mdi:clock-outline"
```

## Boolean State Handling

Home Assistant boolean states are automatically converted to numeric values for mathematical operations.

### Boolean State Scoring

```yaml
sensors:
  # Security system effectiveness
  security_score:
    name: "Security Score"
    formula: "door_locked * 25 + alarm_armed * 35 + motion_clear * 20 + windows_closed * 20"
    variables:
      door_locked: "binary_sensor.front_door_lock" # locked=1.0, unlocked=0.0
      alarm_armed: "binary_sensor.security_system" # armed_*=1.0, disarmed=0.0
      motion_clear: "binary_sensor.motion_sensor" # clear=1.0, motion=0.0
      windows_closed: "binary_sensor.window_sensors" # closed=1.0, open=0.0
    metadata:
      unit_of_measurement: "points"
      icon: "mdi:security"

  # Energy system readiness
  energy_system_readiness:
    name: "Energy System Readiness"
    formula: "round((solar_online + battery_ready + inverter_ready + grid_connected) / 4 * 100)"
    variables:
      solar_online: "binary_sensor.solar_inverter" # online=1.0, offline=0.0
      battery_ready: "binary_sensor.battery_system" # ready=1.0, not_ready=0.0
      inverter_ready: "binary_sensor.main_inverter" # ready=1.0, fault=0.0
      grid_connected: "binary_sensor.grid_connection" # connected=1.0, disconnected=0.0
    metadata:
      unit_of_measurement: "%"
      suggested_display_precision: 0
      icon: "mdi:home-battery"

  # Load balancing readiness
  load_balance_ready:
    name: "Load Balance Ready"
    formula: "battery_available and grid_stable and not maintenance_mode and inverter_online"
    variables:
      battery_available: "binary_sensor.battery_available"
      grid_stable: "binary_sensor.grid_stable"
      maintenance_mode: "binary_sensor.maintenance_mode"
      inverter_online: "binary_sensor.inverter_status"
    metadata:
      icon: "mdi:scale-balance"
```

## Advanced Operator Combinations

### Multi-Condition Energy Management

```yaml
sensors:
  # Comprehensive load management (3=shed_non_essential, 2=optimize, 1=maintain)
  load_management_action:
    name: "Load Management Action"
    formula: |
      3 if (
        (total_load > critical_threshold) or
        (battery_low and grid_expensive) or
        (peak_demand and not solar_available)
      ) else 2 if (
        solar_excess and battery_not_full
      ) else 1
    variables:
      total_load: "sensor.total_house_load"
      critical_threshold: 9000
      battery_low: "battery_level < 25"
      grid_expensive: "electricity_rate > 0.30"
      peak_demand: "binary_sensor.utility_peak_demand"
      solar_available: "solar_power > 2000"
      solar_excess: "solar_power > house_load + 1500"
      battery_not_full: "battery_level < 90"
      battery_level: "sensor.battery_level"
      electricity_rate: "sensor.current_electricity_rate"
      solar_power: "sensor.solar_current_power"
      house_load: "sensor.house_current_load"
          metadata:
        unit_of_measurement: "action"
        icon: "mdi:home-lightning-bolt"

  # Smart appliance scheduling (3=run_now, 2=run_later, 1=postpone)
  appliance_run_recommendation:
    name: "Appliance Run Recommendation"
    formula: |
      3 if (
        solar_excess > 3000 and
        current_hour in [10, 11, 12, 13, 14] and
        not peak_hours and
        grid_stable
      ) else 2 if (
        electricity_rate < 0.15 and
        current_hour not in peak_hours_list and
        battery_level > 50
      ) else 1
    variables:
      solar_excess: "max(0, solar_power - house_load)"
      current_hour: "now().hour"
      peak_hours: "binary_sensor.peak_electricity_hours"
      peak_hours_list: [16, 17, 18, 19, 20, 21]
      grid_stable: "binary_sensor.grid_stable"
      electricity_rate: "sensor.current_electricity_rate"
      battery_level: "sensor.battery_level"
      solar_power: "sensor.solar_current_power"
      house_load: "sensor.house_current_load"
          metadata:
        unit_of_measurement: "recommendation"
        icon: "mdi:washing-machine"
```

### Performance and Efficiency Calculations

```yaml
sensors:
  # System efficiency rating (4=excellent, 3=good, 2=fair, 1=poor)
  overall_efficiency:
    name: "Overall System Efficiency"
    formula: |
      4 if (
        solar_efficiency > 18 and
        battery_efficiency > 95 and
        inverter_efficiency > 96 and
        grid_tie_efficiency > 98
      ) else 3 if (
        solar_efficiency > 15 and
        battery_efficiency > 90 and
        inverter_efficiency > 93
      ) else 2 if (
        solar_efficiency > 12 and
        battery_efficiency > 85
      ) else 1
    variables:
      solar_efficiency: "sensor.solar_panel_efficiency"
      battery_efficiency: "sensor.battery_round_trip_efficiency"
      inverter_efficiency: "sensor.inverter_efficiency"
      grid_tie_efficiency: "sensor.grid_tie_efficiency"
          metadata:
        unit_of_measurement: "rating"
        icon: "mdi:speedometer"

  # Cost optimization score
  cost_optimization_score:
    name: "Cost Optimization Score"
    formula: |
      round(
        (solar_self_consumption * 30) +
        (battery_utilization * 25) +
        (peak_avoidance * 25) +
        (grid_sell_optimization * 20)
      ) if all_systems_online else 0
    variables:
      solar_self_consumption: "min(100, (solar_used_locally / solar_produced) * 100)"
      battery_utilization: "min(100, battery_cycles_per_day * 20)"
      peak_avoidance: "100 if peak_load_avoided else 50"
      grid_sell_optimization: "min(100, grid_sell_efficiency * 100)"
      all_systems_online: "solar_online and battery_online and inverter_online"
      solar_used_locally: "sensor.solar_power_used_locally"
      solar_produced: "sensor.solar_power_produced"
      battery_cycles_per_day: "sensor.battery_daily_cycles"
      peak_load_avoided: "binary_sensor.peak_load_avoided_today"
      grid_sell_efficiency: "sensor.grid_sell_efficiency_ratio"
      solar_online: "binary_sensor.solar_system_online"
      battery_online: "binary_sensor.battery_system_online"
      inverter_online: "binary_sensor.inverter_online"
    metadata:
      unit_of_measurement: "points"
      icon: "mdi:trophy"
```

## Best Practices

### 1. Readable Conditionals

Use parentheses and line breaks for complex expressions:

```yaml
# Good: Clear and readable (1=charge, -1=discharge, 0=hold)
formula: |
  1 if (
    battery_level < 50 and
    solar_available and
    not peak_hours
  ) else -1 if (
    peak_hours and
    battery_level > 80
  ) else 0

# Avoid: Hard to read
formula: "1 if battery_level < 50 and solar_available and not peak_hours else -1 if peak_hours and battery_level > 80 else 0"
```

### 2. Meaningful Variable Names

Use descriptive variable names that explain their purpose:

```yaml
variables:
  # Good: Clear purpose
  battery_needs_charging: "battery_level < 25"
  solar_excess_available: "solar_power > house_load + 1000"
  electricity_rates_high: "current_rate > 0.25"

  # Avoid: Cryptic names
  b_low: "battery_level < 25"
  s_ex: "solar_power > house_load + 1000"
  r_high: "current_rate > 0.25"
```

### 3. Consistent Boolean Logic

Be consistent with boolean expressions:

```yaml
# Good: Consistent positive logic
formula: "solar_available and battery_ready and not maintenance_mode"

# Also good: Consistent negative logic
formula: "not (solar_unavailable or battery_not_ready or maintenance_mode)"
```

### 4. Range Validation

Use meaningful ranges for membership testing:

```yaml
variables:
  # Good: Meaningful ranges
  optimal_voltage_range: [238, 240, 242]
  acceptable_voltage_range: [230, 232, 234, 236, 244, 246, 248, 250]

  # Consider: Whether discrete values or ranges are more appropriate
  voltage_range_low: 220
  voltage_range_high: 250
  # Then use: voltage >= voltage_range_low and voltage <= voltage_range_high
```

### 5. Error Handling

Consider edge cases and provide fallbacks:

```yaml
formula: |
  1 if (
    solar_power > 0 and
    battery_level is not None and
    battery_level > 20
  ) else 0
```

This comprehensive guide covers the major Python operators and constructs available in synthetic sensor formulas, with
practical examples focused on energy monitoring and management scenarios.
