"""Test metadata AST caching functionality."""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, timezone

from ha_synthetic_sensors.core_formula_evaluator import CoreFormulaEvaluator
from ha_synthetic_sensors.evaluator_handlers import HandlerFactory
from ha_synthetic_sensors.evaluator_handlers.metadata_handler import MetadataHandler
from ha_synthetic_sensors.enhanced_formula_evaluation import EnhancedSimpleEvalHelper
from ha_synthetic_sensors.type_definitions import ReferenceValue


class TestMetadataASTCaching:
    """Test that metadata functions work with AST caching."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler_factory = HandlerFactory()
        self.enhanced_helper = EnhancedSimpleEvalHelper()
        self.evaluator = CoreFormulaEvaluator(handler_factory=self.handler_factory, enhanced_helper=self.enhanced_helper)

    def test_metadata_ast_caching_single_call(self):
        """Test that a single metadata call gets cached correctly."""
        # Create mock Home Assistant instance
        mock_hass = Mock()
        mock_state = Mock()
        test_timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_state.last_changed = test_timestamp
        mock_state.entity_id = "sensor.test_entity"
        mock_hass.states.get.return_value = mock_state

        # Create metadata handler with mock hass
        metadata_handler = MetadataHandler(hass=mock_hass)
        self.handler_factory.register_handler("metadata", metadata_handler)

        context = {"test_var": ReferenceValue("test", "value")}

        # First evaluation - should create AST cache
        result1 = self.evaluator.evaluate_formula(
            resolved_formula="metadata(sensor.test_entity, 'last_changed')",
            original_formula="metadata(sensor.test_entity, 'last_changed')",
            handler_context=context,
        )

        # Second evaluation - should use cached AST
        result2 = self.evaluator.evaluate_formula(
            resolved_formula="metadata(sensor.test_entity, 'last_changed')",
            original_formula="metadata(sensor.test_entity, 'last_changed')",
            handler_context=context,
        )

        # Both should return the same result
        assert result1 == test_timestamp.isoformat()
        assert result2 == test_timestamp.isoformat()
        assert result1 == result2

    def test_metadata_ast_caching_multiple_calls(self):
        """Test that formulas with multiple metadata calls get cached correctly."""
        # Create mock Home Assistant instance
        mock_hass = Mock()

        # Set up two different mock states
        mock_state1 = Mock()
        mock_state1.entity_id = "sensor.power"
        mock_state2 = Mock()
        mock_state2.entity_id = "sensor.temp"

        # Configure mock to return different states for different entity_ids
        def get_state(entity_id):
            if entity_id == "sensor.power":
                return mock_state1
            elif entity_id == "sensor.temp":
                return mock_state2
            return None

        mock_hass.states.get.side_effect = get_state

        # Create metadata handler with mock hass
        metadata_handler = MetadataHandler(hass=mock_hass)
        self.handler_factory.register_handler("metadata", metadata_handler)

        context = {"test_var": ReferenceValue("test", "value")}

        # First evaluation - should create AST cache
        result1 = self.evaluator.evaluate_formula(
            resolved_formula="metadata(sensor.power, 'entity_id') + metadata(sensor.temp, 'entity_id')",
            original_formula="metadata(sensor.power, 'entity_id') + metadata(sensor.temp, 'entity_id')",
            handler_context=context,
        )

        # Second evaluation - should use cached AST
        result2 = self.evaluator.evaluate_formula(
            resolved_formula="metadata(sensor.power, 'entity_id') + metadata(sensor.temp, 'entity_id')",
            original_formula="metadata(sensor.power, 'entity_id') + metadata(sensor.temp, 'entity_id')",
            handler_context=context,
        )

        # Both should return the same result
        expected = "sensor.power" + "sensor.temp"  # String concatenation
        assert result1 == expected
        assert result2 == expected
        assert result1 == result2

    def test_metadata_ast_caching_with_variables(self):
        """Test that metadata calls with variables get cached correctly."""
        # Create mock Home Assistant instance
        mock_hass = Mock()
        mock_state = Mock()
        mock_state.entity_id = "sensor.power_meter"
        mock_hass.states.get.return_value = mock_state

        # Create metadata handler with mock hass
        metadata_handler = MetadataHandler(hass=mock_hass)
        self.handler_factory.register_handler("metadata", metadata_handler)

        context = {"power_var": ReferenceValue("power_var", "sensor.power_meter")}

        # First evaluation - should create AST cache
        result1 = self.evaluator.evaluate_formula(
            resolved_formula="metadata(power_var, 'entity_id')",
            original_formula="metadata(power_var, 'entity_id')",
            handler_context=context,
        )

        # Second evaluation - should use cached AST
        result2 = self.evaluator.evaluate_formula(
            resolved_formula="metadata(power_var, 'entity_id')",
            original_formula="metadata(power_var, 'entity_id')",
            handler_context=context,
        )

        # Both should return the same result
        assert result1 == "sensor.power_meter"
        assert result2 == "sensor.power_meter"
        assert result1 == result2
