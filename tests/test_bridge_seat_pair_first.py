"""A guarded launch pair gets a middle trial before speculative seat depth."""
import json
import time
import pcbnew
import pytest
import cec_fr as fr
import cec_search_budget as budget
from test_bridge_new_hole_pair import fixture
from cec_route_proposal_guard import RouteProposalGuard


def solve(data,*,diagnostics=None,policy=None,ops_ok=None,deadline=None):
    path,a,b,side,other,drill=data;board=pcbnew.LoadBoard(str(path))
    options={}if policy is None else dict(seat_pair_first=policy)
    return board,fr._lastmile_bridge(board,tuple(a),{side},tuple(b),{side},200000,
        board.GetNetcodeFromNetname('RENAMED'),[other],200000,drill=drill,dia=drill+.3,
        allow_maze=False,allow_lattice=False,seat_limit=8,diagnostics=diagnostics,
        deadline_monotonic=time.monotonic()+4. if deadline is None else deadline,
        ops_ok=ops_ok,**options)


@pytest.mark.parametrize('rotation,back',[(0,False),(90,True),(180,False),(270,True),(45,False)])
def test_actual_guarded_first_pair_returns_without_spending_eight_seats_per_end(tmp_path,rotation,back):
    data=fixture(tmp_path,rotation=rotation,back=back);raw=data[0].read_bytes();d={}
    board=pcbnew.LoadBoard(str(data[0]))
    guard=RouteProposalGuard(board,'RENAMED',board_path=str(data[0]))
    _,ops=solve(data,policy=True,diagnostics=d,ops_ok=guard)
    assert ops and guard(ops)
    assert d['phase_metrics']['phases']['middle']['calls']>=1
    assert d['phase_metrics']['phases']['validator']['calls']>=1
    assert len(d['endpoints'])==2 and all(e['seats']==1 and e['collection_limit']==1 for e in d['endpoints'])
    assert all(e['counters'].get('origin_geometry_trials')==1 for e in d['endpoints'])
    assert data[0].read_bytes()==raw and not d['no_path_proof']and not d['release_authority']


def test_false_policy_is_identical_to_legacy_search_and_geometry(tmp_path):
    data=fixture(tmp_path);first={};second={}
    assert solve(data,diagnostics=first)[1]==solve(data,policy=False,diagnostics=second)[1]
    assert first['endpoints']==second['endpoints']and first['layers']==second['layers']


def test_validator_refusal_retains_full_seat_domain_not_cached_partial_menu(tmp_path):
    data=fixture(tmp_path);d={};seen=[]
    def refuse(ops):seen.append(ops);return False
    _,ops=solve(data,policy=True,diagnostics=d,ops_ok=refuse)
    assert ops is None and seen
    assert len(d['endpoints'])==4
    assert [e['collection_limit']for e in d['endpoints']]==[1,1,None,None]
    assert all(e['seats']>1 for e in d['endpoints'][2:])
    assert not d['no_path_proof']and not d['phase_metrics']['deadline_exhausted_at_return']


def test_middle_receives_work_before_more_speculative_seats_consume_fake_clock(tmp_path,monkeypatch):
    data=fixture(tmp_path);clock=[100.];real=fr._via_spot_clear;calls=[]
    def costed_real_guard(*args,**kwargs):
        calls.append(tuple(args[1]));clock[0]+=1.
        return real(*args,**kwargs)
    monkeypatch.setattr(fr.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(fr,'_via_spot_clear',costed_real_guard)
    d={}
    with budget.scoped(100000)as work:
        _,ops=solve(data,policy=True,diagnostics=d,deadline=103.)
        assert ops and len(calls)==2
        assert work.stop_reason is None and not budget.exhausted(103.)
    assert d['phase_metrics']['phases']['middle']['calls']>=1
    clock[0]=100.;calls.clear();d={}
    _,ops=solve(data,policy=False,diagnostics=d,deadline=103.)
    assert ops is None and d['phase_metrics']['phases']['middle']['calls']==0


@pytest.mark.parametrize('policy,deadline',[(1,None),('yes',None),(True,float('inf')),(True,1e30)])
def test_first_pair_schedule_needs_literal_boolean_and_finite_existing_lease(tmp_path,policy,deadline):
    data=fixture(tmp_path)
    with pytest.raises(ValueError,match='seat_pair_first'):
        solve(data,policy=policy,deadline=deadline)


def test_expired_parent_lease_cannot_be_reset_by_scheduling(tmp_path):
    d={}
    _,ops=solve(fixture(tmp_path),policy=True,diagnostics=d,deadline=time.monotonic()-1.)
    assert ops is None and d['phase_metrics']['deadline_exhausted_at_return']
    assert d['phase_metrics']['phases']['middle']['calls']==0


def test_optin_actual_saved_board_has_no_native_errors_or_opens(tmp_path):
    import cec_native_drc_runner as native
    data=fixture(tmp_path);board,ops=solve(data,policy=True);assert ops
    for op in ops:
        if op[0]=='via':
            item=pcbnew.PCB_VIA(board);item.SetPosition(op[1]);item.SetViaType(pcbnew.VIATYPE_THROUGH)
            item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);item.SetDrill(pcbnew.FromMM(op[2]));item.SetWidth(pcbnew.FromMM(op[3]))
        else:
            item=pcbnew.PCB_TRACK(board);item.SetStart(op[1]);item.SetEnd(op[2]);item.SetWidth(op[3]);item.SetLayer(op[4])
        item.SetNet(board.FindNet('RENAMED'));board.Add(item)
    child=tmp_path/'child.kicad_pcb';pcbnew.SaveBoard(str(child),board)
    child.with_suffix('.kicad_pro').write_bytes(data[0].with_suffix('.kicad_pro').read_bytes())
    received=native.run(child,tmp_path/'native.json',
        reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',timeout_s=10.)
    assert received['ok']and received['complete'],received
    raw=json.loads((tmp_path/'native.json').read_text())
    assert not raw['unconnected_items']and not any(v['severity']=='error'for v in raw['violations'])
