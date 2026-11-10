import dataclasses

import cimprofiles.cim18.cim18v17 as cim
import pytest

from grid_reducer import filters
from grid_reducer.config_models import Filters


def objects(model, cls):
    return list(model.graph.get(cls, {}).values())


def test_parts_name_real_associations():
    for owner_name, association in filters.PARTS:
        owner = getattr(cim, owner_name)
        assert association in {f.name for f in dataclasses.fields(owner)}, (
            owner_name,
            association,
        )


def test_drop_class_takes_its_parts(ieee13):
    terminals, nodes = (
        len(objects(ieee13, cim.Terminal)),
        len(objects(ieee13, cim.ConnectivityNode)),
    )
    report = filters.run(ieee13, Filters(drop_classes=["Recloser"]))

    assert objects(ieee13, cim.Recloser) == []
    assert objects(ieee13, cim.RecloseSequence) == []
    assert report["deleted"] == {"Recloser": 1}
    assert report["deleted_parts"]["Terminal"] == 2
    assert report["deleted_parts"]["RecloseSequence"] == 3
    assert report["deleted_parts"]["Location"] == 1
    assert len(objects(ieee13, cim.Terminal)) == terminals - 2
    assert len(objects(ieee13, cim.ConnectivityNode)) == nodes
    assert all(t.ConductingEquipment is not None for t in objects(ieee13, cim.Terminal))
    assert all(p.Location is not None for p in objects(ieee13, cim.PositionPoint))
    assert report["references_removed_from_kept"]["ConnectivityNode.Terminals"] == 2


def test_drop_class_includes_subclasses(ieee13):
    switches = sum(len(objects(ieee13, c)) for c in (cim.Fuse, cim.LoadBreakSwitch, cim.Recloser))
    report = filters.run(ieee13, Filters(drop_classes=["Switch"]))
    assert sum(report["deleted"].values()) == switches
    assert objects(ieee13, cim.SwitchPhase) == []
    assert not any(issubclass(cls, cim.Switch) and objs for cls, objs in ieee13.graph.items())


def test_drop_function_blocks(protection):
    report = filters.run(
        protection, Filters(drop_classes=["FunctionBlock", "ProtectionFunctionBlock"])
    )
    assert report["deleted"] == {"FunctionBlock": 1, "OverCurrentProtectionFunctionBlock": 1}
    assert report["deleted_parts"] == {"FunctionOutputVariable": 1}
    assert len(objects(protection, cim.Breaker)) == 1


def test_protection_blocks_are_not_function_blocks(protection):
    # cim18v17's ProtectionFunctionBlock tree does not inherit from FunctionBlock.
    filters.run(protection, Filters(drop_classes=["FunctionBlock"]))
    assert len(objects(protection, cim.OverCurrentProtectionFunctionBlock)) == 1


def test_shared_location_outlives_one_owner(protection):
    breaker = objects(protection, cim.Breaker)[0]
    feeder = objects(protection, cim.Feeder)[0]
    protection.modify(feeder, "Location", breaker.Location)
    filters.run(protection, Filters(drop_classes=["Breaker"]))
    assert objects(protection, cim.Location) == [feeder.Location]
    assert len(objects(protection, cim.PositionPoint)) == 2


def test_drop_attributes(ieee13):
    report = filters.run(ieee13, Filters(drop_attributes=["Fuse.ratedCurrent"]))
    assert report["cleared_attributes"] == {"Fuse.ratedCurrent": 1}
    assert all(fuse.ratedCurrent is None for fuse in objects(ieee13, cim.Fuse))


def test_dropping_a_required_reference_raises(protection, monkeypatch):
    without_terminals = [
        pair for pair in filters.OWNED if pair != (cim.ConductingEquipment, "Terminals")
    ]
    monkeypatch.setattr(filters, "OWNED", without_terminals)
    with pytest.raises(ValueError, match="lost its required ConductingEquipment"):
        filters.run(protection, Filters(drop_classes=["Breaker"]))


@pytest.mark.parametrize(
    "bad, message",
    [
        (Filters(drop_classes=["Recloserr"]), "did you mean Recloser"),
        (Filters(drop_attributes=["Fuse.ratedCurent"]), "no attribute"),
        (Filters(drop_attributes=["IdentifiedObject.mRID"]), "rename pass"),
        (Filters(drop_attributes=["ConductingEquipment.Terminals"]), "list of references"),
        (Filters(drop_attributes=["Terminal.ConductingEquipment"]), "required"),
    ],
)
def test_check_rejects(bad, message):
    with pytest.raises(ValueError, match=message):
        filters.check(bad)
