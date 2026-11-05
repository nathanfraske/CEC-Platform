"""Explicit, dimension-checked rectangular outline replacement.

Retain corner radius and every non-outline item. Unrecognized board-owned
slots, tabs, unequal corner radii, or multiple contours require another declared
mechanical transform; they must never be silently scaled away.
Footprint-owned cutouts are retained only when fully contained by the new edge.
"""
import math


def _xy(point):
    return (point.x/1e6, point.y/1e6)


def _near(a,b):
    return math.dist(a,b) <= .002


def _primitives(x,y,w,h,r):
    segments=[((x+r,y),(x+w-r,y)),((x+w,y+r),(x+w,y+h-r)),
              ((x+w-r,y+h),(x+r,y+h)),((x,y+h-r),(x,y+r))]
    d=r/math.sqrt(2)
    arcs=[] if not r else [
        ((x+w-r,y),(x+w-r+d,y+r-d),(x+w,y+r)),
        ((x+w,y+h-r),(x+w-r+d,y+h-r+d),(x+w-r,y+h)),
        ((x+r,y+h),(x+r-d,y+h-r+d),(x,y+h-r)),
        ((x,y+r),(x+r-d,y+r-d),(x+r,y))]
    return segments,arcs


def resize_rectangular(board, width, height):
    import pcbnew
    from cec_board_geometry import outline_bbox_mm
    width,height=float(width),float(height)
    if not all(math.isfinite(v) and v>0 for v in (width,height)):
        raise ValueError('outline dimensions must be finite and positive')
    x,y,right,bottom=outline_bbox_mm(board)
    old_w,old_h=right-x,bottom-y
    if abs(width-old_w)<1e-6 and abs(height-old_h)<1e-6:
        return {'changed':False,'outline_mm':[old_w,old_h]}
    poly=pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(poly,False) or poly.OutlineCount()!=1:
        raise ValueError('outline replacement refuses multiple or unclosed contours')
    edges=[e for e in board.GetDrawings() if e.GetLayer()==pcbnew.Edge_Cuts]
    segments=[e for e in edges if e.GetShape()==pcbnew.SHAPE_T_SEGMENT]
    arcs=[e for e in edges if e.GetShape()==pcbnew.SHAPE_T_ARC]
    if len(segments)!=4 or len(arcs) not in (0,4) or len(edges)!=len(segments)+len(arcs):
        raise ValueError('outline replacement refuses unrecognized outer edges or board-owned cutouts')
    radius=arcs[0].GetRadius()/1e6 if arcs else 0.
    if 2*radius>=min(width,height):
        raise ValueError('target outline cannot retain the original corner radius')
    from shapely.geometry import box,Polygon
    target=box(x+radius,y+radius,x+width-radius,y+height-radius)
    if radius: target=target.buffer(radius,quad_segs=64)
    for i in range(poly.HoleCount(0)):
        hole=poly.Hole(0,i)
        cutout=Polygon([_xy(hole.CPoint(j)) for j in range(hole.PointCount())])
        if not target.contains(cutout):
            raise ValueError('retained footprint cutout would cross the new outline')
    old_segments,old_arcs=_primitives(x,y,old_w,old_h,radius)
    new_segments,new_arcs=_primitives(x,y,width,height,radius)
    changes=[]
    for items,expected,targets in ((segments,old_segments,new_segments),(arcs,old_arcs,new_arcs)):
        remaining=set(range(len(expected)))
        for edge in items:
            start,end=_xy(edge.GetStart()),_xy(edge.GetEnd())
            matches=[(i,reverse) for i in remaining for reverse in (False,True)
                if _near(start,expected[i][-1 if reverse else 0])
                and _near(end,expected[i][0 if reverse else -1])
                and (len(expected[i])==2 or _near(_xy(edge.GetArcMid()),expected[i][1]))]
            if len(matches)!=1:
                raise ValueError('outline is not the supported rectangle; no geometry changed')
            i,reverse=matches[0]; remaining.remove(i)
            points=targets[i][::-1] if reverse else targets[i]
            changes.append((edge,points))
    # Validate the entire old outline before mutating any edge.
    for edge,points in changes:
        native=[pcbnew.VECTOR2I_MM(*p) for p in points]
        if len(native)==3:
            edge.SetArcGeometry(*native)
        else:
            edge.SetStart(native[0]); edge.SetEnd(native[1])
    actual=outline_bbox_mm(board)
    if abs(actual[2]-actual[0]-width)>.002 or abs(actual[3]-actual[1]-height)>.002:
        raise ValueError('emitted outline differs from requested dimensions')
    return {'changed':True,'source_outline_mm':[old_w,old_h],
            'outline_mm':[width,height],'corner_radius_mm':radius,
            'retained_footprint_cutouts':poly.HoleCount(0)}


