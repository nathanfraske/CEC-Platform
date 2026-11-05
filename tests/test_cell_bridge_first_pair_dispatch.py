"""Complete-cell consumers must fund an existing guarded first-pair trial.

This changes search order, not path/current admission. Synthetic scheduling
spies retain real native source roles and endpoint-join guards.
"""
import pcbnew
import pytest

import cec_fr as fr
import cec_native_via_frontier as frontier
from test_cell_whole_current_bridge_handoff import dispatch
from test_cell_complete_bridge_guard import fixture,run


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('role',['power','address','unowned_address'])
def test_source_role_does_not_lose_first_pair_schedule(monkeypatch,back,angle,role):
    board,pad,other,bridges,legs,detail,deadline=dispatch(
        monkeypatch,back=back,angle=angle,role=role)
    assert bridges
    assert all(kw.get('seat_pair_first')is True for args,kw in bridges)
    assert all(callable(kw.get('ops_ok'))and kw['deadline_monotonic']<=deadline
        for args,kw in bridges)
    assert detail['unchanged_current_contract']['current_authority']['amps']>0


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_different_actual_pad_faces_keep_existing_first_pair_budget(monkeypatch,back,angle):
    board,pad,other,bridges,legs,detail,deadline=dispatch(
        monkeypatch,back=back,angle=angle,same_face=False)
    assert bridges and other is not None
    assert all(kw.get('seat_pair_first')is True and kw['deadline_monotonic']<=deadline
        for args,kw in bridges)
    assert all(kw['start_escape']and kw['end_escape']for args,kw in bridges)


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_frontier_and_direct_call_sites_keep_same_guard_and_outer_lease(monkeypatch,back,quarter):
    board,request,face,other,point,ops,good,bad=fixture(monkeypatch,back=back,quarter=quarter)
    a,b=tuple(request['a']['at_nm']),tuple(request['b']['at_nm'])
    p,q=point(12,8),point(23,8)
    monkeypatch.setattr(frontier,'sites',lambda _b,_n,at,**_k:dict(
        sites_nm=[p]if tuple(at)==a else[q],drill_mm=.3,diameter_mm=.6))
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',lambda _b,s,t,w,*_a,**_k:
        [(tuple(s),tuple(t),w)])
    calls=[]
    def bridge(_b,start,_sf,end,_ef,*args,**kwargs):
        assert kwargs.get('seat_pair_first')is True
        assert callable(kwargs.get('ops_ok'))
        if tuple(start)==p:
            assert tuple(end)==q
            assert kwargs['ops_ok'](ops([p,q],layer=other))is True
        else:
            assert tuple(start)==a and tuple(end)==b
            assert kwargs['ops_ok'](bad)is False and kwargs['ops_ok'](good)is True
        calls.append((tuple(start),kwargs));return None
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    emitted,detail,deadline=run(board,request,other)
    assert not emitted and {start for start,_ in calls}=={a,p}
    assert all(kw['deadline_monotonic']<=deadline for _,kw in calls)
    assert detail['native_plain_endpoint_turn_refusals']==0
