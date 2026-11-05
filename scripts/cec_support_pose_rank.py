"""Order a finite native placement menu by predicted bypass geometry.

This is deliberately not an admission gate or a pose-rejection cache. Pure
translations reuse the final oracle's pad coordinates and declared limits;
rotations and incomplete references remain unknown. Every candidate survives
and the normal native craft/DRC/route transaction still decides acceptance.
"""
from collections import Counter
from copy import deepcopy
import math
from types import SimpleNamespace

import cec_support_craft_gate as craft


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _point(value):
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and all(_number(v) for v in value))


def predict(details, target, candidate, *, loop_excess_max_mm=0.25):
    """Necessary geometry only, including stationary members of an IC cell."""
    import cec_synth_pipeline as synth
    result = dict(status='unknown', new_or_worsened_faults={},
                  release_authority=False, admission_authority=False)
    dx, dy, angle = (candidate.get(k, 0) for k in
                    ('dx_mm', 'dy_mm', 'rotation_delta_deg'))
    if not all(_number(v) for v in (dx, dy, angle)) or abs(angle % 360) > 1e-9:
        return dict(result, reason='unsupported_transform')
    companions = candidate.get('mobility_companion_refs')
    if companions is None:
        companions = target.get('companion_refs') or []
    if (not isinstance(companions, (list, tuple))
            or not all(isinstance(v, str) for v in companions)
            or not isinstance(target.get('ref'), str)):
        return dict(result, reason='unknown_cell_membership')
    moving = {target['ref'], *companions}
    affected = [r for r in details if {r.get('owner_ref'), r.get('cap_ref')} & moving]
    if not affected:
        return dict(result, status='unaffected', reason='no_assigned_bypass_cell')
    identities = Counter((r.get('owner_ref'), str(r.get('owner_pin')), r.get('rail'))
                         for r in details)
    shifted = []
    for row in affected:
        tangent = row.get('tangent_target') or {}
        grounds = row.get('owner_ground_positions_mm')
        points = [row.get(k) for k in ('owner_supply_position_mm',
            'cap_supply_position_mm', 'cap_ground_position_mm')]
        ideal_supply = synth._decoupler_ideal_supply_mm(tangent)
        ideal_loop = (tangent.get('best_loop') or {}).get('loop_proxy_mm')
        limits = (ideal_supply, ideal_loop, row.get('supply_excess_limit_mm'),
                  row.get('return_limit_mm'))
        if (row.get('status') != 'assigned'
                or row.get('return_gate_mode') != 'absolute_ground_distance'
                or row.get('shared_pin_reference')
                or identities[(row.get('owner_ref'), str(row.get('owner_pin')), row.get('rail'))] != 1
                or not all(_number(v) and v >= 0 for v in limits)
                or not all(_point(v) for v in points)
                or not isinstance(grounds, list) or not grounds
                or not all(isinstance(g, dict) and _point(g.get('position')) for g in grounds)):
            return dict(result, reason='incomplete_or_ambiguous_geometry')
        moved = deepcopy(row)
        if row['owner_ref'] in moving:
            moved = synth._translated_decoupler_owner_detail(moved, dx, dy)
        if row['cap_ref'] in moving:
            for key in ('cap_supply_position_mm', 'cap_ground_position_mm'):
                moved[key] = [row[key][0] + dx, row[key][1] + dy]
        # A move can change which physical owner ground pad is nearest.
        moved['owner_ground_position_mm'] = min(
            (g['position'] for g in moved['owner_ground_positions_mm']),
            key=lambda p: math.dist(p, moved['cap_ground_position_mm']))
        moved['ground_distance_mm'] = math.dist(moved['owner_ground_position_mm'],
                                               moved['cap_ground_position_mm'])
        shifted.append(moved)

    def measurement(rows):
        return dict(ok=True, gates={}, faults=dict(
            return_geometry=craft.geometry_faults(rows),
            proximity_geometry=craft.proximity_geometry_faults(rows,
                loop_excess_max_mm=loop_excess_max_mm)))

    comparison = craft.compare(measurement(affected), measurement(shifted))
    return dict(result, status='nonregressing' if comparison['accepted'] else 'regressed',
                reason='translation_geometry_prediction',
                new_or_worsened_faults=comparison['new_or_worsened_faults'])


def rank(details, target, candidates, *, loop_excess_max_mm=0.25):
    """Stable permutation: predicted regressions follow other eligible poses."""
    rows = []
    for index, candidate in enumerate(candidates):
        prediction = predict(details, target, candidate,
                             loop_excess_max_mm=loop_excess_max_mm)
        rows.append((prediction['status'] == 'regressed', index,
                     dict(candidate, electrical_pose_rank=prediction)))
    rows.sort(key=lambda r: (r[0], r[1]))
    ordered = [r[2] for r in rows]
    return dict(candidates=ordered, counts=dict(Counter(
        c['electrical_pose_rank']['status'] for c in ordered)),
        reordered=any(index != row[1] for index, row in enumerate(rows)),
        candidate_count=len(ordered), release_authority=False, admission_authority=False)


def rank_candidates(board_path, target, candidates, policy=None):
    """Read native geometry once per target, not once per proposed pose."""
    import cec_synth_pipeline as synth
    params = dict((policy or {}).get('params') or {})
    adjacency = synth._oracle_decoupler_adjacency(str(board_path), SimpleNamespace(params=params))
    if adjacency.get('error') or not isinstance(adjacency.get('details'), list):
        return dict(candidates=list(candidates), error='native_geometry_unavailable',
                    release_authority=False, admission_authority=False)
    return rank(adjacency['details'], target, candidates,
                loop_excess_max_mm=float(params.get('decoupler_loop_excess_max_mm', 0.25)))
