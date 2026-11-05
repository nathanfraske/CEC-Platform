"""Import cleanup may not erase a finite-width locked landing capsule."""
import ast
import inspect
from types import SimpleNamespace
from unittest import mock

import pcbnew
import pytest

import cec_fr as fr
import cec_router as router


@pytest.mark.parametrize('offset,layer,width', [
    ((0., 0.), pcbnew.F_Cu, .3),
    ((21., 13.), pcbnew.B_Cu, 2.),
    ((7., 31.), pcbnew.In2_Cu, .7),
])
def test_production_import_sanitizer_preserves_locked_capsules(offset, layer, width):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    def add(length, locked):
        item = pcbnew.PCB_TRACK(board)
        p = pcbnew.VECTOR2I_MM(*offset)
        item.SetStart(p)
        item.SetEnd(pcbnew.VECTOR2I(p.x+length, p.y))
        item.SetLayer(layer)
        item.SetWidth(pcbnew.FromMM(width))
        item.SetLocked(locked)
        board.Add(item)
        return item.m_Uuid.AsString()
    exact = add(0, True)
    tiny = add(1, True)
    new_artifact = add(1, False)
    neck = add(10001, False)
    # Execute the actual import boundary's call and keyword contract, not a
    # test-only preserve flag that production can accidentally omit again.
    tree = ast.parse(inspect.getsource(fr.import_ses))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name)
             and n.func.id == 'prune_degenerate_tracks']
    assert len(calls) == 1
    call = ast.Expression(body=calls[0])
    removed = eval(compile(ast.fix_missing_locations(call), 'import-boundary', 'eval'),
                   {'prune_degenerate_tracks': fr.prune_degenerate_tracks, 'board': board})
    assert removed == 1
    assert {t.m_Uuid.AsString() for t in board.GetTracks()} == {exact, tiny, neck}
    assert new_artifact not in {t.m_Uuid.AsString() for t in board.GetTracks()}


def test_ownership_refusal_survives_candidate_pool_and_decision_log(tmp_path):
    path = tmp_path/'renamed.kicad_pcb'
    path.write_text('private diagnostic fixture')
    candidate = fr.Candidate(str(path), '', 17, {'stage_s': {'import_ses': .2}}, True)
    with mock.patch.object(fr, 'copper_geometry_signature',
                           return_value={'sha256': 'changed'}), \
         mock.patch.object(router.cec_score, 'score') as score:
        assert router._candidate_pool([candidate], object(), {},
            protected_contract={'nets': ['/RENAMED_RAIL'], 'sha256': 'expected'}) == []
    score.assert_not_called()
    assert not candidate.ok
    evidence = router._candidate_rejection_evidence([candidate])
    assert evidence['count'] == 1 and evidence['truncated'] == 0
    assert evidence['samples'][0]['sha256']
    assert 'critical copper ownership changed' in evidence['samples'][0]['error']
    log = router.DecisionLog()
    log.add(region='any', iteration=1, candidates=[], chosen=None,
            verdict=None, generation_rejections=evidence)
    assert log.entries[0]['generation_rejections'] == evidence
    assert log.entries[0]['candidates'] == []


def test_failure_diagnostics_are_bounded_not_silent_or_admission(tmp_path):
    candidates = [fr.Candidate('', '', i, {}, False, err='failure'*1000,
                               trace='x'*20000) for i in range(5)]
    row = router._candidate_rejection_evidence(candidates, limit=2)
    assert row['count'] == 5 and row['truncated'] == 3
    assert len(row['samples']) == 2
    assert all(len(r['error']) <= 4096 and len(r['trace']) <= 16384 for r in row['samples'])
    assert all(r['sha256'] is None for r in row['samples'])
    assert row['scope'] == 'diagnostic_not_route_admission'
    with pytest.raises(ValueError):
        router._candidate_rejection_evidence(candidates, limit=0)


def test_console_summary_does_not_expand_full_native_geometry_receipt():
    import copy
    import json
    verdict = {'gates_pass': False, 'drc': 0, 'unconnected': 98,
               'reasons': ['bounded reason' * 100 for _ in range(20)],
               'protected_items': ['native-item'] * 10000}
    original = copy.deepcopy(verdict)
    summary = router._compact_cli_verdict(verdict, evidence_path='/private/exact-log.json')
    assert len(json.dumps(summary)) < 3000
    assert summary['unconnected'] == 98 and summary['gates_pass'] is False
    assert summary['reason_count'] == 20 and summary['more_reasons'] == 12
    assert len(summary['reasons']) == 8
    assert summary['full_evidence'] == '/private/exact-log.json'
    assert verdict == original  # durable diagnostics are not truncated
