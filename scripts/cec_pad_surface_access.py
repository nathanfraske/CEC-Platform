"""Bounded native interior-copper contacts, not terminal ampacity authority.

The finite search samples an unchanged pad's actual flashed copper on one
enabled layer. Every returned point owns a nonzero interior copper disk,
outside any native drilled hole. No bounding-box fallback, neckdown exception,
barrel capacity, current splitting, route clearance or thermal approval is
implied. Callers still own the entire full-width route and admission proof.
"""
from __future__ import annotations

from collections import Counter
import math
import time


SCOPE = "native_layer_interior_copper_contact_only"
MAX_AXIS_SAMPLES = 33
MAX_CONTACT_INSET_NM = 500_000
MAX_COORDINATE_NM = 2_147_483_647
MAX_CAP_AXIS_SAMPLES = 65
MAX_CAP_WIDTH_NM = 100_000_000


def _parameters(layer, contact_inset_nm, *, axis_samples=None, deadline=None):
    if type(layer) is not int or not 0 <= layer <= 127:
        raise ValueError("layer must be a native layer integer")
    if (type(contact_inset_nm) is not int
            or not 1 <= contact_inset_nm <= MAX_CONTACT_INSET_NM):
        raise ValueError("contact_inset_nm must be an integer in [1, 500000]")
    if (axis_samples is not None and (type(axis_samples) is not int
            or not 2 <= axis_samples <= MAX_AXIS_SAMPLES)):
        raise ValueError("axis_samples must be an integer in [2, 33]")
    if deadline is not None and (type(deadline) not in (int, float)
            or not math.isfinite(deadline) or deadline < 0):
        raise ValueError("deadline must be a finite nonnegative monotonic time")


def _point(point_nm):
    if (not isinstance(point_nm, (list, tuple)) or len(point_nm) != 2
            or any(type(value) is not int or abs(value) > MAX_COORDINATE_NM
                   for value in point_nm)):
        raise ValueError("point_nm must contain two bounded integer coordinates")
    return list(point_nm)


def _base(pad, layer, contact_inset_nm):
    position = pad.GetPosition()
    footprint = pad.GetParentFootprint()
    return dict(schema=1, scope=SCOPE, geometry_only=True,
        electrical_capacity_qualified=False, release_authority=False,
        no_path_proof=False, layer_id=layer, contact_inset_nm=contact_inset_nm,
        boundary_guard_nm=1,
        native_error_location="ERROR_INSIDE",
        proof="interior_copper_disk_and_native_hole_exclusion",
        pad=dict(uuid=str(pad.m_Uuid.AsString()),
            footprint_uuid=str(footprint.m_Uuid.AsString()) if footprint else None,
            ref=str(footprint.GetReference()) if footprint else None,
            number=str(pad.GetNumber()), net=str(pad.GetNetname()),
            position_nm=[int(position.x), int(position.y)]))


def _geometry(pad, layer):
    """Keep every native owner alive for the whole bounded sample pass."""
    import pcbnew
    import cec_board_geometry as geometry
    try:
        if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            return None, "npth_pad_has_no_conductive_access"
        board = pad.GetBoard()
        if board is None:
            return None, "missing_native_board_context"
        if layer not in board.GetEnabledLayers().CuStack():
            return None, "layer_not_enabled_copper"
        if not pad.IsOnLayer(layer):
            return None, "pad_not_on_layer"
        if not pad.FlashLayer(layer):
            return None, "pad_not_flashed_on_layer"
        polygon = pad.GetEffectivePolygon(layer, pcbnew.ERROR_INSIDE)
        if polygon is None or polygon.IsEmpty() or polygon.OutlineCount() < 1:
            return None, "native_copper_polygon_unavailable"
        boundaries = geometry.material_boundaries(polygon)
        if not boundaries:
            return None, "native_copper_boundary_unavailable"
        box = polygon.BBox()
        bounds = [int(box.GetLeft()), int(box.GetTop()),
                  int(box.GetRight()), int(box.GetBottom())]
        if (bounds[0] >= bounds[2] or bounds[1] >= bounds[3]
                or any(abs(value) > MAX_COORDINATE_NM for value in bounds)):
            return None, "native_copper_bounds_invalid"
        hole = pad.GetEffectiveHoleShape() if pad.HasHole() else None
        if pad.HasHole() and (hole is None or hole.BBox().GetWidth() <= 0
                              or hole.BBox().GetHeight() <= 0):
            return None, "native_hole_geometry_unavailable"
        return (polygon, boundaries, hole, bounds), None
    except Exception as exc:
        return None, "native_geometry_unavailable:" + type(exc).__name__


