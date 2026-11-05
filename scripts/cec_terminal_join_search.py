"""Bounded chamfered alternatives for provisional diagonal terminal joins.

Only new proposal copper changes. Exact endpoints, widths, layers and every
barrel remain fixed. These are search options, never clearance/style/field
permission; a caller must independently validate the complete selected route.
"""
import itertools
import math
import time
import pcbnew


def variants(ops, *, max_span_nm=500000):
    if (type(max_span_nm) is not int or not 1<=max_span_nm<=1000000
            or not isinstance(ops,list) or not 1<=len(ops)<=128):
        raise ValueError('bounded_provisional_terminal_join_required')
    indices=[i for i,op in enumerate(ops) if op[0]=='trk']
    if not indices:return []
    def choices(op):
        _,s,t,w,layer=op;s=tuple(s);t=tuple(t)
        dx,dy=t[0]-s[0],t[1]-s[1]
        rows=[[op]]
        if not dx or abs(dx)!=abs(dy) or abs(dx)>max_span_nm:return rows
        size=abs(dx)//3
        if size<1:return rows
        for corner in ((s[0],t[1]),(t[0],s[1])):
            def inset(start,end):
                return tuple(end[k]-(size if end[k]>start[k] else -size if end[k]<start[k] else 0)
                    for k in range(2))
            before=inset(s,corner);after=inset(t,corner)
            points=[s,before,after,t]
            rows.append([('trk',pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),w,layer)
                for a,b in zip(points,points[1:])])
        return rows
    first,last=indices[0],indices[-1]
    menus={i:choices(ops[i]) for i in sorted({first,last})}
    out=[]
    for selected in itertools.product(*menus.values()):
        replacements=dict(zip(menus,selected))
        candidate=[item for i,op in enumerate(ops) for item in replacements.get(i,[op])]
        if len(candidate)<=128:out.append(candidate)
    return out


def accept(board, ops, *, net_code, clearance_nm, validate, deadline=None):
    """Mutate only the selected proposal list, only after ALL caller checks.

    Original route is tested first. Refusal leaves the original list intact;
    no native BOARD items, source conductors or fabrication rules are changed.
    """
    import cec_fr as fr
    if not callable(validate):raise ValueError('complete_terminal_join_validator_required')
    if deadline is not None and (type(deadline) not in (int,float)
            or not math.isfinite(deadline) or deadline>time.monotonic()+80.):
        raise ValueError('finite_terminal_join_verification_lease_required')
    for candidate in variants(ops):
        if deadline is not None and time.monotonic()>=deadline:return False
        cache={}
        if any(deadline is not None and time.monotonic()>=deadline
            or not fr._edge_leg_clear(board,op[1],op[2],op[3]//2+clearance_nm)
            or not fr._tap_foreign_clear(board,op[1],op[2],op[3],op[4],clearance_nm,
                {net_code},foreign_cache=cache) for op in candidate if op[0]=='trk'):
            continue
        if validate(candidate) and (deadline is None or time.monotonic()<deadline):
            ops[:]=candidate
            return True
    return False
