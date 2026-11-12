"""Load a sanitize config (schemas/sanitize_config.linkml.yaml) from YAML or JSON."""

from pathlib import Path

import yaml

from grid_reducer.config_models import (
    Filters,
    Layout,
    Noise,
    OutputFormat,
    Reduce,
    Rename,
    SanitizeConfig,
)


def load_config(path: Path | str) -> SanitizeConfig:
    """Read a config file; ``source`` is resolved relative to the file."""
    path = Path(path)
    return parse_config(yaml.safe_load(path.read_text()), base_dir=path.parent)


def parse_config(data: dict, base_dir: Path) -> SanitizeConfig:
    """Validate config data (e.g. a parsed file or a posted form) and fill in omitted sections.

    Raises pydantic.ValidationError on a schema violation and NotImplementedError when it turns on
    a pass that does not exist yet.
    """
    config = SanitizeConfig.model_validate(data)
    config = config.model_copy(
        update={
            "source": str((base_dir / config.source).resolve()),
            "filters": config.filters or Filters(),
            "reduce": config.reduce or Reduce(),
            "layout": config.layout or Layout(),
            "noise": config.noise or Noise(),
            "rename": config.rename or Rename(),
            "outputs": config.outputs or [OutputFormat.cimtbl.value],
        }
    )
    _refuse_unimplemented(config)
    return config


def _refuse_unimplemented(config: SanitizeConfig) -> None:
    requested = {
        "reduce.transformers": config.reduce.transformers,
        "reduce.lines": config.reduce.lines,
        "layout.enabled": config.layout.enabled,
        **{f"noise.{key}": level != "none" for key, level in config.noise.model_dump().items()},
    }
    pending = [key for key, on in requested.items() if on]
    if pending:
        raise NotImplementedError(f"not implemented yet: {', '.join(pending)}")
