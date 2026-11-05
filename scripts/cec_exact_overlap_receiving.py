"""Receive a saved, exact track-overlap normalization; never grant a rating.

Only a caller's finite source UUID scope may change. Reciprocal, exact
centreline interval coverage with identical fabrication fields proves that
the union of KiCad's round straight-track capsules is unchanged. Widths,
layers, nets, mask properties and unknown fields participate in that proof.
All other serialized board state is immutable. Group-owned copper refuses.

The optional per-item lock policy separates physical fabrication fields from
editor locks ONLY after independently checking each surviving source UUID's
literal lock fields. Locks are never copied between tracks or relaxed. This
receiver still grants no authority to edit or retire locked source copper.

This is geometric receiving, not authorization to edit locked copper, a
clearance waiver, or electrical/thermal/fabrication qualification. Callers
still need independent saved-board native DRC and topology/current checks.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import math
import time

import cec_copper_echo as syntax


def _nm(atom):
    value = Decimal(atom) * 1_000_000
    if not value.is_finite() or value != value.to_integral_value():
        raise ValueError('exact_native_coordinate_required')
    return int(value)


def _read(path, scope, deadline, max_items, *, retain_per_item_locks=False):
    if Path(path).stat().st_size > 32 * 1024 * 1024:
        raise ValueError('board_byte_bound')
    root = syntax._parse(syntax._TOKEN.findall(Path(path).read_text(encoding='utf-8')))
    if not root or root[0] != 'kicad_pcb':
        raise ValueError('native_board_required')
    if len(root) > max_items:
        raise ValueError('board_item_bound')
    fixed, tracks, groups = [], {}, set()
    for node in root[1:]:
        if time.monotonic() >= deadline:
            raise ValueError('receiving_deadline')
        if not isinstance(node, list) or not node:
            raise ValueError('malformed_board_item')
        if node[0] == 'group':
            for child in node[1:]:
                if isinstance(child, list) and child and child[0] == 'members':
                    groups.update(child[1:])
        if node[0] != 'segment':
            fixed.append(syntax._freeze(node))
            continue
        fields = {}
        for child in node[1:]:
            if isinstance(child, list) and child:
                if child[0] in fields:
                    raise ValueError('duplicate_segment_field')
                fields[child[0]] = child
        ident = fields.get('uuid', ())
        if len(ident) != 2 or ident[1] in tracks:
            raise ValueError('ambiguous_track_identity')
        uid = ident[1]
        tracks[uid] = node
        if uid not in scope:
            fixed.append(syntax._freeze(node))
    if groups & scope:
        raise ValueError('group_owner_recompile_required')
    rows = []
    for uid in sorted(scope & tracks.keys()):
        node = tracks[uid]
        fields = {child[0]: child for child in node[1:]
                  if isinstance(child, list) and child}
        if (len(fields.get('start', ())) != 3 or len(fields.get('end', ())) != 3
                or len(fields.get('width', ())) != 2
                or len(fields.get('layer', ())) != 2 or len(fields.get('net', ())) != 2):
            raise ValueError('incomplete_native_segment')
        net = syntax._atom(fields['net'][1])
        if ((net[0] == 'number' and net[1] <= 0)
                or net == ('string', '""') or net[0] not in ('number', 'string')):
            raise ValueError('assigned_track_net_required')
        start = tuple(_nm(v) for v in fields['start'][1:])
        end = tuple(_nm(v) for v in fields['end'][1:])
        if start == end or _nm(fields['width'][1]) <= 0:
            raise ValueError('positive_native_capsule_required')
        def lock_field(child):
            return (isinstance(child,list) and child and child[0]=='locked') or child=='locked'
        locks=tuple(syntax._freeze(child) if isinstance(child,list) else syntax._atom(child)
                    for child in node[1:] if lock_field(child))
        if retain_per_item_locks and len(locks)>1:
            raise ValueError('ambiguous_native_track_lock_fields')
        fabrication = tuple(sorted((syntax._freeze(child) if isinstance(child, list)
                                    else syntax._atom(child)
                                    for child in node[1:]
                                    if not (isinstance(child, list)
                                            and child[0] in ('start', 'end', 'uuid'))
                                    and not (retain_per_item_locks and lock_field(child))),
                                   key=repr))
        rows.append(dict(uuid=uid, start=start, end=end, fabrication=fabrication,
                         **({'source_lock_fields':locks} if retain_per_item_locks else {})))
    return sorted(fixed, key=repr), tracks.keys(), rows


def _covered(row, receivers, deadline, remaining):
    ax, ay = row['start']; bx, by = row['end']
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    intervals = []
    for peer in receivers:
        remaining[0] -= 1
        if remaining[0] < 0:
            raise ValueError('coverage_pair_bound')
        if time.monotonic() >= deadline:
            raise ValueError('receiving_deadline')
        if peer['fabrication'] != row['fabrication']:
            continue
        endpoints = [(p[0] - ax, p[1] - ay) for p in (peer['start'], peer['end'])]
        if any(x * dy != y * dx for x, y in endpoints):
            continue
        low, high = sorted(x * dx + y * dy for x, y in endpoints)
        low, high = max(0, low), min(length2, high)
        if high > low:
            intervals.append((low, high, peer['uuid']))
    end, witnesses = 0, []
    for low, high, uid in sorted(intervals):
        if low > end:
            break
        if high > end:
            end = high; witnesses.append(uid)
        if end == length2:
            return witnesses
    raise ValueError('exact_reciprocal_capsule_coverage_missing')


def receive(source, candidate, *, source_track_uuids, timeout_s=2.,
            max_scope=64, max_items=32768, max_pairs=8192,retain_per_item_locks=False):
    """Read-only, bounded proof of identical saved physical copper coverage."""
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 <= timeout_s <= 10 or type(max_scope) is not int
            or not 1 <= max_scope <= 256 or type(max_items) is not int
            or not 1 <= max_items <= 32768 or type(max_pairs) is not int
            or not 1 <= max_pairs <= 131072 or type(retain_per_item_locks) is not bool):
        raise ValueError('bounded_overlap_receiving_required')
    if type(source_track_uuids) not in (list, tuple, set, frozenset):
        raise ValueError('finite_distinct_source_track_scope_required')
    supplied = list(source_track_uuids)
    if (not supplied or len(supplied) > max_scope
            or any(type(uid) is not str or not uid or '"' in uid for uid in supplied)
            or len(set(supplied)) != len(supplied)):
        raise ValueError('finite_distinct_source_track_scope_required')
    scope = {'"' + uid + '"' for uid in supplied}
    started = time.monotonic(); deadline = started + timeout_s
    report = dict(schema=1, ok=False, complete=False, errors=[],
                  reciprocal_copper_coverage=False, non_scoped_board_state_unchanged=False,
                  native_copper_mutated=False, release_authority=False,
                  scope='exact_capsule_union_not_electrical_or_current_qualification')
    try:
        old_fixed, old_ids, old = _read(source, scope, deadline, max_items,
            retain_per_item_locks=retain_per_item_locks)
        new_fixed, new_ids, new = _read(candidate, scope, deadline, max_items,
            retain_per_item_locks=retain_per_item_locks)
        if not scope <= old_ids or not new_ids <= old_ids:
            raise ValueError('source_scope_or_surviving_identity_missing')
        if old_fixed != new_fixed:
            raise ValueError('non_scoped_board_state_changed')
        report['non_scoped_board_state_unchanged'] = True
        if retain_per_item_locks:
            prior={r['uuid']:r['source_lock_fields'] for r in old}
            if any(r['source_lock_fields']!=prior[r['uuid']] for r in new):
                raise ValueError('surviving_original_track_lock_changed')
            report['every_surviving_source_track_lock_retained']=True
        remaining = [max_pairs]
        proofs = []
        for side, subjects, receivers in [('source', old, new), ('candidate', new, old)]:
            for row in subjects:
                proofs.append(dict(side=side, uuid=row['uuid'].strip('"'),
                    covered_by=[u.strip('"') for u in _covered(row, receivers, deadline, remaining)]))
        report.update(ok=True, complete=True, reciprocal_copper_coverage=True,
                      source_tracks=len(old), candidate_tracks=len(new),
                      coverage_checks=max_pairs-remaining[0], proofs=proofs)
    except (ValueError, OSError, ArithmeticError) as exc:
        report['errors'].append(str(exc))
    report['elapsed_s'] = time.monotonic() - started
    return report
