"""Pure polygon geometry shared by bounded placement proposal generators.

These are conservative configuration-space proposals, not native electrical
or fabrication admission. The caller supplies its bounded work/deadline.
"""
import math


def rectangular_sweep(shape, half_x, half_y, work):
    """Minkowski expansion by a rectangle without convex-hulling cavities.

    Sweep each actual boundary segment, including hole rings, rather than
    replacing a diagonal/concave obstacle by its entire bounding rectangle.
    ``work`` must provide tick() and contact() budget checks.
    """
    from shapely import affinity
    from shapely.geometry import MultiPoint
    from shapely.ops import unary_union
    if (shape.is_empty or not shape.is_valid
            or shape.geom_type not in ('Polygon','MultiPolygon')
            or any(type(v) not in (int,float) or not math.isfinite(v) or v<0
                   for v in (half_x,half_y))):
        raise ValueError('valid_bounded_rectangular_sweep_required')
    for axis,distance in ((0,half_x),(1,half_y)):
        if distance<=0:continue
        work.tick();dx,dy=(distance,0) if axis==0 else (0,distance)
        pieces=[affinity.translate(shape,xoff=dx,yoff=dy),
                affinity.translate(shape,xoff=-dx,yoff=-dy)]
        parts=[shape] if shape.geom_type=='Polygon' else shape.geoms
        for part in parts:
            for ring in (part.exterior,*part.interiors):
                points=list(ring.coords)
                for a,b in zip(points,points[1:]):
                    work.contact()
                    poly=MultiPoint([(a[0]-dx,a[1]-dy),(b[0]-dx,b[1]-dy),
                                     (b[0]+dx,b[1]+dy),(a[0]+dx,a[1]+dy)]).convex_hull
                    if poly.geom_type=='Polygon' and poly.area>0:pieces.append(poly)
        shape=unary_union(pieces)
        if (not shape.is_valid or shape.is_empty
                or shape.geom_type not in ('Polygon','MultiPolygon')
                or not all(math.isfinite(v) for v in shape.bounds)):
            raise ValueError('surface_translation_sweep_geometry_unknown')
    work.tick()
    return shape
