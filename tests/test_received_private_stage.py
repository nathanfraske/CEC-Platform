"""Supervisor publication is distinct from producer/self-reported success."""
import hashlib
import json
from pathlib import Path
import pytest
import cec_received_private_stage as stage


def receipt():
    return dict(candidate='private-child',candidate_sha256='a'*64,gates={name:True for name in
        ('operator','invariants','field','ground_returns','source_intake','candidate_intake',
         'parity','native','craft','source_live')})


@pytest.mark.parametrize('name',list(receipt()['gates']))
def test_any_actual_gate_refusal_cannot_publish_selected_family(tmp_path,name):
    r=receipt();r['gates'][name]=False;target=tmp_path/'publication.json'
    result=stage.publish(r,target,live=lambda:True)
    assert not result['ok'] and result['selected']is None and not target.exists()


@pytest.mark.parametrize('value',[1,'true',None,{},False])
def test_truthy_or_unknown_gate_is_not_positive_receiving(tmp_path,value):
    r=receipt();r['gates']['field']=value
    assert not stage.publish(r,tmp_path/'publication.json',live=lambda:True)['ok']


def test_missing_gate_or_source_epoch_never_creates_publication(tmp_path):
    r=receipt();del r['gates']['native']
    assert not stage.publish(r,tmp_path/'publication.json',live=lambda:True)['ok']
    assert not stage.publish(receipt(),tmp_path/'publication.json',live=lambda:False)['ok']
    assert not list(tmp_path.iterdir())


def test_late_epoch_failure_rolls_back_only_exact_own_receipt(tmp_path):
    states=iter([True,False]);target=tmp_path/'publication.json'
    with pytest.raises(ValueError,match='late_source_epoch'):
        stage.publish(receipt(),target,live=lambda:next(states))
    assert not target.exists()


def test_publication_collision_keeps_preexisting_bytes(tmp_path):
    target=tmp_path/'publication.json';target.write_bytes(b'user-owned')
    with pytest.raises(ValueError,match='fresh_publication'):
        stage.publish(receipt(),target,live=lambda:True)
    assert target.read_bytes()==b'user-owned'


def test_success_grants_only_private_prefix_never_whole_net_or_current(tmp_path):
    target=tmp_path/'publication.json'
    result=stage.publish(receipt(),target,live=lambda:True)
    assert result['prefix_accepted'] and result['completed_nets']==[]
    assert not result['current_qualified'] and not result['release_authority']


def _native_warning(uid='new-spur',kind='track_dangling',x=12.):
    return dict(type=kind,severity='warning',description='native diagnostic',
        items=[dict(uuid=uid,pos=dict(x=x,y=10.),description='Track /CONTROL')])


def test_a_completed_join_does_not_pay_for_a_new_warning_only_attached_spur():
    old=dict(violations=[_native_warning('old-label','silk_overlap')],unconnected_items=[{},{}])
    new=dict(violations=[_native_warning()],unconnected_items=[])
    proof=stage.native_findings_delta(old,new)
    assert not proof['ok'] and len(proof['introduced_native_findings'])==1
    assert not proof['inherited_findings_qualified']


def test_native_warning_geometry_and_duplicate_multiplicity_are_not_hidden_by_uuid_or_type():
    a=_native_warning();before=dict(violations=[a])
    assert not stage.native_findings_delta(before,dict(violations=[_native_warning(x=13.)]))['ok']
    assert not stage.native_findings_delta(before,dict(violations=[a,a]))['ok']
    assert stage.native_findings_delta(before,dict(violations=[a]))['ok']
    assert stage.native_findings_delta(before,dict(violations=[]))['ok']


@pytest.mark.parametrize('severity',['ignored','info',None,False])
def test_unknown_native_severity_is_not_admission(severity):
    row=_native_warning();row['severity']=severity
    with pytest.raises(ValueError,match='known_native_finding_severity'):
        stage.native_findings_delta(dict(violations=[]),dict(violations=[row]))


