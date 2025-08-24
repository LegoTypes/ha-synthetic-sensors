"""YAML fixture for testing attribute formula structure preservation."""

ATTRIBUTE_FORMULA_STRUCTURE_TEST = """
version: "1.0"
global_settings:
  device_identifier: "test-device"
  variables:
    energy_grace_period_minutes: '15'
sensors:
  test_sensor:
    name: Test Sensor
    entity_id: sensor.test_entity
    formula: state
    variables:
      within_grace:
        formula: minutes_between(metadata(state, 'last_changed'), now()) < energy_grace_period_minutes
        alternate_states:
          UNAVAILABLE: false
          UNKNOWN: false
    attributes:
      # This should be preserved as formula structure, not flattened to direct reference
      grace_period_active:
        formula: within_grace
      # Test mixed attribute types
      voltage: 240  # Direct value
      computed_value:
        formula: state * 2  # Formula structure
    metadata:
      unit_of_measurement: Wh
      device_class: energy
""".strip()
