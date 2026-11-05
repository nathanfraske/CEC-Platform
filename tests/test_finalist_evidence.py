"""Exact ranking attribution and bounded diagnostic retention regressions."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

import cec_finalist_evidence as fe
import cec_route_preflight as rp


def test_decisive_change_is_first_difference_not_largest_penalty():
    row = fe.compare_keys(('critical', 'congestion'), (11, 100000), (10, 900000))
    assert row['relation'] == 'improved'
    assert row['decisive_change']['field'] == 'critical'
    assert row['changes'][1]['direction'] == 'worsened'
    assert fe.compare_keys(('a',), (2,), (2,))['decisive_change'] is None
    assert fe.compare_keys(('a',), (2,), (3,))['relation'] == 'worsened'


def test_names_match_every_existing_key_field_without_changing_its_order():
    base = {'future_congestion_present': True}
    for i, field in enumerate(rp.PLACEMENT_EVIDENCE_FIELDS):
        candidate = dict(base)
        if field == 'error':
            candidate['error'] = 'fixture failure'
        elif field == 'future_congestion_missing':
            candidate['future_congestion_present'] = False
        else:
            candidate[field] = 1
        comparison = fe.compare_keys(rp.PLACEMENT_EVIDENCE_FIELDS,
                                     rp.placement_evidence_key(base),
                                     rp.placement_evidence_key(candidate))
        assert comparison['decisive_change']['index'] == i
        assert comparison['decisive_change']['field'] == field
        assert comparison['relation'] == 'worsened'
    # Legacy alias must still be ranked under the canonical diagnostic name.
    assert rp.placement_evidence_key({'critical_pair_refused_count': 3})[1] == 3


@pytest.mark.parametrize('fields,base,candidate', [
    (('a',), (0, 1), (0,)), (('a', 'a'), (0, 0), (1, 1)),
    (('a',), (float('nan'),), (0,)), (('a',), (0,), (float('inf'),)),
])
def test_malformed_keys_refused(fields, base, candidate):
    with pytest.raises(ValueError):
        fe.compare_keys(fields, base, candidate)


def files(tmp_path):
    rows = []
    for name in ('before', 'after'):
        path = tmp_path / (name + '.kicad_pcb')
        path.write_text('(fixture ' + name + ')')
        path.with_suffix('.kicad_pro').write_text('{}')
        path.with_suffix('.pourfirst-state.json').write_text('{"fixture": true}')
        rows.append(fe.identity(path))
    return rows


def test_verified_two_artifact_budget_and_source_unchanged(tmp_path):
    before, after = files(tmp_path)
    root = tmp_path / 'diagnostics'
    for _ in range(2):
        row = fe.retain(before, after, {'comparison': 'fixture'}, {'complete': True}, root)
        assert row['retained'] and not row['release_authority'] and not row['promotion_allowed']
        assert len(row['files']) == 6
        assert all(fe.identity(r['path'])['sha256'] == r['sha256'] for r in row['files'])
        assert json.loads(Path(row['evidence']).read_text())['candidate_evidence']['complete']
    row = fe.retain(before, after, {}, {}, root)
    assert row['reason'] == 'diagnostic_artifact_budget_exhausted'
    assert fe.identity(before['path']) == before
    assert fe.identity(after['path']) == after


def test_stale_measured_hash_and_storage_floor_fail_without_claiming_capture(tmp_path):
    before, after = files(tmp_path)
    with mock.patch.object(fe.shutil, 'disk_usage', return_value=SimpleNamespace(free=1)):
        row = fe.retain(before, after, {}, {}, tmp_path / 'low-disk')
    assert row['reason'] == 'diagnostic_storage_floor'
    assert fe.retain(before, after, {}, {}, tmp_path / 'oversize', max_bytes=1)['reason'] == 'diagnostic_byte_budget'
    Path(after['path']).write_text('changed after analysis')
    row = fe.retain(before, after, {}, {}, tmp_path / 'stale')
    assert row['reason'] == 'measured_board_unavailable_or_changed'
    assert not row['retained']


def test_io_failure_does_not_masquerade_as_success(tmp_path):
    before, after = files(tmp_path)
    with mock.patch.object(fe.shutil, 'copy2', side_effect=OSError('fixture disk error')):
        row = fe.retain(before, after, {}, {}, tmp_path / 'fail')
    assert row['reason'] == 'diagnostic_capture_failed'
    assert not row['retained'] and not row['release_authority']
    assert fe.retain(before, after, {}, {}, None)['reason'] == 'no_durable_operation_directory'