def reconcile_candidate(board,candidate):
    """No metadata-only shrink; resizing requires explicit replacement scope."""
    from cec_board_geometry import outline_bbox_mm
    x,y,right,bottom=outline_bbox_mm(board)
    mismatch=abs(right-x-candidate.W)>.002 or abs(bottom-y-candidate.H)>.002
    if mismatch and not getattr(candidate,'outline_replacement_authorized',False):
        raise ValueError('candidate dimensions differ from source without outline replacement authority')
    return resize_rectangular(board,candidate.W,candidate.H) if mismatch else {'changed':False}


def screen_rectangular_proposals(board_path, sizes):
    """Reject unsupported shape transforms before launching placement workers.

    Each proposal uses a private native board. A recessed or slotted source
    can retain its exact outline even when rectangle-only shrink proposals
    are unsupported. Unexpected loading/runtime failures still stop the run.
    """
    import pcbnew
    accepted=[];rejected=[]
    for width,height in sizes:
        board=pcbnew.LoadBoard(str(board_path))
        if board is None:raise RuntimeError('outline proposal source is unloadable')
        try:
            resize_rectangular(board,width,height)
        except ValueError as exc:
            rejected.append({'kind':'unsupported_outline_transform',
                             'outline_mm':[width,height],'reason':str(exc)})
        else:
            accepted.append((width,height))
    return accepted,rejected


def extend_outer_edge(board, *, edge, amount_mm):
    """Extend one straight outer edge, retaining attached fillets and recesses.

    Mechanical proposal only. Never scales the board, footprints, internal
    cutouts or copper. Refuses ambiguous/unsupported edge topology up front.
    """
    import pcbnew
    if edge not in ('left','right','top','bottom') or not math.isfinite(amount_mm) or amount_mm<=0:
        raise ValueError('named edge and positive extension required')
    axis=0 if edge in ('left','right') else 1
    sign=-1 if edge in ('left','top') else 1
    items=[d for d in board.GetDrawings() if d.GetLayer()==pcbnew.Edge_Cuts]
    coords=[_xy(p)[axis] for d in items for p in (d.GetStart(),d.GetEnd())]
    extreme=min(coords) if sign<0 else max(coords)
    matches=[d for d in items if d.GetShape()==pcbnew.SHAPE_T_SEGMENT
             and all(abs(_xy(p)[axis]-extreme)<.002 for p in (d.GetStart(),d.GetEnd()))]
    if len(matches)!=1:raise ValueError('extension requires one unambiguous extreme segment')
    primary=matches[0]
    shift=[0.,0.];shift[axis]=sign*amount_mm
    endpoints=[_xy(primary.GetStart()),_xy(primary.GetEnd())]
    corners=[]
    for p in endpoints:
        adjacent=[d for d in items if d!=primary and
                  any(_near(p,_xy(q)) for q in (d.GetStart(),d.GetEnd()))]
        if len(adjacent)!=1:raise ValueError('ambiguous contour junction')
        d=adjacent[0]
        if d.GetShape()==pcbnew.SHAPE_T_ARC:
            if abs(abs(d.GetArcAngle().AsDegrees())-90)>.1:
                raise ValueError('only quarter-circle attached fillets supported')
            corners.append(d)
        elif d.GetShape()!=pcbnew.SHAPE_T_SEGMENT:
            raise ValueError('unsupported adjacent edge primitive')
    nodes=endpoints+[_xy(p) for d in corners for p in (d.GetStart(),d.GetEnd())]
    changes=[]
    for d in items:
        pts=[_xy(d.GetStart()),_xy(d.GetEnd())]
        if d in corners:pts=[pts[0],_xy(d.GetArcMid()),pts[1]]
        moved=[(p[0]+shift[0],p[1]+shift[1]) if d in corners or any(_near(p,n) for n in nodes) else p for p in pts]
        if moved!=pts:changes.append((d,pts,moved))
    def apply(index):
        for row in changes:
            d=row[0];pts=[pcbnew.VECTOR2I_MM(*p) for p in row[index]]
            if len(pts)==3:d.SetArcGeometry(*pts)
            else:d.SetStart(pts[0]);d.SetEnd(pts[1])
    apply(2)
    poly=pcbnew.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(poly,False) or poly.OutlineCount()!=1:
        apply(1);raise ValueError('extension would invalidate native contour')
    return dict(edge=edge,extension_mm=amount_mm,changed_primitives=len(changes),
                preserves_component_datum=True)
