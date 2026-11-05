"""Independent finite Ground/inventory work, not more time in an old lease."""
import copy
import pytest
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as receiver
from test_macro_compilation_leases import Clock

SIX=('source_ownership','native_frame_and_cuts','canonical_boundary_ownership',
    'complete_endpoint_obligations','independent_ground_endpoint_obligations','complete_component_inventory')


def test_explicit_six_finite_stages_have_fresh_boundaries_and_no_default_change(monkeypatch):
    clock=Clock();monkeypatch.setattr(compiler.time,'monotonic',clock)
    assert compiler.compilation_phases()==compiler.COMPILATION_PHASES
    assert compiler.compilation_phases([1]*3)==compiler.COMPILATION_PHASES
    assert len(compiler.compilation_phases([1]*4))==4
    assert compiler.compilation_phases([1]*6)==SIX
    events=[];checks=[]
    with compiler.observe_compilation_phases(events.append):
        lease=compiler._CompilationLeases(1,[1]*6)
        for name in SIX[1:]:
            clock.spend(.9);lease.advance(name,lambda:checks.append(True)or True)
        clock.spend(.9);lease.finish(lambda:checks.append(True)or True)
    assert lease.finished and len(checks)==6
    assert [(e['event'],e['phase'])for e in events]==[pair for name in SIX for pair in(('start',name),('finish',name))]


@pytest.mark.parametrize('boundary',range(6))
@pytest.mark.parametrize('fault',['expired','input_changed','validation_time'])
def test_every_one_of_the_six_stages_refuses_without_borrowing(monkeypatch,boundary,fault):
    clock=Clock();monkeypatch.setattr(compiler.time,'monotonic',clock)
    lease=compiler._CompilationLeases(1,[1]*6)
    for name in SIX[1:boundary+1]:lease.advance(name,lambda:True)
    def check():
        if fault=='validation_time':clock.spend(1.)
        return fault!='input_changed'
    if fault=='expired':clock.now=lease.deadline
    with pytest.raises(ValueError,match='deadline|source_or_code_changed'):
        if boundary==5:lease.finish(check)
        else:lease.advance(SIX[boundary+1],check)
    assert not lease.finished and lease.index==boundary


def test_complete_inventory_and_Ground_cannot_be_skipped(monkeypatch):
    clock=Clock();monkeypatch.setattr(compiler.time,'monotonic',clock)
    lease=compiler._CompilationLeases(1,[1]*6)
    for name in SIX[1:4]:lease.advance(name,lambda:True)
    with pytest.raises(ValueError,match='all_macro'):lease.finish(lambda:True)
    with pytest.raises(ValueError,match='ordered_complete'):lease.advance(SIX[5],lambda:True)
    lease.advance(SIX[4],lambda:True)
    with pytest.raises(ValueError,match='all_macro'):lease.finish(lambda:True)
    assert not lease.finished


def test_native_six_stage_request_inventory_is_identical_to_fresh_four_stage(tmp_path,monkeypatch):
    from test_complete_cell_connections import native_source
    import cec_force_current as force
    source,_,_,proposal=native_source(tmp_path,monkeypatch)
    before=force._hash(source);events=[]
    _,four=compiler.compile(source,proposal['poses'],board_hint='opaque',compilation_phase_timeouts_s=[9.]*4)
    with compiler.observe_compilation_phases(events.append):
        _,six=compiler.compile(source,proposal['poses'],board_hint='opaque',compilation_phase_timeouts_s=[9.]*6)
    assert [e['phase']for e in events if e['event']=='start']==list(SIX)
    fresh=copy.deepcopy(six)
    fresh['explicit_native_macro_options']['compilation_phase_timeouts_s']=[9.]*4
    assert four==fresh and force._hash(source)==before
    assert not six['routing_admitted']and not six['saved_candidate_authorized']


def test_saved_receiver_independently_runs_all_six_twice(tmp_path,monkeypatch):
    from test_complete_macro_cell import saved_pair
    source,child,_=saved_pair(tmp_path,monkeypatch)
    before=[p.read_bytes()for p in(source,child)]
    result=receiver.receive(source,child,board_hint='opaque',timeout_s=9.5,compilation_phase_timeouts_s=[9.]*6)
    assert result['ok']and result['complete'],result['errors']
    stages=result['bounded_composition']['constituents']
    for prefix in('source_compilation:','ground_source_compilation:'):
        assert all(stages.count(prefix+name)==1 for name in SIX)
    assert set(stages)==set(result['stage_timings_s'])
    assert before==[p.read_bytes()for p in(source,child)]
    assert all(not result[k]for k in('routing_admitted','fab_ready','release_authority','current_qualified'))


def test_six_stage_packet_cannot_exceed_saved_or_quiet_receiving_limit():
    import cec_macro_quiet_output as quiet
    uid='e450e8f7-83a0-468b-9304-4ac09021a6fe'
    stages=quiet.receiving_stages(dict(compilation_phase_timeouts_s=[9.]*6),[uid],9.5)
    assert stages[1:7]==['compile:'+name for name in SIX]
    bad=[9.]*6;bad[4]=9.6
    with pytest.raises(ValueError,match='exceed_receiving_limit'):
        receiver.receive('missing-source','missing-child',board_hint='opaque',timeout_s=9.5,compilation_phase_timeouts_s=bad)
    with pytest.raises(ValueError,match='exceeds_receiving_lease'):
        quiet.receiving_stages(dict(compilation_phase_timeouts_s=bad),[uid],9.5)
