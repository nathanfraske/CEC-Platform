"""Subtract only an exact, full-width source-owned routing prefix.

An incremental compiler must not draw a second copy of a source stub when it
starts at the same terminal. Centreline intervals are exact integer/rational
geometry; only same-net/same-layer straight source tracks at least as wide as
the emitted track count. No pad, barrel, zone, clearance or ampacity credit is
inferred. Only caller-owned NEW tracks may change. Independent saved native
receiving must subsequently prove the source-component boundary connection.
"""
from fractions import Fraction
import math
import time

import pcbnew
import cec_force_current as force
import cec_fr as fr
from cec_native_items import discard_items


def on_centerline(point, track):
    s, t = tuple(track.GetStart()), tuple(track.GetEnd())
    dx, dy = t[0]-s[0], t[1]-s[1]
    px, py = point[0]-s[0], point[1]-s[1]
    return bool((dx or dy) and px*dy == py*dx
        and 0 <= px*dx+py*dy <= dx*dx+dy*dy)


def clip(source, board, origin_pad_uuid, tracks, *, timeout_s=2.):
    """Plan fully before mutation; mutate the supplied new-track list in place."""
    if (source is board or type(timeout_s) not in (int, float)
            or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10
            or type(tracks) is not list or not 1 <= len(tracks) <= 64):
        raise ValueError('bounded_distinct_source_new_track_prefix_required')
    deadline = time.monotonic()+timeout_s
    old_tracks = {force._uid(t): t for t in source.GetTracks()}
    board_tracks = {force._uid(t): t for t in board.GetTracks()}
    if len(old_tracks) + sum(fp.GetPadCount() for fp in source.GetFootprints()) > 16384:
        raise ValueError('native_prefix_source_inventory_budget')
    if len(board_tracks) > 16384:
        raise ValueError('native_prefix_candidate_inventory_budget')
    roots = [p for fp in source.GetFootprints() for p in fp.Pads() if force._uid(p) == origin_pad_uuid]
    if len(roots) != 1:
        raise ValueError('native_prefix_unique_source_terminal_required')
    root = roots[0]
    if root.GetNetCode() <= 0 or not str(root.GetNetname()):
        raise ValueError('native_prefix_assigned_source_net_required')
    graph = fr._read_only_route_connectivity(source)
    owned = [t for t in graph.GetConnectedItems(root) if t.GetClass() == 'PCB_TRACK'
        and t.GetNetCode() == root.GetNetCode()]
    del graph
    cursor = tuple(root.GetPosition())
    seen = set()
    for track in tracks:
        uid = force._uid(track)
        if (uid not in board_tracks or uid in old_tracks or uid in seen
                or track.GetClass() != 'PCB_TRACK'
                or int(track.this) != int(board_tracks[uid].this)
                or track.GetNetCode() != root.GetNetCode()
                or str(track.GetNetname()) != str(root.GetNetname())
                or track.GetWidth() <= 0 or track.GetStart() == track.GetEnd()
                or tuple(track.GetStart()) != cursor):
            raise ValueError('native_prefix_requires_ordered_new_owned_track_chain')
        cursor = tuple(track.GetEnd()); seen.add(uid)
    removed = []; partial = None; witnesses = []
    for track in tracks:
        if time.monotonic() >= deadline:
            raise ValueError('native_prefix_discovery_deadline')
        start, end = tuple(track.GetStart()), tuple(track.GetEnd())
        dx, dy = end[0]-start[0], end[1]-start[1]; norm = dx*dx+dy*dy
        intervals = []
        for old in owned:
            if time.monotonic() >= deadline:
                raise ValueError('native_prefix_discovery_deadline')
            if old.GetLayer() != track.GetLayer() or old.GetWidth() < track.GetWidth():
                continue
            a, b = tuple(old.GetStart()), tuple(old.GetEnd())
            if any((p[0]-start[0])*dy != (p[1]-start[1])*dx for p in (a,b)):
                continue
            bounds = sorted((Fraction((p[0]-start[0])*dx+(p[1]-start[1])*dy,norm),p) for p in (a,b))
            intervals.append((bounds[0][0], bounds[1][0], bounds[1][1], force._uid(old)))
        tip, point = Fraction(0), start; used = []
        for low, high, at, uid in sorted(intervals):
            if low > tip:
                break
            if high > tip:
                tip, point = high, at; used.append(uid)
        if tip <= 0:
            break
        witnesses.append(dict(new_uuid=force._uid(track), source_track_uuids=used,
            old_start_nm=list(start), old_end_nm=list(end), source_full_width=True))
        if tip >= 1:
            removed.append(track)
            continue
        partial = (track, point)
        witnesses[-1]['new_start_nm'] = list(point)
        break
    if time.monotonic() >= deadline:
        raise ValueError('native_prefix_discovery_deadline')
    removed_ids = [force._uid(t) for t in removed]
    if partial is not None:
        partial[0].SetStart(pcbnew.VECTOR2I(*partial[1]))
    tracks[:] = [t for t in tracks if force._uid(t) not in set(removed_ids)]
    if removed:
        discard_items(board, removed)
    return dict(schema=1, removed_new_track_uuids=removed_ids,
        trimmed_new_track_uuid=force._uid(partial[0]) if partial else None,
        source_owned_prefix_witnesses=witnesses, source_material_removed_or_changed=False,
        full_native_receiving_still_required=True, release_authority=False)
