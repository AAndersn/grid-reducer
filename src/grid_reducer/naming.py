"""Compact mRIDs following the CIMTBL-Models conventions (.claude/skills/cimtbl-translate).

Top-level classes get the convention's prefix plus a number, in the order given (``cn_0001``,
``ln_0001``, ``sw_001``); BaseVoltages are named by voltage (``bv_12p47kv``). Child rows extend their
parent's mRID with the convention's suffix, so Terminals and phase children get the names the
cimtables loader generates (``ln_0001_T1``, ``ln_0001_A``). A name already taken gets ``_2``,
``_3``, ... Objects no rule covers are numbered ``<Class>_<n>``; Identity-only objects with a
parent rule get the key their UUID is seeded from (``<loc>_<seq>``, ``<lc>_<row><column>``).
"""

from collections import Counter
from collections.abc import Callable

import cimprofiles.cim18.cim18v17 as cim

# (class, prefix) in match order: an object takes the first class it is an instance of
PREFIXES = (
    (cim.ConnectivityNode, "cn"),
    (cim.TopologicalNode, "tn"),
    (cim.SubGeographicalRegion, "srgn"),
    (cim.GeographicalRegion, "rgn"),
    (cim.Substation, "sub"),
    (cim.Feeder, "fdr"),
    (cim.ConnectedArea, "area"),
    (cim.LoadResponseCharacteristic, "zip"),
    (cim.EnergySource, "src"),
    (cim.ACLineSegment, "ln"),
    (cim.Switch, "sw"),
    (cim.VoltageRegulator, "vr"),
    (cim.PowerTransformer, "xf"),
    (cim.EnergyConsumer, "ld"),
    (cim.LinearShuntCompensator, "cap"),
    (cim.PerLengthPhaseImpedance, "lc"),
    (cim.TransformerTankConfiguration, "xc"),
    (cim.TransformerBankConfiguration, "xb"),
    (cim.OverheadWireInfo, "wire"),
    (cim.CableInfo, "cable"),
    (cim.XYSpacing, "spc"),
    (cim.WireConfiguration, "wc"),
)


def _end_owner(end):
    if end is None:
        return None
    if isinstance(end, cim.PowerTransformerEnd):
        return end.PowerTransformer
    if isinstance(end, cim.AutoTransformerEnd):
        return end.AutoTransformer
    return end.Terminal.ConductingEquipment if end.Terminal else None


def _limit_owner(limit_set):
    if limit_set is None:
        return None
    return limit_set.Equipment or (limit_set.Terminal and limit_set.Terminal.ConductingEquipment)


def _lugs(winding) -> str:
    """h1h2: the designations of the lugs a winding runs between."""
    lugs = (winding.FromTransformerLug, winding.ToTransformerLug)
    return "".join((lug.designation or "").lower() for lug in lugs if lug)


def _mesh(mesh):
    if mesh.FromTransformerEnd:
        ends = f"{mesh.FromTransformerEnd.endNumber}{mesh.ToTransformerEnd.endNumber}"
        return _end_owner(mesh.FromTransformerEnd), f"mesh_{ends}"
    windings = f"{_lugs(mesh.FromWinding)}_{_lugs(mesh.ToWinding)}"
    return mesh.FromWinding.TankConfiguration, f"mesh_{windings}"


def _phase(value) -> str:
    return value.value


def _shunt_phase(child, parent) -> tuple[object, str]:
    """A delta shunt's child is named by its branch (phases=BC), as the cimtables loader does."""
    if getattr(parent, "phaseConnection", None) == cim.PhaseShuntConnectionKind.D and child.phases:
        return parent, _phase(child.phases)
    return parent, _phase(child.phase)


def _first(objects):
    return objects[0] if objects else None


