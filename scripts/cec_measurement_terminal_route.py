"""Bounded proposals for a source-proved isolated sense terminal.

This is not whole-net targeting or numeric current authority. The immutable
parent's manufacturer/schematic demand names both actual lands. Every new
track avoids other same-net material outside the physical pickup land; native
foreign clearance, field, saved topology and complete-cell receiving are due.
"""
import math
import time

import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_device_power_roles as roles
import cec_kelvin_copper_cut as cut
import cec_measurement_leaf as leaf


def assess_path_craft(board,ops,*,net,deadline):
    """Receive the complete proposed surface chain, including its pickup tail.

    Temporary tracks remain outside the Source BOARD. Retained copper is
    included by the existing quality receiver, so a clean maze prefix may
    not double back into its fixed tail or a retained Source endpoint.
    This grants no contact, current, clearance or Kelvin authority.
    """
    import cec_route_quality as quality
    if not ops or any(op[0]!='trk'for op in ops):
        raise ValueError('complete_surface_measurement_craft_chain_required')
    return quality.assess_proposed_route(board,[dict(net=net,layer=int(op[4]),width_nm=op[3],
        start_nm=list(op[1]),end_nm=list(op[2]))for op in ops],deadline=deadline)


def assess_path_field(board,ops,*,net,deadline,netclass_resolver=None,board_hint=None):
    """Check the whole proposed input, including its immutable pickup tail.

    This is the existing native proposal receiver, not a name-only exemption
    or a shielding assumption. Saved-board refill/whole-field admission still
    applies separately. Unknown or incomplete evidence may not fund a path.
    """
    import cec_field_coupling as field
    if not ops or any(op[0]!='trk'for op in ops):
        raise ValueError('complete_surface_measurement_field_chain_required')
    return field.assess_proposed_tracks(board,[dict(net=net,layer=int(op[4]),width_nm=op[3],
        start_nm=list(op[1]),end_nm=list(op[2]))for op in ops],deadline=deadline,
        netclass_resolver=netclass_resolver,board_hint=board_hint)


def _field_runs_clear(points,width_nm,layer,pruning):
    """Splitting one collinear run must not bypass parallel-run pruning."""
    if len(points)<2:return False
    first,last=points[:2]
    for following in points[2:]:
        ux,uy=last[0]-first[0],last[1]-first[1]
        vx,vy=following[0]-last[0],following[1]-last[1]
        if ux*vy==uy*vx and ux*vx+uy*vy>0:
            last=following;continue
        if pruning(pcbnew.VECTOR2I(*first),pcbnew.VECTOR2I(*last),width_nm,layer)is not True:return False
        first,last=last,following
    return pruning(pcbnew.VECTOR2I(*first),pcbnew.VECTOR2I(*last),width_nm,layer)is True


def _direct_pickup(demand, target):
    """A named direct shunt supplies direction, not a whole-net aperture."""
    topology=demand.get('source_topology',{})
    if topology.get('kind')!='direct':return None
    leg=demand['source_segment'].get('leg')
    if leg not in ('p','n'):raise ValueError('exact_direct_measurement_leg_required')
    side=topology.get(leg,{});opposite=topology.get('n' if leg=='p' else 'p',{})
    owner=target.GetParentFootprint()
    pads=list(owner.Pads())
    peers=[p for p in pads if p.GetNumber()==opposite.get('anchor_pad')]
    if (len(pads)!=2 or len(peers)!=1 or force._uid(peers[0])==force._uid(target)
            or side.get('anchor_ref')!=owner.GetReference()
            or opposite.get('anchor_ref')!=owner.GetReference()
            or side.get('anchor_pad')!=target.GetNumber()
            or side.get('anchor_net')!=target.GetNetname()
            or opposite.get('anchor_net')!=peers[0].GetNetname()
            or side.get('series')!=[] or opposite.get('series')!=[]
            or peers[0].GetNetname()==target.GetNetname()
            or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in pads)):
        raise ValueError('exact_source_two_land_direct_shunt_direction_required')
    return peers[0]


