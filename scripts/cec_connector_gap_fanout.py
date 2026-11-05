"""Bounded, native two-row PTH gap fan-out proposals.

This is an explicitly private geometry construction tool, NOT a current-width
exception. It derives gaps from native lands, fans a selected row through the
other row, and recombines on retained copper or a selected plated land. No
source copper is retired here. Parallel paths, pad barrels and inner layers
earn no current/sharing qualification from a geometric success.
"""
from __future__ import annotations

import hashlib
import json
import math
import time


class Refused(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()


def _uid(item):
    return str(item.m_Uuid.AsString())


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise Refused("native_gap_fanout_deadline")


def _inventory_digest(board):
    import cec_field_coupling as field
    inventory = field._field_snapshot_inventory(board)
    return _digest(sorted((list(k), v) for k, v in inventory.items()))


def _ids(values, minimum, maximum):
    if (not isinstance(values, (tuple, list)) or not minimum <= len(values) <= maximum
            or any(type(v) is not str or not v for v in values)
            or len(set(values)) != len(values)):
        raise Refused("explicit_unique_native_gap_source_ids_required")
    return list(values)


def plan(board, root_pad_uuids, *, layer_widths_nm, allowed_layers,
         collector_track_uuids=(), merge_pad_uuids=(), clearance_nm,
         reserve_nm=25000, chamfer_nm=1000000, timeout_s=10.):
    """Read-only native proposal, with actual refusal identities per branch.

    Widths are caller-selected EXPERIMENTAL widths, never auto-rated. The
    clearance floor cannot be lowered below the saved project/native rules.
    ``reserve_nm`` adds a radial construction margin to the collision screen.
    All selected layers must be enabled, allowed and not board-scale planes.
    Only cardinal, aligned two-row plated connector grids are supported.
    """
    import pcbnew
    import cec_fr as fr
    import cec_fab_profile as fab

    roots = _ids(root_pad_uuids, 1, 8)
    collectors = _ids(collector_track_uuids, 0, 8)
    merges = _ids(merge_pad_uuids, 0, 8)
    if (type(layer_widths_nm) is not dict or not 1 <= len(layer_widths_nm) <= 4
            or any(type(k) is not str or type(v) is not int or not 1 <= v <= 10000000
                   for k, v in layer_widths_nm.items())
            or not isinstance(allowed_layers, (list, tuple))
            or len(set(allowed_layers)) != len(allowed_layers)
            or any(type(v) is not str for v in allowed_layers)
            or type(clearance_nm) is not int or not 1 <= clearance_nm <= 10000000
            or type(reserve_nm) is not int or not 1 <= reserve_nm <= 100000
            or type(chamfer_nm) is not int or not 1 <= chamfer_nm <= 10000000
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise Refused("bounded_explicit_native_gap_policy_required")
    deadline = time.monotonic() + timeout_s
    if clearance_nm < int(board.GetDesignSettings().m_MinClearance):
        raise Refused("native_gap_clearance_below_board_minimum")
    # Profile/routing contracts use canonical KiCad layer names. User labels
    # such as SIG1/PWR must neither hide an enabled layer nor alias a plane.
    enabled = set(fab.enabled_copper_layers(board))
    plane_ids = {int(board.GetLayerID(name)) for name in fr.plane_layers(board)}
    if (not set(layer_widths_nm) <= enabled & set(allowed_layers)
            or any(int(board.GetLayerID(name)) in plane_ids for name in layer_widths_nm)):
        raise Refused("native_gap_layer_disabled_forbidden_or_plane")
    pads = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            _tick(deadline)
            if len(pads) >= 32768 or _uid(pad) in pads:
                raise Refused("native_gap_pad_inventory_bound_or_ambiguity")
            pads[_uid(pad)] = pad
    tracks = {_uid(t): t for t in board.GetTracks()}
    if len(tracks) > 32768 or not set(roots + merges) <= pads.keys() or not set(collectors) <= tracks.keys():
        raise Refused("native_gap_explicit_source_missing_or_inventory_bound")
    selected = [pads[u] for u in roots]
    fp = selected[0].GetParentFootprint()
    net = str(selected[0].GetNetname()); code = selected[0].GetNetCode()
    if (not net or code <= 0 or fp.IsDNP()
            or any(_uid(p.GetParentFootprint()) != _uid(fp) or p.GetNetCode() != code
                   for p in selected)):
        raise Refused("native_gap_same_populated_connector_and_net_required")
    rowpads = [p for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and p.HasHole()]
    if not 4 <= len(rowpads) <= 128:
        raise Refused("bounded_two_row_native_plated_connector_required")
    xs = {p.GetPosition().x for p in rowpads}; ys = {p.GetPosition().y for p in rowpads}
    if len(ys) == 2 and len(xs) >= 2:
        axis = 0
    elif len(xs) == 2 and len(ys) >= 2:
        axis = 1
    else:
        raise Refused("cardinal_aligned_two_row_native_connector_required")

    def uv(point):
        xy = (int(point.x), int(point.y))
        return xy if axis == 0 else xy[::-1]

    def xy(point):
        return list(point if axis == 0 else point[::-1])

    root_v = {uv(p.GetPosition())[1] for p in selected}
    if (len(root_v) != 1 or any(p not in rowpads for p in selected)):
        raise Refused("selected_roots_must_share_one_actual_plated_row")
    root_v = next(iter(root_v))
    crossed_v = next(v for v in {uv(p.GetPosition())[1] for p in rowpads} if v != root_v)
    toward = 1 if crossed_v > root_v else -1
    columns = sorted({uv(p.GetPosition())[0] for p in rowpads})
    if any({uv(p.GetPosition())[0] for p in rowpads if uv(p.GetPosition())[1] == v} != set(columns)
           for v in (root_v, crossed_v)):
        raise Refused("native_rows_have_misaligned_or_missing_columns")
    if len(set(uv(p.GetPosition()) for p in rowpads)) != len(rowpads):
        raise Refused("native_gap_duplicate_physical_land_centres")
    merge = [pads[u] for u in merges]
    if any(p not in rowpads or p.GetNetCode() != code or uv(p.GetPosition())[1] != crossed_v for p in merge):
        raise Refused("native_gap_merge_must_be_actual_same_net_crossed_row_pth")
    import cec_route_dimensions as dimensions
    filename = board.GetFileName()
    resolved = dimensions.project_resolver(filename, board=board,
        table=None if filename else dimensions.NetclassTable(source="unsaved_native_board"))
    required_clearance = max(clearance_nm, fr._nm(float((resolved(net) or {}).get("clearance") or .2)))
    if required_clearance < 0:
        raise Refused("native_gap_invalid_project_clearance")
    valid, refused, screens = [], [], {}
    source_facts = []
    for p in rowpads:
        _tick(deadline)
        source_facts.append(dict(uuid=_uid(p), net=str(p.GetNetname()), number=str(p.GetNumber()),
            position_nm=list(p.GetPosition()), size_nm=list(p.GetSize()),
            drill_nm=list(p.GetDrillSize()), orientation_deg=p.GetOrientationDegrees()))
    for layer_name, width in sorted(layer_widths_nm.items()):
        _tick(deadline)
        layer = board.GetLayerID(layer_name)
        if any(not p.IsOnLayer(layer) for p in selected):
            raise Refused("native_gap_root_has_no_actual_target_layer_land")
        anchors = []
        for uid in collectors:
            t = tracks[uid]; a, z = uv(t.GetStart()), uv(t.GetEnd())
            if t.GetClass() != "PCB_TRACK" or t.GetNetCode() != code:
                raise Refused("native_gap_collector_must_be_actual_same_net_track")
            if int(t.GetLayer()) != int(layer):
                continue
            if a[1] != z[1] or a == z or toward * (a[1] - crossed_v) <= 0:
                raise Refused("native_gap_collector_must_be_cardinal_and_beyond_crossed_row")
            anchors.append((uid, sorted((a[0], z[0])), a[1]))
        if len(anchors) > 1:
            raise Refused("native_gap_ambiguous_retained_layer_collector")
        if not anchors and not merge:
            raise Refused("native_gap_layer_has_no_retained_recombination_anchor")
        all_shapes = fr._layer_foreign_shapes(board, layer, {code}, identified=True)
        screens[layer] = all_shapes
        for root in selected:
            ru, rv = uv(root.GetPosition()); ci = columns.index(ru)
            if ci == 0 or ci == len(columns) - 1:
                raise Refused("native_gap_root_needs_two_actual_neighbour_gaps")
            for neighbour in (columns[ci - 1], columns[ci + 1]):
                _tick(deadline)
                if (ru + neighbour) % 2:
                    raise Refused("native_gap_nonintegral_midpoint_refused")
                gap = (ru + neighbour) // 2; departure = abs(gap - ru)
                if departure >= abs(crossed_v - rv):
                    raise Refused("native_gap_no_between_row_45_degree_departure")
                points = [(ru, rv), (gap, rv + toward * departure)]
                if anchors:
                    anchor_uid, extent, anchor_v = anchors[0]
                    if not extent[0] <= gap <= extent[1]:
                        raise Refused("native_gap_retained_collector_does_not_cover_launch_column")
                    points.append((gap, anchor_v))
                    anchor = tracks[anchor_uid]
                else:
                    # The shared spine is outside actual crossed-row copper,
                    # not a footprint/nominal-height proxy. Both bends are 45.
                    anchor = min(merge, key=lambda p: abs(uv(p.GetPosition())[0] - gap))
                    if not anchor.IsOnLayer(layer):
                        raise Refused("native_gap_merge_has_no_actual_target_layer_land")
                    mu, mv = uv(anchor.GetPosition())
                    half_extent = max((p.GetEffectiveShape(layer).BBox().GetHeight()
                        if axis == 0 else p.GetEffectiveShape(layer).BBox().GetWidth()) // 2
                        for p in rowpads if uv(p.GetPosition())[1] == crossed_v)
                    turn_v = crossed_v + toward * (half_extent + required_clearance + (width + 1) // 2 + reserve_nm)
                    spine_v = turn_v + toward * chamfer_nm
                    along = 1 if mu > gap else -1
                    if abs(mu - gap) <= 2 * chamfer_nm:
                        raise Refused("native_gap_insufficient_recombination_chamfer_span")
                    points += [(gap, turn_v), (gap + along * chamfer_nm, spine_v),
                               (mu - along * chamfer_nm, spine_v), (mu, turn_v), (mu, mv)]
                    anchor_uid = _uid(anchor)
                hits = []; material_ok = True
                for a, z in zip(points, points[1:]):
                    _tick(deadline)
                    start, end = pcbnew.VECTOR2I(*xy(a)), pcbnew.VECTOR2I(*xy(z))
                    dx, dy = abs(start.x - end.x), abs(start.y - end.y)
                    if not (dx or dy) or dx and dy and dx != dy:
                        raise Refused("native_gap_non_octilinear_or_collapsed_leg")
                    if not fr._edge_leg_clear(board, start, end, width / 2 + required_clearance + reserve_nm):
                        material_ok = False
                    shape = pcbnew.SHAPE_SEGMENT(start, end, width + 2 * reserve_nm)
                    for collection in all_shapes:
                        for obstacle in collection:
                            _tick(deadline)
                            fact = obstacle[2] or {}
                            clear = 0 if fact.get("kind") == "native_track_rule_area" else max(required_clearance, obstacle[3])
                            if obstacle[0].Collide(shape, clear):
                                hits.append(dict(fact))
                endpoint = pcbnew.VECTOR2I(*xy(points[-1]))
                native_contact = bool(anchor.HitTest(endpoint))
                row = dict(root_pad_uuid=_uid(root), neighbour_column_nm=neighbour,
                    gap_column_nm=gap, layer=layer_name, width_nm=width,
                    points_nm=[xy(p) for p in points], retained_anchor_uuid=anchor_uid,
                    native_anchor_contact=native_contact, material_clear=material_ok,
                    foreign_clear=not hits, native_blockers=[dict(r) for r in { _digest(h): h for h in hits }.values()])
                (valid if native_contact and material_ok and not hits else refused).append(row)
    result = dict(schema=1, scope="private_native_gap_geometry_not_current_or_release_qualification",
        request=dict(root_pad_uuids=roots, layer_widths_nm=layer_widths_nm,
            allowed_layers=list(allowed_layers), collector_track_uuids=collectors,
            merge_pad_uuids=merges, clearance_nm=clearance_nm,
            reserve_nm=reserve_nm, chamfer_nm=chamfer_nm),
        source_inventory_sha256=_inventory_digest(board), source_pad_geometry=source_facts,
        net=net, row_axis=axis, root_row_nm=root_v, crossed_row_nm=crossed_v,
        actual_clearance_nm=required_clearance, valid_paths=valid, refused_paths=refused,
        geometry_complete=True, all_requested_paths_clear=not refused,
        root_geometry_coverage_complete={r["root_pad_uuid"] for r in valid} == set(roots),
        source_copper_retired=False, arbitrary_equal_current_sharing_assumed=False,
        current_qualified=False, barrel_capacity_qualified=False, routing_admitted=False,
        release_authority=False, source_selected=False)
    _tick(deadline)
    result["plan_sha256"] = _digest(result)
    return result


def materialize_private(board, proposal, *, timeout_s=10.):
    """Replay the whole read-only plan before adding experimental tracks.

    This never grants selection/admission, and refuses partially blocked
    requests. Explicit source retirement and independent native connectivity,
    fault, current, Kelvin and matched-stack receiving remain the caller's job.
    """
    import pcbnew
    import cec_parallel_copper as parallel
    import cec_retained_route_reuse as reuse
    check = dict(proposal); digest = check.pop("plan_sha256", None)
    if digest != _digest(check) or check.get("current_qualified") is not False or check.get("release_authority") is not False:
        raise Refused("native_gap_proposal_identity_or_authority_changed")
    if _inventory_digest(board) != check["source_inventory_sha256"]:
        raise Refused("native_gap_board_changed_since_plan")
    req = check["request"]
    replay = plan(board, req["root_pad_uuids"], **{k: v for k, v in req.items() if k != "root_pad_uuids"}, timeout_s=timeout_s)
    if replay != proposal or not replay["all_requested_paths_clear"] or not replay["root_geometry_coverage_complete"]:
        raise Refused("native_gap_private_plan_incomplete_or_changed")
    segments = []
    for row in replay["valid_paths"]:
        segments.extend((*a, *z, row["width_nm"], row["layer"])
                        for a, z in zip(row["points_nm"], row["points_nm"][1:]))
    # Collinear proposed spines are one physical conductor, not extra capacity.
    rows = parallel.normalize_proposals(segments)
    pending = []
    for layer_name in sorted(req["layer_widths_nm"]):
        layer = board.GetLayerID(layer_name)
        proposed = [(pcbnew.VECTOR2I(int(a),int(b)), pcbnew.VECTOR2I(int(c),int(d)), int(w))
                    for a,b,c,d,w,l in rows if l == layer_name]
        pending.extend((a,z,w,layer) for a,z,w in reuse.native_uncovered_plan(board,replay["net"],proposed,layer))
    if not pending or len(pending) > 256:
        raise Refused("native_gap_experimental_track_inventory_bound")
    added = []
    for a,z,width,layer in pending:
        t = pcbnew.PCB_TRACK(board); t.SetNetCode(board.GetNetcodeFromNetname(replay["net"]))
        t.SetLayer(layer); t.SetWidth(width); t.SetStart(a); t.SetEnd(z); t.SetLocked(True)
        board.Add(t); added.append(_uid(t))
    return dict(added_track_uuids=added, no_added_vias=True, no_source_cut=True,
        current_qualified=False, routing_admitted=False, release_authority=False, source_selected=False)
