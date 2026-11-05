"""Bounded negotiation between future return portals and constructor-owned tracks.

The caller owns the editable copper; no net/ref/product policy is inferred here.
Only full-width orthogonal detours with retained electrical contacts are allowed.
Reserved portals are feasibility candidates, not installed vias or plane signoff.
"""
from __future__ import annotations

import math

MM = 1_000_000


def point_segment_distance(point, start, end):
    dx, dy = end[0]-start[0], end[1]-start[1]
    length2 = dx*dx+dy*dy
    t = max(0., min(1., ((point[0]-start[0])*dx+(point[1]-start[1])*dy)/length2)) if length2 else 0.
    return math.hypot(point[0]-start[0]-t*dx, point[1]-start[1]-t*dy)


def detours(start, end, *, width, circles, clearance, max_trials=12):
    """One clean side-step around the whole conflicting interval, not stair steps.

    Circle radii are copper radii; inflate by the UNCHANGED track half width
    and clearance. Exact native geometry, bounds and other copper remain the
    caller's admission oracle. Non-orthogonal and endpoint-blocked cases refuse.
    """
    if len(start)!=2 or len(end)!=2 or any(len(c)!=3 for c in circles):
        raise ValueError("invalid detour dimensions")
    numbers=(*start,*end,width,clearance,*(v for c in circles for v in c))
    if not all(math.isfinite(float(v)) for v in numbers) or width<=0 or clearance<0:
        raise ValueError("invalid detour geometry")
    if not isinstance(max_trials,int) or max_trials<1 or any(c[2]<0 for c in circles):
        raise ValueError("invalid detour budget or radius")
    start,end=tuple(start),tuple(end)
    if start==end or (start[0]!=end[0] and start[1]!=end[1]):
        return []
    axis=1 if start[0]==end[0] else 0
    side=1-axis
    direction=1 if end[axis]>start[axis] else -1
    blocked=[c for c in circles if point_segment_distance(c[:2],start,end)
             < c[2]+width/2+clearance+1e-6]
    if not blocked:
        return [[start,end]]
    inflated=[(c,c[2]+width/2+clearance+.025) for c in blocked]
    lo=min(c[axis]-r for c,r in inflated)
    hi=max(c[axis]+r for c,r in inflated)
    if lo<=min(start[axis],end[axis]) or hi>=max(start[axis],end[axis]):
        return []
    candidates=[]
    for extra in (0.,.10,.25):
        for cross in (min(c[side]-r for c,r in inflated)-extra,
                      max(c[side]+r for c,r in inflated)+extra):
            near,far=(lo,hi) if direction>0 else (hi,lo)
            def p(along,across):
                return (across,along) if axis==1 else (along,across)
            path=[start,p(near,start[side]),p(near,cross),p(far,cross),
                  p(far,start[side]),end]
            candidates.append(path)
    return sorted(candidates,key=lambda p:(sum(math.dist(a,b) for a,b in zip(p,p[1:])),p))[:max_trials]


