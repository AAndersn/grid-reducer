"""Run the sanitize passes in their fixed order, keeping a snapshot of the model after each one.

A run directory holds everything a UI needs to show and compare the steps::

    run.json             the resolved config and one entry per pass
    00_source/           the model as loaded: .cimtbl files and report.json (class counts)
    01_filter/           the model after the filter pass, and that pass's report
    02_rename/           ... one directory per pass that ran
    output/              the final model in each requested format, named rename.model_name
                         (.cimtbl with Terminals and phases folded into node/phases columns)

The run directory holds the original model, so it stays where the model owner keeps it.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cimgraph.models import GraphModel

from grid_reducer import filters, model_io, rename
from grid_reducer.config_models import SanitizeConfig


@dataclass(frozen=True)
class Pass:
    name: str
    enabled: Callable[[SanitizeConfig], bool]
    check: Callable[[SanitizeConfig], None]
    run: Callable[[GraphModel, SanitizeConfig], dict]


PASSES = (
    Pass(
        "filter",
        enabled=lambda config: bool(config.filters.drop_classes or config.filters.drop_attributes),
        check=lambda config: filters.check(config.filters),
        run=lambda model, config: filters.run(model, config.filters),
    ),
    Pass(
        "rename",
        enabled=lambda config: config.rename.enabled,
        check=lambda config: None,
        run=lambda model, config: rename.run(model, config.rename, config.seed),
    ),
)


def run_pipeline(
    config: SanitizeConfig, run_dir: Path, on_progress: Callable[[str], None] = lambda _: None
) -> dict:
    """Sanitize config.source into run_dir, which must not exist or be empty; returns run.json."""
    run_dir = Path(run_dir)
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"{run_dir} is not empty; each run needs its own directory")
    passes = [p for p in PASSES if p.enabled(config)]
    for p in passes:
        p.check(config)

    source = Path(config.source)
    name = source.stem
    on_progress(f"loading {source}")
    model = model_io.load_model(source)
    steps = [_snapshot(model, name, run_dir / "00_source", {"source": str(source)})]
    for number, p in enumerate(passes, start=1):
        on_progress(f"pass {number}: {p.name}")
        steps.append(
            _snapshot(model, name, run_dir / f"{number:02d}_{p.name}", p.run(model, config))
        )

    on_progress("writing outputs")
    output_name = config.rename.model_name if config.rename.enabled else name
    outputs = _write_outputs(model, output_name, config.outputs, run_dir / "output")
    summary = {"config": config.model_dump(mode="json"), "steps": steps, "outputs": outputs}
    (run_dir / "run.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _snapshot(model: GraphModel, name: str, directory: Path, report: dict) -> dict:
    master = model_io.write_cimtbl(model, name, directory)
    report = {**report, "counts": model_io.class_counts(model)}
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return {"step": directory.name, "master": str(master.relative_to(directory.parent))}


def _write_outputs(model: GraphModel, name: str, formats: list[str], directory: Path) -> list[str]:
    directory.mkdir(parents=True)
    written = []
    for output_format in formats:
        if output_format == "cimtbl":
            path = model_io.write_cimtbl(model, name, directory / "cimtbl", terminals="folded")
        elif output_format == "cim_xml":
            path = model_io.write_cim_xml(model, directory / f"{name}.xml")
        else:
            raise ValueError(f"unknown output format {output_format!r}")
        written.append(str(path.relative_to(directory.parent)))
    return written
