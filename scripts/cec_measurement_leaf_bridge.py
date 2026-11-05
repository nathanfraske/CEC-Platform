"""Bounded layer access for source-owned thin measurement leaves.

Ordinary same-net clearance is insufficient for Kelvin/sense copper. Every
track AND every barrel must avoid acquiring other same-net force material;
only the original named pickup aperture and exact typed input are contacts.
This proposes restoration, not force current or full Kelvin qualification.
"""
import math
import time

import pcbnew
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_measurement_leaf as leaf


def compile_contact_guard(board, proposal, *, deadline):
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union
    from shapely.prepared import prep
    import cec_kelvin_copper_cut as cut
    import cec_device_power_roles as roles
    if proposal.get('scope') != 'source_typed_thin_measurement_leaf':
        raise ValueError('source_typed_measurement_leaf_required')
    if set(proposal['track_uuids']) & {force._uid(t) for t in board.GetTracks()}:
        raise ValueError('source_measurement_leaf_not_privately_retired')
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()
        if force._uid(p)==proposal['pad_uuid']]
    if len(pads)!=1:
        raise ValueError('exact_measurement_land_missing')
    pad=pads[0];model=roles.footprint_contract(pad.GetParentFootprint())
    if (not model or model['pins'].get(pad.GetNumber())!='measurement'
            or list(pad.GetPosition())!=proposal['points_nm'][0]
            or str(pad.GetNetname())!=proposal['net']):
        raise ValueError('actual_manufacturer_measurement_land_binding_required')
    work=cut._Work(deadline);kernel=leaf._source_boundary_kernel(proposal)
    layers=tuple(map(int,board.GetEnabledLayers().CuStack()));blocked={l:[] for l in layers}
    material=[*(p for f in board.GetFootprints() for p in f.Pads()),
        *board.GetTracks(),*[z for z in board.Zones() if not z.GetIsRuleArea()]]
    seen=set()
    for item in material:
        work.tick()
        if item.GetNetCode()!=pad.GetNetCode():continue
        uid=force._uid(item)
        for layer in layers:
            if not item.IsOnLayer(layer):continue
            if item.GetClass()=='ZONE':
                if not item.IsFilled():raise ValueError('same_net_native_zone_fill_unknown')
                shape=cut._poly(item.GetFilledPolysList(layer),work)
            else:
                shape=cut._shape(item,layer,True,work)
            allowed=(shape.buffer(proposal['width_nm']/2+1002) if uid==proposal['pad_uuid'] else
                shape.buffer(proposal['width_nm']/2+1002)
                if uid in proposal['boundary_uuids'] and item.GetClass()=='PAD' else
                kernel if uid in proposal['boundary_uuids'] else None)
            if uid in proposal['boundary_uuids']:seen.add(uid)
            blocked[layer].append(shape if allowed is None else shape.difference(allowed))
    if seen!=set(proposal['boundary_uuids']):
        raise ValueError('exact_retained_measurement_pickup_missing')
    forbidden={layer:prep(unary_union(shapes)) for layer,shapes in blocked.items()}
    binding=leaf._binding(board);counts=dict(track_queries=0,barrel_queries=0,refused_contacts=0,
        lease_refusals=0)
    def permit_query():
        try:work.tick();return True
        except cut.Unknown as exc:
            if str(exc)!='copper_cut_deadline_exhausted':raise
            counts['lease_refusals']+=1;return False
    def planar(a,b,width,layer):
        if not permit_query():return False
        counts['track_queries']+=1
        # The bridge's half-width guard rounds outward by one nanometre.
        # This is conservative query geometry, NOT a emitted-width waiver.
        if layer not in forbidden or not proposal['width_nm'] <= width <= proposal['width_nm']+1:
            return False
        body=LineString([tuple(a),tuple(b)]).buffer(width/2+1000,quad_segs=64)
        ok=not forbidden[layer].intersects(body)
        if not ok:counts['refused_contacts']+=1
        return ok
    def barrel(at,diameter_nm):
        if not permit_query():return False
        counts['barrel_queries']+=1
        body=Point(tuple(at)).buffer(diameter_nm/2+1000,quad_segs=64)
        ok=not any(shape.intersects(body) for shape in forbidden.values())
        if not ok:counts['refused_contacts']+=1
        return ok
    def operations(ops):
        if not ops or len(ops)>32 or sum(op[0]=='via' for op in ops)>4:return False
        return all(planar(op[1],op[2],op[3],int(op[4])) if op[0]=='trk'
            else barrel(op[1],round(op[3]*1e6)) if op[0]=='via' else False for op in ops)
    return dict(planar=planar,barrel=barrel,operations=operations,counts=counts,
        unchanged=lambda:leaf._binding(board)==binding,
        no_path_proof=False,release_authority=False)


