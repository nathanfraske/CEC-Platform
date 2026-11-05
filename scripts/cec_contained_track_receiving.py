"""Retirement-only receiving for strictly contained native straight tracks.

Every survivor and all other saved board state must remain identical. Exact
rational capsule containment AND outward-source / inward-survivor native
polygon containment prove that retirement removes no physical copper. This
does not authorize a source cut, infer current sharing, qualify a load, or
replace complete saved native DRC, conductor, field and Kelvin receiving.
"""
from pathlib import Path
import math
import time

import pcbnew
import cec_exact_overlap_receiving as exact


def _disc_inside(point, a, b, diameter_gap):
    dx, dy = b[0]-a[0], b[1]-a[1]
    px, py = point[0]-a[0], point[1]-a[1]
    length2 = dx*dx+dy*dy
    projection = px*dx+py*dy
    if not length2 or projection <= 0:
        numerator, denominator = px*px+py*py, 1
    elif projection >= length2:
        numerator, denominator = (point[0]-b[0])**2+(point[1]-b[1])**2, 1
    else:
        numerator, denominator = (px*dy-py*dx)**2, length2
    return 4*numerator <= diameter_gap*diameter_gap*denominator


def _physical_fields(row):
    # Locks are independently immutable on every survivor. Only the wider
    # track's actual width may differ; mask/unknown fabrication fields may not.
    return tuple(field for field in row['fabrication'] if field[0] != ('atom', 'width'))


def receive(source, candidate, *, source_track_uuids, timeout_s=2.,
            coverage_margin_nm=10, max_scope=64, max_items=32768, max_pairs=8192):
    """Read-only, bounded exact-union proof; all scoped survivors are frozen."""
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 <= timeout_s <= 10 or type(coverage_margin_nm) is not int
            or not 1 <= coverage_margin_nm <= 1000 or type(max_scope) is not int
            or not 1 <= max_scope <= 256 or type(max_items) is not int
            or not 1 <= max_items <= 32768 or type(max_pairs) is not int
            or not 1 <= max_pairs <= 131072):
        raise ValueError('bounded_strict_containment_receiving_required')
    if type(source_track_uuids) not in (list, tuple, set, frozenset):
        raise ValueError('finite_distinct_containment_scope_required')
    ids = list(source_track_uuids)
    if (not ids or len(ids) > max_scope
            or any(type(uid) is not str or not uid or '"' in uid for uid in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('finite_distinct_containment_scope_required')
    scope = {'"'+uid+'"' for uid in ids}
    started = time.monotonic(); deadline = started+timeout_s
    report = dict(schema=1, ok=False, complete=False, errors=[], proofs=[],
        reciprocal_copper_coverage=False, non_scoped_board_state_unchanged=False,
        native_copper_mutated=False, release_authority=False, new_capacity_credited=False,
        scope='strict_contained_capsule_retirement_not_current_qualification')
    try:
        paths = [Path(p).resolve() for p in (source, candidate)]
        old_fixed, old_ids, old_rows = exact._read(paths[0], scope, deadline, max_items,
            retain_per_item_locks=True)
        new_fixed, new_ids, new_rows = exact._read(paths[1], scope, deadline, max_items,
            retain_per_item_locks=True)
        if not scope <= old_ids or not new_ids <= old_ids:
            raise ValueError('source_scope_or_surviving_identity_missing')
        if old_fixed != new_fixed:
            raise ValueError('non_scoped_board_state_changed')
        old = {r['uuid']: r for r in old_rows}; new = {r['uuid']: r for r in new_rows}
        if any(row != old[uid] for uid, row in new.items()):
            raise ValueError('surviving_original_track_changed')
        retired = set(old)-new.keys()
        if not retired or not new:
            raise ValueError('actual_retirement_and_unchanged_scoped_receiver_required')
        boards = [pcbnew.LoadBoard(str(p)) for p in paths]
        if any(board is None for board in boards):
            raise ValueError('both_saved_boards_must_load_natively')
        live = [{t.m_Uuid.AsString(): t for t in b.GetTracks()} for b in boards]
        if any(uid.strip('"') not in live[0] or live[0][uid.strip('"')].GetClass() != 'PCB_TRACK'
                for uid in scope):
            raise ValueError('native_straight_track_scope_required')
        checks = 0
        for uid in sorted(retired):
            target = live[0][uid.strip('"')]; found = False
            for rid in sorted(new):
                checks += 1
                if checks > max_pairs or time.monotonic() >= deadline:
                    raise ValueError('containment_pair_or_deadline_bound')
                receiver = live[1][rid.strip('"')]
                if (_physical_fields(old[uid]) != _physical_fields(new[rid])
                        or target.GetNetname() != receiver.GetNetname()
                        or target.GetLayer() != receiver.GetLayer()):
                    continue
                gap = receiver.GetWidth()-target.GetWidth()-2*coverage_margin_nm
                if gap <= 0 or not all(_disc_inside(p, new[rid]['start'], new[rid]['end'], gap)
                                      for p in (old[uid]['start'], old[uid]['end'])):
                    continue
                outer = pcbnew.SHAPE_POLY_SET(); inner = pcbnew.SHAPE_POLY_SET()
                target.TransformShapeToPolygon(outer, target.GetLayer(), 0, 1, pcbnew.ERROR_OUTSIDE, False)
                receiver.TransformShapeToPolygon(inner, receiver.GetLayer(), 0, 1, pcbnew.ERROR_INSIDE, False)
                outer.BooleanSubtract(inner)
                if time.monotonic() >= deadline:
                    raise ValueError('containment_pair_or_deadline_bound')
                if outer.OutlineCount():
                    continue
                report['proofs'].append(dict(retired_uuid=uid.strip('"'), receiver_uuid=rid.strip('"'),
                    exact_rational_capsule_coverage=True, native_outward_minus_inward_empty=True,
                    curve_error_nm=1, positive_coverage_margin_nm=coverage_margin_nm,
                    area_waiver_used=False, survivor_modified=False))
                found = True; break
            if not found:
                raise ValueError('strict_unchanged_native_capsule_receiver_missing')
        report.update(ok=True, complete=True, reciprocal_copper_coverage=True,
            non_scoped_board_state_unchanged=True, every_surviving_source_track_unchanged=True,
            source_tracks=len(old), candidate_tracks=len(new), coverage_checks=checks,
            retired_track_uuids=sorted(uid.strip('"') for uid in retired))
    except (ValueError, OSError, ArithmeticError, RuntimeError) as exc:
        report['errors'].append(str(exc))
    report['elapsed_s'] = time.monotonic()-started
    return report
