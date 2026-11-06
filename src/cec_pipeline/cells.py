"""Source-owned connected cell moves with explicit agent-authored connections.

The retained ownership compiler supplies cuts and obligations, not placements
or a route search. The model supplies exact poses and paths. Saved receiving
rederives ownership independently; a construction report cannot grant it.
"""

from __future__ import annotations

import math
import time
import uuid

from . import geometry
from .identity import digest, require
from .legacy import bootstrap

bootstrap()


def normalize_poses(values, *, limit=8):
    require(type(limit) is int and 1 <= limit <= 32, "bounded_pose_inventory_required")
    require(
        type(values) is list and 1 <= len(values) <= limit,
        "bounded_explicit_cell_poses_required",
    )
    poses = {}
    for value in values:
        require(
            type(value) is dict
            and set(value) == {"reference", "at_nm", "rotation_deg"},
            "exact_cell_pose_fields_required",
        )
        ref, turn = value["reference"], value["rotation_deg"]
        require(
            type(ref) is str and ref and ref not in poses,
            "unique_cell_references_required",
        )
        require(type(turn) is int and turn % 90 == 0, "cardinal_cell_rotation_required")
        point = geometry.point(value["at_nm"])
        poses[ref] = [point[0] / 1e6, point[1] / 1e6, turn % 360]
    return poses


def plan(board, operation, board_hint):
    import cec_cell_escape_replan as escape

    uid = lambda item: str(item.m_Uuid.AsString())
    poses = normalize_poses(operation["poses"])
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    require(set(poses) <= footprints.keys(), "cell_source_footprint_missing")
    moved = {
        ref
        for ref, target in poses.items()
        if list(footprints[ref].GetPosition()) != [round(v * 1e6) for v in target[:2]]
        or abs((footprints[ref].GetOrientationDegrees() - target[2] + 180) % 360 - 180)
        > 1e-9
    }
    require(moved, "cell_construction_requires_actual_motion")
    allowed = operation["allow_locked_footprint_uuids"]
    require(
        type(allowed) is list
        and len(set(allowed)) == len(allowed)
        and set(allowed) <= {uid(footprints[ref]) for ref in moved},
        "exact_moving_footprint_lock_scope_required",
    )
    require(
        all(
            not footprints[ref].IsLocked() or uid(footprints[ref]) in allowed
            for ref in moved
        ),
        "locked_cell_owner_not_explicitly_scoped",
    )
    track_allow = operation["allow_locked_track_uuids"]
    require(
        type(track_allow) is list
        and len(track_allow) <= 256
        and len(set(track_allow)) == len(track_allow),
        "bounded_cell_track_lock_scope_required",
    )
    shift = operation.get("max_shift_nm", 6_000_000)
    reference_groups = operation.get("reference_group_uuids", [])
    require(
        type(reference_groups) is list
        and len(reference_groups) <= 8
        and all(type(value) is str and value for value in reference_groups)
        and len(set(reference_groups)) == len(reference_groups),
        "explicit_source_reference_group_uuid_scope_required",
    )
    require(
        type(shift) is int and 0 < shift <= 32_000_000, "bounded_cell_motion_required"
    )
    proposal = escape.prepare(
        board,
        poses,
        board_hint=board_hint,
        max_shift_mm=shift / 1e6,
        allow_owned_locked_escapes=bool(track_allow),
        rebuild_projected_ground=False,
        reference_group_uuids=reference_groups,
    )
    retired = set(proposal["retired_track_uuids"])
    tracks = {uid(item): item for item in board.GetTracks()}
    require(
        set(track_allow) <= retired, "cell_lock_permission_outside_source_owned_cuts"
    )
    require(
        all(not tracks[key].IsLocked() or key in track_allow for key in retired),
        "locked_source_cell_departure_not_explicitly_scoped",
    )
    return proposal, moved


