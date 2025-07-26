# Future Extension Architecture for Type Analyzer

## Overview

This document outlines the planned extension architecture to replace the current hardcoded metadata extraction with a
configurable, plugin-based system.

## Current State (Temporary)

The type analyzer currently uses hardcoded Home Assistant-specific metadata extraction:

```python
# Current temporary approach in type_analyzer.py lines 175-185
DEFAULT_HA_METADATA_FIELDS = {
    "device_class": "device_class",
    "unit_of_measurement": "unit_of_measurement",
    "entity_category": "entity_category",
    "state_class": "state_class",
    "synthetic_sensor_type": "type",
}
```

**This is a placeholder that will be replaced with the configurable extension system.**

## Future Architecture Vision

### 1. YAML-Based Extension Configuration

Extensions will be configured in YAML files with global extension sections:

```yaml
version: "1.0"

# Global extension configuration
extensions:
  metadata_providers:
    - name: "ha_entity_provider"
      module: "ha_synthetic_sensors.providers.ha_metadata"
      class: "HAEntityMetadataProvider"
      priority: 100
      config:
        field_mappings:
          device_class: "device_class"
          unit_of_measurement: "unit_of_measurement"
          entity_category: "entity_category"
          state_class: "state_class"
          synthetic_sensor_type: "type"

    - name: "custom_device_provider"
      module: "my_integration.metadata_providers"
      class: "CustomDeviceMetadataProvider"
      priority: 90
      config:
        api_endpoint: "https://device-api.example.com/metadata"
        field_mappings:
          power_rating: "max_power"
          efficiency: "device_efficiency"

  type_resolvers:
    - name: "energy_resolver"
      module: "energy_types.resolvers"
      class: "EnergyTypeResolver"
      priority: 100

    - name: "power_resolver"
      module: "power_types.resolvers"
      class: "PowerTypeResolver"
      priority: 90

sensors:
  # Regular sensor definitions...
```

### 2. Protocol-Based Extension Interface

Extensions will implement well-defined protocols:

```python
@runtime_checkable
class MetadataProviderExtension(Protocol):
    """Protocol for pluggable metadata providers."""

    def get_name(self) -> str:
        """Get the provider name for registration."""

    def get_priority(self) -> int:
        """Get provider priority (higher = runs first)."""

    def can_provide_metadata(self, value: OperandType) -> bool:
        """Check if this provider can extract metadata from the value."""

    def extract_metadata(self, value: OperandType) -> MetadataDict:
        """Extract metadata from the value."""

    def get_field_mappings(self) -> dict[str, str]:
        """Get field mapping configuration for this provider."""

@runtime_checkable
class TypeResolverExtension(Protocol):
    """Protocol for pluggable type resolvers."""

    def get_name(self) -> str:
        """Get the resolver name for registration."""

    def get_priority(self) -> int:
        """Get resolver priority (higher = runs first)."""

    def can_identify_from_metadata(self, metadata: MetadataDict) -> bool:
        """Check if metadata indicates this user type."""

    def is_user_type_instance(self, value: OperandType) -> bool:
        """Type guard to check if a value is an instance of this user type."""

    def get_type_name(self) -> str:
        """Get the type name this resolver handles."""
```

### 3. Dynamic Extension Registry

A registry system will manage extensions:

```python
class ExtensionRegistry:
    """Registry for dynamically loaded extensions."""

    def __init__(self):
        self.metadata_providers: list[MetadataProviderExtension] = []
        self.type_resolvers: list[TypeResolverExtension] = []

    def register_metadata_provider(self, provider: MetadataProviderExtension) -> None:
        """Register a metadata provider with priority ordering."""
        self.metadata_providers.append(provider)
        self.metadata_providers.sort(key=lambda p: p.get_priority(), reverse=True)

    def register_type_resolver(self, resolver: TypeResolverExtension) -> None:
        """Register a type resolver with priority ordering."""
        self.type_resolvers.append(resolver)
        self.type_resolvers.sort(key=lambda r: r.get_priority(), reverse=True)

    def load_extensions_from_yaml(self, extensions_config: dict) -> None:
        """Dynamically load extensions from YAML configuration."""
        # Load metadata providers
        for provider_config in extensions_config.get("metadata_providers", []):
            module = importlib.import_module(provider_config["module"])
            provider_class = getattr(module, provider_config["class"])
            provider = provider_class(provider_config.get("config", {}))
            self.register_metadata_provider(provider)

        # Load type resolvers
        for resolver_config in extensions_config.get("type_resolvers", []):
            module = importlib.import_module(resolver_config["module"])
            resolver_class = getattr(module, resolver_config["class"])
            resolver = resolver_class(resolver_config.get("config", {}))
            self.register_type_resolver(resolver)
```

