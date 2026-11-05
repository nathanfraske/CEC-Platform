"""Explicit rounded cable-access recess in a straight exterior edge.

No component/board identities are inferred. This emits a proposal, not clearance
acceptance. The caller must rerun pad-edge, assembly and mating checks afterward.
"""
import math

def recessed_path(start, end, inward, *, opening, depth, radius):
    """Return line/arc point sequences without changing the two endpoints."""
    values=(*start,*end,*inward,*opening,depth,radius)
    if not all(math.isfinite(v) for v in values):raise ValueError('finite geometry required')
    length=math.dist(start,end)
    if length<=0:raise ValueError('nonzero edge required')
    ux,uy=((end[0]-start[0])/length,(end[1]-start[1])/length)
    nx,ny=inward;a,b=opening
    if (abs(nx*nx+ny*ny-1)>1e-8 or abs(nx*ux+ny*uy)>1e-8
            or not (0<a<b<length) or radius<=0 or depth<=radius or b-a<=2*radius):
        raise ValueError('valid interior recess and orthogonal unit inward vector required')
    def p(u,v):return (start[0]+ux*u+nx*v,start[1]+uy*u+ny*v)
    d=radius/math.sqrt(2)
    return [(p(0,0),p(a,0)),(p(a,0),p(a,depth-radius)),
        (p(a,depth-radius),p(a+radius-d,depth-radius+d),p(a+radius,depth)),
        (p(a+radius,depth),p(b-radius,depth)),
        (p(b-radius,depth),p(b-radius+d,depth-radius+d),p(b,depth-radius)),
        (p(b,depth-radius),p(b,0)),(p(b,0),p(length,0))]


def replace_edge(board, edge, inward, *, opening, depth, radius):
    import pcbnew
    if edge.GetLayer()!=pcbnew.Edge_Cuts or edge.GetShape()!=pcbnew.SHAPE_T_SEGMENT:
        raise ValueError('a native straight Edge.Cuts segment is required')
    xy=lambda p:(p.x/1e6,p.y/1e6)
    path=recessed_path(xy(edge.GetStart()),xy(edge.GetEnd()),inward,
                       opening=opening,depth=depth,radius=radius)
    new=[]
    for points in path:
        item=pcbnew.PCB_SHAPE(board);item.SetLayer(pcbnew.Edge_Cuts);item.SetWidth(edge.GetWidth())
        pts=[pcbnew.VECTOR2I_MM(*p) for p in points]
        if len(pts)==3:item.SetShape(pcbnew.SHAPE_T_ARC);item.SetArcGeometry(*pts)
        else:item.SetShape(pcbnew.SHAPE_T_SEGMENT);item.SetStart(pts[0]);item.SetEnd(pts[1])
        new.append(item)
    board.Remove(edge)
    for item in new:board.Add(item)
    return edge  # keep detached SWIG proxy alive until native export completes