def emit_connections(board, routes, vias, *, identity):
    import pcbnew
    import cec_fr as fr
    import cec_native_rule_areas as rule_areas

    require(
        type(routes) is list
        and len(routes) <= 64
        and type(vias) is list
        and len(vias) <= 32,
        "bounded_explicit_cell_connections_required",
    )
    incoming = []
    enabled = set(board.GetEnabledLayers().CuStack())
    settings = board.GetDesignSettings()
    for index, route in enumerate(routes):
        require(
            type(route) is dict
            and set(route) == {"net", "layer", "width_nm", "points_nm"},
            "exact_connection_fields_required",
        )
        net = board.FindNet(route["net"])
        require(net is not None and net.GetNetCode() > 0, "literal_source_net_required")
        face = board.GetLayerID(route["layer"])
        require(face in enabled, "source_enabled_copper_layer_required")
        width = route["width_nm"]
        require(
            type(width) is int and settings.m_TrackMinWidth <= width <= 20_000_000,
            "native_connection_width_required",
        )
        # Typed pin escapes may legitimately be shorter than their width.
        # Native process, full-width contact and source-role receiving still
        # decide those landings; cosmetic ordinary-chain rules are different.
        points = geometry.path(route["points_nm"], minimum_phase_nm=20_000)
        foreign_zones, foreign = fr._foreign_shape_indexes(
            board, face, {net.GetNetCode()}
        )
        spec = (
            fr._project_netclass_resolver(str(board.GetFileName()))(route["net"]) or {}
        )
        gap = max(
            int(settings.m_MinClearance), round(float(spec.get("clearance") or 0) * 1e6)
        )
        forbidden = [
            row["shape"]
            for row in rule_areas.areas(board, "tracks")
            if face in row["layers"]
        ]
        for leg, (left, right) in enumerate(zip(points, points[1:])):
            a, b = pcbnew.VECTOR2I(*left), pcbnew.VECTOR2I(*right)
            shape = pcbnew.SHAPE_SEGMENT(a, b, width)
            require(
                fr._edge_leg_clear(board, a, b, (width + 1) // 2)
                and fr._snapshot_foreign_clear(a, b, width, gap, foreign_zones, foreign)
                and not any(item.Collide(shape, 0) for item in forbidden),
                "explicit_cell_connection_foreign_copper_edge_or_keepout",
            )
            track = pcbnew.PCB_TRACK(board)
            track.SetNet(net)
            track.SetLayer(face)
            track.SetWidth(width)
            track.SetStart(a)
            track.SetEnd(b)
            track.m_Uuid.Clone(
                pcbnew.KIID(
                    str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            identity + ":route:" + str(index) + ":" + str(leg),
                        )
                    )
                )
            )
            board.Add(track)
            incoming.append(str(track.m_Uuid.AsString()))
    for index, value in enumerate(vias):
        require(
            type(value) is dict
            and set(value) == {"net", "at_nm", "diameter_nm", "drill_nm"},
            "exact_cell_via_fields_required",
        )
        at = geometry.point(value["at_nm"])
        diameter, drill = value["diameter_nm"], value["drill_nm"]
        require(
            type(diameter) is int
            and type(drill) is int
            and diameter >= settings.m_ViasMinSize
            and drill >= settings.m_MinThroughDrill
            and (diameter - drill) >= 2 * settings.m_ViasMinAnnularWidth,
            "saved_process_via_dimensions_required_no_implicit_exception",
        )
        net = board.FindNet(value["net"])
        require(
            net is not None and net.GetNetCode() > 0, "literal_source_via_net_required"
        )
        via = pcbnew.PCB_VIA(board)
        via.SetNet(net)
        via.SetPosition(pcbnew.VECTOR2I(*at))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetWidth(diameter)
        via.SetDrill(drill)
        via.m_Uuid.Clone(
            pcbnew.KIID(
                str(uuid.uuid5(uuid.NAMESPACE_URL, identity + ":via:" + str(index)))
            )
        )
        board.Add(via)
        incoming.append(str(via.m_Uuid.AsString()))
    return incoming


def construct(board, operation, *, board_hint, request):
    import cec_cell_escape_replan as escape

    require(
        not operation.get("vias"),
        "new_barrels_require_add_connections_before_connected_pose_reconstruction",
    )

    require(
        set(operation)
        <= {
            "kind",
            "poses",
            "routes",
            "vias",
            "allow_locked_footprint_uuids",
            "allow_locked_track_uuids",
            "max_shift_nm",
            "reference_group_uuids",
        }
        and {
            "kind",
            "poses",
            "routes",
            "allow_locked_footprint_uuids",
            "allow_locked_track_uuids",
        }
        <= set(operation),
        "exact_source_cell_operation_fields_required",
    )
    proposal, moved = plan(board, operation, board_hint)
    escape.apply_private(board, proposal)
    added = emit_connections(
        board, operation["routes"], operation.get("vias", []), identity=digest(request)
    )
    return dict(
        kind="place_cell",
        moved_refs=sorted(moved),
        affected_footprint_uuids=sorted(
            str(fp.m_Uuid.AsString())
            for fp in board.GetFootprints()
            if fp.GetReference() in moved
        ),
        retired_track_uuids=proposal["retired_track_uuids"],
        added_track_uuids=added,
        allow_locked_track_uuids=operation["allow_locked_track_uuids"],
        reference_group_uuids=operation.get("reference_group_uuids", []),
        source_owned_obligations_recompiled=True,
        max_shift_nm=operation.get("max_shift_nm", 6_000_000),
        source_plan=proposal,
        independent_saved_receiving_required=True,
    )


def preview(source, operation, board_hint):
    import pcbnew
    import cec_cell_escape_replan as escape

    parent = pcbnew.LoadBoard(str(source))
    proposal, moved = plan(parent, operation, board_hint)
    projected = pcbnew.LoadBoard(str(source))
    escape.apply_private(projected, proposal)
    requests = escape.obligations(parent, projected, proposal)
    return dict(
        ok=True,
        complete=True,
        moved_refs=sorted(moved),
        retired_track_uuids=proposal["retired_track_uuids"],
        source_owned_connections=requests,
        route_search_run=False,
        source_modified=False,
        release_authority=False,
    )
