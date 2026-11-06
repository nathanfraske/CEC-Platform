"""Explicit fresh singleton ownership and composition are finite operations."""
import copy,time
from pathlib import Path
import pcbnew,pytest
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as receiver
import cec_selected_cap_ground_boundary as multiport
from test_macro_compilation_leases import Clock

EIGHT=('source_ownership','native_frame_and_cuts','canonical_boundary_ownership',
    'canonical_ground_multiport_boundary','canonical_boundary_composition',
    'complete_endpoint_obligations','independent_ground_endpoint_obligations','complete_component_inventory')


def test_eight_is_explicit_and_legacy_phase_sequences_are_unchanged(monkeypatch):
    from test_macro_ground_compilation_leases import SIX
    assert compiler.compilation_phases()==compiler.COMPILATION_PHASES
    assert compiler.compilation_phases([1]*3)==compiler.COMPILATION_PHASES
    assert compiler.compilation_phases([1]*4)==SIX[:4]
    assert compiler.compilation_phases([1]*6)==SIX
    assert compiler.compilation_phases([1]*8)==EIGHT
    clock=Clock();monkeypatch.setattr(compiler.time,'monotonic',clock);events=[];checks=[]
    with compiler.observe_compilation_phases(events.append):
        leases=compiler._CompilationLeases(1,[1]*8)
        for phase in EIGHT[1:]:
            clock.spend(.9);leases.advance(phase,lambda:checks.append(True)or True)
        clock.spend(.9);leases.finish(lambda:checks.append(True)or True)
    assert len(checks)==8 and leases.finished
    assert [(q['event'],q['phase'])for q in events]==[v for phase in EIGHT for v in(('start',phase),('finish',phase))]


@pytest.mark.parametrize('boundary',range(8))
@pytest.mark.parametrize('fault',['expired','changed','validation_time'])
def test_every_named_operation_refuses_expiry_change_and_validation_overrun(monkeypatch,boundary,fault):
    clock=Clock();monkeypatch.setattr(compiler.time,'monotonic',clock)
    lease=compiler._CompilationLeases(1,[1]*8)
    for phase in EIGHT[1:boundary+1]:lease.advance(phase,lambda:True)
    def check():
        if fault=='validation_time':clock.spend(1.)
        return fault!='changed'
    if fault=='expired':clock.now=lease.deadline
    with pytest.raises(ValueError,match='deadline|source_or_code_changed'):
        if boundary==7:lease.finish(check)
        else:lease.advance(EIGHT[boundary+1],check)
    assert lease.index==boundary and not lease.finished


@pytest.mark.parametrize('fault',['skip_multiport','skip_composition','early_finish','repeat','ten','seven'])
def test_no_phase_can_be_omitted_repeated_or_invented(monkeypatch,fault):
    if fault in('ten','seven'):
        with pytest.raises(ValueError):compiler._phase_budgets([1]*(10 if fault=='ten'else 7))
        return
    clock=Clock();monkeypatch.setattr(compiler.time,'monotonic',clock)
    lease=compiler._CompilationLeases(1,[1]*8)
    for phase in EIGHT[1:3]:lease.advance(phase,lambda:True)
    with pytest.raises(ValueError):
        if fault=='skip_multiport':lease.advance(EIGHT[4],lambda:True)
        elif fault=='skip_composition':
            lease.advance(EIGHT[3],lambda:True);lease.advance(EIGHT[5],lambda:True)
        elif fault=='repeat':lease.advance(EIGHT[2],lambda:True)
        else:lease.finish(lambda:True)
    assert not lease.finished


def test_real_native_eight_and_six_packets_identical_except_explicit_work_sequence(tmp_path,monkeypatch):
    from test_complete_cell_connections import native_source
    source,_,_,p=native_source(tmp_path,monkeypatch);before=source.read_bytes();events=[]
    _,six=compiler.compile(source,p['poses'],board_hint='opaque',compilation_phase_timeouts_s=[9.]*6)
    with compiler.observe_compilation_phases(events.append):
        _,eight=compiler.compile(source,p['poses'],board_hint='opaque',compilation_phase_timeouts_s=[9.]*8)
    assert [q['phase']for q in events if q['event']=='start']==list(EIGHT)
    adjusted=copy.deepcopy(eight);adjusted['explicit_native_macro_options']['compilation_phase_timeouts_s']=[9.]*6
    assert adjusted==six and source.read_bytes()==before
    assert not eight['routing_admitted']and not eight['saved_candidate_authorized']