### 4. Updated MetadataExtractor Architecture

The MetadataExtractor will be refactored to use the extension registry:

```python
class MetadataExtractor:
    """Handles metadata extraction using configurable extensions."""

    def __init__(self, extension_registry: ExtensionRegistry):
        self.extension_registry = extension_registry

    def extract_all_metadata(self, value: OperandType) -> MetadataDict:
        """Extract metadata using registered providers."""
        metadata: MetadataDict = {}

        # Check if it's a UserType (highest priority)
        if isinstance(value, UserType):
            metadata.update(value.get_metadata())
            metadata["type"] = value.get_type_name()
            return metadata

        # Skip metadata extraction for basic built-in types
        if isinstance(value, BUILTIN_VALUE_TYPES + (tuple, type(None))):
            return metadata

        # Use registered metadata providers in priority order
        for provider in self.extension_registry.metadata_providers:
            if provider.can_provide_metadata(value):
                try:
                    provider_metadata = provider.extract_metadata(value)
                    metadata.update(provider_metadata)
                except Exception as e:
                    _LOGGER.warning("Metadata provider %s failed: %s", provider.get_name(), e)

        return metadata
```

### 5. Example Extension Implementations

#### Home Assistant Metadata Provider

```python
class HAEntityMetadataProvider:
    """Home Assistant entity metadata provider."""

    def __init__(self, config: dict):
        self.field_mappings = config.get("field_mappings", DEFAULT_HA_METADATA_FIELDS)
        self.priority = config.get("priority", 100)

    def get_name(self) -> str:
        return "ha_entity_provider"

    def get_priority(self) -> int:
        return self.priority

    def can_provide_metadata(self, value: OperandType) -> bool:
        return isinstance(value, AttributeProvider)

    def extract_metadata(self, value: OperandType) -> MetadataDict:
        if not isinstance(value, AttributeProvider):
            return {}

        attrs = value.attributes
        extracted_metadata = {}

        for metadata_key, attr_key in self.field_mappings.items():
            if attr_key in attrs and attrs[attr_key] is not None:
                if metadata_key == "synthetic_sensor_type":
                    extracted_metadata["type"] = attrs[attr_key]
                else:
                    extracted_metadata[metadata_key] = attrs[attr_key]

        return extracted_metadata

    def get_field_mappings(self) -> dict[str, str]:
        return self.field_mappings
```

#### Custom Device API Metadata Provider

```python
class CustomDeviceMetadataProvider:
    """Custom device API metadata provider."""

    def __init__(self, config: dict):
        self.api_endpoint = config.get("api_endpoint")
        self.field_mappings = config.get("field_mappings", {})
        self.priority = config.get("priority", 50)

    def get_name(self) -> str:
        return "custom_device_provider"

    def get_priority(self) -> int:
        return self.priority

    def can_provide_metadata(self, value: OperandType) -> bool:
        # Check if value has device-specific attributes
        return hasattr(value, "device_id") and hasattr(value, "model")

    def extract_metadata(self, value: OperandType) -> MetadataDict:
        if not self.can_provide_metadata(value):
            return {}

        # Fetch metadata from device API
        device_metadata = self._fetch_device_metadata(value.device_id)

        # Map API fields to metadata fields
        extracted_metadata = {}
        for metadata_key, api_key in self.field_mappings.items():
            if api_key in device_metadata:
                extracted_metadata[metadata_key] = device_metadata[api_key]

        return extracted_metadata

    def _fetch_device_metadata(self, device_id: str) -> dict:
        # Implementation to fetch from API
        pass
```

## Migration Path

### Phase 1: Current State (Implemented)

- Add configuration options
- Support for user-defined providers

### Phase 5: Full Plugin System

1. **Configurability**: Users can define custom metadata extraction rules

2. **Extensibility**: New metadata providers can be added without core changes
3. **Platform Independence**: Core type analyzer is no longer HA-specific

4. **Performance**: Providers only run when they can handle the value type

The migration will maintain full backward compatibility:

- Current YAML files will continue to work unchanged
- Default HA metadata extraction will be preserved
- Gradual migration path for existing integrations

- **Current**: Hardcoded HA metadata extraction with configurable field mappings
- **Next**: Extension protocol definitions and registry implementation
- **Future**: Dynamic loading and user-defined provider support

This architecture aligns with the comparison handler design document's vision for a plugin-based, extensible system while
maintaining the reliability and performance characteristics required for production use.
