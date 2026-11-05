"""Bounded scalar-path finishing; the coordinator still owns final adoption.

Only a closed selected route is eligible. The normal path never authorizes a
locked source cut. Work occurs in a private family and owned process group;
missing/partial worker output cannot replace the route. Parent-side source
reception precedes copying only the PCB, with immutable sidecars unchanged.
Fresh coordinator grading, protected-prefix checks and rollback remain required.
"""
import math
import os
import shutil
import sys
from pathlib import Path


def eligible(result):
    if not isinstance(result,dict):return False
    return (type(result.get('drc')) is int and result['drc']==0
        and type(result.get('unconnected')) is int and result['unconnected']==0
        and isinstance(result.get('routed'),(str,Path)) and bool(str(result['routed'])))


def reporting_build(requested=None):
    if requested is not None:
        if not isinstance(requested,(str,Path)) or not str(requested):
            raise ValueError('explicit_native_reporting_build_path_required')
        return Path(requested).resolve()
    configured=os.environ.get('CEC_NATIVE_DRC_REPORTING_BUILD')
    if configured is not None:
        if not configured.strip():raise ValueError('explicit_native_reporting_build_path_required')
        return Path(configured).resolve()
    # Read-only reuse of the existing private toolchain; no download, install,
    # fallback to capped custom-rule reporting, or assumption of validity.
    # cec_native_drc_runner independently verifies its exact source/build and
    # actual loaded modules every time a native report is produced.
    cache=Path(os.environ.get('XDG_CACHE_HOME',str(Path.home()/'.cache')))/'cec'/'native-drc-10.0.5'
    return cache.resolve() if cache.is_dir() else None


def apply(result,directory,*,board_hint,timeout_s=120.,native_reporting_build=None):
    import json
    import cec_certificate_repair as repair
    import cec_force_current as force
    import cec_operation_budget as budget
    import cec_sensitive_scalar_path_reflow as path_owner
    if not eligible(result):return dict(changed=False,skipped='no_closed_selected_route',release_authority=False)
    if (type(board_hint) is not str or not board_hint or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 1<=timeout_s<=180):
        raise ValueError('bounded_scalar_finish_identity_and_deadline_required')
    build=reporting_build(native_reporting_build)
    if build is None:return dict(changed=False,skipped='verified_native_reporting_build_unavailable',release_authority=False)
    source=Path(result['routed']).resolve();work=Path(directory).resolve()
    if not source.is_file():return dict(changed=False,skipped='selected_route_missing',release_authority=False)
    if work.exists():raise ValueError('fresh_private_scalar_finish_directory_required')
    original=force._hash(source);family=force._family(source,board_hint);epoch=force._code_identity()
    work.mkdir(parents=True);staged=work/'input.kicad_pcb';stage_dir=work/'stage';report=stage_dir/'stage.json'
    answer=dict(changed=False,source_sha256=original,release_authority=False,
        requires_independent_admission=True,report=str(report),source_locked_cut_authorized=False)
    try:
        repair._copy_board_family(str(source),str(staged))
        staged_family=force._family(staged,board_hint)
        if force._hash(staged)!=original:raise ValueError('private_scalar_source_clone_changed')
        operation=budget.run([sys.executable,str(Path(__file__).with_name('cec_sensitive_scalar_path_reflow.py')),
            '--source',str(staged),'--expected-source-sha256',original,'--board-hint',board_hint,
            '--reporting-build',str(build),'--maximum-candidates','1','--out',str(stage_dir)],
            work/'operation',operation='source_scalar_path_finish',timeout=float(timeout_s))
        answer['operation']=operation;payload=json.loads(report.read_text())
        if (force._hash(source)!=original or family!=force._family(source,board_hint) or epoch!=force._code_identity()
                or staged_family!=force._family(staged,board_hint)):
            raise ValueError('scalar_finish_source_family_or_code_changed_during_worker')
        if not isinstance(payload,dict):raise ValueError('scalar_stage_object_required')
        if payload.get('changed') is False:
            answer['skipped']='no_received_source_scalar_path_gain';return answer
        if (payload.get('changed') is not True or payload.get('ok') is not True
                or payload.get('complete') is not True or payload.get('errors')!=[]
                or payload.get('code_identity')!=epoch or payload.get('source_sha256')!=original
                or Path(payload['source']).resolve()!=staged.resolve()
                or payload.get('source_family_and_code_unchanged') is not True
                or type(payload.get('records')) is not list or len(payload['records'])!=1):
            raise ValueError('complete_current_source_bound_scalar_stage_required')
        child=Path(payload['candidate'])
        if (not child.is_absolute() or child.is_symlink() or not child.resolve().is_relative_to(stage_dir.resolve())
                or force._hash(child)!=payload['candidate_sha256']):
            raise ValueError('owned_hash_bound_scalar_finish_candidate_required')
        record=payload['records'][0]
        if not isinstance(record,dict):raise ValueError('scalar_stage_record_object_required')
        params=record['plan']
        if (not isinstance(params,dict) or set(params)!={'retired_track_uuids','points_nm','allow_locked_source'}
                or params['allow_locked_source'] is not False):
            raise ValueError('normal_scalar_finish_cannot_authorize_locked_source_or_unknown_scope')
        proof=path_owner.receive(staged,child,board_hint=board_hint,**params)
        answer['independent_source_path_receiving']=proof
        if (proof.get('ok') is not True or proof.get('complete') is not True
                or proof.get('source_sha256')!=original or proof.get('candidate_sha256')!=payload['candidate_sha256']):
            raise ValueError('parent_scalar_finish_source_receiving_refused')
        if (force._hash(source)!=original or family!=force._family(source,board_hint) or epoch!=force._code_identity()
                or staged_family!=force._family(staged,board_hint) or force._hash(child)!=payload['candidate_sha256']):
            raise ValueError('scalar_finish_source_family_or_code_changed_before_copy')
        # Exact independent replay above retains every source sidecar. Copy
        # only the received PCB; the caller keeps its immutable rollback family
        # and must freshly grade/protect the final selected artifact.
        shutil.copy2(child,source)
        answer.update(changed=True,output_sha256=force._hash(source),
            shortened_centerline_mm=proof['shortened_centerline_mm'],native_strokes_before_after=proof['native_strokes_before_after'])
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        answer['error']=type(exc).__name__+':'+str(exc)
    return answer
