"""Crash/recovery contracts use synthetic families, not board-specific poses."""
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest import mock

import pytest
import cec_placement_checkpoint as cp


def fixture(tmp_path, family='synthetic-alpha'):
    authority = tmp_path / 'source.kicad_sch'
    authority.write_text('current schematic')
    board = tmp_path / 'work.kicad_pcb'
    board.write_text('authored copper before residual routing')
    board.with_suffix('.kicad_pro').write_text('current design rules')
    store = cp.Store(tmp_path / 'checkpoints', family=family, sources=[authority])
    return store, board, authority


def copy_family(source, destination):
    shutil.copy2(source, destination)
    shutil.copy2(source.with_suffix('.kicad_pro'), destination.with_suffix('.kicad_pro'))
    return [destination, destination.with_suffix('.kicad_pro')]


def publish(store, board, rank=10, **kw):
    args = dict(phase='seed', rank=[rank], context={'pins': {}, 'outline_mm': [20, 30]},
                copier=copy_family, validate=lambda p: {'ok': True})
    args.update(kw)
    return store.publish(board, **args)


@pytest.mark.parametrize('family', ['synthetic-alpha', 'unrelated-beta'])
def test_two_slot_recovery_is_monotonic_bounded_and_not_admission(tmp_path, family):
    store, board, authority = fixture(tmp_path, family)
    original = board.read_bytes()
    for i in range(10, 0, -1):
        row = publish(store, board, i)
        assert row['published']
        assert cp.read_current(store.root, expected_family=family)['rank'] == [i]
    assert not publish(store, board, 20)['published']
    row = publish(store, board, 99, phase='preflight')
    assert row['published']  # stronger measurement phase replaces proxy evidence
    assert not row['routing_admitted'] and not row['release_accepted']
    assert not publish(store, board, 0, phase='seed')['published']
    assert len(list(store.root.glob('slot-*/board.kicad_pcb'))) == 2
    assert sum(p.stat().st_size for p in store.root.rglob('*') if p.is_file()) < 15000
    assert board.read_bytes() == original


@pytest.mark.parametrize('family', ['synthetic-alpha', 'unrelated-beta'])
def test_craft_commit_survives_process_death_without_route_admission(tmp_path, family):
    import os
    import subprocess
    import sys
    store, board, authority = fixture(tmp_path, family)
    publish(store, board, 10, phase='selected')
    code = '''
import os, shutil, sys
from pathlib import Path
import cec_placement_checkpoint as cp
root, family, source, board = sys.argv[1:]
board = Path(board)
store = cp.Store(root, family=family, sources=[source])
def copier(source, destination):
    shutil.copy2(source, destination)
    shutil.copy2(source.with_suffix('.kicad_pro'), destination.with_suffix('.kicad_pro'))
    return [destination, destination.with_suffix('.kicad_pro')]
row = store.publish(board, phase='craft', rank=[0, 1],
    context={'pins': {}, 'outline_mm': [20, 30]}, copier=copier,
    validate=lambda p: {'ok': True})
assert row['published']
os._exit(73)
'''
    board.write_text('certified craft fixture, not actual copper evidence')
    environment = {**os.environ, 'PYTHONPATH': str(Path(cp.__file__).parent)}
    result = subprocess.run([sys.executable, '-c', code, str(store.root), family,
                             str(authority), str(board)], env=environment, timeout=10)
    assert result.returncode == 73
    recovered = cp.read_current(store.root, expected_family=family)
    assert recovered['phase'] == 'craft' and recovered['rank'] == [0, 1]
    assert Path(recovered['board']).read_bytes() == board.read_bytes()
    assert not recovered['routing_admitted'] and not recovered['release_accepted']
    assert not publish(store, board, 0, phase='selected')['published']
    assert publish(store, board, 9, phase='placement')['published']


