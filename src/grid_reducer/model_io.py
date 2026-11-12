"""Read and write CIM models: .cimtbl in, .cimtbl and CIM XML out."""

from collections import Counter
from pathlib import Path

import cimtables
from cimgraph.models import GraphModel
from cimgraph.utils import write_xml
from cimtables import document


def load_model(path: Path) -> GraphModel:
    """A cim18v17 model from a .cimtbl master file (which imports its parts)."""
    if path.suffix != ".cimtbl":
        raise ValueError(
            f"{path}: only .cimtbl sources are read; convert .dss, .sxst or CIM XML with a CIMHub "
            f"importer first"
        )
    return cimtables.load_model(path)


def write_cimtbl(
    model: GraphModel, name: str, directory: Path, terminals: str = "explicit"
) -> Path:
    """Write the model as .cimtbl files in a new directory; returns the master file.

    terminals="explicit" writes every Terminal and phase child as its own row, so any mRIDs survive
    a reload. "folded" puts them in node/phases columns; a reload gives them the loader's mRIDs
    (``<equipment>_T<n>``, ``<equipment>_<phase>``), which the rename pass already gave them.
    """
    directory.mkdir(parents=True)
    documents = cimtables.to_documents(model, name, terminals=terminals)
    return document.write_documents(documents, directory)


def write_cim_xml(model: GraphModel, path: Path) -> Path:
    write_xml(model, str(path))
    return path


def class_counts(model: GraphModel) -> dict[str, int]:
    counts = Counter({cls.__name__: len(objects) for cls, objects in model.graph.items()})
    return {name: counts[name] for name in sorted(counts) if counts[name]}
