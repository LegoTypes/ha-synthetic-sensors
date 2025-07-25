"""Integration tests for Evaluator coordination with handler modules.

Tests that the main Evaluator class properly delegates to handler modules
and coordinates their interactions correctly.
"""

from unittest.mock import MagicMock, Mock, patch

from homeassistant.core import HomeAssistant
import pytest

from ha_synthetic_sensors.config_models import FormulaConfig
from ha_synthetic_sensors.evaluator import Evaluator
from ha_synthetic_sensors.evaluator_config import CircuitBreakerConfig, RetryConfig


@pytest.fixture
def evaluator(mock_hass, mock_entity_registry, mock_states):
    """Create Evaluator instance for testing."""
    return Evaluator(mock_hass)


@pytest.fixture
def sample_formula_config():
    """Create sample formula configuration."""
    return FormulaConfig(
        id="test_formula",
        name="Test Formula",
        formula="temp + humidity",
        variables={"temp": "sensor.temperature", "humidity": "sensor.humidity"},
    )


class TestEvaluatorInitialization:
    """Test Evaluator initialization and handler setup."""

    def test_evaluator_initialization(self, mock_hass, mock_entity_registry, mock_states):
        """Test that evaluator initializes with handler modules."""
        evaluator = Evaluator(mock_hass)

        assert evaluator._hass == mock_hass
        assert evaluator._dependency_handler is not None
        assert evaluator._cache_handler is not None
        assert hasattr(evaluator, "_cache_handler")
        assert hasattr(evaluator, "_dependency_parser")

    def test_evaluator_with_custom_configs(self, mock_hass, mock_entity_registry, mock_states):
        """Test evaluator initialization with custom configurations."""
        cb_config = CircuitBreakerConfig(max_fatal_errors=3)
        retry_config = RetryConfig(max_attempts=5)

        evaluator = Evaluator(mock_hass, circuit_breaker_config=cb_config, retry_config=retry_config)

        assert evaluator.get_circuit_breaker_config().max_fatal_errors == 3
        assert evaluator.get_retry_config().max_attempts == 5

    def test_evaluator_data_provider_delegation(self, mock_hass, mock_entity_registry, mock_states):
        """Test that data provider callback is properly delegated."""

        def mock_data_provider(entity_id):
            return 42.0, True

        evaluator = Evaluator(mock_hass, data_provider_callback=mock_data_provider)

        # Verify the callback is accessible through the dependency handler
        assert evaluator._data_provider_callback == mock_data_provider


class TestEvaluatorDelegation:
    """Test that Evaluator properly delegates to handler modules."""

    def test_get_formula_dependencies_delegation(self, evaluator, mock_hass, mock_entity_registry, mock_states):
        """Test that dependency extraction delegates to dependency handler."""
        with patch.object(evaluator._dependency_handler, "get_formula_dependencies") as mock_deps:
            mock_deps.return_value = {"sensor.test"}

            result = evaluator.get_formula_dependencies("sensor.test + 5")

            mock_deps.assert_called_once_with("sensor.test + 5")
            assert result == {"sensor.test"}

    def test_cache_operations_delegation(self, evaluator, mock_hass, mock_entity_registry, mock_states):
        """Test that cache operations delegate to cache handler."""
        with patch.object(evaluator._cache_handler, "clear_cache") as mock_clear:
            evaluator.clear_cache("test_formula")
            mock_clear.assert_called_once_with("test_formula")

        with patch.object(evaluator._cache_handler, "get_cache_stats") as mock_stats:
            mock_stats.return_value = {"hits": 10, "misses": 5}

            stats = evaluator.get_cache_stats()
            mock_stats.assert_called_once()
            # Check that the cache handler stats are included plus error_counts
            assert stats["hits"] == 10
            assert stats["misses"] == 5
            assert "error_counts" in stats

    def test_integration_entity_delegation(self, evaluator, mock_hass, mock_entity_registry, mock_states):
        """Test that integration entity management delegates properly."""
        entities = {"sensor.integration_1", "sensor.integration_2"}

        with patch.object(evaluator._dependency_handler, "update_integration_entities") as mock_update:
            evaluator.update_integration_entities(entities)
            mock_update.assert_called_once_with(entities)

        with patch.object(evaluator._dependency_handler, "get_integration_entities") as mock_get:
            mock_get.return_value = entities

            result = evaluator.get_integration_entities()
            mock_get.assert_called_once()
            assert result == entities