def _contact(native, point_nm, contact_inset_nm):
    import pcbnew
    import cec_board_geometry as geometry
    polygon, boundaries, hole, _bounds = native
    point = pcbnew.VECTOR2I(*point_nm)
    try:
        # Native Collide permits exact tangency. One integer nanometre makes
        # the requested closed disk strictly interior, including at a hole;
        # it is a numerical/contact guard, not an electrical design margin.
        strict_inset = contact_inset_nm + 1
        if not geometry.material_leg_clear(polygon, boundaries, point, point,
                                           strict_inset):
            return False, "interior_contact_disk_not_contained"
        if hole is not None and hole.Collide(
                pcbnew.SHAPE_CIRCLE(point, strict_inset), 0):
            return False, "contact_disk_intersects_native_hole"
    except Exception as exc:
        return False, "native_contact_unavailable:" + type(exc).__name__
    return True, "native_interior_contact"


def contact(pad, layer, point_nm, contact_inset_nm=50_000):
    """Independently replay one contact against the current native pad.

    ``ok`` certifies only a finite copper patch on this face. In particular,
    the contact inset is a geometric search guard, never a current rating.
    """
    _parameters(layer, contact_inset_nm)
    point_nm = _point(point_nm)
    report = _base(pad, layer, contact_inset_nm)
    native, reason = _geometry(pad, layer)
    ok = False
    if native is not None:
        ok, reason = _contact(native, point_nm, contact_inset_nm)
    report.update(ok=ok, point_nm=point_nm, reason=reason)
    return report


def sample(pad, layer, *, contact_inset_nm=50_000, axis_samples=17, deadline=None):
    """Return center-first, deterministic bounded native copper contacts.

    At most ``axis_samples**2 + 1`` points are examined. The world-axis box
    only proposes samples; the ERROR_INSIDE native polygon, all contours and
    the effective hole decide every contact. An empty or interrupted menu is
    never proof that the terminal has no legal attachment.
    """
    _parameters(layer, contact_inset_nm, axis_samples=axis_samples, deadline=deadline)
    report = _base(pad, layer, contact_inset_nm)
    report.update(ok=False, points=[], axis_samples=axis_samples,
        candidate_bound=axis_samples**2 + 1, checked=0, rejected_counts={},
        complete=False, stop="unsupported")
    if deadline is not None and time.monotonic() >= deadline:
        report.update(stop="deadline", reason="deadline_exhausted")
        return report
    native, reason = _geometry(pad, layer)
    if native is None:
        report["reason"] = reason
        return report
    left, top, right, bottom = native[3]
    report["native_bounds_nm"] = list(native[3])
    center = tuple(report["pad"]["position_nm"])
    candidates = [center]
    seen = {center}
    for x_index in range(axis_samples):
        x = left + round((right-left)*x_index/(axis_samples-1))
        for y_index in range(axis_samples):
            y = top + round((bottom-top)*y_index/(axis_samples-1))
            point = (x, y)
            if point not in seen:
                candidates.append(point)
                seen.add(point)
    rejected = Counter()
    for point in candidates:
        if deadline is not None and time.monotonic() >= deadline:
            report.update(stop="deadline", reason="deadline_exhausted")
            break
        ok, reason = _contact(native, point, contact_inset_nm)
        report["checked"] += 1
        if ok:
            report["points"].append(list(point))
        else:
            rejected[reason] += 1
    else:
        report.update(complete=True, stop="complete",
            reason="sampled_interior_contacts" if report["points"] else "no_sampled_interior_contacts")
    report.update(ok=bool(report["points"]), rejected_counts=dict(sorted(rejected.items())))
    return report


def _cap_parameters(width_nm, contact_inset_nm, axis_samples=None):
    if (type(width_nm) is not int or not 2*(contact_inset_nm+1) <= width_nm <= MAX_CAP_WIDTH_NM):
        raise ValueError("width_nm must be an integer enclosing the contact disk and at most 100000000")
    if (axis_samples is not None and (type(axis_samples) is not int
            or not 2 <= axis_samples <= MAX_CAP_AXIS_SAMPLES)):
        raise ValueError("cap axis_samples must be an integer in [2, 65]")


def _cap_contains(center_nm, witness_nm, width_nm, contact_inset_nm):
    # Round a half-nanometre radius DOWN and require the same strict +1 nm
    # guard as native pad contact. Integer arithmetic cannot promote a tangent
    # or a display-float round trip into a finite retained copper disk.
    available = width_nm//2 - contact_inset_nm - 1
    distance_squared = sum((a-b)**2 for a, b in zip(center_nm, witness_nm))
    return available >= 0 and distance_squared <= available**2