def contact_guard(board, demand, *, width_nm, deadline):
    from shapely.geometry import LineString, Point, GeometryCollection
    from shapely.ops import unary_union
    from shapely.prepared import prep
    if (type(width_nm) is not int or not max(200000,int(board.GetDesignSettings().m_TrackMinWidth))
            <=width_nm<=350000 or not math.isfinite(deadline)):
        raise ValueError('bounded_manufacturer_nonload_input_width_required')
    pads={force._uid(p):p for f in board.GetFootprints() for p in f.Pads()}
    root=pads.get(demand['pad_uuid']);target=pads.get(demand['target_uuid'])
    model=roles.footprint_contract(root.GetParentFootprint()) if root else None
    if (not root or not target or not model or root.HasHole()
            or root.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
            or force._uid(root.GetParentFootprint())!=demand['owner_uuid']
            or root.GetNumber()!=demand['input_pin']
            or model['pins'].get(root.GetNumber())!='measurement'
            or root.GetNetname()!=demand['net'] or target.GetNetname()!=demand['net']):
        raise ValueError('actual_source_isolated_manufacturer_measurement_demand_required')
    # Rebuild the component: a producer's singleton/UUID assertion is not
    # authority to ignore existing same-net force contact at the root land.
    import cec_measurement_terminal_access as access
    import cec_measurement_auxiliary_cut as auxiliary
    graph=fr._read_only_route_connectivity(board)
    connected={force._uid(i):i for i in [root,*graph.GetConnectedItems(root)]}
    island=access._input_island(root,list(connected.values()),model,deadline=deadline)
    supplied=demand.get('source_input_island_uuids')
    if (not island or type(supplied) is not list or any(type(u) is not str for u in supplied)
            or len(supplied)!=len(set(supplied)) or sorted(supplied)!=island):
        raise ValueError('exact_native_stranded_measurement_component_required')
    strap=None
    if island!=[force._uid(root)]:
        left=deadline-time.monotonic()
        if left<=0:raise ValueError('measurement_source_component_deadline')
        strap=auxiliary.plan(board,force._uid(root),timeout_s=min(10.,left))
        owned={force._uid(root),*strap['track_uuids'],*strap['boundary_uuids']}
        if len(island)!=3 or set(island)!=owned:
            raise ValueError('exact_literal_auxiliary_input_component_required')
    end=demand['source_segment']['end']
    if (target.GetParentFootprint().GetReference()!=end['ref'] or target.GetNumber()!=end['pad']
            or list(target.GetPosition())!=demand['b_nm']):
        raise ValueError('exact_schematic_measurement_pickup_land_required')
    common=sorted(set(root.GetLayerSet().CuStack())&set(target.GetLayerSet().CuStack()))
    if len(common)!=1:raise ValueError('unique_source_surface_pickup_layer_required')
    layer=int(common[0]);work=cut._Work(deadline)
    opposite=_direct_pickup(demand,target)
    inner_min=None
    if opposite is not None:
        import cec_constraints
        inner_min=cec_constraints._param('kelvin-sense-from-inner-pad','inner_min_mm',.1)
        if (type(inner_min) not in (int,float) or not math.isfinite(inner_min) or inner_min<0):
            raise ValueError('invalid_kelvin_inner_min_policy')
    root_shape=cut._shape(root,layer,True,work)
    pickup=cut._shape(target,layer,True,work)
    layers=tuple(map(int,board.GetEnabledLayers().CuStack()))
    forbidden={face:[] for face in layers}
    for item in [*(p for f in board.GetFootprints() for p in f.Pads()),*board.GetTracks(),
            *[z for z in board.Zones() if not z.GetIsRuleArea()]]:
        work.tick()
        if item.GetNetCode()!=root.GetNetCode():continue
        for face in layers:
            if not item.IsOnLayer(face):continue
            if item.GetClass()=='ZONE':
                if not item.IsFilled():raise ValueError('same_net_saved_measurement_copper_unknown')
                shape=cut._poly(item.GetFilledPolysList(face),work)
            else:shape=cut._shape(item,face,True,work)
            # An SMD pickup aperture exists only on its actual copper face.
            # A barrel must not acquire a same-net force bus underneath it
            # by projecting that surface aperture onto the whole stack.
            allowed=pickup if face==layer else GeometryCollection()
            if force._uid(item) in connected:
                # A certified package strap remains forbidden everywhere
                # except the departure's original root-land aperture. Never
                # license its interior, the other input land, or another face.
                if face==layer:
                    allowed=allowed.union(root_shape.buffer(width_nm/2+1002))
            if force._uid(item)==force._uid(target):
                allowed=allowed.union(pickup.buffer(width_nm/2+1002))
            forbidden[face].append(shape.difference(allowed))
    cut._validate_linear_epochs(work)
    merged={face:unary_union(shapes)for face,shapes in forbidden.items()}
    blocked={face:prep(shape)for face,shape in merged.items()}
    # Ordinary electrical obstacle discovery correctly ignores same-net
    # metal. A quiet input may nevertheless be FORBIDDEN to touch that
    # force copper outside its one actual pickup. Make those exact existing
    # exclusions visible to channel proposal geometry as well as hop vetoes.
    # These expanded AABBs are bounded hints only: neither a box gap nor its
    # absence grants contact, clearance, route or no-path authority.
    hint_boxes=[];pending=[merged[layer]]
    while pending:
        work.tick();shape=pending.pop()
        if hasattr(shape,'geoms'):
            pending.extend(shape.geoms);continue
        if shape.is_empty:continue
        x0,y0,x1,y1=shape.bounds;halo=width_nm/2+1000
        hint_boxes.append((x0-halo,y0-halo,x1+halo,y1+halo))
    root_at=tuple(root.GetPosition());target_at=tuple(target.GetPosition())
    def distance_to_box(at,b):
        return max(b[0]-at[0],0,at[0]-b[2])**2+max(b[1]-at[1],0,at[1]-b[3])**2
    hint_boxes=sorted(set(hint_boxes),key=lambda b:(min(distance_to_box(root_at,b),
        distance_to_box(target_at,b)),b))[:64]
    binding=leaf._binding(board)
    counts=dict(edge_queries=0,barrel_queries=0,refused_contacts=0,lease_refusals=0)
    def permit_query():
        try:work.tick();return True
        except cut.Unknown as exc:
            if str(exc)!='copper_cut_deadline_exhausted':raise
            counts['lease_refusals']+=1;return False
    def planar(a,b,query_width,face):
        # This is the SAME physical pickup/root aperture used by the final
        # whole-path veto, now exposed to every native maze hop. Same-net
        # force material must not be invisible to search just because KiCad
        # electrical clearance rightly permits same-net contact.
        if not permit_query():return False
        counts['edge_queries']+=1
        if (type(query_width) is not int or not width_nm<=query_width<=width_nm+1
                or face not in blocked or tuple(a)==tuple(b)):
            return False
        body=LineString([tuple(a),tuple(b)]).buffer(query_width/2+1000,quad_segs=64)
        ok=not blocked[face].intersects(body)
        if not ok:counts['refused_contacts']+=1
        return ok
    def edge_clear(a,b,query_width):return planar(a,b,query_width,layer)
    def barrel(at,diameter_nm):
        if not permit_query():return False
        counts['barrel_queries']+=1
        if type(diameter_nm) is not int or not 0<diameter_nm<=2000000:return False
        body=Point(tuple(at)).buffer(diameter_nm/2+1000,quad_segs=64)
        ok=not any(shape.intersects(body) for shape in blocked.values())
        if not ok:counts['refused_contacts']+=1
        return ok
    def inward(ops):
        if opposite is None:return True
        # Receive actual native pad-boundary exits, not just the final point
        # lying on the inward half. This is the SAME independent directional
        # checker used by absolute saved-board evidence. No Source copper is
        # added and no isolation/current/Kelvin qualification follows.
        from cec_kelvin_departure import audit_pad_departures
        tracks=[]
        for op in ops:
            work.tick()
            if op[0]!='trk' or int(op[4])!=layer:return False
            track=pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I(*op[1]));track.SetEnd(pcbnew.VECTOR2I(*op[2]))
            track.SetWidth(op[3]);track.SetLayer(layer);track.SetNet(root.GetNet())
            tracks.append(track)
        proof=audit_pad_departures(target,opposite.GetPosition(),tracks,
            inner_min_mm=inner_min,target_pads=[root],connectivity_pads=[root])
        work.tick()
        return proof['ok'] is True
    def operations(ops):
        if not ops or len(ops)>32 or sum(op[0]=='via' for op in ops)>4:return False
        return all(planar(op[1],op[2],op[3],int(op[4])) if op[0]=='trk'
            else barrel(op[1],round(op[3]*1e6)) if op[0]=='via' else False for op in ops) and inward(ops)
    def clear(points):
        work.tick()
        if (not 2<=len(points)<=17 or list(points[0])!=list(root.GetPosition())
                or any(a==b or a[0]!=b[0] and a[1]!=b[1] and abs(a[0]-b[0])!=abs(a[1]-b[1])
                    for a,b in zip(points,points[1:]))):return False
        if not target.GetEffectiveShape(layer).Collide(pcbnew.VECTOR2I(*points[-1]),0):return False
        return (not blocked[layer].intersects(LineString(points).buffer(width_nm/2+1000,quad_segs=64))
            and inward([['trk',a,b,width_nm,layer] for a,b in zip(points,points[1:])]))
    return dict(clear=clear,edge_clear=edge_clear,search_counts=counts,
        planar=planar,barrel=barrel,operations=operations,counts=counts,
        root=root,target=target,layer=layer,opposite=opposite,
        centerline_contact_boxes=hint_boxes,
        source_input_component=dict(uuids=island,
            exact_literal_auxiliary_strap=strap is not None,
            aperture_only_at_original_root_land=True,
            source_copper_retirement_authority=False),
        unchanged=lambda:leaf._binding(board)==binding)


