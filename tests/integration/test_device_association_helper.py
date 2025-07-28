"""Test DeviceAssociationHelper functionality."""

from unittest.mock import MagicMock, patch

import pytest

from ha_synthetic_sensors.device_association import DeviceAssociationHelper


@pytest.fixture
def mock_device_entry():
    """Create a mock device entry."""
    device = MagicMock()
    device.id = "device123"
    device.name = "Test Device"
    device.name_by_user = None
    device.manufacturer = "Test Manufacturer"
    device.model = "Test Model"
    device.sw_version = "1.0.0"
    device.hw_version = "1.0"
    device.identifiers = {("test_domain", "test_device_123")}
    device.connections = set()
    device.via_device_id = None
    device.area_id = "area123"
    device.configuration_url = None
    device.entry_type = None
    device.disabled_by = None
    return device


@pytest.fixture
def mock_entity_entry():
    """Create a mock entity entry."""
    entity = MagicMock()
    entity.entity_id = "sensor.test_sensor"
    entity.device_id = "device123"
    return entity


@pytest.fixture
def device_helper(mock_hass):
    """Create a DeviceAssociationHelper instance."""
    return DeviceAssociationHelper(mock_hass)


class TestDeviceIdentifierFromEntity:
    """Test get_device_identifier_from_entity method."""

    @patch("ha_synthetic_sensors.device_association.er.async_get")
    @patch("ha_synthetic_sensors.device_association.dr.async_get")
    def test_get_device_identifier_success(
        self,
        mock_dr_get,
        mock_er_get,
        mock_hass,
        mock_entity_registry,
        mock_states,
        device_helper,
        mock_device_entry,
        mock_entity_entry,
    ):
        """Test successful device identifier retrieval."""
        # Setup mocks
        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.return_value = mock_entity_entry
        mock_er_get.return_value = mock_entity_registry

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = mock_device_entry
        mock_dr_get.return_value = mock_device_registry

        # Test
        result = device_helper.get_device_identifier_from_entity("sensor.test_sensor")

        # Verify
        assert result == "test_domain:test_device_123"
        mock_entity_registry.async_get.assert_called_once_with("sensor.test_sensor")
        mock_device_registry.async_get.assert_called_once_with("device123")

    @patch("ha_synthetic_sensors.device_association.er.async_get")
    def test_get_device_identifier_no_entity(self, mock_er_get, mock_hass, mock_entity_registry, mock_states, device_helper):
        """Test device identifier when entity doesn't exist."""
        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.return_value = None
        mock_er_get.return_value = mock_entity_registry

        result = device_helper.get_device_identifier_from_entity("sensor.nonexistent")

        assert result is None

    @patch("ha_synthetic_sensors.device_association.er.async_get")
    def test_get_device_identifier_no_device_id(self, mock_er_get, mock_hass, mock_entity_registry, mock_states, device_helper):
        """Test device identifier when entity has no device association."""
        mock_entity_entry = MagicMock()
        mock_entity_entry.device_id = None

        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.return_value = mock_entity_entry
        mock_er_get.return_value = mock_entity_registry

        result = device_helper.get_device_identifier_from_entity("sensor.test_sensor")

        assert result is None

    @patch("ha_synthetic_sensors.device_association.er.async_get")
    @patch("ha_synthetic_sensors.device_association.dr.async_get")
    def test_get_device_identifier_fallback_to_device_id(
        self, mock_dr_get, mock_er_get, mock_hass, mock_entity_registry, mock_states, device_helper, mock_entity_entry
    ):
        """Test fallback to device ID when no identifiers exist."""
        # Device with no identifiers
        mock_device_entry = MagicMock()
        mock_device_entry.id = "device123"
        mock_device_entry.identifiers = set()

        mock_entity_registry = MagicMock()
        mock_entity_registry.async_get.return_value = mock_entity_entry
        mock_er_get.return_value = mock_entity_registry

        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = mock_device_entry
        mock_dr_get.return_value = mock_device_registry

        result = device_helper.get_device_identifier_from_entity("sensor.test_sensor")

        assert result == "device123"

    @patch("ha_synthetic_sensors.device_association.er.async_get")
    def test_get_device_identifier_exception_handling(
        self, mock_er_get, mock_hass, mock_entity_registry, mock_states, device_helper
    ):
        """Test exception handling in device identifier retrieval."""
        mock_er_get.side_effect = Exception("Registry error")

        result = device_helper.get_device_identifier_from_entity("sensor.test_sensor")

        assert result is None


