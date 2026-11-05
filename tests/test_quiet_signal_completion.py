"""Fresh typed requests and actual saved native joins, never caller UUID authority."""
import time
import pcbnew
import pytest
import cec_quiet_signal_completion as op
import cec_additive_pair_repair as additions
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
from cec_native_items import discard_items
from test_quiet_signal_requests import fixture
from test_field_proposals import track


def saved_fixture(tmp_path,monkeypatch,*,quarter=0,back=False):
    board,source,root,tree,spec,output,target=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    hint=str(root);net='/renamed_quiet'
    # Fixture geometry is intentionally simple. Routing success is not mocked:
    # native connectivity and all actual source/package proof remain real.
    proposal=op.plan(board,source,board_hint=hint,net=net)
    assert proposal['complete'],proposal
    child=force._copy_family(source,tmp_path/'child')
    b=pcbnew.LoadBoard(str(child));old={force._uid(t)for t in b.GetTracks()}
    pads=op._pads(b,proposal['request'])
    common=set(pads[0].GetLayerSet().CuStack())&set(pads[1].GetLayerSet().CuStack())
    assert len(common)==1
    track(b,net,tuple(v/1e6 for v in pads[0].GetPosition()),
        tuple(v/1e6 for v in pads[1].GetPosition()),width=.2,layer=next(iter(common)))
    additions.save_native_additions(child,b,{},old,board_hint=hint)
    return source,child,hint,proposal


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_saved_quiet_native_join_receives_without_reclassifying_or_ratings(tmp_path,monkeypatch,quarter,back):
    source,child,hint,proposal=saved_fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    before=[p.read_bytes()for p in (source,child)]
    proof=op.receive(source,child,board_hint=hint,net=proposal['net'])
    assert proof['ok']and proof['complete'],proof['errors']
    assert proof['source_components']==2 and proof['candidate_components']==1
    assert proof['source_class_preserved']and proof['whole_shared_stage_still_required']
    assert len(proof['mandatory_shared_receiving'])==9
    assert not any(proof[k]for k in ('routing_admitted','current_qualified','adc_mode_qualified',
        'load_qualified','release_authority'))
    assert [p.read_bytes()for p in (source,child)]==before


@pytest.mark.parametrize('fault',['wrong_width','wrong_net','orphan','missing_join','source_pin',
    'pose','source_remove','foreign_net','class','stale_source'])
def test_incoming_or_source_quiet_scope_faults_are_refused(tmp_path,monkeypatch,fault):
    source,child,hint,proposal=saved_fixture(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(child));tracks=list(b.GetTracks())
    if fault=='wrong_width':tracks[0].SetWidth(250000)
    elif fault=='wrong_net':tracks[0].SetNet(b.FindNet('+3V3'))
    elif fault=='orphan':track(b,proposal['net'],(30,30),(31,30),width=.2)
    elif fault=='missing_join':discard_items(b,tracks)
    elif fault=='source_pin':
        p=op._pads(b,proposal['request'])[1];p.SetNumber('24')
    elif fault=='pose':op._pads(b,proposal['request'])[1].Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='source_remove':
        # Removing any old native UUID is forbidden even if unrelated.
        footprint=op._pads(b,proposal['request'])[0].GetParentFootprint()
        b.Remove(footprint)
    elif fault=='foreign_net':track(b,'+3V3',(30,30),(31,30),width=.2)
    elif fault=='class':
        monkeypatch.setattr(fr,'_project_netclass_resolver',lambda *a,**k:lambda n:{'name':'Default'})
    elif fault=='stale_source':
        source.write_bytes(source.read_bytes()+b'\n')
    if fault not in ('class','stale_source'):
        try:field._save_field_snapshot(b,child)
        except field._ProposalUnknown:
            # A deliberately wrong-net primitive can be refused by the
            # writer's independent identity boundary before it reaches this
            # receiver. It must never be normalized into accepted evidence.
            assert fault=='wrong_net'
            return
    proof=op.receive(source,child,board_hint=hint,net=proposal['net'])
    if fault=='stale_source':
        # Whitespace is not altered electrical authority; fresh derivation
        # rebinds the actual source, rather than trusting a cached request.
        assert proof['ok'],proof
        assert proof['independently_compiled_source_scope']['request']['source_bindings']['source_sha256']==force._hash(source)
    else:assert not proof['ok']and not proof['complete']and proof['errors'],proof


@pytest.mark.parametrize('net',[None,'',False,7])
def test_plan_requires_explicit_named_signal(tmp_path,monkeypatch,net):
    board,source,root,*_=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='explicit_quiet_signal_net'):
        op.plan(board,source,board_hint=str(root),net=net)


def test_wrong_literal_net_cannot_be_normalized_into_quiet_scope_on_native_reload(tmp_path,monkeypatch):
    source,child,hint,proposal=saved_fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(child))
    original={force._uid(t)for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    incoming=[t for t in board.GetTracks()if force._uid(t)not in original]
    assert incoming
    for item in incoming:item.SetNet(board.FindNet('+3V3'))
    # Deliberately author a bad raw saved file: the normal identity-safe
    # snapshot helper correctly refuses this mutation before receiving.
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child),board)
    proof=op.receive(source,child,board_hint=hint,net=proposal['net'])
    assert not proof['ok'] and not proof['complete']
    assert any('literal_saved_quiet_net_differs' in error for error in proof['errors'])


