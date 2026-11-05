"""Neutral selection, finite policy and fail-closed prefix admission."""
from copy import deepcopy
import os

import pytest
import cec_preflight_native_recovery as recovery


def refusal():
    return dict(gate=False, criticality=dict(nets=['partition/feed'],
        unroutable_connections=[dict(index=3, net='partition/feed')]))


def good_terms():
    return dict.fromkeys(('zones_refilled', 'source_unchanged',
        'source_authority_unchanged',
        'parent_copper_preserved', 'placement_unchanged', 'explicit_nets_complete',
        'current_widths_qualified', 'new_geometry_conforms',
        'previous_pairs_preserved', 'structural_admission',
        'connectivity_improved', 'only_requested_nets_added'), True)


def test_exact_refusal_selection_no_warning_or_leaf_name_guess():
    report=refusal(); original=deepcopy(report)
    report['criticality']['unroutable_connections'].append(dict(net='other/feed'))
    report['warnings']={'ordinary_unroutable_connections': 99}
    assert recovery.targets(report)==('partition/feed',)
    assert report['criticality']['nets']==original['criticality']['nets']


@pytest.mark.parametrize('mutation', ['gate', 'error', 'missing', 'oversized'])
def test_selection_fail_closed(mutation):
    report=refusal()
    if mutation=='gate':report['gate']=True
    if mutation=='error':report['error']='stale'
    if mutation=='missing':report['criticality']['nets']=[]
    if mutation=='oversized':
        report['criticality']['nets']=['n'+str(i) for i in range(5)]
        report['criticality']['unroutable_connections']=[dict(net=n) for n in report['criticality']['nets']]
    assert recovery.targets(report)==()


@pytest.mark.parametrize('key', list(good_terms()))
@pytest.mark.parametrize('replacement', [False, None, 'true', 1])
def test_every_independent_gate_mandatory(key, replacement):
    terms=good_terms();terms[key]=replacement
    assert not recovery.admitted(terms)
    del terms[key]
    assert not recovery.admitted(terms)
    assert recovery.admitted(good_terms())


@pytest.mark.parametrize('value', [-1, 0, float('nan'), float('inf'), True, 301])
def test_invalid_time_policy_refused_before_native_io(tmp_path,value):
    with pytest.raises(ValueError,match='finite'):
        recovery.construct(tmp_path/'no-input', tmp_path/'out', ['arbitrary'], wall_s=value)
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('value', [-1, 0, float('nan'), float('inf'), True, 101])
def test_invalid_span_policy_refused_before_native_io(tmp_path,value):
    with pytest.raises(ValueError,match='finite'):
        recovery.construct(tmp_path/'no-input',tmp_path/'out',['arbitrary'],max_span_mm=value)


@pytest.mark.parametrize('value', [0, 33, True, 2.5])
def test_invalid_attempt_policy_refused_before_native_io(tmp_path,value):
    with pytest.raises(ValueError,match='finite'):
        recovery.construct(tmp_path/'no-input',tmp_path/'out',['arbitrary'],attempts_per_pair=value)


@pytest.mark.parametrize('gate,expected', [
    ((True,'pass'),True), ((None,'not_run'),False), ((False,'error'),False),
    ((False,'legacy',[dict(uuids=['old'])]),True),
    ((False,'new',[dict(uuids=['new'])]),False),
    ((False,'unidentified',[dict(count=1)]),False),
    ((False,'malformed',['failure']),False),
])
def test_inherited_debt_is_not_permission_for_new_geometry(gate,expected):
    assert recovery.geometry_scope_ok(gate,{'new'}) is expected


def test_current_identity_is_exact_and_restored(monkeypatch):
    monkeypatch.delenv('CEC_THERMAL_BOARD_HINT',raising=False)
    with recovery._current_identity('family-x'):
        assert os.environ['CEC_THERMAL_BOARD_HINT']=='family-x'
        with pytest.raises(ValueError,match='conflicting'):
            with recovery._current_identity('family-y'):pass
        assert os.environ['CEC_THERMAL_BOARD_HINT']=='family-x'
    assert 'CEC_THERMAL_BOARD_HINT' not in os.environ
    monkeypatch.setenv('CEC_THERMAL_BOARD_HINT','family-x')
    with pytest.raises(RuntimeError):
        with recovery._current_identity('family-x'):raise RuntimeError('stop')
    assert os.environ['CEC_THERMAL_BOARD_HINT']=='family-x'


