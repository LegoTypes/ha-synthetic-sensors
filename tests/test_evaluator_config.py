"""Tests for evaluator configuration methods."""

from ha_synthetic_sensors.evaluator import CircuitBreakerConfig, Evaluator, RetryConfig


class TestEvaluatorConfiguration:
    """Test evaluator configuration methods."""

    def test_get_circuit_breaker_config_default(self, mock_hass):
        """Test getting default circuit breaker configuration."""
        evaluator = Evaluator(mock_hass)
        config = evaluator.get_circuit_breaker_config()

        assert isinstance(config, CircuitBreakerConfig)
        assert config.max_fatal_errors == 5
        assert config.max_transitory_errors == 20
        assert config.track_transitory_errors is True
        assert config.reset_on_success is True

    def test_get_circuit_breaker_config_custom(self, mock_hass):
        """Test getting custom circuit breaker configuration."""
        custom_config = CircuitBreakerConfig(
            max_fatal_errors=10, max_transitory_errors=50, track_transitory_errors=False, reset_on_success=False
        )
        evaluator = Evaluator(mock_hass, circuit_breaker_config=custom_config)
        config = evaluator.get_circuit_breaker_config()

        assert config.max_fatal_errors == 10
        assert config.max_transitory_errors == 50
        assert config.track_transitory_errors is False
        assert config.reset_on_success is False

    def test_update_circuit_breaker_config(self, mock_hass):
        """Test updating circuit breaker configuration."""
        evaluator = Evaluator(mock_hass)

        # Verify initial config
        initial_config = evaluator.get_circuit_breaker_config()
        assert initial_config.max_fatal_errors == 5

        # Update config
        new_config = CircuitBreakerConfig(
            max_fatal_errors=15, max_transitory_errors=30, track_transitory_errors=False, reset_on_success=False
        )
        evaluator.update_circuit_breaker_config(new_config)

        # Verify updated config
        updated_config = evaluator.get_circuit_breaker_config()
        assert updated_config.max_fatal_errors == 15
        assert updated_config.max_transitory_errors == 30
        assert updated_config.track_transitory_errors is False
        assert updated_config.reset_on_success is False

    def test_get_retry_config_default(self, mock_hass):
        """Test getting default retry configuration."""
        evaluator = Evaluator(mock_hass)
        config = evaluator.get_retry_config()

        assert isinstance(config, RetryConfig)
        assert config.enabled is True
        assert config.max_attempts == 3
        assert config.backoff_seconds == 5.0
        assert config.exponential_backoff is True
        assert config.retry_on_unknown is True
        assert config.retry_on_unavailable is True

    def test_get_retry_config_custom(self, mock_hass):
        """Test getting custom retry configuration."""
        custom_config = RetryConfig(
            enabled=False,
            max_attempts=5,
            backoff_seconds=10.0,
            exponential_backoff=False,
            retry_on_unknown=False,
            retry_on_unavailable=False,
        )
        evaluator = Evaluator(mock_hass, retry_config=custom_config)
        config = evaluator.get_retry_config()

        assert config.enabled is False
        assert config.max_attempts == 5
        assert config.backoff_seconds == 10.0
        assert config.exponential_backoff is False
        assert config.retry_on_unknown is False
        assert config.retry_on_unavailable is False

    def test_update_retry_config(self, mock_hass):
        """Test updating retry configuration."""
        evaluator = Evaluator(mock_hass)

        # Verify initial config
        initial_config = evaluator.get_retry_config()
        assert initial_config.max_attempts == 3

        # Update config
        new_config = RetryConfig(
            enabled=False,
            max_attempts=7,
            backoff_seconds=15.0,
            exponential_backoff=False,
            retry_on_unknown=False,
            retry_on_unavailable=True,
        )
        evaluator.update_retry_config(new_config)

        # Verify updated config
        updated_config = evaluator.get_retry_config()
        assert updated_config.enabled is False
        assert updated_config.max_attempts == 7
        assert updated_config.backoff_seconds == 15.0
        assert updated_config.exponential_backoff is False
        assert updated_config.retry_on_unknown is False
        assert updated_config.retry_on_unavailable is True

    def test_integration_entities_management(self, mock_hass):
        """Test integration entities getter and update methods."""
        evaluator = Evaluator(mock_hass)

        # Initially empty
        assert evaluator.get_integration_entities() == set()

        # Update entities
        test_entities = {"span.meter_001", "span.efficiency_input", "span.baseline"}
        evaluator.update_integration_entities(test_entities)

        # Verify entities are stored
        assert evaluator.get_integration_entities() == test_entities

        # Update with different entities
        new_entities = {"integration.sensor_a", "integration.sensor_b"}
        evaluator.update_integration_entities(new_entities)

        # Verify entities are replaced, not merged
        assert evaluator.get_integration_entities() == new_entities

        # Clear entities
        evaluator.update_integration_entities(set())
        assert evaluator.get_integration_entities() == set()


class TestCircuitBreakerConfig:
    """Test CircuitBreakerConfig dataclass."""

    def test_circuit_breaker_config_defaults(self):
        """Test default values for CircuitBreakerConfig."""
        config = CircuitBreakerConfig()

        assert config.max_fatal_errors == 5
        assert config.max_transitory_errors == 20
        assert config.track_transitory_errors is True
        assert config.reset_on_success is True

    def test_circuit_breaker_config_custom_values(self):
        """Test custom values for CircuitBreakerConfig."""
        config = CircuitBreakerConfig(
            max_fatal_errors=10, max_transitory_errors=50, track_transitory_errors=False, reset_on_success=False
        )

        assert config.max_fatal_errors == 10
        assert config.max_transitory_errors == 50
        assert config.track_transitory_errors is False
        assert config.reset_on_success is False


class TestRetryConfig:
    """Test RetryConfig dataclass."""

    def test_retry_config_defaults(self):
        """Test default values for RetryConfig."""
        config = RetryConfig()

        assert config.enabled is True
        assert config.max_attempts == 3
        assert config.backoff_seconds == 5.0
        assert config.exponential_backoff is True
        assert config.retry_on_unknown is True
        assert config.retry_on_unavailable is True

    def test_retry_config_custom_values(self):
        """Test custom values for RetryConfig."""
        config = RetryConfig(
            enabled=False,
            max_attempts=7,
            backoff_seconds=12.5,
            exponential_backoff=False,
            retry_on_unknown=False,
            retry_on_unavailable=True,
        )

        assert config.enabled is False
        assert config.max_attempts == 7
        assert config.backoff_seconds == 12.5
        assert config.exponential_backoff is False
        assert config.retry_on_unknown is False
        assert config.retry_on_unavailable is True
