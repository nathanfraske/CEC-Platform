"""Exact native finite lane caps after a conservative envelope refusal.

The centreline envelope has an oversized semicircular end cap: it is not
the union of the two actual trace caps. Only a terminal straight edge may
use this refinement. Miters, member identity, board material, reservations,
field coupling and complete saved-route admission remain separate gates.
"""
import math

import pcbnew
import cec_fr as fr


def clear(a, b, *, width_mm, gap_mm, clearance_nm, zone_rows, copper_rows):
    if (not isinstance(a, (list, tuple)) or not isinstance(b, (list, tuple))
            or len(a) != 2 or len(b) != 2
            or any(type(v) not in (int, float) or not math.isfinite(v)
                for v in (*a, *b, width_mm, gap_mm))
            or width_mm <= 0 or gap_mm < 0 or type(clearance_nm) is not int
            or clearance_nm < 0):
        raise ValueError('finite_actual_paired_terminal_cap_geometry_required')
    dx,dy = b[0]-a[0],b[1]-a[1]
    length = math.hypot(dx,dy)
    if length <= 1e-12:
        return False
    offset = (width_mm+gap_mm)/2
    ox,oy = -dy/length*offset,dx/length*offset
    for sign in (-1,1):
        start = pcbnew.VECTOR2I_MM(a[0]+sign*ox,a[1]+sign*oy)
        end = pcbnew.VECTOR2I_MM(b[0]+sign*ox,b[1]+sign*oy)
        if not fr._snapshot_foreign_clear(start,end,pcbnew.FromMM(width_mm),
                clearance_nm,zone_rows,copper_rows):
            return False
    return True