@pytest.mark.parametrize('after_gate',[True,False])
@pytest.mark.parametrize('proactive',[True,False])
@pytest.mark.parametrize('authority_suffix',[
    '.kicad_pro','.priority-replacements.json','.power-prefix.json','.route-lineage.json'])
def test_pipeline_reruns_whole_preflight_never_flips_gate(
        tmp_path,monkeypatch,after_gate,proactive,authority_suffix):
    import contextlib
    import json
    from pathlib import Path
    from types import SimpleNamespace
    import cec_full_pipeline as pipeline
    import cec_route_preflight as preflight
    import cec_operation_budget as operation
    import cec_synth_pipeline as synth
    source=tmp_path/'parent.kicad_pcb';source.write_text('controller fixture, not native CAD')
    cfg=SimpleNamespace(board='unrelated-family',params={})
    monkeypatch.setattr(pipeline,'_route_params_for_board',lambda *_:{})
    monkeypatch.setattr(pipeline,'_code_closure_signature',lambda *_:'test-code')
    monkeypatch.setattr(synth,'_oracle_env',lambda *_:contextlib.nullcontext())
    analyzed=[];workers=[]
    def analyze(path,**_kwargs):
        analyzed.append(path)
        return refusal() if Path(path)==source else dict(gate=after_gate)
    monkeypatch.setattr(preflight,'analyze_multiresolution',analyze)
    monkeypatch.setattr(preflight,'compact_placement_evidence',lambda r:dict(gate=r['gate']))
    def worker(command,*_args,**_kwargs):
        workers.append(command)
        out=Path(command[command.index('--out')+1]);out.mkdir()
        child=out/'board.kicad_pcb';child.write_text('saved native proposal controller fixture')
        proof=dict(ok=True,terms=good_terms(),source_sha256=pipeline.sha256_file(source),
            nets=['partition/feed'],
            source_unchanged=True,board=str(child),proposal_sha256=pipeline.sha256_file(child),
            policy=dict(wall_s=90.,max_span_mm=50.,attempts_per_pair=8),
            artifact_signature=pipeline._files_signature([source,child]))
        (out/'report.json').write_text(json.dumps(proof))
    monkeypatch.setattr(operation,'run',worker)
    options=dict(grid_mm=1,iterations=4,backend='cpu',
                 constructive_nets=('partition/feed',) if proactive else ())
    stage=pipeline._preflight_stage(source,tmp_path/'preflight',cfg,**options)
    assert stage['admission_gate'] is after_gate
    child=Path(stage['board'])
    assert child!=source and analyzed==([str(child)] if proactive else [str(source),str(child)])
    assert source.read_text()=='controller fixture, not native CAD'
    assert str(child) in stage['_artifacts'] and len(workers)==1
    # Same immutable request reuses exact proof, never repeats the worker.
    repeated=pipeline._preflight_stage(source,tmp_path/'preflight',cfg,**options)
    assert repeated['board']==str(child) and len(workers)==1
    # Changed child bytes invalidate the cached proof, not the input parent.
    child.write_text('tampered')
    refused=pipeline._preflight_stage(source,tmp_path/'preflight',cfg,**options)
    assert refused['board']==str(source) and not refused['admission_gate'] and len(workers)==1
    # A meaningful rule-authority change is a new bounded request, even when
    # PCB bytes stay identical. It must not get stuck behind a stale cache.
    source.with_suffix(authority_suffix).write_text('{"new_authority":"fixture"}')
    renewed=pipeline._preflight_stage(source,tmp_path/'preflight',cfg,**options)
    assert renewed['board']!=str(source) and len(workers)==2


