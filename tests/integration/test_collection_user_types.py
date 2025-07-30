"""Test user type support in collection patterns."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ha_synthetic_sensors import StorageManager, async_setup_synthetic_sensors
from ha_synthetic_sensors.collection_resolver import CollectionResolver
from ha_synthetic_sensors.comparison_handlers import register_user_comparison_handler
from ha_synthetic_sensors.comparison_handlers.base_handler import BaseComparisonHandler
from ha_synthetic_sensors.comparison_handlers.comparison_protocol import ComparisonTypeInfo
from ha_synthetic_sensors.constants_types import TypeCategory
from ha_synthetic_sensors.type_analyzer import OperandType


class MockEnergyValue:
    """Mock energy value with unit conversion for testing user types."""

    def __init__(self, value: float, unit: str = "W"):
        self.value = value
        self.unit = unit

    def to_watts(self) -> float:
        """Convert to watts."""
        if self.unit == "kW":
            return self.value * 1000
        if self.unit == "mW":
            return self.value / 1000
        return self.value  # Already in watts

    def __str__(self) -> str:
        return f"{self.value}{self.unit}"


class EnergyComparisonHandler(BaseComparisonHandler):
    """Test energy comparison handler for collection pattern testing."""

    def get_supported_types(self) -> set[TypeCategory]:
        """Get supported type categories."""
        return {TypeCategory.STRING}  # We handle energy strings

    def get_supported_operators(self) -> set[str]:
        """Get supported operators."""
        return {"==", "!=", "<", "<=", ">", ">="}

    def get_type_info(self) -> ComparisonTypeInfo:
        """Get type information for this comparison handler."""
        return ComparisonTypeInfo(
            type_name="energy",
            priority=5,  # Higher priority than built-in handlers
            supported_operators=self.get_supported_operators(),
            can_handle_user_types=True,
        )

    def can_handle_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Check if this handler can process the given raw operands."""
        if op not in self.get_supported_operators():
            return False

        # Handle MockEnergyValue objects directly
        if isinstance(left_raw, MockEnergyValue) or isinstance(right_raw, MockEnergyValue):
            return True

        # Handle string energy values (e.g., "50W", "2kW")
        if isinstance(left_raw, str) and isinstance(right_raw, str):
            try:
                self._parse_energy_string(left_raw)
                self._parse_energy_string(right_raw)
                return True
            except ValueError:
                return False

        # Handle mixed cases
        if (isinstance(left_raw, MockEnergyValue) and isinstance(right_raw, str)) or (
            isinstance(left_raw, str) and isinstance(right_raw, MockEnergyValue)
        ):
            try:
                if isinstance(right_raw, str):
                    self._parse_energy_string(right_raw)
                elif isinstance(left_raw, str):
                    self._parse_energy_string(left_raw)
                return True
            except ValueError:
                return False

        return False

    def _parse_energy_string(self, energy_str: str) -> MockEnergyValue:
        """Parse energy string like '50W' or '2kW' into MockEnergyValue."""
        energy_str = energy_str.strip()
        if energy_str.endswith("kW"):
            return MockEnergyValue(float(energy_str[:-2]), "kW")
        if energy_str.endswith("mW"):
            return MockEnergyValue(float(energy_str[:-2]), "mW")
        if energy_str.endswith("W"):
            return MockEnergyValue(float(energy_str[:-1]), "W")
        raise ValueError(f"Invalid energy string: {energy_str}")

    def compare_raw(self, left_raw: OperandType, right_raw: OperandType, op: str) -> bool:
        """Compare raw energy values directly."""
        if not self.can_handle_raw(left_raw, right_raw, op):
            return False

        try:
            # Convert both operands to MockEnergyValue
            left_energy = left_raw if isinstance(left_raw, MockEnergyValue) else self._parse_energy_string(left_raw)
            right_energy = right_raw if isinstance(right_raw, MockEnergyValue) else self._parse_energy_string(right_raw)

            # Convert both to watts for comparison
            left_watts = left_energy.to_watts()
            right_watts = right_energy.to_watts()

            return self._apply_operator(left_watts, right_watts, op)

        except (ValueError, TypeError):
            return False

    def _compare(self, actual_val: OperandType, expected_val: OperandType, op: str) -> bool:
        """Perform the actual comparison after type validation."""
        return self.compare_raw(actual_val, expected_val, op)


