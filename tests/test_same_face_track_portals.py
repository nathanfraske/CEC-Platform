"""Retained escapes are exact same-face native material, not via authority."""
import time
from types import SimpleNamespace

import pcbnew
import pytest

import cec_force_current as force
import cec_field_coupling as field
import cec_fr as fr
import cec_native_component_ports as ports
import cec_native_portal_geometry as geometry
import cec_ordinary_signal_completion as ordinary
from test_ordinary_native_portals import fixture, target


def track(board,net,a,b,face=pcbnew.F_Cu,width=100000):
    t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*b))
    t.SetWidth(width);t.SetLayer(face);t.SetNetCode(board.GetNetcodeFromNetname(net));board.Add(t)
    return t


def menu(board,net,pad,**kwargs):
    return ports.same_face_track_endpoints(board,net,pad,route_layers=[pcbnew.F_Cu,pcbnew.B_Cu],
        toward_nm=(15_000_000,10_000_000),deadline=time.monotonic()+2.,**kwargs)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_retained_endpoints_and_no_cross_layer_barrel_inference(tmp_path,quarter,back):
    source,b,net=fixture(tmp_path)
    root=next(p for f in b.GetFootprints()for p in f.Pads() if tuple(p.GetPosition())==(5_000_000,10_000_000))
    escape=track(b,net,(5,10),(8,10))
    tail=track(b,net,(8,10),(10,10))
    island=track(b,net,(10.000001,10),(12,10),width=1)
    # A real through via connects an otherwise unrooted back-face track in
    # the FULL native graph. It cannot grant this endpoint menu a layer jump.
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(8,10));via.SetWidth(600000)
    via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(escape.GetNet());b.Add(via)
    other=track(b,net,(8,10),(8,13),pcbnew.B_Cu)
    # Keep the nearby same-net island physically separate from the tail.
    island.SetStart(pcbnew.VECTOR2I_MM(11,10))
    for f in b.GetFootprints():
        f.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:f.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    for item in (escape,tail,island,via,other):
        item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:item.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    before=force._item_key(escape),force._item_key(tail),force._item_key(root)
    rows=menu(b,net,root)
    ids={u for r in rows for u in r['native_uuids']}
    assert force._uid(tail) in ids
    assert not ids&{force._uid(island),force._uid(other),force._uid(via)}
    assert all(r['layers']==[int(escape.GetLayer())] for r in rows)
    for r in rows[1:]:
        item=next(t for t in (escape,tail)if force._uid(t)in r['native_uuids'])
        assert tuple(r['at_nm']) in (tuple(item.GetStart()),tuple(item.GetEnd()))
        assert r['retained_same_face_root_pad_uuid']==force._uid(root)
        assert r['retained_same_face_path_native_uuids'][-1]==force._uid(root)
    assert before==(force._item_key(escape),force._item_key(tail),force._item_key(root))


def test_native_capsule_contact_not_coordinate_proximity(tmp_path):
    _,b,net=fixture(tmp_path)
    root=next(p for f in b.GetFootprints()for p in f.Pads() if tuple(p.GetPosition())==(5_000_000,10_000_000))
    stem=track(b,net,(5,10),(8,10))
    touching=track(b,net,(8,10.099999),(10,10.099999))
    separated=track(b,net,(6,10.100001),(7,10.100001))
    rows=menu(b,net,root);ids={u for r in rows for u in r['native_uuids']}
    assert force._uid(touching)in ids and force._uid(separated)not in ids
    assert force._uid(stem)in ids


def test_plated_pad_does_not_import_contacts_from_a_different_face(tmp_path):
    _,b,net=fixture(tmp_path)
    root=next(p for f in b.GetFootprints()for p in f.Pads() if tuple(p.GetPosition())==(5_000_000,10_000_000))
    root.SetAttribute(pcbnew.PAD_ATTRIB_PTH);root.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    root.SetLayerSet(pcbnew.LSET.AllCuMask())
    front=track(b,net,(5,10),(8,10))
    back=track(b,net,(5,10),(5,13),pcbnew.B_Cu)
    rows=menu(b,net,root)
    for item in (front,back):
        found=[r for r in rows if r['native_uuids']==[force._uid(item)]]
        assert found and all(r['layers']==[int(item.GetLayer())]for r in found)
    assert not any(len(r['layers'])>1 for r in rows[1:])


@pytest.mark.parametrize('fault',['bool_limit','over_limit','over_shift','bad_shift','nonint_point','future_deadline','wrong_root'])
def test_exact_same_face_policy_refuses_bad_authority(tmp_path,fault):
    _,b,net=fixture(tmp_path);root=next(iter(next(iter(b.GetFootprints())).Pads()))
    kw=dict(route_layers=[pcbnew.F_Cu],toward_nm=(15_000_000,10_000_000),deadline=time.monotonic()+2.)
    if fault=='bool_limit':kw['max_sites']=True
    elif fault=='over_limit':kw['max_sites']=33
    elif fault=='over_shift':kw['max_shift_mm']=33
    elif fault=='bad_shift':kw['max_shift_mm']=float('nan')
    elif fault=='nonint_point':kw['toward_nm']=(1.,2)
    elif fault=='future_deadline':kw['deadline']=time.monotonic()+11
    elif fault=='wrong_root':root=pcbnew.PAD(root.GetParentFootprint());root.SetNetCode(b.GetNetcodeFromNetname(net))
    with pytest.raises(ValueError):ports.same_face_track_endpoints(b,net,root,**kw)


