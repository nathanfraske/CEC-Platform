"""Search grids propose geometry; they never qualify copper or extend time."""
from types import SimpleNamespace
import pcbnew
import pytest
import cec_fr as fr
import cec_force_current as force
import cec_native_portal_geometry as geometry
import cec_ordinary_signal_completion as ordinary
from test_ordinary_native_portals import fixture,target


def stubs(monkeypatch,bridge,*,accept=True):
    import cec_route_proposal_guard as guards
    import cec_field_search as search
    seen=[]
    class Guard:
        def __init__(self,*a,**k):self.counts={};seen.append(('guard_context',k))
        def __call__(self,ops):seen.append(('complete_guard',ops));return accept
    monkeypatch.setattr(guards,'RouteProposalGuard',Guard)
    monkeypatch.setattr(search,'PlanarSearchGuard',lambda *a,**k:SimpleNamespace(active=False))
    monkeypatch.setattr(fr,'_lastmile_route_layers',lambda b,**k:[pcbnew.In2_Cu]
        if k['exclude_front']else[pcbnew.F_Cu,pcbnew.In2_Cu,pcbnew.B_Cu])
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    return seen


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_coarse_refusal_reaches_fine_without_changing_source_or_saved_scope(tmp_path,monkeypatch,quarter,back):
    source,board,net=fixture(tmp_path,quarter=quarter,back=back)
    q=ordinary.plan(board,source,board_hint='synthetic',net=net)
    candidate=force._copy_family(source,tmp_path/'child');before=source.read_bytes();calls=[]
    def bridge(b,A,al,B,bl,width,*args,**kw):
        calls.append(kw)
        if kw['middle_grid_mm']==.5:return None
        return [('trk',pcbnew.VECTOR2I(*A),pcbnew.VECTOR2I(*B),width,next(iter(al)))]
    guard_calls=stubs(monkeypatch,bridge)
    request=target(board,q);request['middle_grid_schedule_mm']=[.5,.25]
    r=geometry.apply_native_portals(candidate,request,5.)
    assert r['closed']==1 and r['middle_grid_schedule_mm']==[.5,.25]
    assert [c['middle_grid_mm']for c in calls]==[.5,.5,.25]
    assert calls[0]['deadline_monotonic']==calls[1]['deadline_monotonic']
    assert calls[0]['deadline_monotonic']<calls[2]['deadline_monotonic']
    assert all(c['max_expanded_states']==50000 and c['middle_max_vias']==2
        and c['canonical_turns_only']and c['native_endpoint_seeds']for c in calls)
    assert any(k=='complete_guard'for k,v in guard_calls)
    saved=ordinary.receive(source,candidate,board_hint='synthetic',net=net)
    assert saved['ok']and saved['complete']and saved['whole_shared_stage_still_required']
    assert source.read_bytes()==before and not r['release_authority']


def test_coarse_timeout_reserves_fine_time_without_resetting_global_lease(tmp_path,monkeypatch):
    source,board,net=fixture(tmp_path);q=ordinary.plan(board,source,board_hint='synthetic',net=net)
    child=force._copy_family(source,tmp_path/'child');clock=[1000.];calls=[]
    monkeypatch.setattr(geometry,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    def bridge(b,A,al,B,bl,width,*args,**kw):
        calls.append(kw)
        if kw['middle_grid_mm']==.5:
            clock[0]=kw['deadline_monotonic']+.01;return None
        return [('trk',pcbnew.VECTOR2I(*A),pcbnew.VECTOR2I(*B),width,next(iter(al)))]
    stubs(monkeypatch,bridge);request=target(board,q);request['middle_grid_schedule_mm']=[.5,.25]
    r=geometry.apply_native_portals(child,request,5.)
    assert r['closed']==1
    assert [c['middle_grid_mm']for c in calls]==[.5,.25]
    assert [c['deadline_monotonic']for c in calls]==[1002.5,1005.]


@pytest.mark.parametrize('schedule',[None,True,.5,[],[.5,.5],[.25,.5],[.5,0],
    [1.,.5,.25,.1],[float('nan')],[float('inf')],[True],[1.01],[.099],['.5']])
def test_invalid_search_schedule_refuses_before_native_load_or_write(schedule):
    with pytest.raises(ValueError,match='strictly_refining_native_portal_grid_schedule'):
        geometry.apply_native_portals('missing',{'middle_grid_schedule_mm':schedule},5.)


@pytest.mark.parametrize('schedule',[[.5,.25],[.25]])
def test_complete_coarse_or_fine_offer_cannot_bypass_final_native_guard(tmp_path,monkeypatch,schedule):
    source,board,net=fixture(tmp_path);q=ordinary.plan(board,source,board_hint='synthetic',net=net)
    child=force._copy_family(source,tmp_path/'child');original=child.read_bytes()
    def bridge(b,A,al,B,bl,width,*args,**kw):
        return [('trk',pcbnew.VECTOR2I(*A),pcbnew.VECTOR2I(*B),width,next(iter(al)))]
    seen=stubs(monkeypatch,bridge,accept=False)
    request=target(board,q);request['middle_grid_schedule_mm']=schedule
    r=geometry.apply_native_portals(child,request,5.)
    assert r['closed']==0 and any(k=='complete_guard'for k,v in seen)
    assert child.read_bytes()==original


@pytest.mark.parametrize('back',[False,True])
def test_actual_native_search_and_guards_construct_saved_ordinary_join(tmp_path,back):
    source,board,net=fixture(tmp_path,back=back)
    q=ordinary.plan(board,source,board_hint='synthetic',net=net)
    child=force._copy_family(source,tmp_path/'child');original=source.read_bytes()
    request=target(board,q);request['middle_grid_schedule_mm']=[.5,.25]
    r=geometry.apply_native_portals(child,request,10.)
    assert r['closed']==1,r
    proof=ordinary.receive(source,child,board_hint='synthetic',net=net)
    assert proof['ok']and proof['complete'],proof
    assert source.read_bytes()==original
