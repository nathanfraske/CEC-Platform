"""Purposeful source-retaining power contours and explicit symmetric via plans.

The model chooses the native source objects and style. The source-derived
current requirement determines the floor. No fictitious FEM copper, inferred
layer sharing or new barrel-capacity credit is introduced by this compiler.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict

from .identity import digest, require
from .legacy import bootstrap

bootstrap()


def parameters(board, source, operation, board_hint):
    import cec_full_current_planar_reflow as authority
    import cec_fab_profile as fab
    import cec_fr as fr

    tracks = {str(item.m_Uuid.AsString()): item for item in board.GetTracks()}
    ids = operation["track_uuids"]
    require(
        type(ids) is list
        and 1 <= len(ids) <= 128
        and len(set(ids)) == len(ids)
        and set(ids) <= tracks.keys(),
        "explicit_source_power_contour_tracks_required",
    )
    selected = [tracks[key] for key in ids]
    require(
        len({(item.GetNetname(), int(item.GetLayer())) for item in selected}) == 1,
        "one_literal_power_net_and_face_per_contour",
    )
    net, face = str(selected[0].GetNetname()), int(selected[0].GetLayer())
    # A thermal load and a deliberately larger conductor budget are distinct
    # source contracts. Use the existing typed routing authority, not the old
    # branch-subtraction helper's equality assumption. Preserve both exactly.
    kind, domain, contract = authority._model(board, source, net, board_hint)
    layer = fab.COPPER_LAYER_IDS.get(face)
    required = contract.get("required_by_layer_mm", {}).get(layer)
    require(
        type(required) in (int, float) and math.isfinite(required) and required > 0,
        "complete_source_power_current_width_required",
    )
    required_nm = math.ceil(required * 1e6)
    spec = fr._project_netclass_resolver(str(source))(net) or {}
    gap = max(
        int(board.GetDesignSettings().m_MinClearance),
        round(float(spec.get("clearance") or 0) * 1e6),
    )
    floors = [
        int(z.GetMinThickness())
        for z in board.Zones()
        if not z.GetIsRuleArea() and z.GetMinThickness() > 0
    ]
    require(floors, "source_zone_minimum_thickness_required")
    return dict(
        net=net,
        layer_id=face,
        required_width_nm=required_nm,
        clearance_nm=gap,
        min_thickness_nm=min(floors),
        current_domain=domain,
        current_domain_kind=kind,
        unchanged_current_contract=contract,
    )


def construct(board, source, operation, *, board_hint, request):
    if operation["kind"] == "power_route":
        return construct_route(
            board, source, operation, board_hint=board_hint, request=request
        )
    if operation["kind"] == "bank_collector":
        return construct_bank(
            board, source, operation, board_hint=board_hint, request=request
        )
    import cec_native_contour_regions as regions

    require(
        set(operation)
        == {
            "kind",
            "track_uuids",
            "style",
            "allow_locked_track_uuids",
            "allow_grouped_track_uuids",
        },
        "exact_source_power_operation_fields_required",
    )
    model = parameters(board, source, operation, board_hint)
    style = operation["style"]
    require(style in ("square", "chamfer45"), "purposeful_power_contour_style_required")
    locked = operation["allow_locked_track_uuids"]
    grouped = operation["allow_grouped_track_uuids"]
    require(
        set(locked) <= set(operation["track_uuids"])
        and set(grouped) <= set(operation["track_uuids"]),
        "power_permissions_outside_explicit_source_scope",
    )
    proposal = regions.plan(
        board,
        operation["track_uuids"],
        required_width_nm=model["required_width_nm"],
        clearance_nm=model["clearance_nm"],
        min_thickness_nm=model["min_thickness_nm"],
        contour_style=style,
        allow_locked_track_uuids=locked,
        allow_grouped_track_uuids=grouped,
        timeout_s=8.0,
    )
    zone_ids = [
        str(uuid.uuid5(uuid.NAMESPACE_URL, digest(request) + ":power:" + str(i)))
        for i in range(len(proposal["regions_nm"]))
    ]
    made = regions.materialize(
        board,
        proposal,
        allow_locked_track_uuids=locked,
        allow_grouped_track_uuids=grouped,
        zone_uuids=zone_ids,
        timeout_s=8.0,
    )
    regions.fill(board, proposal, made["zone_uuids"], timeout_s=8.0)
    return dict(
        kind="power_contour",
        source_current_model=model,
        contour_record=dict(plan=proposal, materialized=made),
        added_zone_uuids=zone_ids,
        source_tracks_retained=True,
        new_barrel_capacity_credited=False,
        new_current_or_thermal_qualification=False,
    )


def receive(source, candidate, operation, record, *, board_hint):
    """Rebind the current floor to the parent, then invoke saved typed receiving."""
    import pcbnew

    if operation["kind"] == "power_route":
        import cec_full_current_planar_reflow as planar

        return planar.receive(
            source,
            candidate,
            board_hint=board_hint,
            retired_track_uuids=operation["track_uuids"],
            timeout_s=10.0,
        )
    if operation["kind"] == "bank_collector":
        import cec_source_pad_bank_stage as bank

        return bank.receive(
            source,
            candidate,
            record["bank_plan"],
            zone_uuid=record["added_zone_uuids"][0],
            board_hint=board_hint,
            timeout_s=10.0,
        )
    import cec_native_contour_receiving as native

    model = parameters(pcbnew.LoadBoard(str(source)), source, operation, board_hint)
    require(
        digest(model) == digest(record["source_current_model"]),
        "power_source_current_requirement_changed",
    )
    plan = record["contour_record"]["plan"]
    require(
        all(
            plan[key] == model[key]
            for key in (
                "net",
                "layer_id",
                "required_width_nm",
                "clearance_nm",
                "min_thickness_nm",
            )
        ),
        "power_contour_requirement_not_independently_received",
    )
    return native.receive(
        source,
        candidate,
        [record["contour_record"]],
        board_hint=board_hint,
        sense_timeout_s=10.0,
    )


def _source_tree(tracks):
    """A bounded connected tree, including short branch tails, not a guessed chain.

    This is construction scope only. Saved receiving must still restore every
    native boundary and surviving partition, including branches not chosen as
    the replacement path's two endpoints.
    """
    graph = defaultdict(set)
    edges = set()
    for item in tracks:
        a, b = tuple(item.GetStart()), tuple(item.GetEnd())
        edge = frozenset((a, b))
        require(a != b and edge not in edges, "nondegenerate_unique_power_tree_edges_required")
        edges.add(edge)
        graph[a].add(b)
        graph[b].add(a)
    require(graph, "nonempty_power_source_tree_required")
    seen, pending = set(), [next(iter(graph))]
    while pending:
        node = pending.pop()
        if node not in seen:
            seen.add(node)
            pending.extend(graph[node] - seen)
    require(len(seen) == len(graph) == len(edges) + 1,
            "one_connected_acyclic_power_source_tree_required")
    return sorted(list(p) for p, adjacent in graph.items() if len(adjacent) == 1)


def construct_route(board, source, operation, *, board_hint, request):
    import pcbnew
    import cec_full_current_planar_reflow as planar
    from cec_native_items import discard_items
    from .geometry import path, length
    from .cells import emit_connections

    require(
        set(operation)
        == {"kind", "track_uuids", "points_nm", "allow_locked_track_uuids"},
        "exact_full_current_route_operation_fields_required",
    )
    model = planar.plan(
        board,
        source,
        board_hint=board_hint,
        retired_track_uuids=operation["track_uuids"],
        timeout_s=8.0,
    )
    live = {str(item.m_Uuid.AsString()): item for item in board.GetTracks()}
    cut = [live[key] for key in model["retired_track_uuids"]]
    allow = operation["allow_locked_track_uuids"]
    require(
        set(allow) <= set(model["retired_track_uuids"])
        and all(
            not item.IsLocked() or str(item.m_Uuid.AsString()) in allow for item in cut
        ),
        "exact_locked_full_current_cut_permission_required",
    )
    points = path(operation["points_nm"], minimum_phase_nm=20000)
    ports = _source_tree(cut)
    require(
        points[0] in ports and points[-1] in ports,
        "full_current_path_endpoints_must_be_exact_source_tree_leaves",
    )
    original_length = sum(item.GetLength() for item in cut)
    require(length(points) < original_length, "power_route_must_shorten_not_meander")
    locked = any(item.IsLocked() for item in cut)
    discard_items(board, cut)
    added = emit_connections(
        board,
        [
            dict(
                net=model["net"],
                layer=str(pcbnew.BOARD.GetStandardLayerName(model["layer_id"])),
                width_nm=model["width_nm"],
                points_nm=points,
            )
        ],
        [],
        identity=digest(request),
    )
    for item in board.GetTracks():
        if str(item.m_Uuid.AsString()) in added:
            item.SetLocked(locked)
    return dict(
        kind="power_route",
        source_current_model=model,
        added_track_uuids=added,
        retired_track_uuids=model["retired_track_uuids"],
        added_zone_uuids=[],
        source_width_face_and_current_retained=True,
        new_barrel_capacity_credited=False,
        source_tree_leaves_nm=ports,
        all_native_branch_boundaries_still_require_saved_receiving=True,
        saved_centerline_mm=round((original_length - length(points)) / 1e6, 6),
    )


def construct_bank(board, source, operation, *, board_hint, request):
    import pcbnew
    import cec_pad_bank_collector as bank
    import cec_fr as fr
    import cec_zone_fill as fill
    import cec_redundant_force_branch as authority

    require(
        set(operation)
        == {"kind", "pad_uuids", "support_track_uuids", "layer", "chamfer_nm"},
        "exact_source_bank_operation_fields_required",
    )
    pads = {
        str(pad.m_Uuid.AsString()): pad
        for fp in board.GetFootprints()
        for pad in fp.Pads()
    }
    require(
        type(operation["pad_uuids"]) is list
        and 2 <= len(operation["pad_uuids"]) <= 32
        and set(operation["pad_uuids"]) <= pads.keys(),
        "bounded_literal_bank_source_pads_required",
    )
    net = str(pads[operation["pad_uuids"][0]].GetNetname())
    domain, contract = authority._model(board, net, board_hint)
    spec = fr._project_netclass_resolver(str(source))(net) or {}
    gap = max(
        int(board.GetDesignSettings().m_MinClearance),
        round(float(spec.get("clearance") or 0) * 1e6),
    )
    floors = [
        int(zone.GetMinThickness())
        for zone in board.Zones()
        if not zone.GetIsRuleArea() and zone.GetMinThickness() > 0
    ]
    require(floors, "source_zone_feature_floor_required")
    proposal = bank.plan(
        board,
        operation["pad_uuids"],
        layer_id=board.GetLayerID(operation["layer"]),
        support_track_uuids=operation["support_track_uuids"],
        clearance_nm=gap,
        min_thickness_nm=min(floors),
        chamfer_nm=operation["chamfer_nm"],
        timeout_s=8.0,
    )
    made = bank.materialize(board, proposal)
    zone = next(
        zone
        for zone in board.Zones()
        if str(zone.m_Uuid.AsString()) == made["zone_uuid"]
    )
    identity = str(uuid.uuid5(uuid.NAMESPACE_URL, digest(request) + ":bank"))
    zone.m_Uuid.Clone(pcbnew.KIID(identity))
    selected = pcbnew.ZONES()
    selected.append(zone)
    fill.compile_selected(board, selected, timeout_s=8.0, initialize_selected=True)
    return dict(
        kind="bank_collector",
        bank_plan=proposal,
        added_zone_uuids=[identity],
        source_current_model=dict(domain=domain, contract=contract),
        source_conductors_retained=True,
        new_barrel_capacity_credited=False,
        new_current_or_thermal_qualification=False,
    )


def symmetric_grid(*, center_nm, rows, columns, pitch_nm):
    """Deterministic centered grid, not random scatter or an ampacity claim."""
    from .geometry import point

    center = point(center_nm)
    require(
        type(rows) is int
        and type(columns) is int
        and 1 <= rows <= 8
        and 1 <= columns <= 8
        and rows * columns <= 32,
        "bounded_explicit_via_grid_required",
    )
    require(
        type(pitch_nm) is int and 0 < pitch_nm <= 10_000_000,
        "positive_native_via_pitch_required",
    )
    require(
        ((rows - 1) * pitch_nm) % 2 == 0 and ((columns - 1) * pitch_nm) % 2 == 0,
        "via_grid_must_have_exact_integer_center",
    )
    x0 = center[0] - (columns - 1) * pitch_nm // 2
    y0 = center[1] - (rows - 1) * pitch_nm // 2
    return [
        point([x0 + c * pitch_nm, y0 + r * pitch_nm])
        for r in range(rows)
        for c in range(columns)
    ]
