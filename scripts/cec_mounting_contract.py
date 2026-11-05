"""Declared mount count/geometry admission, independent of placement heuristics.

Hardware clearance is a board input, not an inferred screw/washer standard.
The native checker is read-only and includes both component faces. Native DRC
separately checks copper against the footprint's outer-layer rule areas.
"""
from __future__ import annotations

import math


def repair_radial_drill_field(footprint, min_gap_mm, *, guard_mm=0.05):
    """Repair an explicitly owned mount's radial stitching-hole positions.

    Bore, primary land, hardware envelope, pose, pad sizes, nets and layers are
    immutable. This is not a clearance or mechanical qualification grant;
    enclosing saved-board receiving must check all foreign copper and holes.
    Already compliant fields are left alone, rather than retroactively adding
    the repair guard to the manufacturing floor.
    """
    import pcbnew
    report = dict(complete=False, applicable=True, changes=[],
                  release_authority=False, scope='declared_radial_stitch_positions_only')
    try:
        if any(isinstance(v, bool) or not math.isfinite(v) or v < 0
               for v in (min_gap_mm, guard_mm)) or min_gap_mm <= 0:
            raise ValueError('invalid_radial_drill_spacing_authority')
        pads = list(footprint.Pads())
        if not 4 <= len(pads) <= 65:
            raise ValueError('unsupported_radial_pad_inventory')
        for p in pads:
            if (p.GetAttribute() != pcbnew.PAD_ATTRIB_PTH or
                p.GetShape() != pcbnew.PAD_SHAPE_CIRCLE or
                p.GetDrillShape() != pcbnew.PAD_DRILL_SHAPE_CIRCLE or
                p.GetDrillSize().x != p.GetDrillSize().y or
                p.GetSize().x != p.GetSize().y or
                not 0 < p.GetDrillSize().x < p.GetSize().x):
                raise ValueError('unsupported_radial_pad_geometry')
        ordered = sorted(pads, key=lambda p: p.GetDrillSize().x, reverse=True)
        central, satellites = ordered[0], ordered[1:]
        if central.GetDrillSize().x <= satellites[0].GetDrillSize().x:
            raise ValueError('ambiguous_central_mount_bore')
        if any(p.GetNumber() != central.GetNumber() or
               p.GetNetCode() != central.GetNetCode() or
               tuple(p.GetLayerSet().Seq()) != tuple(central.GetLayerSet().Seq())
               for p in satellites):
            raise ValueError('radial_field_terminal_or_layer_identity_mismatch')
        cx, cy = central.GetPosition().x, central.GetPosition().y
        vectors = [(p.GetPosition().x-cx, p.GetPosition().y-cy) for p in satellites]
        radii = [math.hypot(*v) for v in vectors]
        if min(radii) <= 0 or max(radii)-min(radii) > 2:
            raise ValueError('unsupported_nonuniform_radial_field')
        original_gaps = [math.dist((p.GetPosition().x, p.GetPosition().y),
                          (q.GetPosition().x, q.GetPosition().y))
                          -(p.GetDrillSize().x+q.GetDrillSize().x)/2
                          for i, p in enumerate(pads) for q in pads[i+1:]]
        if min(original_gaps) >= min_gap_mm*1e6:
            report.update(complete=True, applied_count=0,
                          minimum_gap_mm=min(original_gaps)/1e6)
            return report
        units = [(x/r, y/r) for (x, y), r in zip(vectors, radii)]
        floor = (min_gap_mm + guard_mm)*1e6
        needed = max(radii)
        for p in satellites:
            needed = max(needed, (central.GetDrillSize().x+p.GetDrillSize().x)/2 + floor)
        for i, p in enumerate(satellites):
            for j in range(i+1, len(satellites)):
                distance = math.dist(units[i], units[j])
                if distance <= 0:
                    raise ValueError('duplicate_radial_satellite_direction')
                needed = max(needed, ((p.GetDrillSize().x+satellites[j].GetDrillSize().x)/2
                                     + floor)/distance)
        needed = math.ceil(needed) + 2  # retain the floor after integer rounding
        if any(needed + p.GetSize().x/2 > central.GetSize().x/2 for p in satellites):
            raise ValueError('radial_spacing_exceeds_immutable_contact_envelope')
        proposals = [(p, (round(cx+ux*needed), round(cy+uy*needed)))
                     for p, (ux, uy) in zip(satellites, units)]
        positions = [(central, (cx, cy))] + proposals
        for i, (p, a) in enumerate(positions):
            for q, b in positions[i+1:]:
                gap = math.dist(a, b)-(p.GetDrillSize().x+q.GetDrillSize().x)/2
                if gap < floor:
                    raise ValueError('integer_radial_spacing_does_not_meet_guard')
        for p, point in proposals:
            old = (p.GetPosition().x, p.GetPosition().y)
            if old != point:
                report['changes'].append(dict(uuid=p.m_Uuid.AsString(), before_nm=list(old),
                                              after_nm=list(point)))
                p.SetPosition(pcbnew.VECTOR2I(*point))
        report.update(complete=True, applied_count=len(report['changes']),
                      original_radius_mm=sum(radii)/len(radii)/1e6,
                      proposed_radius_mm=needed/1e6, minimum_guard_mm=guard_mm,
                      central_pad_and_bore_unchanged=True,
                      satellite_sizes_drills_and_terminals_unchanged=True)
    except Exception as exc:
        by_id = {p.m_Uuid.AsString(): p for p in footprint.Pads()}
        for row in report['changes']:
            by_id[row['uuid']].SetPosition(pcbnew.VECTOR2I(*row['before_nm']))
        report.update(applied_count=0, error='%s: %s' % (type(exc).__name__, exc))
    return report