# class -> obj -> (parent, suffix), in an order where every parent is named before its children
Rule = Callable[[object], tuple[object, str]]
CHILDREN: tuple[tuple[type, Rule], ...] = (
    (cim.Terminal, lambda t: (t.ConductingEquipment, f"T{t.sequenceNumber}")),
    (cim.ACLineSegmentPhase, lambda p: (p.ACLineSegment, _phase(p.phase))),
    (cim.EnergyConsumerPhase, lambda p: _shunt_phase(p, p.EnergyConsumer)),
    (cim.EnergySourcePhase, lambda p: (p.EnergySource, _phase(p.phase))),
    (cim.ShuntCompensatorPhase, lambda p: _shunt_phase(p, p.ShuntCompensator)),
    (
        cim.PowerElectronicsConnectionPhase,
        lambda p: _shunt_phase(p, p.PowerElectronicsConnection),
    ),
    (cim.SwitchPhase, lambda p: (p.Switch, _phase(p.phaseSide1))),
    (cim.PowerTransformerEnd, lambda e: (e.PowerTransformer, str(e.endNumber))),
    (cim.AutoTransformerEnd, lambda e: (e.AutoTransformer, str(e.endNumber))),
    (cim.TransformerPhaseEnd, lambda e: (_end_owner(e), f"{e.endNumber}_{_phase(e.phase)}")),
    (cim.TransformerTank, lambda t: (t.PowerTransformer, "tank")),
    (cim.RatioTapChanger, lambda t: (_end_owner(t.TransformerEnd), "tap")),
    (
        cim.TapChangerControl,
        lambda c: (_first([_end_owner(t.TransformerEnd) for t in c.TapChanger or []]), "ctrl"),
    ),
    (cim.RegulatingControl, lambda c: (_first(c.RegulatingCondEq), "ctrl")),
    (
        cim.TransformerLug,
        lambda lug: (lug.TankConfiguration, f"lug_{(lug.designation or '').lower()}"),
    ),
    (cim.TransformerWinding, lambda w: (w.TankConfiguration, f"wdg_{_lugs(w)}")),
    (cim.TransformerMeshImpedance, _mesh),
    (cim.TransformerCore, lambda core: (core.TankConfiguration, "core")),
    (cim.OperationalLimitSet, lambda s: (_limit_owner(s), "limits")),
    (cim.CurrentLimit, lambda limit: (_limit_owner(limit.OperationalLimitSet), "norm")),
    (cim.PowerElectronicsUnit, lambda u: (u.PowerElectronicsConnection, "unit")),
    (cim.RecloseSequence, lambda r: (r.ProtectedSwitch, f"rs{r.recloseStep}")),
    (cim.XYConductorPosition, lambda p: (p.XYSpacing, str(p.sequenceNumber))),
    (cim.WireSequenceConfiguration, lambda w: (w.WireConfiguration, str(w.sequenceNumber))),
    (cim.Location, lambda loc: (_first(loc.PowerSystemResources), "loc")),
)
# Identity-only classes: obj -> (parent, suffix) of the key their UUID is seeded from
IDENTITY_KEYS: tuple[tuple[type, Rule], ...] = (
    (cim.PositionPoint, lambda p: (p.Location, str(p.sequenceNumber))),
    (cim.PhaseImpedanceData, lambda d: (d.PhaseImpedance, f"{d.row}{d.column}")),
)


def assign(ordered: dict[type, list]) -> tuple[dict, dict, Counter]:
    """New mRIDs (obj -> str), seed keys of Identity-only objects (obj -> str), and the count of
    objects per class that no rule covered. ``ordered`` lists each class's objects in the order
    they are numbered."""
    objects = [obj for class_objects in ordered.values() for obj in class_objects]
    names, taken = {}, set()

    def claim(obj, name: str) -> None:
        unique, copy = name, 1
        while unique in taken:
            copy += 1
            unique = f"{name}_{copy}"
        taken.add(unique)
        names[obj] = unique

    groups = {}
    for obj in objects:
        if isinstance(obj, cim.BaseVoltage):
            claim(obj, _base_voltage_name(obj))
            continue
        prefix = _prefix(obj)
        if prefix:
            groups.setdefault(prefix, []).append(obj)
    for prefix, members in groups.items():
        width = len(str(len(members)))
        for number, obj in enumerate(members, start=1):
            claim(obj, f"{prefix}_{number:0{width}d}")

    for cls, rule in CHILDREN:
        for obj in objects:
            if obj in names or not isinstance(obj, cls):
                continue
            parent, suffix = rule(obj)
            if parent in names:
                claim(obj, f"{names[parent]}_{suffix}")

    unprefixed = Counter()
    for cls, class_objects in ordered.items():
        rest = [obj for obj in class_objects if obj not in names]
        if "mRID" not in cls.__dataclass_fields__ or not rest:
            continue
        unprefixed[cls.__name__] = len(rest)
        width = len(str(len(rest)))
        for number, obj in enumerate(rest, start=1):
            claim(obj, f"{cls.__name__}_{number:0{width}d}")

    seed_keys = {}
    for cls, rule in IDENTITY_KEYS:
        for obj in objects:
            if isinstance(obj, cls):
                parent, suffix = rule(obj)
                if parent in names:
                    seed_keys[obj] = f"{names[parent]}_{suffix}"
    return names, seed_keys, unprefixed


def _prefix(obj) -> str | None:
    if isinstance(obj, cim.PowerElectronicsConnection):
        units = obj.PowerElectronicsUnit or []
        if units and all(isinstance(unit, cim.PhotoVoltaicUnit) for unit in units):
            return "pv"
        if units and all(isinstance(unit, cim.BatteryUnit) for unit in units):
            return "storage"
        return "pec"
    for cls, prefix in PREFIXES:
        if isinstance(obj, cls):
            return prefix
    return None


def _base_voltage_name(base_voltage) -> str:
    """bv_4p16kv, bv_480v: the nominal voltage, kV from 1 kV up."""
    volts = base_voltage.nominalVoltage.to("V")
    if volts >= 1000:
        return f"bv_{base_voltage.nominalVoltage.to('kV'):g}kv".replace(".", "p")
    return f"bv_{volts:g}v".replace(".", "p")
