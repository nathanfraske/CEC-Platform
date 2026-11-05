"""Finite real-land contacts for typed non-return package Ground links.

Centres are not mandatory track attachment points inside a real connected
SMD land. Keep the existing wire-length limit, class-width middle, native
endpoint qualification and independently received Ground hierarchy. These
proposals add no copper, vias, current allowance or return/release authority.
"""
import math
import time

import pcbnew
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_force_current as force
import cec_fr as fr
import cec_native_pad_ports as ports


def _role(left,right):
    first,last=left.GetParentFootprint(),right.GetParentFootprint()
    model=roles.footprint_contract(first)
    return bool(model and force._uid(first)==force._uid(last) and not first.IsDNP()
        and model['pins'].get(left.GetNumber()) in ('address','reference')
        and model['pins'].get(right.GetNumber()) in ('ground','power_return')
        and not set(model['pins'].values()) & {'power_output','switch','feedback'}
        and left.GetNetCode()>0 and left.GetNetCode()==right.GetNetCode()
        and left.GetNetname()==right.GetNetname()=='GND'
        and all(p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and not p.HasHole()
            and len(tuple(p.GetLayerSet().CuStack()))==1 for p in (left,right))
        and tuple(left.GetLayerSet().CuStack())==tuple(right.GetLayerSet().CuStack()))


def _length(first,last):
    dx,dy=(abs(a-b) for a,b in zip(first,last))
    return (max(dx,dy)+(math.sqrt(2)-1)*min(dx,dy))/1e6


def contacts(board,left,right,*,maximum_wire_mm=4.,deadline=None,max_pairs=8):
    if (type(maximum_wire_mm) not in (int,float) or not math.isfinite(maximum_wire_mm)
            or not 0<maximum_wire_mm<=4. or type(max_pairs) is not int or not 1<=max_pairs<=8
            or deadline is not None and (type(deadline) not in (int,float) or not math.isfinite(deadline))):
        raise ValueError('bounded_same_package_ground_contact_proposals_required')
    if not _role(left,right):return None
    deadline=min(time.monotonic()+1.,deadline) if deadline is not None else time.monotonic()+1.
    if time.monotonic()>=deadline:return None
    width=max(200000,int(board.GetDesignSettings().m_TrackMinWidth))
    a=ports.sites(left,width_nm=width,toward_nm=tuple(right.GetPosition()),max_sites=8,deadline=deadline)
    b=ports.sites(right,width_nm=width,toward_nm=tuple(left.GetPosition()),max_sites=8,deadline=deadline)
    pairs=sorted(((s,t) for s in a for t in b if _length(s,t)<=maximum_wire_mm+1e-9),
        key=lambda p:(_length(*p),p))[:max_pairs]
    if not pairs:return None
    return dict(scope='native_nonreturn_same_package_ground_attachment_proposals',
        from_pad_uuid=force._uid(left),to_pad_uuid=force._uid(right),
        minimum_attachment_width_nm=width,maximum_wire_mm=float(maximum_wire_mm),
        minimum_octilinear_wire_mm=_length(*pairs[0]),
        pairs=[dict(start_nm=list(s),end_nm=list(t)) for s,t in pairs],
        actual_complete_wire_and_endpoint_receiving_still_required=True,
        copper_or_return_or_current_authority=False,release_authority=False)


def links(board,left,right,*,maximum_wire_mm=4.,deadline):
    proof=contacts(board,left,right,maximum_wire_mm=maximum_wire_mm,deadline=deadline)
    if proof is None:return []
    layer=int(next(iter(left.GetLayerSet().CuStack())))
    width=max(200000,int(board.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(board,'GND')['width']))
    gap=max(200000,int(board.GetDesignSettings().m_MinClearance),int(cells._netclass(board,'GND')['clearance']))
    minimum=proof['minimum_attachment_width_nm']
    escapes=tuple(fr._pad_local_escape(p,width,gap,minimum) for p in (left,right))
    choices=[];cache={}
    def accept(legs):
        if (not legs or time.monotonic()>=deadline
                or sum(math.dist(tuple(s),tuple(t)) for s,t,w in legs)>maximum_wire_mm*1e6+1e-3
                or not any(w>=width for s,t,w in legs)
                or any(w<minimum or not fr._edge_leg_clear(board,s,t,w/2+gap)
                    or not fr._tap_foreign_clear(board,s,t,w,layer,gap,{left.GetNetCode()},foreign_cache=cache)
                    for s,t,w in legs)):
            return
        ops=[('trk',tuple(s),tuple(t),int(w),layer) for s,t,w in legs]
        if ops not in choices:choices.append(ops)
    for pair in proof['pairs']:
        if time.monotonic()>=deadline:break
        a,b=tuple(pair['start_nm']),tuple(pair['end_nm'])
        for path in fr._canonical_45_xy_paths(a,b):
            if time.monotonic()>=deadline:break
            accept(fr._profiled_lastmile_path([pcbnew.VECTOR2I(*p) for p in path],width,*escapes))
    if not choices:
        for pair in proof['pairs']:
            if time.monotonic()>=deadline:break
            legs=fr._guarded_profiled_lastmile_legs(board,
                pcbnew.VECTOR2I(*pair['start_nm']),pcbnew.VECTOR2I(*pair['end_nm']),
                width,layer,gap,left.GetNetCode(),
                lambda s,t,half:fr._edge_leg_clear(board,s,t,half+gap),
                foreign_cache=cache,allow_maze=True,
                deadline_monotonic=min(deadline,time.monotonic()+1.),
                max_length_nm=maximum_wire_mm*1e6,start_escape=escapes[0],end_escape=escapes[1])
            accept(legs)
            if choices:break
    return choices
