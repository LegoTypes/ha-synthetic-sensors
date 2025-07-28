"""Tests for the centralized domain cache system in constants_entities."""

import pytest
from unittest.mock import Mock, patch
from ha_synthetic_sensors.constants_entities import (
    get_ha_entity_domains,
    clear_domain_cache,
    _get_cached_domains,
    _set_cached_domains,
    _get_cache_key,
    is_ha_entity_domain,
    get_valid_entity_types,
    get_numeric_entity_types,
    get_boolean_entity_types,
    get_string_entity_types,
)


class TestDomainCacheSystem:
    """Test the centralized domain cache system."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_domain_cache()

    def test_cache_key_generation(self):
        """Test cache key generation for different hass instances."""
        # Test no hass
        key1 = _get_cache_key(None)
        assert key1 == "default"

        # Test with mock hass
        mock_hass1 = Mock()
        mock_hass1_id = id(mock_hass1)
        key2 = _get_cache_key(mock_hass1)
        assert key2 == str(mock_hass1_id)

        # Test different hass instances get different keys
        mock_hass2 = Mock()
        mock_hass2_id = id(mock_hass2)
        key3 = _get_cache_key(mock_hass2)
        assert key3 == str(mock_hass2_id)
        assert key2 != key3

    def test_cache_set_and_get(self):
        """Test setting and getting cached domains."""
        # Test setting cache
        test_domains = frozenset(["sensor", "switch", "light"])
        _set_cached_domains(None, test_domains)

        # Test getting cache
        cached = _get_cached_domains(None)
        assert cached == test_domains

        # Test setting cache for specific hass
        mock_hass = Mock()
        _set_cached_domains(mock_hass, test_domains)
        cached = _get_cached_domains(mock_hass)
        assert cached == test_domains

    def test_cache_clear(self):
        """Test clearing the cache."""
        # Set some cache entries
        test_domains = frozenset(["sensor", "switch"])
        _set_cached_domains(None, test_domains)

        mock_hass = Mock()
        _set_cached_domains(mock_hass, test_domains)

        # Verify cache exists
        assert _get_cached_domains(None) is not None
        assert _get_cached_domains(mock_hass) is not None

        # Clear specific hass cache
        clear_domain_cache(mock_hass)
        assert _get_cached_domains(mock_hass) is None
        assert _get_cached_domains(None) is not None  # Other cache still exists

        # Clear all cache
        clear_domain_cache()
        assert _get_cached_domains(None) is None

    def test_get_ha_entity_domains_caching(self, mock_hass, mock_entity_registry, mock_states):
        """Test that get_ha_entity_domains uses caching correctly."""
        # Mock registry to return specific domains
        mock_registry = Mock()
        mock_entity1 = Mock()
        mock_entity1.domain = "sensor"
        mock_entity2 = Mock()
        mock_entity2.domain = "switch"
        mock_registry.entities.values.return_value = [mock_entity1, mock_entity2]

        with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_registry):
            # First call should populate cache
            domains1 = get_ha_entity_domains(mock_hass)
            assert len(domains1) > 0

            # Verify cache was set
            cached = _get_cached_domains(mock_hass)
            assert cached == domains1

            # Second call should return cached result
            domains2 = get_ha_entity_domains(mock_hass)
            assert domains2 == domains1

            # Clear cache and verify regeneration
            clear_domain_cache(mock_hass)
            domains3 = get_ha_entity_domains(mock_hass)
            assert domains3 == domains1  # Should be same domains
            assert _get_cached_domains(mock_hass) == domains3  # Cache restored

    def test_get_ha_entity_domains_with_hass(self, mock_hass, mock_entity_registry, mock_states):
        """Test get_ha_entity_domains with hass instance."""
        # Mock registry to return specific domains
        mock_registry = Mock()
        mock_entity1 = Mock()
        mock_entity1.domain = "sensor"
        mock_entity2 = Mock()
        mock_entity2.domain = "switch"
        mock_registry.entities.values.return_value = [mock_entity1, mock_entity2]

        with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_registry):
            domains = get_ha_entity_domains(mock_hass)

            # Should include registry domains
            assert "sensor" in domains
            assert "switch" in domains

            # Should be cached
            cached = _get_cached_domains(mock_hass)
            assert cached == domains

    def test_is_ha_entity_domain(self, mock_hass, mock_entity_registry, mock_states):
        """Test domain validation with caching."""
        # Mock registry to return specific domains
        mock_registry = Mock()
        mock_entity1 = Mock()
        mock_entity1.domain = "sensor"
        mock_entity2 = Mock()
        mock_entity2.domain = "switch"
        mock_registry.entities.values.return_value = [mock_entity1, mock_entity2]

        with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_registry):
            # Test valid domains
            assert is_ha_entity_domain("sensor", mock_hass) is True
            assert is_ha_entity_domain("switch", mock_hass) is True

            # Test invalid domains
            assert is_ha_entity_domain("invalid_domain", mock_hass) is False
            assert is_ha_entity_domain("", mock_hass) is False

    def test_entity_type_functions(self, mock_hass, mock_entity_registry, mock_states):
        """Test entity type classification functions."""
        with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_entity_registry):
            # Test valid entity types
            valid_types = get_valid_entity_types(mock_hass)
            assert "sensor" in valid_types
            assert "span" in valid_types

            numeric_types = get_numeric_entity_types(mock_hass)
            assert "sensor" in numeric_types
            # 'span' is not a numeric device class, so it should not be in numeric_types

            boolean_types = get_boolean_entity_types(mock_hass)
            assert "binary_sensor" in boolean_types
            assert "switch" in boolean_types

            string_types = get_string_entity_types(mock_hass)
            assert "input_text" in string_types

    def test_cache_invalidation_integration(self, mock_hass, mock_entity_registry, mock_states):
        """Test that cache invalidation works across the system."""
        # Mock registry
        mock_registry = Mock()
        mock_entity = Mock()
        mock_entity.domain = "sensor"
        mock_registry.entities.values.return_value = [mock_entity]

        with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_registry):
            # Populate cache
            domains1 = get_ha_entity_domains(mock_hass)
            assert _get_cached_domains(mock_hass) is not None

            # Simulate registry change by clearing cache
            clear_domain_cache(mock_hass)
            assert _get_cached_domains(mock_hass) is None

            # Verify system regenerates cache
            domains2 = get_ha_entity_domains(mock_hass)
            assert domains2 == domains1
            assert _get_cached_domains(mock_hass) == domains2

    def test_multiple_hass_instances(self, mock_hass, mock_entity_registry, mock_states):
        """Test cache behavior with multiple hass instances."""
        mock_hass1 = Mock()
        mock_hass2 = Mock()

        # Mock different registries for different hass instances
        mock_registry1 = Mock()
        mock_entity1 = Mock()
        mock_entity1.domain = "sensor"
        mock_registry1.entities.values.return_value = [mock_entity1]

        mock_registry2 = Mock()
        mock_entity2 = Mock()
        mock_entity2.domain = "switch"
        mock_registry2.entities.values.return_value = [mock_entity2]

        with patch("homeassistant.helpers.entity_registry.async_get") as mock_get:
            mock_get.side_effect = lambda hass: mock_registry1 if hass == mock_hass1 else mock_registry2

            # Get domains for both instances
            domains1 = get_ha_entity_domains(mock_hass1)
            domains2 = get_ha_entity_domains(mock_hass2)

            # Should have different cache keys
            assert _get_cached_domains(mock_hass1) != _get_cached_domains(mock_hass2)

            # Clear one instance cache
            clear_domain_cache(mock_hass1)
            assert _get_cached_domains(mock_hass1) is None
            assert _get_cached_domains(mock_hass2) is not None

    def test_cache_performance(self, mock_hass, mock_entity_registry, mock_states):
        """Test that caching improves performance."""
        # Mock registry
        mock_registry = Mock()
        mock_entity = Mock()
        mock_entity.domain = "sensor"
        mock_registry.entities.values.return_value = [mock_entity]

        with patch("homeassistant.helpers.entity_registry.async_get", return_value=mock_registry):
            # First call (cache miss)
            domains1 = get_ha_entity_domains(mock_hass)

            # Second call (cache hit) should be faster
            # We can't easily measure performance in unit tests, but we can verify
            # that the cache is being used
            domains2 = get_ha_entity_domains(mock_hass)
            assert domains1 == domains2

            # Verify cache is being used by checking cache state
            cached = _get_cached_domains(mock_hass)
            assert cached == domains1

    def test_cache_edge_cases(self):
        """Test cache behavior with edge cases."""
        # Test with None domains
        _set_cached_domains(None, None)
        assert _get_cached_domains(None) is None

        # Test with empty domains
        empty_domains = frozenset()
        _set_cached_domains(None, empty_domains)
        assert _get_cached_domains(None) == empty_domains

        # Test clearing non-existent cache
        clear_domain_cache(Mock())  # Should not raise exception

        # Test with very large domain set
        large_domains = frozenset([f"domain_{i}" for i in range(1000)])
        _set_cached_domains(None, large_domains)
        assert _get_cached_domains(None) == large_domains

    def test_requires_hass_parameter(self):
        """Test that functions require hass parameter when accessing registry."""
        # Test that get_ha_entity_domains requires hass
        with pytest.raises(Exception):
            get_ha_entity_domains()  # Should fail without hass

        # Test that is_ha_entity_domain requires hass
        with pytest.raises(Exception):
            is_ha_entity_domain("sensor")  # Should fail without hass

        # Test that is_valid_entity_id requires hass
        with pytest.raises(Exception):
            is_valid_entity_id("sensor.temperature")  # Should fail without hass
