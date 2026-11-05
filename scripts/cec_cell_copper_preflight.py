"""Native retained-copper screening for whole-cell placement proposals.

Courtyard legality does not establish copper legality. A proposal may put a
new land on an immutable power track or barrel even though every package fits.
This read-only oracle names those exact source objects before reconstruction.
It is a preflight, not hole/mask/current qualification or routing admission.
"""
import math

import pcbnew


def check(board, refs, *, retained_uuids, clearance_nm=None, max_checks=2_000_000):
    """Check every selected copper land on every enabled native copper layer.

    The caller supplies an exact retained object scope, not a blanket net
    exemption or a producer's claim that missing routes are already complete.
    Same-net contact is permitted here, but proves no rated current path.
    Unknown/missing objects and exhausted budgets fail closed. No net codes,
    footprint poses, tracks, groups, zones or connectivity are modified.
    """
    import cec_decoupler_cell as cell
    refs, ids = tuple(refs), tuple(retained_uuids)
    if (not refs or len(refs)>64 or len(set(refs))!=len(refs)
            or any(not isinstance(r,str) or not r for r in refs)
            or len(ids)>16384 or len(set(ids))!=len(ids)
            or any(not isinstance(u,str) or not u for u in ids)
            or type(max_checks) is not int or not 1<=max_checks<=4_000_000
            or (clearance_nm is not None and (type(clearance_nm) is not int
                or not 0<=clearance_nm<=2_000_000))):
        raise ValueError('bounded_exact_cell_and_retained_copper_scope_required')
    fps={fp.GetReference():fp for fp in board.GetFootprints()}
    if len(fps)!=len(list(board.GetFootprints())) or not set(refs)<=fps.keys():
        raise ValueError('cell_footprint_identity_missing_or_ambiguous')
    copper={t.m_Uuid.AsString():t for t in board.GetTracks()}
    if not set(ids)<=copper.keys():
        raise ValueError('retained_copper_identity_missing')
    if any(copper[u].GetClass() not in ('PCB_TRACK','PCB_ARC','PCB_VIA') for u in ids):
        raise ValueError('unsupported_retained_copper_primitive')
    layers=tuple(board.GetEnabledLayers().CuStack())
    minimum=max(int(board.GetDesignSettings().m_MinClearance),clearance_nm or 0)
    classes={}
    def clearance(net):
        if net not in classes:classes[net]=max(minimum,int(cell._netclass(board,net)['clearance']))
        return classes[net]
    # Shapes are immutable for this invocation; avoid rebuilding connectivity
    # or generating a fresh effective shape for each pad/copper pair.
    shapes={layer:[(u,copper[u],copper[u].GetEffectiveShape(layer)) for u in ids
                   if copper[u].IsOnLayer(layer)] for layer in layers}
    conflicts=[];checked=0;complete=True
    for ref in sorted(refs):
        for pad in fps[ref].Pads():
            for layer in layers:
                if not pad.IsOnLayer(layer):continue
                shape=pad.GetEffectiveShape(layer)
                for uid,item,other in shapes[layer]:
                    if checked>=max_checks:
                        complete=False;break
                    checked+=1
                    if pad.GetNetCode()>0 and item.GetNetCode()==pad.GetNetCode():continue
                    gap=max(clearance(pad.GetNetname()),clearance(item.GetNetname()))
                    if shape.Collide(other,gap):
                        conflicts.append(dict(ref=ref,pad=pad.GetNumber(),
                            pad_uuid=pad.m_Uuid.AsString(),pad_net=pad.GetNetname(),
                            conductor_uuid=uid,conductor_net=item.GetNetname(),
                            kind=item.GetClass(),layer=board.GetLayerName(layer),
                            clearance_nm=gap,overlap=bool(shape.Collide(other,0))))
                if not complete:break
            if not complete:break
        if not complete:break
    return dict(schema=1,ok=complete and not conflicts,complete=complete,
        conflicts=conflicts,checks=checked,retained_items=len(ids),
        errors=[] if complete else ['native_copper_preflight_budget_exhausted'],
        scope='native_foreign_retained_track_arc_and_barrel_clearance',
        release_authority=False,routing_admitted=False,
        requires_zone_refill_hole_mask_current_and_whole_board_receiving=True)


def pose_trial(board, refs, delta_mm, *, retained_uuids, clearance_nm=None, pose_validator=None):
    """Temporarily translate a complete cell, measure, and restore exactly."""
    if (len(delta_mm)!=2 or not all(math.isfinite(v) for v in delta_mm)
            or math.hypot(*delta_mm)>64):
        raise ValueError('bounded_finite_cell_translation_required')
    selected=[board.FindFootprintByReference(r) for r in refs]
    if any(fp is None for fp in selected):raise ValueError('cell_member_missing')
    grouped={i.m_Uuid.AsString() for g in board.Groups() for i in g.GetItems()}
    if any(fp.IsLocked() or fp.m_Uuid.AsString() in grouped for fp in selected):
        raise ValueError('protected_cell_member')
    old=[tuple(fp.GetPosition()) for fp in selected]
    move=pcbnew.VECTOR2I(*(round(v*1e6) for v in delta_mm))
    try:
        for fp in selected:fp.Move(move)
        result=check(board,refs,retained_uuids=retained_uuids,clearance_nm=clearance_nm)
        if result['ok'] and pose_validator is not None:
            evidence=pose_validator(board)
            if not isinstance(evidence,dict) or type(evidence.get('ok')) is not bool:
                raise ValueError('independent_pose_oracle_evidence_missing')
            result['additional_pose_check']=evidence
            result['ok']=evidence['ok']
        return result
    finally:
        for fp,at in zip(selected,old):fp.SetPosition(pcbnew.VECTOR2I(*at))


