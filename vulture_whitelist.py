# Vulture whitelist for ha-synthetic-sensors
# This file tells vulture to ignore these items that appear unused
# but are actually used (e.g., by HA framework, public API, etc.)

# Home Assistant entity lifecycle methods (called by HA framework)
async_will_remove_from_hass
async_update

# Public API exception classes that external consumers may use
EmptyCollectionError
SensorCreationError
IntegrationTeardownError
CacheInvalidationError
InvalidOperatorError

# Cache metrics attributes used in monitoring/debugging
timestamp
total_entries
dependency_entries
misses
evictions
enable_metrics
_current_cycle_id
_cycle_cache

# Public API methods for extensibility
register_user_handler
register_handler_type
get_all_handlers
clear_handlers

# Service layer public API
async_unload_services
get_last_evaluation_result
get_last_validation_result
get_last_sensor_info

# YAML operations API
async_load_yaml_file
validate_raw_yaml_structure
config_to_yaml

# Storage manager public API
async_export_yaml
async_clear_all_data
get_storage_stats
has_data

# Cross-sensor reference management API
get_entity_id_for_sensor_key
get_sensor_key_for_entity_id
get_all_entity_mappings
has_cross_sensor_references
is_registration_pending
is_registration_complete
are_all_registrations_complete

# Device association API
get_entities_for_device
suggest_device_identifier
get_device_friendly_name
find_devices_by_criteria
get_device_area

# Metadata and validation API
get_attribute_metadata
validate_metadata
extract_ha_sensor_properties

# Evaluation API
validate_formula_syntax
get_evaluation_context

# Constants that are part of public API
ALL_KNOWN_METADATA_PROPERTIES
DATA_KEY_SENSOR_SETS
DATA_KEY_GLOBAL_SETTINGS
VALIDATION_RESULT_IS_VALID
VALIDATION_RESULT_ERRORS
ALL_NON_NUMERIC_DEVICE_CLASSES
DEFAULT_DOMAIN
DeviceClassType
StateClassType

# Protocol attributes and methods (used for type checking and extensibility)
priority
supported_operators
can_handle_user_types
can_handle_user_type
get_ordered_handlers

# Dataclass attributes used during object construction
attribute
extra_attributes

# Internal APIs that may be used by advanced consumers
_find_entities_in_areas
_entity_matches_device_class_filter
get_entities_matching_patterns
_is_boolean_like
evaluate_condition
get_sensor_config
load_from_file
get_sensor_by_unique_id
