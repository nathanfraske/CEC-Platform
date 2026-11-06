"""Source roles and actual contact ownership are distinct bounded operations."""
import copy
from contextlib import contextmanager
import os
import time
from pathlib import Path

import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as receiver
import cec_source_device_pinmap as pinmap
import cec_source_ground_leaf as canonical
import cec_source_linear_power_stage as stage
from test_macro_compilation_leases import Clock
from test_macro_multiport_compilation_leases import EIGHT

NINE=(EIGHT[0],'source_contact_ownership',*EIGHT[1:])


def test_nine_is_explicit_and_legacy_sequences_stay_identical(monkeypatch):
    assert compiler.compilation_phases([1]*9)==NINE
    assert compiler.compilation_phases([1]*8)==EIGHT
    assert compiler.compilation_phases()==compiler.COMPILATION_PHASES
    assert len(compiler.compilation_phases([1]*3))==3
    assert len(compiler.compilation_phases([1]*4))==4
    assert len(compiler.compilation_phases([1]*6))==6
    clock=Clock();monkeypatch.setattr(compiler.time,'monotonic',clock);events=[];checks=[]
    with compiler.observe_compilation_phases(events.append):
        lease=compiler._CompilationLeases(1,[1]*9)
        for phase in NINE[1:]:
            clock.spend(.8);lease.advance(phase,lambda:checks.append(True)or True)
        clock.spend(.8);lease.finish(lambda:checks.append(True)or True)
    assert len(checks)==9 and lease.finished
    assert [(q['event'],q['phase'])for q in events]==[
        pair for phase in NINE for pair in(('start',phase),('finish',phase))]


@pytest.mark.parametrize('boundary',range(9))
@pytest.mark.parametrize('fault',['expired','changed','validation_time'])
def test_all_nine_boundaries_refuse_expiry_mutation_and_fence_overrun(monkeypatch,boundary,fault):
    clock=Clock();monkeypatch.setattr(compiler.time,'monotonic',clock)
    lease=compiler._CompilationLeases(1,[1]*9)
    for phase in NINE[1:boundary+1]:lease.advance(phase,lambda:True)
    def check():
        if fault=='validation_time':clock.spend(1.)
        return fault!='changed'
    if fault=='expired':clock.now=lease.deadline
    with pytest.raises(ValueError,match='deadline|source_or_code_changed'):
        if boundary==8:lease.finish(check)
        else:lease.advance(NINE[boundary+1],check)
    assert lease.index==boundary and not lease.finished


def test_actual_native_eight_and_nine_packets_match_except_work_sequence(tmp_path,monkeypatch):
    from test_complete_cell_connections import native_source
    source,_,_,proposal=native_source(tmp_path,monkeypatch);before=source.read_bytes()
    _,eight=compiler.compile(source,proposal['poses'],board_hint='opaque',compilation_phase_timeouts_s=[9.]*8)
    events=[]
    with compiler.observe_compilation_phases(events.append):
        _,nine=compiler.compile(source,proposal['poses'],board_hint='opaque',compilation_phase_timeouts_s=[9.]*9)
    assert [e['phase']for e in events if e['event']=='start']==list(NINE)
    normalized=copy.deepcopy(nine)
    normalized['explicit_native_macro_options']['compilation_phase_timeouts_s']=[9.]*8
    assert normalized==eight and before==source.read_bytes()
    assert not nine['routing_admitted']and not nine['saved_candidate_authorized']


def test_independent_saved_receiver_replays_all_nine_twice(tmp_path,monkeypatch):
    from test_complete_macro_cell import saved_pair
    source,child,_=saved_pair(tmp_path,monkeypatch);before=[p.read_bytes()for p in(source,child)]
    result=receiver.receive(source,child,board_hint='opaque',timeout_s=9.5,
        compilation_phase_timeouts_s=[9.]*9)
    assert result['ok']and result['complete'],result['errors']
    phases=result['bounded_composition']['constituents']
    for prefix in('source_compilation:','ground_source_compilation:'):
        assert all(phases.count(prefix+name)==1 for name in NINE)
    assert before==[p.read_bytes()for p in(source,child)]
    assert all(not result[k]for k in('routing_admitted','fab_ready','release_authority','current_qualified'))


