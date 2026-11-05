"""Finite proposals for relocating an uncommitted two-layer transition.

Only a declared virtual degree-two transition can move. Physical contacts,
other vertices, layer tags and widths stay fixed. The caller must qualify the
entire required via field and both landing connections before committing.
"""
import math


def candidates(plan, center, *, fixed_contacts, face_tag='face',
               radius_scales=(1., .75, .5), full_width_extensions_mm=(), limit=24):
    """Yield (replacement, new_center) without lengthening the narrow neck.

    A direct pad-to-transition face neck is rotated in 45-degree increments
    and optionally shortened. The other incident edge is rewired at its full
    original width with an orthogonal elbow. Optional, explicitly bounded
    extensions move the field farther out using the BODY width on the face,
    never by making the narrow pad neck longer. Detailed routing may move an
    elbow, but not the physical contact or the new transition. Branches and
    already physical/via-in-pad transition locations are deliberately refused.
    These are proposals only; geometry, landing and electrical qualification
    remain the caller's responsibility.
    """
    rows=[tuple(s) for s in plan]
    center=tuple(center)
    fixed={tuple(p) for p in fixed_contacts}
    if (len(center)!=2 or any(not math.isfinite(float(v)) for v in center)
            or type(limit) is not int or not 0<=limit<=128
            or any(not math.isfinite(float(s)) or not 0<s<=1 for s in radius_scales)
            or len(full_width_extensions_mm)>4
            or any(not math.isfinite(float(v)) or not 0<v<=25
                   for v in full_width_extensions_mm)
            or any(len(s)!=6 or any(not math.isfinite(float(v)) for v in s[:5])
                   or s[4]<=0 for s in rows)
            or any(len(p)!=2 or any(not math.isfinite(float(v)) for v in p) for p in fixed)):
        raise ValueError('invalid transition search declaration')
    if center in fixed:
        return
    incident=[(i,s) for i,s in enumerate(rows) if center in (s[:2],s[2:4])]
    face=[(i,s) for i,s in incident if s[5]==face_tag]
    if len(incident)!=2 or len(face)!=1:
        return
    fi,neck=face[0]
    contact=neck[2:4] if neck[:2]==center else neck[:2]
    if contact not in fixed:
        return
    bi,body=next((i,s) for i,s in incident if i!=fi)
    other=body[2:4] if body[:2]==center else body[:2]
    dx,dy=center[0]-contact[0],center[1]-contact[1]
    length=math.hypot(dx,dy)
    if length<1e-6 or not (abs(dx)<1e-6 or abs(dy)<1e-6 or abs(abs(dx)-abs(dy))<1e-6):
        return
    # A third edge passing through the proposed vertex is also a branch.
    from shapely.geometry import LineString, Point
    if any(LineString((s[:2],s[2:4])).distance(Point(center))<1e-6
           for i,s in enumerate(rows) if i not in (fi,bi)):
        return
    count=0;seen={center}
    turns=(0,2,-2,1,-1,3,-3,4)
    base=[(scale,0.,turn) for scale in radius_scales for turn in turns]
    extensions=[(1.,length_mm,turn) for turn in turns
                for length_mm in sorted(full_width_extensions_mm,reverse=True)]
    # Interleave topology families. Appending extensions after every shrinking
    # trial made them unreachable under the caller's shared time budget.
    portfolio=[row for i in range(max(len(base),len(extensions)))
               for rows in (base,extensions) for row in rows[i:i+1]]
    for scale,extension,turn in portfolio:
        angle=turn*math.pi/4
        rx,ry=dx*math.cos(angle)-dy*math.sin(angle),dx*math.sin(angle)+dy*math.cos(angle)
        neck_end=(round(contact[0]+scale*rx,6),round(contact[1]+scale*ry,6))
        q=(round(contact[0]+(scale+extension/length)*rx,6),
           round(contact[1]+(scale+extension/length)*ry,6))
        if (q in seen or q in fixed or (extension and neck_end in fixed)
                or math.dist(neck_end,contact)>length+1e-6):
            continue
        seen.add(q)
        if count>=limit:
            return
        replacement=[]
        for i,s in enumerate(rows):
            if i==fi:
                a,b=(neck_end,contact) if s[:2]==center else (contact,neck_end)
                replacement.append((*a,*b,s[4],s[5]))
                if extension:
                    u,v=(q,neck_end) if s[:2]==center else (neck_end,q)
                    replacement.append((*u,*v,max(s[4],body[4]),face_tag))
            elif i==bi:
                a,b=(q,other) if s[:2]==center else (other,q)
                elbow=(a[0],b[1])
                replacement.extend((*u,*v,s[4],s[5])
                    for u,v in ((a,elbow),(elbow,b)) if math.dist(u,v)>1e-6)
            else:
                replacement.append(s)
        count+=1
        yield replacement,q
