#!/usr/bin/env python3
"""Shared exact board-outline geometry.

KiCad's ``GetBoardEdgesBoundingBox()`` encloses the *painted stroke* on
Edge.Cuts.  It is therefore wider and taller than the manufactured outline by
one full line width.  Feeding that box back into a generator grows a board on
every regeneration and shifts center-relative mechanical contracts by half a
line width.  The polygonized outline follows the Edge.Cuts centerline and is
the dimensional authority for placement and mating coordinates.
"""

import pcbnew

import cec_swig_guard  # noqa: F401  -- keep long-running pcbnew sessions typed


_MM = 1_000_000.0


def outline_material(board):
    """Read native board material, including concavities and closed cutouts."""
    outline = pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(outline, False):
        raise ValueError("board Edge.Cuts do not form a valid closed outline")
    if outline.OutlineCount() < 1:
        raise ValueError("board has no closed Edge.Cuts outline")
    return outline


def material_boundaries(outline):
    """Open chains tracing every closed contour, without a filled interior.

    Native closed-chain Collide treats the entire interior as solid, which
    would reject every track inside the board. Repeating the first vertex in
    an explicitly open chain retains every boundary segment without that
    filled-polygon meaning. Keep the result with its native outline owner.
    """
    boundaries = []
    for index in range(outline.OutlineCount()):
        contours = [outline.COutline(index)]
        contours.extend(outline.CHole(index, hole)
                        for hole in range(outline.HoleCount(index)))
        for contour in contours:
            boundary = pcbnew.SHAPE_LINE_CHAIN()
            for vertex in range(contour.PointCount()):
                boundary.Append(contour.CPoint(vertex))
            boundary.Append(contour.CPoint(0))
            boundary.SetClosed(False)
            boundaries.append(boundary)
    return tuple(boundaries)


def material_leg_clear(outline, boundaries, start, end, margin_nm):
    """A whole capsule must stay in material, not merely in its bounding box.

    Both endpoint containment and clearance from *every* boundary are needed:
    endpoints may lie on opposite sides of a notch/hole while their segment
    leaves board material. Native integer geometry handles tangency consistently
    with other route collision queries. The caller supplies copper radius plus
    its unchanged copper-to-edge clearance.
    """
    if not outline.Contains(start) or not outline.Contains(end):
        return False
    segment = pcbnew.SEG(start, end)
    return not any(boundary.Collide(segment, int(margin_nm))
                   for boundary in boundaries)


def outline_bbox_mm(board):
    """Return ``(left, top, right, bottom)`` for the Edge.Cuts centerline.

    Fail closed when KiCad cannot form a valid closed outline. Falling back
    to the painted-stroke bounding box would recreate dimensional drift.
    """
    outline = outline_material(board)
    bbox = outline.BBox()
    left = bbox.GetLeft() / _MM
    top = bbox.GetTop() / _MM
    right = bbox.GetRight() / _MM
    bottom = bbox.GetBottom() / _MM
    if right <= left or bottom <= top:
        raise ValueError("board Edge.Cuts outline has zero area")
    return left, top, right, bottom