def repair_declared_radial_fields(board, declarations, min_gap_mm, *,
                                 guard_mm=0.05, allow_locked_footprint_uuids=()):
    """Exact ref/FPID declarations authorize scope, never arbitrary terminals."""
    allowed = {str(uid) for uid in allow_locked_footprint_uuids}
    details = []
    for ref, libid in sorted(declarations.items()):
        matches = [fp for fp in board.GetFootprints() if fp.GetReference() == str(ref)]
        row = dict(reference=str(ref), declared_fpid=str(libid), applied_count=0)
        if len(matches) != 1 or matches[0].GetFPIDAsString() != str(libid):
            row.update(complete=False, error='missing_duplicate_or_changed_mount_declaration')
        elif matches[0].IsLocked() and matches[0].m_Uuid.AsString() not in allowed:
            row.update(complete=False, error='locked_mount_requires_explicit_geometry_authority')
        else:
            row.update(repair_radial_drill_field(matches[0], min_gap_mm, guard_mm=guard_mm))
        details.append(row)
    return dict(complete=all(row['complete'] for row in details), details=details,
                applied_count=sum(row['applied_count'] for row in details),
                release_authority=False)


def repair_native_mount_fields(board, rules, *, board_path=None,
                              allow_locked_footprint_uuids=()):
    """Factory-repair entry for explicitly marked mounting-hole footprints.

    Native library role AND BOM/position exclusion identify mechanical mounts.
    No refdes, coordinate or product name participates in candidate selection.
    Through-hole connector arrays are never inferred to be mounting fields.
    Only multi-hole circular fields are eligible; other mounts are untouched.
    """
    import pcbnew
    from cec_fab_native_geometry import hole_rule_floor
    report = dict(complete=False, applied_count=0, details=[], release_authority=False)
    try:
        values = [rules[key] for key in ('h2h', 'h2h_pad_pad')]
        if any(isinstance(v, bool) or not math.isfinite(v) or v < 0 for v in values):
            raise ValueError('invalid_mount_hole_spacing_authority')
        source_floor, source = hole_rule_floor(board_path) if board_path else (0., {'present': False})
        floor = max(*values, source_floor, board.GetDesignSettings().m_HoleToHoleMin/1e6)
        if not math.isfinite(floor) or floor <= 0:
            raise ValueError('missing_mount_hole_spacing_authority')
        required_attributes = pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
        declarations = {}
        for fp in board.GetFootprints():
            if (str(fp.GetFPID().GetLibItemName()).startswith('MountingHole_') and
                fp.GetAttributes() & required_attributes == required_attributes and
                len(list(fp.Pads())) >= 4):
                if fp.GetReference() in declarations:
                    raise ValueError('duplicate_native_mount_declaration')
                declarations[fp.GetReference()] = fp.GetFPIDAsString()
        report.update(repair_declared_radial_fields(board, declarations, floor,
            allow_locked_footprint_uuids=allow_locked_footprint_uuids),
            minimum_gap_mm=floor, source_dru=source)
    except Exception as exc:
        report['error'] = '%s: %s' % (type(exc).__name__, exc)
    return report


def positive(value, name):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("%s must be finite and positive" % name)
    return number


def _polygons(outline):
    from shapely.geometry import Polygon
    result = []
    for i in range(outline.OutlineCount()):
        def points(contour):
            return [(contour.CPoint(j).x/1e6, contour.CPoint(j).y/1e6)
                    for j in range(contour.PointCount())]
        polygon = Polygon(points(outline.Outline(i)),
            [points(outline.Hole(i, h)) for h in range(outline.HoleCount(i))])
        if not polygon.is_valid:
            raise ValueError("invalid mechanical outline polygon")
        result.append(polygon)
    return result