def test_source_hash_refused_before_any_worker_or_namespace(tmp_path):
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();source.write_bytes(b'exact literal source')
    out=tmp_path/'out'
    with pytest.raises(ValueError,match='expected_source_epoch'):
        stage.run(source,out,board_hint='synthetic',expected_source_sha256='0'*64)
    assert not out.exists() and source.read_bytes()==b'exact literal source'


def test_worker_refuses_queued_source_epoch_before_proposal(tmp_path,monkeypatch):
    monkeypatch.setattr(stage,'identity',lambda *args:{'epoch':'now'})
    request=dict(source=str(tmp_path/'source'),directory=str(tmp_path),board_hint='synthetic',
        assembly_instance=None,identity={'epoch':'old'})
    with pytest.raises(ValueError,match='queued_source_epoch'):
        stage.worker(request)
    assert not (tmp_path/'UNADMITTED-family').exists()


@pytest.mark.parametrize('net',[None,'',False,3])
@pytest.mark.parametrize('operator',['quiet_signal','quiet_native_portals'])
def test_quiet_stage_requires_explicit_named_source_request_before_namespace(tmp_path,net,operator):
    with pytest.raises(ValueError,match='explicit_bounded_received_operator_required'):
        stage.run(tmp_path/'missing',tmp_path/'out',board_hint='synthetic',
            expected_source_sha256='0'*64,operator=operator,net=net)
    assert not(tmp_path/'out').exists()


@pytest.mark.parametrize('compiled',[False,True])
@pytest.mark.parametrize('operator',['quiet_signal','quiet_native_portals'])
def test_quiet_worker_dispatch_stops_at_finite_planner_or_constructor_refusal(tmp_path,monkeypatch,compiled,operator):
    # Test dispatch only. Refusal fixtures never fake any receiving/admission.
    import pcbnew
    import cec_quiet_signal_completion as quiet
    from test_lastmile import _board
    source=tmp_path/'source.kicad_pcb'
    pcbnew.SaveBoard(str(source),_board([],edge=(0,0,20,20)))
    monkeypatch.setattr(stage,'identity',lambda *a:{'exact':'epoch'})
    seen=[]
    def plan(*a,**kw):
        seen.append(('plan',kw));return {'complete':compiled}
    def construct(*a,**kw):
        seen.append(('construct',kw));return {'complete':False}
    monkeypatch.setattr(quiet,'plan',plan);monkeypatch.setattr(quiet,'construct_private',construct)
    monkeypatch.setattr(quiet,'receive',lambda *a,**k:pytest.fail('no saved candidate to receive'))
    result=stage.worker(dict(source=str(source),directory=str(tmp_path),board_hint='synthetic',
        assembly_instance=None,identity={'exact':'epoch'},operator=operator,net='/typed'))
    assert result['gates']=={}and result['reason']=='finite_proposal_incomplete'
    assert [x[0]for x in seen]==(['plan','construct']if compiled else['plan'])
    assert result['attempts'][0]['module']=='cec_quiet_signal_completion'
    if compiled:
        assert seen[-1][1].get('strategy')==('native_portals'if operator=='quiet_native_portals'else None)
    assert not(tmp_path/'publication.json').exists()


@pytest.mark.parametrize('pad',[None,'',False,3])
def test_measurement_stage_requires_explicit_actual_input_before_namespace(tmp_path,pad):
    with pytest.raises(ValueError,match='explicit_bounded_received_operator_required'):
        stage.run(tmp_path/'missing',tmp_path/'out',board_hint='synthetic',
            expected_source_sha256='0'*64,operator='measurement_input',pad_uuid=pad)
    assert not(tmp_path/'out').exists()


@pytest.mark.parametrize('operator,net,pad',[('ground',None,True),
    ('quiet_signal','/N','invented'),('ordinary_columns','+3V3','invented'),
    ('measurement_input','/guessed_net','actual-pad')])