def required_ground_portals(board, *, board_path="", max_portals=128):
    """Fast exact POFV candidates BEFORE broad copper construction.

    Reuse production assignment, return-pin selection and process/clearance
    rules. Only completely qualified pad-centre portals are reserved in this
    slice; dogbones and other return-rail topologies keep their normal solver.
    """
    import pcbnew
    import cec_constraints
    import cec_decoupler_cell as cells
    import cec_fab_profile as fab
    import cec_fr
    name=fab.active_profile_name(board,hint=board_path)
    profile=fab.get_profile(name) if name else None
    geometry=fab.preferred_pofv_geometry(profile)
    report={"schema":1,"scope":"future_pad_center_portals_not_installed",
            "profile":name,"portals":[],"refused":[],"budget":max_portals}
    if not geometry:
        report["reason"]="no_declared_pofv_geometry"
        return report
    diameter,drill=geometry
    if not fab.pofv_dimensions(profile,diameter,drill)[0]:
        report["reason"]="process_geometry_refused"
        return report
    assignment=cec_constraints._device_bypass_assignment(board,project_max_mm=3.5)
    pads={}
    for row in cells._ordered_assigned_cells(board,assignment):
        req=row["requirement"]
        owner=board.FindFootprintByReference(req["ref"])
        cap=board.FindFootprintByReference(row["cap_ref"])
        rail,cp,owners=cells._cell_return_pads(req,owner,cap)
        if rail!="GND" or cp is None or not owners:
            continue
        op=min(owners,key=lambda p:math.hypot(p.GetPosition().x-cp.GetPosition().x,
                                             p.GetPosition().y-cp.GetPosition().y))
        for pad in (op,cp):
            pads[(pad.GetParentFootprint().GetReference(),pad.GetNumber(),
                  pad.m_Uuid.AsString())]=pad
    cache={}
    for index,((ref,pin,uid),pad) in enumerate(sorted(pads.items())):
        if index>=max_portals:
            report["reason"]="portal_budget_exhausted"
            break
        pos=pad.GetPosition(); code=pad.GetNetCode()
        detail={}
        checks={"smd":pad.GetAttribute()==pcbnew.PAD_ATTRIB_SMD,
            "edge":cec_fr._edge_leg_clear(board,pos,pos,pcbnew.FromMM(diameter)//2),
            "hole":cells._hole_to_hole_clear(board,pos,drill)[0],
            "copper":cec_fr._via_spot_clear(board,pos,pcbnew.FromMM(diameter),
                pcbnew.FromMM(.20),{code},drill_nm=pcbnew.FromMM(drill),net_code=code,
                contained_layers={pad.GetLayer()},foreign_cache=cache,report=detail)}
        item={"ref":ref,"pad":pin,"uuid":uid,"net":pad.GetNetname(),"net_code":code,
            "at_mm":[pos.x/MM,pos.y/MM],"diameter_mm":diameter,"drill_mm":drill,
            "layer_ids":list(board.GetEnabledLayers().CuStack())}
        if all(checks.values()):
            report["portals"].append(item)
        else:
            report["refused"].append({**item,"checks":checks,"copper":detail})
    return report


def reservation_clearance(board, minimum_mm=.25):
    """One conservative copper-spacing floor for all constructor consumers."""
    return max(float(minimum_mm),board.GetDesignSettings().m_MinClearance/MM,
        *(float(net.GetNetClassSlow().GetClearance())/MM
          for net in board.GetNetInfo().NetsByNetcode().values()))


def segment_portal_conflict(start, end, width_mm, *, net, layer_id, portals,
                            clearance_mm):
    """First measured foreign portal displaced by a full-width conductor."""
    return next((portal for portal in portals
        if portal['net'] != net and layer_id in portal['layer_ids']
        and point_segment_distance(portal['at_mm'],start,end)
            < width_mm/2+portal['diameter_mm']/2+clearance_mm), None)


def replan_owned_tracks(board, owned_tracks, portals, *, clearance_mm=.25,
                        max_tracks=32,max_trials=12):
    """Recompile only caller-owned tracks; keep every old contact and width.

    All other copper is a native obstacle. The old track is not removed until
    its replacement passes. Failed or unsupported proposals retain the original
    track. No via is fabricated here, nor is a narrowed pinch point allowed.
    """
    import pcbnew
    import cec_fr
    from cec_native_items import discard_items
    if (not math.isfinite(clearance_mm) or clearance_mm<0
            or not isinstance(max_tracks,int) or max_tracks<1
            or not isinstance(max_trials,int) or max_trials<1):
        raise ValueError("invalid native detour clearance or budget")
    # Conservative board/netclass floor, never an implicit relaxation to the
    # adapter's default clearance. Pair-specific custom DRC remains final gate.
    clearance_mm=max(clearance_mm,board.GetDesignSettings().m_MinClearance/MM,
        *(float(net.GetNetClassSlow().GetClearance())/MM
          for net in board.GetNetInfo().NetsByNetcode().values()))
    report={"schema":1,"scope":"constructor_owned_tracks_only",
            "changed":0,"trials":0,"accepted":[],"refused":[],
            "clearance_mm":clearance_mm,
            "portal_postcheck_scope":"track_obstacles_only_not_via_or_plane_signoff"}
    candidates=[t for t in owned_tracks if t.GetClass()=="PCB_TRACK"]
    for track in candidates:
        start,end=track.GetStart(),track.GetEnd()
        a,b=(start.x/MM,start.y/MM),(end.x/MM,end.y/MM)
        layer,code,width=track.GetLayer(),track.GetNetCode(),track.GetWidth()
        relevant=[p for p in portals if layer in p["layer_ids"] and p["net_code"]!=code]
        blocked=[p for p in relevant if point_segment_distance(p["at_mm"],a,b)
                 < width/(2*MM)+p["diameter_mm"]/2+clearance_mm]
        if not blocked:
            continue
        row={"uuid":track.m_Uuid.AsString(),"net":track.GetNetname(),
            "layer":board.GetLayerName(layer),"width_mm":width/MM,
            "start_mm":a,"end_mm":b,"portal_pads":[[p["ref"],p["pad"]] for p in blocked]}
        if len(report["accepted"])+len(report["refused"])>=max_tracks:
            report["budget_exhausted"]=True
            break
        if any(g.ContainsItem(track) for g in board.Groups()):
            report["refused"].append({**row,"reason":"group_owner_recompile_required"})
            continue
        paths=detours(a,b,width=width/MM,
            circles=[(*p["at_mm"],p["diameter_mm"]/2) for p in relevant],
            clearance=clearance_mm,max_trials=max_trials)
        contacts=[]
        original=track.GetEffectiveShape(layer)
        for other in [*board.GetTracks(),*(p for f in board.GetFootprints() for p in f.Pads())]:
            if (other.m_Uuid.AsString()==row["uuid"] or other.GetNetCode()!=code
                    or layer not in other.GetLayerSet().CuStack()):
                continue
            shape=other.GetEffectiveShape(layer)
            if original.Collide(shape,0):
                contacts.append(shape)
        selected=None; cache={}
        for path in paths:
            report["trials"]+=1
            segments=[(pcbnew.VECTOR2I_MM(*s),pcbnew.VECTOR2I_MM(*e)) for s,e in zip(path,path[1:])]
            shapes=[pcbnew.SHAPE_SEGMENT(s,e,width) for s,e in segments]
            if not all(any(shape.Collide(contact,0) for shape in shapes) for contact in contacts):
                continue
            if not all(cec_fr._edge_leg_clear(board,s,e,width//2)
                       and cec_fr._tap_foreign_clear(board,s,e,width,layer,
                           pcbnew.FromMM(clearance_mm),{code},foreign_cache=cache)
                       for s,e in segments):
                continue
            if any(point_segment_distance(p["at_mm"],s,e)
                   < width/(2*MM)+p["diameter_mm"]/2+clearance_mm
                   for p in relevant for s,e in zip(path,path[1:])):
                continue
            selected=segments;break
        if selected is None:
            report["refused"].append({**row,"reason":"no_full_width_contact_preserving_detour"})
            continue
        # Allocate the complete replacement before destroying the old native
        # item. The caller owns these segments; unrelated groups stay intact.
        replacements=[]
        try:
            for s,e in selected:
                item=pcbnew.PCB_TRACK(board)
                item.SetStart(s);item.SetEnd(e);item.SetWidth(width);item.SetLayer(layer)
                item.SetNetCode(code);item.SetLocked(track.IsLocked())
                board.Add(item);replacements.append(item)
        except Exception:
            discard_items(board,replacements)
            raise
        discard_items(board,[track])
        report["changed"]+=1
        report["accepted"].append({**row,"path_mm":[[s.x/MM,s.y/MM] for s,_ in selected]
            +[[selected[-1][1].x/MM,selected[-1][1].y/MM]],"retained_contacts":len(contacts)})
    report["remaining_blocked_portals"]=[p for p in portals if any(
        t.GetNetCode()!=p["net_code"] and t.GetClass()=="PCB_TRACK"
        and t.GetLayer() in p["layer_ids"] and point_segment_distance(p["at_mm"],
            (t.GetStart().x/MM,t.GetStart().y/MM),(t.GetEnd().x/MM,t.GetEnd().y/MM))
            < t.GetWidth()/(2*MM)+p["diameter_mm"]/2+clearance_mm
        for t in board.GetTracks())]
    return report