def cap_contact(pad, layer, center_nm, witness_nm, width_nm, *, contact_inset_nm=50_000):
    """Replay an endpoint cap containing a distinct native interior witness.

    The endpoint center need not lie on the pad. A full-width round track cap
    must contain the WHOLE independently proved contact disk, not just touch
    the pad or its bounding box. Clearance and the actual incident segment are
    the caller's separate obligations. This is not terminal ampacity evidence.
    """
    _parameters(layer, contact_inset_nm)
    _cap_parameters(width_nm, contact_inset_nm)
    center_nm, witness_nm = _point(center_nm), _point(witness_nm)
    report = contact(pad, layer, witness_nm, contact_inset_nm)
    contained = _cap_contains(center_nm, witness_nm, width_nm, contact_inset_nm)
    report.update(center_nm=center_nm, witness_nm=witness_nm, width_nm=width_nm,
        conservative_cap_radius_nm=width_nm//2,
        cap_contains_contact_disk=contained,
        proof="full_width_round_cap_contains_native_interior_disk")
    if report["ok"] and not contained:
        report.update(ok=False, reason="round_cap_does_not_contain_contact_disk")
    elif report["ok"]:
        report["reason"] = "native_interior_disk_contained_in_round_cap"
    return report


def sample_caps(pad, layer, width_nm, *, contact_inset_nm=50_000,
                axis_samples=41, contact_axis_samples=17, deadline=None):
    """Bounded exterior endpoint centers with native interior contact disks.

    A grid over the pad's box expanded by the unchanged trace radius proposes
    centers only. Native pad material proves each witness; exact integer disk
    containment proves the cap/witness relation. The caller must still screen
    the full cap and every route leg against unchanged obstacles and rules.
    No sampled absence, terminal current sharing, or neckdown grant is implied.
    """
    import pcbnew
    _parameters(layer, contact_inset_nm, axis_samples=contact_axis_samples, deadline=deadline)
    _cap_parameters(width_nm, contact_inset_nm, axis_samples)
    report = _base(pad, layer, contact_inset_nm)
    report.update(ok=False, contacts=[], width_nm=width_nm, axis_samples=axis_samples,
        contact_axis_samples=contact_axis_samples, candidate_bound=axis_samples**2,
        checked=0, rejected_counts={}, complete=False, stop="unsupported",
        conservative_cap_radius_nm=width_nm//2,
        proof="full_width_round_cap_contains_native_interior_disk")
    if deadline is not None and time.monotonic() >= deadline:
        report.update(stop="deadline", reason="deadline_exhausted")
        return report
    sampled = sample(pad, layer, contact_inset_nm=contact_inset_nm,
                     axis_samples=contact_axis_samples, deadline=deadline)
    report["contact_search"] = {key: value for key, value in sampled.items() if key != "points"}
    witnesses = sampled["points"]
    if not witnesses:
        report.update(stop=sampled.get("stop", "unsupported"),
            reason=sampled.get("reason", "native_interior_contact_unavailable"),
            complete=sampled.get("complete", False))
        return report
    if deadline is not None and time.monotonic() >= deadline:
        report.update(stop="deadline", reason="deadline_exhausted")
        return report
    native, reason = _geometry(pad, layer)
    if native is None:
        report["reason"] = reason
        return report
    radius = width_nm//2
    left, top, right, bottom = native[3]
    bounds = [left-radius, top-radius, right+radius, bottom+radius]
    if any(abs(value) > MAX_COORDINATE_NM for value in bounds):
        report["reason"] = "cap_search_bounds_out_of_range"
        return report
    report["native_bounds_nm"], report["search_bounds_nm"] = list(native[3]), bounds
    left, top, right, bottom = bounds
    rejected, seen = Counter(), set()
    for x_index in range(axis_samples):
        x = left + round((right-left)*x_index/(axis_samples-1))
        for y_index in range(axis_samples):
            if deadline is not None and time.monotonic() >= deadline:
                report.update(stop="deadline", reason="deadline_exhausted")
                break
            center = [x, top + round((bottom-top)*y_index/(axis_samples-1))]
            if tuple(center) in seen:
                continue
            seen.add(tuple(center))
            report["checked"] += 1
            if native[0].Contains(pcbnew.VECTOR2I(*center)):
                rejected["center_on_native_pad_outline"] += 1
                continue
            witness = min(witnesses, key=lambda p: (sum((a-b)**2 for a, b in zip(center, p)), p))
            if not _cap_contains(center, witness, width_nm, contact_inset_nm):
                rejected["no_contained_native_contact_disk"] += 1
                continue
            report["contacts"].append(dict(center_nm=center, witness_nm=list(witness)))
        else:
            continue
        break
    else:
        report.update(complete=True, stop="complete", reason=("sampled_exterior_caps"
            if report["contacts"] else "no_sampled_exterior_caps"))
    # A partial native witness menu is never reported as an exhaustive search.
    if not sampled.get("complete", False):
        report["complete"] = False
    report.update(ok=bool(report["contacts"]), rejected_counts=dict(sorted(rejected.items())))
    return report
