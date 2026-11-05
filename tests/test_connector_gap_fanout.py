"""Native connector-gap proposals generalize across orientation, names/layers."""
import copy

import pcbnew
import pytest

import cec_connector_gap_fanout as gap
from cec_local_copper_cell import copper_inventory


def fixture(angle=0, mirror=False, name="/ARBITRARY_POWER", pitch=4.2, row_gap=5.5,
            pad_size=(2.7,3.7)):
    b = pcbnew.CreateEmptyBoard(); b.SetCopperLayerCount(6)
    own = pcbnew.NETINFO_ITEM(b, name); other = pcbnew.NETINFO_ITEM(b, "/UNRELATED_FOREIGN")
    b.Add(own); b.Add(other)
    for a,z in [((0,0),(80,0)),((80,0),(80,80)),((80,80),(0,80)),((0,80),(0,0))]:
        e = pcbnew.PCB_SHAPE(b); e.SetShape(pcbnew.SHAPE_T_SEGMENT)
        e.SetLayer(pcbnew.Edge_Cuts); e.SetStart(pcbnew.VECTOR2I_MM(*a)); e.SetEnd(pcbnew.VECTOR2I_MM(*z)); b.Add(e)
    def at(x,y):
        if mirror: x = -x
        for _ in range(angle//90): x,y = -y,x
        return pcbnew.VECTOR2I_MM(40+x,40+y)
    fp = pcbnew.FOOTPRINT(b); fp.SetReference("RENAMED_NATIVE_CONNECTOR"); b.Add(fp)
    pads = {}; roots = []
    for y in (0,row_gap):
        for i in range(-3,4):
            p = pcbnew.PAD(fp); fp.Add(p); p.SetNumber(str(len(pads)+1))
            p.SetAttribute(pcbnew.PAD_ATTRIB_PTH); p.SetLayerSet(pcbnew.PAD.PTHMask())
            p.SetShape(pcbnew.PAD_SHAPE_OVAL); p.SetSize(pcbnew.VECTOR2I_MM(*pad_size))
            p.SetDrillSize(pcbnew.VECTOR2I_MM(1.8,1.8)); p.SetOrientationDegrees(angle)
            p.SetPosition(at(i*pitch,y))
            p.SetNet(own if y==row_gap and i in (0,2) or y==0 and i==-2 else other)
            pads[(i,y)] = p
            if y==row_gap and i in (0,2): roots.append(p)
    tracks = []
    for layer in (pcbnew.F_Cu,pcbnew.B_Cu):
        t = pcbnew.PCB_TRACK(b); t.SetNet(own); t.SetLayer(layer); t.SetWidth(3400000)
        t.SetStart(at(-3*pitch,-4.5)); t.SetEnd(at(3*pitch,-4.5)); t.SetLocked(True); b.Add(t); tracks.append(t)
        # Real retained connection to the actual plated merge land.
        t = pcbnew.PCB_TRACK(b); t.SetNet(own); t.SetLayer(layer); t.SetWidth(3400000)
        t.SetStart(at(-2*pitch,0)); t.SetEnd(at(-2*pitch,-4.5)); b.Add(t)
    return b,roots,pads[(-2,0)],tracks,other,at


def propose(b,roots,merge,tracks, width=950000):
    layers = ["F.Cu","B.Cu","In2.Cu","In3.Cu"]
    return gap.plan(b,[gap._uid(p) for p in roots],layer_widths_nm={l:width for l in layers},
        allowed_layers=layers,collector_track_uuids=[gap._uid(t) for t in tracks],
        merge_pad_uuids=[gap._uid(merge)],clearance_nm=200000)


@pytest.mark.parametrize("angle",[0,90,180,270])
@pytest.mark.parametrize("mirror",[False,True])
@pytest.mark.parametrize("name",["/ARBITRARY_POWER","/UNRELATED_HIERARCHY/VRAIL"])
def test_native_four_layer_gap_recombination_saved_contacts_and_no_source_mutation(tmp_path,angle,mirror,name):
    b,roots,merge,tracks,_,_ = fixture(angle,mirror,name)
    before = copper_inventory(b); p = propose(b,roots,merge,tracks)
    assert copper_inventory(b) == before
    assert p["all_requested_paths_clear"] and p["root_geometry_coverage_complete"],p["refused_paths"]
    assert len(p["valid_paths"]) == 16
    assert not p["arbitrary_equal_current_sharing_assumed"] and not p["current_qualified"]
    emitted = gap.materialize_private(b,p)
    assert emitted["no_added_vias"] and not emitted["routing_admitted"]
    after = copper_inventory(b)
    assert all(after[k] == v for k,v in before.items())
    path=tmp_path/"native-gap-candidate.kicad_pcb"; pcbnew.SaveBoard(str(path),b)
    saved=pcbnew.LoadBoard(str(path)); saved.BuildConnectivity()
    sp={gap._uid(p):p for f in saved.GetFootprints() for p in f.Pads()}
    for root in roots:
        connected={gap._uid(p) for p in saved.GetConnectivity().GetConnectedItems(sp[gap._uid(root)])}
        assert gap._uid(merge) in connected
    for t in saved.GetTracks():
        if gap._uid(t) not in emitted["added_track_uuids"]: continue
        a,z=t.GetStart(),t.GetEnd(); dx,dy=abs(a.x-z.x),abs(a.y-z.y)
        assert dx==0 or dy==0 or dx==dy


@pytest.mark.parametrize("fault",["foreign_track","foreign_land","native_rule_area","undersized_gap"])
def test_actual_native_blocker_refuses_branch_and_construction_without_mutation(fault):
    b,roots,merge,tracks,other,at=fixture(pitch=3.6 if fault=="undersized_gap" else 4.2)
    if fault=="foreign_track":
        t=pcbnew.PCB_TRACK(b); t.SetNet(other); t.SetLayer(pcbnew.In2_Cu); t.SetWidth(200000)
        t.SetStart(at(-1,1)); t.SetEnd(at(3.1,1)); b.Add(t)
    elif fault=="foreign_land":
        fp=pcbnew.FOOTPRINT(b); b.Add(fp); p=pcbnew.PAD(fp); fp.Add(p)
        p.SetNet(other); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetSize(pcbnew.VECTOR2I_MM(.3,.3)); p.SetPosition(at(2.1,1))
    elif fault=="native_rule_area":
        z=pcbnew.ZONE(b); z.SetIsRuleArea(True); z.SetDoNotAllowTracks(True); z.SetLayer(pcbnew.In2_Cu)
        poly=z.Outline(); poly.NewOutline()
        for pt in ((1,1),(3,1),(3,2),(1,2)):
            v=at(*pt); poly.Append(v.x,v.y)
        b.Add(z)
    before=copper_inventory(b); p=propose(b,roots,merge,tracks)
    assert p["geometry_complete"] and p["refused_paths"] and not p["all_requested_paths_clear"]
    if fault!="undersized_gap": assert any(r["native_blockers"] for r in p["refused_paths"])
    with pytest.raises(gap.Refused): gap.materialize_private(b,p)
    assert copper_inventory(b)==before


@pytest.mark.parametrize("fault",["changed_land","changed_track","tampered_path","capacity_claim","disabled_layer","plane","wrong_merge","missing_column"])
def test_identity_layer_and_capacity_boundaries_are_fail_closed(fault):
    b,roots,merge,tracks,other,at=fixture(); p=propose(b,roots,merge,tracks)
    if fault=="changed_land": roots[0].SetDrillSize(pcbnew.VECTOR2I_MM(1.7,1.7))
    elif fault=="changed_track": tracks[0].SetWidth(3399999)
    elif fault in ("tampered_path","capacity_claim"):
        p=copy.deepcopy(p)
        if fault=="tampered_path": p["valid_paths"][0]["points_nm"][1][0]+=1
        else: p["current_qualified"]=True
        p.pop("plan_sha256"); p["plan_sha256"]=gap._digest(p)
    elif fault=="disabled_layer": b.SetCopperLayerCount(2)
    elif fault=="plane":
        z=pcbnew.ZONE(b); z.SetLayer(pcbnew.In2_Cu); poly=z.Outline(); poly.NewOutline()
        for x,y in ((0,0),(80,0),(80,80),(0,80)): poly.Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
        b.Add(z)
    elif fault=="wrong_merge": merge.SetNet(other)
    else:
        fp=roots[0].GetParentFootprint(); p0=next(p0 for p0 in fp.Pads() if tuple(p0.GetPosition())==tuple(at(4.2,0)))
        fp.Remove(p0)
    before=copper_inventory(b)
    with pytest.raises(gap.Refused): gap.materialize_private(b,p)
    assert copper_inventory(b)==before


@pytest.mark.parametrize("fault",["no_merge","lower_clearance","deadline","nonintegral_column"])
def test_explicit_bounded_requests_do_not_invent_contact_or_relax_clearance(fault):
    b,roots,merge,tracks,_,at=fixture()
    request=dict(layer_widths_nm={"In2.Cu":950000},allowed_layers=["In2.Cu"],
        merge_pad_uuids=[gap._uid(merge)],clearance_nm=200000)
    if fault=="no_merge": request["merge_pad_uuids"]=[]
    elif fault=="lower_clearance": b.GetDesignSettings().m_MinClearance=200000; request["clearance_nm"]=199999
    elif fault=="deadline": request["timeout_s"]=0
    else:
        for p in roots[0].GetParentFootprint().Pads():
            if p.GetPosition().x==pcbnew.FromMM(44.2): p.Move(pcbnew.VECTOR2I(1,0))
    before=copper_inventory(b)
    with pytest.raises(gap.Refused): gap.plan(b,[gap._uid(p) for p in roots],**request)
    assert copper_inventory(b)==before


def test_native_custom_layer_labels_do_not_hide_canonical_routing_or_plane_identity():
    b,roots,merge,tracks,_,_=fixture()
    assert b.SetLayerName(pcbnew.In2_Cu,"DIFFERENT_SIGNAL_LABEL")
    p=propose(b,roots,merge,tracks)
    assert p["all_requested_paths_clear"]
    assert {r["layer"] for r in p["valid_paths"]}=={"F.Cu","B.Cu","In2.Cu","In3.Cu"}
    z=pcbnew.ZONE(b); z.SetLayer(pcbnew.In2_Cu); poly=z.Outline(); poly.NewOutline()
    for x,y in ((0,0),(80,0),(80,80),(0,80)): poly.Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
    b.Add(z)
    with pytest.raises(gap.Refused,match="disabled_forbidden_or_plane"):
        propose(b,roots,merge,tracks)


@pytest.mark.parametrize("pitch,row_gap,pad_size",[(5.08,7.62,(3.,4.)),(3.9,4.6,(2.2,3.2))])
@pytest.mark.parametrize("angle",[0,90])
def test_gap_and_recombination_follow_changed_native_pitch_and_land_extents(pitch,row_gap,pad_size,angle):
    b,roots,merge,tracks,_,_=fixture(angle,pitch=pitch,row_gap=row_gap,pad_size=pad_size)
    before=copper_inventory(b); p=propose(b,roots,merge,tracks)
    assert p["all_requested_paths_clear"] and p["root_geometry_coverage_complete"],p["refused_paths"]
    actual={r["gap_column_nm"] for r in p["valid_paths"]}
    row_axis=p["row_axis"]
    columns=sorted({list(pad.GetPosition())[row_axis] for pad in roots[0].GetParentFootprint().Pads()})
    assert actual<= {(left+right)//2 for left,right in zip(columns,columns[1:])}
    assert copper_inventory(b)==before