def test_measurement_identity_cannot_expand_other_operators_or_target_whole_net(tmp_path,operator,net,pad):
    with pytest.raises(ValueError,match='explicit_bounded_received_operator_required'):
        stage.run(tmp_path/'missing',tmp_path/'out',board_hint='synthetic',
            expected_source_sha256='0'*64,operator=operator,net=net,pad_uuid=pad)
    assert not(tmp_path/'out').exists()


@pytest.mark.parametrize('compiled',[False,True])
def test_measurement_worker_refusal_never_reaches_receiving_or_publication(tmp_path,monkeypatch,compiled):
    import pcbnew
    import cec_isolated_measurement_completion as op
    from test_lastmile import _board
    source=tmp_path/'source.kicad_pcb'
    pcbnew.SaveBoard(str(source),_board([],edge=(0,0,20,20)))
    monkeypatch.setattr(stage,'identity',lambda *a:{'exact':'epoch'})
    seen=[]
    def plan(*args,**kwargs):
        seen.append(('plan',kwargs));return {'complete':compiled,'pad_uuid':'real-input'}
    def construct(*args,**kwargs):
        seen.append(('construct',kwargs));return {'complete':False}
    monkeypatch.setattr(op,'plan',plan);monkeypatch.setattr(op,'construct_private',construct)
    monkeypatch.setattr(op,'receive',lambda *a,**k:pytest.fail('no complete saved candidate'))
    result=stage.worker(dict(source=str(source),directory=str(tmp_path),board_hint='synthetic',
        assembly_instance=None,identity={'exact':'epoch'},operator='measurement_input',pad_uuid='real-input'))
    assert result['gates']=={} and result['reason']=='finite_proposal_incomplete'
    assert [x[0]for x in seen]==(['plan','construct']if compiled else['plan'])
    assert seen[0][1]['pad_uuid']=='real-input'
    if compiled:assert seen[1][1]['timeout_s']==20.
    assert result['attempts'][0]['module']=='cec_isolated_measurement_completion'
    assert not(tmp_path/'publication.json').exists()


def test_assembly_child_changes_only_matched_member(tmp_path):
    p=tmp_path/'child';p.write_bytes(b'child')
    original={'schema':1,'role':'carrier','contract':{'path':'contract','sha256':'a'*64},
        'members':{'carrier':{'path':'old','sha256':'b'*64},'cover':{'path':'peer','sha256':'c'*64}}}
    child=stage.matched_instance(original,p)
    assert original['members']['carrier']['path']=='old'
    assert child['members']['carrier']==dict(path=str(p.resolve()),sha256=hashlib.sha256(b'child').hexdigest())
    assert child['members']['cover']==original['members']['cover'] and child['contract']==original['contract']


def test_negative_epoch_cache_prevents_worker_repeat_and_policy_change_rebinds(tmp_path,monkeypatch):
    """Supervisor-only fixture: no native gate is mocked into admission."""
    import io
    import cec_native_drc_runner as native
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();source.write_bytes(b'original')
    epoch={'policy':1};launched=[]
    monkeypatch.setattr(stage,'identity',lambda *args:dict(epoch))
    monkeypatch.setattr(native,'_describe_build',lambda *args:{'verified-test-tool':1})
    class RefusedWorker:
        def __init__(self,args,**kwargs):
            launched.append(args);request=json.loads(Path(args[-1]).read_text())
            stage.write(Path(request['directory'])/'receiving.json',{'gates':{},'reason':'test_unknown'})
            self.stdout=io.BytesIO(b'bounded refusal');self.stderr=io.BytesIO();self.returncode=0
        def wait(self,timeout=None):return 0
    monkeypatch.setattr(stage.subprocess,'Popen',RefusedWorker)
    kwargs=dict(board_hint='synthetic',expected_source_sha256=hashlib.sha256(b'original').hexdigest())
    first=stage.run(source,tmp_path/'out',**kwargs)
    assert not first['ok'] and not first.get('selected')
    second=stage.run(source,tmp_path/'out',**kwargs)
    assert second['cached_attempt']and len(launched)==1
    epoch['policy']=2
    third=stage.run(source,tmp_path/'out',**kwargs)
    assert not third['ok']and len(launched)==2
    assert not list((tmp_path/'out').rglob('publication.json'))