def board_evidence(board, expected, *, drill_mm, hardware_diameter_mm,
                   clearance_mm=0.25, hole_type="npth", tolerance_mm=0.05,
                   net_name=None, contact_diameter_mm=None):
    """Check explicit board-relative mount centers against native board truth.

    ``expected`` is an arbitrary ref -> (x, y) map. No product, reference
    selector, absolute board coordinate, or silent omission is encoded here.
    Courtyard AABBs are conservative; this gate does not establish mechanical
    strength, screw length, torque or fan/standoff compatibility.
    """
    import pcbnew
    drill_mm = positive(drill_mm, "mount_drill_mm")
    radius = positive(hardware_diameter_mm, "mount_hardware_diameter_mm") / 2
    clearance_mm = positive(clearance_mm, "mount_hardware_clearance_mm")
    tolerance_mm = positive(tolerance_mm, "mount_tolerance_mm")
    contact = (positive(contact_diameter_mm, 'mount_contact_diameter_mm')
               if contact_diameter_mm is not None else None)
    if contact is not None and (hole_type != 'pth' or not net_name or contact <= drill_mm):
        raise ValueError('a declared contact requires a grounded plated annulus')
    if not expected or hole_type not in ("npth", "pth"):
        raise ValueError("required mounts need positions and an explicit hole type")
    from cec_board_geometry import outline_bbox_mm
    from shapely.geometry import Point
    from shapely.ops import unary_union
    x0, y0, x1, y1 = outline_bbox_mm(board)
    native_outline = pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(native_outline, False):
        raise ValueError("mount support requires a closed board outline")
    substrate = unary_union(_polygons(native_outline))
    fps = list(board.GetFootprints())
    rows, violations = [], []
    attribute = (pcbnew.PAD_ATTRIB_NPTH if hole_type == "npth"
                 else pcbnew.PAD_ATTRIB_PTH)
    for ref, target in sorted(expected.items()):
        matches = [fp for fp in fps if fp.GetReference() == ref]
        row = {"ref": ref, "expected_mm": [x0 + target[0], y0 + target[1]],
               "hardware_diameter_mm": 2 * radius, "violations": []}
        if len(matches) != 1:
            row["violations"].append("missing_or_duplicate_mount")
        else:
            fp = matches[0]
            x, y = fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6
            row["position_mm"] = [x, y]
            if math.hypot(x - row["expected_mm"][0], y - row["expected_mm"][1]) > tolerance_mm:
                row["violations"].append("mount_displaced_from_declared_position")
            if min(x-x0, x1-x, y-y0, y1-y) < radius + clearance_mm - tolerance_mm:
                row["violations"].append("hardware_envelope_out_of_bounds")
            if not substrate.buffer(1e-6).covers(Point(x,y).buffer(radius + clearance_mm)):
                row["violations"].append("hardware_envelope_crosses_edge_or_cutout")
            holes = [p for p in fp.Pads() if
                     p.GetAttribute() == attribute and
                     abs(p.GetDrillSize().x / 1e6 - drill_mm) <= tolerance_mm and
                     abs(p.GetDrillSize().y / 1e6 - drill_mm) <= tolerance_mm and
                     math.hypot(p.GetPosition().x / 1e6 - x,
                                p.GetPosition().y / 1e6 - y) <= tolerance_mm]
            row["matching_holes"] = len(holes)
            if len(holes) != 1:
                row["violations"].append("wrong_drill_type_size_or_center")
            if hole_type == "npth" and any(p.GetNetCode() for p in holes):
                row["violations"].append("isolated_mechanical_hole_has_electrical_net")
            if hole_type == "pth" and net_name:
                for pad in fp.Pads():
                    if pad.GetNetname() != net_name:
                        row["violations"].append("mount_not_on_declared_net")
                    if pad.GetLocalZoneConnection() != pcbnew.ZONE_CONNECTION_FULL:
                        row["violations"].append("mount_not_solid_plane_connected")
                for pad in holes:
                    diameter = min(pad.GetSize().x, pad.GetSize().y)/1e6
                    if contact is not None:
                        row['contact_diameter_mm'] = diameter
                        if any(abs(size/1e6-contact) > tolerance_mm
                               for size in (pad.GetSize().x, pad.GetSize().y)):
                            row['violations'].append('wrong_ground_contact_diameter')
                        # A slimmer exposed ring must not invite a live net
                        # beneath a wider conductive screw/washer allowance.
                        required = max(0., radius + clearance_mm - diameter/2)
                        local = (pad.GetLocalClearance() or 0)/1e6
                        row['foreign_copper_clearance_mm'] = local
                        if diameter < 2*radius and local < required-1e-6:
                            row['violations'].append('missing_hardware_foreign_copper_clearance')
                    elif diameter < 2*radius-tolerance_mm:
                        row["violations"].append("ground_contact_smaller_than_hardware")
            if hole_type == "npth":
                # An isolated screw cannot rely on solder mask over a live
                # power pour. Require persistent native exclusion on BOTH
                # exposed copper faces, not merely a drawn review circle.
                keepouts = {pcbnew.F_Cu: [], pcbnew.B_Cu: []}
                for zone in fp.Zones():
                    if not (zone.GetIsRuleArea() and zone.GetDoNotAllowTracks()
                            and zone.GetDoNotAllowVias() and zone.GetDoNotAllowPads()
                            and zone.GetDoNotAllowZoneFills()):
                        continue
                    for polygon in _polygons(zone.Outline()):
                        for layer in keepouts:
                            if zone.GetLayerSet().Contains(layer):
                                keepouts[layer].append(polygon)
                envelope = Point(x, y).buffer(radius)
                for layer, polygons in keepouts.items():
                    if not unary_union(polygons).buffer(1e-6).covers(envelope):
                        row["violations"].append("missing_hardware_copper_keepout:%s" %
                                                 board.GetLayerName(layer))
            # Both faces: a screw is not a same-face-only placement object.
            for other in fps:
                if other is fp or other.GetReference() == ref:
                    continue
                for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
                    poly = other.GetCourtyard(layer)
                    if not poly.OutlineCount():
                        continue
                    box = poly.BBox()
                    dx = max(box.GetLeft()/1e6-x, 0, x-box.GetRight()/1e6)
                    dy = max(box.GetTop()/1e6-y, 0, y-box.GetBottom()/1e6)
                    if math.hypot(dx, dy) < radius + clearance_mm - 1e-6:
                        row["violations"].append("hardware_conflict:%s:%s" %
                            (other.GetReference(), board.GetLayerName(layer)))
            for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
                poly = fp.GetCourtyard(layer)
                if not poly.OutlineCount():
                    row["violations"].append("missing_hardware_courtyard:%s" % layer)
                    continue
                box = poly.BBox()
                if min(x-box.GetLeft()/1e6, box.GetRight()/1e6-x,
                       y-box.GetTop()/1e6, box.GetBottom()/1e6-y) < radius + clearance_mm - tolerance_mm:
                    row["violations"].append("undersized_hardware_courtyard:%s" % layer)
        violations += [{"ref": ref, "reason": reason} for reason in row["violations"]]
        rows.append(row)
    return {"schema": 1, "ok": not violations, "applicable": True,
            "required_count": len(expected), "details": rows,
            "violations": violations, "mechanical_qualification": False}