@pytest.mark.parametrize('seconds',[True,0,-1,11,float('nan'),float('inf')])
def test_receiver_rejects_invalid_or_extended_lease(seconds):
    with pytest.raises(ValueError,match='bounded_quiet_signal_work_lease'):
        op.receive('missing','missing',board_hint='synthetic',net='/N',timeout_s=seconds)


def test_constructor_recompiles_scope_and_does_not_accept_a_forged_request(tmp_path,monkeypatch):
    board,source,root,*_=fixture(tmp_path,monkeypatch)
    candidate=force._copy_family(source,tmp_path/'child')
    proposal=dict(net='/not-source-owned',request={'root_pad_uuid':'invented'})
    with pytest.raises(ValueError,match='fresh_source_quiet_request_refused'):
        op.construct_private(source,candidate,proposal,board_hint=str(root))


def test_scope_compile_and_child_share_one_construction_lease(tmp_path,monkeypatch):
    import cec_certificate_repair as repair
    board,source,root,*_=fixture(tmp_path,monkeypatch)
    candidate=force._copy_family(source,tmp_path/'child')
    real_plan=op.plan;clock=[100.];seen=[]
    monkeypatch.setattr(op.time,'monotonic',lambda:clock[0])
    def compile_scope(*args,**kwargs):
        assert 0<kwargs['timeout_s']<=8.
        result=real_plan(*args,**kwargs);clock[0]+=2.;return result
    monkeypatch.setattr(op,'plan',compile_scope)
    def bounded_refusal(func,args,**kwargs):
        seen.append((args,kwargs,repair._WORKER_DEADLINE.get()))
        return {'closed':False}
    monkeypatch.setattr(repair,'_spawn_apply',bounded_refusal)
    before=repair._WORKER_DEADLINE.get()
    result=op.construct_private(source,candidate,dict(net='/renamed_quiet'),board_hint=str(root),timeout_s=8.)
    assert not result['complete']and not result['routing_admitted']
    assert seen[0][0][2]==3. and seen[0][1]==dict(timeout_s=6.,search_budget_arg=2)
    assert seen[0][2]==108. and repair._WORKER_DEADLINE.get()==before


def test_compilation_cannot_reset_exhausted_construction_lease(tmp_path,monkeypatch):
    import cec_certificate_repair as repair
    board,source,root,*_=fixture(tmp_path,monkeypatch)
    candidate=force._copy_family(source,tmp_path/'child')
    real_plan=op.plan;clock=[100.]
    monkeypatch.setattr(op.time,'monotonic',lambda:clock[0])
    def compile_scope(*args,**kwargs):
        result=real_plan(*args,**kwargs);clock[0]+=7.5;return result
    monkeypatch.setattr(op,'plan',compile_scope)
    monkeypatch.setattr(repair,'_spawn_apply',lambda *a,**k:pytest.fail('no fresh child lease'))
    result=op.construct_private(source,candidate,dict(net='/renamed_quiet'),board_hint=str(root),timeout_s=8.)
    assert not result['complete']and result['reason']=='quiet_construction_lease_exhausted_before_search'


def test_standard_scope_search_and_saving_share_finite_twenty_second_constructor(tmp_path,monkeypatch):
    import cec_certificate_repair as repair
    board,source,root,*_=fixture(tmp_path,monkeypatch)
    candidate=force._copy_family(source,tmp_path/'child');real_plan=op.plan;clock=[100.];seen=[]
    monkeypatch.setattr(op.time,'monotonic',lambda:clock[0])
    def compile_scope(*args,**kwargs):
        assert kwargs['timeout_s']<=10.
        result=real_plan(*args,**kwargs);clock[0]+=2.;return result
    monkeypatch.setattr(op,'plan',compile_scope)
    def bounded_refusal(func,args,**kwargs):
        seen.append((args,kwargs,repair._WORKER_DEADLINE.get()));return {'closed':False}
    monkeypatch.setattr(repair,'_spawn_apply',bounded_refusal)
    result=op.construct_private(source,candidate,dict(net='/renamed_quiet'),board_hint=str(root))
    assert not result['complete']and result['whole_construction_lease_s']==20.
    assert seen[0][0][2]==10. and seen[0][1]==dict(timeout_s=18.,search_budget_arg=2)
    assert seen[0][2]==120.


@pytest.mark.parametrize('seconds',[True,0,-1,21,float('nan'),float('inf')])
def test_constructor_never_accepts_unbounded_or_unknown_work(seconds):
    with pytest.raises(ValueError,match='bounded_quiet_signal_work_lease'):
        op.construct_private('missing','missing',dict(net='/N'),board_hint='synthetic',timeout_s=seconds)
