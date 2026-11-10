from pathlib import Path

import click

from grid_reducer.config import load_config
from grid_reducer.pipeline import run_pipeline


@click.group()
def cli():
    pass


@cli.command()
@click.argument("config_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--run-dir",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="New or empty directory for the step snapshots and outputs.",
)
def sanitize(config_file: Path, run_dir: Path):
    """Sanitize the model named in CONFIG_FILE (YAML or JSON)."""
    summary = run_pipeline(load_config(config_file), run_dir, on_progress=click.echo)
    for output in summary["outputs"]:
        click.echo(f"wrote {run_dir / output}")