def test_scopes_are_closed_before_advance_and_fresh_on_contact_entry(tmp_path,monkeypatch):
    from test_programming_resistor_placement import fixture
    board,owner,part,root,tree,poses=fixture(tmp_path,monkeypatch)
    observed=[];original=escape._source_observations
    thermal_before=os.environ.get('CEC_THERMAL_BOARD_HINT')
    @contextmanager
    def observe(*a,**kw):
        with original(*a,**kw):
            current=(pinmap._observations.get(),canonical._export_observations.get(),stage._observations.get())
            assert all(v is not None for v in current)
            observed.append(current)
            if len(observed)==2:raise RuntimeError('contact_scope_entered')
            yield
    monkeypatch.setattr(escape,'_source_observations',observe)
    def advance():
        assert pinmap._observations.get()is None
        assert canonical._export_observations.get()is None
        assert stage._observations.get()is None
        assert os.environ.get('CEC_THERMAL_BOARD_HINT')==thermal_before
        return time.monotonic()+9.
    with pytest.raises(RuntimeError,match='contact_scope_entered'):
        escape._prepare_split_source(board,poses,board_hint=str(root),deadline=time.monotonic()+9.,
            advance=advance,allow_linear_power_stage_reconstruction=True)
    assert len(observed)==2 and all(a is not b for a,b in zip(*observed))
    assert pinmap._observations.get()is None and canonical._export_observations.get()is None
    assert stage._observations.get()is None
    assert os.environ.get('CEC_THERMAL_BOARD_HINT')==thermal_before


@pytest.mark.parametrize('fault',['metadata','pin_metadata','poses','options','source','canonical','roles'])
def test_advance_callback_cannot_change_source_or_role_inputs(tmp_path,monkeypatch,fault):
    from test_complete_cell_connections import native_source
    source,board,_,proposal=native_source(tmp_path,monkeypatch)
    poses=proposal['poses'];options=dict(reference_group_uuids=[])
    owner=board.FindFootprintByReference(next(iter(poses)))
    def advance():
        if fault=='metadata':owner.SetField('Manufacturer','changed')
        elif fault=='pin_metadata':next(iter(owner.Pads())).SetPinType('passive')
        elif fault=='poses':poses[owner.GetReference()][0]+=.1
        elif fault=='options':options['reference_group_uuids'].append('changed')
        elif fault=='source':source.write_bytes(source.read_bytes()+b'\n; changed Source\n')
        elif fault=='canonical':
            # The fixture deliberately has no canonical root; appearance of
            # a newly declared root changes the exact observation too.
            root=source.with_suffix('.kicad_sch');root.write_text('(kicad_sch (version 20250114))')
            monkeypatch.setattr(canonical.source_nc,'_root',lambda *a:root)
        else:
            # A callback can introspect a Python generator but cannot mutate
            # the retained role frame and call that a fresh Source derivation.
            import inspect
            frame=inspect.currentframe().f_back
            frame.f_locals['role_frame']['control_shunts']['forged']={'current_authority':True}
        return time.monotonic()+9.
    with pytest.raises((ValueError,FileNotFoundError)):
        escape._prepare_split_source(board,poses,board_hint='opaque',deadline=time.monotonic()+9.,
            advance=advance,**options)


def test_fake_unstarted_done_and_reused_continuation_refused(tmp_path,monkeypatch):
    from test_complete_cell_connections import native_source
    def forged():yield {};return {'caller':'forged'}
    fake=forged();next(fake)
    with pytest.raises(ValueError,match='fresh_private_Source_role'):escape._finish_source_contacts(fake)
    source,board,_,proposal=native_source(tmp_path,monkeypatch)
    steps=escape._prepare_source_steps(board,proposal['poses'],board_hint='opaque')
    with pytest.raises(ValueError,match='fresh_private_Source_role'):escape._finish_source_contacts(steps)
    next(steps);assert escape._finish_source_contacts(steps)['poses']==proposal['poses']
    with pytest.raises(ValueError,match='fresh_private_Source_role'):escape._finish_source_contacts(steps)


@pytest.mark.parametrize('kind',['bool','expired','too_long','nan','inf'])
def test_advance_cannot_supply_unbounded_or_expired_contact_deadline(tmp_path,monkeypatch,kind):
    from test_complete_cell_connections import native_source
    source,board,_,proposal=native_source(tmp_path,monkeypatch)
    def advance():
        return dict(bool=True,expired=time.monotonic()-1,too_long=time.monotonic()+11,
            nan=float('nan'),inf=float('inf'))[kind]
    with pytest.raises(ValueError,match='bounded_source_role_handoff_deadline'):
        escape._prepare_split_source(board,proposal['poses'],board_hint='opaque',
            deadline=time.monotonic()+9.,advance=advance)