class TestDeviceInfoFromIdentifier:
    """Test get_device_info_from_identifier method."""

    @patch("ha_synthetic_sensors.device_association.dr.async_get")
    def test_get_device_info_with_domain_identifier(self, mock_dr_get, device_helper, mock_device_entry):
        """Test getting device info with domain:identifier format."""
        mock_device_registry = MagicMock()
        mock_device_registry.async_get_device.return_value = mock_device_entry
        mock_dr_get.return_value = mock_device_registry

        result = device_helper.get_device_info_from_identifier("test_domain:test_device_123")

        expected = {
            "device_id": "device123",
            "name": "Test Device",
            "manufacturer": "Test Manufacturer",
            "model": "Test Model",
            "sw_version": "1.0.0",
            "hw_version": "1.0",
            "identifiers": [("test_domain", "test_device_123")],
            "connections": [],
            "via_device_id": None,
            "area_id": "area123",
            "configuration_url": None,
            "entry_type": None,
            "disabled_by": None,
        }

        assert result == expected
        mock_device_registry.async_get_device.assert_called_once_with({("test_domain", "test_device_123")})

    @patch("ha_synthetic_sensors.device_association.dr.async_get")
    def test_get_device_info_with_device_id(self, mock_dr_get, device_helper, mock_device_entry):
        """Test getting device info with device ID format."""
        mock_device_registry = MagicMock()
        mock_device_registry.async_get.return_value = mock_device_entry
        mock_dr_get.return_value = mock_device_registry

        result = device_helper.get_device_info_from_identifier("device123")

        assert result["device_id"] == "device123"
        mock_device_registry.async_get.assert_called_once_with("device123")

    @patch("ha_synthetic_sensors.device_association.dr.async_get")
    def test_get_device_info_device_not_found(self, mock_dr_get, device_helper):
        """Test getting device info when device doesn't exist."""
        mock_device_registry = MagicMock()
        mock_device_registry.async_get_device.return_value = None
        mock_dr_get.return_value = mock_device_registry

        result = device_helper.get_device_info_from_identifier("nonexistent:device")

        assert result is None

    @patch("ha_synthetic_sensors.device_association.dr.async_get")
    def test_get_device_info_exception_handling(self, mock_dr_get, device_helper):
        """Test exception handling in device info retrieval."""
        mock_dr_get.side_effect = Exception("Registry error")

        result = device_helper.get_device_info_from_identifier("test:device")

        assert result is None


class TestEntitiesForDevice:
    """Test get_entities_for_device method."""

    @patch("ha_synthetic_sensors.device_association.er.async_get")
    @patch("ha_synthetic_sensors.device_association.dr.async_get")
    @patch("ha_synthetic_sensors.device_association.er.async_entries_for_device")
    def test_get_entities_for_device_success(
        self,
        mock_entries_for_device,
        mock_dr_get,
        mock_er_get,
        mock_hass,
        mock_entity_registry,
        mock_states,
        device_helper,
        mock_device_entry,
    ):
        """Test successful entity retrieval for device."""
        # Setup mock entities
        mock_entity1 = MagicMock()
        mock_entity1.entity_id = "sensor.device_power"
        mock_entity2 = MagicMock()
        mock_entity2.entity_id = "sensor.device_energy"

        mock_entity_registry = MagicMock()
        mock_er_get.return_value = mock_entity_registry

        mock_device_registry = MagicMock()
        mock_device_registry.async_get_device.return_value = mock_device_entry
        mock_dr_get.return_value = mock_device_registry

        mock_entries_for_device.return_value = [mock_entity1, mock_entity2]

        result = device_helper.get_entities_for_device("test_domain:test_device_123")

        assert result == ["sensor.device_power", "sensor.device_energy"]
        mock_entries_for_device.assert_called_once_with(mock_entity_registry, "device123")

    @patch("ha_synthetic_sensors.device_association.dr.async_get")
    def test_get_entities_for_device_not_found(self, mock_dr_get, mock_hass, mock_entity_registry, mock_states, device_helper):
        """Test entity retrieval when device doesn't exist."""
        mock_device_registry = MagicMock()
        mock_device_registry.async_get_device.return_value = None
        mock_dr_get.return_value = mock_device_registry

        result = device_helper.get_entities_for_device("nonexistent:device")

        assert result == []

    @patch("ha_synthetic_sensors.device_association.dr.async_get")
    def test_get_entities_for_device_exception_handling(
        self, mock_dr_get, mock_hass, mock_entity_registry, mock_states, device_helper
    ):
        """Test exception handling in entity retrieval."""
        mock_dr_get.side_effect = Exception("Registry error")

        result = device_helper.get_entities_for_device("test:device")

        assert result == []


