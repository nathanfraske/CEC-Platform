"""Read-only explicit-plan receiving experiment, not a production selector."""
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import cec_swig_guard
cec_swig_guard.pin()
import wx
quiet = wx.LogNull()
import pcbnew
import cec_constraints as constraints
import cec_force_current as force
import cec_full_pipeline as pipeline
import cec_native_drc_runner as native
import cec_score as score
import cec_synth_pipeline as synth
from cec_suite_source_audit_cache import SuiteSourceAuditCache


def record_annotation_receiving(out,label,proof,*,same_prior=None):
    """Persist the raw failing boundary BEFORE a verdict can stop the suite.

    This is diagnostic evidence only. No field, deadline, native finding or
    comparison is removed, rewritten or promoted to admission authority.
    """
    if label not in('initial','postnative','postintake'):
        raise ValueError('finite_annotation_diagnostic_boundary_required')
    if same_prior is not None and type(same_prior)is not bool:
        raise ValueError('literal_annotation_comparison_result_required')
    path=Path(out)/('typed-'+label+'-receiving.json')
    assert not path.exists()
    pipeline.atomic_json(path,dict(kind='raw_annotation_boundary_diagnostic',boundary=label,
        receiving=proof,same_prior=same_prior,selection_authority=False,release_authority=False))


def isolated_final_typed(path,key,row,out):
    """Fresh native ownership for the final seal, with exact failure evidence.

    Repeated long-lived SWIG sessions cannot stand in for a fresh saved
    reconstruction. This changes no receiver, comparison or constituent
    lease. The result still must equal the original live typed proof.
    """
    import subprocess
    request=out/'typed-final-input.json';result=out/'typed-final-replay.json'
    assert not request.exists()and not result.exists()
    pipeline.atomic_json(request,dict(path=str(path),board_hint=key,row=row))
    request_sha=force._hash(request);epoch=force._code_identity();family=force._family(path,key)
    worker='''import json,sys
from pathlib import Path
import cec_swig_guard
cec_swig_guard.pin()
import wx
quiet=wx.LogNull()
import cec_force_current as force
import cec_suite_annotation_transition as annotations
request,result=map(Path,sys.argv[1:]);raw=json.loads(request.read_text())
path=Path(raw['path']);key=raw['board_hint'];row=raw['row']
assert path==Path(row['path'])and force._hash(path)==row['sha256']
epoch=force._code_identity();family=force._family(path,key);request_sha=force._hash(request)
proof=annotations.receive_row(path,row,board_hint=key,timeout_s=10.)
assert family==force._family(path,key)and epoch==force._code_identity()and request_sha==force._hash(request)
force._write(result,proof)
raise SystemExit(0 if proof.get('ok')is True and proof.get('complete')is True else 2)
'''
    try:
        job=subprocess.run([sys.executable,'-c',worker,str(request),str(result)],
            text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60.)
    except subprocess.TimeoutExpired as exc:
        pipeline.atomic_json(out/'typed-final-failure.json',dict(complete=False,
            reason='isolated_final_typed_timeout',worker_aggregate_limit_s=60.,
            native_constituent_limit_s=10.,admitted=False,release_authority=False))
        raise ValueError('isolated_final_typed_timeout')from exc
    assert request_sha==force._hash(request)and epoch==force._code_identity()and family==force._family(path,key)
    proof=json.loads(result.read_text())if result.is_file()else None
    if job.returncode!=0 or not isinstance(proof,dict)or proof.get('ok')is not True or proof.get('complete')is not True:
        pipeline.atomic_json(out/'typed-final-failure.json',dict(complete=False,
            reason='isolated_final_typed_refused_or_crashed',exit_code=job.returncode,
            actual_receiving=proof,output_tail=job.stdout[-8000:],admitted=False,release_authority=False))
        raise ValueError('isolated_final_typed_refused_or_crashed:'+str((proof or {}).get('error')))
    return proof


