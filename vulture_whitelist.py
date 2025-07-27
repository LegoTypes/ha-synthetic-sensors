# Vulture whitelist for ha-synthetic-sensors
# This file tells vulture to ignore these items that appear unused
# but are actually used (e.g., by HA framework, public API, etc.)

# Home Assistant entity lifecycle methods (called by HA framework)
async_will_remove_from_hass = None
async_update = None

# Public API exception classes that external consumers may use
EmptyCollectionError = None
SensorCreationError = None
IntegrationTeardownError = None
CacheInvalidationError = None
InvalidOperatorError = None

# Cache metrics attributes used in monitoring/debugging
timestamp = None
total_entries = None
dependency_entries = None
misses = None
evictions = None
enable_metrics = None
_current_cycle_id = None
_cycle_cache = None

# Public API methods for extensibility
register_user_handler = None
register_handler_type = None
get_all_handlers = None
clear_handlers = None

# Service layer public API
async_unload_services = None
get_last_evaluation_result = None
get_last_validation_result = None
get_last_sensor_info = None

# YAML operations API
async_load_yaml_file = None
validate_raw_yaml_structure = None
config_to_yaml = None

# Storage manager public API
async_export_yaml = None
async_clear_all_data = None
get_storage_stats = None
has_data = None

# Cross-sensor reference management API
get_entity_id_for_sensor_key = None
get_sensor_key_for_entity_id = None
get_all_entity_mappings = None
has_cross_sensor_references = None
is_registration_pending = None
is_registration_complete = None
are_all_registrations_complete = None

# Device association API
get_entities_for_device = None
suggest_device_identifier = None
get_device_friendly_name = None
find_devices_by_criteria = None
get_device_area = None

# Metadata and validation API
get_attribute_metadata = None
validate_metadata = None
extract_ha_sensor_properties = None

# Evaluation API
validate_formula_syntax = None
get_evaluation_context = None

# Constants that are part of public API
ALL_KNOWN_METADATA_PROPERTIES = None
DATA_KEY_SENSOR_SETS = None
DATA_KEY_GLOBAL_SETTINGS = None
VALIDATION_RESULT_IS_VALID = None
VALIDATION_RESULT_ERRORS = None
ALL_NON_NUMERIC_DEVICE_CLASSES = None
DEFAULT_DOMAIN = None
DeviceClassType = None
StateClassType = None

# Protocol attributes and methods (used for type checking and extensibility)
priority = None
supported_operators = None
can_handle_user_types = None
can_handle_user_type = None
get_ordered_handlers = None

# Dataclass attributes used during object construction
attribute = None
extra_attributes = None

# Internal APIs that may be used by advanced consumers
_find_entities_in_areas = None
_entity_matches_device_class_filter = None
get_entities_matching_patterns = None
_is_boolean_like = None
evaluate_condition = None
get_sensor_config = None
load_from_file = None
get_sensor_by_unique_id = None
