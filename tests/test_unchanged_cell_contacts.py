"""Stationary off-centre native contacts are not reconnection obligations."""
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_force_current as force
import cec_field_coupling as field
from test_cell_escape_replan import fixture


def case(monkeypatch,tmp_path,quarter=0,back=False):
    b,poses,owner,cap=fixture(monkeypatch,prefix='unrelated_hierarchy')
    pad=owner.FindPadByNumber('3');track=pcbnew.PCB_TRACK(b);track.SetNet(pad.GetNet())
    track.SetStart(pad.GetPosition()+pcbnew.VECTOR2I(150000,0))
    track.SetEnd(track.GetStart()+pcbnew.VECTOR2I(0,2000000));track.SetWidth(200000);track.SetLayer(pcbnew.F_Cu);b.Add(track)
    if back:
        for fp in b.GetFootprints():
            fp.SetLayer(pcbnew.B_Cu)
            for p in fp.Pads():
                mask=pcbnew.LSET();mask.AddLayer(pcbnew.B_Cu);p.SetLayerSet(mask)
        track.SetLayer(pcbnew.B_Cu)
    if quarter:
        for item in [*b.GetFootprints(),*b.GetTracks()]:
            item.Rotate(pcbnew.VECTOR2I_MM(20,20),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    poses={f.GetReference():[f.GetPosition().x/1e6,f.GetPosition().y/1e6,f.GetOrientationDegrees()] for f in (owner,cap)}
    poses[cap.GetReference()][0]+=.5
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    return pcbnew.LoadBoard(str(path)),path,poses,force._uid(owner),force._uid(pad),force._uid(track)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_native_land_and_stroke_are_retained_across_frames(monkeypatch,tmp_path,quarter,back):
    b,path,poses,owner,puid,tuid=case(monkeypatch,tmp_path,quarter,back)
    other=pcbnew.LoadBoard(str(path));p=next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p)==puid)
    q=next(p for f in other.GetFootprints() for p in f.Pads() if force._uid(p)==puid)
    old=next(t for t in b.GetTracks() if force._uid(t)==tuid);new=next(t for t in other.GetTracks() if force._uid(t)==tuid)
    assert tuple(p.GetPosition())!=tuple(old.GetStart())
    assert escape._unchanged_retained_surface_contact(p,q,old,new,int(old.GetLayer()))
    assert path.read_bytes()


@pytest.mark.parametrize('quarter',range(4))
def test_stationary_source_owner_does_not_receive_a_fictional_offcentre_route(monkeypatch,tmp_path,quarter):
    b,path,poses,owner,puid,tuid=case(monkeypatch,tmp_path,quarter)
    proposal=escape.prepare(b,poses,board_hint='opaque');draft=pcbnew.LoadBoard(str(path));escape.apply_private(draft,proposal)
    row=next(r for r in proposal['row_plan']['source_incident_boundaries'] if r['pad_uuid']==puid)
    assert row['disposition']=='unchanged_source_pad_contact_retained' and tuid not in proposal['retired_track_uuids']
    requests=escape.obligations(b,draft,proposal)
    assert 'retained:'+puid+':'+tuid not in requests
    assert any(q['kind']=='local_supply' for q in requests.values())
    assert any(q['kind']=='ground' for q in requests.values())
    assert force._uid(next(t for t in draft.GetTracks() if force._uid(t)==tuid))==tuid


@pytest.mark.parametrize('fault',['pad_motion','pad_net','pad_size','pad_parent','stroke_start','stroke_end','stroke_width',
    'stroke_layer','stroke_net','stroke_mask','missing_stroke','noncontact'])
def test_source_identity_or_geometry_change_is_not_treated_as_an_intact_contact(monkeypatch,tmp_path,fault):
    b,path,poses,owner,puid,tuid=case(monkeypatch,tmp_path);other=pcbnew.LoadBoard(str(path))
    p=next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p)==puid)
    q=next(p for f in other.GetFootprints() for p in f.Pads() if force._uid(p)==puid)
    old=next(t for t in b.GetTracks() if force._uid(t)==tuid);new=next(t for t in other.GetTracks() if force._uid(t)==tuid)
    if fault=='pad_motion':q.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='pad_net':q.SetNet(other.FindNet('OUT'))
    elif fault=='pad_size':q.SetSize(q.GetSize()+pcbnew.VECTOR2I(1,0))
    elif fault=='pad_parent':q.GetParentFootprint().m_Uuid.Clone(pcbnew.KIID())
    elif fault=='stroke_start':new.SetStart(new.GetStart()+pcbnew.VECTOR2I(1,0))
    elif fault=='stroke_end':new.SetEnd(new.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='stroke_width':new.SetWidth(new.GetWidth()+1)
    elif fault=='stroke_layer':new.SetLayer(pcbnew.B_Cu)
    elif fault=='stroke_net':new.SetNet(other.FindNet('OUT'))
    elif fault=='stroke_mask':new.SetHasSolderMask(True)
    elif fault=='missing_stroke':new=None
    elif fault=='noncontact':
        old.Move(pcbnew.VECTOR2I(1000000,0));new.Move(pcbnew.VECTOR2I(1000000,0))
    assert not escape._unchanged_retained_surface_contact(p,q,old,new,pcbnew.F_Cu)


@pytest.mark.parametrize('fault',['unchanged','remove_membership','different_group_uuid','different_container'])
def test_native_board_container_identity_not_eda_group_proxy_owns_stationary_contact(monkeypatch,tmp_path,fault):
    b,path,poses,owner,puid,tuid=case(monkeypatch,tmp_path)
    old=next(t for t in b.GetTracks() if force._uid(t)==tuid)
    group=pcbnew.PCB_GROUP(b);group.SetName('unrelated source contact group');b.Add(group);group.AddItem(old)
    field._save_field_snapshot(b,path);other=pcbnew.LoadBoard(str(path))
    p=next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p)==puid)
    q=next(p for f in other.GetFootprints() for p in f.Pads() if force._uid(p)==puid)
    new=next(t for t in other.GetTracks() if force._uid(t)==tuid)
    actual=next(g for g in other.Groups() if g.ContainsItem(new))
    if fault=='remove_membership':actual.RemoveItem(new)
    elif fault=='different_group_uuid':actual.m_Uuid.Clone(pcbnew.KIID())
    elif fault=='different_container':
        actual.RemoveItem(new);replacement=pcbnew.PCB_GROUP(other)
        replacement.SetName(actual.GetName());other.Add(replacement);replacement.AddItem(new)
    assert escape._unchanged_retained_surface_contact(p,q,old,new,pcbnew.F_Cu)==(fault=='unchanged')