class TestDeviceValidation:
    """Test device validation methods."""

    def test_validate_device_exists_true(self, device_helper):
        """Test device validation when device exists."""
        with patch.object(device_helper, "get_device_info_from_identifier", return_value={"device_id": "123"}):
            result = device_helper.validate_device_exists("test:device")
            assert result is True

    def test_validate_device_exists_false(self, device_helper):
        """Test device validation when device doesn't exist."""
        with patch.object(device_helper, "get_device_info_from_identifier", return_value=None):
            result = device_helper.validate_device_exists("nonexistent:device")
            assert result is False

    def test_suggest_device_identifier(self, device_helper):
        """Test device identifier suggestion."""
        with patch.object(device_helper, "get_device_identifier_from_entity", return_value="suggested:device"):
            result = device_helper.suggest_device_identifier("sensor.test")
            assert result == "suggested:device"

    def test_get_device_friendly_name_with_info(self, device_helper):
        """Test getting friendly name when device info exists."""
        device_info = {"name": "Friendly Device Name"}
        with patch.object(device_helper, "get_device_info_from_identifier", return_value=device_info):
            result = device_helper.get_device_friendly_name("test:device")
            assert result == "Friendly Device Name"

    def test_get_device_friendly_name_without_info(self, device_helper):
        """Test getting friendly name when device info doesn't exist."""
        with patch.object(device_helper, "get_device_info_from_identifier", return_value=None):
            result = device_helper.get_device_friendly_name("test:device")
            assert result == "test:device"

    def test_get_device_friendly_name_none_name(self, device_helper):
        """Test getting friendly name when device name is None."""
        device_info = {"name": None}
        with patch.object(device_helper, "get_device_info_from_identifier", return_value=device_info):
            result = device_helper.get_device_friendly_name("test:device")
            assert result == "test:device"


