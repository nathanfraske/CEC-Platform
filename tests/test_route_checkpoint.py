"""Crash/identity/storage guards and real coordinator timeout handoff."""
import json
import multiprocessing
import os
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

import cec_route_checkpoint as checkpoint
import cec_full_pipeline as pipeline


def copy_family(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    project = target.with_suffix('.kicad_pro')
    project.write_text('{"rules":"unchanged"}')
    return [target, project]


def kill_during_copy(root, source):
    store = checkpoint.Store(root, context={'family': 'synthetic'}, sources=[source])
    def interrupted(a, b):
        b.write_text('partial')
        os._exit(23)
    store.publish(source, stage='detailed_route', rank=[0, 1], copier=interrupted)


@pytest.fixture
def store(tmp_path):
    source = tmp_path / 'input.kicad_pcb'
    source.write_text('board')
    item = checkpoint.Store(tmp_path / 'checkpoints', context={'family': 'synthetic'},
                            sources=[source])
    return item, source


def publish(store, source, opens=9):
    return store.publish(source, stage='pre_power_signal_access', rank=[0, opens],
                         copier=copy_family)


def test_two_slots_bound_history_and_refuse_non_improvement(store):
    item, source = store
    for opens in range(9, 3, -1):
        assert publish(item, source, opens)['published']
    assert not publish(item, source, 7)['published']
    records, errors = checkpoint.committed(item.root, context=item.context)
    assert not errors
    assert [r['rank'] for r in records] == [[0, 4], [0, 5]]
    assert len(list(item.root.glob('*/board.kicad_pcb'))) == 2
    assert all(r['release_accepted'] is False and r['routing_admitted'] is False for r in records)


def test_actual_killed_writer_preserves_prior_committed_family(store):
    item, source = store
    previous = publish(item, source)
    process = multiprocessing.get_context('spawn').Process(
        target=kill_during_copy, args=(str(item.root), str(source)))
    process.start()
    process.join(10)
    if process.is_alive():
        process.kill()
        process.join(2)
        pytest.fail('synthetic interrupted writer did not exit within its budget')
    assert process.exitcode == 23
    records, errors = checkpoint.committed(item.root, context=item.context)
    assert not errors and len(records) == 1
    assert records[0]['board'] == previous['board']
    assert checkpoint.sha(records[0]['board']) == previous['sha256']


@pytest.mark.parametrize('target', ['board.kicad_pcb', 'board.kicad_pro', 'checkpoint.json'])
def test_tampered_artifact_never_becomes_a_candidate(store, target):
    item, source = store
    record = publish(item, source)
    (Path(record['board']).parent / target).write_text('{}')
    records, errors = checkpoint.committed(item.root, context=item.context)
    assert not records and errors


def test_source_changed_or_wrong_context_refuses_old_receipt(store):
    item, source = store
    publish(item, source)
    with pytest.raises(ValueError, match='identity'):
        checkpoint.committed(item.root, context={'family': 'other'})
    source.write_text('changed source')
    records, errors = checkpoint.committed(item.root, context=item.context)
    assert not records and errors


def test_pointer_traversal_is_refused(store):
    item, source = store
    publish(item, source)
    pointer = item.root / 'current.json'
    data = json.loads(pointer.read_text())
    data['committed'][0]['slot'] = '../outside'
    pointer.write_text(json.dumps(data))
    records, errors = checkpoint.committed(item.root, context=item.context)
    assert not records and errors


def test_symlink_store_and_unowned_directory_are_not_adopted(tmp_path):
    source = tmp_path / 'input'; source.write_text('source')
    outside = tmp_path / 'outside'; outside.mkdir()
    link = tmp_path / 'link'; link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        checkpoint.Store(link, context={}, sources=[source])
    (outside / 'user-data').write_text('keep')
    with pytest.raises(ValueError, match='nonempty'):
        checkpoint.Store(outside, context={}, sources=[source])
    assert (outside / 'user-data').read_text() == 'keep'


def test_oversized_copy_cannot_replace_previous_or_leave_large_files(store):
    item, source = store
    prior = publish(item, source)
    item.max_family_bytes = 10
    with pytest.raises(ValueError, match='storage bound'):
        publish(item, source, 3)
    records, errors = checkpoint.committed(item.root, context=item.context)
    assert not errors and records[0]['board'] == prior['board']
    assert not list((item.root / 'slot-1').glob('*.kicad*'))


@pytest.mark.parametrize('rank', [[-1, 3], [0, float('nan')], [False, 2], [1], [0, 1.5]])
def test_missing_or_nonfinite_native_metrics_refused(store, rank):
    item, source = store
    with pytest.raises(ValueError, match='measured counts'):
        item.publish(source, stage='detailed_route', rank=rank, copier=copy_family)


def test_publisher_does_not_snapshot_failures_or_arbitrary_temporary_files(tmp_path):
    callback = checkpoint.publisher(tmp_path / 'unused', None, 'absent', 0)
    assert callback(stage='detailed_route', status='failed', artifact='absent') is None
    assert callback(stage='random-stage', status='passed', artifact='absent') is None
    assert not (tmp_path / 'unused').exists()


@pytest.mark.parametrize('library,nets,expected', [
    ('Fiducial:Fiducial_1mm', [0], True),
    ('Fiducial:Fiducial_1mm', [2], False),
    ('Capacitor:C_0402', [0], False)])
def test_only_real_non_electrical_marks_are_movable(library, nets, expected):
    footprint = SimpleNamespace(GetFPIDAsString=lambda: library,
        Pads=lambda: [SimpleNamespace(GetNetCode=lambda net=net: net) for net in nets])
    assert checkpoint.optical_mark(footprint) is expected


@pytest.mark.parametrize('preserved', [True, False])
def test_coordinator_recovers_only_freshly_graded_preserved_checkpoint(tmp_path, monkeypatch, preserved):
    import cec_score
    import cec_synth_pipeline as synth
    import cec_operation_budget
    from route_candidate_test_support import run_candidate_in_process
    monkeypatch.setattr(cec_operation_budget, 'run', run_candidate_in_process)
    source = tmp_path / 'source.kicad_pcb'; source.write_text('9')
    partial = tmp_path / 'partial.kicad_pcb'; partial.write_text('4')
    out = tmp_path / 'route'
    cfg = SimpleNamespace(board='synthetic-family', params={'automatic_pin_escape_tier': True})
    monkeypatch.delenv('CEC_JOB_DEADLINE_EPOCH', raising=False)
    monkeypatch.delenv('CEC_OPERATION_DEADLINE_EPOCH', raising=False)
    monkeypatch.setattr(pipeline, '_route_params_for_board', lambda *_: dict(cfg.params))
    monkeypatch.setattr(pipeline, '_source_files', lambda *_: [source])
    monkeypatch.setattr(pipeline, '_copy_sidecars', lambda a,b,**_: copy_family(Path(a), Path(b)))
    monkeypatch.setattr(synth, 'config_with_board_route_authority', lambda c,p: (c, {}))
    monkeypatch.setattr(cec_score, 'score', lambda p: SimpleNamespace(drc=0, unconnected=int(Path(p).read_text())))
    monkeypatch.setattr(checkpoint, 'preservation', lambda *_: {'ok': preserved})
    monkeypatch.setattr(checkpoint, 'assembly_normalize', lambda p,*_: (p, {'changed':False}))
    monkeypatch.setattr(checkpoint, 'normalize_complete_pair_additions', lambda parent,p,*_: (p, {'changed':False}))
    graded = []
    def grade(board, work, _cfg, **_):
        board = Path(board)
        if board == source:
            return None
        graded.append(str(board))
        target = Path(work) / 'incumbent' / 'board.kicad_pcb'
        copy_family(board, target)
        return dict(routed=str(target), seed=2, gate=False, sort_key=[1, 4],
                    drc=0, unconnected=4, gate_terms={'routing_complete':False})
    monkeypatch.setattr(pipeline, '_grade_route_incumbent', grade)
    def killed_route(*_, **kw):
        saved = kw['checkpoint'](stage='pre_power_signal_access', status='passed', artifact=partial)
        assert saved['published']
        raise TimeoutError('synthetic post-stage budget exhausted')
    monkeypatch.setattr(synth, 'route_oracle_grade', killed_route)
    if preserved:
        result = pipeline._route_stage(source, out, cfg, passes=1, opt=1, seed=2, timeout=1, thermal='lazy')
        assert result['winner_origin'] == 'route_checkpoint'
        assert result['unconnected'] == 4 and not result['ok']
        assert Path(result['board']).read_text() == '4'
        assert result['fab_repair']['skipped'] == 'retained_checkpoint_resume_pending'
    else:
        with pytest.raises(pipeline.PipelineBlocked):
            pipeline._route_stage(source, out, cfg, passes=1, opt=1, seed=2, timeout=1, thermal='lazy')
    assert len(graded) == 1
    report = json.loads((out / 'candidate-summary.json').read_text())
    assert report['candidates'][0]['unconnected'] is None
    assert report['candidates'][0]['incumbent_gate_regressions'] is None
    assert 'TimeoutError' in report['candidates'][0]['blocker_evidence']['operation_failure']['log_tail']


def test_zone_contract_ignores_only_generated_object_identity():
    row = ('id-one','RAIL','power',False,(0,2),(((1,2),(3,4)),))
    same = ('id-two', *row[1:])
    assert checkpoint.physical_zones([row], {'RAIL'}) == checkpoint.physical_zones([same], {'RAIL'})
    for altered in [(*row[:4], (0,4), row[5]),
                    (*row[:5], (((1,2),(9,9)),)),
                    (row[0], 'OTHER', *row[2:])]:
        assert checkpoint.physical_zones([row], {'RAIL'}) != checkpoint.physical_zones([altered], {'RAIL'})


@pytest.mark.parametrize('preserved', [True, False])
def test_pair_addition_cleanup_keeps_source_copper_and_native_registry(tmp_path, monkeypatch, preserved):
    import gc
    import pcbnew
    import cec_fr, cec_placement_route_prefix as pairs
    source = tmp_path / 'source.kicad_pcb'
    candidate = tmp_path / 'candidate.kicad_pcb'
    board = pcbnew.BOARD()
    nets = {}
    for index, name in enumerate(('/DIFFERENT_P', '/DIFFERENT_N', '/OTHER'), 1):
        nets[name] = pcbnew.NETINFO_ITEM(board, name, index)
        board.Add(nets[name])
    def via(name, x):
        item = pcbnew.PCB_VIA(board)
        item.SetNet(nets[name])
        item.SetPosition(pcbnew.VECTOR2I(x*1000000, 2000000))
        item.SetWidth(600000)
        item.SetDrill(300000)
        item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(item)
    via('/DIFFERENT_P', 1)
    pcbnew.SaveBoard(str(source), board)
    via('/DIFFERENT_P', 2)
    via('/DIFFERENT_N', 3)
    via('/OTHER', 4)
    pcbnew.SaveBoard(str(candidate), board)
    before = (source.read_bytes(), candidate.read_bytes())
    monkeypatch.setattr(pairs, 'capture', lambda _: {'qualified_critical_pairs': [
        {'qualified':True, 'p':'/DIFFERENT_P', 'n':'/DIFFERENT_N'}]})
    monkeypatch.setattr(pairs, 'check_qualified_pairs', lambda *_: {'ok':False})
    monkeypatch.setattr(checkpoint, 'preservation', lambda *_: {'ok':preserved})
    monkeypatch.setattr(cec_fr, 'refill_zones_isolated', lambda _: True)
    cfg = SimpleNamespace(params={}, dir=str(tmp_path), board='synthetic-family')
    if preserved:
        target, report = checkpoint.normalize_complete_pair_additions(
            source, candidate, tmp_path / 'out', cfg)
        assert report['changed'] and len(report['removed']) == 2
    else:
        with pytest.raises(ValueError, match='native continuation admission'):
            checkpoint.normalize_complete_pair_additions(source, candidate, tmp_path / 'out', cfg)
        target = tmp_path / 'out' / 'board.kicad_pcb'
    gc.collect()
    reloaded = pcbnew.LoadBoard(str(target))
    assert isinstance(reloaded, pcbnew.BOARD)
    assert sorted((t.GetNetname(), t.GetPosition().x) for t in reloaded.GetTracks()) == [
        ('/DIFFERENT_P', 1000000), ('/OTHER', 4000000)]
    assert before == (source.read_bytes(), candidate.read_bytes())
