"""Bounded portal proposals at immutable power-reservation boundaries.

Proposal-only geometry: rectangles cannot certify a via, fan-in, return field,
or route. All original rows remain; the native solver owns every admission.
"""
from collections import defaultdict
import math


def _blocked_interval(origin, direction, rect, inflation, lower, upper):
    """Intersection of a finite ray parameter and a closed inflated rectangle."""
    lo,hi=lower,upper
    for coordinate,velocity,a,b in zip(origin,direction,rect[:2],rect[2:]):
        a,b=min(a,b)-inflation,max(a,b)+inflation
        if abs(velocity)<1e-12:
            if coordinate<a or coordinate>b:return None
            continue
        enter,leave=sorted(((a-coordinate)/velocity,(b-coordinate)/velocity))
        lo,hi=max(lo,enter),min(hi,leave)
        if lo>hi:return None
    return lo,hi


def free_intervals(origin, direction, obstacles, *, inflation, lower, upper):
    """Complement of blocked closed intervals inside the caller's exact budget."""
    values=(*origin,*direction,inflation,lower,upper)
    if (not all(math.isfinite(float(v)) for v in values) or inflation<0
            or lower>upper or math.hypot(*direction)<1e-12):
        raise ValueError('invalid bounded portal ray')
    blocked=[]
    for rect in obstacles:
        if len(rect)!=4 or not all(math.isfinite(float(v)) for v in rect):
            raise ValueError('invalid reservation rectangle')
        span=_blocked_interval(origin,direction,rect,inflation,lower,upper)
        if span is not None:blocked.append(span)
    free=[];cursor=lower
    for lo,hi in sorted(blocked):
        if lo>cursor:free.append((cursor,lo))
        cursor=max(cursor,hi)
    if cursor<upper:free.append((cursor,upper))
    return free


def boundary_rows(rows, reservations, *, p_net, n_net, diameter_mm,
                  clearance_mm, inset_mm=.01, max_intervals=2):
    """Add finite leads in clear intervals missed by the original lead menu.

    Every row keeps its original heading, polarity, lateral displacement and
    per-heading lead bounds. Rectangles on any layer constrain through vias.
    Only the exact member's own net is exempt. Inset is a search margin, never
    a clearance exception. Native guards must still evaluate the full board.
    """
    if (not all(math.isfinite(float(v)) and float(v)>=0 for v in
                (diameter_mm,clearance_mm,inset_mm)) or diameter_mm<=0
            or inset_mm<=0 or type(max_intervals) is not int or max_intervals<1):
        raise ValueError('invalid portal boundary policy')
    rectangles=[]
    for reservation in reservations:
        if not isinstance(reservation,dict):raise ValueError('invalid reservation')
        rect=tuple(float(reservation[k]) for k in ('x0','y0','x1','y1'))
        if not all(math.isfinite(v) for v in rect):raise ValueError('nonfinite reservation')
        rectangles.append((str(reservation.get('net') or ''),rect))
    groups=defaultdict(list)
    for row in rows:
        key=(row['side'],row['sign'],tuple(row['route_heading']),float(row['lateral_mm']))
        groups[key].append(row)
    added=[]
    for group in groups.values():
        first=min(group,key=lambda r:r['lead_mm'])
        low,high=min(r['lead_mm'] for r in group),max(r['lead_mm'] for r in group)
        if high-low<=2*inset_mm:continue
        hx,hy=first['route_heading'];lead=first['lead_mm']
        # Use each actual member origin: the two annular lands, not just their
        # midpoint, must avoid foreign reservations. Intersect their domains.
        intervals=[(low,high)]
        for member,net in (('p',p_net),('n',n_net)):
            origin=(first[member][0]-hx*lead,first[member][1]-hy*lead)
            member_free=free_intervals(origin,(hx,hy),
                [rect for owner,rect in rectangles if owner!=net],
                inflation=diameter_mm/2+clearance_mm,lower=low,upper=high)
            intervals=[(max(a,c),min(b,d)) for a,b in intervals for c,d in member_free
                       if min(b,d)-max(a,c)>2*inset_mm]
        # A wide interval already represented by the old lead menu is not a
        # new failure hypothesis. Fill only genuinely unsampled clear windows.
        intervals=[(a,b) for a,b in intervals if not any(
            a+inset_mm<=r['lead_mm']<=b-inset_mm for r in group)]
        intervals=sorted(intervals,key=lambda span:(-(span[1]-span[0]),span))[:max_intervals]
        existing={round(float(r['lead_mm'])*1e6) for r in group}
        for a,b in intervals:
            for new_lead in ((a+b)/2,a+inset_mm,b-inset_mm):
                identity=round(new_lead*1e6)
                if identity in existing:continue
                existing.add(identity)
                delta=new_lead-lead
                new=dict(first,lead_mm=round(new_lead,6),
                    proposal_source='power-boundary-clear-interval',
                    boundary_interval_mm=[round(a,6),round(b,6)])
                for key in ('center','p','n'):
                    new[key]=(first[key][0]+hx*delta,first[key][1]+hy*delta)
                added.append(new)
    return added
