"""A scalar finisher is a bounded proposal, never a worker-owned admission."""
import json
import os
from pathlib import Path
from unittest import mock

import pytest
import cec_route_scalar_finish as finish
import cec_force_current as force
import cec_sensitive_scalar_path_reflow as owner
import cec_operation_budget as budget


@pytest.mark.parametrize('result',[None,[],42,{},dict(drc=True,unconnected=0,routed='x'),
    dict(drc=0,unconnected=False,routed='x'),dict(drc=0,unconnected=1,routed='x'),
    dict(drc=1,unconnected=0,routed='x'),dict(drc=0.,unconnected=0,routed='x'),
    dict(drc=0,unconnected=0,routed='')])
def test_only_a_literal_closed_selected_route_is_eligible(result):
    assert not finish.eligible(result)


@pytest.mark.parametrize('path',['board.kicad_pcb',Path('board.kicad_pcb')])
def test_closed_route_is_eligible_without_waiving_any_release_gate(path):
    assert finish.eligible(dict(drc=0,unconnected=0,routed=path,gate=False))


@pytest.mark.parametrize('bad',[False,0,'',[],{}])
def test_bad_explicit_native_build_is_not_silently_replaced(bad):
    with pytest.raises(ValueError):finish.reporting_build(bad)


def test_native_build_lookup_is_read_only_and_explicit_configuration_wins(tmp_path,monkeypatch):
    monkeypatch.setenv('XDG_CACHE_HOME',str(tmp_path/'cache'))
    monkeypatch.delenv('CEC_NATIVE_DRC_REPORTING_BUILD',raising=False)
    assert finish.reporting_build() is None
    cached=tmp_path/'cache'/'cec'/'native-drc-10.0.5';cached.mkdir(parents=True)
    assert finish.reporting_build()==cached.resolve()
    configured=tmp_path/'explicit';monkeypatch.setenv('CEC_NATIVE_DRC_REPORTING_BUILD',str(configured))
    assert finish.reporting_build()==configured.resolve()
    monkeypatch.setenv('CEC_NATIVE_DRC_REPORTING_BUILD','')
    with pytest.raises(ValueError):finish.reporting_build()


def setup_worker(tmp_path,monkeypatch,*,fault=None,parent_fault=None):
    source=tmp_path/'selected'/'board.kicad_pcb';source.parent.mkdir();source.write_text('immutable selected copper')
    source.with_suffix('.kicad_dru').write_text('(version 1)\n')
    monkeypatch.setattr(force,'_code_identity',lambda:{'synthetic-runtime':'fixed'})
    monkeypatch.setattr(finish,'reporting_build',lambda requested:tmp_path/'verified-build')
    calls=[]
    def receive(staged,child,**params):
        calls.append(('receive',params))
        proof=dict(ok=True,complete=True,source_sha256=force._hash(staged),candidate_sha256=force._hash(child),
            shortened_centerline_mm=2.,native_strokes_before_after=[6,2])
        if parent_fault=='refused':proof['ok']=False
        elif parent_fault=='incomplete':proof['complete']=False
        elif parent_fault=='truthy':proof['ok']='yes'
        elif parent_fault=='source_hash':proof['source_sha256']='0'*64
        elif parent_fault=='child_hash':proof['candidate_sha256']='0'*64
        elif parent_fault=='child_race':child.write_text('concurrent unreceived child')
        elif parent_fault=='staged_race':staged.write_text('concurrent changed source clone')
        elif parent_fault=='code_race':monkeypatch.setattr(force,'_code_identity',lambda:{'synthetic-runtime':'changed'})
        return proof
    monkeypatch.setattr(owner,'receive',receive)
    def run(command,directory,**kwargs):
        calls.append(('worker',command,kwargs))
        assert kwargs['operation']=='source_scalar_path_finish' and kwargs['timeout']==120.
        assert '--allow-locked-source' not in command
        assert command[command.index('--maximum-candidates')+1]=='1'
        stage_dir=Path(command[command.index('--out')+1]);stage_dir.mkdir()
        staged=Path(command[command.index('--source')+1]);child=stage_dir/'child'/'board.kicad_pcb';child.parent.mkdir()
        child.write_text('independently received shorter copper')
        payload=dict(ok=True,complete=True,changed=True,errors=[],code_identity=force._code_identity(),
            source=str(staged),source_sha256=force._hash(staged),candidate=str(child),candidate_sha256=force._hash(child),
            source_family_and_code_unchanged=True,records=[dict(plan=dict(
                retired_track_uuids=['synthetic-one','synthetic-two'],points_nm=[[0,0],[1000000,1000000]],allow_locked_source=False))])
        if fault=='failure':raise RuntimeError('supervised worker failed')
        if fault=='no_report':return dict(status='complete')
        if fault=='no_gain':payload['changed']=False
        elif fault=='partial':payload['complete']=False
        elif fault=='truthy':payload['complete']='yes'
        elif fault=='changed_integer':payload['changed']=1
        elif fault=='errors':payload['errors']=['native refusal']
        elif fault=='epoch':payload['code_identity']={}
        elif fault=='source_hash':payload['source_sha256']='0'*64
        elif fault=='source_path':payload['source']=str(source)
        elif fault=='child_hash':payload['candidate_sha256']='0'*64
        elif fault=='outside':payload['candidate']=str(source)
        elif fault=='symlink':
            alias=stage_dir/'alias.kicad_pcb';alias.symlink_to(child);payload['candidate']=str(alias)
        elif fault=='records':payload['records']=[]
        elif fault=='record_type':payload['records']=[[]]
        elif fault=='lock':payload['records'][0]['plan']['allow_locked_source']=True
        elif fault=='scope':payload['records'][0]['plan']['force_any_net']=True
        elif fault=='staged':staged.write_text('changed private source')
        elif fault=='staged_sidecar':staged.with_suffix('.kicad_dru').write_text('changed rules')
        elif fault=='payload_type':payload=[]
        elif fault=='malformed':
            (stage_dir/'stage.json').write_text('{');return dict(status='complete')
        (stage_dir/'stage.json').write_text(json.dumps(payload))
        return dict(status='complete')
    monkeypatch.setattr(budget,'run',run)
    return source,calls


