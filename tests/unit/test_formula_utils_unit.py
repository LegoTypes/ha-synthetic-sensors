from ha_synthetic_sensors.config_models import FormulaConfig
from ha_synthetic_sensors.formula_utils import tokenize_formula, add_optional_formula_fields


def test_tokenize_formula_extracts_tokens() -> None:
    tokens = tokenize_formula("a + sensor.kitchen + b")
    # extractor splits domain and object; ensure domain token appears and variables too
    assert "a" in tokens and "b" in tokens and "sensor" in tokens


def test_add_optional_formula_fields_includes_name_variables_and_metadata() -> None:
    f = FormulaConfig(id="main", formula="1", name="Test", variables={"a": 1}, metadata={"m": 2})
    data: dict[str, object] = {}
    add_optional_formula_fields(data, f, include_variables=True)
    assert data.get("name") == "Test"
    assert "variables" in data and data["variables"] == {"a": 1}
    assert data.get("metadata") == {"m": 2}