def search(board, proposal, *, timeout_s=2., include_power_layer=False):
    """Real native bridge and optional maze with unchanged contact/width rules."""
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(include_power_layer) is not bool):
        raise ValueError('bounded_measurement_bridge_required')
    import cec_measurement_route_policy as policy
    policy.require_layer_bridge(board,proposal['pad_uuid'])
    started=time.monotonic();deadline=started+timeout_s
    guard=compile_contact_guard(board,proposal,deadline=deadline)
    return _search(board,proposal,guard,started=started,deadline=deadline,
        include_power_layer=include_power_layer)


def search_isolated(board,demand,*,width_nm,timeout_s=2.,include_power_layer=False):
    """Use the same native bridge producer without inventing an owned leaf.

    Immutable manufacturer/schematic lineage names the exact input and
    pickup. No existing source channel, retirement or current credit exists
    for an isolated input; its own full-stack contact guard remains required.
    """
    import cec_measurement_terminal_route as terminal
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(include_power_layer) is not bool):
        raise ValueError('bounded_isolated_measurement_bridge_required')
    import cec_measurement_route_policy as policy
    policy.require_layer_bridge(board,demand['pad_uuid'])
    started=time.monotonic();deadline=started+timeout_s
    guard=terminal.contact_guard(board,demand,width_nm=width_nm,deadline=deadline)
    points=[list(guard[key].GetPosition()) for key in ('root','target')]
    context=dict(points_nm=points,net=demand['net'],width_nm=width_nm,layer=guard['layer'],
        source_length_mm=0.)  # Search uses actual span, never invented source copper.
    result=_search(board,context,guard,started=started,deadline=deadline,
        include_power_layer=include_power_layer)
    result.update(source_owned_channel=False,retirement_authority=False,
        exact_pickup_land_only=True,current_authority=False)
    return result


