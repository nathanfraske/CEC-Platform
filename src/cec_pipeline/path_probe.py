"""Read-only, all-guards geometric scout for an explicit native path.

Keepout freedom alone is not route clearance. This combines the existing
native full-width copper/hole/reserved-fill, permission and edge predicates,
with obstruction identities. It does not grant ownership, connectivity,
current, stack or DRC authority and never inserts/removes board material.
"""

from contextlib import contextmanager
from . import geometry
from .identity import require
from .legacy import bootstrap

bootstrap()


@contextmanager
def _fresh_edges(board):
    """The legacy edge cache is immutable only within a construction pass."""
    absent = object()
    previous = getattr(board, "_cec_edge_leg_cache", absent)
    if previous is not absent:
        delattr(board, "_cec_edge_leg_cache")
    try:
        yield
    finally:
        if previous is not absent:
            board._cec_edge_leg_cache = previous
        elif hasattr(board, "_cec_edge_leg_cache"):
            delattr(board, "_cec_edge_leg_cache")


def inspect(board, *, net, layer, width_nm, points_nm, clearance_nm):
    import pcbnew
    import cec_fr as fr
    import cec_native_rule_areas as rules

    signal = board.FindNet(net)
    require(signal is not None and signal.GetNetCode() > 0,
            "literal_probe_net_required")
    face = board.GetLayerID(layer)
    require(face in set(board.GetEnabledLayers().CuStack()),
            "enabled_probe_copper_layer_required")
    settings = board.GetDesignSettings()
    require(type(width_nm) is int
            and max(1, int(settings.m_TrackMinWidth)) <= width_nm <= 20_000_000,
            "bounded_process_probe_width_required")
    require(type(clearance_nm) is int and 0 <= clearance_nm <= 20_000_000,
            "bounded_probe_clearance_required")
    points = geometry.path(points_nm, minimum_phase_nm=20_000)
    filename = str(board.GetFileName())
    spec = (fr._project_netclass_resolver(filename)(net) or {}) if filename else {}
    gap = max(clearance_nm, int(settings.m_MinClearance),
              round(float(spec.get("clearance") or 0) * 1e6))
    # Retain the shared construction guard, even if the saved minimum is less.
    edge = max(500_000, int(settings.m_CopperEdgeClearance))
    unknown = []
    unfilled = []
    zones, copper = fr._identified_foreign_shape_indexes(board, face, {signal.GetNetCode()})
    # The routing-policy snapshot deliberately allows antipads in ordinary
    # plane fills. A read-only existing-copper scout must inventory those too.
    zone_rows = list(zones["rows"])
    copper_rows = list(copper["rows"])
    item_gap = fr._foreign_clearance_resolver(board)
    for zone in board.Zones():
        if (not zone.GetIsRuleArea() and face in zone.GetLayerSet().CuStack()
                and zone.GetNetCode() != signal.GetNetCode()):
            identity = dict(kind="actual_foreign_zone_fill", uuid=zone.m_Uuid.AsString(),
                            net=zone.GetNetname(), layer=layer)
            clearance = max(gap, int(zone.GetLocalClearance()), item_gap(zone, face))
            if not zone.IsFilled() or not zone.HasFilledPolysForLayer(face):
                unfilled.append((zone.Outline(), clearance, dict(identity, kind="unfilled_foreign_zone")))
            else:
                fill = zone.GetFilledPolysList(face)
                zone_rows.append((fill, fill.BBox(), identity, clearance))
    # Existing helpers have legacy extraction fallbacks. Missing physical
    # inventory is UNKNOWN here, never an obstacle silently disappearing.
    inventory = {(r[2].get("kind"), r[2].get("uuid")) for r in copper_rows}
    expected = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            uid = pad.m_Uuid.AsString()
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH and pad.HasHole():
                expected.append(("npth_hole", uid))
            if pad.GetNetCode() != signal.GetNetCode() and face in pad.GetLayerSet().CuStack():
                expected.append(("pad", uid))
        expected.extend(("footprint_graphic", g.m_Uuid.AsString())
                        for g in fp.GraphicalItems() if g.GetLayer() == face)
    for track in board.GetTracks():
        if track.GetNetCode() != signal.GetNetCode() and track.IsOnLayer(face):
            expected.append(("via" if track.GetClass() == "PCB_VIA" else "track",
                             track.m_Uuid.AsString()))
    unknown.extend(dict(kind="native_shape_missing", object_kind=kind, uuid=uid)
                   for kind, uid in expected if (kind, uid) not in inventory)
    for graphic in board.GetDrawings():
        if graphic.GetLayer() != face:
            continue
        identity = dict(kind="board_copper_graphic", uuid=graphic.m_Uuid.AsString())
        try:
            shape = graphic.GetEffectiveShape()
            copper_rows.append((shape, shape.BBox(), identity, gap))
        except Exception:
            unknown.append(dict(identity, kind="native_shape_missing"))
    zones, copper = fr._bucket_foreign_shapes(zone_rows), fr._bucket_foreign_shapes(copper_rows)
    outline = pcbnew.SHAPE_POLY_SET()
    outline_known = bool(board.GetBoardPolygonOutlines(outline, False) and outline.OutlineCount())
    if not outline_known:
        unknown.append(dict(kind="native_outline_unavailable"))
    rows = []
    with _fresh_edges(board):
        for a, b in zip(points, points[1:]):
            start, end = pcbnew.VECTOR2I(*a), pcbnew.VECTOR2I(*b)
            capsule = pcbnew.SHAPE_SEGMENT(start, end, width_nm)
            local_unknown = list(unknown)
            for area, clearance, identity in unfilled:
                if area.Collide(capsule, clearance):
                    local_unknown.append(identity)
            foreign_clear = fr._snapshot_foreign_clear(start, end, width_nm, gap, zones, copper)
            hits = fr._snapshot_foreign_blockers(start, end, width_nm, gap, zones, copper, limit=17)
            local_unknown.extend(h for h in hits if h.get("geometry_status") == "unknown")
            permission = rules.track_conflict(board, start, end, width_nm, face)
            edge_clear = (fr._edge_leg_clear(board, start, end, (width_nm + 1)//2,
                                            edge_mm=edge/1e6) if outline_known else None)
            blocked = any(h.get("geometry_status") != "unknown" for h in hits) or permission is not None or edge_clear is False
            state = "blocked" if blocked else "unknown" if local_unknown or not foreign_clear else "clear"
            rows.append(dict(start_nm=a, end_nm=b, foreign_copper_and_holes_clear=foreign_clear,
                             permission_clear=permission is None, permission_hit=permission,
                             edge_clear=edge_clear, blockers=hits[:16], unknown=local_unknown,
                             blockers_truncated=len(hits) > 16, status=state,
                             geometry_screen_clear=state == "clear"))
    return dict(schema=1, scope="read_only_explicit_path_geometry_not_route_acceptance",
                net=net, layer=layer, width_nm=width_nm, clearance_nm=gap,
                edge_clearance_nm=edge, points_nm=points, unknown=unknown,
                project_context=filename or "unsaved_board_settings_only",
                legs=rows, geometry_screen_clear=all(r["geometry_screen_clear"] for r in rows),
                ownership_checked=False, connectivity_checked=False, current_qualified=False,
                stack_checked=False, native_DRC_run=False, release_authority=False)
