import re
from collections import Counter

import cimprofiles.cim18.cim18v17 as cim
import cimtables
from cimtables import document
import pytest

from grid_reducer import model_io, rename
from grid_reducer.config_models import Rename


def all_objects(model):
    return [obj for objects in model.graph.values() for obj in objects.values()]


def write(model, directory):
    master = model_io.write_cimtbl(model, "out", directory / "cimtbl")
    model_io.write_cim_xml(model, directory / "out.xml")
    return master


def tokens(directory):
    text = "\n".join(path.read_text() for path in directory.rglob("*") if path.is_file())
    return set(re.findall(r"[\w.-]+", text.lower()))


def cimtbl_text(master):
    return "\n".join(path.read_text() for path in sorted(master.parent.glob("*.cimtbl")))


def node_degrees(model):
    return sorted(len(node.Terminals) for node in model.graph[cim.ConnectivityNode].values())


def test_no_source_identity_is_written(ieee13, tmp_path):
    originals = set()
    for obj in all_objects(ieee13):
        originals.add(str(obj.identifier).lower())
        # BaseVoltages are named by their (published) voltage, as the source already does
        if getattr(obj, "mRID", None) and not isinstance(obj, cim.BaseVoltage):
            originals.add(obj.mRID.lower())
    assert len(originals) > 500

    report = rename.run(ieee13, Rename(), seed=1)
    master = write(ieee13, tmp_path)

    assert originals & tokens(tmp_path) == set()
    assert "Model = feeder" in master.read_text()
    assert report["scope"] == {"authority": rename.AUTHORITY, "model": "feeder"}


def test_prefixed_names_are_dense(ieee13):
    before = Counter(type(obj).__name__ for obj in all_objects(ieee13))
    report = rename.run(ieee13, Rename(), seed=1)
    assert report["renamed"] == dict(sorted(before.items()))
    assert report["unprefixed"] == {
        "BaseFrequency": 1,
        "CoordinateSystem": 1,
        "OperationalLimitType": 2,
    }
    numbers = {}
    for obj in all_objects(ieee13):
        match = re.fullmatch(r"([a-z]+)_(\d+)", getattr(obj, "mRID", None) or "")
        if match:
            numbers.setdefault(match[1], []).append(match[2])
    assert {"cn", "ln", "sw", "xf", "vr", "ld", "cap", "pv", "storage", "lc", "src"} <= set(
        numbers
    )
    for prefix, digits in numbers.items():
        width = len(str(len(digits)))
        assert sorted(digits) == [f"{n:0{width}d}" for n in range(1, len(digits) + 1)], prefix
    for cls, objects in ieee13.graph.items():
        assert all(key == obj.identifier for key, obj in objects.items())
        if "mRID" in cls.__dataclass_fields__:
            assert all(obj.name is None and obj.description is None for obj in objects.values())


def test_children_extend_their_parent(ieee13):
    rename.run(ieee13, Rename(), seed=1)
    for terminal in ieee13.graph[cim.Terminal].values():
        assert terminal.mRID == f"{terminal.ConductingEquipment.mRID}_T{terminal.sequenceNumber}"
    for phase in ieee13.graph[cim.ACLineSegmentPhase].values():
        assert phase.mRID == f"{phase.ACLineSegment.mRID}_{phase.phase.value}"
    for end in ieee13.graph[cim.PowerTransformerEnd].values():
        assert end.mRID == f"{end.PowerTransformer.mRID}_{end.endNumber}"
    for location in ieee13.graph[cim.Location].values():
        assert location.mRID == f"{location.PowerSystemResources[0].mRID}_loc"
    bv = {obj.mRID for obj in ieee13.graph[cim.BaseVoltage].values()}
    assert {"bv_4p16kv", "bv_480v", "bv_115kv"} <= bv


def test_names_fold_like_the_loaders(ieee13, tmp_path):
    # Terminals and phase children carry the mRIDs the cimtables loader generates, so the
    # writer can fold them into node/phases columns and a reload gives back the same model.
    rename.run(ieee13, Rename(), seed=1)
    documents = cimtables.to_documents(ieee13, "out", terminals="folded")
    master = document.write_documents(documents, tmp_path)
    text = "\n".join(path.read_text() for path in tmp_path.glob("*.cimtbl"))
    assert "Table Terminal:" not in text
    assert cimtables.diff_models(ieee13, cimtables.load_model(master)) == []


def test_structure_survives_a_reload(ieee13, tmp_path):
    degrees, counts = node_degrees(ieee13), model_io.class_counts(ieee13)
    rename.run(ieee13, Rename(), seed=1)
    master = write(ieee13, tmp_path)
    reloaded = cimtables.load_model(master)
    assert cimtables.diff_models(ieee13, reloaded) == []
    assert model_io.class_counts(reloaded) == counts
    assert node_degrees(reloaded) == degrees
    feeder = next(iter(ieee13.graph[cim.Feeder].values()))
    assert ieee13.find_by_mRID("fdr_1") is feeder


