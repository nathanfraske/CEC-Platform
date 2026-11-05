"""Native purposeful landing geometry, not prettier dashboard overlays."""
import copy
import math

import pcbnew
import pytest

import cec_rectilinear_copper as tracks
import cec_rounded_landing as zones
from cec_local_copper_cell import copper_inventory


def fixture(angle=0,mirror=False,layer=pcbnew.F_Cu):
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6)
    n=pcbnew.NETINFO_ITEM(b,"/RENAMED_CURRENT_DOMAIN");b.Add(n)
    def at(x,y):
        if mirror:x=-x
        for _ in range(angle//90):x,y=-y,x
        return pcbnew.VECTOR2I_MM(30+x,30+y)
    for a,z in [((0,0),(60,0)),((60,0),(60,60)),((60,60),(0,60)),((0,60),(0,0))]:
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*z));edge.SetLayer(pcbnew.Edge_Cuts);b.Add(edge)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference("RENAMED_PAD_OWNER");b.Add(fp)
    p=pcbnew.PAD(fp);fp.Add(p);p.SetNet(n);p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetSize(pcbnew.VECTOR2I_MM(2,2));p.SetPosition(at(0,0))
    ls=pcbnew.LSET();ls.AddLayer(layer);p.SetLayerSet(ls)
    t=pcbnew.PCB_TRACK(b);t.SetNet(n);t.SetStart(at(0,0));t.SetEnd(at(0,1.3))
    t.SetWidth(6000000);t.SetLayer(layer);b.Add(t)
    return b,t,at


def circle_fixture(**kwargs):
    b,t,at=fixture(**kwargs);layer=t.GetLayer();net=t.GetNet();b.Remove(t)
    z=pcbnew.ZONE(b);z.SetLayer(layer);z.SetNet(net);z.SetZoneName("RENAMED_NATIVE_LANDING")
    z.SetLocalClearance(200000);z.SetMinThickness(100000)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL);z.Outline().NewOutline()
    for i in range(48):
        p=at(3*math.cos(2*math.pi*i/48),3*math.sin(2*math.pi*i/48))
        z.Outline().Append(p.x,p.y)
    b.Add(z);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    return b,z


def canonical(points):
    return all(a[0]==b[0] or a[1]==b[1] or abs(a[0]-b[0])==abs(a[1]-b[1])
               for a,b in zip(points,points[1:]+points[:1]))


@pytest.mark.parametrize("angle",[0,90,180,270])
@pytest.mark.parametrize("mirror",[False,True])
@pytest.mark.parametrize("layer",[pcbnew.F_Cu,pcbnew.B_Cu])
def test_exact_45_degree_incoming_capsule_gets_native_chamfer_without_width_or_path_loss(
        tmp_path,angle,mirror,layer):
    b,t,at=fixture(angle,mirror,layer);t.SetEnd(at(1.3,1.3))
    uid=t.m_Uuid.AsString();row=tracks._track_row(t)
    plan=tracks.plan(b,[uid],clearance_nm=200000,min_thickness_nm=250000,
        required_width_nm=6000000,contour_style="chamfer45",contour_grid_nm=1000,
        fill_envelope_margin_nm=4,retire_source_tracks=False)
    assert canonical(plan["polygon_nm"]) and not plan["new_capacity_credited"]
    emitted=tracks.materialize(b,plan);b.BuildConnectivity()
    assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path=tmp_path/"diagonal-native.kicad_pcb";pcbnew.SaveBoard(str(path),b)
    saved=pcbnew.LoadBoard(str(path));received=tracks.receive(saved,plan,emitted["zone_uuid"])
    assert received["complete"] and received["ok"],received
    assert tracks._track_row(next(item for item in saved.GetTracks()
        if item.m_Uuid.AsString()==uid))==row


@pytest.mark.parametrize("offset_nm",[1,1000,100000])
def test_chamfer_cover_does_not_accept_almost_45_degree_or_arbitrary_diagonal(offset_nm):
    b,t,at=fixture();p=at(1.3,1.3);p.x+=offset_nm;t.SetEnd(p)
    with pytest.raises(tracks.Refused,match="centerline"):
        tracks.plan(b,[t.m_Uuid.AsString()],clearance_nm=200000,min_thickness_nm=250000,
            required_width_nm=6000000,contour_style="chamfer45")


def test_square_cover_still_requires_manhattan_centerline():
    b,t,at=fixture();t.SetEnd(at(1.3,1.3))
    with pytest.raises(tracks.Refused,match="centerline"):
        tracks.plan(b,[t.m_Uuid.AsString()],clearance_nm=200000,min_thickness_nm=250000,
            required_width_nm=6000000)


