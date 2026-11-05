"""Native observations and actual visible copper screening."""

from __future__ import annotations
import time
from pathlib import Path
from .legacy import ROOT, bootstrap

bootstrap()
import cec_suite_inspection as inspection
from . import geometry as design

from .identity import require


def _native():
    import cec_swig_guard

    cec_swig_guard.pin()
    import pcbnew, wx

    quiet = wx.LogNull()
    return pcbnew, quiet


def native_world(source, board_hint):
    pcbnew, quiet = _native()
    board = pcbnew.LoadBoard(str(source))
    import cec_ordinary_route_receiving as ordinary
    import cec_fr as fr

    settings = board.GetDesignSettings()
    limits = {
        name: int(getattr(settings, name))
        for name in (
            "m_MinClearance",
            "m_TrackMinWidth",
            "m_ViasMinSize",
            "m_MinThroughDrill",
            "m_HoleToHoleMin",
            "m_HoleClearance",
            "m_CopperEdgeClearance",
            "m_ViasMinAnnularWidth",
        )
        if type(getattr(settings, name, None)) is int
    }
    stack = [
        dict(
            id=int(layer),
            name=str(pcbnew.BOARD.GetStandardLayerName(layer)),
            saved_label=str(board.GetLayerName(layer)),
        )
        for layer in board.GetEnabledLayers().CuStack()
    ]
    resolve = fr._project_netclass_resolver(str(source), board=board)
    names = sorted(
        {
            str(item.GetNetname())
            for _code, item in board.GetNetInfo().NetsByNetcode().items()
            if item.GetNetname()
        }
    )
    require(len(names) <= 4096, "bounded_source_netclass_inventory_required")
    classes = {}
    for name in names:
        spec = resolve(name) or {}
        classes[name] = {
            key: spec[key]
            for key in (
                "name",
                "clearance",
                "track_width",
                "via_diameter",
                "via_drill",
                "track_width_by_layer_mm",
            )
            if key in spec
        }

    uid = lambda t: str(t.m_Uuid.AsString())
    pos = lambda p: [int(p.x), int(p.y)]
    grouped = {uid(i) for g in board.Groups() for i in g.GetItems()}
    require(
        len(list(board.GetTracks())) <= 16384
        and len(list(board.GetFootprints())) <= 4096
        and len(list(board.Zones())) <= 256,
        "bounded_native_world_required",
    )
    tracks = []
    vias = []
    for t in board.GetTracks():
        row = dict(
            uuid=uid(t),
            net=str(t.GetNetname()),
            locked=bool(t.IsLocked()),
            grouped=uid(t) in grouped,
        )
        if t.GetClass() == "PCB_VIA":
            row.update(
                at=pos(t.GetPosition()),
                diameter_nm=t.GetWidth(pcbnew.F_Cu),
                drill_nm=t.GetDrillValue(),
            )
            vias.append(row)
        else:
            row.update(
                kind=t.GetClass(),
                layer=int(t.GetLayer()),
                layer_name=str(pcbnew.BOARD.GetStandardLayerName(t.GetLayer())),
                a=pos(t.GetStart()),
                b=pos(t.GetEnd()),
                width_nm=int(t.GetWidth()),
            )
            tracks.append(row)
    fps = []
    for f in board.GetFootprints():
        fps.append(
            dict(
                uuid=uid(f),
                ref=f.GetReference(),
                value=f.GetValue(),
                footprint=f.GetFPIDAsString(),
                at=pos(f.GetPosition()),
                rotation_deg=f.GetOrientationDegrees(),
                side="B" if f.IsFlipped() else "F",
                fields={str(v.GetName()): str(v.GetText()) for v in f.GetFields()},
                locked=bool(f.IsLocked()),
                pads=[
                    dict(
                        uuid=uid(p),
                        pin=str(p.GetNumber()),
                        net=str(p.GetNetname()),
                        at=pos(p.GetPosition()),
                        size_nm=pos(p.GetSize()),
                        drill_nm=pos(p.GetDrillSize()),
                        rotation_deg=p.GetOrientationDegrees(),
                        layers=[int(l) for l in p.GetLayerSet().CuStack()],
                    )
                    for p in f.Pads()
                ],
            )
        )
    zones = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        poly = z.Outline()
        contours = []
        for i in range(poly.OutlineCount()):
            contour = poly.COutline(i)
            contours.append(
                [pos(contour.CPoint(k)) for k in range(contour.PointCount())]
            )
        zones.append(
            dict(
                uuid=uid(z),
                net=z.GetNetname(),
                name=z.GetZoneName(),
                locked=bool(z.IsLocked()),
                layers=[int(l) for l in z.GetLayerSet().CuStack()],
                outlines_nm=contours,
                hole_count=sum(poly.HoleCount(i) for i in range(poly.OutlineCount())),
                saved_fill_islands=sum(
                    z.GetFilledPolysList(l).OutlineCount()
                    for l in z.GetLayerSet().CuStack()
                    if z.HasFilledPolysForLayer(l)
                ),
            )
        )
    try:
        eligible = sorted(ordinary.eligible_nets(board, source, board_hint))
        eligibility = "source-derived"
    except (ValueError, KeyError, FileNotFoundError) as exc:
        eligible = []
        eligibility = "unknown; no ordinary construction permission: " + str(exc)
    return dict(
        schema=1,
        source=str(source),
        sha256=inspection.sha(source),
        units="native_integer_nanometres",
        saved_global_limits_nm=limits,
        source_netclass_geometry_mm=classes,
        layer_stack=stack,
        local_rules_can_override_global_limits=True,
        properties={str(k): str(v) for k, v in board.GetProperties().items()},
        board=board_hint,
        ordinary_nets=eligible,
        ordinary_role_status=eligibility,
        tracks=tracks,
        vias=vias,
        footprints=fps,
        zones=zones,
        release_authority=False,
    )


