"""Replace every name and identifier in the model with canonical ones.

Every object gets a compact mRID following the CIMTBL-Models conventions (``naming``: ``cn_0001``,
``ln_0001``, ``ln_0001_T1``); name, aliasName and description are cleared (CIMHub exports under
the mRID). The model scope (the .cimtbl Authority and Model, also the seed of every
generated UUID) is set to grid-reducer's authority and the configured model name, and identifiers
are regenerated under it, so no identifier can be derived from a source mRID or GIS id.

Numbering follows the network: a depth-first LinkNet spanning tree (cimtopology) grown from the
sources orders ConnectivityNodes and ConductingEquipment from the source outward, one path after
another, and each Terminal follows its equipment. Each two-terminal branch is turned so its
Terminal 1 is on the node the walk reached it from. Everything else, and every tie, is in an order
shuffled by the run's seed; the equipment is added to the LinkNet in that order too, so which
branch the walk takes first at a fork tells nothing about the source file. Numbers are dense per
prefix, so they tell nothing the published object counts don't.
"""

import dataclasses
import itertools
import random
import uuid
from collections import Counter

import cimprofiles.cim18.cim18v17 as cim
from cimgraph.core import set_model_scope
from cimgraph.models import GraphModel
from cimtopology.core import LinkNet, spanning_forest

from grid_reducer import naming
from grid_reducer.config_models import Rename

AUTHORITY = "https://github.com/Grid-Kitchen/grid-reducer"
IDENTITY_TEXT = ("mRID", "name", "aliasName", "description")
OFF_NETWORK = (float("inf"),)  # sort key of objects the walk doesn't number


def run(model: GraphModel, rename: Rename, seed: int | None) -> dict:
    rng = random.Random(seed)
    set_model_scope(AUTHORITY, rename.model_name)
    ordered = {}
    for cls in sorted(model.graph, key=lambda cls: cls.__name__):
        objects = list(model.graph[cls].values())
        rng.shuffle(objects)
        ordered[cls] = objects
    keys, upstream = walk(ordered)
    reoriented = Counter(
        type(equipment).__name__
        for equipment, node in upstream.items()
        if _orient(equipment, node)
    )
    for equipment in [obj for obj in keys if isinstance(obj, cim.ConductingEquipment)]:
        for terminal in equipment.Terminals:
            keys[terminal] = (*keys[equipment], terminal.sequenceNumber)
    for objects in ordered.values():
        objects.sort(key=lambda obj: keys.get(obj, OFF_NETWORK))

    names, seed_keys, unprefixed = naming.assign(ordered)

    for cls, objects in ordered.items():
        for obj in objects:
            if obj in names:
                _rename(obj, names[obj])
            elif obj in seed_keys:
                obj.uuid(
                    mRID=seed_keys[obj]
                )  # seeds the UUID; an Identity-only object keeps no mRID
            else:
                obj.uuid(uri=str(uuid.UUID(int=rng.getrandbits(128), version=4)))
        model.graph[cls].clear()
        model.graph[cls].update((obj.identifier, obj) for obj in objects)
    model._mrid_count = -1  # cim-graph rebuilds its mRID index only when the object count changes
    return {
        "scope": {"authority": AUTHORITY, "model": rename.model_name},
        "renamed": {cls.__name__: len(objects) for cls, objects in ordered.items()},
        "unprefixed": dict(sorted(unprefixed.items())),
        "reoriented": dict(sorted(reoriented.items())),
        "text_left": _text_left(model),
    }


