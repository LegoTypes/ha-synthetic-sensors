"""Tests for the Pre-Evaluation Processing Phase."""

import pytest
from unittest.mock import Mock, MagicMock

from ha_synthetic_sensors.config_models import FormulaConfig, SensorConfig
from ha_synthetic_sensors.evaluator_phases.pre_evaluation import PreEvaluationPhase
from ha_synthetic_sensors.evaluator_results import EvaluatorResults
from ha_synthetic_sensors.exceptions import BackingEntityResolutionError, SensorMappingError


class TestPreEvaluationPhase:
    """Test the Pre-Evaluation Processing Phase."""

    @pytest.fixture
    def phase(self) -> PreEvaluationPhase:
        """Create a pre-evaluation phase instance."""
        return PreEvaluationPhase()

    @pytest.fixture
    def mock_dependencies(self) -> dict:
        """Create mock dependencies for the phase."""
        return {
            "hass": Mock(),
            "data_provider_callback": Mock(),
            "dependency_handler": Mock(),
            "cache_handler": Mock(),
            "error_handler": Mock(),
            "sensor_to_backing_mapping": {},
            "allow_ha_lookups": False,
            "variable_resolution_phase": Mock(),
            "dependency_management_phase": Mock(),
            "context_building_phase": Mock(),
        }

    @pytest.fixture
    def basic_config(self) -> FormulaConfig:
        """Create a basic formula configuration."""
        return FormulaConfig(
            id="test_sensor",  # Match the sensor unique_id to avoid being treated as attribute
            name="Test Formula",
            formula="state * 2",
            variables={},
        )

    @pytest.fixture
    def basic_sensor_config(self) -> SensorConfig:
        """Create a basic sensor configuration."""
        return SensorConfig(
            unique_id="test_sensor",
            entity_id="sensor.test_sensor",
            name="Test Sensor",
            formulas=[
                FormulaConfig(
                    id="test_sensor",
                    formula="state * 2",
                    variables={},
                )
            ],
        )

    def test_initialization(self, phase: PreEvaluationPhase, mock_hass, mock_entity_registry, mock_states) -> None:
        """Test phase initialization."""
        assert phase._hass is None
        assert phase._data_provider_callback is None
        assert phase._dependency_handler is None
        assert phase._cache_handler is None
        assert phase._error_handler is None
        assert phase._sensor_to_backing_mapping is None
        assert phase._allow_ha_lookups is False

    def test_set_evaluator_dependencies(
        self, phase: PreEvaluationPhase, mock_dependencies: dict, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test setting evaluator dependencies."""
        phase.set_evaluator_dependencies(**mock_dependencies)

        assert phase._hass == mock_dependencies["hass"]
        assert phase._data_provider_callback == mock_dependencies["data_provider_callback"]
        assert phase._dependency_handler == mock_dependencies["dependency_handler"]
        assert phase._cache_handler == mock_dependencies["cache_handler"]
        assert phase._error_handler == mock_dependencies["error_handler"]
        assert phase._sensor_to_backing_mapping == mock_dependencies["sensor_to_backing_mapping"]
        assert phase._allow_ha_lookups == mock_dependencies["allow_ha_lookups"]

    def test_perform_pre_evaluation_checks_circuit_breaker(
        self,
        phase: PreEvaluationPhase,
        mock_dependencies: dict,
        basic_config: FormulaConfig,
        mock_hass,
        mock_entity_registry,
        mock_states,
    ) -> None:
        """Test circuit breaker check in pre-evaluation."""
        # Setup circuit breaker to skip evaluation
        mock_dependencies["error_handler"].should_skip_evaluation.return_value = True

        phase.set_evaluator_dependencies(**mock_dependencies)

        result, context = phase.perform_pre_evaluation_checks(basic_config, None, None, "test_formula")

        assert result is not None
        assert "Skipping formula" in result["error"]
        assert context is None

    def test_perform_pre_evaluation_checks_cache_hit(
        self,
        phase: PreEvaluationPhase,
        mock_dependencies: dict,
        basic_config: FormulaConfig,
        mock_hass,
        mock_entity_registry,
        mock_states,
    ) -> None:
        """Test cache check in pre-evaluation."""
        # Setup cache to return a result
        cache_result = EvaluatorResults.create_success_result(100.0)
        mock_dependencies["error_handler"].should_skip_evaluation.return_value = False
        mock_dependencies["cache_handler"].check_cache.return_value = cache_result

        phase.set_evaluator_dependencies(**mock_dependencies)

        result, context = phase.perform_pre_evaluation_checks(basic_config, None, None, "test_formula")

        assert result == cache_result
        assert context is None

    def test_perform_pre_evaluation_checks_state_token_validation_no_sensor_config(
        self,
        phase: PreEvaluationPhase,
        mock_dependencies: dict,
        basic_config: FormulaConfig,
        mock_hass,
        mock_entity_registry,
        mock_states,
    ) -> None:
        """Test state token validation when no sensor config is provided."""
        # Setup no cache hit and no circuit breaker
        mock_dependencies["error_handler"].should_skip_evaluation.return_value = False
        mock_dependencies["cache_handler"].check_cache.return_value = None
        mock_dependencies["dependency_management_phase"].extract_and_prepare_dependencies.return_value = (set(), set())
        mock_dependencies["dependency_handler"].check_dependencies.return_value = (set(), set(), set())
        mock_dependencies["dependency_management_phase"].handle_dependency_issues.return_value = None
        mock_dependencies["context_building_phase"].build_evaluation_context.return_value = {"var1": 100}
        mock_dependencies["dependency_management_phase"].validate_evaluation_context.return_value = None

        phase.set_evaluator_dependencies(**mock_dependencies)

        result, context = phase.perform_pre_evaluation_checks(basic_config, None, None, "test_formula")

        # Should continue to dependency extraction since no sensor config
        assert result is None
        assert context == {"var1": 100}

    def test_validate_state_token_resolution_no_sensor_config(
        self, phase: PreEvaluationPhase, basic_config: FormulaConfig, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test state token validation with no sensor config."""
        result = phase._validate_state_token_resolution(None, basic_config)

        assert result is not None
        assert "State token requires sensor configuration" in result["error"]

    def test_validate_state_token_resolution_attribute_formula(
        self,
        phase: PreEvaluationPhase,
        basic_config: FormulaConfig,
        basic_sensor_config: SensorConfig,
        mock_hass,
        mock_entity_registry,
        mock_states,
    ) -> None:
        """Test state token validation for attribute formulas."""
        # Create attribute formula (has underscore in ID)
        attribute_config = FormulaConfig(
            id="test_sensor_voltage",
            name="Test Attribute",
            formula="state * 1.1",
            variables={},
        )

        result = phase._validate_state_token_resolution(basic_sensor_config, attribute_config)

        # Attribute formulas should not validate backing entity
        assert result is None

    def test_validate_state_token_resolution_no_backing_entity_mapping(
        self,
        phase: PreEvaluationPhase,
        basic_config: FormulaConfig,
        basic_sensor_config: SensorConfig,
        mock_hass,
        mock_entity_registry,
        mock_states,
    ) -> None:
        """Test state token validation when no backing entity mapping exists."""
        # Setup phase with empty mapping
        phase._sensor_to_backing_mapping = {}  # Empty mapping
        phase._dependency_handler = Mock()
        phase._dependency_handler.get_integration_entities.return_value = set()
        phase._allow_ha_lookups = False

        # This should raise SensorMappingError (fatal error) because sensor has entity_id but no mapping
        with pytest.raises(SensorMappingError):
            phase._validate_state_token_resolution(basic_sensor_config, basic_config)

    def test_validate_state_token_resolution_backing_entity_not_registered(
        self,
        phase: PreEvaluationPhase,
        basic_config: FormulaConfig,
        basic_sensor_config: SensorConfig,
        mock_hass,
        mock_entity_registry,
        mock_states,
    ) -> None:
        """Test state token validation when backing entity is not registered."""
        # Setup phase with backing entity mapping but not registered
        phase._sensor_to_backing_mapping = {"test_sensor": "sensor.backing_entity"}  # Mapping exists but entity not registered
        phase._dependency_handler = Mock()
        phase._dependency_handler.get_integration_entities.return_value = set()  # Empty set = not registered
        phase._allow_ha_lookups = False

        # This should raise BackingEntityResolutionError (fatal error) because backing entity is not registered
        with pytest.raises(BackingEntityResolutionError):
            phase._validate_state_token_resolution(basic_sensor_config, basic_config)

    def test_validate_state_token_resolution_backing_entity_registered(
        self,
        phase: PreEvaluationPhase,
        basic_config: FormulaConfig,
        basic_sensor_config: SensorConfig,
        mock_hass,
        mock_entity_registry,
        mock_states,
    ) -> None:
        """Test state token validation when backing entity is registered."""
        # Setup phase with backing entity mapping and registered
        phase._sensor_to_backing_mapping = {"test_sensor": "sensor.backing_entity"}
        phase._dependency_handler = Mock()
        phase._dependency_handler.get_integration_entities.return_value = {"sensor.backing_entity"}

        result = phase._validate_state_token_resolution(basic_sensor_config, basic_config)

        # Should pass validation
        assert result is None

    def test_validate_state_token_resolution_allow_ha_lookups(
        self,
        phase: PreEvaluationPhase,
        basic_config: FormulaConfig,
        basic_sensor_config: SensorConfig,
        mock_hass,
        mock_entity_registry,
        mock_states,
    ) -> None:
        """Test state token validation when allow_ha_lookups is enabled."""
        # Setup phase with backing entity mapping but not registered, but allow_ha_lookups enabled
        phase._sensor_to_backing_mapping = {"test_sensor": "sensor.backing_entity"}
        phase._dependency_handler = Mock()
        phase._dependency_handler.get_integration_entities.return_value = set()
        phase._allow_ha_lookups = True

        result = phase._validate_state_token_resolution(basic_sensor_config, basic_config)

        # Should pass validation when allow_ha_lookups is enabled
        assert result is None

    def test_validate_state_token_resolution_self_reference(
        self, phase: PreEvaluationPhase, basic_config: FormulaConfig, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test state token validation for self-reference sensors."""
        # Create sensor config without entity_id (self-reference)
        self_ref_sensor_config = SensorConfig(
            unique_id="test_sensor",
            entity_id=None,  # No entity_id = self-reference
            name="Test Sensor",
            formulas=[
                FormulaConfig(
                    id="test_sensor",
                    formula="state * 2",
                    variables={},
                )
            ],
        )

        # Setup phase with no backing entity mapping
        phase._sensor_to_backing_mapping = {}

        result = phase._validate_state_token_resolution(self_ref_sensor_config, basic_config)

        # Should pass validation for self-reference
        assert result is None

    def test_handle_dependency_issues_no_issues(
        self, phase: PreEvaluationPhase, mock_dependencies: dict, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test handling dependency issues when there are no issues."""
        phase.set_evaluator_dependencies(**mock_dependencies)

        # Setup dependency management phase to return None (no issues)
        phase._dependency_management_phase.handle_dependency_issues.return_value = None

        result = phase._handle_dependency_issues(set(), set(), set(), "test_formula")

        assert result is None

    def test_handle_dependency_issues_with_error(
        self, phase: PreEvaluationPhase, mock_dependencies: dict, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test handling dependency issues when there is an error."""
        phase.set_evaluator_dependencies(**mock_dependencies)

        # Setup dependency management phase to return error
        error_result = {"error": "Missing dependencies", "state": "unavailable", "missing_dependencies": ["sensor.missing"]}
        phase._dependency_management_phase.handle_dependency_issues.return_value = error_result

        result = phase._handle_dependency_issues({"sensor.missing"}, set(), set(), "test_formula")

        assert result is not None
        assert result["error"] == "Missing dependencies"
        assert result["state"] == "unavailable"

    def test_validate_evaluation_context_no_issues(
        self, phase: PreEvaluationPhase, mock_dependencies: dict, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test evaluation context validation when there are no issues."""
        phase.set_evaluator_dependencies(**mock_dependencies)

        # Setup dependency management phase to return None (no issues)
        phase._dependency_management_phase.validate_evaluation_context.return_value = None

        result = phase._validate_evaluation_context({"var1": 100}, "test_formula")

        assert result is None

    def test_validate_evaluation_context_with_error(
        self, phase: PreEvaluationPhase, mock_dependencies: dict, mock_hass, mock_entity_registry, mock_states
    ) -> None:
        """Test evaluation context validation when there is an error."""
        phase.set_evaluator_dependencies(**mock_dependencies)

        # Setup dependency management phase to return error
        error_result = {"error": "Invalid context", "state": "unavailable"}
        phase._dependency_management_phase.validate_evaluation_context.return_value = error_result

        result = phase._validate_evaluation_context({"var1": None}, "test_formula")

        assert result is not None
        assert result["error"] == "Invalid context"
        assert result["state"] == "unavailable"
        # Should increment error count
        phase._error_handler.increment_error_count.assert_called_once_with("test_formula")

    def test_perform_pre_evaluation_checks_success(
        self,
        phase: PreEvaluationPhase,
        mock_dependencies: dict,
        basic_config: FormulaConfig,
        basic_sensor_config: SensorConfig,
        mock_hass,
        mock_entity_registry,
        mock_states,
    ) -> None:
        """Test successful pre-evaluation checks."""
        # Setup all checks to pass
        mock_dependencies["error_handler"].should_skip_evaluation.return_value = False
        mock_dependencies["cache_handler"].check_cache.return_value = None
        mock_dependencies["sensor_to_backing_mapping"] = {"test_sensor": "sensor.backing_entity"}
        mock_dependencies["dependency_handler"].get_integration_entities.return_value = {"sensor.backing_entity"}
        mock_dependencies["dependency_management_phase"].extract_and_prepare_dependencies.return_value = (set(), set())
        mock_dependencies["dependency_handler"].check_dependencies.return_value = (set(), set(), set())
        mock_dependencies["dependency_management_phase"].handle_dependency_issues.return_value = None
        mock_dependencies["context_building_phase"].build_evaluation_context.return_value = {"var1": 100}
        mock_dependencies["dependency_management_phase"].validate_evaluation_context.return_value = None

        phase.set_evaluator_dependencies(**mock_dependencies)

        result, context = phase.perform_pre_evaluation_checks(basic_config, None, basic_sensor_config, "test_formula")

        assert result is None
        assert context == {"var1": 100}
