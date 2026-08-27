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


def outline_bbox_mm(board):
    """Return ``(left, top, right, bottom)`` for the Edge.Cuts centerline.

    Fail closed when KiCad cannot form a valid closed outline.  Falling back
    to the painted-stroke bounding box would recreate the dimensional drift
    this helper exists to prevent.
    """
    outline = pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(outline, False):
        raise ValueError("board Edge.Cuts do not form a valid closed outline")
    if outline.OutlineCount() < 1:
        raise ValueError("board has no closed Edge.Cuts outline")
    bbox = outline.BBox()
    left = bbox.GetLeft() / _MM
    top = bbox.GetTop() / _MM
    right = bbox.GetRight() / _MM
    bottom = bbox.GetBottom() / _MM
    if right <= left or bottom <= top:
        raise ValueError("board Edge.Cuts outline has zero area")
    return left, top, right, bottom