def test_saved_receiver_runs_all_eight_constituents_twice_without_prefix_acceptance(tmp_path,monkeypatch):
    from test_complete_macro_cell import saved_pair
    source,child,_=saved_pair(tmp_path,monkeypatch);before=[p.read_bytes()for p in(source,child)]
    result=receiver.receive(source,child,board_hint='opaque',timeout_s=9.5,compilation_phase_timeouts_s=[9.]*8)
    assert result['ok']and result['complete'],result['errors']
    phases=result['bounded_composition']['constituents']
    for prefix in('source_compilation:','ground_source_compilation:'):
        assert all(phases.count(prefix+name)==1 for name in EIGHT)
    assert set(phases)==set(result['stage_timings_s'])and before==[p.read_bytes()for p in(source,child)]
    assert all(not result[k]for k in('routing_admitted','fab_ready','release_authority','current_qualified'))


@pytest.mark.parametrize('fault',['native','proposal','transport','canonical','family','code','expired','long','bool'])
def test_suspended_frame_is_never_a_caller_owned_or_reusable_certificate(tmp_path,monkeypatch,fault):
    from test_ground_boundary_single_call import source_case
    b,p,t,_=source_case(tmp_path,monkeypatch)
    steps=compiler._extra_ownership_steps(b,Path(b.GetFileName()),t,p,time.monotonic()+8.)
    assert next(steps)=='canonical_ground_multiport_boundary'
    if fault=='native':b.FindFootprintByReference('R_program').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='proposal':p['selected_programming_resistors']['R_program']['current_authority']=True
    elif fault=='transport':t['changes']=[]
    elif fault=='canonical':Path(p['board_hint']).write_text('; changed canonical Source')
    elif fault=='family':Path(b.GetFileName()).with_suffix('.kicad_pro').write_text('{}')
    elif fault=='code':monkeypatch.setattr(compiler.force,'_code_identity',lambda:{'changed':'code'})
    deadline=True if fault=='bool'else time.monotonic()+(-1 if fault=='expired'else 11 if fault=='long'else 8)
    with pytest.raises(ValueError,match='live_inputs_changed|bounded_fresh_ground'):
        compiler._finish_extra_ownership(steps,deadline)


def test_quiet_and_saved_receivers_cannot_exceed_existing_per_operation_limit():
    import cec_macro_quiet_output as quiet
    uid='e450e8f7-83a0-468b-9304-4ac09021a6fe'
    stages=quiet.receiving_stages(dict(compilation_phase_timeouts_s=[9.]*8),[uid],9.5)
    assert stages[1:9]==['compile:'+name for name in EIGHT]
    bad=[9.]*8;bad[3]=9.6
    with pytest.raises(ValueError,match='exceed_receiving_limit'):
        receiver.receive('missing-source','missing-child',board_hint='opaque',timeout_s=9.5,compilation_phase_timeouts_s=bad)
    with pytest.raises(ValueError,match='exceeds_receiving_lease'):
        quiet.receiving_stages(dict(compilation_phase_timeouts_s=bad),[uid],9.5)


def test_completed_or_caller_authored_generator_cannot_supply_an_ownership_result(tmp_path,monkeypatch):
    from test_ground_boundary_single_call import source_case
    def forged():
        yield 'canonical_ground_multiport_boundary'
        return [{'caller':'forged authority'}]
    fake=forged();next(fake)
    with pytest.raises(ValueError,match='fresh_private_native_boundary_operation'):
        compiler._finish_extra_ownership(fake,time.monotonic()+8.)
    b,p,t,_=source_case(tmp_path,monkeypatch)
    steps=compiler._extra_ownership_steps(b,Path(b.GetFileName()),t,p,time.monotonic()+8.)
    next(steps);assert len(compiler._finish_extra_ownership(steps,time.monotonic()+8.))==2
    with pytest.raises(ValueError,match='fresh_private_native_boundary_operation'):
        compiler._finish_extra_ownership(steps,time.monotonic()+8.)
