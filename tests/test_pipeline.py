import json

import cimprofiles.cim18.cim18v17 as cim
import cimtables
import pytest
from click.testing import CliRunner

from grid_reducer.cli import cli
from grid_reducer.config import parse_config
from grid_reducer.pipeline import run_pipeline


@pytest.fixture
def make_config(tmp_path, ieee13_path):
    def make(**sections):
        return parse_config({"source": str(ieee13_path), **sections}, base_dir=tmp_path)

    return make


def test_run_writes_a_snapshot_per_pass(tmp_path, make_config):
    config = make_config(filters={"drop_classes": ["Recloser"]}, outputs=["cimtbl", "cim_xml"])
    summary = run_pipeline(config, tmp_path / "run")

    run = tmp_path / "run"
    assert [step["step"] for step in summary["steps"]] == ["00_source", "01_filter", "02_rename"]
    assert json.loads((run / "run.json").read_text()) == summary
    source = cimtables.load_model(run / summary["steps"][0]["master"])
    filtered = cimtables.load_model(run / summary["steps"][1]["master"])
    assert len(source.graph[cim.Recloser]) == 1
    assert not filtered.graph.get(cim.Recloser)
    assert json.loads((run / "01_filter" / "report.json").read_text())["deleted"] == {
        "Recloser": 1
    }
    assert summary["outputs"] == ["output/cimtbl/feeder.cimtbl", "output/feeder.xml"]
    renamed = cimtables.load_model(run / summary["steps"][2]["master"])
    output = cimtables.load_model(run / summary["outputs"][0])
    assert cimtables.diff_models(renamed, output) == []
    written = [path.read_text() for path in (run / "output").rglob("*") if path.is_file()]
    assert not any("ieee13" in text.lower() for text in written)
    cimtbl = "\n".join(path.read_text() for path in (run / "output" / "cimtbl").glob("*.cimtbl"))
    assert "Table Terminal:" not in cimtbl
    assert "Table ACLineSegmentPhase:" not in cimtbl


def test_rename_can_be_turned_off(tmp_path, make_config):
    summary = run_pipeline(make_config(rename={"enabled": False}), tmp_path / "run")
    assert [step["step"] for step in summary["steps"]] == ["00_source"]
    assert summary["outputs"] == ["output/cimtbl/IEEE13_CDPSM.cimtbl"]


def test_source_snapshot_matches_source(tmp_path, make_config, ieee13_path):
    summary = run_pipeline(make_config(), tmp_path / "run")
    snapshot = cimtables.load_model(tmp_path / "run" / summary["steps"][0]["master"])
    assert cimtables.diff_models(cimtables.load_model(ieee13_path), snapshot) == []


def test_refuses_a_used_run_dir(tmp_path, make_config):
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "old.txt").write_text("")
    with pytest.raises(FileExistsError):
        run_pipeline(make_config(), tmp_path / "run")


def test_bad_filter_fails_before_loading(tmp_path, make_config):
    config = make_config(filters={"drop_classes": ["NoSuchClass"]})
    with pytest.raises(ValueError, match="not a cim18v17 class"):
        run_pipeline(config, tmp_path / "run")
    assert not (tmp_path / "run").exists()


def test_cli_sanitize(tmp_path, ieee13_path):
    config_file = tmp_path / "sanitize.yaml"
    config_file.write_text(
        f"source: {ieee13_path}\nfilters:\n  drop_attributes: [Fuse.ratedCurrent]\n"
    )
    result = CliRunner().invoke(
        cli, ["sanitize", str(config_file), "--run-dir", str(tmp_path / "run")]
    )
    assert result.exit_code == 0, result.output
    assert "pass 1: filter" in result.output
    assert (tmp_path / "run" / "output" / "cimtbl").is_dir()