@pytest.mark.parametrize('fault',['failure','no_report','no_gain','partial','truthy','changed_integer','errors','epoch',
    'source_hash','source_path','child_hash','outside','symlink','records','record_type','lock','scope',
    'staged','staged_sidecar','payload_type','malformed'])
def test_worker_flags_or_tampered_private_source_cannot_replace_selected_board(tmp_path,monkeypatch,fault):
    source,calls=setup_worker(tmp_path,monkeypatch,fault=fault);raw=source.read_bytes();rules=source.with_suffix('.kicad_dru').read_bytes()
    q=finish.apply(dict(drc=0,unconnected=0,routed=str(source)),tmp_path/'work',board_hint='synthetic')
    assert not q['changed'] and not q['release_authority'],q
    assert source.read_bytes()==raw and source.with_suffix('.kicad_dru').read_bytes()==rules
    assert not any(c[0]=='receive' for c in calls)


@pytest.mark.parametrize('fault',['refused','incomplete','truthy','source_hash','child_hash','child_race','staged_race','code_race'])
def test_parent_independent_receiving_is_bound_and_checked_again_before_copy(tmp_path,monkeypatch,fault):
    source,calls=setup_worker(tmp_path,monkeypatch,parent_fault=fault);raw=source.read_bytes()
    q=finish.apply(dict(drc=0,unconnected=0,routed=source),tmp_path/'work',board_hint='synthetic')
    assert not q['changed'] and q.get('error'),q
    assert source.read_bytes()==raw and [c[0] for c in calls]==['worker','receive']


def test_received_proposal_copies_only_board_and_still_requires_coordinator_admission(tmp_path,monkeypatch):
    source,calls=setup_worker(tmp_path,monkeypatch);rules=source.with_suffix('.kicad_dru').read_bytes()
    q=finish.apply(dict(drc=0,unconnected=0,routed=source),tmp_path/'work',board_hint='synthetic')
    assert q['changed'] and q['shortened_centerline_mm']==2. and q['native_strokes_before_after']==[6,2],q
    assert q['requires_independent_admission'] and not q['source_locked_cut_authorized'] and not q['release_authority']
    assert source.read_text()=='independently received shorter copper' and source.with_suffix('.kicad_dru').read_bytes()==rules
    assert [c[0] for c in calls]==['worker','receive']


@pytest.mark.parametrize('options',[dict(board_hint=''),dict(timeout_s=True),dict(timeout_s=0),
    dict(timeout_s=181),dict(timeout_s=float('inf')),dict(timeout_s=float('nan'))])
