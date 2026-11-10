# ⚡ Getting Started with `grid-reducer`

[![Build](https://github.com/Grid-Kitchen/grid-reducer/actions/workflows/ci.yml/badge.svg)](https://github.com/Grid-Kitchen/grid-reducer/actions/workflows/ci.yml)
![Python](https://img.shields.io/pypi/pyversions/grid-reducer)
![License](https://img.shields.io/github/license/Grid-Kitchen/grid-reducer)
![Coverage](https://img.shields.io/codecov/c/github/Grid-Kitchen/grid-reducer)

[View Full Documentation.](https://grid-kitchen.github.io/grid-reducer).

Welcome! Follow the steps below to get `grid-reducer` up and running locally.  
We recommend using a Python virtual environment for a clean install 🔒🐍.

This software is being provided as a prototype only. For your intended use, it is your responsibility to independently validate the results in accordance with your applicable software quality assurance program.

## Status: CIM rewrite in progress

grid-reducer is being rewritten to work on CIM models (cim18v17) instead of OpenDSS decks. It reads a
`.cimtbl` model (from [cim-tables](https://github.com/PNNL-CIM-Tools/CIM-Tables); other formats go
through a CIMHub importer first) and runs a fixed sequence of passes chosen by a config file:

| Pass | Status |
|------|--------|
| filter: drop CIM classes (with the parts they own) and attributes | done |
| reduce transformers, reduce lines | planned |
| layout (force-directed, pinned at trunk branch points) | planned |
| noise (grid-meta noise catalog) | planned |
| rename, validate | planned |

The dependencies are not all released yet: `pyproject.toml` points uv at sibling checkouts of
CIM-Graph, CIM-Profiles and CIM-Tables.

```bash
uv sync --extra dev
uv run grid sanitize examples/sanitize.example.yaml --run-dir runs/example
```

The config schema is `src/grid_reducer/schemas/sanitize_config.linkml.yaml`; `codegen.sh` regenerates
the pydantic models and JSON Schema from it. A run directory holds a `.cimtbl` snapshot and a
`report.json` after every pass, plus `run.json` and the outputs. It contains the original model, so
keep it where the model owner keeps the source.

```python
from grid_reducer.config import load_config
from grid_reducer.pipeline import run_pipeline

summary = run_pipeline(load_config("sanitize.yaml"), "runs/feeder_1", on_progress=print)
```

## Attribution and Disclaimer

This software was created under a project sponsored by the U.S. Department of Energy’s Office of Electricity, an agency of the United States Government. Neither the United States Government nor the United States Department of Energy, nor Battelle, nor any of their employees, nor any jurisdiction or organization that has cooperated in the development of these materials, makes any warranty, express or implied, or assumes any legal liability or responsibility for the accuracy, completeness, or usefulness or any information, apparatus, product, software, or process disclosed, or represents that its use would not infringe privately owned rights.

Reference herein to any specific commercial product, process, or service by trade name, trademark, manufacturer, or otherwise does not necessarily constitute or imply its endorsement, recommendation, or favoring by the United States Government or any agency thereof, or Battelle Memorial Institute. The views and opinions of authors expressed herein do not necessarily state or reflect those of the United States Government or any agency thereof.

PACIFIC NORTHWEST NATIONAL LABORATORY

operated by BATTELLE

for the UNITED STATES DEPARTMENT OF ENERGY

under Contract DE-AC05-76RL01830