class TestDeviceListing:
    """Test device listing and search methods."""

    @patch("ha_synthetic_sensors.device_association.dr.async_get")
    def test_list_all_devices_success(self, mock_dr_get, device_helper):
        """Test successful device listing."""
        # Create mock devices
        device1 = MagicMock()
        device1.id = "device1"
        device1.name = "Device One"
        device1.name_by_user = None
        device1.manufacturer = "Manufacturer A"
        device1.model = "Model X"
        device1.sw_version = "1.0"
        device1.hw_version = "1.0"
        device1.area_id = "area1"
        device1.disabled_by = None
        device1.identifiers = {("domain1", "device1")}

        device2 = MagicMock()
        device2.id = "device2"
        device2.name = "Device Two"
        device2.name_by_user = "Custom Name"
        device2.manufacturer = "Manufacturer B"
        device2.model = "Model Y"
        device2.sw_version = "2.0"
        device2.hw_version = "2.0"
        device2.area_id = "area2"
        device2.disabled_by = "user"
        device2.identifiers = {("domain2", "device2")}

        mock_device_registry = MagicMock()
        mock_device_registry.devices = {"device1": device1, "device2": device2}
        mock_dr_get.return_value = mock_device_registry

        result = device_helper.list_all_devices()

        assert len(result) == 2

        # Check first device
        device1_info = next(d for d in result if d["device_id"] == "device1")
        assert device1_info["device_identifier"] == "domain1:device1"
        assert device1_info["name"] == "Device One"
        assert device1_info["manufacturer"] == "Manufacturer A"
        assert device1_info["disabled"] is False

        # Check second device (with custom name and disabled)
        device2_info = next(d for d in result if d["device_id"] == "device2")
        assert device2_info["device_identifier"] == "domain2:device2"
        assert device2_info["name"] == "Custom Name"  # Uses name_by_user
        assert device2_info["manufacturer"] == "Manufacturer B"
        assert device2_info["disabled"] is True

    @patch("ha_synthetic_sensors.device_association.dr.async_get")
    def test_list_all_devices_no_identifiers(self, mock_dr_get, device_helper):
        """Test device listing when device has no identifiers."""
        device = MagicMock()
        device.id = "device1"
        device.name = "Device One"
        device.name_by_user = None
        device.manufacturer = "Manufacturer A"
        device.model = "Model X"
        device.sw_version = "1.0"
        device.hw_version = "1.0"
        device.area_id = "area1"
        device.disabled_by = None
        device.identifiers = set()  # No identifiers

        mock_device_registry = MagicMock()
        mock_device_registry.devices = {"device1": device}
        mock_dr_get.return_value = mock_device_registry

        result = device_helper.list_all_devices()

        assert len(result) == 1
        assert result[0]["device_identifier"] == "device1"  # Falls back to device ID

    @patch("ha_synthetic_sensors.device_association.dr.async_get")
    def test_list_all_devices_exception_handling(self, mock_dr_get, device_helper):
        """Test exception handling in device listing."""
        mock_dr_get.side_effect = Exception("Registry error")

        result = device_helper.list_all_devices()

        assert result == []

    def test_find_devices_by_criteria_manufacturer(self, device_helper):
        """Test finding devices by manufacturer."""
        mock_devices = [
            {"manufacturer": "Test Manufacturer", "model": "Model A", "name": "Device 1"},
            {"manufacturer": "Other Manufacturer", "model": "Model B", "name": "Device 2"},
            {"manufacturer": "Test Manufacturer", "model": "Model C", "name": "Device 3"},
        ]

        with patch.object(device_helper, "list_all_devices", return_value=mock_devices):
            result = device_helper.find_devices_by_criteria(manufacturer="Test Manufacturer")

        assert len(result) == 2
        assert all(d["manufacturer"] == "Test Manufacturer" for d in result)

    def test_find_devices_by_criteria_model(self, device_helper):
        """Test finding devices by model."""
        mock_devices = [
            {"manufacturer": "Test Manufacturer", "model": "Model A", "name": "Device 1"},
            {"manufacturer": "Other Manufacturer", "model": "Model A", "name": "Device 2"},
            {"manufacturer": "Test Manufacturer", "model": "Model C", "name": "Device 3"},
        ]

        with patch.object(device_helper, "list_all_devices", return_value=mock_devices):
            result = device_helper.find_devices_by_criteria(model="Model A")

        assert len(result) == 2
        assert all(d["model"] == "Model A" for d in result)

    def test_find_devices_by_criteria_name_pattern(self, device_helper):
        """Test finding devices by name pattern."""
        mock_devices = [
            {"manufacturer": "Test Manufacturer", "model": "Model A", "name": "Living Room Device"},
            {"manufacturer": "Other Manufacturer", "model": "Model B", "name": "Kitchen Device"},
            {"manufacturer": "Test Manufacturer", "model": "Model C", "name": "Bedroom Light"},
        ]

        with patch.object(device_helper, "list_all_devices", return_value=mock_devices):
            result = device_helper.find_devices_by_criteria(name_pattern="device")

        assert len(result) == 2
        assert all("device" in d["name"].lower() for d in result)

    def test_find_devices_by_criteria_multiple_filters(self, device_helper):
        """Test finding devices with multiple criteria."""
        mock_devices = [
            {"manufacturer": "Test Manufacturer", "model": "Model A", "name": "Living Room Device"},
            {"manufacturer": "Test Manufacturer", "model": "Model B", "name": "Kitchen Device"},
            {"manufacturer": "Other Manufacturer", "model": "Model A", "name": "Living Room Light"},
        ]

        with patch.object(device_helper, "list_all_devices", return_value=mock_devices):
            result = device_helper.find_devices_by_criteria(manufacturer="Test Manufacturer", name_pattern="living room")

        assert len(result) == 1
        assert result[0]["name"] == "Living Room Device"