def walk(ordered: dict[type, list]) -> tuple[dict[object, tuple], dict[object, object]]:
    """Sort keys of ConnectivityNodes and ConductingEquipment in depth-first walk order, and the
    node each branch was walked from (equipment -> its upstream ConnectivityNode).

    A node and each branch are ranked as the walk emits them; a one-terminal device (load, source,
    capacitor) sorts right after its node.
    """
    linknet = LinkNet()
    node_of = {}  # LinkNet node index -> ConnectivityNode
    equipment_of = {}  # LinkNet equipment index -> ConductingEquipment
    for cls, objects in ordered.items():
        if not issubclass(cls, cim.ConductingEquipment):
            continue
        for equipment in objects:
            nodes = [t.ConnectivityNode for t in equipment.Terminals or [] if t.ConnectivityNode]
            if not nodes:
                continue
            index = linknet.add_equipment(equipment.mRID, [node.mRID for node in nodes])
            equipment_of[index] = equipment
            for node in nodes:
                node_of[linknet.node[node.mRID]] = node

    sources = [
        linknet.node[terminal.ConnectivityNode.mRID]
        for cls, objects in ordered.items()
        if issubclass(cls, cim.EnergySource)
        for source in objects
        for terminal in source.Terminals or []
        if terminal.ConnectivityNode
    ]
    every_node = range(1, linknet.node_count + 1)
    forest = spanning_forest(linknet, [*sources, *every_node], depth_first=True)

    keys, upstream = {}, {}
    counter = itertools.count()

    def rank(obj):
        if obj not in keys:
            keys[obj] = (next(counter), 0)

    for terminal in forest.order:
        equipment = linknet.terminal_equipment[terminal]
        rank(node_of[linknet.terminal_node[terminal]])
        rank(equipment_of[equipment])
        upstream[equipment_of[equipment]] = node_of[linknet.terminal_node[terminal]]
        for other in linknet.equipment_terminals[equipment]:
            rank(node_of[linknet.terminal_node[other]])
    for node in every_node:
        rank(node_of[node])
    for index, equipment in equipment_of.items():
        if equipment not in keys:
            first_node = node_of[linknet.terminal_node[linknet.equipment_terminals[index][0]]]
            keys[equipment] = (keys[first_node][0], 1)
    return keys, upstream


def _orient(equipment, upstream_node) -> bool:
    """Make a two-terminal branch's Terminal 1 the one on its upstream node; True if it was turned.

    Swapping the sequence numbers keeps every Terminal on its node and every reference to it. The
    sides of a SwitchPhase and the points of the branch's own Location turn with it. Transformers
    and regulators keep theirs: their Terminals are their windings' ends.
    """
    terminals = sorted(equipment.Terminals or [], key=lambda terminal: terminal.sequenceNumber)
    if isinstance(equipment, (cim.PowerTransformer, cim.AutoTransformer)) or len(terminals) != 2:
        return False
    first, second = terminals
    if first.ConnectivityNode is upstream_node:
        return False
    first.sequenceNumber, second.sequenceNumber = second.sequenceNumber, first.sequenceNumber
    for phase in getattr(equipment, "SwitchPhase", None) or []:
        phase.phaseSide1, phase.phaseSide2 = phase.phaseSide2, phase.phaseSide1
    location = equipment.Location
    if location and location.PowerSystemResources == [equipment] and location.PositionPoints:
        numbers = [point.sequenceNumber for point in location.PositionPoints]
        for point in location.PositionPoints:
            point.sequenceNumber = min(numbers) + max(numbers) - point.sequenceNumber
    return True


def _rename(obj, new_name: str) -> None:
    obj.uuid(mRID=new_name)  # mRID, and the identifier seeded from it under the new scope
    obj.name = None
    obj.aliasName = None
    obj.description = None


def _text_left(model: GraphModel) -> dict[str, int]:
    """Free-text attributes still set, by Class.attribute: candidates for filters.drop_attributes."""
    counts = Counter()
    for objects in model.graph.values():
        for obj in objects.values():
            for field in dataclasses.fields(obj):
                if field.name in IDENTITY_TEXT or field.type not in ("str", "Optional[str]"):
                    continue
                if getattr(obj, field.name) is not None:
                    counts[f"{type(obj).__name__}.{field.name}"] += 1
    return dict(sorted(counts.items()))
