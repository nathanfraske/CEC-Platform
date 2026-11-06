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


def linear_stage_option(operation):
    value = operation.get("allow_linear_power_stage_reconstruction", False)
    require(type(value) is bool, "explicit_linear_power_stage_boolean_required")
    return value


def source_boundary_span_option(operation):
    """Explicit native work reach only; never ownership or current credit."""
    name = "max_source_boundary_span_nm"
    value = operation.get(name, 8_000_000)
    require(type(value) is int and 1 <= value <= 32_000_000,
            "bounded_explicit_source_boundary_span_required")
    require(name not in operation or operation.get("native_macro") is True,
            "source_boundary_span_requires_native_macro")
    return value


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

    linear_stage = linear_stage_option(operation)
    require("max_source_boundary_span_nm" not in operation,
            "source_boundary_span_requires_native_macro")
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
        allow_linear_power_stage_reconstruction=linear_stage,
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
    """Add an explicit connection batch atomically, including failed probes.

    Checks may fail after earlier legs/routes have been added. Those tentative
    objects must never become obstacles or apparent connectivity for a retry.
    This is rollback only; all existing geometry/process checks still apply.
    """
    original = {str(item.m_Uuid.AsString()) for item in board.GetTracks()}
    try:
        return _emit_connections(board, routes, vias, identity=identity)
    except BaseException:
        for item in list(board.GetTracks()):
            if str(item.m_Uuid.AsString()) not in original:
                board.Remove(item)
        raise


def _emit_connections(board, routes, vias, *, identity):
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
    existing = {str(item.m_Uuid.AsString()) for item in board.GetTracks()}
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
            uid = str(track.m_Uuid.AsString())
            require(uid not in existing and board.ResolveItem(track.m_Uuid, True) is None,
                    "new_connection_identity_must_not_alias_existing_native_item")
            board.Add(track)
            existing.add(uid)
            incoming.append(uid)
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
        uid = str(via.m_Uuid.AsString())
        require(uid not in existing and board.ResolveItem(via.m_Uuid, True) is None,
                "new_connection_identity_must_not_alias_existing_native_item")
        board.Add(via)
        existing.add(uid)
        incoming.append(uid)
    return incoming


