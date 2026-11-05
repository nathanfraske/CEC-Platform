"""Several mandatory native gates each retain their own ten-second ceiling."""
import pytest
import cec_native_cell_pose_domains as domains
from test_complete_macro_cell import fixture


def receiving_trial(tmp_path,monkeypatch,quarter,costs):
    source,parent,unused,packet=fixture(tmp_path,monkeypatch,quarter=quarter)
    seed=packet['source_plan']['poses'];cap=next(iter(packet['source_plan']['selected_bypasses']))
    clock=[100.];actual_compile=domains.compiler.compile
    actual_prefill=domains.compiler.pre_refill_barrel_screen;actual_fill=domains.additive._ground_refill
    def compile(*a,**k):
        result=actual_compile(*a,**k);clock[0]+=costs['compile'];return result
    def prefill(*a,**k):
        result=actual_prefill(*a,**k);clock[0]+=costs['prefill'];return result
    def fill(*a,**k):
        result=actual_fill(*a,**k);clock[0]+=costs['fill'];return result
    monkeypatch.setattr(domains.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(domains.compiler,'compile',compile)
    monkeypatch.setattr(domains.compiler,'pre_refill_barrel_screen',prefill)
    monkeypatch.setattr(domains.additive,'_ground_refill',fill)
    raw=source.read_bytes()
    result=domains.propose(source,seed,board_hint='opaque',transport_source_barrels=True,
        frozen_target_refs=[cap],radius_mm=.25,grid_mm=.25,max_candidates=16,max_results=2)
    assert raw==source.read_bytes() and not result['routing_admitted']
    assert result['independent_stage_max_seconds']==10.
    return result


@pytest.mark.parametrize('quarter',range(4))
def test_completed_source_compile_does_not_starve_following_native_gates(tmp_path,monkeypatch,quarter):
    result=receiving_trial(tmp_path,monkeypatch,quarter,dict(compile=8.,prefill=4.,fill=3.))
    assert result['offers'],result['fresh_receiving']
    assert result['fresh_receiving'][-1]['source_owned_macro_native_frame']['ok']
    assert result['explicit_maximum_stages']==1+2+6*2


@pytest.mark.parametrize('stage',['compile','prefill','fill'])
def test_an_individual_expired_native_gate_still_refuses_the_offer(tmp_path,monkeypatch,stage):
    costs=dict(compile=0.,prefill=0.,fill=0.);costs[stage]=11.
    result=receiving_trial(tmp_path,monkeypatch,0,costs)
    assert not result['offers'] and result['fresh_receiving']
    expected={'compile':'source_compile_deadline','prefill':'pre_refill_barrel_deadline','fill':'native_refill_deadline'}[stage]
    assert all(expected in q['refusal'] for q in result['fresh_receiving'])
