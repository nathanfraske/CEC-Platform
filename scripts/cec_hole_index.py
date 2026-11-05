"""Scalar-only spatial broad phase for an immutable hole-geometry snapshot.

This index is not a clearance certificate. Queries return a conservative,
native-order subset for the caller's unchanged exact drill-spacing test.
Never retain a snapshot across board mutations or independent route plans.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType


@dataclass(frozen=True)
class ViaHole:
    x: int
    y: int
    drill: int
    uuid: str
    net_code: int
    net_name: str


class HoleIndex:
    def __init__(self, rows, *, cell_nm=1_000_000):
        if isinstance(cell_nm, bool) or not isinstance(cell_nm, int) or cell_nm <= 0:
            raise ValueError('positive integer spatial cell size required')
        self.rows = tuple(rows)
        self.cell_nm = cell_nm
        cells, identities = {}, {}
        for index, row in enumerate(self.rows):
            cells.setdefault((row.x // cell_nm, row.y // cell_nm), []).append(index)
            identities.setdefault(row.uuid, []).append(index)
        self._cells = MappingProxyType({key: tuple(values) for key, values in cells.items()})
        self._identities = MappingProxyType({key: tuple(values) for key, values in identities.items()})
        self._max_drill = max((row.drill for row in self.rows), default=0)

    def nearby(self, x, y, drill_nm, gap_nm, *, include_uuid=None):
        if (not math.isfinite(float(gap_nm)) or gap_nm < 0
                or (drill_nm is not None and
                    (not math.isfinite(float(drill_nm)) or drill_nm < 0))):
            raise ValueError('finite nonnegative drill and gap required')
        radius = (0 if drill_nm is None else
                  max(0, math.ceil((drill_nm + self._max_drill) / 2 + gap_nm)))
        x0, x1 = (x-radius)//self.cell_nm, (x+radius)//self.cell_nm
        y0, y1 = (y-radius)//self.cell_nm, (y+radius)//self.cell_nm
        # A huge query must not enumerate a huge mostly empty lattice. The
        # exhaustive scalar fallback is still conservative and deterministic.
        if (x1-x0+1)*(y1-y0+1) > max(16, 4*len(self._cells)):
            return self.rows
        indices = set(self._identities.get(include_uuid, ()))
        for ix in range(x0,x1+1):
            for iy in range(y0,y1+1):
                indices.update(self._cells.get((ix,iy), ()))
        return tuple(self.rows[i] for i in sorted(indices))
