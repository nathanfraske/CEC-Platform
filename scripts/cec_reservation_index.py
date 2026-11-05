"""Immutable, bounded broad phase for exact ordered route reservations.

No geometry is rounded or admitted here. The caller still applies its exact
segment/rectangle predicate to the returned rows, in original input order.
"""
from __future__ import annotations

import math


class ReservationIndex(tuple):
    """Tuple-compatible snapshot; finite buckets accelerate local queries."""

    def __new__(cls, rows, tile_mm=4.0, max_bucket_cells=256):
        rows=tuple(tuple(row) for row in rows)
        tile_mm=float(tile_mm)
        if (not math.isfinite(tile_mm) or tile_mm <= 0
                or not isinstance(max_bucket_cells,int) or isinstance(max_bucket_cells,bool)
                or max_bucket_cells < 1):
            raise ValueError('invalid reservation index policy')
        obj=super().__new__(cls,rows)
        buckets={}
        global_rows=[]
        for index,row in enumerate(rows):
            if len(row)!=5:
                raise ValueError('reservation index requires layer-projected five-tuples')
            x0,y0,x1,y1=map(float,row[:4])
            if not all(map(math.isfinite,(x0,y0,x1,y1))) or x0>x1 or y0>y1:
                raise ValueError('invalid finite reservation rectangle')
            ix0,iy0,ix1,iy1=(math.floor(v/tile_mm) for v in (x0,y0,x1,y1))
            if (ix1-ix0+1)*(iy1-iy0+1)>max_bucket_cells:
                global_rows.append(index)
                continue
            for x in range(ix0,ix1+1):
                for y in range(iy0,iy1+1):
                    buckets.setdefault((x,y),[]).append(index)
        obj.tile_mm=tile_mm
        obj.max_bucket_cells=max_bucket_cells
        obj._buckets={cell:tuple(indices) for cell,indices in buckets.items()}
        obj._global_rows=tuple(global_rows)
        return obj

    def __reduce__(self):
        # Native route workers use spawn; serialize values, never cache state
        # or references to a mutable board/process-owned geometry object.
        return ReservationIndex,(tuple(self),self.tile_mm,self.max_bucket_cells)

    def candidates(self, points, margin):
        points=tuple(points)
        if not points:
            return ()
        margin=float(margin)
        if not math.isfinite(margin) or margin<0:
            raise ValueError('invalid reservation query margin')
        xs,ys=zip(*points)
        if not all(math.isfinite(float(v)) for v in (*xs,*ys)):
            raise ValueError('invalid reservation query coordinates')
        # One conservative cell halo protects the broad phase from boundary
        # roundoff. It cannot hide a collision or alter the exact predicate.
        ix0=math.floor((min(xs)-margin)/self.tile_mm)-1
        iy0=math.floor((min(ys)-margin)/self.tile_mm)-1
        ix1=math.floor((max(xs)+margin)/self.tile_mm)+1
        iy1=math.floor((max(ys)+margin)/self.tile_mm)+1
        if (ix1-ix0+1)*(iy1-iy0+1)>self.max_bucket_cells:
            return self
        indices=set(self._global_rows)
        for x in range(ix0,ix1+1):
            for y in range(iy0,iy1+1):
                indices.update(self._buckets.get((x,y),()))
        return tuple(self[index] for index in sorted(indices))


def build(rows, *, tile_mm=4.0, max_bucket_cells=256, minimum_items=16):
    """Skip index construction for tiny lists; preserve tuple compatibility."""
    if isinstance(rows,ReservationIndex):
        return rows
    rows=tuple(tuple(row) for row in rows)
    return (ReservationIndex(rows,tile_mm,max_bucket_cells)
            if len(rows)>=minimum_items else rows)