def test_column_geometry_receiver_loads_actual_saved_boards_without_nested_current_lease(tmp_path,monkeypatch):
    import pcbnew
    import cec_ordinary_power_columns as columns
    from test_lastmile import _board
    source=tmp_path/'source.kicad_pcb';candidate=tmp_path/'child.kicad_pcb'
    pcbnew.SaveBoard(str(source),_board([],edge=(0,0,20,20)))
    pcbnew.SaveBoard(str(candidate),_board([],edge=(0,0,20,20)))
    seen=[]
    def scoped(parent,child,**kw):
        assert parent.GetClass()=='BOARD'and child.GetClass()=='BOARD'
        seen.append(kw);return {'ok':True,'complete':True}
    monkeypatch.setattr(columns,'receive_native',scoped)
    monkeypatch.setattr(columns,'receive',lambda *a,**kw:pytest.fail('nested ten-second full receiver forbidden'))
    proof=stage.column_scope_receive(source,candidate,board_hint='synthetic',net='/REAL_SCOPE')
    assert proof['ok']and seen==[dict(source=source,board_hint='synthetic',net='/REAL_SCOPE',timeout_s=10.)]
    # A geometry-only PASS cannot replace the independently current-bound
    # source replay. This is still a publication refusal.
    receipt_value=receipt();receipt_value['gates']['invariants']=False
    assert not stage.publish(receipt_value,tmp_path/'publication.json',live=lambda:True)['ok']


@pytest.mark.parametrize('fault',['missing_build','different_build','incomplete','producer_changed'])
def test_native_tool_proof_uses_actual_runner_schema_not_report_label(fault):
    expected={'cli':'private-cli','artifacts':{'engine':'a'*64}}
    proof=dict(ok=True,complete=True,source_and_producer_unchanged=True,reporting_build=expected)
    if fault=='missing_build':proof.pop('reporting_build')
    elif fault=='different_build':proof['reporting_build']={'engine':'unverified'}
    elif fault=='incomplete':proof['complete']=False
    else:proof['source_and_producer_unchanged']=False
    with pytest.raises(ValueError,match='native_tool_epoch'):
        stage.require_native_tool(proof,expected)


def test_actual_native_runner_descriptor_shape_is_accepted():
    expected={'root':'private-build','artifacts':{'engine':'a'*64}}
    stage.require_native_tool(dict(ok=True,complete=True,source_and_producer_unchanged=True,
                                  reporting_build=expected),expected)


@pytest.mark.parametrize('candidate_ok',[True,False])
def test_real_intake_pair_reuses_source_audits_but_not_native_board_intake(tmp_path,monkeypatch,candidate_ok):
    from unittest.mock import Mock
    import cec_full_pipeline as pipeline,cec_synth_pipeline as synth
    import cec_constraints,cec_generalization_gate,cec_beta_electrical_audit
    from cec_suite_source_audit_cache import SuiteSourceAuditCache
    cfg=synth.Config.load('hub-standard-rev2');candidate=tmp_path/'candidate.kicad_pcb'
    candidate.write_bytes(Path(cfg.pcb).read_bytes())
    monkeypatch.setattr(SuiteSourceAuditCache,'_signature',lambda self,mode:'exact-fixture-epoch')
    live=Mock(side_effect=[{'ok':True},{'ok':candidate_ok}]);general=Mock(return_value={'ok':True})
    electrical=Mock(return_value={'findings':[]})
    monkeypatch.setattr(cec_constraints,'intake_gate',live)
    monkeypatch.setattr(cec_generalization_gate,'audit',general)
    monkeypatch.setattr(cec_beta_electrical_audit,'audit',electrical)
    monkeypatch.setattr(pipeline,'_project_rule_authority_delta',lambda *args:{'ok':True})
    reports,session=stage.receive_intakes(cfg,Path(cfg.pcb),candidate,tmp_path)
    assert reports['source_intake']['ok']is True
    assert reports['candidate_intake']['ok']is candidate_ok
    assert live.call_count==2 and general.call_count==electrical.call_count==1
    assert session.hits==session.misses==2
    assert reports['suite_source_audit_cache']['native_pcb_intake_or_route_receiving_cached']is False
    r=receipt();r['gates']['candidate_intake']=reports['candidate_intake']['ok']
    if not candidate_ok:assert not stage.publish(r,tmp_path/'publication.json',live=lambda:True)['ok']