def _search(board,proposal,guard,*,started,deadline,include_power_layer):
    """Shared bounded geometry search; caller has compiled its typed guard."""
    plane_ids={board.GetLayerID(n) for n in fr.plane_layers(board)}
    layers=[board.GetLayerID(n) for n in fab.routing_layers(board,include_power=include_power_layer)
        if board.GetLayerID(n) not in plane_ids]
    bridge=[l for l in layers if l!=proposal['layer']]
    if not bridge:raise ValueError('authorized_nonplane_measurement_bridge_layer_missing')
    a,b=[tuple(p) for p in (proposal['points_nm'][0],proposal['points_nm'][-1])]
    gap=max(int(board.GetDesignSettings().m_MinClearance),200000)
    width=proposal['width_nm'];layer=int(proposal['layer'])
    code=board.GetNetcodeFromNetname(proposal['net']);foreign={}
    limit=round((max(proposal['source_length_mm'],math.dist(a,b)/1e6)+16)*1e6)
    detail={'source_channel_trials':[]};ops=None
    # A fixed pickup can be buried under power copper on other layers. Its
    # old, exclusively owned surface channel is an actual source-derived
    # escape, not a fictitious existing island or a whole-net contact waiver.
    # Re-propose the guarded suffix to each bounded old internal vertex, then
    # bridge there. The suffix remains NEW copper in the complete operation.
    ports=[]
    points=[tuple(p) for p in proposal['points_nm']]
    for index in range(1,len(points)-1):
        suffix=[('trk',s,t,width,layer) for s,t in zip(points[index:],points[index+1:])]
        if (suffix and len(suffix)<=16 and guard['operations'](suffix)
                and all(fr._edge_leg_clear(board,pcbnew.VECTOR2I(*s),pcbnew.VECTOR2I(*t),width/2+gap)
                    and fr._tap_foreign_clear(board,pcbnew.VECTOR2I(*s),pcbnew.VECTOR2I(*t),
                        width,layer,gap,{code},foreign_cache=foreign)
                    for _,s,t,_,_ in suffix)):
            ports.append((points[index],suffix))
    ports=ports[:8]+[(b,[])]
    # Keep a bounded share for native portals. A difficult source vertex must
    # not consume the entire lease before the other access strategies run.
    now=time.monotonic();channel_deadline=now+max(0,deadline-now)/(8 if len(points)==2 else 3)
    for index,(at,suffix) in enumerate(ports):
        now=time.monotonic()
        if now>=channel_deadline:break
        trial={};suffix_length=sum(math.dist(op[1],op[2]) for op in suffix)
        lease=now+(channel_deadline-now)/(len(ports)-index)
        def joined(candidate):
            all_ops=[*candidate,*suffix]
            return (sum(math.dist(op[1],op[2]) for op in all_ops if op[0]=='trk')<=limit
                and guard['operations'](all_ops))
        found=fr._lastmile_bridge(board,a,[layer],at,[layer],width,code,bridge,gap,
            leg_ok=lambda s,t,h:fr._edge_leg_clear(board,s,t,h+gap),
            seat_limit=8,allow_maze=False,foreign_cache=foreign,deadline_monotonic=lease,
            refine_stubs=True,planar_guard=guard['planar'],ops_ok=joined,
            multilayer_lays=layers,max_length_nm=max(0,round(limit-suffix_length)),diagnostics=trial)
        detail['source_channel_trials'].append(dict(anchor_nm=list(at),
            replayed_source_segments=len(suffix),diagnostics=trial,found=bool(found)))
        if found and joined(found):
            ops=[*found,*suffix];break
    # A radial launch ladder may miss a free pocket behind a large trunk.
    # Derive ordinary seats from native all-layer copper, then prove the
    # surface stub separately. Passing all-layer endpoint access below means
    # the NEW barrel in suffix_ops will be emitted, never a ghost native via.
    if not ops and time.monotonic()<deadline:
        import cec_native_via_frontier as frontier
        try:
            # The retained pickup may sit beneath a wide trunk. Its owned
            # source channel can leave that shadow at an internal vertex;
            # looking only around the final pickup wastes all portal seats
            # on pockets that are inaccessible from its surface channel.
            # This finite union proposes geometry, not an existing contact.
            seats=None;native_sites=[];seen=set()
            now=time.monotonic();frontier_deadline=now+max(0,deadline-now)/4
            for index,(center,_) in enumerate(ports):
                now=time.monotonic()
                if now>=frontier_deadline:break
                lease=now+(frontier_deadline-now)/(len(ports)-index)
                try:
                    part=frontier.sites(board,code,list(center),clearance_nm=gap,
                        max_sites=8,deadline=lease,barrel_guard=guard['barrel'],diverse=True)
                except (ValueError,RuntimeError) as exc:
                    detail.setdefault('native_frontier_errors',[]).append(
                        dict(source_anchor_nm=list(center),error=str(exc)))
                    continue
                if seats is None:seats=part
                for site in part['sites_nm']:
                    key=tuple(site)
                    if key not in seen:seen.add(key);native_sites.append(site)
            if seats is not None:seats=dict(seats,sites_nm=native_sites[:48])
        except Exception as exc:
            # This remains an explicit incomplete planning outcome, not
            # permission to omit contact/factory checks or claim no path.
            if not isinstance(exc,(ValueError,RuntimeError)):raise
            seats=None;detail['native_frontier_error']=str(exc)
        if seats:
            detail['native_frontier_sites']=len(seats['sites_nm'])
            detail['native_frontier_trials']=[]
            # Prove short source-channel escapes before funding deep bridges.
            # Rank their exact emitted suffixes, retaining one shortest guarded
            # suffix per physical portal. This is a finite proposal portfolio,
            # not a new pickup aperture or an inferred existing barrel.
            jobs=[(tuple(site),anchor,suffix) for site in seats['sites_nm']
                for anchor,suffix in ports]
            now=time.monotonic();stub_deadline=now+max(0,deadline-now)/3
            ready={};detail['native_frontier_stub_trials']=[]
            for index,(at,anchor,suffix) in enumerate(jobs):
                now=time.monotonic()
                if now>=stub_deadline:break
                remaining=limit-sum(math.dist(op[1],op[2]) for op in suffix)-math.dist(a,at)
                if remaining<=0:continue
                lease=min(now+.15,now+(stub_deadline-now)/(len(jobs)-index))
                stub=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*anchor),
                    pcbnew.VECTOR2I(*at),width,layer,gap,code,
                    lambda s,t,h:fr._edge_leg_clear(board,s,t,h+gap)
                        and guard['planar'](s,t,2*int(h)+1,layer),
                    allow_maze=True,maze_margin_mm=2.5,foreign_cache=foreign,
                    deadline_monotonic=lease,max_length_nm=round(remaining),refine_maze=True)
                detail['native_frontier_stub_trials'].append(dict(site_nm=list(at),
                    source_anchor_nm=list(anchor),found=bool(stub)))
                if not stub:continue
                suffix_ops=[('trk',s,t,w,layer) for s,t,w in stub]
                suffix_ops.extend([('via',at,seats['drill_mm'],seats['diameter_mm']),*suffix])
                if not guard['operations'](suffix_ops):continue
                length=sum(math.dist(op[1],op[2]) for op in suffix_ops if op[0]=='trk')
                if length+math.dist(a,at)>limit:continue
                key=(length+math.dist(a,at),length,tuple(anchor))
                if at not in ready or key<ready[at][0]:
                    ready[at]=(key,anchor,suffix_ops,length)
            ranked=sorted(ready.items(),key=lambda item:(item[1][0],item[0]))
            detail['native_frontier_ready_portals']=len(ranked)
            for index,(at,(_,anchor,suffix_ops,length)) in enumerate(ranked):
                now=time.monotonic()
                if now>=deadline:break
                lease=now+(deadline-now)/(len(ranked)-index)
                def complete(candidate):
                    joined=[*candidate,*suffix_ops]
                    return (sum(math.dist(op[1],op[2]) for op in joined if op[0]=='trk')<=limit
                        and guard['operations'](joined))
                trial={}
                found=fr._lastmile_bridge(board,a,[layer],at,list(map(int,board.GetEnabledLayers().CuStack())),
                    width,code,bridge,gap,seat_limit=8,allow_maze=True,foreign_cache=foreign,
                    deadline_monotonic=lease,refine_stubs=True,planar_guard=guard['planar'],
                    ops_ok=complete,multilayer_lays=layers,diagnostics=trial,
                    # The cheap source-channel tier already tried each
                    # authorized layer's canonical access. A native frontier
                    # can sit behind a trunk outside a tiny endpoint-margin
                    # window. Fund one explicit full-stack native-outline
                    # fallback before repeating deep single-layer mazes.
                    # Same lease, length, contact and factory guards apply.
                    _multilayer_only=True,_multilayer_pair_limit=2,
                    middle_native_board_envelope=True,middle_grid_mm=.4,
                    leg_ok=lambda s,t,h:fr._edge_leg_clear(board,s,t,h+gap),
                    max_length_nm=round(limit-length))
                detail['native_frontier_trials'].append(dict(site_nm=list(at),
                    source_anchor_nm=list(anchor),found=bool(found),diagnostics=trial,
                    lease_s=max(0,lease-now)))
                if found and complete(found):ops=[*found,*suffix_ops];break
    if ops and not guard['operations'](ops):ops=None
    if not guard['unchanged']():raise ValueError('measurement_bridge_changed_native_source')
    return dict(ops=ops,diagnostics=detail,contact_guard=guard['counts'],
        elapsed_s=time.monotonic()-started,no_path_proof=False,
        routing_admitted=False,kelvin_qualified=False,release_authority=False)
