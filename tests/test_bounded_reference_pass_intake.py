"""Synthetic provenance mutants, not hardware or manufacturing evidence."""
import copy
import json
from pathlib import Path
import pytest
import root_run_bounded_dense_reference_pass_20261020 as runner


def evidence(tmp_path, monkeypatch):
    epoch = {'synthetic_annotation_intake_only': True}
    monkeypatch.setattr(runner.force, '_code_identity', lambda: epoch)
    board = tmp_path/'fixture.kicad_pcb'
    board.write_text('SYNTHETIC PROVENANCE FIXTURE, NOT A HARDWARE BOARD')
    report = tmp_path/'native.json'
    report.write_text(json.dumps({'synthetic_fixture': True}))
    digest = runner.force._hash(board)
    stage = dict(ok=True, complete=True, changed=True, errors=[], opens=0, new_native_faults=[],
        candidate=str(board), candidate_sha256=digest, code_identity=epoch,
        native_producer=dict(ok=True, complete=True,
            native_inventory=dict(potentially_truncated=False), report=str(report),
            report_sha256=runner.force._hash(report), source_files={str(board): digest}))
    return stage, board, report


def test_native_only_intake_is_source_bound_but_never_a_full_board_grade(tmp_path, monkeypatch):
    stage, board, _ = evidence(tmp_path, monkeypatch)
    original = copy.deepcopy(stage)
    before = board.read_bytes()
    result = runner.native_only_grade(stage)
    assert result['native_only_annotation_intake'] and not result['full_board_grade']
    assert not result['fab_ready'] and not result['release_authority']
    assert result['boards']['candidate']['sha256'] == runner.force._hash(board)
    assert result['boards']['candidate']['native_producer'] == stage['native_producer']
    assert original == stage and before == board.read_bytes()


@pytest.mark.parametrize('fault', ['stage_ok', 'stage_complete', 'stage_changed', 'stage_errors',
    'stage_opens', 'stage_new_native', 'board_hash', 'board_bytes', 'epoch', 'native_ok',
    'native_complete', 'truncated', 'report_hash', 'report_bytes', 'source_files',
    'missing_board_binding', 'source_missing', 'report_missing'])
def test_false_stale_incomplete_or_unbound_native_intake_never_advances(tmp_path, monkeypatch, fault):
    stage, board, report = evidence(tmp_path, monkeypatch)
    native = stage['native_producer']
    if fault in ('stage_ok', 'stage_complete', 'stage_changed'):
        stage[fault.removeprefix('stage_')] = False
    elif fault == 'stage_errors': stage['errors'] = ['fixture_failure']
    elif fault == 'stage_opens': stage['opens'] = 1
    elif fault == 'stage_new_native': stage['new_native_faults'] = ['fixture_new_fault']
    elif fault == 'board_hash': stage['candidate_sha256'] = '0'*64
    elif fault == 'board_bytes': board.write_text('CHANGED SYNTHETIC FIXTURE')
    elif fault == 'epoch': stage['code_identity'] = {}
    elif fault == 'native_ok': native['ok'] = False
    elif fault == 'native_complete': native['complete'] = False
    elif fault == 'truncated': native['native_inventory']['potentially_truncated'] = True
    elif fault == 'report_hash': native['report_sha256'] = '0'*64
    elif fault == 'report_bytes': report.write_text('CHANGED SYNTHETIC REPORT')
    elif fault == 'source_files': native['source_files'] = {str(report): '0'*64}
    elif fault == 'missing_board_binding': native['source_files'] = {str(report): runner.force._hash(report)}
    elif fault == 'source_missing': native['source_files'] = {str(tmp_path/'not-present'): '0'*64}
    elif fault == 'report_missing': native['report'] = str(tmp_path/'not-present.json')
    else: raise AssertionError(fault)
    with pytest.raises((ValueError, OSError)):
        runner.native_only_grade(stage)
