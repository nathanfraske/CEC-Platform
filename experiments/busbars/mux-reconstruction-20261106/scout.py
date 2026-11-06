"""Compile the one map-derived cohort against the exact repaired parent."""
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
SOURCE = ROOT / 'experiments/busbars/cap-ground-repair-20261106/candidate/board.kicad_pcb'
SHA = '1512d4f046daebaba629ac29db4bc5caf2d53bc6ccf370e44deb903c4259b045'
STUDY = ROOT / 'experiments/busbars/reservoir-repack-20261106/geometry-map-derived-seven.json'


def worker():
    import pcbnew
    import cec_force_current as force
    import cec_cell_macro_requests as compiler
    from cec_pipeline import cells
    assert force._hash(SOURCE) == SHA
    study = json.loads(STUDY.read_text())
    assert study['source_sha256'] == SHA and study['paired_ok'] and not study['court_clashes']
    board = pcbnew.LoadBoard(str(SOURCE))
    poses = study['proposed_poses']
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    operation = dict(kind='place_cell', native_macro=True,
        allow_linear_power_stage_reconstruction=True,
        poses=[dict(reference=ref, at_nm=value[:2], rotation_deg=round(value[2]) % 360)
               for ref, value in sorted(poses.items())],
        allow_locked_footprint_uuids=[force._uid(fps[r]) for r in poses if fps[r].IsLocked()],
        allow_locked_track_uuids=[], allow_locked_transport_uuids=[],
        reference_group_uuids=[], routes=[], vias=[], max_shift_nm=6000000)
    start = time.monotonic()
    result = dict(source=str(SOURCE), source_sha256=SHA, study_sha256=force._hash(STUDY),
                  operation=operation, board_saved=False, accepted=False)
    try:
        with compiler.observe_compilation_phases(
                lambda event: print('CEC_PHASE=' + json.dumps(event), flush=True)):
            _, packet, transported = cells.compile_macro(board, operation, 'atx-24pin-rev3',
                                                         enforce_locks=False)
        result.update(status='source_compiled', packet=packet, transported=transported)
    except Exception as exc:
        result.update(status='compile_refused', error_type=type(exc).__name__,
                      error=str(exc), traceback=traceback.format_exc())
    assert force._hash(SOURCE) == SHA
    result['elapsed_s'] = time.monotonic() - start
    print('CEC_RESULT=' + json.dumps(result, separators=(',', ':')))


def main():
    revision = sys.argv[1]
    assert revision and len(revision) <= 32 and all(c.isalnum() or c in '-_' for c in revision)
    target = WORK / ('compile-' + revision + '.json')
    assert not target.exists(), 'fresh_observation_required'
    path = ROOT / 'experiments/busbars/coherent-mux-20261106/scout.py'
    spec = importlib.util.spec_from_file_location('bounded_phase_runner', path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    code, output, reason = runner.bounded_compile([sys.executable, str(Path(__file__).resolve()), '--worker'])
    lines = [v.removeprefix('CEC_RESULT=') for v in output.splitlines() if v.startswith('CEC_RESULT=')]
    report = json.loads(lines[0]) if code == 0 and len(lines) == 1 else dict(
        status='worker_timeout' if reason else 'worker_failed', reason=reason,
        exit_code=code, diagnostic_output=output[-8000:], board_saved=False, accepted=False)
    report['events'] = [json.loads(v.split('=', 1)[1]) for v in output.splitlines()
                        if v.startswith('CEC_PHASE=')]
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('packet', 'operation')}, indent=2))


if __name__ == '__main__':
    worker() if '--worker' in sys.argv else main()