class TestEvaluationWorkflow:
    """Test the complete evaluation workflow coordination."""

    def test_evaluation_workflow_cache_hit(
        self, evaluator, sample_formula_config, mock_hass, mock_entity_registry, mock_states
    ):
        """Test evaluation workflow when cache hit occurs."""
        cached_result = {"success": True, "value": 85.0, "cached": True, "state": "ok"}

        with patch.object(evaluator._cache_handler, "check_cache") as mock_cache:
            mock_cache.return_value = cached_result

            result = evaluator.evaluate_formula(sample_formula_config)

            mock_cache.assert_called_once()
            assert result == cached_result

    def test_evaluation_workflow_cache_miss(
        self, evaluator, sample_formula_config, mock_hass, mock_entity_registry, mock_states
    ):
        """Test evaluation workflow when cache miss occurs."""
        # Mock cache miss
        with patch.object(evaluator._cache_handler, "check_cache") as mock_cache_check:
            mock_cache_check.return_value = None

            # Mock states for evaluation
            def mock_states_get(entity_id):
                if entity_id == "sensor.temperature":
                    state = Mock()
                    state.state = "25.0"
                    return state
                elif entity_id == "sensor.humidity":
                    state = Mock()
                    state.state = "60.0"
                    return state
                return None

            mock_hass.states.get.side_effect = mock_states_get

            # Mock cache storage
            with patch.object(evaluator._cache_handler, "cache_result") as mock_cache_store:
                # Create context with variable values
                context = {"temp": 25.0, "humidity": 60.0}

                result = evaluator.evaluate_formula(sample_formula_config, context)

                # Verify delegation occurred
                mock_cache_check.assert_called_once()
                mock_cache_store.assert_called_once()

                # Verify result
                assert result["success"] is True
                assert result["value"] == 85.0  # 25 + 60

    def test_evaluation_workflow_missing_dependencies(
        self, evaluator, sample_formula_config, mock_hass, mock_entity_registry, mock_states
    ):
        """Test evaluation workflow with missing dependencies."""
        with patch.object(evaluator._cache_handler, "check_cache") as mock_cache:
            mock_cache.return_value = None

            with patch.object(evaluator._dependency_handler, "extract_and_prepare_dependencies") as mock_extract:
                mock_extract.return_value = ({"missing_sensor"}, set())

                with patch.object(evaluator._dependency_handler, "check_dependencies") as mock_check_deps:
                    mock_check_deps.return_value = ({"missing_sensor"}, set(), set())  # Missing dependency

                    result = evaluator.evaluate_formula(sample_formula_config)

                    assert result["success"] is False
                    assert result["state"] == "unavailable"
                    assert "missing_sensor" in result.get("error", "")

    def test_evaluation_workflow_unavailable_dependencies(
        self, evaluator, sample_formula_config, mock_hass, mock_entity_registry, mock_states
    ):
        """Test evaluation workflow with unavailable dependencies."""
        with patch.object(evaluator._cache_handler, "check_cache") as mock_cache:
            mock_cache.return_value = None

            with patch.object(evaluator._dependency_handler, "extract_and_prepare_dependencies") as mock_extract:
                mock_extract.return_value = ({"unavailable_sensor"}, set())

                with patch.object(evaluator._dependency_handler, "check_dependencies") as mock_check_deps:
                    mock_check_deps.return_value = (set(), {"unavailable_sensor"}, set())  # Unavailable dependency

                    result = evaluator.evaluate_formula(sample_formula_config)

                    assert result["success"] is True  # State reflection - non-fatal
                    assert result["state"] == "unavailable"  # Reflects unavailable dependency
                    assert "unavailable_sensor" in result.get("unavailable_dependencies", [])

    def test_evaluation_workflow_mixed_variable_validation_negative(
        self, evaluator, mock_hass, mock_entity_registry, mock_states
    ):
        """Test evaluation workflow with mixed variable validation - negative case where A has no variables but B does."""
        # Create a formula config where A (direct entity) and B (variable) are mixed
        formula_config = FormulaConfig(
            id="test_mixed_invalid",
            name="Test Mixed Invalid",
            formula="sensor.direct_entity + variable_b",  # A is direct entity, B is variable
            variables={"variable_b": "sensor.variable_entity"},  # Only B has variable mapping
        )

        with patch.object(evaluator._cache_handler, "check_cache") as mock_cache:
            mock_cache.return_value = None

            with patch.object(evaluator._dependency_handler, "extract_and_prepare_dependencies") as mock_extract:
                # This should fail because sensor.direct_entity doesn't exist as a variable
                mock_extract.return_value = ({"sensor.direct_entity", "variable_b"}, set())

                with patch.object(evaluator._dependency_handler, "check_dependencies") as mock_check_deps:
                    # sensor.direct_entity is missing (not defined as variable or existing entity)
                    mock_check_deps.return_value = ({"sensor.direct_entity"}, set(), set())

                    result = evaluator.evaluate_formula(formula_config)

                    assert result["success"] is False
                    assert result["state"] == "unavailable"
                    assert "sensor.direct_entity" in result.get("error", "")

    def test_evaluation_workflow_global_literal_reference(self, evaluator, mock_hass, mock_entity_registry, mock_states):
        """Test evaluation workflow where A references a global literal value."""
        # Enable HA lookups for this test
        evaluator.update_allow_ha_lookups(True)

        # Create a formula config where A is a global literal and B is a variable
        formula_config = FormulaConfig(
            id="test_global_literal",
            name="Test Global Literal",
            formula="global_constant + variable_b",
            variables={
                "global_constant": 42.5,  # A is a global literal
                "variable_b": "sensor.variable_entity",  # B is a variable
            },
        )

        with patch.object(evaluator._cache_handler, "check_cache") as mock_cache:
            mock_cache.return_value = None

            with patch.object(evaluator._cache_handler, "cache_result") as mock_cache_store:
                # Provide context with resolved values
                context = {"global_constant": 42.5, "variable_b": 57.5}
                result = evaluator.evaluate_formula(formula_config, context)

                # Verify success
                assert result["success"] is True
                assert result["value"] == 100.0  # 42.5 + 57.5
                assert result["state"] == "ok"

                # Verify delegation occurred
                mock_cache.assert_called_once()
                mock_cache_store.assert_called_once()


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration with handler modules."""

    def test_circuit_breaker_skips_evaluation(
        self, evaluator, sample_formula_config, mock_hass, mock_entity_registry, mock_states
    ):
        """Test that circuit breaker skips evaluation and handler calls."""
        # Trigger circuit breaker by setting error count
        evaluator._error_handler._error_count["Test Formula"] = 10  # Above default threshold

        # Mock the dependency handler to avoid actual evaluation
        evaluator._dependency_handler = MagicMock()
        evaluator._dependency_handler.check_dependencies.return_value = (set(), set(), set())

        # Mock the cache handler
        evaluator._cache_handler = MagicMock()
        evaluator._cache_handler.check_cache.return_value = None

        # Mock the formula preprocessor
        evaluator._formula_preprocessor = MagicMock()

        # Mock the build_evaluation_context method
        evaluator._build_evaluation_context = MagicMock()

        # Attempt evaluation - should be skipped due to circuit breaker
        result = evaluator.evaluate_formula(sample_formula_config)

        # Verify result indicates skipping
        assert result["success"] is False
        assert "Skipping formula" in result["error"]

        # Verify that dependency checking was not called (circuit breaker prevented it)
        evaluator._dependency_handler.check_dependencies.assert_not_called()

    def test_circuit_breaker_reset_on_success(
        self, evaluator, sample_formula_config, mock_hass, mock_entity_registry, mock_states
    ):
        """Test that circuit breaker resets error counts on successful evaluation."""
        # Set initial error count
        evaluator._error_handler._error_count["Test Formula"] = 3

        # Mock cache miss
        with patch.object(evaluator._cache_handler, "check_cache") as mock_cache:
            mock_cache.return_value = None

            # Mock cache storage
            with patch.object(evaluator._cache_handler, "cache_result") as mock_cache_store:
                # Provide context with resolved values for successful evaluation
                context = {"temp": 20.0, "humidity": 60.0}

                # Perform successful evaluation
                result = evaluator.evaluate_formula(sample_formula_config, context)

                # Verify successful result
                assert result["success"] is True
                assert result["value"] == 80.0  # 20 + 60

                # Verify error count was reset
                assert "Test Formula" not in evaluator._error_handler._error_count

                # Verify delegation occurred
                mock_cache.assert_called_once()
                mock_cache_store.assert_called_once()


class TestConfigurationManagement:
    """Test configuration management integration."""

    def test_update_circuit_breaker_config(self, evaluator, mock_hass, mock_entity_registry, mock_states):
        """Test updating circuit breaker configuration."""
        new_config = CircuitBreakerConfig(max_fatal_errors=10)
        evaluator.update_circuit_breaker_config(new_config)

        assert evaluator.get_circuit_breaker_config().max_fatal_errors == 10

    def test_update_retry_config(self, evaluator, mock_hass, mock_entity_registry, mock_states):
        """Test updating retry configuration."""
        new_config = RetryConfig(max_attempts=8)
        evaluator.update_retry_config(new_config)

        assert evaluator.get_retry_config().max_attempts == 8

    def test_validate_formula_syntax_delegation(self, evaluator, mock_hass, mock_entity_registry, mock_states):
        """Test that formula syntax validation works."""
        # Test valid formula
        errors = evaluator.validate_formula_syntax("A + B")
        assert len(errors) == 0

        # Test invalid formula
        errors = evaluator.validate_formula_syntax("A +")
        assert len(errors) > 0


class TestErrorHandling:
    """Test error handling coordination between modules."""

    def test_dependency_validation_integration(self, evaluator, mock_hass, mock_entity_registry, mock_states):
        """Test dependency validation integration."""
        dependencies = {"sensor.test1", "sensor.test2"}

        with patch.object(evaluator._dependency_handler, "validate_dependencies") as mock_validate:
            mock_validate.return_value = {
                "valid": False,
                "missing_entities": ["sensor.test1"],
                "unavailable_entities": ["sensor.test2"],
            }

            result = evaluator.validate_dependencies(dependencies)

            mock_validate.assert_called_once_with(dependencies)
            assert result["valid"] is False
            assert "sensor.test1" in result["missing_entities"]
            assert "sensor.test2" in result["unavailable_entities"]

    def test_evaluation_context_building(self, evaluator, sample_formula_config, mock_hass, mock_entity_registry, mock_states):
        """Test that evaluation context is built correctly."""
        # Enable HA lookups for context building
        evaluator.update_allow_ha_lookups(True)

        # Mock states for context building
        def mock_states_get(entity_id):
            state = Mock()
            if entity_id == "sensor.temperature":
                state.state = "25.0"
            elif entity_id == "sensor.humidity":
                state.state = "60.0"
            return state

        mock_hass.states.get.side_effect = mock_states_get

        # Get evaluation context
        context = evaluator.get_evaluation_context(sample_formula_config)

        # Verify that variables are resolved to their actual values
        # The context building phase now properly resolves entity references
        assert "temp" in context
        assert "humidity" in context
        assert context["temp"] == 25.0  # Resolved value, not entity ID
        assert context["humidity"] == 60.0  # Resolved value, not entity ID
