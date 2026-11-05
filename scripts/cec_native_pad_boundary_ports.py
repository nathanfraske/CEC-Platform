"""Coalesce cut contacts only on the same real, connected surface land.

Multiple old bends inside one convex SMD pad are attachment choices, not
independent terminals. No near-coordinate, same-net, THT/barrel or abstract
component merge is allowed. This read-only proposal adapter does not replace
independent restoration of EVERY original boundary and surviving partition.
"""
import time
import pcbnew
import cec_force_current as force


def plan(board, boundaries, *, retired_track_uuids, timeout_s=2.):
    if (type(timeout_s) not in (int, float) or not 0 < timeout_s <= 10.
            or not isinstance(boundaries, list) or len(boundaries) != 1
            or not isinstance(retired_track_uuids, (list, tuple, set))
            or not 1 <= len(retired_track_uuids) <= 32
            or len(set(retired_track_uuids)) != len(retired_track_uuids)):
        raise ValueError('bounded_exact_native_pad_boundary_scope_required')
    deadline = time.monotonic()+timeout_s
    row = boundaries[0]; anchors = row.get('anchors_nm'); net = row.get('net')
    if (not isinstance(net, str) or not net or not isinstance(anchors, list)
            or not 2 <= len(anchors) <= 16 or row.get('external_boundary_count') != len(anchors)
            or any(not isinstance(p, (list, tuple)) or len(p) != 2
                or any(type(v) is not int or abs(v) > 2_000_000_000 for v in p) for p in anchors)
            or len({tuple(p) for p in anchors}) != len(anchors)):
        raise ValueError('exact_distinct_source_boundary_anchors_required')
    layer = int(board.GetLayerID(row.get('layer', '')))
    code = board.GetNetcodeFromNetname(net)
    if code <= 0 or layer not in board.GetEnabledLayers().CuStack():
        raise ValueError('actual_native_boundary_net_and_face_required')
    native = [*(p for fp in board.GetFootprints() for p in fp.Pads()), *board.GetTracks()]
    if len(native) > 16384:
        raise ValueError('native_pad_boundary_inventory_bound')
    old = set(retired_track_uuids)
    cuts = [i for i in native if force._uid(i) in old]
    if (len(cuts) != len(old) or any(i.GetClass() != 'PCB_TRACK'
            or str(i.GetNetname()) != net or int(i.GetLayer()) != layer for i in cuts)):
        raise ValueError('exact_same_net_native_boundary_cut_required')
    own = [i for i in native if force._uid(i) not in old and i.GetNetCode() == code and i.IsOnLayer(layer)]
    simple = {pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL,
              pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT}
    groups = {}
    for point in anchors:
        if time.monotonic() >= deadline:
            raise ValueError('native_pad_boundary_deadline')
        marker = pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*point), pcbnew.VECTOR2I(*point), 1)
        touched = [i for i in own if i.GetEffectiveShape(layer).Collide(marker, 0)]
        if not touched:
            raise ValueError('source_boundary_has_no_retained_native_contact')
        pads = [i for i in touched if i.GetClass() == 'PAD'
            and i.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and not i.HasHole()
            and i.GetShape() in simple]
        if len(pads) > 1:
            raise ValueError('ambiguous_overlapping_native_boundary_lands')
        pad = pads[0] if pads else None
        key = ('pad', force._uid(pad)) if pad else ('point', *point)
        at = list(pad.GetPosition()) if pad else list(point)
        ids = [force._uid(pad)] if pad else sorted(force._uid(i) for i in touched)
        if not 1 <= len(ids) <= 16:
            raise ValueError('bounded_exact_boundary_contact_owners_required')
        group = groups.setdefault(key, dict(at_nm=at, native_uuids=ids,
            source_anchor_points_nm=[], actual_layer=layer,
            basis='one_actual_connected_convex_smd_land' if pad else 'unchanged_exact_native_point'))
        group['source_anchor_points_nm'].append(list(point))
    if len(groups) != 2:
        raise ValueError('two_actual_native_boundary_groups_required')
    ports = sorted(groups.values(), key=lambda p: tuple(p['at_nm']))
    if ports[0]['at_nm'] == ports[1]['at_nm']:
        raise ValueError('distinct_actual_native_boundary_port_centres_required')
    return dict(schema=1, scope='read_only_actual_surface_land_boundary_proposals',
        endpoints_nm=[p['at_nm'] for p in ports], ports=ports,
        source_external_anchor_count=len(anchors), source_pad_or_exact_point_groups=2,
        independently_restore_every_original_anchor_required=True,
        native_board_mutated=False, current_or_barrel_capacity_credited=False,
        release_authority=False)
