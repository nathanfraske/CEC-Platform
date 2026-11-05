"""Failure-only evidence keeps exact inputs without unbounded artifact growth."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import cec_failure_replay as replay
import cec_fab_repair as repair


def fixture(tmp_path):
    board = tmp_path / 'renamed.kicad_pcb'
    board.write_bytes(b'original copper')
    board.with_suffix('.kicad_pro').write_bytes(b'original rules')
    extra = tmp_path / 'generated-track-uuids.json'
    extra.write_text('["owned"]')
    return board, extra


def save(snapshot, root, **kwargs):
    return replay.retain(snapshot, root, context={'step': 'polish'},
        error=RuntimeError('native failure'), engine={'worker.py': 'digest'}, **kwargs)


def test_pre_mutation_bytes_sidecars_engine_and_no_environment(tmp_path):
    board, extra = fixture(tmp_path)
    captured = replay.capture(board, extra_files=(extra,))
    board.write_bytes(b'corrupted after crash')
    report = save(captured, tmp_path / 'evidence')
    assert report['status'] == 'retained'
    root = Path(report['directory'])
    record = replay.verify(root, engine={'worker.py': 'digest'})
    assert (root / board.name).read_bytes() == b'original copper'
    assert (root / board.with_suffix('.kicad_pro').name).read_bytes() == b'original rules'
    assert (root / extra.name).read_text() == '["owned"]'
    assert not record['release_authority'] and record['diagnostic_only']
    assert 'environment' not in record
    with pytest.raises(ValueError, match='engine changed'):
        replay.verify(root, engine={'worker.py': 'new digest'})
    (root / board.name).write_bytes(b'changed')
    with pytest.raises(ValueError, match='input changed'):
        replay.verify(root, engine={'worker.py': 'digest'})


def test_deduplication_and_corruption_refusal(tmp_path):
    board, _ = fixture(tmp_path)
    captured = replay.capture(board)
    first = save(captured, tmp_path / 'store')
    second = save(captured, tmp_path / 'store')
    assert first['directory'] == second['directory'] and second['deduplicated']
    (Path(first['directory']) / board.name).write_text('corrupt')
    assert save(captured, tmp_path / 'store')['status'] == 'existing_evidence_corrupt'


def test_quota_and_free_space_refusals_are_explicit(tmp_path, monkeypatch):
    board, _ = fixture(tmp_path)
    assert replay.capture(board, max_bytes=1)['status'] == 'input_quota_exceeded'
    assert replay.capture(board, extra_files=(tmp_path / 'missing',))['status'] == 'input_missing'
    captured = replay.capture(board)
    assert save(captured, tmp_path / 'small', max_store_bytes=1)['status'] == 'store_quota_exceeded'
    monkeypatch.setattr(replay.shutil, 'disk_usage', lambda _: SimpleNamespace(free=replay.FREE_FLOOR_BYTES))
    assert save(captured, tmp_path / 'full')['status'] == 'free_space_floor'
    assert not list(tmp_path.rglob('replay.json'))


def test_concurrent_writers_share_quota_and_identical_inputs_deduplicate(tmp_path):
    board, _ = fixture(tmp_path)
    snapshot = replay.capture(board)
    root = tmp_path / 'same'
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(lambda _: save(snapshot, root), range(8)))
    assert sum(not r['deduplicated'] for r in rows) == 1
    used = sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    other = tmp_path / 'different'

    def store(index):
        return replay.retain(snapshot, other, context={'step': 'polish', 'index': index},
            error=RuntimeError('native failure'), engine={'worker.py': 'digest'},
            max_store_bytes=used + 100)

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(store, range(8)))
    assert sum(r['status'] == 'retained' for r in rows) == 1
    assert sum(r['status'] == 'store_quota_exceeded' for r in rows) == 7
    assert not list(other.glob('.partial-*'))


def test_manifest_tampering_and_extra_sidecars_refused(tmp_path):
    board, _ = fixture(tmp_path)
    stored = save(replay.capture(board), tmp_path / 'store')
    root = Path(stored['directory'])
    extra = root / 'undeclared.kicad_dru'
    extra.write_text('unexpected rules')
    with pytest.raises(ValueError, match='undeclared'):
        replay.verify(root, engine={'worker.py': 'digest'})
    extra.unlink()
    manifest = root / 'replay.json'
    record = json.loads(manifest.read_text())
    record['context']['step'] = 'different-operation'
    manifest.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='identity changed'):
        replay.verify(root, engine={'worker.py': 'digest'})


def test_failure_logs_are_bounded_and_flagged(tmp_path):
    board, _ = fixture(tmp_path)
    error = repair.NativeWorkerFailure('repair', subprocess.CompletedProcess(
        ['python', 'worker'], -11, stdout='x' * 100000, stderr='native fault'))
    row = replay.retain(replay.capture(board), tmp_path / 'store',
        context={}, error=error, engine={})
    data = replay.verify(row['directory'], engine={})['failure']
    assert len(data['stdout']) == replay.LOG_LIMIT and data['stdout_truncated']
    assert data['returncode'] == -11 and data['stderr'] == 'native fault'


@pytest.mark.parametrize('fail_step', ['repair', 'dangling_cleanup', 'post_backtrack_acute',
                                    'sliver_cleanup', 'score', 'fab_check', 'foreign_check'])
def test_transaction_keeps_immediately_preceding_input_not_baseline(tmp_path, monkeypatch, fail_step):
    board, _ = fixture(tmp_path)
    baseline = board.read_bytes()
    metrics = dict(drc=0, unconnected=1, kelvin_ok=True, diffpair_ok=True,
                   route_blocking=0, route_advisory=0, objective=1.)
    fab = dict(fab_blocking=0, fab_drc=0, fab_unconnected=1)
    foreign = dict(foreign_status='ok', foreign_blocking=0)
    observations = []

    def worker(step, result):
        def run(path, **_kwargs):
            path = Path(path)
            if path == board:
                return dict(result)
            if step == fail_step:
                observations.append(path.read_bytes())
                path.write_bytes(b'partially overwritten by failing step')
                raise repair.NativeWorkerFailure(step, subprocess.CompletedProcess(
                    ['test-native-worker', step], -11, stdout='entered ' + step, stderr='fault'))
            if step in ('repair', 'dangling_cleanup', 'post_backtrack_acute', 'sliver_cleanup'):
                path.write_bytes(path.read_bytes() + ('/' + step).encode())
            return dict(result)
        return run

    for name, step, result in (
        ('_repair_isolated', 'repair', {'backtracks': 1}),
        ('_dangling_cleanup_isolated', 'dangling_cleanup', {}),
        ('_post_backtrack_acute_isolated', 'post_backtrack_acute', {}),
        ('_sliver_repair_isolated', 'sliver_cleanup', {}),
        ('_score_isolated', 'score', metrics), ('_fab_isolated', 'fab_check', fab),
        ('_foreign_isolated', 'foreign_check', foreign)):
        monkeypatch.setattr(repair, name, worker(step, result))
    monkeypatch.setattr(replay, 'engine_signature', lambda _: {'fixture': 'stable'})
    report = repair.repair_admitted(str(board), allow_locked_track_uuids=('owned',))
    failed = [row for row in report['variants'] if 'error' in row]
    assert len(failed) == len(observations) and failed
    for row, expected in zip(failed, observations):
        assert not row['safe']
        directory = Path(row['failure_evidence']['directory'])
        record = replay.verify(directory, engine={'fixture': 'stable'})
        assert (directory / record['board']).read_bytes() == expected
        assert record['context']['step'] == fail_step
        assert json.loads((directory / 'generated-track-uuids.json').read_text()) == ['owned']
    assert board.read_bytes() == baseline and not report['adopted']
    assert not list(tmp_path.glob('.cec-fab-admit-*'))


def test_success_keeps_no_capsule(tmp_path, monkeypatch):
    board, _ = fixture(tmp_path)
    metrics = dict(drc=0, unconnected=0, kelvin_ok=True, diffpair_ok=True,
                   route_blocking=0, route_advisory=0, objective=1.)
    monkeypatch.setattr(repair, '_score_isolated', lambda _: dict(metrics))
    monkeypatch.setattr(repair, '_fab_isolated', lambda _: dict(fab_blocking=0, fab_drc=0, fab_unconnected=0))
    monkeypatch.setattr(repair, '_foreign_isolated', lambda _: dict(foreign_status='ok', foreign_blocking=0))
    monkeypatch.setattr(repair, '_repair_isolated', lambda *args, **kwargs: {})
    monkeypatch.setattr(repair, '_sliver_repair_isolated', lambda *args, **kwargs: {})
    result = repair.repair_admitted(str(board))
    assert not result['adopted'] and not (tmp_path / '.cec-fab-failures').exists()


def test_real_native_child_crash_preserves_original_loadable_input(tmp_path):
    import pcbnew
    board = tmp_path / 'native.kicad_pcb'
    native = pcbnew.CreateEmptyBoard()
    track = pcbnew.PCB_TRACK(native)
    track.SetStart(pcbnew.VECTOR2I_MM(5, 4))
    track.SetEnd(pcbnew.VECTOR2I_MM(7, 4))
    track.SetLayer(pcbnew.B_Cu)
    track.SetWidth(pcbnew.FromMM(.2))
    native.Add(track)
    pcbnew.SaveBoard(str(board), native, True)
    snapshot = replay.capture(board)
    code = '''import os,resource,signal,sys
import pcbnew
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
board=pcbnew.LoadBoard(sys.argv[1])
assert board is not None
open(sys.argv[1],'w').write('partial failed save')
print('loaded native input',flush=True)
os.kill(os.getpid(),signal.SIGSEGV)
'''
    process = subprocess.run([sys.executable, '-X', 'faulthandler', '-c', code, str(board)],
        capture_output=True, text=True, timeout=10)
    assert process.returncode == -11
    assert 'Segmentation fault' in process.stderr
    evidence = replay.retain(snapshot, tmp_path / 'store', context={'step': 'native-test'},
        error=repair.NativeWorkerFailure('native-test', process), engine={})
    record = replay.verify(evidence['directory'], engine={})
    restored = Path(evidence['directory']) / record['board']
    loaded = pcbnew.LoadBoard(str(restored))
    assert len(list(loaded.GetTracks())) == 1
    assert next(iter(loaded.GetTracks())).GetEnd() == pcbnew.VECTOR2I_MM(7, 4)
    assert 'loaded native input' in record['failure']['stdout']
