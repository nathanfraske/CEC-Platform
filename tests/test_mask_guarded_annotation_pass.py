"""A rejected synthetic next child must not erase the last received child."""
import copy
import json
from types import SimpleNamespace
import pytest
import root_run_mask_guarded_bounded_reference_pass_20261020 as runner
import cec_reference_mask_obstacles as masks
from test_bounded_reference_pass_intake import evidence


@pytest.mark.parametrize('fault', ['opens', 'new_native', 'incomplete', 'errors'])
def test_refused_next_child_is_bounded_and_last_received_child_is_retained(tmp_path, monkeypatch, fault):
    initial, board, report = evidence(tmp_path, monkeypatch)
    report.write_text(json.dumps(dict(synthetic_fixture=True, violations=[dict(type='synthetic')])) )
    initial['native_producer']['report_sha256'] = runner.force._hash(report)
    initial.update(source=str(board), source_sha256=runner.force._hash(board), source_raw_native_count=2,
        proposal=dict(board_hint='explicit_synthetic_orchestration_only', records=[dict(reference='X77')]))
    start = tmp_path/'start-stage.json'; start.write_text(json.dumps(initial))
    out = tmp_path/'pass'
    monkeypatch.setattr(masks, 'observe', lambda *a: dict(ok=True, complete=True))
    calls = []
    def refused(command, **kwargs):
        calls.append(command)
        target = runner.Path(command[command.index('--out')+1]); target.mkdir()
        bad = copy.deepcopy(initial)
        bad['proposal']['records'] = [dict(reference='X88')]
        if fault == 'opens': bad['opens'] = 1
        elif fault == 'new_native': bad['new_native_faults'] = [dict(synthetic_new_fault=True)]
        elif fault == 'incomplete': bad['complete'] = False
        else: bad['errors'] = ['synthetic_rejection']
        (target/'stage.json').write_text(json.dumps(bad))
        return SimpleNamespace(returncode=0, stdout='synthetic worker rejected next child', stderr='')
    monkeypatch.setattr(runner.subprocess, 'run', refused)
    monkeypatch.setattr(runner.sys, 'argv', ['synthetic-bounded-pass', '--start-stage', str(start),
        '--out', str(out), '--reporting-build', 'synthetic-unused', '--additional-cohorts', '3'])
    before = board.read_bytes(); runner.main()
    saved = json.loads((out/'pass.json').read_text())
    assert len(calls) == 1 and saved['ok'] and saved['complete']
    assert saved['stop_reason'] == 'next_annotation_rejected_last_received_child_retained'
    assert saved['stages'] == [str(start)] and saved['represented_references'] == ['X77']
    assert saved['candidate'] == str(board) and not saved['attempts'][0]['accepted']
    assert before == board.read_bytes() and not saved['fab_ready'] and not saved['release_authority']
