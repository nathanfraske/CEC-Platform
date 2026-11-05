"""Native bank covers must generalize without sacrificing real source copper."""
import copy

import pcbnew
import pytest

import cec_pad_bank_collector as bank
import cec_rectilinear_copper as owner
from cec_local_copper_cell import copper_inventory


def fixture(angle=0, mirror=False, layer=pcbnew.F_Cu):
    b = pcbnew.CreateEmptyBoard(); b.SetCopperLayerCount(6)
    n = pcbnew.NETINFO_ITEM(b, "/UNRELATED_RENAMED_BANK"); b.Add(n)
    for a, z in [((0,0),(80,0)),((80,0),(80,80)),((80,80),(0,80)),((0,80),(0,0))]:
        edge = pcbnew.PCB_SHAPE(b); edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a)); edge.SetEnd(pcbnew.VECTOR2I_MM(*z))
        edge.SetLayer(pcbnew.Edge_Cuts); b.Add(edge)
    def at(x, y):
        if mirror: x = -x
        for _ in range(angle//90): x, y = -y, x
        return pcbnew.VECTOR2I_MM(40+x, 40+y)
    fp = pcbnew.FOOTPRINT(b); fp.SetReference("RENAMED_CONNECTOR"); b.Add(fp)
    pads = []
    for i, x in enumerate((0, 4.2, 8.4)):
        p = pcbnew.PAD(fp); fp.Add(p); p.SetNet(n); p.SetNumber(str(70+i))
        p.SetShape(pcbnew.PAD_SHAPE_OVAL); p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        p.SetLayerSet(pcbnew.PAD.PTHMask()); p.SetSize(pcbnew.VECTOR2I_MM(2.7,3.7))
        p.SetDrillSize(pcbnew.VECTOR2I_MM(1.8,1.8)); p.SetPosition(at(x,0))
        p.SetOrientationDegrees(angle); pads.append(p)
    tracks = []
    for x in (2.1,8.4):
        t = pcbnew.PCB_TRACK(b); t.SetNet(n); t.SetLayer(layer); t.SetLocked(True)
        t.SetStart(at(x,0)); t.SetEnd(at(x,-5.4)); t.SetWidth(3400000); b.Add(t); tracks.append(t)
    return b, pads, tracks


def proposal(b, pads, tracks, layer=pcbnew.F_Cu):
    return bank.plan(b, [p.m_Uuid.AsString() for p in pads], layer_id=layer,
        support_track_uuids=[t.m_Uuid.AsString() for t in tracks],
        clearance_nm=200000, min_thickness_nm=200000)


@pytest.mark.parametrize("angle", [0,90,180,270])
@pytest.mark.parametrize("mirror", [False,True])
@pytest.mark.parametrize("layer", [pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_solid_bank_covers_actual_oval_lands_and_caps_without_moving_them(tmp_path,angle,mirror,layer):
    b, pads, tracks = fixture(angle,mirror,layer); before = copper_inventory(b)
    p = proposal(b,pads,tracks,layer); assert copper_inventory(b) == before
    assert len(p["polygon_nm"]) == 8 and 0 < p["actual_chamfer_nm"] <= 600000
    assert all(owner._centerline_allowed(a,z,"chamfer45")
        for a,z in zip(p["polygon_nm"],p["polygon_nm"][1:]+p["polygon_nm"][:1]))
    emitted = bank.materialize(b,p); b.BuildConnectivity(); assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path = tmp_path/"bank.kicad_pcb"; pcbnew.SaveBoard(str(path),b)
    saved = pcbnew.LoadBoard(str(path)); result = bank.receive(saved,p,emitted["zone_uuid"])
    assert result["ok"] and result["complete"], result
    assert result["source_conductors_retained"] and not result["new_capacity_credited"]
    assert not result["release_authority"]


@pytest.mark.parametrize("fault", ["foreign", "changed_pad", "changed_track", "rehashed_envelope", "rehashed_authority"])
def test_bank_refuses_foreign_copper_changed_sources_and_tampered_geometry_without_mutation(fault):
    b,pads,tracks = fixture(); p = proposal(b,pads,tracks)
    if fault == "foreign":
        n = pcbnew.NETINFO_ITEM(b,"/OTHER_NET"); b.Add(n)
        fp = pcbnew.FOOTPRINT(b); b.Add(fp); pad = pcbnew.PAD(fp); fp.Add(pad)
        pad.SetNet(n); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetLayerSet(pcbnew.PAD.SMDMask()); pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
        pad.SetPosition(pcbnew.VECTOR2I_MM(44.2,37))
    elif fault == "changed_pad": pads[0].SetDrillSize(pcbnew.VECTOR2I_MM(1.7,1.7))
    elif fault == "changed_track": tracks[0].SetWidth(3399999)
    else:
        p = copy.deepcopy(p)
        if fault == "rehashed_envelope": p["polygon_nm"][0][0] += 1
        else: p["release_authority"] = True
        p.pop("plan_sha256"); p["plan_sha256"] = owner._digest(p)
    before = copper_inventory(b)
    with pytest.raises(bank.Refused): bank.materialize(b,p)
    assert copper_inventory(b) == before


@pytest.mark.parametrize("fault", ["mixed_net", "not_row", "missing", "duplicate", "unrated_claim"])
def test_explicit_same_net_row_is_not_inferred_from_nearness_or_names(fault):
    b,pads,tracks = fixture()
    ids = [p.m_Uuid.AsString() for p in pads]
    if fault == "mixed_net": pads[0].SetNetCode(0)
    elif fault == "not_row": pads[0].Move(pcbnew.VECTOR2I(0,1))
    elif fault == "missing": ids[0] = "not-a-native-uuid"
    elif fault == "duplicate": ids[0] = ids[1]
    else: tracks[0].SetEnd(pcbnew.VECTOR2I_MM(60,60))
    with pytest.raises(bank.Refused):
        bank.plan(b,ids,layer_id=pcbnew.F_Cu,support_track_uuids=[t.m_Uuid.AsString() for t in tracks],
                  clearance_nm=200000,min_thickness_nm=200000)


@pytest.mark.parametrize("fault", ["unfilled", "thermal_relief", "source_loss", "spill", "deadline"])
def test_saved_receiving_rejects_unfilled_relieved_trimmed_or_unbound_copper(fault):
    b,pads,tracks = fixture(); p = proposal(b,pads,tracks); emitted = bank.materialize(b,p)
    z = next(z for z in b.Zones() if z.m_Uuid.AsString() == emitted["zone_uuid"])
    b.BuildConnectivity(); assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    if fault == "unfilled": z.UnFill()
    elif fault == "thermal_relief": z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    elif fault in ("source_loss", "spill"):
        fill = z.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
        if fault == "source_loss":
            cut = owner._poly([[40000000,39999999],[40000001,39999999],
                               [40000001,40000000],[40000000,40000000]])
            fill.BooleanSubtract(cut)
        else: fill.BooleanAdd(owner._poly([[44000000,41000000],[44000001,41000000],
                                          [44000001,45000000],[44000000,45000000]]))
        z.SetFilledPolysList(pcbnew.F_Cu,fill)
    received = bank.receive(b,p,emitted["zone_uuid"],timeout_s=0 if fault == "deadline" else 10.)
    assert not received["ok"] and not received["complete"], received


@pytest.mark.parametrize("angle", [0,90,180,270])
@pytest.mark.parametrize("mirror", [False,True])
@pytest.mark.parametrize("layer", [pcbnew.F_Cu,pcbnew.B_Cu])
def test_pad_only_bank_closes_native_islands_without_inventing_stems_or_capacity(tmp_path,angle,mirror,layer):
    b,pads,tracks=fixture(angle,mirror,layer)
    # Existing support is retained, but it is not claimed as the source of a
    # new current rating or a mandatory stem in a pad-only collector.
    original=copper_inventory(b)
    poses=[(tuple(p.GetPosition()),tuple(p.GetDrillSize()),tuple(p.GetSize())) for p in pads]
    p=bank.plan(b,[pad.m_Uuid.AsString() for pad in pads],layer_id=layer,
        clearance_nm=200000,min_thickness_nm=200000)
    assert p['retained_source_tracks']==[] and not p['new_capacity_credited']
    assert copper_inventory(b)==original
    emitted=bank.materialize(b,p);b.BuildConnectivity()
    assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path=tmp_path/'unrelated-pad-only-bank.kicad_pcb'
    pcbnew.SaveBoard(str(path),b);saved=pcbnew.LoadBoard(str(path))
    proof=bank.receive(saved,p,emitted['zone_uuid'])
    assert proof['ok'] and proof['complete'] and proof['retained_track_count']==0
    native=pcbnew.CONNECTIVITY_DATA()
    saved_pads={pad.m_Uuid.AsString():pad for fp in saved.GetFootprints() for pad in fp.Pads()}
    for item in [*saved_pads.values(),*saved.GetTracks(),*saved.Zones()]:
        assert native.Add(item)
    connected={pads[0].m_Uuid.AsString()}|{item.m_Uuid.AsString()
        for item in native.GetConnectedItems(saved_pads[pads[0].m_Uuid.AsString()])}
    assert {pad.m_Uuid.AsString() for pad in pads}<=connected
    assert [(tuple(saved_pads[pad.m_Uuid.AsString()].GetPosition()),
        tuple(saved_pads[pad.m_Uuid.AsString()].GetDrillSize()),
        tuple(saved_pads[pad.m_Uuid.AsString()].GetSize())) for pad in pads]==poses
    assert not proof['new_capacity_credited'] and not proof['release_authority']
