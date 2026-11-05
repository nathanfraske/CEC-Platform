"""Finite source-discovered stub/keeper cohorts, retaining the last good child."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import cec_swig_guard; cec_swig_guard.pin()
import wx; quiet = wx.LogNull()
import cec_force_current as force
import cec_terminal_shadow_keeper_finish as owner


def native_intake(stage):
    assert all(stage[k] is True for k in ('ok','complete','changed','source_family_and_code_unchanged'))
    assert stage['errors'] == [] and type(stage['opens']) is int and stage['opens'] == 0
    assert stage['new_native_faults'] == [] and stage['code_identity'] == force._code_identity()
    child = Path(stage['candidate']); assert force._hash(child) == stage['candidate_sha256']
    n = stage['native_producer']; assert n['ok'] is True and n['complete'] is True
    assert n['native_inventory']['potentially_truncated'] is False
    assert force._hash(Path(n['report'])) == n['report_sha256']
    raw = json.loads(Path(n['report']).read_text())
    assert raw['unconnected_items'] == [] and type(stage['candidate_raw_native_count']) is int
    assert len(raw['violations']) == stage['candidate_raw_native_count']
    assert all(force._hash(Path(p)) == h for p, h in n['source_files'].items())
    assert any(p.endswith('.kicad_pcb') and h == stage['candidate_sha256'] for p, h in n['source_files'].items())
    return dict(code_identity=stage['code_identity'], candidate=str(child),
        boards=dict(candidate=dict(sha256=stage['candidate_sha256'], native_producer=n)),
        native_only_typed_conductor_intake=True, full_board_grade=False, fab_ready=False, release_authority=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('source', 'grade', 'out', 'reporting-build'): p.add_argument('--'+key, type=Path, required=True)
    p.add_argument('--hint', required=True); p.add_argument('--maximum-cohorts', type=int, default=2)
    p.add_argument('--max-trials', type=int, default=8); p.add_argument('--allow-locked-source', action='store_true')
    a = p.parse_args(); assert not a.out.exists() and 1 <= a.maximum_cohorts <= 4 and 1 <= a.max_trials <= 8
    a.out.mkdir(parents=True); epoch = force._code_identity(); source = a.source.resolve(); cursor = source; grade = a.grade
    inputs = {str(q.resolve()):force._hash(q) for q in (Path(__file__), Path(owner.__file__), a.source, a.grade)}
    worker = Path('build/root_try_terminal_shadow_keeper_20261020.py'); inputs[str(worker)] = force._hash(worker)
    env = dict(os.environ, PYTHONPATH='scripts:ops:build', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    stages = []; attempts = []; seen = {force._hash(cursor)}; stop = 'explicit_finite_cohort_limit'
    for cohort in range(a.maximum_cohorts):
        found = owner.discover(cursor, board_hint=a.hint, allow_locked_source=a.allow_locked_source, maximum_trials=a.max_trials)
        discovery = a.out/('discovery-'+str(cohort)+'.json'); force._write(discovery, found); inputs[str(discovery)] = force._hash(discovery)
        accepted = False
        for trial, row in enumerate(found['proposals'][:a.max_trials]):
            work = a.out/('cohort-'+str(cohort)+'-trial-'+str(trial))
            target = row['target']
            command = [sys.executable, str(worker), '--source', str(cursor), '--grade', str(grade),
                '--hint', a.hint, '--out', str(work), '--reporting-build', str(a.reporting_build), '--zone-uuid', target['zone_uuid']]
            for uid in target['track_uuids']: command += ['--track-uuid', uid]
            if a.allow_locked_source: command.append('--allow-locked-source')
            log = work.with_suffix('.log')
            try:
                run = subprocess.run(command, capture_output=True, text=True, env=env, timeout=55)
                log.write_text(run.stdout+run.stderr)
                attempt = dict(cohort=cohort, trial=trial, target=target, returncode=run.returncode, log=str(log), accepted=False)
                attempts.append(attempt); inputs[str(log)] = force._hash(log)
                path = work/'stage.json'
                if not path.exists(): continue
                inputs[str(path)] = force._hash(path); stage = json.loads(path.read_text())
                if run.returncode or not stage['ok'] or not stage['complete'] or not stage['changed']: continue
                assert Path(stage['source']).resolve() == cursor and stage['source_sha256'] == force._hash(cursor)
                incoming = native_intake(stage); child = Path(stage['candidate']).resolve()
                assert stage['candidate_sha256'] not in seen
                seen.add(stage['candidate_sha256']); stages.append(str(path)); cursor = child
                grade = a.out/('intake-'+str(cohort)+'.native-only.json'); force._write(grade, incoming)
                inputs[str(grade)] = force._hash(grade); attempt['accepted'] = True; accepted = True
                print(json.dumps(dict(cohort=cohort, trial=trial, accepted=True,
                    retired_tracks=stage['proposal']['track_uuids'], candidate_sha256=stage['candidate_sha256'])), flush=True)
                break
            except subprocess.TimeoutExpired:
                attempts.append(dict(cohort=cohort, trial=trial, timeout_s=55, accepted=False))
        if not accepted:
            stop = 'finite_native_terminal_shadow_menu_yielded_no_received_child'; break
    assert epoch == force._code_identity() and all(force._hash(Path(q)) == h for q, h in inputs.items())
    force._write(a.out/'pass.json', dict(ok=True, complete=True, changed=bool(stages), code_identity=epoch,
        source=str(source), source_sha256=force._hash(source), candidate=str(cursor), candidate_sha256=force._hash(cursor),
        board_hint=a.hint, stages=stages, attempts=attempts, stop_reason=stop, input_sha256=inputs,
        original_whole_native_current_clipped_and_reference_receiving_still_required=True,
        all_contours_clean=False, new_ui_tabs=0, fab_ready=False, release_authority=False))
    print(json.dumps(dict(pass_report=str(a.out/'pass.json'), changed=bool(stages), phases=len(stages), stop_reason=stop)), flush=True)


if __name__ == '__main__': main()