def reconcile(board, declarations, *, net_name=None, reference_visible=None):
    """Apply explicit mechanical footprint declarations without moving datums.

    The caller owns ref/footprint policy. Only declared identities are touched;
    nets must already exist. Tracks, zones and unrelated footprints are intact.
    """
    from pathlib import Path
    import pcbnew
    import cec_pcb
    from cec_native_items import discard_items
    net = board.FindNet(str(net_name)) if net_name else None
    if net_name and (net is None or net.GetNetCode() <= 0):
        raise ValueError("declared mounting net is absent: %s" % net_name)
    changed = []
    for ref, libid in sorted(declarations.items()):
        fp = board.FindFootprintByReference(str(ref))
        if fp is None:
            raise ValueError("declared mounting footprint is absent: %s" % ref)
        if str(fp.GetFPIDAsString()) != str(libid):
            nick, name = str(libid).split(":", 1)
            path = Path(cec_pcb.fp_path(nick, name))
            replacement = pcbnew.FootprintLoad(str(path.parent), name)
            if replacement is None:
                raise ValueError("declared mounting footprint cannot be loaded")
            replacement.SetFPID(pcbnew.LIB_ID(nick, name))
            replacement.SetReference(str(ref))
            replacement.SetPosition(fp.GetPosition())
            replacement.SetOrientationDegrees(fp.GetOrientationDegrees())
            if fp.IsFlipped():
                replacement.Flip(replacement.GetPosition(), False)
            replacement.SetLocked(fp.IsLocked())
            discard_items(board, [fp]); board.Add(replacement); fp = replacement
            changed.append(str(ref))
        if (reference_visible is not None
                and fp.Reference().IsVisible() != bool(reference_visible)):
            fp.Reference().SetVisible(bool(reference_visible))
            if str(ref) not in changed: changed.append(str(ref))
        if net is not None:
            for pad in fp.Pads():
                if pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
                    raise ValueError("grounded mount contains an unplated pad")
                if pad.GetNetname() != net_name or pad.GetLocalZoneConnection() != pcbnew.ZONE_CONNECTION_FULL:
                    pad.SetNet(net); pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
                    if str(ref) not in changed: changed.append(str(ref))
    return {"ok": True, "changed": changed}
