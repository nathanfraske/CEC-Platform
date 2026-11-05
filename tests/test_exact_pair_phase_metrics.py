"""Bridge telemetry observes real native search, never candidate authority."""
import time
import pytest
import pcbnew
import cec_fr as fr
from test_bridge_new_hole_pair import fixture


def bridge(data,diagnostic=None,**kw):
    path,a,b,side,other,drill=data;board=pcbnew.LoadBoard(str(path))
    return fr._lastmile_bridge(board,tuple(a),{side},tuple(b),{side},200000,
        board.GetNetcodeFromNetname('RENAMED'),[other],200000,drill=drill,dia=drill+.3,
        allow_maze=False,allow_lattice=False,seat_limit=1,diagnostics=diagnostic,**kw)


@pytest.mark.parametrize('rotation,back',[(0,False),(90,True),(45,False)])
def test_metrics_keep_actual_candidate_order_and_admission(tmp_path,rotation,back):
    data=fixture(tmp_path,rotation=rotation,back=back);before=data[0].read_bytes()
    expected=bridge(data);diagnostic={};actual=bridge(data,diagnostic)
    assert expected and actual==expected
    m=diagnostic['phase_metrics']
    assert m['outcome']=='candidate_returned' and not m['no_path_proof']
    assert not m['release_authority'] and m['phase_times_inclusive']
    assert m['phases']['setup']['calls']>0 and m['phases']['seats']['calls']>0
    assert m['phases']['middle']['calls']>0
    assert data[0].read_bytes()==before


def test_exhausted_budget_empty_counters_still_has_honest_stage(tmp_path):
    data=fixture(tmp_path);d={}
    assert bridge(data,d,deadline_monotonic=time.monotonic()-1)is None
    m=d['phase_metrics'];assert m['deadline_exhausted_at_return']
    assert m['outcome']=='no_candidate_returned' and not m['no_path_proof']
    assert set(m['phases'])=={'setup','seats','middle','validator'}
    assert all(r['calls']>=0 and r['elapsed_s']>=0 for r in m['phases'].values())


def test_validator_refusal_is_not_changed_by_metrics(tmp_path):
    data=fixture(tmp_path);d={};seen=[]
    def refuse(ops):seen.append(ops);return False
    assert bridge(data,ops_ok=refuse)is None;expected=list(seen);seen.clear()
    assert bridge(data,d,ops_ok=refuse)is None
    assert seen==expected
    assert d['phase_metrics']['phases']['validator']['calls']==len(seen)>0
    assert not d['no_path_proof']


def test_exception_recorded_without_swallowing_or_relabeling():
    @fr._bridge_phase_metrics
    def work(*,diagnostics=None):raise RuntimeError('original refusal')
    d={}
    with pytest.raises(RuntimeError,match='original refusal'):work(diagnostics=d)
    assert d['phase_metrics']['outcome']=='exception'
    assert not d['phase_metrics']['no_path_proof']
