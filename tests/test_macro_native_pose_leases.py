"""Explicit native checks retain every physical test and one default lease."""
import copy
from pathlib import Path
import pcbnew,pytest
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as receiver
from test_macro_compilation_leases import Clock


@pytest.mark.parametrize('value',[[],[1],[1,1],[1]*4,[True,1,1],[0,1,1],[-1,1,1],
    [float('nan'),1,1],[float('inf'),1,1],[10.1,1,1],[1.01,1,1]])
def test_explicit_pose_has_exactly_three_finite_constituents_no_larger_than_outer(value):
    with pytest.raises(ValueError):compiler._pose_phase_budgets(value,1.)


def test_default_pose_deadline_is_never_reset_but_explicit_stages_are_separate(monkeypatch):
    clock=Clock();monkeypatch.setattr(compiler.time,'monotonic',clock)
    legacy=compiler._NativePoseLeases(1.)
    original_deadline=legacy.deadline
    clock.spend(.7);legacy.advance(compiler.NATIVE_POSE_PHASES[1],lambda:True)
    assert legacy.deadline==original_deadline
    clock.now=original_deadline
    with pytest.raises(ValueError,match='deadline'):legacy.advance(compiler.NATIVE_POSE_PHASES[2],lambda:True)
    events=[];checks=[]
    with compiler.observe_native_pose_phases(events.append):
        fresh=compiler._NativePoseLeases(1.,[1.]*3)
        for name in compiler.NATIVE_POSE_PHASES[1:]:
            clock.spend(.8);fresh.advance(name,lambda:checks.append(True)or True)
        clock.spend(.8);fresh.finish(lambda:checks.append(True)or True)
    assert len(checks)==3 and fresh.finished
    assert [(q['event'],q['phase'])for q in events]==[q for name in compiler.NATIVE_POSE_PHASES
        for q in [('start',name),('finish',name)]]


@pytest.mark.parametrize('index',range(3))
@pytest.mark.parametrize('fault',['expired','changed','validation_overrun','observer_overrun'])
def test_each_phase_seals_before_advance_and_no_prefix_can_pass(monkeypatch,index,fault):
    clock=Clock();monkeypatch.setattr(compiler.time,'monotonic',clock)
    def observe(event):
        if fault=='observer_overrun'and event['event']=='finish'and event['index']==index:clock.spend(1.)
    with compiler.observe_native_pose_phases(observe):
        lease=compiler._NativePoseLeases(1.,[1.]*3)
        for name in compiler.NATIVE_POSE_PHASES[1:index+1]:lease.advance(name,lambda:True)
        if fault=='expired':clock.now=lease.deadline
        def check():
            if fault=='validation_overrun':clock.spend(1.)
            return fault!='changed'
        with pytest.raises(ValueError,match='deadline|inputs_changed'):
            if index==2:lease.finish(check)
            else:lease.advance(compiler.NATIVE_POSE_PHASES[index+1],check)
        assert not lease.finished and lease.index==index


def test_pose_stages_cannot_skip_repeat_finish_early_or_be_reused():
    lease=compiler._NativePoseLeases(1.,[1.]*3)
    with pytest.raises(ValueError,match='ordered'):lease.advance(compiler.NATIVE_POSE_PHASES[2],lambda:True)
    with pytest.raises(ValueError,match='all_native'):lease.finish(lambda:True)
    lease.advance(compiler.NATIVE_POSE_PHASES[1],lambda:True)
    with pytest.raises(ValueError,match='ordered'):lease.advance(compiler.NATIVE_POSE_PHASES[1],lambda:True)
    lease.advance(compiler.NATIVE_POSE_PHASES[2],lambda:True);lease.finish(lambda:True)
    with pytest.raises(ValueError,match='deadline'):lease.finish(lambda:True)


@pytest.mark.parametrize('quarter,back',[(0,False),(1,False),(2,True),(3,True)])
def test_actual_native_split_and_legacy_results_match_except_explicit_schedule(tmp_path,monkeypatch,quarter,back):
    from test_complete_macro_cell import fixture
    source,parent,posed,packet=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    before=source.read_bytes();native=[compiler._native_pose_binding(b)for b in(parent,posed)]
    legacy=compiler.native_pose_screen(parent,posed,packet,timeout_s=9.)
    events=[]
    with compiler.observe_native_pose_phases(events.append):
        split=compiler.native_pose_screen(parent,posed,packet,timeout_s=9.,phase_timeouts_s=[9.]*3)
    composition=split.pop('bounded_composition')
    assert split==legacy and split['ok'],split
    assert composition['constituents']==list(compiler.NATIVE_POSE_PHASES)
    assert [q['phase']for q in events if q['event']=='start']==list(compiler.NATIVE_POSE_PHASES)
    assert before==source.read_bytes()and native==[compiler._native_pose_binding(b)for b in(parent,posed)]
    assert not any(split[k]for k in('routing_admitted','fab_ready','release_authority'))


