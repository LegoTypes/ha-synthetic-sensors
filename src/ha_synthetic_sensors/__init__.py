"""Home Assistant Synthetic Sensors Package.

A reusable package for creating and managing synthetic sensors in Home Assistant
integrations using formula-based calculations and YAML configuration.
"""

from .config_manager import ConfigManager
from .evaluator import Evaluator
from .integration import (
    SyntheticSensorsIntegration,
    async_reload_integration,
    async_setup_integration,
    async_unload_integration,
    get_example_config,
    get_integration,
    validate_yaml_content,
)
from .name_resolver import NameResolver
from .sensor_manager import SensorManager
from .service_layer import ServiceLayer

__version__ = "0.1.0"
__all__ = [
    "ConfigManager",
    "Evaluator",
    "NameResolver",
    "SensorManager",
    "ServiceLayer",
    "SyntheticSensorsIntegration",
    "async_reload_integration",
    "async_setup_integration",
    "async_unload_integration",
    "get_example_config",
    "get_integration",
    "validate_yaml_content",
]
