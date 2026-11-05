"""Bounded courtyard-edge relocation proposals, never placement authority.

Use the actual closed laminate, including cutouts, and native courtyards.
Proposals preserve rotation and must independently pass native DRC, assembly,
connectivity, protected copper/fill and placement-authority admission.
"""
import math


def translation_offsets(courtyard, outline, *, margin_mm=.9,
                        max_shift_mm=1., step_mm=.05, limit=8):
    from shapely import affinity
    if (not all(math.isfinite(x) for x in (margin_mm, max_shift_mm, step_mm))
            or not 0 < margin_mm <= 5 or not 0 < max_shift_mm <= 2
            or not .025 <= step_mm <= max_shift_mm
            or type(limit) is not int or not 1 <= limit <= 32):
        raise ValueError('finite bounded edge proposal domain required')
    if (courtyard.is_empty or outline.is_empty or not courtyard.is_valid
            or not outline.is_valid or courtyard.area <= 0 or outline.area <= 0):
        raise ValueError('valid area-bearing courtyard and laminate required')
    usable = outline.buffer(-margin_mm, join_style='mitre')
    if usable.is_empty or usable.covers(courtyard):
        return []
    candidates = []
    # Eight directions provide cardinal repairs and compound corner repairs.
    # No product, reference, coordinate or assumed rectangular outline enters.
    for i in range(1, math.floor(max_shift_mm/step_mm+1e-9)+1):
        distance = round(i*step_mm, 6)
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            x, y = round(dx*distance,6), round(dy*distance,6)
            if math.hypot(x,y) > max_shift_mm+1e-9:
                continue
            if usable.covers(affinity.translate(courtyard,xoff=x,yoff=y)):
                candidates.append((x,y))
    return sorted(set(candidates),key=lambda p:(math.hypot(*p),abs(p[0])+abs(p[1]),p))[:limit]


def proposals(board, references, *, immutable_refs=(), **kwargs):
    import pcbnew
    from cec_assembly_envelope import polygon_from_native
    outline = pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(outline, False):
        raise ValueError('closed native outline required')
    laminate = polygon_from_native(outline)
    fixed = set(immutable_refs)
    fixed.update(item.GetReference() for group in board.Groups()
                 for item in group.GetItems() if item.GetClass() == 'FOOTPRINT')
    result = []
    for ref in sorted(set(references)):
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            raise ValueError('missing requested footprint: '+ref)
        if fp.IsLocked() or ref in fixed:
            continue
        courtyard = polygon_from_native(fp.GetCourtyard(fp.GetLayer()))
        at = fp.GetPosition()
        for dx,dy in translation_offsets(courtyard,laminate,**kwargs):
            result.append(dict(ref=ref,delta_mm=[dx,dy],pose_mm=[
                round(at.x/1e6+dx,6),round(at.y/1e6+dy,6),
                float(fp.GetOrientationDegrees())],release_authority=False))
    return result
