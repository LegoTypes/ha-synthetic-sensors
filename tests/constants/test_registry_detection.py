"""Test to verify registry detection works correctly."""

from unittest.mock import MagicMock, Mock

from ha_synthetic_sensors.constants_entities import get_ha_entity_domains


def test_registry_detection_with_basic_mock() -> None:
    """Test that we get a helpful error when using basic MagicMock instead of proper fixtures."""
    # This simulates what happens when a test uses a basic MagicMock
    # instead of the proper mock_hass fixture
    basic_mock_hass = MagicMock()

    # This should trigger the error message but not raise an exception
    domains = get_ha_entity_domains(basic_mock_hass)

    # Should return some domains from the mock registry
    # The basic mock is permissive and returns mock objects that can be iterated
    assert isinstance(domains, frozenset)  # nosec B101


def test_registry_detection_with_proper_fixtures(
    mock_hass: Mock, mock_entity_registry: Mock, mock_states: dict[str, Mock]
) -> None:
    """Test that proper fixtures work correctly."""
    # Set up the mock hass with entity registry and states
    mock_hass.entity_registry = mock_entity_registry

    def mock_states_get(entity_id: str) -> Mock | None:
        return mock_states.get(entity_id)

    mock_hass.states.get.side_effect = mock_states_get
    mock_hass.states.entity_ids.return_value = list(mock_states.keys())

    # This should work without any error messages
    domains = get_ha_entity_domains(mock_hass)

    # Should return actual domains from the registry
    assert len(domains) > 0  # nosec B101
    assert "sensor" in domains  # nosec B101