def construct(board, operation, *, board_hint, request):
    import cec_cell_escape_replan as escape

    linear_stage_option(operation)
    source_boundary_span_option(operation)
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
            "native_macro",
            "allow_locked_transport_uuids",
            "allow_linear_power_stage_reconstruction",
            "max_source_boundary_span_nm",
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
    require(type(operation.get("native_macro", False)) is bool,
            "explicit_native_macro_boolean_required")
    packet = None
    transported = []
    if operation.get("native_macro", False):
        moved = set(normalize_poses(operation["poses"]))
        projected, packet, transported = compile_macro(board, operation, board_hint)
        proposal = packet["source_plan"]
        board = projected
    else:
        require("allow_locked_transport_uuids" not in operation,
                "transport_lock_scope_requires_native_macro")
        proposal, moved = plan(board, operation, board_hint)
        escape.apply_private(board, proposal)
    added = emit_connections(
        board, operation["routes"], operation.get("vias", []), identity=digest(request)
    )
    result = dict(
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
    if packet is not None:
        result.update(native_macro_packet=packet, native_macro_packet_version=1,
                      transported_source_copper_uuids=transported)
        # Internal-only native frame; never serialize this object in receipts.
        result["_native_board"] = board
        result["source_plan"] = packet["source_plan"]
        result["retired_track_uuids"] = packet["retired_track_uuids"]
    return result


def compile_macro(board, operation, board_hint, *, enforce_locks=True):
    """Fresh compiler output owns transport; no caller packet/ID allowlist."""
    import cec_cell_macro_requests as compiler
    import cec_control_gate_bias_placement as native
    import cec_force_current as force
    import pcbnew
    import cec_cell_row_rebuild as row
    linear_stage = linear_stage_option(operation)
    boundary_span = source_boundary_span_option(operation)
    require(row._source_binding(board)==row._source_binding(
        pcbnew.LoadBoard(str(board.GetFileName()))), "native_macro_requires_exact_saved_source")
    poses = normalize_poses(operation["poses"])
    footprints = {f.GetReference(): f for f in board.GetFootprints()}
    require(set(poses) <= footprints.keys(), "cell_source_footprint_missing")
    moved={ref for ref,target in poses.items() if list(footprints[ref].GetPosition())!=
           [round(v*1e6)for v in target[:2]] or
           (footprints[ref].GetOrientationDegrees()-target[2])%360!=0}
    require(moved,"cell_construction_requires_actual_motion")
    fp_locks=operation["allow_locked_footprint_uuids"]
    require(type(fp_locks)is list and len(set(fp_locks))==len(fp_locks)
            and set(fp_locks)<={force._uid(footprints[r])for r in moved},
            "exact_moving_footprint_lock_scope_required")
    require(all(not footprints[r].IsLocked()or force._uid(footprints[r])in fp_locks
                for r in moved),"locked_cell_owner_not_explicitly_scoped")
    projected, packet = compiler.compile(
        board.GetFileName(), poses, board_hint=board_hint,
        max_shift_mm=operation.get("max_shift_nm", 6_000_000) / 1e6,
        # Observation and construction compile the SAME positively owned cut
        # scope. Caller consent is checked per fresh ID below; it must never
        # choose a different ownership model by being empty/nonempty.
        timeout_s=10., allow_owned_locked_escapes=True,
        max_obstacle_track_mm=boundary_span / 1e6,
        reference_group_uuids=operation.get("reference_group_uuids", ()),
        compilation_phase_timeouts_s=(10.,)*(9 if linear_stage else 8),
        allow_linear_power_stage_reconstruction=linear_stage)
    require(packet.get("schema") == 1 and packet.get("scope") ==
            "source_typed_complete_native_macro_requests", "typed_native_macro_packet_required")
    old = {force._uid(t): native._track(board,t) for t in board.GetTracks()}
    new = {force._uid(t): native._track(projected,t) for t in projected.GetTracks()}
    retired = set(packet["retired_track_uuids"])
    require(old.keys() - new.keys() == retired and not new.keys() - old.keys(),
            "exact_compiler_source_copper_population_required")
    allowed = set(operation["allow_locked_track_uuids"])
    raw_allowed=operation["allow_locked_track_uuids"]
    require(type(raw_allowed)is list and len(raw_allowed)<=256 and len(allowed)==len(raw_allowed)
            and allowed<=retired,"exact_macro_source_cut_lock_scope_required")
    require(not enforce_locks or all(not old[u]["locked"] or u in allowed for u in retired),
            "locked_macro_source_cut_not_explicitly_scoped")
    transported = sorted(u for u in new if old[u] != new[u])
    transport = packet["transport"]
    authorized = set(packet["source_plan"].get("row_plan", {}).get("transformed_track_uuids", []))
    for name in ("changes", "source_process_barrel_motion",
                 "explicit_source_typed_ordinary_barrel_motion",
                 "explicitly_reproved_private_signal_port_reseats",
                 "explicitly_reproved_private_signal_return_reseats"):
        authorized.update(q["uuid"] for q in transport.get(name, []))
    authorized.update(q["uuid"] for q in packet.get(
        "source_factory_ground_pickups_carried_without_retirement", []))
    require(set(transported) <= authorized,
            "native_macro_changed_unowned_source_copper")
    scope=operation.get("allow_locked_transport_uuids",[])
    require(type(scope)is list and len(scope)<=128 and len(set(scope))==len(scope)
            and set(scope)<=set(transported),"exact_native_macro_transport_lock_scope_required")
    require(not enforce_locks or all(not old[u]["locked"]or u in scope for u in transported),
            "locked_macro_source_transport_not_explicitly_scoped")
    return projected, packet, transported


def preview(source, operation, board_hint):
    import pcbnew
    import cec_cell_escape_replan as escape

    source_boundary_span_option(operation)
    parent = pcbnew.LoadBoard(str(source))
    require(type(operation.get("native_macro", False)) is bool,
            "explicit_native_macro_boolean_required")
    if operation.get("native_macro", False):
        _, packet, transported = compile_macro(parent,operation,board_hint,enforce_locks=False)
        source_tracks={str(t.m_Uuid.AsString()):t for t in parent.GetTracks()}
        return dict(ok=True,complete=True,moved_refs=sorted(packet["source_plan"]["poses"]),
                    retired_track_uuids=packet["retired_track_uuids"],
                    source_owned_connections=packet["requests"],
                    native_macro_packet=packet,native_macro_packet_version=1,
                    transported_source_copper_uuids=transported,
                    required_locked_transport_uuids=[u for u in transported if source_tracks[u].IsLocked()],
                    required_locked_cut_uuids=[u for u in packet["retired_track_uuids"] if source_tracks[u].IsLocked()],
                    route_search_run=False,source_modified=False,release_authority=False)
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


def receive_macro(source, candidate, operation, record, board_hint):
    """Receipt claims cannot replace fresh compiler and independent receiving."""
    import pcbnew
    import cec_complete_macro_cell as receiving
    linear_stage = linear_stage_option(operation)
    boundary_span = source_boundary_span_option(operation)
    require(operation.get("native_macro") is True, "explicit_native_macro_mode_required")
    _, packet, transported = compile_macro(pcbnew.LoadBoard(str(source)), operation, board_hint)
    require(record.get("native_macro_packet_version") == 1
            and record.get("native_macro_packet") == packet
            and record.get("transported_source_copper_uuids") == transported,
            "fresh_exact_native_macro_construction_packet_required")
    return receiving.receive(source,candidate,board_hint=board_hint,timeout_s=10.,
        max_shift_mm=operation.get("max_shift_nm",6000000)/1e6,
        allow_owned_locked_escapes=True,
        max_obstacle_track_mm=boundary_span / 1e6,
        reference_group_uuids=operation.get("reference_group_uuids",()),
        compilation_phase_timeouts_s=(10.,)*(9 if linear_stage else 8),
        native_pose_phase_timeouts_s=(10.,)*3,
        pose_selection_phase_timeouts_s=(10.,)*4,
        allow_linear_power_stage_reconstruction=linear_stage)