def annotation_epoch_preflight(plan):
    """Cheap rejection only, BEFORE any board's costly native/intake work.

    A serialized family is never authority. Positive results still owe the
    entire fresh typed chain and all saved-board gates. Report concrete
    worker-runtime/path mismatches instead of a late generic stale-plan error.
    """
    report=[];epoch=force._code_identity()
    for row in plan['boards']:
        declaration=row.get('annotation_transition')
        if declaration is None:continue
        assert len(declaration['steps'])==2
        step=declaration['steps'][1]
        if step['kind']!='reference_map':continue
        started=time.monotonic();proposal=Path(step['proposal']['path'])
        assert force._hash(proposal)==step['proposal']['sha256'],'annotation_proposal_input_changed'
        q=json.loads(proposal.read_text());binding=q['binding'];source=Path(binding['source'])
        expected=declaration['steps'][0]['candidate']
        assert str(source.resolve())==str(Path(expected['path']).resolve())
        assert binding['source_sha256']==expected['sha256']==force._hash(source)
        assert binding['code_identity']==epoch,'annotation_source_code_epoch_mismatch'
        saved=binding['source_family'];live=force._family(source,row['board'])
        if saved!=live:
            difference=dict(missing_live=sorted(saved.keys()-live.keys()),
                extra_live=sorted(live.keys()-saved.keys()),
                changed=sorted(k for k in saved.keys()&live.keys()if saved[k]!=live[k]))
            raise ValueError('annotation_source_family_epoch_mismatch:'+row['board']+':'+json.dumps(difference))
        assert time.monotonic()-started<10.,'annotation_epoch_preflight_deadline'
        report.append(dict(board=row['board'],source=str(source),source_sha256=binding['source_sha256'],
            proposal=str(proposal),proposal_sha256=force._hash(proposal),rejection_only=True,
            typed_chain_and_all_native_gates_still_required=True,admitted=False))
    assert epoch==force._code_identity()
    return report