@pytest.mark.parametrize('fault',['pad_shape','pad_offset','metadata','via_inner_width','lock','group',
    'Source_file','family','packet','evidence','code','priority_side_effect'])
@pytest.mark.parametrize('when',['start_middle','finish_last'])
def test_actual_native_mutation_between_seams_is_not_hidden_by_partial_xy_binding(tmp_path,monkeypatch,fault,when):
    from test_complete_macro_cell import fixture
    source,parent,posed,packet=fixture(tmp_path,monkeypatch)
    evidence=tmp_path/'manufacturer.txt';evidence.write_bytes(b'actual bound input')
    packet['diagnostic_binding_test']=dict(evidence_files_sha256={str(evidence):compiler.force._hash(evidence)})
    fired=[]
    def mutate():
        fired.append(True);fp=next(iter(posed.GetFootprints()));p=next(iter(fp.Pads()))
        if fault=='pad_shape':p.SetShape(pcbnew.PAD_SHAPE_OVAL)
        elif fault=='pad_offset':p.SetOffset(pcbnew.VECTOR2I(1,0))
        elif fault=='metadata':fp.SetValue(fp.GetValue()+' mutated')
        elif fault=='via_inner_width':
            via=next(t for t in posed.GetTracks()if t.GetClass()=='PCB_VIA')
            via.Padstack().SetMode(pcbnew.PADSTACK.MODE_CUSTOM)
            via.SetWidth(pcbnew.In1_Cu,via.GetWidth(pcbnew.In1_Cu)+1)
        elif fault=='lock':fp.SetLocked(not fp.IsLocked())
        elif fault=='group':next(iter(posed.Groups())).SetName('mutated owner')
        elif fault=='Source_file':source.write_bytes(source.read_bytes()+b'\n; changed\n')
        elif fault=='family':source.with_suffix('.kicad_dru').write_text('(version 1)')
        elif fault=='packet':packet['routing_admitted']=True
        elif fault=='evidence':evidence.write_bytes(b'changed')
        elif fault=='code':monkeypatch.setattr(compiler.force,'_code_identity',lambda:{'changed':'code'})
    def observe(event):
        selected=(event['event']=='start'and event['index']==1 if when=='start_middle'
            else event['event']=='finish'and event['index']==2)
        if selected and fault!='priority_side_effect':mutate()
    if fault=='priority_side_effect':
        import cec_macro_priority_preflight as priority
        original=priority.inspect
        def changed(*args,**kwargs):
            result=original(*args,**kwargs);next(iter(args[1].GetFootprints())).SetValue('changed private frame')
            fired.append(True);return result
        monkeypatch.setattr(priority,'inspect',changed)
    with compiler.observe_native_pose_phases(observe):
        with pytest.raises((ValueError,KeyError),match='changed|transport|identity|snapshot'):
            compiler.native_pose_screen(parent,posed,packet,timeout_s=9.,phase_timeouts_s=[9.]*3)
    assert fired


def test_saved_receiver_exposes_every_native_stage_and_never_borrows_from_old_outer_lease(tmp_path,monkeypatch):
    from test_complete_macro_cell import saved_pair
    source,child,_=saved_pair(tmp_path,monkeypatch);before=[p.read_bytes()for p in(source,child)]
    result=receiver.receive(source,child,board_hint='opaque',timeout_s=9.5,
        compilation_phase_timeouts_s=[9.]*8,native_pose_phase_timeouts_s=[9.]*3)
    assert result['ok']and result['complete'],result['errors']
    phases=result['bounded_composition']['constituents']
    required=['independent_native_prefill_and_refill',
        *['independent_native_pose:'+name for name in compiler.NATIVE_POSE_PHASES],'independent_native_terminals']
    i=phases.index(required[0]);assert phases[i:i+len(required)]==required
    assert set(phases)==set(result['stage_timings_s'])
    assert before==[p.read_bytes()for p in(source,child)]


def test_saved_receiver_cannot_increase_constituents_beyond_outer_limit():
    with pytest.raises(ValueError,match='within_existing_limit'):
        receiver.receive('not-needed','not-needed',board_hint='opaque',timeout_s=1.,native_pose_phase_timeouts_s=[1.,1.01,1.])
