"""Bound a native motion contact audit, including stationary conductors.

Moving a footprint into an unchanged track is still a new routing debt.
Literal native bounding boxes select a conservative audit inventory only;
the separate native shape inspector decides actual collisions. Boxes never
stand in for copper, connectivity, current capacity or retirement permission.
"""
import math
import time
import pcbnew
import cec_force_current as force


def scope(source, candidate, changed_native_uuids, *, clearance_nm,
          timeout_s=3., maximum_tracks=256, provisional_reconstruction_track_uuids=()):
    if (type(changed_native_uuids) not in (list, tuple, set) or
            not 1 <= len(changed_native_uuids) <= 256 or
            len(set(changed_native_uuids)) != len(changed_native_uuids) or
            any(type(u) is not str or not u for u in changed_native_uuids) or
            type(clearance_nm) is not int or not 0 <= clearance_nm <= 2000000 or
            type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or
            not 0 < timeout_s <= 10 or type(maximum_tracks) is not int or
            not 1 <= maximum_tracks <= 512):
        raise ValueError('bounded_literal_native_motion_impact_inventory_required')
    deadline = time.monotonic() + timeout_s
    def inventory(board):
        native = [*board.GetFootprints(), *board.GetTracks(), *board.Zones()]
        if len(native) > 16384:
            raise ValueError('native_motion_impact_board_inventory_bound')
        indexed = {force._uid(t): t for t in native}
        if len(indexed) != len(native):
            raise ValueError('unique_native_motion_impact_identity_required')
        return indexed
    old, new = inventory(source), inventory(candidate)
    selected = set(changed_native_uuids)
    if not selected <= old.keys() & new.keys():
        raise ValueError('native_motion_impact_requires_existing_source_and_candidate_items')
    pending=set(provisional_reconstruction_track_uuids)
    if (type(provisional_reconstruction_track_uuids) not in (list,tuple,set)
            or len(pending)!=len(provisional_reconstruction_track_uuids) or len(pending)>512
            or not pending<=selected or any(old[u].GetClass()!='PCB_TRACK' or new[u].GetClass()!='PCB_TRACK' for u in pending)):
        raise ValueError('native_motion_impact_exact_changed_provisional_track_scope_required')
    def box(item):
        if item.GetClass()=='FOOTPRINT':
            # Silkscreen labels and distant fabrication text are not copper
            # obstacles. All native lands, holes and copper graphics ARE.
            shapes=[*item.Pads(),*[g for g in item.GraphicalItems() if g.IsOnCopperLayer()],
                *[f for f in item.GetFields() if f.IsVisible() and f.IsOnCopperLayer()]]
            if not shapes:return None
            boxes=[g.GetBoundingBox() for g in shapes]
            return (min(b.GetLeft() for b in boxes),min(b.GetTop() for b in boxes),
                max(b.GetRight() for b in boxes),max(b.GetBottom() for b in boxes))
        bbox=item.GetBoundingBox()
        return (bbox.GetX(),bbox.GetY(),bbox.GetRight(),bbox.GetBottom())
    windows = []
    for uid in sorted(selected):
        if old[uid].GetClass() != new[uid].GetClass():
            raise ValueError('native_motion_impact_item_class_changed')
        for item in (old[uid], new[uid]):
            # A provisional endpoint seed is already a mandatory rewrite.
            # Its abandoned, stretched body cannot own additional stationary
            # routes. New physical pad/barrel contacts still select those,
            # and actual reconstructed routes need full independent guards.
            if uid in pending:continue
            bounds=box(item)
            if bounds is None:continue
            x0,y0,x1,y1=bounds
            windows.append((x0-clearance_nm,y0-clearance_nm,x1+clearance_nm,y1+clearance_nm))
    tracks = []
    for item in candidate.GetTracks():
        if time.monotonic() >= deadline:
            raise ValueError('native_motion_impact_inventory_deadline')
        if item.GetClass() != 'PCB_TRACK':
            continue
        uid = force._uid(item)
        if uid not in old or old[uid].GetClass() != 'PCB_TRACK':
            raise ValueError('native_motion_impact_cannot_own_added_or_retired_copper')
        bounds = [box(old[uid]), box(item)]
        def intersects(a, b):
            return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])
        if uid in selected or any(intersects(a,b) for a in bounds for b in windows):
            tracks.append(uid)
    if len(tracks)>maximum_tracks:
        raise ValueError('native_motion_impact_audit_track_count_bound:'+str(len(tracks))+':'+str(maximum_tracks))
    return dict(schema=1, complete=True, audit_track_uuids=sorted(tracks),
        changed_native_uuids=sorted(selected), audit_includes_stationary_conductors=True,
        bounding_boxes_are_conservative_audit_scope_only=True,
        provisional_endpoint_seeds_are_mandatory_audit_and_reconstruction_only=sorted(pending),
        non_copper_fields_not_used_as_copper_scope=True,
        actual_native_shape_collision_receiving_required=True,
        native_geometry_mutated=False, automatic_retirement_authorized=False,
        current_qualified=False, release_authority=False)