def test_retained_native_escape_closes_at_project_width_with_shared_deadline(tmp_path,monkeypatch):
    import cec_route_proposal_guard as guards
    import cec_field_search as search
    source,b,net=fixture(tmp_path)
    old=track(b,net,(5,10),(9,10),width=100000)
    field._save_field_snapshot(b,source)
    candidate=force._copy_family(source,tmp_path/'retained');q=ordinary.plan(b,source,board_hint='synthetic',net=net)
    intent=target(b,q);intent['retained_same_face_track_ends']=True;calls=[]
    class Guard:
        def __init__(self,*a,**kw):self.counts={}
        def __call__(self,ops):return True
    monkeypatch.setattr(guards,'RouteProposalGuard',Guard)
    monkeypatch.setattr(search,'PlanarSearchGuard',lambda *a,**kw:SimpleNamespace(active=False))
    monkeypatch.setattr(fr,'_lastmile_route_layers',lambda b,**kw:[pcbnew.B_Cu]if kw['exclude_front']else[pcbnew.F_Cu,pcbnew.B_Cu])
    def bridge(board,A,al,B,bl,width,*args,**kw):
        calls.append((A,al,B,bl,width,kw['deadline_monotonic']))
        return [('trk',pcbnew.VECTOR2I(*A),pcbnew.VECTOR2I(*B),width,pcbnew.F_Cu)]
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    before=source.read_bytes();started=time.monotonic()
    result=geometry.apply_native_portals(candidate,intent,5.)
    assert result['closed']==1 and result['retained_same_face_track_ends'],result
    assert any((9_000_000,10_000_000)in (A,B) for A,_,B,_,_,_ in calls)
    assert all(width==220000 and end<=started+5. for _,_,_,_,width,end in calls)
    received=ordinary.receive(source,candidate,board_hint='synthetic',net=net)
    assert received['ok']and received['whole_shared_stage_still_required'],received
    saved=pcbnew.LoadBoard(str(candidate));retained=next(t for t in saved.GetTracks()if force._uid(t)==force._uid(old))
    assert retained.GetWidth()==100000 and force._item_key(retained)==force._item_key(old)
    assert source.read_bytes()==before


def test_deadline_and_unknown_policy_cannot_create_attachment_authority(tmp_path):
    source,b,net=fixture(tmp_path);q=ordinary.plan(b,source,board_hint='synthetic',net=net)
    intent=target(b,q);intent['retained_same_face_track_ends']='yes'
    with pytest.raises(ValueError,match='explicit_retained_same_face'):
        geometry.apply_native_portals(source,intent,2.)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_explicit_full_web_barrel_at_rooted_track_end_exposes_real_faces_only(tmp_path,quarter,back):
    _,b,net=fixture(tmp_path)
    root=next(p for f in b.GetFootprints() for p in f.Pads() if tuple(p.GetPosition())==(5000000,10000000))
    stem=track(b,net,(5,10),(8,10),width=220000)
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(8,10));via.SetWidth(600000)
    via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(stem.GetNet());b.Add(via)
    other=track(b,net,(8,10),(8,13),pcbnew.B_Cu,width=220000)
    for i in [*b.GetFootprints(),*b.GetTracks()]:
        i.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:i.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    before=field._field_snapshot_inventory(b)
    ordinary_menu=menu(b,net,root)
    rows=menu(b,net,root,minimum_barrel_web_nm=220000)
    extra=[r for r in rows if r.get('retained_barrel_uuid')==force._uid(via)]
    assert extra and all(set(r['layers'])=={pcbnew.F_Cu,pcbnew.B_Cu} for r in extra)
    assert all(r['native_finite_track_barrel_contact'] and not r['barrel_capacity_qualified'] and not r['new_barrel'] for r in extra)
    assert not any(r.get('retained_barrel_uuid') for r in ordinary_menu)
    assert force._uid(other) not in {u for r in rows for u in r['native_uuids']}
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('fault',['underweb','not_endpoint','unrooted','wrong_net'])
def test_no_extra_face_from_underweb_nearby_body_or_unrooted_barrel(tmp_path,fault):
    _,b,net=fixture(tmp_path)
    root=next(p for f in b.GetFootprints() for p in f.Pads() if tuple(p.GetPosition())==(5000000,10000000))
    stem=track(b,net,(5,10),(8,10),width=220000)
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(7 if fault=='not_endpoint' else 8,
        11 if fault=='unrooted' else 10));via.SetWidth(500000 if fault=='underweb' else 600000)
    via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(stem.GetNet());b.Add(via)
    if fault=='wrong_net':b.Add(pcbnew.NETINFO_ITEM(b,'/OTHER'));via.SetNet(b.FindNet('/OTHER'))
    rows=menu(b,net,root,minimum_barrel_web_nm=220000)
    assert not any(r.get('retained_barrel_uuid') for r in rows)


@pytest.mark.parametrize('width',[True,0,1,2000001,float('nan')])
def test_explicit_barrel_contact_policy_cannot_relax_board_floor_or_be_ambiguous(tmp_path,width):
    _,b,net=fixture(tmp_path);root=next(iter(next(iter(b.GetFootprints())).Pads()))
    # A nonzero explicit native floor is mandatory for this fixture too.
    b.GetDesignSettings().m_TrackMinWidth=150000
    with pytest.raises(ValueError,match='sufficient_retained_barrel_web'):
        menu(b,net,root,minimum_barrel_web_nm=width)