class TestDeviceArea:
    """Test device area functionality."""

    @patch("homeassistant.helpers.area_registry.async_get")
    def test_get_device_area_success(self, mock_ar_get, device_helper):
        """Test successful device area retrieval."""
        # Mock device info with area
        device_info = {"area_id": "area123"}

        # Mock area entry
        mock_area_entry = MagicMock()
        mock_area_entry.name = "Living Room"

        mock_area_registry = MagicMock()
        mock_area_registry.async_get_area.return_value = mock_area_entry
        mock_ar_get.return_value = mock_area_registry

        with patch.object(device_helper, "get_device_info_from_identifier", return_value=device_info):
            result = device_helper.get_device_area("test:device")

        assert result == "Living Room"
        mock_area_registry.async_get_area.assert_called_once_with("area123")

    def test_get_device_area_no_device_info(self, device_helper):
        """Test device area when device info doesn't exist."""
        with patch.object(device_helper, "get_device_info_from_identifier", return_value=None):
            result = device_helper.get_device_area("nonexistent:device")

        assert result is None

    def test_get_device_area_no_area_id(self, device_helper):
        """Test device area when device has no area assigned."""
        device_info = {"area_id": None}

        with patch.object(device_helper, "get_device_info_from_identifier", return_value=device_info):
            result = device_helper.get_device_area("test:device")

        assert result is None

    @patch("homeassistant.helpers.area_registry.async_get")
    def test_get_device_area_area_not_found(self, mock_ar_get, device_helper):
        """Test device area when area entry doesn't exist."""
        device_info = {"area_id": "area123"}

        mock_area_registry = MagicMock()
        mock_area_registry.async_get_area.return_value = None
        mock_ar_get.return_value = mock_area_registry

        with patch.object(device_helper, "get_device_info_from_identifier", return_value=device_info):
            result = device_helper.get_device_area("test:device")

        assert result is None

    @patch("homeassistant.helpers.area_registry.async_get")
    def test_get_device_area_exception_handling(self, mock_ar_get, device_helper):
        """Test exception handling in device area retrieval."""
        device_info = {"area_id": "area123"}
        mock_ar_get.side_effect = Exception("Area registry error")

        with patch.object(device_helper, "get_device_info_from_identifier", return_value=device_info):
            result = device_helper.get_device_area("test:device")

        assert result is None


class TestDevicePatterns:
    """Test device pattern and grouping functionality."""

    def test_create_device_identifier_from_entity_pattern_power_suffix(self, device_helper):
        """Test device identifier creation from entity with power suffix."""
        result = device_helper.create_device_identifier_from_entity_pattern("sensor.living_room_power")
        assert result == "synthetic:living_room"

    def test_create_device_identifier_from_entity_pattern_energy_suffix(self, device_helper):
        """Test device identifier creation from entity with energy suffix."""
        result = device_helper.create_device_identifier_from_entity_pattern("sensor.kitchen_energy")
        assert result == "synthetic:kitchen"

    def test_create_device_identifier_from_entity_pattern_no_suffix(self, device_helper):
        """Test device identifier creation from entity with no recognized suffix."""
        result = device_helper.create_device_identifier_from_entity_pattern("sensor.custom_measurement")
        assert result == "synthetic:custom_measurement"

    def test_create_device_identifier_from_entity_pattern_multiple_suffixes(self, device_helper):
        """Test device identifier creation from entity with multiple possible suffixes."""
        result = device_helper.create_device_identifier_from_entity_pattern("sensor.device_battery_status")
        # Should remove "_status" first (last match)
        assert result == "synthetic:device_battery"

    def test_create_device_identifier_from_entity_pattern_invalid_entity_id(self, device_helper):
        """Test device identifier creation from invalid entity ID."""
        result = device_helper.create_device_identifier_from_entity_pattern("invalid_entity_id")
        assert result == "synthetic:invalid_entity_id"

    def test_group_entities_by_device_pattern_with_devices(self, device_helper):
        """Test entity grouping when entities have device associations."""
        entity_ids = ["sensor.device1_power", "sensor.device1_energy", "sensor.device2_power"]

        def mock_get_device_identifier(entity_id):
            if "device1" in entity_id:
                return "real:device1"
            elif "device2" in entity_id:
                return "real:device2"
            return None

        with patch.object(device_helper, "get_device_identifier_from_entity", side_effect=mock_get_device_identifier):
            result = device_helper.group_entities_by_device_pattern(entity_ids)

        expected = {"real:device1": ["sensor.device1_power", "sensor.device1_energy"], "real:device2": ["sensor.device2_power"]}
        assert result == expected

    def test_group_entities_by_device_pattern_without_devices(self, device_helper):
        """Test entity grouping when entities have no device associations."""
        entity_ids = ["sensor.living_room_power", "sensor.living_room_energy", "sensor.kitchen_power"]

        with patch.object(device_helper, "get_device_identifier_from_entity", return_value=None):
            result = device_helper.group_entities_by_device_pattern(entity_ids)

        expected = {
            "synthetic:living_room": ["sensor.living_room_power", "sensor.living_room_energy"],
            "synthetic:kitchen": ["sensor.kitchen_power"],
        }
        assert result == expected

    def test_group_entities_by_device_pattern_mixed(self, device_helper):
        """Test entity grouping with mix of real and synthetic device associations."""
        entity_ids = ["sensor.real_device_power", "sensor.pattern_power", "sensor.pattern_energy"]

        def mock_get_device_identifier(entity_id):
            if "real_device" in entity_id:
                return "real:device123"
            return None

        with patch.object(device_helper, "get_device_identifier_from_entity", side_effect=mock_get_device_identifier):
            result = device_helper.group_entities_by_device_pattern(entity_ids)

        expected = {
            "real:device123": ["sensor.real_device_power"],
            "synthetic:pattern": ["sensor.pattern_power", "sensor.pattern_energy"],
        }
        assert result == expected


