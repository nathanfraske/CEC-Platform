"""Proved native faces earn bounded independent effort, never new access."""
import copy
import time
from types import SimpleNamespace
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_native_portal_geometry as geometry
import cec_ordinary_signal_completion as ordinary
from test_ordinary_native_portals import fixture,target
from test_native_portal_resolution_portfolio import stubs


def plated_fixture(tmp_path,quarter=0):
    source,board,net=fixture(tmp_path,quarter=quarter)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3));pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    field._save_field_snapshot(board,source)
    q=ordinary.plan(board,source,board_hint='synthetic',net=net)
    request=target(board,q);request['retained_same_face_track_ends']=True
    return source,board,net,request


@pytest.mark.parametrize('quarter',range(4))
def test_layer_topologies_are_subsets_without_changing_actual_points_or_metadata(quarter):
    def point(x,y):
        for _ in range(quarter):x,y=-y,x
        return [x+17000000,y-8000000]
    a=dict(at_nm=point(1,2),layers=[6,2,0],native_uuids=['real_a'],
        retained_barrel_uuid='actual_retained',barrel_capacity_qualified=False)
    b=dict(at_nm=point(4,7),layers=[0,2],native_uuids=['real_b'])
    source=[(a,b),(dict(a,at_nm=point(2,2)),b)];prior=copy.deepcopy(source)
    result=geometry._face_strata_pairs(source)
    assert len(result)==6 and source==prior
    assert len({(p['layers'][0],q['layers'][0])for p,q in result})==6
    for pair in result:
        for old,child in zip(source[0],pair):
            assert len(child['layers'])==1 and set(child['layers'])<=set(old['layers'])
            assert {k:v for k,v in child.items()if k!='layers'}=={k:v for k,v in old.items()if k!='layers'}
    assert [(a['layers'][0],b['layers'][0])for a,b in result[:2]]==[(0,0),(2,2)]


@pytest.mark.parametrize('maximum',[True,0,17,1.5])
def test_unbounded_face_portfolio_refuses(maximum):
    with pytest.raises(ValueError):geometry._face_strata_pairs([],maximum=maximum)


@pytest.mark.parametrize('faces',[[],[0,0],[True],[0.0],list(range(9)),None])
def test_malformed_proved_menu_is_not_repaired_or_expanded(faces):
    with pytest.raises(ValueError):geometry._face_strata_pairs([
        (dict(layers=faces),dict(layers=[0]))])


def test_single_face_legacy_menu_has_no_extra_warm_pass():
    a=dict(at_nm=[0,0],layers=[0],native_uuids=['a']);b=dict(a,at_nm=[1,1])
    assert geometry._face_strata_pairs([(a,b)])==[]


@pytest.mark.parametrize('quarter',range(4))
def test_expensive_surface_heap_cannot_starve_guarded_native_back_face(tmp_path,monkeypatch,quarter):
    source,board,net,request=plated_fixture(tmp_path,quarter);child=force._copy_family(source,tmp_path/'child')
    # The native same-face inventory owns its real monotonic clock. Keep the
    # scheduling clock in that epoch too; a literal 1000s can be in the far
    # future immediately after a WSL restart and must correctly be refused.
    before=source.read_bytes();origin=time.monotonic();clock=[origin];calls=[]
    monkeypatch.setattr(geometry,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    def bridge(board,A,al,B,bl,width,*args,**kw):
        calls.append((set(al),set(bl),kw))
        if al==bl=={pcbnew.B_Cu}:
            return [('trk',pcbnew.VECTOR2I(*A),pcbnew.VECTOR2I(*B),width,pcbnew.B_Cu)]
        # An unhelpful F heap uses its WHOLE slice. It cannot own later ones.
        clock[0]=kw['deadline_monotonic']+.001;return None
    guard=stubs(monkeypatch,bridge)
    result=geometry.apply_native_portals(child,request,5.)
    assert result['closed']==1 and result['face_strata_count']==9,result
    assert len(calls)==3 and all(d['face_stratified']for d in result['directions'])
    assert all(k['deadline_monotonic']<=origin+5. for _,_,k in calls)
    assert clock[0]<origin+1.75 and any(k=='complete_guard'for k,v in guard)
    assert all(k['native_endpoint_seeds']and k['canonical_turns_only']and k['middle_max_vias']==2
        and k['max_expanded_states']==50000 for _,_,k in calls)
    proof=ordinary.receive(source,child,board_hint='synthetic',net=net)
    assert proof['ok']and proof['complete']and proof['whole_shared_stage_still_required'],proof
    assert source.read_bytes()==before and not result['release_authority']


def test_stratified_refusal_keeps_original_combined_search_and_global_cap(tmp_path,monkeypatch):
    source,board,net,request=plated_fixture(tmp_path);child=force._copy_family(source,tmp_path/'child')
    origin=time.monotonic();clock=[origin];calls=[]
    monkeypatch.setattr(geometry,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    def bridge(board,A,al,B,bl,width,*args,**kw):
        calls.append((set(al),set(bl),kw))
        if len(al)>1 and len(bl)>1:
            return [('trk',pcbnew.VECTOR2I(*A),pcbnew.VECTOR2I(*B),width,pcbnew.F_Cu)]
        clock[0]=kw['deadline_monotonic']+.00001;return None
    stubs(monkeypatch,bridge);request['middle_grid_schedule_mm']=[.5,.25]
    result=geometry.apply_native_portals(child,request,5.)
    assert result['closed']==1 and result['original_combined_portfolio_preserved']
    assert len(calls)==19 and all(k['deadline_monotonic']<=origin+5. for _,_,k in calls)
    assert result['directions'][-1]['face_stratified']is False
    assert ordinary.receive(source,child,board_hint='synthetic',net=net)['ok']


def test_warm_offer_still_owes_complete_native_guard(tmp_path,monkeypatch):
    source,board,net,request=plated_fixture(tmp_path);child=force._copy_family(source,tmp_path/'child')
    before=child.read_bytes()
    def bridge(board,A,al,B,bl,width,*args,**kw):
        return [('trk',pcbnew.VECTOR2I(*A),pcbnew.VECTOR2I(*B),width,pcbnew.F_Cu)]
    seen=stubs(monkeypatch,bridge,accept=False)
    result=geometry.apply_native_portals(child,request,5.)
    assert result['closed']==0 and any(k=='complete_guard'for k,v in seen)
    assert child.read_bytes()==before


def test_actual_multiface_native_search_keeps_saved_source_scope(tmp_path):
    source,board,net,request=plated_fixture(tmp_path);child=force._copy_family(source,tmp_path/'child')
    before=source.read_bytes()
    result=geometry.apply_native_portals(child,request,10.)
    assert result['closed']==1 and result['face_strata_count']>0,result
    proof=ordinary.receive(source,child,board_hint='synthetic',net=net)
    assert proof['ok']and proof['complete'],proof
    assert source.read_bytes()==before and not result['no_path_proof']