@pytest.mark.parametrize('failure', ['copy', 'certificate', 'pointer'])
def test_interrupted_commit_keeps_previous_complete_artifact_family(tmp_path, failure):
    store, board, _ = fixture(tmp_path)
    first = publish(store, board)
    board.write_text('new candidate')
    original_json = cp.atomic_json

    def write(path, data):
        if ((failure == 'certificate' and path.name.endswith('.placement-checkpoint.json'))
                or (failure == 'pointer' and path.name == 'current.json')):
            raise OSError('injected interruption')
        original_json(path, data)

    def interrupted_copy(source, destination):
        shutil.copy2(source, destination)
        raise OSError('interrupted between board and rule sidecar')

    with mock.patch.object(cp, 'atomic_json', side_effect=write), pytest.raises(OSError):
        publish(store, board, 9, copier=interrupted_copy if failure == 'copy' else copy_family)
    current = cp.read_current(store.root)
    assert current['sha256'] == first['sha256']
    assert Path(current['board']).with_suffix('.kicad_pro').read_text() == 'current design rules'
    # A new coordinator can recover and overwrite only the incomplete slot.
    recovered = cp.Store(store.root, family=store.family, sources=[tmp_path/'source.kicad_sch'])
    assert publish(recovered, board, 8)['published']


@pytest.mark.parametrize('defect', ['board', 'project', 'missing', 'source', 'family', 'path', 'pointer'])
def test_corrupt_or_stale_work_is_never_resumable(tmp_path, defect):
    store, board, authority = fixture(tmp_path)
    row = publish(store, board)
    saved = Path(row['board'])
    if defect == 'board': saved.write_text('changed copper')
    if defect == 'project': saved.with_suffix('.kicad_pro').write_text('weakened rules')
    if defect == 'missing': saved.with_suffix('.kicad_pro').unlink()
    if defect == 'source': authority.write_text('changed schematic')
    if defect == 'path': (store.root/'current.json').write_text(json.dumps({'slot':'../escape'}))
    if defect == 'pointer': (store.root/'current.json').write_text('{}')
    with pytest.raises((ValueError, OSError)):
        cp.read_current(store.root, expected_family='wrong' if defect == 'family' else store.family)


