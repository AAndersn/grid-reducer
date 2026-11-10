"""Filter pass: delete whole CIM classes, with the parts they own, and clear chosen attributes.

The profile does not mark which associations are compositions, so PARTS lists them. A part is
deleted with its owner once no owner is left (a Location shared by two switches stays until both
are gone). The report counts what was deleted and every reference removed from a kept object, so
a part PARTS misses shows up there rather than silently.
"""

import dataclasses
import difflib
from collections import Counter, deque

import cimprofiles.cim18.cim18v17 as cim
from cimgraph.models import GraphModel

from grid_reducer.config_models import Filters

#: (owner class, association): the association's targets are parts of the owner.
PARTS = (
    ("ConductingEquipment", "Terminals"),
    ("ACDCTerminal", "OperationalLimitSet"),
    ("Equipment", "OperationalLimitSet"),
    ("OperationalLimitSet", "OperationalLimitValue"),
    ("PowerSystemResource", "Location"),
    ("Location", "PositionPoints"),
    ("ACLineSegment", "ACLineSegmentPhases"),
    ("Switch", "SwitchPhase"),
    ("ProtectedSwitch", "RecloseSequences"),
    ("EnergyConsumer", "EnergyConsumerPhase"),
    ("EnergySource", "EnergySourcePhase"),
    ("ShuntCompensator", "ShuntCompensatorPhase"),
    ("PowerElectronicsConnection", "PowerElectronicsConnectionPhase"),
    ("PowerElectronicsConnection", "PowerElectronicsUnit"),
    ("RotatingMachine", "RotatingMachinePhase"),
    ("PowerTransformer", "PowerTransformerEnd"),
    ("PowerTransformer", "TransformerTanks"),
    ("AutoTransformer", "AutoTransformerEnd"),
    ("TransformerTank", "TransformerWindings"),
    ("TransformerEnd", "RatioTapChanger"),
    ("TransformerEnd", "PhaseTapChanger"),
    ("TransformerEnd", "FromMeshImpedance"),
    ("TransformerEnd", "ToMeshImpedance"),
    ("TapChanger", "TapChangerControl"),
    ("PerLengthPhaseImpedance", "PhaseImpedanceData"),
    ("Curve", "CurveDatas"),
    ("FunctionBlock", "FunctionOutputVariable"),
    ("FunctionBlock", "Input"),
)

#: Identity slots; the rename pass replaces them, and clearing them would break the model.
IDENTITY_ATTRIBUTES = frozenset({"identifier", "mRID"})


def _field(cls: type, name: str) -> dataclasses.Field:
    return {f.name: f for f in dataclasses.fields(cls)}[name]


def _owner_slots() -> tuple[list[tuple[type, str]], list[tuple[type, str]]]:
    """(owner class, part association) pairs, and (part class, back-reference) pairs."""
    owned, backrefs = [], set()
    for owner_name, association in PARTS:
        owner = getattr(cim, owner_name)
        part_name, backref = _field(owner, association).metadata["inverse"].split(".")
        owned.append((owner, association))
        backrefs.add((getattr(cim, part_name), backref))
    return owned, sorted(backrefs, key=lambda pair: (pair[0].__name__, pair[1]))


OWNED, BACKREFS = _owner_slots()


def check(filters: Filters) -> None:
    """Raise ValueError for a class or attribute the filters cannot drop, before any model loads."""
    for name in filters.drop_classes or []:
        _profile_class(name)
    for spec in filters.drop_attributes or []:
        class_name, attribute = spec.split(".")
        cls = _profile_class(class_name)
        names = [f.name for f in dataclasses.fields(cls)]
        if attribute not in names:
            raise ValueError(
                f"{spec}: {class_name} has no attribute {attribute!r}{_hint(attribute, names)}"
            )
        if attribute in IDENTITY_ATTRIBUTES:
            raise ValueError(f"{spec}: identities are replaced by the rename pass, not dropped")
        metadata = _field(cls, attribute).metadata
        if metadata.get("maxOccurs") == "unbounded":
            raise ValueError(f"{spec}: a list of references; drop the referenced class instead")
        if int(metadata.get("minOccurs", "0")) >= 1:
            raise ValueError(
                f"{spec}: required by the profile (minOccurs {metadata['minOccurs']})"
            )