class TestDeviceAssociationConfigValidation:
    """Test device association configuration validation."""

    def test_validate_device_association_config_valid(self, device_helper):
        """Test validation of valid device association config."""
        config = {"device_identifier": "test:device", "device_name": "Test Device", "suggested_area": "Living Room"}

        with patch.object(device_helper, "validate_device_exists", return_value=True):
            errors = device_helper.validate_device_association_config(config)

        assert errors == []

    def test_validate_device_association_config_device_not_exists(self, device_helper):
        """Test validation when device doesn't exist."""
        config = {"device_identifier": "nonexistent:device", "device_name": "Test Device"}

        with patch.object(device_helper, "validate_device_exists", return_value=False):
            errors = device_helper.validate_device_association_config(config)

        assert len(errors) == 1
        assert "Device 'nonexistent:device' does not exist" in errors[0]

    def test_validate_device_association_config_invalid_device_name(self, device_helper):
        """Test validation with invalid device name type."""
        config = {
            "device_identifier": "test:device",
            "device_name": 123,  # Should be string
            "suggested_area": "Living Room",
        }

        with patch.object(device_helper, "validate_device_exists", return_value=True):
            errors = device_helper.validate_device_association_config(config)

        assert len(errors) == 1
        assert "device_name must be a string" in errors[0]

    def test_validate_device_association_config_invalid_suggested_area(self, device_helper):
        """Test validation with invalid suggested_area type."""
        config = {
            "device_identifier": "test:device",
            "device_name": "Test Device",
            "suggested_area": 123,  # Should be string
        }

        with patch.object(device_helper, "validate_device_exists", return_value=True):
            errors = device_helper.validate_device_association_config(config)

        assert len(errors) == 1
        assert "suggested_area must be a string" in errors[0]

    def test_validate_device_association_config_multiple_errors(self, device_helper):
        """Test validation with multiple errors."""
        config = {"device_identifier": "nonexistent:device", "device_name": 123, "suggested_area": 456}

        with patch.object(device_helper, "validate_device_exists", return_value=False):
            errors = device_helper.validate_device_association_config(config)

        assert len(errors) == 3
        assert any("does not exist" in error for error in errors)
        assert any("device_name must be a string" in error for error in errors)
        assert any("suggested_area must be a string" in error for error in errors)

    def test_validate_device_association_config_no_device_identifier(self, device_helper):
        """Test validation with no device identifier."""
        config = {"device_name": "Test Device", "suggested_area": "Living Room"}

        errors = device_helper.validate_device_association_config(config)

        assert errors == []  # No device identifier is valid