def main():
    root = Path('/home/codex/src/CEC-Platform')
    sys.path.insert(0,str(root/'ops'))
    import cec_suite_annotation_transition as annotations
    import typed_print_runtime as runtime
    import cec_received_private_stage as stage
    plan_path, out = map(Path, sys.argv[1:])
    plan = json.loads(plan_path.read_text())
    early_identity=annotation_epoch_preflight(plan)
    out.mkdir(exist_ok=False)
    code = force._code_identity()
    driver_sha = force._hash(Path(__file__))
    audit_session = SuiteSourceAuditCache(root)
    report = dict(schema=1, kind='fresh-native-parity-and-early-intake',
        plan=str(plan_path.resolve()), plan_sha256=force._hash(plan_path),
        out_of_scope=plan['out_of_scope'], release_authority=False,
        production_selector_changed=False, full_intake_repeated=True,
        annotation_rejection_preflight=early_identity,code_identity=code, boards={})
    keep = []
    typed_states = []
    for row in plan['boards']:
        key = row['board']
        path = Path(row['path'])
        if not path.is_absolute(): path = root/path
        assert force._hash(path) == row['sha256'], key+' input identity changed'
        cfg = synth.Config.load(key)
        family = force._family(path, key)
        source = pipeline._files_signature(pipeline._source_files(cfg, path))
        d = out/key.replace('/', '-')
        d.mkdir()
        typed = None
        if annotations.kind(row) is not None:
            declaration=row[annotations.kind(row)]
            typed=annotations.receive_row(path,row,board_hint=key,timeout_s=10.)
            record_annotation_receiving(d,'initial',typed)
            assert typed['ok']and typed['complete'],typed.get('error')
            deps=annotations.dependencies()
            deps[str(Path(runtime.__file__).resolve())]=force._hash(Path(runtime.__file__))
            native_start=runtime.before_native(path,evidence_dir=d)
            native_args=typed['candidate_native_arguments']
        else:native_args={'board_hint':key}
        producer = native.run(path, d/'native.json',
            reporting_build='/home/codex/.cache/cec/native-drc-10.0.5', timeout_s=10., **native_args)
        assert producer['ok'] and producer['complete'], producer.get('errors')
        if typed is not None:
            quarantine=runtime.quarantine(path,d,producer,native_start)
            live_typed=annotations.receive_row(path,row,board_hint=key,timeout_s=10.)
            same=annotations.same_replay(live_typed,typed)
            record_annotation_receiving(d,'postnative',live_typed,same_prior=same)
            assert live_typed['ok']and live_typed['complete'],live_typed.get('error')
            assert same,'typed_annotation_identity_changed_after_native'
            context=producer['native_library_context']
            assert context['bound']and context['source_and_context_unchanged']
            assert stage.stable(context['authority'])==stage.stable(typed['new_library_context'])
            assert deps=={p:force._hash(Path(p))for p in deps}
        raw = json.loads((d/'native.json').read_text())
        b = pcbnew.LoadBoard(str(path))
        keep.append(b)
        parity = constraints._chk_sch_pcb_sync(b, str(path), {'sch': str(cfg.sch)})
        with force._thermal_hint(key):
            measured = score.score(str(path), drc_json=str(d/'native.json'))
        intake = pipeline._source_intake(cfg, str(path), d/'source-intake.json',
            allow_derived_input=True, assembly_instance=row.get('assembly_instance'),
            suite_audit_cache=audit_session)
        edge = b.GetBoardEdgesBoundingBox()
        errors = [v for v in raw['violations'] if v['severity'] == 'error']
        r = dict(path=str(path), sha256=row['sha256'], producer=producer,
            opens=len(raw['unconnected_items']), native_errors=len(errors),
            native_types=dict(Counter(v['type'] for v in errors)),
            warnings=sum(v['severity'] == 'warning' for v in raw['violations']),
            exclusions=len(raw.get('excluded_violations', [])), scored_drc=measured.drc,
            parity=parity, source_signature=source,
            outline_bbox_including_stroke_mm=[pcbnew.ToMM(edge.GetWidth()), pcbnew.ToMM(edge.GetHeight())],
            source_unchanged=force._hash(path) == row['sha256'],
            source_family_unchanged=family == force._family(path, key),
            source_inputs_unchanged=source == pipeline._files_signature(pipeline._source_files(cfg, path)),
            source_intake_ok=intake['ok'], source_intake_report=str(d/'source-intake.json'),
            intake_reasons=intake['intake'].get('reasons'),
            manifest_errors=intake['manifest_errors'],
            project_rule_authority=intake['project_rule_authority'],
            electrical_blockers=intake['electrical_source_audit']['blocker_count'],
            generalization_ok=intake['generalization_gate'].get('ok'))
        if typed is not None:
            final_typed=annotations.receive_row(path,row,board_hint=key,timeout_s=10.)
            same=annotations.same_replay(final_typed,typed)
            record_annotation_receiving(d,'postintake',final_typed,same_prior=same)
            assert final_typed['ok']and final_typed['complete'],final_typed.get('error')
            assert same,'typed_annotation_identity_changed_after_intake'
            assert deps=={p:force._hash(Path(p))for p in deps}
            r['typed_print_transition']=dict(ok=True,complete=True,declaration=declaration,
                source_identity_sha256=__import__('cec_received_private_stage').digest(typed['source_identity']),
                candidate_identity_sha256=__import__('cec_received_private_stage').digest(typed['candidate_identity']),
                dependencies=deps,runtime_quarantine=quarantine,admitted=False)
            typed_states.append((path,key,row,typed,deps))
        report['boards'][key] = r
        print(json.dumps({**{k: r[k] for k in ('opens', 'native_errors', 'scored_drc',
            'parity', 'source_intake_ok', 'intake_reasons', 'electrical_blockers')},
            'board': key}, default=str), flush=True)
        pipeline.atomic_json(out/'receiving.json', report)
    report['suite_source_audit_reuse'] = audit_session.evidence()
    for path,key,row,typed,deps in typed_states:
        final=isolated_final_typed(path,key,row,out/key.replace('/','-'))
        import cec_received_private_stage as stage
        same=annotations.same_replay(stage.stable(final),stage.stable(typed))
        if not same:
            pipeline.atomic_json(out/key.replace('/','-')/'typed-final-comparison-failure.json',
                dict(original=typed,final=final,same_replay=False,admitted=False,release_authority=False))
        assert same and final['ok']and final['complete'],'final_typed_annotation_transition_changed'
        assert deps=={p:force._hash(Path(p))for p in deps}
    report['typed_print_transitions_live']=True
    report['code_unchanged'] = code == force._code_identity()
    report['plan_unchanged'] = force._hash(plan_path) == report['plan_sha256']
    report['driver_sha256']=driver_sha
    report['driver_unchanged']=driver_sha==force._hash(Path(__file__))
    report['goal_complete'] = (report['code_unchanged'] and report['plan_unchanged'] and report['driver_unchanged']
        and all(r['source_unchanged'] and r['source_family_unchanged']
            and r['source_inputs_unchanged'] and r['source_intake_ok']
            and r['parity'][0] is True and r['opens'] == 0
            and r['native_errors'] == 0 and r['warnings'] == 0 and r['exclusions'] == 0
            and r['producer'].get('native_library_context', {}).get('bound') is True
            and r['scored_drc'] == 0
            for r in report['boards'].values()))
    pipeline.atomic_json(out/'receiving.json', report)
    print('goal complete', report['goal_complete'], 'code unchanged',
          report['code_unchanged'], flush=True)


if __name__ == '__main__':
    main()