def run(model: GraphModel, filters: Filters) -> dict:
    """Apply the filters to the model in place; returns the pass report.

    Raises ValueError (leaving the model partly filtered) if dropping would strip a required
    reference from an object that is kept.
    """
    check(filters)
    deleted, cascaded, touched = _drop_classes(model, filters.drop_classes or [])
    cleared_attributes = _drop_attributes(model, filters.drop_attributes or [])
    return {
        "deleted": _sorted(deleted),
        "deleted_parts": _sorted(cascaded),
        "references_removed_from_kept": _sorted(_removed_references(model, touched)),
        "cleared_attributes": _sorted(cleared_attributes),
    }


def _drop_classes(model: GraphModel, class_names: list[str]) -> tuple[Counter, Counter, list]:
    targets = tuple(_profile_class(name) for name in class_names)
    queue = deque(
        (obj, False)
        for cls in list(model.graph)
        if targets and issubclass(cls, targets)
        for obj in list(model.graph[cls].values())
    )
    deleted, cascaded, touched = Counter(), Counter(), []
    while queue:
        obj, is_part = queue.popleft()
        if model.graph.get(type(obj), {}).get(obj.identifier) is not obj:
            continue
        parts = _parts_of(obj)
        touched += _referenced(obj)
        model.delete(obj)
        (cascaded if is_part else deleted)[type(obj).__name__] += 1
        queue.extend((part, True) for part in parts if _is_orphan(part))
    return deleted, cascaded, touched


def _drop_attributes(model: GraphModel, specs: list[str]) -> Counter:
    cleared = Counter()
    for spec in specs:
        class_name, attribute = spec.split(".")
        cls = _profile_class(class_name)
        for graph_cls in list(model.graph):
            if not issubclass(graph_cls, cls):
                continue
            for obj in model.graph[graph_cls].values():
                if getattr(obj, attribute) is not None:
                    model.modify(obj, attribute, None)
                    cleared[f"{graph_cls.__name__}.{attribute}"] += 1
    return cleared


def _parts_of(obj) -> list:
    parts = []
    for owner, association in OWNED:
        if isinstance(obj, owner):
            value = getattr(obj, association)
            parts += value if isinstance(value, list) else [value] if value is not None else []
    return parts


def _is_orphan(part) -> bool:
    return all(
        getattr(part, backref) in (None, [])
        for part_cls, backref in BACKREFS
        if isinstance(part, part_cls)
    )


def _referenced(obj) -> list[tuple[object, str]]:
    """(object, its attribute naming obj) for every object obj references."""
    pairs = []
    for f in dataclasses.fields(obj):
        inverse = f.metadata.get("inverse")
        value = getattr(obj, f.name)
        if f.metadata.get("type") != "Association" or not inverse or not value:
            continue
        for other in value if isinstance(value, list) else [value]:
            pairs.append((other, inverse.split(".")[1]))
    return pairs


def _removed_references(model: GraphModel, touched: list[tuple[object, str]]) -> Counter:
    """Count references removed from objects still in the model; raise if one was required."""
    removed = Counter()
    for other, attribute in touched:
        if model.graph.get(type(other), {}).get(other.identifier) is not other:
            continue
        removed[f"{type(other).__name__}.{attribute}"] += 1
        metadata = _field(type(other), attribute).metadata
        if int(metadata.get("minOccurs", "0")) >= 1 and getattr(other, attribute) in (None, []):
            raise ValueError(
                f"{type(other).__name__} {other.mRID or other.identifier} lost its required "
                f"{attribute}; drop it too, or add the association to filters.PARTS"
            )
    return removed


def _profile_class(name: str) -> type:
    cls = getattr(cim, name, None)
    if not isinstance(cls, type):
        raise ValueError(f"{name!r} is not a cim18v17 class{_hint(name, cim.__all__)}")
    return cls


def _hint(name: str, candidates) -> str:
    close = difflib.get_close_matches(name, candidates, n=3)
    return f" (did you mean {', '.join(close)}?)" if close else ""


def _sorted(counts: Counter) -> dict[str, int]:
    return {key: counts[key] for key in sorted(counts)}