def test_refuses_unowned_directory_symlink_and_failed_intake_without_mutation(tmp_path):
    store, board, authority = fixture(tmp_path)
    owned = tmp_path / 'user-files'
    owned.mkdir()
    sentinel = owned / 'keep.txt'
    sentinel.write_text('user data')
    with pytest.raises(ValueError, match='unowned'):
        cp.Store(owned, family=store.family, sources=[authority])
    assert sentinel.read_text() == 'user data'
    with pytest.raises(ValueError, match='intake'):
        publish(store, board, validate=lambda p: {'ok': False})
    assert not (store.root / 'current.json').exists()
    (store.root/'slot-0').symlink_to(owned, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        publish(store, board)
    assert sentinel.exists()


def test_source_checked_checkpoint_is_distinct_from_unknown_routed_board(tmp_path):
    import cec_full_pipeline as pipeline
    store, board, authority = fixture(tmp_path)
    assert pipeline._placement_stage_artifact_provenance(board) is None
    row = publish(store, board)
    saved = Path(row['board'])
    proof = pipeline._placement_stage_artifact_provenance(saved)
    assert proof['kind'] == 'pipeline_placement_work' and not proof['routing_admitted']
    # Even a nearby weaker journal must not resurrect a tampered checkpoint.
    saved.with_suffix('.kicad_pro').write_text('changed project')
    (saved.parent/'pipeline-state.json').write_text(json.dumps({'stages':{'placement':{
        'artifacts':[{'path':str(saved),'sha256':cp.sha(saved)}]}}}))
    with pytest.raises(ValueError, match='artifact'):
        pipeline._placement_stage_artifact_provenance(saved)


def test_checkpoint_is_published_before_exact_route_probe(tmp_path):
    import cec_synth_pipeline as synth
    store, board, _ = fixture(tmp_path)
    cfg = SimpleNamespace(params={})
    cand = SimpleNamespace(strat='synthetic', seed=0, residual=0,
                           corridor_cross_aware=0, corridor_cross=0, proxy={'hpwl':1},
                           route_preflight={})
    events = []

    def materialize(candidate, owner, path):
        copy_family(board, Path(path))

    def checkpoint(candidate, owner, path, **kw):
        events.append(kw['phase'])
        publish(store, Path(path), phase=kw['phase'], rank=kw['rank'][0])

    def interrupted_probe(payload):
        assert cp.read_current(store.root)['phase'] == 'seed'
        events.append('interrupted-native-probe')
        raise KeyboardInterrupt('simulated coordinator termination')

    with mock.patch.object(synth, 'materialize', side_effect=materialize), \
         mock.patch.object(synth, '_route_authority_digest', return_value='unique-work-checkpoint'), \
         mock.patch.object(synth, '_route_preflight_worker_count', return_value=1), \
         mock.patch.object(synth, '_route_authority_analyze', side_effect=interrupted_probe), \
         pytest.raises(KeyboardInterrupt):
        synth.rerank_route_preflight(cfg, [cand], topk=1, checkpoint=checkpoint)
    assert events == ['seed', 'interrupted-native-probe']
    assert Path(cp.read_current(store.root)['board']).is_file()


def test_review_uses_checkpoint_and_does_not_call_it_journaled(tmp_path):
    import cec_pass_review as review
    target = tmp_path / 'attempt'
    source = tmp_path / 'source.sch'
    source.write_text('current')
    board = tmp_path / 'work.kicad_pcb'
    board.write_text('seed')
    board.with_suffix('.kicad_pro').write_text('rules')
    store = cp.Store(target/'02-placement/checkpoints', family='synthetic', sources=[source])
    row = publish(store, board)
    state = {'board':'synthetic', 'stages':{'placement':{'status':'timed_out'}}}
    path, stage, verified = review.select_output(target, state)
    assert path == Path(row['board']) and stage == 'placement-checkpoint:seed' and not verified
    path.with_suffix('.kicad_pro').write_text('corrupted')
    with pytest.raises(ValueError, match='refusing fallback'):
        review.select_output(target, state)


@pytest.mark.parametrize('outcome', ['accepted', 'inner_rejected', 'outer_rejected'])
def test_only_outer_accepted_repair_can_publish_a_new_work_checkpoint(tmp_path, outcome):
    import cec_synth_pipeline as synth
    base = SimpleNamespace(route_preflight={'critical_pair_refused_count': 3},
        residual=0, corridor_cross=0, corridor_cross_aware=0, proxy={'hpwl': 1}, P={})
    candidate = SimpleNamespace(route_preflight={'critical_pair_refused_count':
                                                4 if outcome == 'outer_rejected' else 2},
        residual=0, corridor_cross=0, corridor_cross_aware=0, proxy={'hpwl': 1}, P={})
    cfg = SimpleNamespace(params={})
    callback = mock.Mock()
    def materialize(cand, owner, path):
        Path(path).write_text('accepted native artifact')
    with mock.patch.object(synth, 'repair_route_preflight', return_value=(candidate,
            {'accepted': outcome != 'inner_rejected'})), \
         mock.patch.object(synth, 'materialize', side_effect=materialize):
        selected, report = synth.repair_route_preflight_iterative(
            cfg, base, rounds=1, checkpoint=callback)
    assert callback.call_count == (1 if outcome == 'accepted' else 0)
    assert (selected is candidate) == (outcome == 'accepted')


def test_oversized_sidecar_cannot_accumulate_or_replace_incumbent(tmp_path):
    store, board, _ = fixture(tmp_path)
    first = publish(store, board)
    store.max_family_bytes = 100
    board.with_suffix('.kicad_pro').write_text('x' * 200)
    with pytest.raises(ValueError, match='bounded storage'):
        publish(store, board, 1)
    assert cp.read_current(store.root)['sha256'] == first['sha256']
    assert not list((store.root/'slot-1').glob('*'))
