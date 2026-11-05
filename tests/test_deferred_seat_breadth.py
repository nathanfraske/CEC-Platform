"""Finite fair work allocation is not new geometry or no-path authority."""
import time
import pytest
import cec_fr as fr
from test_exact_pair_phase_metrics import bridge
from test_bridge_new_hole_pair import fixture


def test_ranked_existing_deferred_seats_get_only_eight_attempts_and_quarter_lease(monkeypatch):
    monkeypatch.setattr(fr.time,'monotonic',lambda:100.)
    deferred={(i,0):(float(i),(i,0))for i in range(20,0,-1)}
    before=dict(deferred);seen=[];stats={}
    fr._fund_deferred_seat_breadth(deferred,lambda x,y,lease:seen.append((x,y,lease))or False,
        deadline=108.,stats=stats)
    assert [x for x,y,lease in seen]==list(range(1,9))
    assert all(100.<lease<=102. for x,y,lease in seen)
    assert stats['early_deferred_maze_trials']==8 and deferred==before


def test_success_stops_extra_work_and_failed_portfolio_remains_available(monkeypatch):
    monkeypatch.setattr(fr.time,'monotonic',lambda:0.)
    deferred={(i,0):(i,(i,0))for i in range(16)};seen=[]
    fr._fund_deferred_seat_breadth(deferred,lambda x,y,lease:seen.append(x)or x==2,deadline=8.)
    assert seen==[0,1,2]
    assert len(deferred)==16 # all failed/untried seats remain for final search


def test_expiry_never_invokes_geometry(monkeypatch):
    monkeypatch.setattr(fr.time,'monotonic',lambda:10.)
    fr._fund_deferred_seat_breadth({(0,0):(0,(0,0))},
        lambda *args:pytest.fail('expired work must not start'),deadline=9.)


@pytest.mark.parametrize('rotation,back',[(0,False),(90,True),(45,False)])
def test_native_fast_candidate_identical_under_explicit_fair_effort(tmp_path,rotation,back):
    data=fixture(tmp_path,rotation=rotation,back=back);before=data[0].read_bytes()
    expected=bridge(data);d={}
    actual=bridge(data,d,deferred_seat_breadth=True,deadline_monotonic=time.monotonic()+5.)
    assert actual==expected and expected
    assert data[0].read_bytes()==before and not d['no_path_proof']
    assert all(not e['counters'].get('early_deferred_maze_trials')for e in d['endpoints'])


@pytest.mark.parametrize('policy,deadline',[(1,1.),('yes',1.),(True,None),(True,float('inf'))])
def test_optin_requires_literal_boolean_and_existing_finite_lease(tmp_path,policy,deadline):
    with pytest.raises(ValueError,match='deferred_seat_breadth'):
        bridge(fixture(tmp_path),{},deferred_seat_breadth=policy,deadline_monotonic=deadline)


@pytest.mark.parametrize('wall_s,expanded_fair',[(8.,True),(35.,False)])
def test_actual_certificate_caller_keeps_long_legacy_lease_without_short_optin(monkeypatch,wall_s,expanded_fair):
    import cec_certificate_repair as repair
    from test_lastmile import _board
    from test_field_proposals import signature
    b=_board([(5,5,'/N'),(8,5,'/N')],edge=(0,0,30,30))
    for fp in b.GetFootprints():list(fp.Pads())[0].SetPadName('1')
    window=repair.NegotiationWindow(net='/N',distance_mm=3,width_mm=.2,clearance_mm=.2,
        blocker_uuids=(),blocker_nets=(),blocker_hits=0,omitted_movable_blockers=0,
        fixed_blocker_hits=0,trapped_endpoints=0,
        endpoints=(dict(kind='pad',ref='X1',pad='1'),dict(kind='pad',ref='X2',pad='1')),priority=())
    before=signature(b);calls=[]
    monkeypatch.setattr(fr,'_project_netclass_resolver',lambda path:lambda net:{})
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',lambda *a,**kw:None)
    monkeypatch.setattr(fr,'_lastmile_refusal_certificate',lambda *a,**kw:{'no_path_proof':False})
    def quick_refusal(*args,**kwargs):
        # Keep native endpoints and real guard objects; only force search
        # families to finish quickly so expanded remaining lease stays long.
        assert callable(kwargs['ops_ok'])
        assert kwargs['planar_guard']is None or callable(kwargs['planar_guard'])
        assert callable(kwargs['leg_ok'])
        assert args[8]==200000
        calls.append(kwargs)
        return None
    monkeypatch.setattr(fr,'_lastmile_bridge',quick_refusal)
    changed,evidence=repair._close_certificate_pair(b,window,board_path='none.kicad_pcb',
        prefer_bridge=True,wall_timeout_s=wall_s)
    assert not changed and signature(b)==before
    assert len(calls)==2
    assert calls[0]['ops_ok']is calls[1]['ops_ok']
    assert calls[0]['planar_guard']is calls[1]['planar_guard']
    assert calls[0]['deferred_seat_breadth']is False
    assert calls[1]['deferred_seat_breadth']is expanded_fair
    remaining=calls[1]['deadline_monotonic']-time.monotonic()
    assert remaining>(30 if wall_s==35 else 0)
    assert remaining<=wall_s
    assert evidence['refusal']=='certificate_pair_no_exact_clear_path'
