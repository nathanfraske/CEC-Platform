"""Bounded integer construction of a strict local polygon subset.

Native intersection/fracture can quantize a crossing into a sliver outside
one operand. Never ignore its area or use it as a clearance tolerance. Remove
its integer bounding rectangle, strictly within the already authorized local
window, then re-prove zero spill against BOTH original operands. No restored
Source material, outward offset, relaxed proof, or current qualification.
"""
import time
import pcbnew


def refine(before, compiled, candidate, window, *, deadline):
    def tick():
        if time.monotonic() >= deadline:
            raise ValueError('native_subtractive_clip_deadline')
    tick()
    if window.OutlineCount() != 1 or window.HoleCount(0) != 0:
        raise ValueError('one_literal_rectangular_local_clip_window_required')
    bounds = window.BBox()
    corners = {(bounds.GetX(), bounds.GetY()), (bounds.GetRight(), bounds.GetY()),
               (bounds.GetRight(), bounds.GetBottom()), (bounds.GetX(), bounds.GetBottom())}
    outline = window.Outline(0)
    if outline.PointCount() != 4 or {tuple(outline.CPoint(i)) for i in range(4)} != corners:
        raise ValueError('one_literal_rectangular_local_clip_window_required')
    trial = candidate.CloneDropTriangulation()
    records = []
    # This is a finite constructor, not an unbounded keep-shrinking repair.
    for iteration in range(5):
        rectangles = []
        for name, operand in (('Source', before), ('compiled', compiled)):
            tick()
            spill = trial.CloneDropTriangulation(); spill.BooleanSubtract(operand)
            if spill.OutlineCount() > 16:
                raise ValueError('native_subtractive_clip_spill_inventory_bound')
            for index in range(spill.OutlineCount()):
                tick(); ring = spill.Outline(index)
                if ring.PointCount() > 64 or spill.HoleCount(index):
                    raise ValueError('native_subtractive_clip_spill_inventory_bound')
                box = ring.BBox()
                # One integer unit makes the removal strictly enclose the
                # measured sliver. It is NEW SUBTRACTION, never accepted spill.
                x0, y0 = box.GetX()-1, box.GetY()-1
                x1, y1 = box.GetRight()+1, box.GetBottom()+1
                if not (bounds.GetX() <= x0 < x1 <= bounds.GetRight()
                        and bounds.GetY() <= y0 < y1 <= bounds.GetBottom()):
                    raise ValueError('native_subtractive_clip_spill_not_strictly_local')
                rectangles.append((name, (x0, y0, x1, y1)))
        if not rectangles:
            tick()
            return trial, dict(rounds=len(records), subtractions=records,
                exact_zero_spill_against_Source_and_compiled=True,
                spill_area_tolerance_used=False, restored_native_material=False,
                current_capacity_qualified=False)
        if iteration == 4:
            raise ValueError('native_subtractive_clip_construction_round_bound')
        rows = []
        for name, (x0, y0, x1, y1) in sorted(set(rectangles)):
            tick(); rectangle = pcbnew.SHAPE_POLY_SET(); rectangle.NewOutline()
            for x, y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1)):
                rectangle.Append(x,y)
            trial.BooleanSubtract(rectangle)
            rows.append(dict(operand=name, rectangle_nm=[x0,y0,x1,y1]))
        trial.Fracture(); records.append(rows)
    raise AssertionError('finite subtractive construction must return or refuse')
