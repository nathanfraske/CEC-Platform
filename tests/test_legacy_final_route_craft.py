"""An electrical-only pass cannot bypass whole-copper final route acceptance."""
import copy
from dataclasses import asdict
from types import SimpleNamespace

import pytest
import pcbnew
import cec_route_quality as quality
import cec_dispatch as dispatch
import cec_cascade as cascade
import cec_router as router
import cec_constraints as constraints
import cec_field_coupling as field
from route_final_craft_fixtures import clean_quality
from test_reverse_jog_everywhere import POINTS
from test_route_junction_serial_bridges import native_board


def scored(report):
    return SimpleNamespace(gates_pass=True, drc=0, unconnected=0, kelvin_ok=True,
        diffpair_ok=True, tracks=4, vias=0, drc_types={}, drc_loci=[], length=5.,
        detail={'route_quality': report, 'unconn_nets': []})


def other_independent_gates(monkeypatch):
    """Isolate the real final consumer, not DRC/thermal/procurement qualification."""
    monkeypatch.setattr(router.cec_score, 'gate', lambda m, rules: (True, []))
    monkeypatch.setattr(router.cec_score, 'objective', lambda m, weights: 0.)
    monkeypatch.setattr(constraints, 'via_on_pad_summary', lambda p:
        dict(same=0, diff=0, n_vias=0))
    monkeypatch.setattr(constraints, 'foreign_on_pour_summary', lambda p:
        dict(applicable=False, n_tracks=0, n_vias=0, n_pours=0, by_pour={}))
    monkeypatch.setattr(constraints, 'laid_pour_incursion_summary', lambda p:
        dict(applicable=False, n_parts=0, n_tracks=0, n_vias=0))
    for name in ('high-current-stackup-2oz', 'hub-stackup-6layer',
                 'through-vias-only', 'mezzanine-segment-contract'):
        monkeypatch.setitem(constraints.CHECKERS, name, lambda *a: (None, 'not applicable'))
    monkeypatch.setattr(constraints, 'release_gate', lambda *a, **kw:
        dict(ok=True, blockers=[]))
    monkeypatch.setattr(field, 'field_coupling_summary', lambda p:
        dict(applicable=False, ok=True))


@pytest.mark.parametrize('face', range(0, 64, 2))
@pytest.mark.parametrize('kink', (False, True))
def test_native_all_faces_reach_every_legacy_final_consumer(face, kink, tmp_path, monkeypatch):
    board = native_board(POINTS if kink else [(0, 0), (4000000, 0)], face, 1, True)
    board.SetCopperLayerCount(32)
    path = tmp_path / 'candidate.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    report = quality.analyze_board(pcbnew.LoadBoard(str(path)))
    assert report['ok'] is True  # The intermediate advisory is intentionally preserved.
    assert report['reverse_diagonal_jog_count'] == int(kink)
    expected = not kink
    metrics = scored(report)
    monkeypatch.setattr(dispatch.cec_fr, 'generate_batch', lambda *a, **kw:
        [SimpleNamespace(ok=True, board=str(path), seed=17)])
    monkeypatch.setattr(dispatch.cec_score, 'score', lambda *a, **kw: metrics)
    candidates = dispatch._generate_scored('unused', {}, (17,), 1, str(tmp_path))
    assert candidates[0].route_quality == report
    assert candidates[0].gates_pass is True
    ctx = dispatch.JudgeContext(str(path), [asdict(candidates[0])], 0, 'test', [])
    assert (dispatch.det_haiku(ctx).action == 'accept') is expected
    assert (dispatch.det_escalate(ctx).action == 'accept') is expected
    # An arbitrary model verdict cannot waive the guard by choosing accept.
    best, log = dispatch.agent_route(str(path), tiers=[lambda ctx:
        dispatch.Verdict('accept', seed=17)], request_fn=lambda p, s: candidates,
        verbose=False)
    assert (best is not None) is expected
    if kink:
        assert 'route craft' in log[0]['note']
    monkeypatch.setattr(cascade.cec_router, 'board_spec', lambda *a, **kw:
        (SimpleNamespace(), 'fixture'))
    monkeypatch.setattr(cascade.cec_router, 'route', lambda *a, **kw:
        (str(path), SimpleNamespace(final={'verdict': {'gates_pass': True}})))
    _, _, verdict = cascade.route_tier('fixture', str(path), panel=1, swarm=False,
        max_iters=1, kmax=1, seeds=(17,), passes=1, opt_time=0, verbose=False)
    assert verdict['electrical_gates_pass'] is True
    assert verdict['gates_pass'] is expected
    assert cascade._route_ok(verdict) is expected
    # Even a legacy caller incorrectly claiming gates_pass=True is rechecked.
    inherited = dict(gates_pass=True, drc=0, unconnected=0, route_quality=report)
    assert cascade._route_ok(inherited) is expected
    other_independent_gates(monkeypatch)
    independent = router.independent_drc(str(path), SimpleNamespace(kelvin_pairs=[]))
    assert independent['electrical_gates_pass'] is True
    assert independent['gates_pass'] is expected
    assert independent['route_quality'] == report


