"""Source-proved removal of a small, pad-free ground-plane dead-end tail.

This is not mesh pruning or a bypass-current waiver. The unlocked, ungrouped
uniform straight-segment chain must have exactly one free tip and terminate
at one retained native through via which directly touches a saved ground
plane. No tail material may contact another land, zone, junction, or barrel.
Saved exact replay, every surviving native partition, and all already-proved
short ground returns are mandatory. DRC, field, current, and release receiving
remain separate; inherited factory/PI debt is never qualified here.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
from cec_cell_row_rebuild import _source_binding
from cec_native_items import discard_items


def _deadline(timeout_s):
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('bounded_ground_dead_end_lease_required')
    return time.monotonic() + timeout_s


def plan(board, seed_uuid, *, ground_net='GND', timeout_s=10.,
         max_tracks=8, max_length_mm=12.):
    deadline = _deadline(timeout_s)
    if (type(seed_uuid) is not str or not seed_uuid or type(ground_net) is not str
            or not ground_net or type(max_tracks) is not int or not 1 <= max_tracks <= 8
            or type(max_length_mm) not in (int, float) or not math.isfinite(max_length_mm)
            or not 0 < max_length_mm <= 12):
        raise ValueError('bounded_explicit_ground_dead_end_scope_required')
    tracks = list(board.GetTracks())
    pads = [p for f in board.GetFootprints() for p in f.Pads()]
    zones = [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == ground_net]
    if len(tracks) + len(pads) + len(zones) > 16384:
        raise ValueError('ground_dead_end_native_inventory_bound')
    matches = [t for t in tracks if force._uid(t) == seed_uuid]
    if len(matches) != 1:
        raise ValueError('unique_native_ground_dead_end_seed_required')
    seed = matches[0]
    if seed.GetClass() != 'PCB_TRACK' or seed.GetNetname() != ground_net:
        raise ValueError('native_ground_track_seed_required')
    layer, width = int(seed.GetLayer()), int(seed.GetWidth())
    if not 0 < width <= 350000 or any(not z.IsFilled() for z in zones):
        raise ValueError('small_tail_and_known_saved_ground_fill_required')
    grouped = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    own = [t for t in tracks if t.GetNetname() == ground_net and t.IsOnLayer(layer)]

    def check_time():
        if time.monotonic() >= deadline:
            raise ValueError('ground_dead_end_inventory_deadline')

    def contacts(edge, point=None):
        shape = (edge.GetEffectiveShape(layer) if point is None else
                 pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*point), pcbnew.VECTOR2I(*point), width))
        result = []
        for other in own:
            check_time()
            if force._uid(other) != force._uid(edge) and shape.Collide(other.GetEffectiveShape(layer), 0):
                result.append(other)
        return result

    ends = [tuple(seed.GetStart()), tuple(seed.GetEnd())]
    free = [point for point in ends if not contacts(seed, point)]
    if len(free) != 1:
        raise ValueError('exactly_one_free_native_ground_tail_tip_required')
    point = free[0]
    current = seed
    retired, length, root = [], 0., None
    while True:
        check_time()
        uid = force._uid(current)
        ends = [tuple(current.GetStart()), tuple(current.GetEnd())]
        if (current.GetClass() != 'PCB_TRACK' or current.IsLocked() or uid in grouped
                or current.GetParentGroup() is not None or current.GetWidth() != width
                or current.GetLayer() != layer or current.GetNetname() != ground_net
                or point not in ends or ends[0] == ends[1] or uid in retired):
            raise ValueError('unlocked_ungrouped_uniform_endpoint_tail_required')
        length += current.GetLength()/1e6
        retired.append(uid)
        if len(retired) > max_tracks or length > max_length_mm:
            raise ValueError('ground_dead_end_tail_scope_bound')
        material = current.GetEffectiveShape(layer)
        for other in [*pads, *zones]:
            check_time()
            if not other.IsOnLayer(layer):
                continue
            shape = (other.GetFilledPolysList(layer) if other.GetClass() == 'ZONE'
                     else other.GetEffectiveShape(layer))
            if material.Collide(shape, 0):
                raise ValueError('ground_tail_has_actual_land_or_plane_contact')
        far = ends[1] if point == ends[0] else ends[0]
        next_items = [i for i in contacts(current) if force._uid(i) not in retired]
        if len(next_items) != 1:
            raise ValueError('ground_tail_has_branch_or_missing_endpoint_root')
        following = next_items[0]
        if not following.GetEffectiveShape(layer).Collide(
                pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*far), pcbnew.VECTOR2I(*far), width), 0):
            raise ValueError('ground_tail_has_interior_contact')
        if following.GetClass() == 'PCB_VIA':
            if (tuple(following.GetPosition()) != far
                    or following.GetViaType() != pcbnew.VIATYPE_THROUGH):
                raise ValueError('exact_retained_through_via_endpoint_required')
            root = following
            break
        if following.GetClass() != 'PCB_TRACK' or far not in (
                tuple(following.GetStart()), tuple(following.GetEnd())):
            raise ValueError('ground_tail_terminates_at_unowned_interior_junction')
        current, point = following, far
    planes = []
    for zone in zones:
        check_time()
        for lid in board.GetEnabledLayers().CuStack():
            if zone.IsOnLayer(lid) and root.IsOnLayer(lid) and zone.GetFilledPolysList(lid).Collide(
                    root.GetEffectiveShape(lid), 0):
                planes.append(force._uid(zone))
                break
    if not planes:
        raise ValueError('retained_root_has_no_actual_saved_ground_plane_contact')
    return dict(schema=1, kind='pad_free_native_ground_dead_end_tail',
                seed_uuid=seed_uuid, ground_net=ground_net, max_tracks=max_tracks,
                max_length_mm=max_length_mm, source_binding=_source_binding(board),
                retired_track_uuids=retired, retained_root_via_uuid=force._uid(root),
                source_layer=layer, source_width_nm=width, source_length_mm=length,
                root_plane_uuids=sorted(planes), current_qualified=False, release_authority=False)


def subtract(board, proposal, *, timeout_s=10.):
    fresh = plan(board, proposal['seed_uuid'], ground_net=proposal['ground_net'],
                 max_tracks=proposal['max_tracks'], max_length_mm=proposal['max_length_mm'],
                 timeout_s=timeout_s)
    if fresh != proposal:
        raise ValueError('ground_dead_end_stale_or_forged_source_plan')
    by_id = {force._uid(t): t for t in board.GetTracks()}
    discard_items(board, [by_id[u] for u in fresh['retired_track_uuids']])


def _receive_exact_subtraction(source, candidate, proposal, *, board_hint,
                              subtractor, timeout_s=10.):
    """Shared saved replay; the typed operator still derives its own cut."""
    result = dict(schema=1, ok=False, complete=False, errors=[], current_qualified=False,
                  inherited_debt_qualified=False, release_authority=False,
                  full_saved_board_receiving_still_required=True)
    try:
        deadline = _deadline(timeout_s)
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        if source == candidate:
            raise ValueError('distinct_saved_ground_tail_candidates_required')
        families = [force._family(p, board_hint) for p in (source, candidate)]
        epoch = force._code_identity()
        before, after = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        retired = set(proposal['retired_track_uuids'])
        old = ordinary._partition(before, deadline, retired_uuids=retired)
        retained = set().union(*old)
        new = ordinary._partition(after, deadline, retained_keys=retained)
        if any(not any(part <= q for q in new) for part in old):
            raise ValueError('ground_tail_cut_lost_surviving_native_partition')
        new_pads = {force._uid(p): p for f in after.GetFootprints() for p in f.Pads()}
        returns = []
        for fp in before.GetFootprints():
            for pad in fp.Pads():
                if time.monotonic() >= deadline:
                    raise ValueError('ground_tail_return_receiving_deadline')
                if pad.GetNetname() != proposal['ground_net']:
                    continue
                prior = cells._existing_return(before, pad, 3.5)
                if prior is None:
                    continue
                child = new_pads.get(force._uid(pad))
                current = cells._existing_return(after, child, 3.5) if child is not None else None
                if current is None or current[0] > prior[0] + 1e-6:
                    raise ValueError('ground_tail_cut_worsened_proved_local_return')
                returns.append(dict(pad_uuid=force._uid(pad), before_mm=prior[0], after_mm=current[0]))
        with tempfile.TemporaryDirectory(prefix='cec-ground-tail-receiving-') as work:
            expected = force._copy_family(source, Path(work)/'expected')
            basis = pcbnew.LoadBoard(str(source))
            subtractor(basis, proposal, timeout_s=max(.001, deadline-time.monotonic()))
            additive._ground_refill(basis)
            field._save_field_snapshot(basis, expected)
            _, old_nodes = additive._nodes(expected)
            _, new_nodes = additive._nodes(candidate)
            if old_nodes.keys() != new_nodes.keys() or any(
                    syntax._freeze(old_nodes[u]) != syntax._freeze(new_nodes[u]) for u in old_nodes):
                raise ValueError('ground_tail_not_exact_native_subtract_and_refill')
            if (force._preservation_snapshot(expected)[1] != force._preservation_snapshot(candidate)[1]
                    or force._sidecars(expected) != force._sidecars(candidate)):
                raise ValueError('ground_tail_outline_rules_or_sidecars_changed')
        if (families != [force._family(p, board_hint) for p in (source, candidate)]
                or epoch != force._code_identity() or time.monotonic() >= deadline):
            raise ValueError('ground_tail_source_code_or_lease_changed')
        result.update(ok=True, complete=True, retired_track_uuids=sorted(retired),
                      retained_root_via_uuid=proposal['retained_root_via_uuid'],
                      all_surviving_native_partitions_preserved=True,
                      proved_short_ground_returns_preserved=returns,
                      exact_subtraction_and_ground_refill_received=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    return result


def receive(source, candidate, proposal, *, board_hint, timeout_s=10.):
    return _receive_exact_subtraction(source, candidate, proposal,
        board_hint=board_hint, subtractor=subtract, timeout_s=timeout_s)
