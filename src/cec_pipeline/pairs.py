"""Bounded legacy pair-semantic nonregression; never physics qualification.

The retained oracle has project defaults. They are inherited assumptions, not
new source-qualified skew, edge-rate, impedance or return-continuity limits.
Saved filled reference samples are measured, not continuous-field proof.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import sys


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def compare(before, after):
    """Conservative structured comparison, preserving explicit inherited debt.

    Exact inherited issue text deliberately refuses ambiguous magnitude/location
    changes: a same-count replacement cannot acquire credit as an improvement.
    Scalar improvements are allowed; altered inherited issues require review.
    """
    def finite_tree(value, depth=0):
        _require(depth <= 32, 'bounded_pair_evidence_required')
        if type(value) is float:
            _require(math.isfinite(value), 'nonfinite_pair_evidence')
        elif type(value) in (list, tuple):
            _require(len(value) <= 65536, 'bounded_pair_evidence_required')
            for item in value:
                finite_tree(item, depth + 1)
        elif type(value) is dict:
            _require(len(value) <= 4096, 'bounded_pair_evidence_required')
            for item in value.values():
                finite_tree(item, depth + 1)
        else:
            _require(value is None or type(value) in (str, int, bool),
                     'json_pair_evidence_required')

    _require(type(before) is dict and type(after) is dict, 'pair_report_required')
    finite_tree(before)
    finite_tree(after)
    for report in (before, after):
        _require(report.get('applicable') is True and type(report.get('ok')) is bool,
                 'pair_measurement_unavailable')
        _require(type(report.get('pairs')) is list and len(report['pairs']) == 1,
                 'one_complete_pair_measurement_required')
    a, b = before['pairs'][0], after['pairs'][0]
    _require(all(a.get(k) == b.get(k) and type(a.get(k)) is str
                 for k in ('kind', 'p', 'n')), 'pair_identity_changed')
    lower = ('skew_mm', 'uncoupled_length_mm', 'vias_p', 'vias_n')
    higher = ('reference_coverage_pct', 'coupled_coverage_pct')
    regressions = []
    for key in lower + higher:
        values = (a.get(key), b.get(key))
        _require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0
                     for v in values), 'invalid_pair_metric:' + key)
        if (values[1] > values[0] if key in lower else values[1] < values[0]):
            regressions.append('metric:' + key)
    for row in (a, b):
        _require(type(row.get('violations')) is list
                 and all(type(v) is str and v for v in row['violations']),
                 'complete_pair_issues_required')
    _require(before['ok'] == (not a['violations'])
             and after['ok'] == (not b['violations']), 'inconsistent_pair_verdict')
    # Strings include exact semantic identity/location and magnitude. Do not
    # normalize coordinates/numbers and silently merge distinct physical faults.
    new = sorted(set(b['violations']) - set(a['violations']))
    regressions.extend('issue:' + issue for issue in new)
    for key in ('missing_return_vias', 'transition_reference_samples',
                'plated_terminal_reference_samples'):
        expected = list if key == 'missing_return_vias' else int
        _require(key in a and key in b and type(a[key]) is expected
                 and type(b[key]) is expected, 'complete_pair_return_evidence_required')
        # An altered failing sample cannot hide behind unchanged coverage/count.
        if a[key] != b[key] and b['violations']:
            regressions.append('changed_inherited_return_evidence:' + key)
    return dict(ok=not regressions, regressions=regressions,
                inherited_debt=list(a['violations']), candidate_debt=list(b['violations']),
                source_metrics={k: a[k] for k in lower + higher},
                candidate_metrics={k: b[k] for k in lower + higher})


def _snapshot(board):
    """Actual native conductor geometry, including saved filled shared returns."""
    from cec_native_frozen_zone_access import _zones
    import pcbnew
    tracks = {}
    for t in board.GetTracks():
        tracks[str(t.m_Uuid.AsString())] = (
            str(t.GetNetname()), t.GetClass(), tuple(t.GetStart()),
            tuple(t.GetEnd()), int(t.GetWidth()), int(t.GetLayer()),
            tuple(int(l) for l in t.GetLayerSet().CuStack()),
            int(t.GetDrillValue()) if t.GetClass() == 'PCB_VIA' else None,
            tuple(t.GetMid()) if t.GetClass() == 'PCB_ARC' else None)
    pads = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            copper = []
            for layer in p.GetLayerSet().CuStack():
                polygon = pcbnew.SHAPE_POLY_SET()
                p.TransformShapeToPolygon(polygon, layer, 0, 1, pcbnew.ERROR_OUTSIDE, False)
                copper.append((int(layer), polygon.Format()))
            pads.append((str(p.m_Uuid.AsString()), str(p.GetNetname()),
                         tuple(p.GetPosition()), tuple(p.GetSize()),
                         tuple(p.GetDrillSize()), p.GetOrientationDegrees(),
                         int(p.GetShape()), tuple(p.GetOffset()),
                         tuple(int(l) for l in p.GetLayerSet().CuStack()), tuple(copper)))
    return tracks, sorted(pads), _zones(board)


def _worker(source, candidate):
    from .legacy import bootstrap
    bootstrap()
    import cec_swig_guard
    cec_swig_guard.pin()
    import pcbnew
    import cec_constraints as constraints
    boards = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
    names = [constraints._coupled_pair_names(b) for b in boards]
    _require(names[0] == names[1], 'complete_pair_inventory_changed')
    _require(len(names[0]) <= 32, 'bounded_pair_inventory_required')
    a, b = map(_snapshot, boards)
    changed = {k for k in a[0].keys() | b[0].keys() if a[0].get(k) != b[0].get(k)}
    nets = {row[0] for tracks in (a[0], b[0]) for k, row in tracks.items() if k in changed}
    shared = a[1:] != b[1:] or 'GND' in nets
    scope = [row for row in names[0] if shared or set(row[1:]) & nets]
    results = []
    for kind, p, n in scope:
        reports = [constraints.high_speed_pair_summary(str(source), board=board,
                   only_pair=(p, n)) for board in boards]
        results.append(dict(pair=[kind, p, n], **compare(*reports)))
    return dict(ok=all(r['ok'] for r in results), complete=True, pairs=results,
                scope=[list(row) for row in scope], scope_from_native_geometry=True,
                changed_track_count=len(changed), changed_track_nets=sorted(nets),
                complete_pair_inventory=[list(row) for row in names[0]],
                shared_return_or_terminal_geometry_changed=shared,
                inherited_legacy_policy_assumptions=True,
                continuous_return_proof=False, physics_qualification=False,
                source_policy_path=str(source))


def receive(source, candidate, *, timeout_s=8.0):
    """One aggregate killable lease for both loads and every affected pair."""
    _require(type(timeout_s) in (int, float) and math.isfinite(timeout_s)
             and 0 < timeout_s < 10, 'pair_lease_must_be_below_ten_seconds')
    for path in (source, candidate):
        _require(Path(path).is_file() and Path(path).stat().st_size <= 64 * 1024**2,
                 'bounded_saved_pair_board_required')
    env = dict(os.environ)
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get('PYTHONPATH', '')
    try:
        proc = subprocess.run([sys.executable, '-m', __name__, str(source), str(candidate)],
                              capture_output=True, text=True, timeout=timeout_s, env=env)
        _require(proc.returncode == 0, 'pair_native_worker_failed:' + proc.stderr[-1000:])
        result = json.loads(proc.stdout)
        _require(type(result) is dict and type(result.get('ok')) is bool
                 and result.get('complete') is True and type(result.get('pairs')) is list
                 and type(result.get('scope')) is list
                 and len(result['pairs']) == len(result['scope'])
                 and result.get('scope_from_native_geometry') is True
                 and result.get('physics_qualification') is False,
                 'malformed_pair_worker_result')
        return result
    except (subprocess.TimeoutExpired, ValueError) as exc:
        return dict(ok=False, complete=False, unavailable=True, reason=str(exc), physics_qualification=False)


if __name__ == '__main__':
    print(json.dumps(_worker(*sys.argv[1:]), allow_nan=False))
