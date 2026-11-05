"""Rectangular-outline antenna-face attachment, independent of placement scoring.

This is a mechanical placement contract, NOT RF/EMC or keepout qualification.
The measurement adapter covers the vendored MINI modules whose physical antenna
end is -Y. Wired-only use does not imply an RF keepout or a universal edge rule:
measurements become blockers only under an explicit mechanical placement policy.
"""
import math
import re


def face_evidence(body, outline, direction, *, max_inset_mm=.3, overhang_mm=5.):
    """Measure signed face-to-edge gap; tuples are (left, top, right, bottom)."""
    dx, dy = direction
    if (not all(math.isfinite(v) for v in (*body, *outline, dx, dy,
                                          max_inset_mm, overhang_mm))
            or min(max_inset_mm, overhang_mm) < 0
            or min(abs(dx), abs(dy)) > 1e-6
            or max(abs(dx), abs(dy)) < .5):
        raise ValueError("invalid cardinal antenna-face contract")
    if abs(dx) > abs(dy):
        edge, gap = ("left", body[0]-outline[0]) if dx < 0 else ("right", outline[2]-body[2])
    else:
        edge, gap = ("top", body[1]-outline[1]) if dy < 0 else ("bottom", outline[3]-body[3])
    return {"ok": -overhang_mm-1e-6 <= gap <= max_inset_mm+1e-6,
            "edge": edge, "signed_gap_mm": round(gap, 6),
            "max_inset_mm": max_inset_mm, "max_overhang_mm": overhang_mm}


def board_evidence(board, *, contracts=None, max_inset_mm=.3, overhang_mm=5.,
                   require_edge=False):
    """Read actual embedded footprint courtyards, not a proposal's stored pose.

    Explicit contracts map references to local direction and optional distance
    limits. This adapter currently certifies rectangular outline edge bands.
    Pad containment and copper/part antenna keepouts remain separate gates.
    """
    import pcbnew
    contracts = contracts or {}
    bb = board.GetBoardEdgesBoundingBox()
    outline = (bb.GetLeft()/1e6, bb.GetTop()/1e6, bb.GetRight()/1e6, bb.GetBottom()/1e6)
    if outline[2] <= outline[0] or outline[3] <= outline[1]:
        raise ValueError("antenna edge check requires a real board outline")
    details, seen = [], set()
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        name = str(fp.GetFPID().GetLibItemName())
        inferred = bool(re.search(r"ESP32-(?:S2|S3|C6)-MINI-1(?!U)", name, re.I))
        if ref not in contracts and not inferred:
            continue
        seen.add(ref)
        rule = contracts.get(ref) or {}
        dx, dy = rule.get("direction", (0., -1.))
        if fp.IsFlipped():
            dx = -dx
        angle = math.radians(fp.GetOrientationDegrees())
        direction = (dx*math.cos(angle)+dy*math.sin(angle),
                     -dx*math.sin(angle)+dy*math.cos(angle))
        poly = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
        if not poly.OutlineCount():
            raise ValueError("antenna owner %s has no embedded courtyard" % ref)
        pb = poly.BBox()
        body = (pb.GetLeft()/1e6, pb.GetTop()/1e6, pb.GetRight()/1e6, pb.GetBottom()/1e6)
        row = face_evidence(body, outline, direction,
            max_inset_mm=float(rule.get("max_inset_mm", max_inset_mm)),
            overhang_mm=float(rule.get("overhang_mm", overhang_mm)))
        details.append(dict(row, ref=ref, footprint=name,
                            required=bool(require_edge or ref in contracts),
                            authority="explicit" if ref in contracts else "MINI-local-minus-Y"))
    missing = sorted(set(contracts)-seen)
    violations = [row for row in details if row["required"] and not row["ok"]]
    violations += [{"ref": r, "ok": False, "reason": "declared_antenna_owner_missing"} for r in missing]
    return {"schema": 1, "ok": not violations, "applicable": bool(details or missing),
            "contract": "physical_module_edge_attachment_not_RF",
            "details": details, "violations": violations,
            "repair_stage": "critical_macro_edge_reservation" if violations else None}