def translation_menu(board,refs,*,retained_uuids,bounds_mm,max_trials=256,timeout_s=10.,pose_validator=None):
    """Conservative contact events; exact native oracle filters each trial.

    Net- and layer-specific land/capsule forbidden rectangles produce a
    finite translation domain. Only proposal geometry uses bounding boxes;
    the final check uses KiCad's effective shapes. This cannot grow the board
    or move a conductor, and a failed finite domain is not an unroutability
    proof. Entire caller-defined cell relationships remain rigid.
    """
    from shapely.geometry import box
    from shapely.ops import unary_union
    import time
    if (len(bounds_mm)!=4 or not all(math.isfinite(v) for v in bounds_mm)
            or bounds_mm[0]>=bounds_mm[2] or bounds_mm[1]>=bounds_mm[3]
            or max(abs(v) for v in bounds_mm)>6
            or type(max_trials) is not int or not 1<=max_trials<=256
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10):
        raise ValueError('bounded_two_dimensional_cell_translation_domain_required')
    started=time.monotonic()
    original=pose_trial(board,refs,(0.,0.),retained_uuids=retained_uuids,pose_validator=pose_validator)
    if original['ok']:return dict(ok=True,trials=0,delta_mm=[0.,0.],preflight=original)
    if not original['complete']:return dict(ok=False,trials=0,preflight=original)
    ids=set(retained_uuids);tracks=[t for t in board.GetTracks() if t.m_Uuid.AsString() in ids]
    minimum=int(board.GetDesignSettings().m_MinClearance)
    import cec_decoupler_cell as cell
    classes={}
    def clearance(net):
        if net not in classes:classes[net]=max(minimum,int(cell._netclass(board,net)['clearance']))
        return classes[net]
    domain=box(*bounds_mm);forbidden=[]
    for ref in refs:
        fp=board.FindFootprintByReference(ref)
        for pad in fp.Pads():
            for layer in board.GetEnabledLayers().CuStack():
                if not pad.IsOnLayer(layer):continue
                pb=pad.GetEffectiveShape(layer).BBox()
                for item in tracks:
                    if not item.IsOnLayer(layer) or (pad.GetNetCode()>0
                            and pad.GetNetCode()==item.GetNetCode()):continue
                    tb=item.GetEffectiveShape(layer).BBox()
                    gap=max(clearance(pad.GetNetname()),clearance(item.GetNetname()))+1
                    rect=box((tb.GetLeft()-pb.GetRight()-gap)/1e6,
                        (tb.GetTop()-pb.GetBottom()-gap)/1e6,
                        (tb.GetRight()-pb.GetLeft()+gap)/1e6,
                        (tb.GetBottom()-pb.GetTop()+gap)/1e6)
                    if rect.intersects(domain):forbidden.append(rect)
    free=domain.difference(unary_union(forbidden)) if forbidden else domain
    polys=[free] if free.geom_type=='Polygon' else list(getattr(free,'geoms',()))
    sites=set()
    for poly in polys:
        if poly.geom_type!='Polygon' or poly.is_empty:continue
        point=poly.representative_point();sites.add((point.x,point.y))
        sites.update(tuple(p) for p in poly.exterior.coords[:-1])
    # A diagonal conductor's bounding rectangle can cover the entire small
    # domain even though its real capsule leaves ample legal space. Do not
    # declare such an approximation to be proof that placement cannot fit.
    # Interleave a finite coarse native fallback, including axial exits at
    # each radius, without deleting any retained obstacle from the oracle.
    coarse=set()
    x0,y0,x1,y1=bounds_mm
    xs=[x0+(x1-x0)*i/24 for i in range(25)]
    ys=[y0+(y1-y0)*i/24 for i in range(25)]
    coarse.update((x,y) for x in xs for y in ys)
    event_sites=sorted(sites,key=lambda p:(math.hypot(*p),p))
    fallback=sorted(coarse,key=lambda p:(math.hypot(*p),p))
    candidates=[];seen=set()
    for index in range(max(len(event_sites),len(fallback))):
        for menu in (event_sites,fallback):
            if index<len(menu) and menu[index] not in seen:
                seen.add(menu[index]);candidates.append(menu[index])
    history=[]
    for delta in candidates[:max_trials]:
        if time.monotonic()-started>=timeout_s:
            return dict(ok=False,trials=len(history),preflight=original,history=history,
                reason='native_cell_domain_deadline',routing_admitted=False,release_authority=False)
        evidence=pose_trial(board,refs,delta,retained_uuids=retained_uuids,pose_validator=pose_validator)
        history.append(dict(delta_mm=list(delta),ok=evidence['ok'],
            conflicts=len(evidence['conflicts']),additional_pose_check=evidence.get('additional_pose_check')))
        if evidence['ok']:
            return dict(ok=True,trials=len(history),delta_mm=list(delta),preflight=evidence,
                history=history,routing_admitted=False,release_authority=False)
    return dict(ok=False,trials=len(history),preflight=original,history=history,
        reason='bounded_retained_copper_cell_domain_refused',
        routing_admitted=False,release_authority=False)
