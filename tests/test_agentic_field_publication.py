"""A full current semantic audit supersedes, but never destroys, old evidence."""
import importlib.util
import json
from pathlib import Path

import pytest

from cec_pipeline import checkpoint, fields


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'cec_publish_agentic_review_test', ROOT/'ops'/'cec_publish_agentic_review.py')
publication = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publication)


def valid_report():
    report = dict(complete=True, ok=True, applicable=False,
                  audit_basis='exact_collinear_union_v1',
                  parallel_angle_limit_deg=15., perpendicular_crossing_min_deg=75.,
                  minimum_parallel_mm=1., interactions=[], classified_nets={},
                  track_geometry={}, blocker_keys=[], blocking_count=0)
    report['semantic_inventory'] = fields.inventory(report)
    assert report['semantic_inventory']['status'] == 'known'
    return report


class AuditWorkbench:
    """Only the helper boundary is faked; reports use the real inventory."""
    def __init__(self, jobs):
        self.jobs = jobs
        self.epoch = 'current'
        self.calls = []

    def _job(self, token):
        self.calls.append(token)
        path, data = self.jobs[token]
        if data['code_identity'] != self.epoch:
            raise ValueError('job_code_identity_changed')
        return path, data


@pytest.fixture
def audit_suite(tmp_path):
    rows, tokens, jobs = [], [], {}
    selected = {}
    for index in range(9):
        board = 'board-'+str(index)
        token = 'job-'+str(index)
        sha = format(index+1, '064x')
        rows.append(dict(board=board, sha256=sha))
        tokens.append(token)
        directory = tmp_path/token
        directory.mkdir()
        path = directory/'job.json'
        data = dict(board=board, token=token, source_sha256=sha,
                    candidate_sha256=sha, code_identity='current', request=dict(kind='inspect'))
        if index == 0:
            data['source_sha256'] = 'a'*64
            data['request'] = dict(operations=[dict(kind='repair_chain')])
            selected[board] = (path, data)
        jobs[token] = (path, data)
        step = 'fields_candidate' if index == 0 else 'fields_source'
        (directory/(step+'.json')).write_text(json.dumps(dict(
            complete=True, candidate_sha256=sha, result=valid_report())))
    return AuditWorkbench(jobs), tokens, rows, selected


def evidence(w, token, selected):
    path, data = w.jobs[token]
    step = 'fields_candidate' if data['board'] in selected else 'fields_source'
    return path.parent/(step+'.json')


def test_full_nine_audit_uses_selected_candidate_and_exact_untouched_sources(audit_suite):
    w, tokens, rows, selected = audit_suite
    result = publication.received_field_refresh(w, list(reversed(tokens)), rows, selected)
    assert len(result) == 9 and set(w.calls) == set(tokens)
    for row, entry in zip(rows, result):
        path = Path(entry['path'])
        assert checkpoint.sha(path) == entry['sha256']
        record = json.loads(path.read_text())
        assert record['candidate_sha256'] == row['sha256']
        assert path.name == ('fields_candidate.json' if row['board'] in selected else 'fields_source.json')


@pytest.mark.parametrize('fault', ['missing_token', 'duplicate_token', 'wrong_board',
    'duplicate_board', 'wrong_source', 'non_inspect_source', 'stale_epoch',
    'missing_evidence', 'wrong_candidate_hash', 'missing_candidate_hash',
    'incomplete_record', 'incomplete_report', 'unknown_inventory', 'old_audit_basis',
    'missing_inventory', 'altered_inventory', 'selected_source_only', 'wrong_selected_token'])
def test_current_full_suite_audit_refuses_inexact_or_unknown_evidence(audit_suite, fault):
    w, tokens, rows, selected = audit_suite
    token = tokens[1]
    path, data = w.jobs[token]
    report_path = evidence(w, token, selected)
    record = json.loads(report_path.read_text())
    if fault == 'missing_token': tokens.pop()
    elif fault == 'duplicate_token': tokens[-1] = tokens[0]
    elif fault == 'wrong_board': data['board'] = 'not-in-published-suite'
    elif fault == 'duplicate_board': data['board'] = rows[0]['board']
    elif fault == 'wrong_source': data['source_sha256'] = 'b'*64
    elif fault == 'non_inspect_source': data['request'] = dict(kind='construct')
    elif fault == 'stale_epoch': data['code_identity'] = 'old'
    elif fault == 'missing_evidence': report_path.unlink()
    elif fault == 'wrong_candidate_hash': record['candidate_sha256'] = 'c'*64
    elif fault == 'missing_candidate_hash': record.pop('candidate_sha256')
    elif fault == 'incomplete_record': record['complete'] = False
    elif fault == 'incomplete_report': record['result']['complete'] = False
    elif fault == 'unknown_inventory': record['result'].pop('track_geometry')
    elif fault == 'old_audit_basis': record['result']['audit_basis'] = 'segment_pairs_v0'
    elif fault == 'missing_inventory': record['result'].pop('semantic_inventory')
    elif fault == 'altered_inventory': record['result']['semantic_inventory']['blocking_count'] = 1
    elif fault == 'selected_source_only':
        child_path, child_data = w.jobs[tokens[0]]
        child_data['request'] = dict(kind='inspect')
        child_data['source_sha256'] = rows[0]['sha256']
        candidate_evidence = child_path.parent/'fields_candidate.json'
        candidate_evidence.rename(child_path.parent/'fields_source.json')
    elif fault == 'wrong_selected_token':
        selected[rows[0]['board']] = (w.jobs[tokens[0]][0], dict(token='different-selected-job'))
    if fault not in ('missing_evidence', 'selected_source_only'):
        report_path.write_text(json.dumps(record))
    with pytest.raises((ValueError, FileNotFoundError)):
        publication.received_field_refresh(w, tokens, rows, selected)
    if fault == 'stale_epoch':
        assert token in w.calls


@pytest.mark.parametrize('group', ['field_receipts', 'superseded_field_receipts'])
def test_portable_normalization_hash_checks_active_and_archived_field_evidence(tmp_path, group):
    # Minimal control-plane archive: CAD producer checks are orthogonal; this
    # exercises the actual portable evidence loop, with a real semantic audit.
    origin = tmp_path/'origin.json'
    origin.write_text(json.dumps(dict(boards=[])))
    asset = tmp_path/'field.json'
    asset.write_text(json.dumps(dict(complete=True, candidate_sha256='a'*64,
                                     result=valid_report())))
    receipt = dict(format=checkpoint.FORMAT, origin_receipt='origin.json',
                   origin_receipt_sha256=checkpoint.sha(origin), boards=[],
                   **{group: [dict(path='field.json', sha256=checkpoint.sha(asset))]})
    path = tmp_path/'receipt.json'
    path.write_text(json.dumps(receipt))
    normalized = checkpoint.normalize(path, checkpoint.sha(path))
    assert normalized[group][0]['path'] == str(asset)
    asset.write_text(asset.read_text()+'\nchanged historical evidence\n')
    with pytest.raises(ValueError, match='portable_field_evidence_changed'):
        checkpoint.normalize(path, checkpoint.sha(path))
