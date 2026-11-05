"""Bounded chart-first/back-outline passes; every child needs fresh native DRC.

This orchestrates the existing annotation owner. It does not add a new
clearance exception, shrink text, move a part, or provide routing authority.
The intermediate native-only grade is explicitly not a full-board grade.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import cec_force_current as force


def native_only_grade(stage):
    """Forward actual source-bound native evidence, never a synthetic pass."""
    if not (stage['ok'] and stage['complete'] and stage['changed']
            and not stage['errors'] and not stage['opens'] and not stage['new_native_faults']):
        raise ValueError('only_received_native_annotation_children_can_advance')
    child = Path(stage['candidate'])
    native = stage['native_producer']
    if not (force._hash(child) == stage['candidate_sha256']
            and native['ok'] and native['complete']
            and not native['native_inventory']['potentially_truncated']
            and force._hash(Path(native['report'])) == native['report_sha256']
            and stage['code_identity'] == force._code_identity()):
        raise ValueError('actual_current_native_annotation_evidence_required')
    for path, digest in native['source_files'].items():
        if force._hash(Path(path)) != digest:
            raise ValueError('native_annotation_source_file_changed')
    if not any(path.endswith('.kicad_pcb') and digest == stage['candidate_sha256']
               for path, digest in native['source_files'].items()):
        raise ValueError('native_annotation_report_is_not_bound_to_actual_child')
    return dict(code_identity=stage['code_identity'], candidate=str(child),
        boards=dict(candidate=dict(sha256=stage['candidate_sha256'], native_producer=native)),
        native_only_annotation_intake=True, full_board_grade=False,
        fab_ready=False, release_authority=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('start-stage', 'out', 'reporting-build'):
        parser.add_argument('--'+key, type=Path, required=True)
    parser.add_argument('--additional-cohorts', type=int, default=4)
    parser.add_argument('--maximum-components', type=int, default=6)
    parser.add_argument('--max-seeds', type=int, default=16)
    args = parser.parse_args()
    if (args.out.exists() or not 0 <= args.additional_cohorts <= 8
            or not 1 <= args.maximum_components <= 8 or not 1 <= args.max_seeds <= 32):
        raise ValueError('fresh_bounded_annotation_pass_required')
    args.out.mkdir(parents=True)
    started = time.monotonic()
    epoch = force._code_identity()
    worker = Path('ops/cec_dense_reference_mapping.py')
    inputs = {str(q): force._hash(q) for q in (Path(__file__), args.start_stage, worker)}
    stage_path = args.start_stage
    initial = json.loads(stage_path.read_text())
    current_grade = native_only_grade(initial)
    hint = initial['proposal']['board_hint']
    source = Path(initial['source'])
    if force._hash(source) != initial['source_sha256']:
        raise ValueError('initial_annotation_source_changed')
    stages = [str(stage_path)]
    refs = [row['reference'] for row in initial['proposal']['records']]
    attempts = []
    stop = 'explicit_finite_cohort_limit'
    env = dict(os.environ, PYTHONPATH='scripts:build:ops',
        OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    for index in range(args.additional_cohorts):
        intake = args.out / ('intake-'+str(index)+'.native-only.json')
        force._write(intake, current_grade)
        inputs[str(intake)] = force._hash(intake)
        work = args.out / ('cohort-'+str(index))
        command = [sys.executable, str(worker), '--source', current_grade['candidate'],
            '--grade', str(intake), '--hint', hint, '--reporting-build', str(args.reporting_build),
            '--maximum-components', str(args.maximum_components), '--max-seeds', str(args.max_seeds),
            '--out', str(work)]
        try:
            run = subprocess.run(command, capture_output=True, text=True, env=env, timeout=55)
            log = args.out / ('cohort-'+str(index)+'.log')
            log.write_text(run.stdout+run.stderr)
            inputs[str(log)] = force._hash(log)
            trial_path = work/'stage.json'
            row = dict(index=index, returncode=run.returncode, log=str(log), accepted=False)
            attempts.append(row)
            if run.returncode or not trial_path.exists():
                stop = 'bounded_worker_refusal_or_incomplete_attempt'
                break
            stage = json.loads(trial_path.read_text())
            if (stage['source_sha256'] != current_grade['boards']['candidate']['sha256']
                    or Path(stage['source']).resolve() != Path(current_grade['candidate']).resolve()):
                raise ValueError('annotation_worker_rebased_away_from_actual_preceding_child')
            incoming = native_only_grade(stage)
            new_refs = [r['reference'] for r in stage['proposal']['records']]
            if not new_refs or set(refs).intersection(new_refs):
                raise ValueError('annotation_repeat_or_missing_owned_reference')
            if stage['candidate_raw_native_count'] >= stage['source_raw_native_count']:
                stop = 'no_strict_native_marking_progress'
                break
            current_grade = incoming
            stages.append(str(trial_path))
            refs.extend(new_refs)
            inputs[str(trial_path)] = force._hash(trial_path)
            row.update(accepted=True, references=new_refs,
                raw_native=[stage['source_raw_native_count'], stage['candidate_raw_native_count']])
            print(json.dumps(row), flush=True)
        except subprocess.TimeoutExpired:
            stop = 'bounded_worker_deadline'
            attempts.append(dict(index=index, accepted=False, timeout_s=55))
            break
    if epoch != force._code_identity() or any(force._hash(Path(p)) != h for p, h in inputs.items()):
        raise ValueError('annotation_pass_input_or_runtime_changed')
    candidate = Path(current_grade['candidate'])
    force._write(args.out/'pass.json', dict(ok=True, complete=True, changed=True,
        code_identity=epoch, source=str(source), source_sha256=initial['source_sha256'],
        candidate=str(candidate), candidate_sha256=force._hash(candidate), board_hint=hint,
        stages=stages, attempts=attempts, represented_references=refs, stop_reason=stop,
        source_raw_native_count=initial['source_raw_native_count'],
        candidate_raw_native_count=len(json.loads(Path(current_grade['boards']['candidate']
            ['native_producer']['report']).read_text())['violations']),
        elapsed_s=time.monotonic()-started, input_sha256=inputs,
        independent_whole_board_receiving_still_required=True,
        all_dense_markings_repaired=False, fab_ready=False, release_authority=False))
    print(json.dumps(dict(pass_report=str(args.out/'pass.json'), references=refs,
        stop_reason=stop, candidate_sha256=force._hash(candidate))), flush=True)


if __name__ == '__main__':
    main()