def test_already_passed_preflight_does_not_construct(tmp_path,monkeypatch):
    import contextlib
    from types import SimpleNamespace
    import cec_full_pipeline as pipeline
    import cec_route_preflight as preflight
    import cec_synth_pipeline as synth
    import cec_operation_budget as operation
    source=tmp_path/'board.kicad_pcb';source.write_text('no mutation')
    monkeypatch.setattr(pipeline,'_route_params_for_board',lambda *_:{})
    monkeypatch.setattr(synth,'_oracle_env',lambda *_:contextlib.nullcontext())
    monkeypatch.setattr(preflight,'analyze_multiresolution',lambda *_args,**_kw:dict(gate=True))
    monkeypatch.setattr(preflight,'compact_placement_evidence',lambda r:r)
    def unexpected(*_args,**_kwargs):raise AssertionError('unnecessary worker')
    monkeypatch.setattr(operation,'run',unexpected)
    result=pipeline._preflight_stage(source,tmp_path/'out',SimpleNamespace(board='other',params={}),
                                    grid_mm=1,iterations=4,backend='cpu')
    assert result['admission_gate'] and result['board']==str(source)


def compact_refusal():
    return dict(gate=False,critical_unroutable_connections=[dict(net='partition/feed')],
        critical_route_refused_count=0,critical_declaration_error_count=0,
        critical_pin_access_blocked_count=0,fanout_blocked_count=0)


@pytest.mark.parametrize('blocker',[
    None,'critical_route_refused_count','critical_declaration_error_count',
    'critical_pin_access_blocked_count','fanout_blocked_count'])
def test_placement_recovery_only_before_raster_driven_eco(blocker):
    report=compact_refusal()
    assert recovery.targets(report)==('partition/feed',)
    if blocker:report[blocker]=1
    assert recovery.placement_eligible(report) is (blocker is None)
    if blocker:
        del report[blocker]
        assert not recovery.placement_eligible(report)


@pytest.mark.parametrize('failure',[None,'priority','authority','pose','copper','exception'])
def test_early_commit_is_complete_transaction_or_rollback(tmp_path,monkeypatch,failure):
    import json
    from pathlib import Path
    from types import SimpleNamespace
    import cec_full_pipeline as pipeline
    import cec_fr as fr
    import pcbnew
    source=tmp_path/'board.kicad_pcb';source.write_text('original placement controller fixture')
    cfg=SimpleNamespace(params={},pins={'fixed':['immutable']})
    monkeypatch.setattr(pipeline,'_code_closure_signature',lambda *_:'test-code')
    monkeypatch.setattr(fr,'copy_project_sidecars',lambda *_:[])
    def preflight(parent,out,*_args,**kwargs):
        assert kwargs['constructive_nets']==('partition/feed',)
        out=Path(out);out.mkdir(parents=True)
        child=out/'board.kicad_pcb';child.write_text('admitted native prefix controller fixture')
        receipt=out/'preflight.json'
        receipt.write_text(json.dumps(dict(native_recovery=dict(ok=True,terms=good_terms()))))
        return dict(admission_gate=True,board=str(child),report=str(receipt),_artifacts=[str(child),str(receipt)])
    monkeypatch.setattr(pipeline,'_preflight_stage',preflight)
    monkeypatch.setattr(pipeline,'_copy_sidecars',lambda a,b,**_:Path(b).write_bytes(Path(a).read_bytes()))
    def authority(*_args,**_kwargs):
        cfg.params['temporary']='mutation'
        if failure=='exception':raise RuntimeError('native commit interrupted')
        return dict(ok=failure!='authority')
    monkeypatch.setattr(pipeline,'_ensure_placement_route_authority',authority)
    monkeypatch.setattr(pipeline,'_measure_placement_priority_routes',lambda *_a,**_k:{})
    monkeypatch.setattr(pipeline,'_placement_priority_route_gate',lambda *_:dict(ok=failure!='priority'))
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda *_:SimpleNamespace(GetTracks=lambda:[]))
    monkeypatch.setattr(fr,'copper_geometry_prefix_contract',lambda *_:{})
    monkeypatch.setattr(fr,'check_copper_geometry_prefix',lambda *_:dict(ok=failure!='copper'))
    def poses(path):
        return 'moved' if failure=='pose' and Path(path)==source else 'fixed'
    monkeypatch.setattr(pipeline,'_placement_position_signature',poses)
    result=pipeline._placement_native_route_escape(cfg,source,compact_refusal())
    assert result['changed'] is (failure is None)
    if failure:
        assert source.read_text()=='original placement controller fixture'
        assert cfg.params=={} and cfg.pins=={'fixed':['immutable']}
    else:
        assert source.read_text()=='admitted native prefix controller fixture'
        assert result['placement_unchanged']
