"""Finite exact centreline contacts on existing native straight tracks.

A connected island is not accessible only at segment ends. This proposes
interior contacts without splitting/moving its copper, changing nets, or
claiming via, current, clearance or release qualification.
"""
import math
from fractions import Fraction


def segment_distance_squared(a,b,c,d):
    """Exact squared separation of two literal integer native centrelines.

    Callers still own width, layer, contact, current and mutation authority.
    Rational distances avoid an epsilon turning a lost contact into a match.
    Degenerate segments are valid points, never invented routing material.
    """
    for p in (a,b,c,d):
        if len(p)!=2 or any(type(v) is not int or abs(v)>2_147_483_647 for v in p):
            raise ValueError('literal_integer_segment_distance_required')
    def orientation(p,q,r):return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def point_segment(p,q,r):
        x,y=r[0]-q[0],r[1]-q[1];u,v=p[0]-q[0],p[1]-q[1];n=x*x+y*y;dot=u*x+v*y
        if not n or dot<=0:return Fraction(u*u+v*v)
        if dot>=n:return Fraction((p[0]-r[0])**2+(p[1]-r[1])**2)
        return Fraction((u*y-v*x)**2,n)
    if (orientation(a,b,c)*orientation(a,b,d)<=0 and orientation(c,d,a)*orientation(c,d,b)<=0
            and all(max(min(a[i],b[i]),min(c[i],d[i]))<=min(max(a[i],b[i]),max(c[i],d[i])) for i in (0,1))):
        return Fraction(0)
    return min(point_segment(a,c,d),point_segment(b,c,d),point_segment(c,a,b),point_segment(d,a,b))


def on_centerline(item, point_nm):
    if item.GetClass()!='PCB_TRACK' or len(point_nm)!=2:
        return False
    if any(type(v) is not int or abs(v)>2_147_483_647 for v in point_nm):
        return False
    a,b=item.GetStart(),item.GetEnd();x,y=point_nm
    dx,dy=b.x-a.x,b.y-a.y
    return bool((dx or dy) and (x-a.x)*dy==(y-a.y)*dx
        and 0<=(x-a.x)*dx+(y-a.y)*dy<=dx*dx+dy*dy)


def sites(item, *, toward_nm=None, max_sites=8):
    """Uniform and nearest-projection candidates, snapped ON the real line."""
    if (type(max_sites) is not int or not 0<=max_sites<=16
            or (toward_nm is not None and (len(toward_nm)!=2
                or any(type(v) is not int or abs(v)>2_147_483_647 for v in toward_nm)))):
        raise ValueError('bounded_native_track_contact_domain_required')
    if item.GetClass()!='PCB_TRACK' or max_sites==0:return []
    a,b=item.GetStart(),item.GetEnd();dx,dy=b.x-a.x,b.y-a.y
    if not (dx or dy) or (dx and dy and abs(dx)!=abs(dy)):
        return []
    # On an octilinear native segment, an integer scalar gives exact integer
    # centreline contacts. Independently rounding x and y can move a point
    # off a 45 degree centreline, falsely turning proximity into ownership.
    n=max(abs(dx),abs(dy));ux=0 if not dx else (1 if dx>0 else -1)
    uy=0 if not dy else (1 if dy>0 else -1)
    steps={round(n*i/(max_sites+1)) for i in range(1,max_sites+1)}
    if toward_nm is not None:
        t=round(((toward_nm[0]-a.x)*ux+(toward_nm[1]-a.y)*uy)/(ux*ux+uy*uy))
        steps.add(max(1,min(n-1,t)))
    points=[(int(a.x+ux*s),int(a.y+uy*s)) for s in steps if 0<s<n]
    if toward_nm is None:points.sort(key=lambda p:(math.dist(p,((a.x+b.x)/2,(a.y+b.y)/2)),p))
    else:points.sort(key=lambda p:(math.dist(p,toward_nm),p))
    return [p for p in points if on_centerline(item,p)][:max_sites]