def menus(board, demand, *, width_nm, timeout_s=10., max_choices=16,max_length_nm=None,board_hint=None):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(max_choices) is not int or not 1<=max_choices<=48):
        raise ValueError('bounded_isolated_measurement_menu_required')
    max_length_nm=fr._checked_route_length_nm(max_length_nm)
    if board_hint is not None and(type(board_hint)is not str or not board_hint.strip()):
        raise ValueError('explicit_measurement_field_design_identity_required')
    deadline=time.monotonic()+timeout_s;guard=contact_guard(board,demand,width_nm=width_nm,deadline=deadline)
    root,target,layer=[guard[k] for k in ('root','target','layer')]
    from cec_field_search import PlanarSearchGuard
    saved_name=str(board.GetFileName()or'')
    # Unsaved native proposal boards have no project path to resolve. They
    # may still use conservative name/physical roles; never search the CWD
    # for an unrelated project's class authority. Saved receiving is due.
    resolver=(fr._project_netclass_resolver(saved_name,board=board)if saved_name else lambda _net:None)
    pruning=PlanarSearchGuard(board,demand['net'],netclass_resolver=resolver,board_hint=board_hint)
    field_checks=dict(queries=0,refusals=0,complete_pickup_tail_included=True,
        saved_refilled_whole_board_receiving_still_required=True)
    start=tuple(root.GetPosition());end=tuple(target.GetPosition())
    # All aperture points are in the actual named land. Long-axis offsets
    # expose its inward side without guessing which direction the bus takes.
    heading=target.GetOrientationDegrees()*math.pi/180
    size=target.GetSize();axis=heading if size.x>=size.y else heading+math.pi/2
    radius=max(size.x,size.y)/2-width_nm/2-2000
    ends=[end]
    for fraction in (.5,.75):
        for sign in (-1,1):
            ends.append((end[0]+round(sign*radius*fraction*math.cos(axis)),
                         end[1]+round(sign*radius*fraction*math.sin(axis))))
    ends=list(dict.fromkeys(ends));tails={at:[] for at in ends}
    foreign={};gap=max(200000,int(board.GetDesignSettings().m_MinClearance))
    tail_preflight=dict(queries=0,foreign_or_edge_refusals=0)
    if guard['opposite'] is not None:
        # Reuse the established textbook launch construction. A maze can
        # search up to its OUTSIDE knee; it may never optimize away the
        # perpendicular inward shunt take-off itself.
        peer=guard['opposite'].GetPosition()
        reach=math.hypot(size.x,size.y)/2e6
        x,y,ux,uy=fr._inner_edge_pt(target,peer,inset_mm=min(.12,reach*.25))
        if abs(ux)>1e-9 and abs(uy)>1e-9 and abs(abs(ux)-abs(uy))>1e-9:
            raise ValueError('canonical_direct_shunt_orientation_required')
        pickup=(round(x*1e6),round(y*1e6))
        if not target.GetEffectiveShape(layer).Collide(pcbnew.VECTOR2I(*pickup),0):
            raise ValueError('native_inner_shunt_pickup_unavailable')
        span=math.dist(end,tuple(peer))/1e6
        tails={}
        pickups=[pickup]
        # A shunt may legitimately serve several separately typed input
        # legs. A retained sibling take-off can occupy the centre channel;
        # that is not permission to rejoin it outside the cut or turn the
        # new lead diagonally across the inner edge. Reuse the same bounded
        # land-width offsets as the ordinary aperture portfolio, but move
        # them TRANSVERSELY and keep each launch strictly perpendicular.
        for fraction in (.5,.75):
            for sign in (-1,1):
                at=(pickup[0]+round(-uy*sign*radius*fraction),
                    pickup[1]+round(ux*sign*radius*fraction))
                if target.GetEffectiveShape(layer).Collide(pcbnew.VECTOR2I(*at),0):pickups.append(at)
        # Same bounded run preferences and inter-pad cap as the established
        # canonical tap family; these are proposals, not clearance waivers.
        for pickup in pickups:
            for preferred in (.9,.3,.45,.6,.75,1.2):
                run=min(preferred,max(.3,span*.45))
                knee=(pickup[0]+round(ux*run*1e6),pickup[1]+round(uy*run*1e6))
                if (fr._tap_launch_refusal([pcbnew.VECTOR2I(*pickup),pcbnew.VECTOR2I(*knee)],(ux,uy)) is None
                        and guard['planar'](knee,pickup,width_nm,layer)):
                    # The finishing tail is immutable during maze search.
                    # Fund only goals whose COMPLETE tail passes the SAME
                    # foreign/edge checks as final admission. Previously a
                    # blocked preferred run could consume every funded seat,
                    # starving shorter lawful runs at the same physical port.
                    # This is pruning, never clearance or contact authority.
                    tail_preflight['queries']+=1
                    if (not fr._edge_leg_clear(board,pcbnew.VECTOR2I(*knee),pcbnew.VECTOR2I(*pickup),width_nm/2+gap)
                            or not fr._tap_foreign_clear(board,pcbnew.VECTOR2I(*knee),pcbnew.VECTOR2I(*pickup),width_nm,
                                layer,gap,{root.GetNetCode()},foreign_cache=foreign)):
                        tail_preflight['foreign_or_edge_refusals']+=1
                        continue
                    tails[knee]=[pickup]
        ends=list(tails)
    paths=[]
    bounded_refusals=0;searches=[];craft_queries=0;craft_refusals=0
    def within_length(points):
        return max_length_nm is None or sum(math.dist(a,b)for a,b in zip(points,points[1:]))<=max_length_nm
    def craft_clear(points):
        nonlocal craft_queries,craft_refusals
        craft_queries+=1
        q=assess_path_craft(board,[['trk',list(a),list(b),width_nm,layer]
            for a,b in zip(points,points[1:])],net=demand['net'],deadline=deadline)
        ok=q.get('ok')is True and q.get('complete')is True and q.get('board_mutated')is False
        if not ok:craft_refusals+=1
        return ok
    def field_clear(points):
        if not _field_runs_clear(points,width_nm,layer,pruning):return False
        field_checks['queries']+=1
        proof=assess_path_field(board,[['trk',list(a),list(b),width_nm,layer]
            for a,b in zip(points,points[1:])],net=demand['net'],deadline=deadline,
            netclass_resolver=resolver,board_hint=board_hint)
        ok=proof.get('ok')is True and proof.get('complete')is True and proof.get('board_mutated')is False
        if not ok:field_checks['refusals']+=1
        return ok
    contact_unknown=[]
    def contact_test(predicate,*args):
        # A native copper-cut lease/geometry unknown is a refused offer,
        # never a clear path and never grounds for increasing this lease.
        # Keep the failure local to the finite menu rather than aborting an
        # entire multi-obligation transaction during one candidate test.
        import cec_kelvin_copper_cut as cut
        try:return predicate(*args)
        except cut.Unknown as exc:
            if len(contact_unknown)<8:contact_unknown.append(str(exc))
            return False
    def admit(points):
        nonlocal bounded_refusals
        if len(paths)>=max_choices:return False
        points=[tuple(p) for p in points];points=[p for i,p in enumerate(points) if not i or p!=points[i-1]]
        if not within_length(points):bounded_refusals+=1;return False
        if not contact_test(guard['clear'],points):return False
        if not all(fr._edge_leg_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width_nm/2+gap)
                and fr._tap_foreign_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width_nm,
                    layer,gap,{root.GetNetCode()},foreign_cache=foreign) for a,b in zip(points,points[1:])):return False
        if not field_clear(points)or not craft_clear(points):return False
        if points not in paths:paths.append(points)
        return True
    for at in ends:
        for points in [*fr._canonical_45_xy_paths(start,at),*fr._offset_manhattan_xy_paths(start,at)]:
            if time.monotonic()>=deadline or len(paths)>=max_choices:break
            admit([*points,*tails[at]])
    if not paths:
        # Only an actual, lineage-named two-land shunt supplies an inward
        # short-axis pickup. Long-axis offsets alone miss that real aperture
        # when the load trace occupies the middle of a short shunt land.
        anchors=[q for q in demand.get('source_topology',{}).values()
            if isinstance(q,dict) and q.get('anchor_ref')==target.GetParentFootprint().GetReference()
            and str(q.get('anchor_pad'))==target.GetNumber()]
        peers=[p for p in target.GetParentFootprint().Pads() if force._uid(p)!=force._uid(target)]
        inward=[]
        if guard['opposite'] is None and anchors and len(peers)==1 and peers[0].GetNetname()!=target.GetNetname():
            dx,dy=(int(v)-end[k] for k,v in enumerate(peers[0].GetPosition()))
            length=math.hypot(dx,dy)
            if length:
                for fraction in (.75,.5):
                    inset=max(0,min(size.x,size.y)/2-width_nm/2-2000)*fraction
                    point=(end[0]+round(dx/length*inset),end[1]+round(dy/length*inset))
                    if target.GetEffectiveShape(layer).Collide(pcbnew.VECTOR2I(*point),0):
                        inward.append(point)
        maze_ends=list(dict.fromkeys([*inward,*ends]))
        if guard['opposite'] is not None:
            # Do not split one finite lease thirty ways after adding sibling
            # pad ports. First fund one knee for EVERY distinct physical
            # pickup; use only spare seats for alternative runs. Canonical
            # paths above still examine the full deterministic portfolio.
            selected=[];seen_pickups=set()
            for at in maze_ends:
                pickup=tuple(tails[at][-1])
                if pickup not in seen_pickups:
                    selected.append(at);seen_pickups.add(pickup)
            for at in maze_ends:
                if len(selected)>=6:break
                if at not in selected:selected.append(at)
            maze_ends=selected[:6]
        def complete_points(candidate,at):
            return [tuple(candidate[0][0]),*[tuple(q[1]) for q in candidate],*tails.get(at,[])]
        # This is two finite SEARCH windows under one unchanged <=10 s
        # lease, not a physical no-path claim. Preserve the local tier and
        # reserve half the remaining time for a wider native surface detour.
        tiers=(6.,12.)
        for tier,margin in enumerate(tiers):
            if time.monotonic()>=deadline:break
            tier_deadline=time.monotonic()+(deadline-time.monotonic())/(len(tiers)-tier)
            for index,at in enumerate(maze_ends):
                if time.monotonic()>=tier_deadline or paths:break
                lease=time.monotonic()+(tier_deadline-time.monotonic())/(len(maze_ends)-index)
                diagnostics={}
                legs=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*start),pcbnew.VECTOR2I(*at),
                    width_nm,layer,gap,root.GetNetCode(),
                    lambda a,b,h:fr._edge_leg_clear(board,a,b,h+gap)
                        and contact_test(guard['edge_clear'],a,b,2*int(h)+1)
                        and pruning(a,b,2*int(h)+1,layer)is True,foreign_cache=foreign,
                    deadline_monotonic=lease,refine_maze=True,endpoint_detail_grid_mm=.2,
                    maze_margin_mm=margin,max_length_nm=max_length_nm,
                    refinement_grids_mm=(.2,.1)if max_length_nm is not None else (),
                    search_diagnostics=diagnostics,
                    centerline_obstacle_boxes=guard['centerline_contact_boxes'],
                    run_guard=(None if not pruning.active else lambda a,b,w:pruning(a,b,w,layer)),
                    path_validator=lambda candidate:within_length(complete_points(candidate,at))
                        and contact_test(guard['clear'],complete_points(candidate,at))
                        and field_clear(complete_points(candidate,at))
                        and craft_clear(complete_points(candidate,at)))
                searches.append(dict(target_nm=list(at),margin_mm=margin,diagnostics=diagnostics,
                    path_found=bool(legs)))
                if legs:admit(complete_points(legs,at))
            if paths:break
    if not guard['unchanged']():raise ValueError('isolated_measurement_menu_changed_native_source')
    return dict(ops=[[['trk',list(a),list(b),width_nm,layer] for a,b in zip(points,points[1:])]
        for points in paths],source_unchanged=True,no_path_proof=False,retirement_authority=False,
        current_authority=False,release_authority=False,exact_pickup_land_only=True,
        source_input_component=guard['source_input_component'],
         same_net_force_search=dict(guard['search_counts']),bounded_native_searches=searches,
         same_net_contact_unknown_refusals=contact_unknown,
         complete_path_craft=dict(queries=craft_queries,refusals=craft_refusals,
            fixed_pickup_tail_included=True,retained_copper_included=True),
         complete_path_field=field_checks,field_search_pruning=pruning.report(),
         pickup_tail_preflight=tail_preflight,
         proposal_length_bound_nm=max_length_nm,length_bound_refusals=bounded_refusals)
