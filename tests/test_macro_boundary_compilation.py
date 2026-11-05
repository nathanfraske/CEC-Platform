"""Fresh boundary ownership is explicit bounded work, never a cached pass."""
import pytest
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as receiver
from test_macro_compilation_leases import Clock


FOUR = ('source_ownership', 'native_frame_and_cuts',
    'canonical_boundary_ownership', 'complete_endpoint_obligations')


def test_four_phases_are_explicit_and_legacy_names_stay_unchanged(monkeypatch):
    clock=Clock();monkeypatch.setattr(compiler.time,'monotonic',clock)
    assert compiler.compilation_phases() == compiler.COMPILATION_PHASES
    assert compiler.compilation_phases([1,2,3]) == compiler.COMPILATION_PHASES
    assert compiler.compilation_phases([1,2,3,4]) == FOUR
    events=[];checks=[]
    with compiler.observe_compilation_phases(events.append):
        lease=compiler._CompilationLeases(1,[1,2,3,4])
        for index,name in enumerate(FOUR[1:]):
            clock.spend(.5)
            assert lease.advance(name,lambda:checks.append(clock.now)or True)==clock.now+index+2
        clock.spend(.5);lease.finish(lambda:checks.append(clock.now)or True)
    assert lease.finished and len(checks)==4
    assert [(r['event'],r['phase'])for r in events]==[
        pair for name in FOUR for pair in (('start',name),('finish',name))]


@pytest.mark.parametrize('boundary',range(4))
@pytest.mark.parametrize('fault',['expired','input_changed','validation_time'])
def test_every_boundary_refuses_without_borrowing(monkeypatch,boundary,fault):
    clock=Clock();monkeypatch.setattr(compiler.time,'monotonic',clock)
    lease=compiler._CompilationLeases(1,[1,1,1,1])
    for name in FOUR[1:boundary+1]:lease.advance(name,lambda:True)
    def check():
        if fault=='validation_time':clock.spend(1.)
        return fault!='input_changed'
    if fault=='expired':clock.now=lease.deadline
    with pytest.raises(ValueError,match='deadline|source_or_code_changed'):
        if boundary==3:lease.finish(check)
        else:lease.advance(FOUR[boundary+1],check)
    assert not lease.finished and lease.index==boundary


def test_explicit_boundary_cannot_skip_remaining_endpoint_obligations(monkeypatch):
    clock=Clock();monkeypatch.setattr(compiler.time,'monotonic',clock)
    lease=compiler._CompilationLeases(1,[1,1,1,1])
    lease.advance(FOUR[1],lambda:True)
    with pytest.raises(ValueError,match='ordered_complete'):
        lease.advance(FOUR[3],lambda:True)
    lease.advance(FOUR[2],lambda:True)
    with pytest.raises(ValueError,match='all_macro'):
        lease.finish(lambda:True)
    assert not lease.finished


def test_literal_native_four_phase_packet_fresh_replay(tmp_path,monkeypatch):
    from test_complete_cell_connections import native_source
    import cec_force_current as force
    source,parent,private,proposal=native_source(tmp_path,monkeypatch)
    before=force._hash(source);events=[]
    with compiler.observe_compilation_phases(events.append):
        draft,packet=compiler.compile(source,proposal['poses'],board_hint='opaque',
            compilation_phase_timeouts_s=[9.,9.,9.,9.])
    options=compiler.packet_options(packet)
    assert options['compilation_phase_timeouts_s']==[9.,9.,9.,9.]
    _,fresh=compiler.compile(source,proposal['poses'],board_hint='opaque',**options)
    assert packet==fresh and force._hash(source)==before
    assert [e['phase']for e in events if e['event']=='start']==list(FOUR)
    assert not packet['routing_admitted'] and not packet['saved_candidate_authorized']


def test_complete_saved_receiver_counts_both_fresh_four_phase_derivations(tmp_path,monkeypatch):
    from test_complete_macro_cell import saved_pair
    source,child,_=saved_pair(tmp_path,monkeypatch)
    before=[p.read_bytes()for p in (source,child)]
    result=receiver.receive(source,child,board_hint='opaque',timeout_s=9.5,
        compilation_phase_timeouts_s=[9.,9.,9.,9.])
    assert result['ok'] and result['complete'],result['errors']
    stages=result['bounded_composition']['constituents']
    for prefix in ('source_compilation:','ground_source_compilation:'):
        assert all(stages.count(prefix+name)==1 for name in FOUR)
    assert set(stages)==set(result['stage_timings_s'])
    assert before==[p.read_bytes()for p in (source,child)]
    assert all(not result[k]for k in ('routing_admitted','fab_ready','release_authority','current_qualified'))


def test_quiet_receiver_schedules_exact_same_four_phases():
    import cec_macro_quiet_output as quiet
    uid='e450e8f7-83a0-468b-9304-4ac09021a6fe'
    options=dict(compilation_phase_timeouts_s=[9.,9.,9.,9.])
    stages=quiet.receiving_stages(options,[uid],9.5)
    assert stages[1:5]==['compile:'+name for name in FOUR]
    with pytest.raises(ValueError,match='exceeds_receiving_lease'):
        quiet.receiving_stages(dict(compilation_phase_timeouts_s=[9.,9.,9.6,9.]),[uid],9.5)


def test_four_phase_packet_cannot_exceed_saved_receiving_limit():
    with pytest.raises(ValueError,match='exceed_receiving_limit'):
        receiver.receive('missing-source','missing-child',board_hint='opaque',timeout_s=9.,
            compilation_phase_timeouts_s=[9.,9.,9.5,9.])
