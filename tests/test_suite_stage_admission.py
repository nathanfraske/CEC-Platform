from cec_board_suite import stage_summary
import pytest


def test_status_projection_and_mutation_gate_coexist():
    import cec_stage_admission as admission
    before = {'drc': 0, 'unconnected': 1, 'unconn_nets': ['/SIGNAL'],
              'kelvin_ok': True, 'diffpair_ok': True}
    after = {**before, 'unconnected': 0, 'unconn_nets': []}
    assert admission.accepts(before, after, require_strict=True)[0]
    assert admission.admission_ok({'ok': True, 'admission_gate': False}) is False
    assert admission.label({'ok': True, 'admission_gate': False}) == 'BLOCK'


def test_execution_complete_does_not_imply_admission():
    row = stage_summary({'status':'complete', 'result':{'ok':False, 'reason':'no corridor'}})
    assert row['status'] == 'blocked'
    assert row['execution_status'] == 'complete'
    assert row['admission_ok'] is False
    assert row['reason'] == 'no corridor'


def test_missing_or_running_evidence_is_not_a_pass():
    for record in ({'status':'complete'}, {'status':'running'}, {'status':'failed','error':'bad'}):
        assert stage_summary(record)['admission_ok'] is None
    assert stage_summary({'status':'complete','result':{'ok':True}})['admission_ok'] is True


def test_completed_analysis_does_not_override_explicit_admission_refusal():
    row = stage_summary({'status': 'complete', 'result': {
        'ok': True, 'admission_gate': False, 'report': 'evidence.json'}})
    assert row['execution_status'] == 'complete'
    assert row['status'] == 'blocked'
    assert row['admission_ok'] is False


def test_journal_prints_and_saves_admission_separately(tmp_path, capsys):
    import json
    from cec_full_pipeline import StageJournal
    path = tmp_path / 'state.json'
    journal = StageJournal(path, 'synthetic-board')
    raw = journal.run('synthetic-analysis', 'input-digest', lambda: {
        'ok': True, 'admission_gate': False})
    assert raw == {'ok': True, 'admission_gate': False}
    row = json.loads(path.read_text())['stages']['synthetic-analysis']
    assert row['status'] == 'complete'
    assert row['admission_ok'] is False
    output = capsys.readouterr().out
    assert 'BLOCK' in output and 'PASS' not in output


@pytest.mark.parametrize('result,expected', [
    ({'ok': True, 'admission_gate': True}, True),
    ({'ok': False, 'admission_gate': True}, False),
    ({'ok': True, 'admission_gate': False}, False),
    ({'admission_gate': True}, None), ({}, None), (None, None),
    ({'ok': True, 'admission_gate': None}, None),
    ({'ok': True, 'admission_gate': 'true'}, None),
    ({'ok': True, 'admission_gate': 1}, None),
    ({'ok': 1}, None),
])
def test_shared_outcome_requires_explicit_boolean_evidence(result, expected):
    from cec_stage_admission import admission_ok
    assert admission_ok(result) is expected


def test_running_analysis_cannot_publish_early_admission():
    assert stage_summary({'status': 'running', 'result': {
        'ok': True, 'admission_gate': True}})['admission_ok'] is None


@pytest.mark.parametrize('field', ['reason', 'status'])
def test_budget_failure_projection_keeps_its_causal_reason(field):
    row = stage_summary({'status': 'timed_out', 'failure_evidence': {
        field: 'campaign_budget_exhausted'}})
    assert row['admission_ok'] is None
    assert row['reason'] == 'campaign_budget_exhausted'


def test_resumed_refusal_keeps_raw_evidence_and_is_never_printed_pass(tmp_path, capsys):
    from cec_full_pipeline import StageJournal
    artifact = tmp_path / 'evidence.json'
    artifact.write_text('{}')
    journal = StageJournal(tmp_path / 'state.json', 'renamed-fixture')
    raw = {'ok': True, 'admission_gate': False}
    journal.run('any-analysis', 'digest', lambda: {**raw, '_artifacts': [artifact]})
    capsys.readouterr()
    def should_not_run():
        raise AssertionError('unchanged evidence should resume')
    assert journal.run('any-analysis', 'digest', should_not_run) == raw
    output = capsys.readouterr().out
    assert 'RESUME-BLOCK' in output and 'PASS' not in output