class TestCollectionUserTypes:
    """Test that collection patterns support user-defined comparison handlers."""

    @pytest.fixture
    def mock_device_entry(self):
        """Create a mock device entry for testing."""
        mock_device_entry = Mock()
        mock_device_entry.name = "Test Device"
        mock_device_entry.identifiers = {("ha_synthetic_sensors", "test_device_123")}
        return mock_device_entry

    @pytest.fixture
    def mock_device_registry(self, mock_device_entry):
        """Create a mock device registry that returns the test device."""
        mock_registry = Mock()
        mock_registry.devices = Mock()
        mock_registry.async_get_device.return_value = mock_device_entry
        return mock_registry

    @pytest.fixture
    def mock_async_add_entities(self):
        """Create a mock async_add_entities function."""
        return Mock()

    @pytest.fixture
    def energy_handler(self):
        """Create and register energy comparison handler."""
        handler = EnergyComparisonHandler()
        register_user_comparison_handler(handler)
        return handler

    def create_data_provider_callback(self, backing_data: dict[str, Any]):
        """Create a data provider callback for virtual backing entities."""

        def data_provider(entity_id: str):
            return {"value": backing_data.get(entity_id), "exists": entity_id in backing_data}

        return data_provider

    def test_user_type_handler_registration(self, energy_handler):
        """Test that user-defined handlers can be registered."""
        from ha_synthetic_sensors.comparison_handlers import get_comparison_factory

        factory = get_comparison_factory()
        handler_info = factory.get_handler_info()

        # Check that our energy handler is registered
        energy_handlers = [h for h in handler_info if h["type_name"] == "energy"]
        assert len(energy_handlers) == 1
        assert energy_handlers[0]["priority"] == 5

    def test_energy_value_comparison_direct(self, energy_handler):
        """Test direct energy value comparison outside collection context."""
        from ha_synthetic_sensors.comparison_handlers import compare_values

        # Test same unit comparison
        result = compare_values("100W", "50W", ">")
        assert result is True

        result = compare_values("100W", "150W", "<")
        assert result is True

        # Test cross-unit comparison (kW to W)
        result = compare_values("2kW", "1500W", ">")
        assert result is True

        result = compare_values("1kW", "2000W", "<")
        assert result is True

        # Test equality with unit conversion
        result = compare_values("1kW", "1000W", "==")
        assert result is True

    def test_collection_resolver_uses_user_types(
        self, energy_handler, mock_hass, mock_entity_registry, mock_states, mock_device_registry
    ):
        """Test that collection resolver now uses user-defined comparison handlers."""
        # Create a collection resolver with proper mocking
        with patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry:
            MockDeviceRegistry.return_value = mock_device_registry

            collection_resolver = CollectionResolver(mock_hass)
            # Mock the registries to avoid real HA dependencies
            collection_resolver._entity_registry = mock_entity_registry
            collection_resolver._area_registry = Mock()
            collection_resolver._device_registry = mock_device_registry

            # Create a mock entity state with energy attribute using the mock_states fixture
            mock_state = Mock()
            mock_state.attributes = {"power_consumption": "2kW"}
            mock_states["sensor.test_device"] = mock_state

            # Test attribute condition matching with energy comparison
            result = collection_resolver._entity_matches_attribute_condition(
                "sensor.test_device", "power_consumption", ">=", "1500W"
            )

            # Should return True because 2kW >= 1500W (2000W >= 1500W)
            assert result is True

            # Test with different threshold
            result = collection_resolver._entity_matches_attribute_condition(
                "sensor.test_device", "power_consumption", "<", "3kW"
            )

            # Should return True because 2kW < 3kW
            assert result is True

    def test_collection_resolver_state_comparison_user_types(
        self, energy_handler, mock_hass, mock_entity_registry, mock_states, mock_device_registry
    ):
        """Test that state comparison also works with user-defined types."""
        # Create a collection resolver with proper mocking
        with patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry:
            MockDeviceRegistry.return_value = mock_device_registry

            collection_resolver = CollectionResolver(mock_hass)
            collection_resolver._entity_registry = mock_entity_registry
            collection_resolver._area_registry = Mock()
            collection_resolver._device_registry = mock_device_registry

            # Create a mock entity state with energy value as state using mock_states
            mock_state = Mock()
            mock_state.state = "1.5kW"
            mock_states["sensor.power_meter"] = mock_state

            # Test state condition matching with energy comparison
            result = collection_resolver._entity_matches_state_condition("sensor.power_meter", ">=", "1000W")

            # Should return True because 1.5kW >= 1000W (1500W >= 1000W)
            assert result is True

            # Test with higher threshold
            result = collection_resolver._entity_matches_state_condition("sensor.power_meter", ">", "2kW")

            # Should return False because 1.5kW > 2kW is false
            assert result is False

    def test_energy_comparison_error_handling(
        self, energy_handler, mock_hass, mock_entity_registry, mock_states, mock_device_registry
    ):
        """Test error handling with malformed energy values."""
        # Create a collection resolver with proper mocking
        with patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry:
            MockDeviceRegistry.return_value = mock_device_registry

            collection_resolver = CollectionResolver(mock_hass)
            collection_resolver._entity_registry = mock_entity_registry
            collection_resolver._area_registry = Mock()
            collection_resolver._device_registry = mock_device_registry

            # Create a mock entity state with invalid energy attribute using mock_states
            mock_state = Mock()
            mock_state.attributes = {"power_consumption": "invalid_energy"}
            mock_states["sensor.test_device"] = mock_state

            # Should handle the error gracefully and return False
            result = collection_resolver._entity_matches_attribute_condition(
                "sensor.test_device", "power_consumption", ">=", "1500W"
            )

            # Should return False due to parsing error
            assert result is False

    def test_user_type_priority_over_builtin(self, energy_handler):
        """Test that user-defined handlers take priority over built-in handlers."""
        from ha_synthetic_sensors.comparison_handlers import get_comparison_factory

        factory = get_comparison_factory()

        # Energy handler should be selected for energy string comparisons
        # even though string handler could technically handle them
        result = factory.compare("100W", "50W", ">")
        assert result is True

        # This demonstrates that the energy handler processed the comparison
        # with unit awareness rather than lexicographic string comparison
        result = factory.compare("2kW", "500W", ">")
        assert result is True  # 2000W > 500W (energy comparison)

        # If this were lexicographic string comparison, "2kW" would not be > "500W"
        # since "2" < "5" lexicographically

    async def test_collection_resolver_architectural_integration_full_stack(
        self,
        energy_handler,
        mock_hass,
        mock_entity_registry,
        mock_states,
        mock_config_entry,
        mock_async_add_entities,
        mock_device_registry,
    ):
        """Test the full integration stack with user types in collection patterns."""

        # Set up backing data with energy values
        backing_data = {"sensor.power_meter_1": "2kW", "sensor.power_meter_2": "500W", "sensor.power_meter_3": "1.5kW"}

        # Create data provider for virtual backing entities
        data_provider = self.create_data_provider_callback(backing_data)

        # Create change notifier callback
        def change_notifier_callback(changed_entity_ids: set[str]) -> None:
            pass

        # Create sensor-to-backing mapping
        sensor_to_backing_mapping = {"high_power_devices": "sensor.power_meter_1"}

        # Set up storage manager with proper mocking
        with (
            patch("ha_synthetic_sensors.storage_manager.Store") as MockStore,
            patch("homeassistant.helpers.device_registry.async_get") as MockDeviceRegistry,
        ):
            # Mock setup
            mock_store = AsyncMock()
            mock_store.async_load.return_value = None
            MockStore.return_value = mock_store
            MockDeviceRegistry.return_value = mock_device_registry

            # Create storage manager
            storage_manager = StorageManager(mock_hass, "test_storage", enable_entity_listener=False)
            storage_manager._store = mock_store
            await storage_manager.async_load()

            # Create sensor set
            sensor_set_id = "test_energy_sensors"
            await storage_manager.async_create_sensor_set(
                sensor_set_id=sensor_set_id, device_identifier="test_device_123", name="Test Energy Sensors"
            )

            # Load YAML with energy collection patterns from fixture
            from pathlib import Path

            yaml_fixture_path = Path(__file__).parent.parent / "yaml_fixtures" / "integration_test_collection_user_types.yaml"
            with open(yaml_fixture_path, "r") as f:
                yaml_content = f.read()

            # Import YAML
            result = await storage_manager.async_from_yaml(yaml_content=yaml_content, sensor_set_id=sensor_set_id)
            assert result["sensors_imported"] == 1

            # Set up synthetic sensors via public API
            sensor_manager = await async_setup_synthetic_sensors(
                hass=mock_hass,
                config_entry=mock_config_entry,
                async_add_entities=mock_async_add_entities,
                storage_manager=storage_manager,
                device_identifier="test_device_123",
                data_provider_callback=data_provider,
                change_notifier=change_notifier_callback,
                sensor_to_backing_mapping=sensor_to_backing_mapping,
            )

            # Verify sensor manager was created
            assert sensor_manager is not None
            assert mock_async_add_entities.called

            # Test formula evaluation with energy comparisons
            await sensor_manager.async_update_sensors()

            # Verify results
            sensors = storage_manager.list_sensors(sensor_set_id=sensor_set_id)
            assert len(sensors) == 1

            # Clean up
            await storage_manager.async_delete_sensor_set(sensor_set_id)
