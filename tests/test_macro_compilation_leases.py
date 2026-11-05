"""Ordered compilation leases are bounded work, never prefix admission."""
import pytest
import cec_cell_macro_requests as op


class Clock:
    def __init__(self):self.now=100.
    def __call__(self):return self.now
    def spend(self,n):self.now+=n


@pytest.fixture
def clock(monkeypatch):
    value=Clock();monkeypatch.setattr(op.time,'monotonic',value);return value


@pytest.mark.parametrize('value',[[],[1],[1,2],[1,2,3,4,5],[0,1,1],[-1,1,1],
    [11,1,1],[True,1,1],[float('nan'),1,1],[1,float('inf'),1],None,'123'])
def test_explicit_three_or_four_positive_finite_real_budgets_only(value):
    with pytest.raises(ValueError):op._phase_budgets(value)
    with pytest.raises(ValueError):op.packet_options({'explicit_native_macro_options':{
        'compilation_phase_timeouts_s':value}})


@pytest.mark.parametrize('timeout',[0,-1,11,True,float('nan')])
def test_default_timeout_stays_bounded(clock,timeout):
    with pytest.raises(ValueError):op._CompilationLeases(timeout,None)


def test_all_three_independent_budgets_and_fresh_boundary_checks(clock):
    checks=[];events=[]
    def check():checks.append(clock.now);return True
    with op.observe_compilation_phases(events.append):
        leases=op._CompilationLeases(1,[2,3,4])
        assert leases.deadline==102
        clock.spend(1.9);assert leases.advance(op.COMPILATION_PHASES[1],check)==104.9
        clock.spend(2.9);assert leases.advance(op.COMPILATION_PHASES[2],check)==pytest.approx(108.8)
        clock.spend(3.9);leases.finish(check)
    assert leases.finished and len(checks)==3
    assert [(e['event'],e['index'])for e in events]==[
        ('start',0),('finish',0),('start',1),('finish',1),('start',2),('finish',2)]
    assert all(e['explicit_ordered_composition']for e in events)


@pytest.mark.parametrize('phase',[0,1])
def test_expired_phase_cannot_advance_or_borrow(clock,phase):
    leases=op._CompilationLeases(10,[1,10,10]);checks=[]
    if phase:leases.advance(op.COMPILATION_PHASES[1],lambda:True)
    clock.now=leases.deadline
    with pytest.raises(ValueError,match='deadline'):
        leases.advance(op.COMPILATION_PHASES[phase+1],lambda:checks.append(1)or True)
    assert leases.index==phase and not leases.finished and checks==[]


def test_expired_second_cannot_finish_prefix(clock):
    leases=op._CompilationLeases(10,[1,1,1]);leases.advance(op.COMPILATION_PHASES[1],lambda:True)
    clock.spend(1)
    with pytest.raises(ValueError):leases.finish(lambda:True)
    assert not leases.finished


@pytest.mark.parametrize('action',['skip','repeat','early_finish','fourth'])
def test_no_phase_order_skip(clock,action):
    leases=op._CompilationLeases(10,[1,1,1])
    if action=='skip':call=lambda:leases.advance(op.COMPILATION_PHASES[2],lambda:True)
    elif action=='repeat':call=lambda:leases.advance(op.COMPILATION_PHASES[0],lambda:True)
    elif action=='early_finish':call=lambda:leases.finish(lambda:True)
    else:
        leases.advance(op.COMPILATION_PHASES[1],lambda:True)
        leases.advance(op.COMPILATION_PHASES[2],lambda:True)
        call=lambda:leases.advance('fourth',lambda:True)
    with pytest.raises(ValueError):call()
    assert not leases.finished


def test_default_is_one_original_deadline_not_three_resets(clock):
    events=[]
    with op.observe_compilation_phases(events.append):
        leases=op._CompilationLeases(10,None);clock.spend(4)
        assert leases.advance(op.COMPILATION_PHASES[1],lambda:True)==110
        clock.spend(4);assert leases.advance(op.COMPILATION_PHASES[2],lambda:True)==110
        clock.spend(2)
        with pytest.raises(ValueError,match='deadline'):leases.finish(lambda:True)
    assert not leases.finished and all(not e['explicit_ordered_composition'] for e in events)


@pytest.mark.parametrize('boundary',[0,1,2])
def test_live_input_refusal_at_every_boundary(clock,boundary):
    leases=op._CompilationLeases(10,[1,1,1])
    for n in range(boundary):leases.advance(op.COMPILATION_PHASES[n+1],lambda:True)
    with pytest.raises(ValueError,match='source_or_code_changed'):
        if boundary==2:leases.finish(lambda:False)
        else:leases.advance(op.COMPILATION_PHASES[boundary+1],lambda:False)
    assert leases.index==boundary and not leases.finished


@pytest.mark.parametrize('where',['check','observer'])
def test_final_validation_and_diagnostic_time_counts(clock,where):
    def observer(event):
        # Returned forged values have no scheduling authority.
        if where=='observer' and event['event']=='finish' and event['index']==2:
            event['deadline_monotonic']=1e99;clock.spend(1)
        return {'deadline_monotonic':1e99}
    with op.observe_compilation_phases(observer):
        leases=op._CompilationLeases(10,[1,1,1])
        leases.advance(op.COMPILATION_PHASES[1],lambda:True)
        leases.advance(op.COMPILATION_PHASES[2],lambda:True)
        def check():
            if where=='check':clock.spend(1)
            return True
        with pytest.raises(ValueError,match='deadline'):leases.finish(check)
    assert not leases.finished


def test_observer_is_context_local_and_not_packet_input(clock):
    first=[];second=[]
    with op.observe_compilation_phases(first.append):
        op._CompilationLeases(1,None)
        with op.observe_compilation_phases(second.append):op._CompilationLeases(1,None)
        op._CompilationLeases(1,None)
    op._CompilationLeases(1,None)
    assert len(first)==2 and len(second)==1
    with pytest.raises(ValueError):op.observe_compilation_phases(None).__enter__()
    options=op.packet_options({'explicit_native_macro_options':{'compilation_phase_timeouts_s':[1,2,3]}})
    assert options=={'compilation_phase_timeouts_s':[1,2,3]}
    with pytest.raises(ValueError):op.packet_options({'explicit_native_macro_options':{'observer':first}})


def test_native_compile_explicit_phase_inputs_replay_unchanged(tmp_path,monkeypatch):
    from test_complete_cell_connections import native_source
    import cec_force_current as force
    path,parent,private,proposal=native_source(tmp_path,monkeypatch)
    before=force._hash(path);events=[]
    with op.observe_compilation_phases(events.append):
        draft,packet=op.compile(path,proposal['poses'],board_hint='opaque',
            compilation_phase_timeouts_s=[10,10,10])
    options=op.packet_options(packet)
    assert options['compilation_phase_timeouts_s']==[10,10,10]
    _,replayed=op.compile(path,proposal['poses'],board_hint='opaque',**options)
    assert packet==replayed and force._hash(path)==before
    assert [(e['event'],e['index'])for e in events]==[
        ('start',0),('finish',0),('start',1),('finish',1),('start',2),('finish',2)]
    assert not packet['routing_admitted'] and not packet['saved_candidate_authorized']
