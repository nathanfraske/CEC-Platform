"""Pad-center overshoot repair preserves full-width native pad overlap."""
import copy

import pcbnew
import pytest

import cec_pad_landing as landing
import cec_rectilinear_copper as owner
from cec_local_copper_cell import copper_inventory
from test_rectilinear_copper import fixture


def setup(angle=0, mirror=False, layer=pcbnew.F_Cu, locked=False, grouped=False):
    b, ts = fixture(angle=angle, mirror=mirror, layer=layer, locked=locked, grouped=grouped)
    t = ts[-1]; center = t.GetEnd()
    p = next(p for fp in b.GetFootprints() for p in fp.Pads() if p.GetPosition() == center)
    p.SetSize(pcbnew.VECTOR2I_MM(2.5,.7)); p.SetOrientationDegrees(angle)
    return b, t, p


def plan(b,t,p,**kw):
    return landing.plan(b,t.m_Uuid.AsString(),p.m_Uuid.AsString(),
        required_width_nm=2200000,clearance_nm=200000,**kw)


def cover(b,t):
    return owner.plan(b,[t.m_Uuid.AsString()],required_width_nm=2200000,
        clearance_nm=200000,min_thickness_nm=100000,contour_style="chamfer45",
        contour_grid_nm=1000,fill_envelope_margin_nm=4,retire_source_tracks=False,
        allow_locked_track_uuids=[t.m_Uuid.AsString()],allow_grouped_track_uuids=[t.m_Uuid.AsString()])


@pytest.mark.parametrize("angle",[0,90,180,270])
@pytest.mark.parametrize("mirror",[False,True])
@pytest.mark.parametrize("layer",[pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_native_pad_landing_is_full_width_and_not_a_refdes_coordinate_exception(tmp_path,angle,mirror,layer):
    b,t,p=setup(angle,mirror,layer);before=copper_inventory(b)
    proposed=plan(b,t,p);assert copper_inventory(b)==before
    assert proposed["target_track"]["width_nm"]==2200000
    assert proposed["target_track"]["end_nm"]!=proposed["source_track"]["end_nm"]
    landing.materialize(b,proposed)
    c=cover(b,t);e=owner.materialize(b,c,allow_locked_track_uuids=[t.m_Uuid.AsString()],
        allow_grouped_track_uuids=[t.m_Uuid.AsString()])
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path=tmp_path/"native-pad-landing.kicad_pcb";pcbnew.SaveBoard(str(path),b)
    received=landing.receive(pcbnew.LoadBoard(str(path)),proposed,c,e["zone_uuid"])
    assert received["ok"] and received["full_width_native_pad_overlap_received"]
    assert not received["release_authority"] and not received["new_capacity_credited"]


@pytest.mark.parametrize("locked,grouped",[(True,False),(False,True),(True,True)])
def test_locked_and_grouped_native_track_needs_exact_explicit_ownership(locked,grouped):
    b,t,p=setup(locked=locked,grouped=grouped);uid=t.m_Uuid.AsString();before=copper_inventory(b)
    with pytest.raises(landing.Refused):plan(b,t,p)
    proposed=plan(b,t,p,allow_locked_track_uuids=[uid],allow_grouped_track_uuids=[uid])
    with pytest.raises(landing.Refused):landing.materialize(b,proposed)
    assert copper_inventory(b)==before
    landing.materialize(b,proposed,allow_locked_track_uuids=[uid],allow_grouped_track_uuids=[uid])


@pytest.mark.parametrize("fault",["attached_toe","foreign_copper","pad_too_narrow","not_center",
    "non_manhattan","drill","stale_pad","rehashed_target","rehashed_width"])
def test_unqualified_or_attached_toe_cannot_be_silently_trimmed(fault):
    b,t,p=setup();proposed=plan(b,t,p)
    if fault=="attached_toe":
        extra=pcbnew.PCB_TRACK(b);extra.SetNet(t.GetNet());extra.SetLayer(t.GetLayer())
        extra.SetStart(pcbnew.VECTOR2I_MM(38,38.9));extra.SetEnd(pcbnew.VECTOR2I_MM(40,38.9))
        extra.SetWidth(100000);b.Add(extra)
    elif fault=="foreign_copper":
        n=pcbnew.NETINFO_ITEM(b,"/UNRELATED");b.Add(n);extra=pcbnew.PCB_TRACK(b)
        extra.SetNet(n);extra.SetLayer(t.GetLayer());extra.SetWidth(100000)
        extra.SetStart(pcbnew.VECTOR2I_MM(37,35));extra.SetEnd(pcbnew.VECTOR2I_MM(39,35));b.Add(extra)
    elif fault=="pad_too_narrow":p.SetSize(pcbnew.VECTOR2I_MM(1.5,.7))
    elif fault=="not_center":t.SetEnd(pcbnew.VECTOR2I(t.GetEnd().x+1,t.GetEnd().y))
    elif fault=="non_manhattan":t.SetStart(pcbnew.VECTOR2I(t.GetStart().x+1,t.GetStart().y))
    elif fault=="drill":p.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    elif fault=="stale_pad":p.Move(pcbnew.VECTOR2I(1,0))
    elif fault=="rehashed_target":proposed["target_track"]["end_nm"][1]+=1
    else:proposed["target_track"]["width_nm"]-=1
    if fault.startswith("rehashed"):
        proposed.pop("plan_sha256");proposed["plan_sha256"]=owner._digest(proposed)
    before=copper_inventory(b)
    with pytest.raises(landing.Refused):landing.materialize(b,proposed)
    assert copper_inventory(b)==before


@pytest.mark.parametrize("fault",["unfilled","wrong_pad","rehashed_witness","one_nm_overlap_loss"])
def test_saved_receiving_requires_real_full_width_overlap_not_an_old_ok_flag(fault):
    b,t,p=setup();proposed=plan(b,t,p);landing.materialize(b,proposed)
    c=cover(b,t);e=owner.materialize(b,c);z=next(iter(b.Zones()))
    fill=owner._poly(c["polygon_nm"])
    if fault=="one_nm_overlap_loss":
        at=[min(p[k] for p in proposed["full_width_pad_overlap_nm"]) for k in (0,1)]
        fill.BooleanSubtract(owner._poly([(at[0],at[1]),(at[0]+1,at[1]),
            (at[0]+1,at[1]+1),(at[0],at[1]+1)]))
    z.SetFilledPolysList(t.GetLayer(),fill);z.SetIsFilled(True)
    if fault=="unfilled":z.SetIsFilled(False)
    elif fault=="wrong_pad":p.Move(pcbnew.VECTOR2I(1,0))
    elif fault=="rehashed_witness":
        proposed=copy.deepcopy(proposed);proposed["full_width_pad_overlap_nm"][0][0]+=1
        proposed.pop("plan_sha256");proposed["plan_sha256"]=owner._digest(proposed)
    with pytest.raises(landing.Refused):landing.receive(b,proposed,c,e["zone_uuid"])