def damaged_report(kind):
    report = clean_quality()
    if kind == 'missing': return None
    if kind == 'empty': return {}
    if kind == 'non-dict': return ['craft_ok']
    if kind == 'stale-policy': report['policy_identity']['modules']['cec_route_quality.py'] = '0' * 64
    elif kind == 'missing-policy': report.pop('policy_identity')
    elif kind == 'failed': report['error'] = 'native observation failed'
    elif kind == 'incomplete': report['complete'] = False
    elif kind == 'truthy-complete': report['complete'] = 1
    elif kind == 'truthy-craft': report['craft_ok'] = 1
    elif kind == 'scoped': report['track_uuid_scope'] = []
    elif kind == 'missing-scope': report.pop('track_uuid_scope')
    elif kind == 'inconsistent-count': report['issue_count'] = 1
    elif kind == 'truthy-count': report['issue_count'] = False
    elif kind == 'hidden-issue': report['issues'] = [{'type': 'reverse_diagonal_jog'}]
    elif kind == 'hidden-non45': report['non_octilinear'] = [{'type': 'non45'}]
    elif kind == 'missing-inventory': report.pop('issues')
    elif kind == 'geometry-failed': report['geometry_ok'] = False
    elif kind == 'protected-failed': report['ok'] = False
    elif kind == 'contour-failed': report['power_contour_review_ok'] = False
    elif kind == 'contour-incomplete': report['power_contours']['complete'] = False
    elif kind == 'hidden-contour': report['power_contours']['findings'] = [{'type': 'rounded_overhang'}]
    elif kind == 'missing-contours': report.pop('power_contours')
    return report


@pytest.mark.parametrize('kind', ('missing', 'empty', 'non-dict', 'stale-policy',
    'missing-policy', 'failed', 'incomplete', 'truthy-complete', 'truthy-craft', 'scoped',
    'missing-scope', 'inconsistent-count', 'truthy-count', 'hidden-issue', 'hidden-non45',
    'missing-inventory', 'geometry-failed', 'protected-failed', 'contour-failed',
    'contour-incomplete', 'hidden-contour', 'missing-contours'))
def test_partial_stale_or_contradictory_reports_cannot_be_final_acceptance(kind):
    report = damaged_report(kind)
    before = copy.deepcopy(report)
    assert not all(quality.final_craft_terms(report).values())
    row = dict(gates_pass=True, route_quality=report, drc=0, unconnected=0)
    assert not dispatch._candidate_accepts(row)
    assert not cascade._route_ok(row)
    assert report == before


def test_old_electrical_only_dispatch_candidate_is_unverified_not_clean():
    candidate = dispatch.CandidateMetrics(seed=0, params={}, board='old', drc=0,
        unconnected=0, kelvin_ok=True, diffpair_ok=True, gates_pass=True,
        tracks=1, vias=0, drc_types={}, drc_loci=[], unconn_nets=[])
    assert not dispatch._candidate_accepts(candidate)
    assert not dispatch._candidate_accepts({'gates_pass': 1, 'route_quality': clean_quality()})


def test_native_scoped_clean_observation_cannot_sign_whole_board():
    board = native_board([(0, 0), (4000000, 0)], 0, 0, False)
    uuid = next(iter(board.GetTracks())).m_Uuid.AsString()
    report = quality.analyze_board(board, track_uuid_scope={uuid})
    assert report['craft_ok'] is True and report['track_uuid_scope'] == [uuid]
    assert not all(quality.final_craft_terms(report).values())