def visible_delta(source, candidate, retired, added):
    """Reject centerline-only changes covered by unchanged native copper.

    Exact conservative native polygon subtraction is a cosmetic screening
    tool, not an electrical/current certificate. No area epsilon waives a
    remnant, and pads/vias are considered before expensive filled zones.
    """
    pcbnew, quiet = _native()
    before, after = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
    uid = lambda t: str(t.m_Uuid.AsString())
    deadline = time.monotonic() + 3.0
    old = {uid(t): t for t in before.GetTracks()}
    new = {uid(t): t for t in after.GetTracks()}

    def poly(item, face, outside):
        value = pcbnew.SHAPE_POLY_SET()
        item.TransformShapeToPolygon(
            value,
            face,
            0,
            1,
            pcbnew.ERROR_OUTSIDE if outside else pcbnew.ERROR_INSIDE,
            False,
        )
        return value

    groups = {(str(old[u].GetNetname()), int(old[u].GetLayer())) for u in retired}
    changes = []
    for net, face in sorted(groups):
        first = pcbnew.SHAPE_POLY_SET()
        last = pcbnew.SHAPE_POLY_SET()
        for u in retired:
            if str(old[u].GetNetname()) == net and int(old[u].GetLayer()) == face:
                first.BooleanAdd(poly(old[u], face, True))
        for u in added:
            if str(new[u].GetNetname()) == net and int(new[u].GetLayer()) == face:
                last.BooleanAdd(poly(new[u], face, True))
        removed = first.CloneDropTriangulation()
        removed.BooleanSubtract(last)
        inserted = last.CloneDropTriangulation()
        inserted.BooleanSubtract(first)
        retained = [
            *(p for f in before.GetFootprints() for p in f.Pads()),
            *(t for t in before.GetTracks() if uid(t) not in retired),
            *(z for z in before.Zones() if not z.GetIsRuleArea()),
        ]
        for item in retained:
            if not removed.OutlineCount() and not inserted.OutlineCount():
                break
            require(time.monotonic() < deadline, "visible_material_delta_deadline")
            if str(item.GetNetname()) != net or not item.IsOnLayer(face):
                continue
            if item.GetClass() == "ZONE":
                if not item.HasFilledPolysForLayer(face):
                    continue
                cover = item.GetFilledPolysList(face)
            else:
                cover = poly(item, face, False)
            removed.BooleanSubtract(cover)
            inserted.BooleanSubtract(cover)
        changes.append(
            dict(
                net=net,
                layer=face,
                removed_exposed_area_nm2=removed.Area(),
                inserted_exposed_area_nm2=inserted.Area(),
                silhouette_changed=bool(
                    removed.OutlineCount() or inserted.OutlineCount()
                ),
            )
        )
    return dict(
        complete=True,
        groups=changes,
        exposed_copper_changed=any(c["silhouette_changed"] for c in changes),
        scope="cosmetic_native_silhouette_screen_not_current_or_continuity_proof",
    )
