"""Bounded diagnostic debt after motion, including still-canonical tracks.

This identifies actual new native obstacles, not automatic retirement rights.
The caller must reconstruct a whole transaction and independently receive its
connectivity, current, clearances and immutable source. No board exceptions.
"""
import math
import time
import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_route_quality as quality


def inspect(source, candidate, track_uuids, *, clearance_for, timeout_s=5.,
            transient_reconstruction_track_uuids=(), maximum_tracks=256, maximum_transient_tracks=64):
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or not callable(clearance_for)
            or type(track_uuids) not in (list, tuple, set, frozenset)
            or type(maximum_tracks) is not int or not 1<=maximum_tracks<=512
            or type(maximum_transient_tracks) is not int or not 1<=maximum_transient_tracks<=128
            or not 1 <= len(track_uuids) <= maximum_tracks
            or len(set(track_uuids)) != len(track_uuids)
            or any(type(u) is not str or not u for u in track_uuids)):
        raise ValueError('bounded_explicit_native_motion_inventory_required')
    deadline = time.monotonic() + timeout_s
    old = {force._uid(t): t for t in source.GetTracks()}
    new = {force._uid(t): t for t in candidate.GetTracks()}
    if type(transient_reconstruction_track_uuids) not in (tuple,list,set,frozenset):
        raise ValueError('exact_bounded_provisional_track_reconstruction_scope_required')
    transient=set(transient_reconstruction_track_uuids)
    if (len(transient_reconstruction_track_uuids)!=len(transient) or len(transient)>maximum_transient_tracks or
            not transient<=old.keys() & new.keys() or
            any(old[u].GetClass()!='PCB_TRACK' or new[u].GetClass()!='PCB_TRACK' for u in transient)):
        raise ValueError('exact_bounded_provisional_track_reconstruction_scope_required')
    if (len(old) > 16384 or len(new) > 16384 or not set(track_uuids) <= old.keys()
            or not set(track_uuids) <= new.keys()
            or list(source.GetEnabledLayers().CuStack()) != list(candidate.GetEnabledLayers().CuStack())):
        raise ValueError('exact_existing_motion_track_and_layer_identity_required')
    caches = [{}, {}]
    rows = []
    def width(item):
        return item.GetWidth(item.TopLayer()) if item.GetClass() == 'PCB_VIA' else item.GetWidth()
    for uid in sorted(track_uuids):
        if time.monotonic() >= deadline:
            raise ValueError('native_motion_contact_inventory_deadline')
        prior, item = old[uid], new[uid]
        if (prior.GetClass() != item.GetClass()
                or prior.GetClass() not in ('PCB_TRACK', 'PCB_VIA')
                or str(prior.GetNetname()) != str(item.GetNetname())
                or width(item) != width(prior)
                or prior.IsLocked() != item.IsLocked()):
            raise ValueError('motion_inventory_cannot_credit_width_or_identity_changes')
        if item.GetClass() == 'PCB_VIA':
            # A barrel is a rigid cell/current object, never a planar reroute.
            continue
        if prior.GetLayer() != item.GetLayer():
            raise ValueError('motion_inventory_cannot_credit_a_layer_change')
        gap = clearance_for(str(item.GetNetname()))
        if type(gap) is not int or not 0 <= gap <= 2000000:
            raise ValueError('explicit_native_motion_clearance_required')
        blockers = []
        for phase,(board, track, cache) in enumerate(zip((source, candidate), (prior, item), caches)):
            key = (int(track.GetLayer()), int(track.GetNetCode()))
            if key not in cache:
                zones,copper=fr._identified_foreign_shape_indexes(board, track.GetLayer(), {track.GetNetCode()})
                if phase and transient:
                    # A malformed, explicitly pending replacement stroke is
                    # not stationary source material. Omit ONLY these exact
                    # track shapes from this PRIVATE dependency ordering.
                    # Pads, barrels, zones and all final receiving stay real.
                    copper_rows=copper.get('rows',()) if isinstance(copper,dict) else copper
                    copper=fr._bucket_foreign_shapes([r for r in copper_rows
                        if (r[2] or {}).get('uuid') not in transient])
                cache[key]=(zones,copper)
            zones, copper = cache[key]
            blockers.append(fr._snapshot_foreign_blockers(track.GetStart(), track.GetEnd(),
                track.GetWidth(), gap, zones, copper))
        was_clear = not blockers[0]
        is_canonical = quality.is_canonical_stroke(tuple(item.GetStart()), tuple(item.GetEnd()))
        rows.append(dict(uuid=uid, net=str(item.GetNetname()), layer=candidate.GetLayerName(item.GetLayer()),
            source_native_clear=was_clear, candidate_native_clear=not blockers[1],
            candidate_canonical=is_canonical, source_obstacles=blockers[0],
            candidate_obstacles=blockers[1],
            needs_transaction_reconstruction=(not is_canonical or (was_clear and bool(blockers[1])))))
    if time.monotonic() >= deadline:
        raise ValueError('native_motion_contact_inventory_deadline')
    return dict(schema=1, scope='native_motion_new_obstacle_debt_only', complete=True,
        tracks=rows, rebuild_track_uuids=[r['uuid'] for r in rows if r['needs_transaction_reconstruction']],
        canonical_heading_is_not_clearance=True, source_mutated=False, candidate_mutated=False,
        transient_reconstruction_track_uuids=sorted(transient),
        provisional_exclusions_are_not_retirement_or_clearance_permission=True,
        automatic_retirement_authorized=False, current_qualified=False,
        clearance_qualified=False, release_authority=False)
