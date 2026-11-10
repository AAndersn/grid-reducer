from pathlib import Path

import pydantic
import pytest

from grid_reducer.config import load_config, parse_config

EXAMPLE = Path(__file__).parents[1] / "examples" / "sanitize.example.yaml"


def test_example_config_loads():
    config = load_config(EXAMPLE)
    assert Path(config.source).is_file()
    assert config.filters.drop_classes == [
        "FunctionBlock",
        "ProtectionFunctionBlock",
        "RecloseSequence",
    ]
    assert config.outputs == ["cimtbl", "cim_xml"]


def test_omitted_sections_take_defaults(tmp_path):
    config = parse_config({"source": "model.cimtbl"}, base_dir=tmp_path)
    assert config.source == str(tmp_path / "model.cimtbl")
    assert not config.filters.drop_classes
    assert config.reduce.lines is False
    assert config.noise.transformers == "none"
    assert config.outputs == ["cimtbl"]


@pytest.mark.parametrize(
    "data",
    [
        {"source": "m.cimtbl", "reduse": {"lines": True}},
        {"source": "m.cimtbl", "noise": {"transformers": "medium"}},
        {"source": "m.cimtbl", "filters": {"drop_attributes": ["ratedCurrent"]}},
        {"source": "m.cimtbl", "outputs": ["dss"]},
        {"seed": 1},
    ],
)
def test_schema_violations_raise(tmp_path, data):
    with pytest.raises(pydantic.ValidationError):
        parse_config(data, base_dir=tmp_path)


@pytest.mark.parametrize(
    "section",
    [{"reduce": {"lines": True}}, {"layout": {"enabled": True}}, {"noise": {"loads": "low"}}],
)
def test_unimplemented_passes_raise(tmp_path, section):
    with pytest.raises(NotImplementedError, match="not implemented yet"):
        parse_config({"source": "m.cimtbl", **section}, base_dir=tmp_path)