@pytest.mark.parametrize('authority',['canonical','code','policy'])
def test_actual_cache_invalidates_authority_mutation_between_live_intakes(tmp_path,monkeypatch,authority):
    import cec_full_pipeline as pipeline,cec_synth_pipeline as synth
    import cec_constraints,cec_generalization_gate,cec_beta_electrical_audit
    from cec_suite_source_audit_cache import SuiteSourceAuditCache
    cfg=synth.Config.load('hub-standard-rev2');candidate=tmp_path/'candidate.kicad_pcb'
    candidate.write_bytes(Path(cfg.pcb).read_bytes())
    files={name:tmp_path/(name+'.authority')for name in ('canonical','code','policy')}
    for path in files.values():path.write_text('old')
    monkeypatch.setattr(SuiteSourceAuditCache,'_signature',lambda self,mode:stage.digest(
        [(name,path.read_text())for name,path in files.items()]))
    calls=[]
    def live(*args,**kwargs):
        calls.append(args)
        if len(calls)==2:files[authority].write_text('changed')
        return {'ok':True}
    monkeypatch.setattr(cec_constraints,'intake_gate',live)
    monkeypatch.setattr(cec_generalization_gate,'audit',lambda *args:{'ok':True})
    monkeypatch.setattr(cec_beta_electrical_audit,'audit',lambda *args:{'findings':[]})
    monkeypatch.setattr(pipeline,'_project_rule_authority_delta',lambda *args:{'ok':True})
    with pytest.raises(ValueError,match='epoch changed'):
        stage.receive_intakes(cfg,Path(cfg.pcb),candidate,tmp_path)
    assert len(calls)==2 and not (tmp_path/'publication.json').exists()


def test_parent_and_worker_identity_use_same_explicit_hint_and_restore_caller(tmp_path,monkeypatch):
    import os
    from types import SimpleNamespace
    import cec_force_current as force,cec_source_retaining_ses_import as retaining
    import cec_full_pipeline as pipeline,cec_synth_pipeline as synth
    from cec_suite_source_audit_cache import SuiteSourceAuditCache
    source=tmp_path/'source';source.write_text('(kicad_pcb)')
    (tmp_path/'fp-lib-table').write_text('(fp_lib_table (version 7))')
    monkeypatch.setattr(force,'_family',lambda *args:{'source':'exact'})
    monkeypatch.setattr(force,'_code_identity',lambda:{'code':'exact'})
    monkeypatch.setattr(retaining,'assembly_identity',lambda *args:None)
    monkeypatch.setattr(synth.Config,'load',lambda *args:SimpleNamespace(params={},dir=str(tmp_path)))
    monkeypatch.setattr(pipeline,'_source_files',lambda *args:[source])
    monkeypatch.setattr(SuiteSourceAuditCache,'_signature',lambda self,mode:os.environ.get('CEC_THERMAL_BOARD_HINT'))
    monkeypatch.setenv('CEC_THERMAL_BOARD_HINT','different-caller-context')
    parent=stage.identity(source,'explicit-board',None)
    assert os.environ['CEC_THERMAL_BOARD_HINT']=='different-caller-context'
    monkeypatch.setenv('CEC_THERMAL_BOARD_HINT','explicit-board')
    worker=stage.identity(source,'explicit-board',None)
    assert parent==worker and parent['suite_source_code_policy_epoch']=='explicit-board'