def test_context_is_validated_before_private_work_or_worker_launch(tmp_path,monkeypatch,options):
    source,calls=setup_worker(tmp_path,monkeypatch);params=dict(board_hint='synthetic');params.update(options)
    with pytest.raises(ValueError):finish.apply(dict(drc=0,unconnected=0,routed=source),tmp_path/'work',**params)
    assert not calls and not (tmp_path/'work').exists()


@pytest.mark.parametrize('mode',['disabled','reserve','open','improved','worse','grade_error','pair_gate_loss','worker_error'])
def test_normal_route_coordinator_invokes_once_and_independently_adopts_or_restores(tmp_path,monkeypatch,mode):
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    import cec_fab_repair
    import cec_dimension_repair
    import cec_route_checkpoint
    from test_route_incumbent_selection import fixture,grade
    from route_candidate_test_support import run_candidate_in_process
    source,cfg=fixture(tmp_path);raw=source.read_bytes()
    if mode=='disabled':cfg.params['route_scalar_path_finish']=False
    calls=[]
    def oracle(path,**kwargs):
        if kwargs.get('route') is not False:return dict(gate=False,routed=None,error='no fresh route')
        finished='finish-comparison' in str(path)
        if finished and mode=='grade_error':raise RuntimeError('independent grade failed')
        q=grade(path,opens=1 if mode=='open' else 0,length=35 if finished and mode=='worse' else 25 if finished else 30)
        if finished and mode=='pair_gate_loss':q['gate_terms']['pairs_ok']=False
        return q
    def proposal(result,directory,**kwargs):
        calls.append((result,directory,kwargs))
        if mode=='worker_error':raise RuntimeError('private optional failure')
        p=Path(result['routed']);p.write_bytes(p.read_bytes()+b'\n')
        return dict(changed=True,release_authority=False)
    monkeypatch.setenv('CEC_DIMENSION_REPAIR','0');monkeypatch.setenv('CEC_FAB_REPAIR','0')
    monkeypatch.setattr(synth,'route_oracle_grade',oracle)
    monkeypatch.setattr(pipeline,'_route_candidate_cohorts',lambda *a,results,**k:results.append(dict(gate=False,routed=None,error='no fresh route')))
    monkeypatch.setattr(cec_route_checkpoint,'preservation',lambda *a,**k:dict(ok=True))
    monkeypatch.setattr(budget,'run',run_candidate_in_process)
    monkeypatch.setattr(budget,'optional_work_admission',lambda *a,**k:dict(start=mode!='reserve'))
    monkeypatch.setattr(finish,'apply',proposal)
    result=pipeline._route_stage(source,tmp_path/'work',cfg,passes=1,opt=1,seed=22,timeout=1,thermal='lazy')
    assert source.read_bytes()==raw and not result['gate']
    invoked=mode not in ('disabled','reserve','open');assert bool(calls)==invoked
    admitted=mode=='improved'
    assert bool(result['source_scalar_finish'].get('coordinator_admitted'))==admitted
    if admitted:
        assert result['winner_origin']=='incumbent_polish' and Path(result['board']).read_bytes()==raw+b'\n'
    else:assert Path(result['board']).read_bytes()==raw and result['winner_origin']=='incumbent'
    if mode in ('worse','grade_error','pair_gate_loss'):assert result['incumbent_finish_admission']['admitted'] is False


def test_real_native_private_wrapper_discovers_and_receives_an_unlocked_source_path(tmp_path):
    import pcbnew
    import cec_field_coupling as field
    from test_sensitive_scalar_path_reflow import fixture
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('native DRC reporting build not configured')
    board,source,cut,*_=fixture(tmp_path)
    for track in cut:track.SetLocked(False)
    field._save_field_snapshot(board,source)
    raw=source.read_bytes();sidecars=force._sidecars(source)
    q=finish.apply(dict(drc=0,unconnected=0,routed=source),tmp_path/'automatic-finish',
        board_hint='synthetic',native_reporting_build=Path(build))
    assert q['changed'] and q['independent_source_path_receiving']['ok'],q
    assert q['shortened_centerline_mm']>1 and q['native_strokes_before_after']==[6,1]
    assert source.read_bytes()!=raw and force._sidecars(source)==sidecars
    assert q['requires_independent_admission'] and not q['release_authority']