@pytest.mark.parametrize("angle",[0,90,180,270])
@pytest.mark.parametrize("mirror",[False,True])
@pytest.mark.parametrize("layer",[pcbnew.F_Cu,pcbnew.B_Cu])
def test_chamfered_short_stroke_saved_native_fill_preserves_full_capsule(tmp_path,angle,mirror,layer):
    b,t,_=fixture(angle,mirror,layer);initial=copper_inventory(b)
    plan=tracks.plan(b,[t.m_Uuid.AsString()],clearance_nm=200000,min_thickness_nm=100000,
        required_width_nm=6000000,contour_style="chamfer45")
    assert copper_inventory(b)==initial and canonical(plan["polygon_nm"])
    assert len(plan["polygon_nm"])==8 and not plan["new_capacity_credited"]
    emitted=tracks.materialize(b,plan);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path=tmp_path/"native.kicad_pcb";pcbnew.SaveBoard(str(path),b)
    received=tracks.receive(pcbnew.LoadBoard(str(path)),plan,emitted["zone_uuid"])
    assert received["complete"] and received["ok"],received


@pytest.mark.parametrize("angle",[0,90,180,270])
@pytest.mark.parametrize("mirror",[False,True])
@pytest.mark.parametrize("layer",[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize("style",["square","chamfer45"])
def test_round_zone_keeps_identity_process_ownership_and_all_old_native_fill(tmp_path,angle,mirror,layer,style):
    b,z=circle_fixture(angle=angle,mirror=mirror,layer=layer);old=zones._configuration(z)
    source=zones._native_source(z);plan=zones.plan(b,z.m_Uuid.AsString(),required_width_nm=6000000,style=style)
    assert zones._native_source(z)==source and canonical(plan["polygon_nm"])
    assert len(plan["polygon_nm"])==(4 if style=="square" else 8)
    assert not plan["release_authority"] and not plan["new_capacity_credited"]
    emitted=zones.materialize(b,plan);b.BuildConnectivity();batch=pcbnew.ZONES();batch.append(z)
    assert pcbnew.ZONE_FILLER(b).Fill(batch);assert zones._configuration(z)==old
    path=tmp_path/"zone.kicad_pcb";pcbnew.SaveBoard(str(path),b)
    received=zones.receive(pcbnew.LoadBoard(str(path)),plan)
    assert received["complete"] and received["ok"],received
    assert emitted["zone_uuid"]==old["uuid"]


@pytest.mark.parametrize("fault",["changed_source","foreign_pad","unfilled","deadline","lock","contract","hole","fake_style","rehashed_shape"])
def test_round_zone_refuses_invalid_authority_and_stale_or_incomplete_geometry(fault):
    b,z=circle_fixture();uid=z.m_Uuid.AsString()
    plan=zones.plan(b,uid,required_width_nm=6000000)
    if fault in ("unfilled","deadline"):
        zones.materialize(b,plan)
        result=zones.receive(b,plan,timeout_s=0 if fault=="deadline" else 2)
        assert not result["complete"] and not result["ok"]
        return
    if fault=="changed_source":z.SetAssignedPriority(7)
    elif fault=="foreign_pad":
        n=pcbnew.NETINFO_ITEM(b,"/FOREIGN_ARBITRARY");b.Add(n)
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);p=pcbnew.PAD(fp);fp.Add(p)
        p.SetNet(n);p.SetSize(pcbnew.VECTOR2I_MM(.1,.1));p.SetPosition(pcbnew.VECTOR2I_MM(30,30))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetLayerSet(pcbnew.PAD.SMDMask())
    elif fault=="lock":z.SetLocked(True)
    elif fault=="contract":
        with pytest.raises(zones.Refused):zones.plan(b,uid,required_width_nm=6002001)
        return
    elif fault=="hole":
        z.Outline().NewHole(0);z.Outline().Append(30000000,30000000,0,0)
        z.Outline().Append(30000001,30000000,0,0);z.Outline().Append(30000000,30000001,0,0)
    elif fault=="fake_style":plan["style"]="round"
    else:plan["polygon_nm"][0][0]+=1
    if fault in ("fake_style","rehashed_shape"):
        plan.pop("plan_sha256");plan["plan_sha256"]=tracks._digest(plan)
    initial=copper_inventory(b)
    with pytest.raises(zones.Refused):zones.materialize(b,plan)
    assert copper_inventory(b)==initial


def test_one_nanometre_landing_loss_never_becomes_area_tolerance():
    b,z=circle_fixture();plan=zones.plan(b,z.m_Uuid.AsString(),required_width_nm=6000000)
    zones.materialize(b,plan);fill=tracks._poly(plan["polygon_nm"])
    cut=tracks._poly([(30000000,30000000),(30000001,30000000),(30000001,30000001),(30000000,30000001)])
    fill.BooleanSubtract(cut);z.SetFilledPolysList(pcbnew.F_Cu,fill);z.SetIsFilled(True)
    received=zones.receive(b,plan)
    assert received["complete"] and not received["ok"] and received["reason"]=="native_landing_copper_loss"


@pytest.mark.parametrize("grid",[1,2,1000])
def test_new_support_planes_snap_outward_never_original_copper(grid):
    b,t,_=fixture();t.SetWidth(6535523);t.Move(pcbnew.VECTOR2I(37,-53))
    old=tracks._native_capsule(t)
    pts=tracks.purposeful_envelope(old,grid_nm=grid)
    assert all(v%grid==0 for p in pts for v in p) and canonical(pts)
    missing=old.CloneDropTriangulation();missing.BooleanSubtract(tracks._poly(pts))
    assert not missing.OutlineCount()


@pytest.mark.parametrize("fault",["source_loss","outside_declared_envelope","undeclared_guard","rehashed_guard"])
def test_declared_native_fill_domain_never_tolerates_copper_loss_or_unbound_spill(fault):
    b,t,_=fixture();t.SetWidth(6535523)
    plan=tracks.plan(b,[t.m_Uuid.AsString()],clearance_nm=200000,min_thickness_nm=250000,
        required_width_nm=6000000,contour_style="chamfer45",contour_grid_nm=1000,fill_envelope_margin_nm=4)
    original=copy.deepcopy(plan)
    assert plan["actual_fill_envelope_nm"]!=plan["polygon_nm"]
    if fault in ("undeclared_guard","rehashed_guard"):
        if fault=="undeclared_guard":plan.pop("fill_envelope_margin_nm")
        else:plan["actual_fill_envelope_nm"][0][0]-=1
        plan.pop("plan_sha256");plan["plan_sha256"]=tracks._digest(plan)
        initial=copper_inventory(b)
        with pytest.raises(tracks.Refused):tracks.materialize(b,plan)
        assert copper_inventory(b)==initial
        return
    emitted=tracks.materialize(b,plan);z=list(b.Zones())[0]
    fill=tracks._poly(plan["actual_fill_envelope_nm"])
    if fault=="source_loss":
        fill.BooleanSubtract(tracks._poly([(30000000,30000000),(30000001,30000000),(30000001,30000001),(30000000,30000001)]))
    else:
        first=plan["actual_fill_envelope_nm"][0]
        fill.BooleanAdd(tracks._poly([(first[0],first[1]-100),(first[0]+100,first[1]-100),(first[0]+100,first[1]+100),(first[0],first[1]+100)]))
    z.SetFilledPolysList(pcbnew.F_Cu,fill);z.SetIsFilled(True)
    result=tracks.receive(b,plan,emitted["zone_uuid"])
    assert not result["ok"]
    if fault=="source_loss":assert result["complete"] and result["missing_source_tracks"]


def test_native_odd_width_diagonal_fill_is_bound_to_actual_declared_domain(tmp_path):
    b,t,_=fixture();t.SetWidth(6535523);t.Move(pcbnew.VECTOR2I(37239,193739))
    plan=tracks.plan(b,[t.m_Uuid.AsString()],clearance_nm=200000,min_thickness_nm=250000,
        required_width_nm=6000000,contour_style="chamfer45",contour_grid_nm=1000,fill_envelope_margin_nm=4)
    emitted=tracks.materialize(b,plan);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path=tmp_path/"integer-fill.kicad_pcb";pcbnew.SaveBoard(str(path),b)
    result=tracks.receive(pcbnew.LoadBoard(str(path)),plan,emitted["zone_uuid"])
    assert result["complete"] and result["ok"] and result["fill_envelope_margin_nm"]==4
    assert not result["new_capacity_credited"] and not result["release_authority"]


@pytest.mark.parametrize("angle",[0,90,180,270])
@pytest.mark.parametrize("layer",[pcbnew.F_Cu,pcbnew.B_Cu])
def test_style_cover_preserves_real_current_track_and_default_capacity_without_ghost_credit(tmp_path,angle,layer):
    import cec_force_current as force
    import cec_power_contours as contours
    b,t,_=fixture(angle=angle,layer=layer);uid=t.m_Uuid.AsString();row=tracks._track_row(t)
    domain=dict(source_refs=["RENAMED_PAD_OWNER"],sink_refs=["RENAMED_PAD_OWNER"])
    contract=dict(required_by_layer_mm={pcbnew.LayerName(layer):5.})
    before=force._graph(b,t.GetNetname(),domain,contract,{})[0]
    assert contours.audit_board(b)["finding_count"]==1
    plan=tracks.plan(b,[uid],clearance_nm=200000,min_thickness_nm=100000,required_width_nm=6000000,
        contour_style="chamfer45",retire_source_tracks=False)
    emitted=tracks.materialize(b,plan);assert not emitted["retired_track_uuids"]
    assert tracks._track_row(next(t for t in b.GetTracks() if t.m_Uuid.AsString()==uid))==row
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path=tmp_path/"retained.kicad_pcb";pcbnew.SaveBoard(str(path),b);saved=pcbnew.LoadBoard(str(path))
    received=tracks.receive(saved,plan,emitted["zone_uuid"]);assert received["ok"] and received["complete"]
    ghosts,_=tracks.enclosed_track_witnesses(saved,plan,emitted["zone_uuid"]);assert not ghosts
    after=force._graph(saved,plan["net"],domain,contract,{})[0]
    assert before["rated_connectivity"]==after["rated_connectivity"]
    assert before["trace_connectivity"]==after["trace_connectivity"]
    audit=contours.audit_board(saved);assert audit["complete"] and audit["finding_count"]==0
    assert audit["purposeful_native_cover_count"]==1


@pytest.mark.parametrize("fault",["unfilled","wrong_net","circle_outline","tiny_loss","missing_track"])
def test_a_name_or_outline_does_not_hide_uncovered_native_capsules(fault):
    import cec_power_contours as contours
    b,t,_=fixture();uid=t.m_Uuid.AsString()
    plan=tracks.plan(b,[uid],clearance_nm=200000,min_thickness_nm=100000,required_width_nm=6000000,
        contour_style="chamfer45",retire_source_tracks=False)
    e=tracks.materialize(b,plan);z=list(b.Zones())[0]
    z.SetFilledPolysList(pcbnew.F_Cu,tracks._poly(plan["polygon_nm"]));z.SetIsFilled(True)
    if fault=="unfilled":z.SetIsFilled(False)
    elif fault=="wrong_net":
        n=pcbnew.NETINFO_ITEM(b,"/UNRELATED");b.Add(n);z.SetNet(n)
    elif fault=="circle_outline":
        z.Outline().RemoveAllContours();z.Outline().NewOutline()
        for i in range(48):z.Outline().Append(round(30000000+4000000*math.cos(2*math.pi*i/48)),round(30000000+4000000*math.sin(2*math.pi*i/48)))
    elif fault=="tiny_loss":
        fill=z.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
        fill.BooleanSubtract(tracks._poly([(30000000,30000000),(30000001,30000000),(30000001,30000001),(30000000,30000001)]))
        z.SetFilledPolysList(pcbnew.F_Cu,fill)
    else:
        b.Remove(t)
        assert not tracks.receive(b,plan,e["zone_uuid"])["ok"]
        return
    audit=contours.audit_board(b)
    assert audit["finding_count"]>=1 and not audit["purposeful_native_cover_count"]


def test_actual_round_zone_is_detected_without_confusing_drills_or_chamfered_landings():
    import cec_power_contours as contours
    b,z=circle_fixture();audit=contours.audit_board(b)
    assert audit["types"]=={"rounded_compact_zone_landing":1}
    p=zones.plan(b,z.m_Uuid.AsString(),required_width_nm=6000000)
    zones.materialize(b,p);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    assert contours.audit_board(b)["finding_count"]==0


def test_readonly_proposal_view_keeps_actual_native_zones_in_inventory(monkeypatch):
    import cec_power_contours as contours
    import cec_route_quality as craft
    b,z=circle_fixture();before=copper_inventory(b);seen=[];original=contours.audit_board
    def observed(view,**kwargs):
        seen.append([item.m_Uuid.AsString() for item in view.Zones()])
        return original(view,**kwargs)
    monkeypatch.setattr(contours,"audit_board",observed)
    result=craft.assess_proposed_route(b,[dict(net=z.GetNetname(),layer=pcbnew.F_Cu,
        start_nm=[40000000,40000000],end_nm=[41000000,40000000],width_nm=200000)])
    assert result["ok"] is True and result["complete"],result
    assert seen==[[z.m_Uuid.AsString()]] and copper_inventory(b)==before
