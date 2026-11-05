#!/usr/bin/env python3
"""Bounded, manifest-authoritative parallel current-BETA pipeline campaign.

This coordinator never grants admission itself. Each board runs the canonical
pipeline in an isolated process; blocked boards cannot hide peers' progress.
Source inputs and results remain distinct, and no artifact is auto-promoted.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

import cec_beta_manifest as manifest
import cec_stage_admission

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signature_unchanged(signature):
    """Check every declared file, including missing/deleted inputs."""
    return all((ROOT / row['path']).is_file()
               and sha(ROOT / row['path']) == row['sha256']
               for row in signature['files'])


def inputs(boards, overrides=None):
    overrides = overrides or {}
    if set(overrides) - set(boards):
        raise ValueError('input override must select a campaign board')
    unknown = (set(boards) | set(overrides)) - set(manifest.WAVE_BOARDS)
    if unknown:
        raise ValueError('not a current wave board: ' + ', '.join(sorted(unknown)))
    rows = []
    for name in dict.fromkeys(boards):
        entry = manifest.BY_BOARD[name]
        directory = ROOT/'beta'/entry['directory']
        board = Path(overrides[name]).resolve() if name in overrides else directory/entry['pcb']
        if not board.is_file():
            raise FileNotFoundError(board)
        # Hash the complete declared hierarchy, never recursively discover
        # another board or treat an old candidate as a source fallback.
        import cec_full_pipeline as pipeline
        import cec_synth_pipeline as synth
        cfg = synth.Config.load(name)
        signature = pipeline._files_signature(pipeline._source_files(cfg, board))
        rows.append({'board': name, 'input': str(board), 'input_sha256': sha(board),
                     'derived': name in overrides, 'source_signature': signature})
    return rows


def continuation_inputs(summary, boards):
    """Explicit completed-attempt lineage, never a latest-file heuristic.

    A blocked attempt is useful work; its process need not have succeeded.
    Source/engine stability during that attempt and current source identity
    are still mandatory. No-output attempts explicitly start fresh.
    """
    import cec_pass_review
    summary = Path(summary).resolve()
    report = json.loads(summary.read_text())
    overrides, lineage = {}, {}
    for name in dict.fromkeys(boards):
        if name not in manifest.WAVE_BOARDS:
            raise ValueError('not a current wave board: ' + name)
        row = report.get('boards', {}).get(name)
        if not row:
            raise ValueError('previous suite does not contain requested board: ' + name)
        if (row.get('status') in ('running', 'queued')
                or row.get('source_inputs_unchanged') is not True
                or row.get('engine_unchanged') is not True
                or not signature_unchanged(row['source_signature'])):
            raise ValueError('previous attempt is running or has invalid/stale authority: ' + name)
        target = summary.parent / name
        state_path = target / 'pipeline-state.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if state.get('board', name) != name:
            raise ValueError('previous journal family mismatch: ' + name)
        path, stage, verified = cec_pass_review.select_output(target, state)
        if path is not None and (verified or stage.startswith('placement-checkpoint:')):
            overrides[name] = str(path)
            lineage[name] = {'mode': 'continue', 'previous_suite': str(summary),
                             'stage': stage, 'input_sha256': sha(path)}
        else:
            lineage[name] = {'mode': 'fresh', 'previous_suite': str(summary),
                             'reason': 'no_verified_resumable_output', 'stage': stage}
    return overrides, lineage


def frontier_inputs(plan_path, expected_sha256, boards=None):
    """Explicit hash-bound received inputs, NEVER a canonical fallback.

    Validation is not admission. Zero-open records are immutable read-only
    controls, including manifest projects which are not wave-enabled.
    """
    if type(expected_sha256)is not str or not re.fullmatch('[0-9a-f]{64}',expected_sha256):
        raise ValueError('exact frontier plan SHA-256 required')
    plan=Path(plan_path).resolve(strict=True)
    if sha(plan)!=expected_sha256:raise ValueError('frontier plan hash changed')
    data=json.loads(plan.read_text())
    if type(data)is not dict or type(data.get('boards'))is not list or not data['boards']:
        raise ValueError('nonempty frontier boards list required')
    records={};bound_files={plan};assembly_identities={}
    def bound(path,expected):
        if type(path)is not str or not path or type(expected)is not str or not re.fullmatch('[0-9a-f]{64}',expected):
            raise ValueError('exact frontier artifact path and SHA-256 required')
        result=Path(path);result=(ROOT/result).resolve(strict=True)
        if not result.is_file()or sha(result)!=expected:raise ValueError('frontier artifact hash changed: '+str(result))
        bound_files.add(result);return result
    for record in data['boards']:
        if type(record)is not dict or type(record.get('board'))is not str:
            raise ValueError('named frontier board record required')
        name=record['board'];entry=manifest.BY_BOARD.get(name)
        if not entry or not entry.get('pcb'):raise ValueError('unsupported frontier board: '+name)
        if name in records:raise ValueError('duplicate frontier board: '+name)
        if type(record.get('expected_opens'))is not int or record['expected_opens']<0:
            raise ValueError('nonnegative integer frontier open inventory required')
        candidate=bound(record.get('path'),record.get('sha256'))
        # Historical plans also carry descriptive prose or an unverified path
        # in lineage. Only an explicitly hashed artifact supplies identity.
        if 'lineage_sha256'in record:bound(record.get('lineage'),record['lineage_sha256'])
        if ('parent_path'in record)!=('parent_sha256'in record):raise ValueError('complete frontier parent binding required')
        if 'parent_path'in record:bound(record['parent_path'],record['parent_sha256'])
        instance=record.get('assembly_instance')
        if instance is not None:
            import cec_assembly_instance
            resolved=cec_assembly_instance.resolve(candidate,instance,ROOT)
            assembly_identities[name]=json.loads(json.dumps(resolved,default=str))
            bound_files.update(resolved['paths'].values())
        records[name]={**record,'path':str(candidate)}
    selected=list(records)if boards is None else list(boards)
    if not selected or len(selected)!=len(set(selected)):raise ValueError('unique selected frontier boards required')
    if set(selected)-records.keys():raise ValueError('selected board missing from frontier plan')
    import cec_full_pipeline as pipeline,cec_synth_pipeline as synth
    result=[]
    for name in selected:
        record=records[name];control=record['expected_opens']==0
        if name not in manifest.WAVE_BOARDS and not control:raise ValueError('frontier board not wave-enabled: '+name)
        cfg=synth.Config.load(name)
        signature=pipeline._files_signature(set(pipeline._source_files(cfg,record['path']))|bound_files)
        result.append(dict(board=name,input=record['path'],input_sha256=record['sha256'],derived=True,
            source_signature=signature,frontier_plan=str(plan),frontier_plan_sha256=expected_sha256,
            frontier_control_read_only=control,assembly_instance=record.get('assembly_instance'),
            frontier_assembly_identity=assembly_identities.get(name),
            continuation=dict(mode='explicit_frontier',expected_opens=record['expected_opens'],
                lineage=record.get('lineage'),lineage_sha256=record.get('lineage_sha256'),
                lineage_artifact_verified='lineage_sha256'in record,
                parent_path=record.get('parent_path'),parent_sha256=record.get('parent_sha256'))))
    if sha(plan)!=expected_sha256 or any(not signature_unchanged(r['source_signature'])for r in result):
        raise ValueError('frontier authority changed during input validation')
    return result


def assert_frontier_live(row):
    if not row.get('frontier_plan'):return
    fresh=frontier_inputs(row['frontier_plan'],row['frontier_plan_sha256'],[row['board']])[0]
    for key in ('input','input_sha256','source_signature','assembly_instance','frontier_assembly_identity','frontier_control_read_only'):
        if fresh[key]!=row[key]:raise ValueError('frontier dispatch authority changed: '+key)


def command(row, out, *, trials, passes, workers_per_board=2, priority_repair_timeout=None):
    if (not isinstance(workers_per_board, int) or isinstance(workers_per_board, bool)
            or workers_per_board < 1):
        raise ValueError('workers per board must be a positive integer')
    if priority_repair_timeout is not None and (
            isinstance(priority_repair_timeout, bool)
            or not math.isfinite(float(priority_repair_timeout))
            or float(priority_repair_timeout) <= 0):
        raise ValueError('priority repair timeout must be finite and positive')
    args = [sys.executable, str(ROOT/'scripts/cec_full_pipeline.py'),
        '--board', row['board'], '--out', str(out), '--workers', str(workers_per_board),
        '--strategies', 'dataflow,hybrid', '--placement-seeds', '0',
        '--craft-trials', str(trials), '--craft-rounds', '2', '--craft-epochs', '1',
        '--passes', str(passes), '--opt', '8', '--route-candidates', '2',
        '--route-workers', '1', '--route-timeout', '600', '--no-dashboard']
    if priority_repair_timeout is not None:
        args += ['--priority-repair-timeout', str(float(priority_repair_timeout))]
    if row.get('frontier_plan'):
        assert_frontier_live(row)
        if row['frontier_control_read_only']:raise ValueError('frontier control is read-only, not a routing job')
        if row.get('assembly_instance')is not None:raise ValueError('frontier assembly dispatch requires explicit pipeline context threading')
        import cec_interface_eco
        eco=cec_interface_eco.read_status(row['input'])
        if eco and eco.get('route_authority_invalidated'):raise ValueError('frontier route authority invalidated; explicit rebase required')
        return args+['--input-board',row['input'],'--allow-derived-input']
    if row['derived']:
        args += ['--input-board', row['input'], '--allow-derived-input']
        # A moved interface is a placement seed, never retained route authority.
        # Validate the hash-bound certificate at launch; do not infer an ECO
        # from its filename, refdes, or the fact that it is a derived board.
        import cec_interface_eco
        eco = cec_interface_eco.read_status(row['input'])
        if eco and eco.get('route_authority_invalidated'):
            args += ['--replace-placement']
    else:
        args += ['--replace-placement', '--fresh-placement-only']
    return args


def write_json(path, payload):
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(payload, indent=2, default=str)+'\n')
    os.replace(temporary, path)


def geometry_dispatch_gate(row):
    """Inspect source-declared shared geometry before launching any worker."""
    import cec_xfcn_contract
    entry = manifest.BY_BOARD[row['board']]
    return cec_xfcn_contract.mating_compilation_gate(
        ROOT / 'beta' / entry['directory'] / entry['schematic'])


def geometry_dispatch_refusal(row):
    gate = geometry_dispatch_gate(row)
    if gate.get('ok') is True:
        return None
    return {'status': 'blocked_or_failed', 'reason': gate['reason'],
            'worker_launched': False, 'qualification_valid': False,
            'retryable_without_geometry_change': False,
            'retry_requires': gate['retry_requires'],
            'stages': {'interface_compilation': stage_summary(
                {'status': 'complete', 'result': gate})},
            'failure_evidence': gate}


def stage_summary(data):
    """Keep execution completion distinct from physical admission."""
    result = data.get('result') or {}
    execution = data.get('status')
    admission = cec_stage_admission.admission_ok(result) if execution == 'complete' else None
    return {'execution_status': execution,
            'status': ('blocked' if admission is False else execution),
            'admission_ok': admission,
            'reason': (result.get('reason') or result.get('stop_reason')
                       or ('explicit_admission_gate_refused'
                           if result.get('admission_gate') is False else None)
                       or (data.get('failure_evidence') or {}).get('status')
                       or (data.get('failure_evidence') or {}).get('reason')),
            'error': data.get('error'),
            'failure_evidence': data.get('failure_evidence')}


def terminalize_state(path, *, process_status, exit_code):
    """Reconcile a dead owned job's running stage without altering prior evidence."""
    path = Path(path)
    if not path.is_file():
        return None
    state = json.loads(path.read_text())
    terminal = 'timed_out' if process_status=='budget_exhausted' else 'interrupted'
    changed = False
    for row in state.get('stages', {}).values():
        if row.get('status') != 'running':
            continue
        row.update(status=terminal, terminal_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                   failure_evidence={'reason':process_status, 'exit_code':exit_code,
                                     'authority':'campaign_observed_process_exit'})
        changed = True
    if changed:
        write_json(path, state)
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--boards', default=None)
    parser.add_argument('--input', action='append', default=[], metavar='BOARD=PCB')
    parser.add_argument('--continue-suite', help='Explicit prior suite.json; retain verified work, re-run all gates')
    parser.add_argument('--frontier-plan',help='Explicit received nine-board plan; no canonical fallback or automatic child promotion')
    parser.add_argument('--expected-frontier-plan-sha256')
    parser.add_argument('--jobs', type=int, default=3)
    parser.add_argument('--workers-per-board', type=int, default=2,
                        help='Ceiling for each board placement and nested exact-probe pool')
    parser.add_argument('--priority-repair-timeout', type=float, default=None,
                        help='Explicit per-board critical-placement repair budget, bounded by job timeout')
    parser.add_argument('--trials', type=int, default=24)
    parser.add_argument('--passes', type=int, default=8)
    parser.add_argument('--job-timeout', type=float, default=1800)
    parser.add_argument('--minimum-free-gib', type=float, default=8)
    parser.add_argument('--review-dir', help='Optional desktop-visible copy of this pass gallery and previews')
    args = parser.parse_args(argv)
    if bool(args.frontier_plan)!=bool(args.expected_frontier_plan_sha256):
        parser.error('--frontier-plan and --expected-frontier-plan-sha256 must be supplied together')
    if args.frontier_plan and(args.input or args.continue_suite):
        parser.error('--frontier-plan cannot combine with --input or --continue-suite')
    if (not 1 <= args.jobs <= 6 or args.workers_per_board < 1
            or not math.isfinite(args.job_timeout) or args.job_timeout <= 0
            or not math.isfinite(args.minimum_free_gib) or args.minimum_free_gib < 0
            or (args.priority_repair_timeout is not None and (
                not math.isfinite(args.priority_repair_timeout) or args.priority_repair_timeout <= 0))
            or args.trials < 1 or args.passes < 1):
        parser.error('invalid bounded resource policy')
    errors = manifest.validate(str(ROOT))
    if errors:
        raise ValueError('current-BETA manifest invalid: ' + '; '.join(errors))
    overrides = {}
    for item in args.input:
        name, path = item.split('=', 1)
        if name in overrides: raise ValueError('duplicate input override: ' + name)
        overrides[name] = path
    selected = [value for value in (args.boards if args.boards is not None else ','.join(manifest.WAVE_BOARDS)).split(',') if value]
    if not selected:
        parser.error('at least one wave board is required')
    lineage = {}
    if args.continue_suite:
        if overrides:
            parser.error('--continue-suite and --input cannot be combined')
        overrides, lineage = continuation_inputs(args.continue_suite, selected)
    rows = (frontier_inputs(args.frontier_plan,args.expected_frontier_plan_sha256,
                           selected if args.boards is not None else None)
            if args.frontier_plan else inputs(selected, overrides))
    for row in rows:
        if row['board'] in lineage:
            row['continuation'] = lineage[row['board']]
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out/'suite.json'
    if summary_path.exists():
        raise ValueError('use a new campaign directory; existing evidence is immutable')
    report = {'schema':1, 'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'engine_sha256':sha(__file__), 'jobs':args.jobs,
        'workers_per_board':args.workers_per_board, 'minimum_free_gib':args.minimum_free_gib,
        'priority_repair_timeout_s':args.priority_repair_timeout,
        'not_wave_enabled':[row['board'] for row in manifest.PROJECTS if not row['wave']],
        'boards':{row['board']:{**row, 'status':'queued'} for row in rows}, 'promoted':False}
    write_json(summary_path, report)
    lock = threading.Lock()

    def update(name, result):
        with lock:
            report['boards'][name].update(result)
            write_json(summary_path, report)

    def execute(row):
        target = out/row['board']
        target.mkdir(parents=True, exist_ok=True)
        if row.get('frontier_plan'):
            assert_frontier_live(row)
            if row['frontier_control_read_only']:
                result=dict(status='read_only_control',worker_launched=False,qualification_valid=False,
                    reason='frontier zero-open control retained; fresh receiving is separate',
                    source_board_unchanged=sha(row['input'])==row['input_sha256'],
                    source_inputs_unchanged=signature_unchanged(row['source_signature']))
                write_json(target/'campaign-input.json',{**row,'command':None})
                write_json(target/'campaign-result.json',result);return result
        # Do not start even a normalization worker for a row whose shared
        # geometry compiler already proves the current constraints conflict.
        refusal = geometry_dispatch_refusal(row)
        if refusal is not None:
            refusal.update(source_board_unchanged=sha(row['input']) == row['input_sha256'],
                           source_inputs_unchanged=signature_unchanged(row['source_signature']))
            write_json(target/'campaign-input.json', {**row, 'command': None})
            write_json(target/'campaign-result.json', refusal)
            return refusal
        if shutil.disk_usage(out).free < args.minimum_free_gib * 1024**3:
            return {'status':'resource_refused', 'reason':'free disk below campaign floor'}
        cmd = command(row, target, trials=args.trials, passes=args.passes,
                      workers_per_board=args.workers_per_board,
                      priority_repair_timeout=args.priority_repair_timeout)
        import cec_full_pipeline as pipeline
        # A campaign may coexist with active development, but a mixed-engine
        # result must never be presented as a replay of one code revision.
        engine = pipeline._files_signature(sorted((ROOT/'scripts').glob('*.py')))
        write_json(target/'campaign-input.json', {**row, 'command':cmd,
                                                  'engine_signature':engine})
        started = time.monotonic()
        env = dict(os.environ, PYTHONUNBUFFERED='1', OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2',
                   CEC_JOB_DEADLINE_EPOCH=str(time.time()+args.job_timeout))
        with (target/'pipeline.log').open('w') as log:
            proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    env=env, start_new_session=True)
            write_json(target/'campaign-process.json', {'pid':proc.pid, 'status':'running'})
            update(row['board'], {'status':'running', 'pid':proc.pid})
            try:
                exit_code = proc.wait(timeout=args.job_timeout)
                status = 'completed' if exit_code == 0 else 'blocked_or_failed'
            except subprocess.TimeoutExpired:
                import signal
                os.killpg(proc.pid, signal.SIGTERM)
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL); proc.wait()
                exit_code, status = proc.returncode, 'budget_exhausted'
        result = {'status':status, 'exit_code':exit_code,
                  'elapsed_s':time.monotonic()-started,
                  'source_board_unchanged':sha(row['input']) == row['input_sha256'],
                  'source_inputs_unchanged':signature_unchanged(row['source_signature']),
                  'engine_unchanged':signature_unchanged(engine)}
        state_path = target/'pipeline-state.json'
        if state_path.exists():
            state = terminalize_state(state_path, process_status=status, exit_code=exit_code)
            result['stages'] = {name:stage_summary(data)
                                for name,data in state.get('stages',{}).items()}
        if not result['source_inputs_unchanged']:
            result['status'] = 'source_changed_during_run'
        elif not result['engine_unchanged']:
            result['status'] = 'engine_changed_during_run'
        result['qualification_valid'] = (exit_code == 0 and result['source_inputs_unchanged']
                                         and result['engine_unchanged'])
        write_json(target/'campaign-process.json', {'pid':proc.pid, 'status':result['status']})
        write_json(target/'campaign-result.json', result)
        import cec_pass_review
        try:
            result['review'] = cec_pass_review.publish(
                target, row['board'], result, mirror=args.review_dir)
        except Exception as exc:
            result['review_error'] = str(exc)
        write_json(target/'campaign-result.json', result)
        return result

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        pending = {pool.submit(execute,row):row['board'] for row in rows}
        for future in as_completed(pending):
            name = pending[future]
            try: result = future.result()
            except Exception as exc: result = {'status':'coordinator_error','error':str(exc)}
            update(name, result)
            import cec_pass_review
            gallery_path = cec_pass_review.gallery(report, out/'all-boards.png', mirror=args.review_dir)
            with lock:
                report['gallery'] = gallery_path
                write_json(summary_path, report)
            print(json.dumps({'board':name, **{k:v for k,v in result.items()
                              if k not in ('stages', 'review')},
                              'viewer_url':(result.get('review') or {}).get('viewer_url'),
                              'gallery':gallery_path}),flush=True)
    report['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    import cec_pass_review
    report['gallery'] = cec_pass_review.gallery(report, out/'all-boards.png', mirror=args.review_dir)
    write_json(summary_path,report)


if __name__ == '__main__': main()