def test_seed_reproduces_the_numbering(ieee13_path, tmp_path):
    texts = []
    for run_number, seed in enumerate([7, 7, 8]):
        model = model_io.load_model(ieee13_path)
        rename.run(model, Rename(model_name="published"), seed=seed)
        texts.append(cimtbl_text(write(model, tmp_path / str(run_number))))
    assert texts[0] == texts[1]
    assert texts[0] != texts[2]


def test_reports_free_text_left(protection):
    location = next(iter(protection.graph[cim.Location].values()))
    location.geoInfoReference = "GIS-123"
    report = rename.run(protection, Rename(), seed=1)
    assert report["text_left"]["Location.geoInfoReference"] == 1
    assert not any(key.endswith((".name", ".mRID")) for key in report["text_left"])


def number(obj):
    return int(obj.mRID.rsplit("_", 1)[1])


def test_numbering_starts_at_the_source(ieee13):
    rename.run(ieee13, Rename(), seed=1)
    source = next(iter(ieee13.graph[cim.EnergySource].values()))
    assert source.mRID == "src_1"
    assert source.Terminals[0].mRID == "src_1_T1"
    assert number(source.Terminals[0].ConnectivityNode) == 1


def test_every_node_is_reached_from_a_lower_number(ieee13):
    rename.run(ieee13, Rename(), seed=1)
    neighbors = {}
    for cls, objects in ieee13.graph.items():
        if not issubclass(cls, cim.ConductingEquipment):
            continue
        for equipment in objects.values():
            nodes = {terminal.ConnectivityNode for terminal in equipment.Terminals}
            for node in nodes:
                neighbors.setdefault(node, set()).update(nodes - {node})
    for node, adjacent in neighbors.items():
        if number(node) > 1:
            assert min(number(other) for other in adjacent) < number(node), node.mRID


@pytest.mark.parametrize("seed", range(5))
def test_lines_follow_the_walk(ieee13, seed):
    # Depth first, a fork's later branch starts from a lower node number than the path just
    # walked, but each line reaches a new node numbered after every node reached before it.
    # (Not a link: a parallel line or one closing a loop reaches no new node. IEEE13 has none.)
    rename.run(ieee13, Rename(), seed=seed)
    lines = sorted(ieee13.graph[cim.ACLineSegment].values(), key=number)
    downstream = [max(number(t.ConnectivityNode) for t in line.Terminals) for line in lines]
    assert downstream == sorted(downstream)


def two_terminal_branches(model):
    for cls, objects in model.graph.items():
        if issubclass(cls, cim.ConductingEquipment) and not issubclass(
            cls, (cim.PowerTransformer, cim.AutoTransformer)
        ):
            yield from (obj for obj in objects.values() if len(obj.Terminals) == 2)


def by_sequence(equipment):
    return sorted(equipment.Terminals, key=lambda terminal: terminal.sequenceNumber)


def point_at(terminal):
    location = terminal.ConductingEquipment.Location
    (point,) = [p for p in location.PositionPoints if p.sequenceNumber == terminal.sequenceNumber]
    return point.xPosition, point.yPosition


@pytest.mark.parametrize("seed", range(3))
def test_branches_point_away_from_the_source(ieee13, seed):
    rename.run(ieee13, Rename(), seed=seed)
    for branch in two_terminal_branches(ieee13):
        first, second = by_sequence(branch)
        assert number(first.ConnectivityNode) < number(second.ConnectivityNode), branch.mRID
        assert (first.mRID, second.mRID) == (f"{branch.mRID}_T1", f"{branch.mRID}_T2")


def test_turned_branches_keep_their_points_and_sides(ieee13):
    # Turn every line backwards first (terminals and points together), so rename must turn them all.
    lines = list(ieee13.graph[cim.ACLineSegment].values())
    for line in lines:
        first, second = by_sequence(line)
        first.sequenceNumber, second.sequenceNumber = 2, 1
        for point in line.Location.PositionPoints:
            point.sequenceNumber = 3 - point.sequenceNumber
    switch_phase = next(iter(ieee13.graph[cim.SwitchPhase].values()))
    upstream, downstream = by_sequence(switch_phase.Switch)
    upstream.sequenceNumber, downstream.sequenceNumber = 2, 1
    side_a_terminal = downstream  # now Terminal 1, so phaseSide1 is its side
    switch_phase.phaseSide1 = cim.SinglePhaseKind("A")
    switch_phase.phaseSide2 = cim.SinglePhaseKind("B")
    points = {terminal: point_at(terminal) for line in lines for terminal in line.Terminals}

    report = rename.run(ieee13, Rename(), seed=1)

    assert report["reoriented"]["ACLineSegment"] == len(lines)
    assert report["reoriented"][type(switch_phase.Switch).__name__] == 1
    assert side_a_terminal.sequenceNumber == 2
    assert all(point_at(terminal) == xy for terminal, xy in points.items())
    side = getattr(switch_phase, f"phaseSide{side_a_terminal.sequenceNumber}")
    assert side == cim.SinglePhaseKind("A")
