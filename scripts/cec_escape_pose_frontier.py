"""Bounded complete-cell pose proposals with real all-layer return access.

Courtyards alone are insufficient: a surface land can fit over a foreign
inner/back bus while its through-via cannot. These are upstream proposals,
not replacement, power, field, Kelvin, or fabrication release authority.
"""
import math
from pathlib import Path
import time

import pcbnew
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_constraints as constraints
import cec_decoupler_cell as cell
import cec_device_power_roles as roles
import cec_fab_profile as fab
import cec_force_current as force
from cec_native_items import discard_items


def _source_local_event_contract(board,root_pad_uuids,*,board_hint,deadline):
    """Fresh saved-source low-power/local-rule authority, proposal only."""
    import cec_ground_local_mesh_entry as local
    if (type(board_hint)is not str or not board_hint or type(root_pad_uuids)not in(list,tuple)
            or not 1<=len(root_pad_uuids)<=8 or any(type(u)is not str or not u for u in root_pad_uuids)
            or len(set(root_pad_uuids))!=len(root_pad_uuids)):
        raise ValueError('explicit_source_local_ground_event_context_required')
    source=Path(board.GetFileName()).resolve(strict=True)
    if source.suffix!='.kicad_pcb':raise ValueError('named_saved_ground_event_source_required')
    before=row._source_binding(board);family=force._family(source,board_hint);epoch=force._code_identity()
    if row._source_binding(pcbnew.LoadBoard(str(source)))!=before:
        raise ValueError('ground_event_board_must_equal_named_saved_source')
    context=local.join._context(board,board_hint,deadline)
    roots=[];geometries=set()
    for uid in root_pad_uuids:
        if time.monotonic()>=deadline:raise ValueError('source_local_ground_event_deadline')
        pad=local._owner(context,uid)
        native,group,geometry=local._source_geometry(board,pad)
        geometries.add(tuple(geometry));roots.append(dict(pad_uuid=uid,source_group_uuid=group,
            ordinary_board_limits_nm=native['ordinary_board_limits_nm'],
            all_local_dimensions_at_or_above_ordinary_setup=True))
    if len(geometries)!=1:raise ValueError('one_exact_source_local_ground_event_geometry_required')
    if (row._source_binding(board)!=before or force._family(source,board_hint)!=family
            or force._code_identity()!=epoch or time.monotonic()>=deadline):
        raise ValueError('source_local_ground_event_epoch_or_deadline_changed')
    geometry=next(iter(geometries))
    return dict(scope='source_typed_local_ground_mesh_entry_event_proposal',
        source=str(source),source_sha256=force._hash(source),source_family=family,
        source_native_binding=before,code_identity=epoch,roots=roots,
        diameter_nm=geometry[0],drill_nm=geometry[1],maximum_ground_reach_mm=1.5,
        final_source_local_mesh_receiving_still_required=True,release_authority=False)


def rigid_poses(board, refs, anchor_ref, delta_mm, rotation_deg):
    """Quarter-turn the entire declared cell, preserving its relationships."""
    refs = tuple(refs)
    if (not refs or len(refs) > 8 or len(set(refs)) != len(refs)
            or anchor_ref not in refs or len(delta_mm) != 2
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in delta_mm)
            or math.hypot(*delta_mm) > 16
            or type(rotation_deg) not in (int, float) or rotation_deg not in (0, 90, 180, 270)):
        raise ValueError('bounded_complete_cell_rigid_pose_required')
    fps = {r: board.FindFootprintByReference(r) for r in refs}
    if any(f is None for f in fps.values()):
        raise ValueError('complete_cell_pose_member_missing')
    origin = fps[anchor_ref].GetPosition()
    # KiCad's positive orientation is clockwise in board coordinates.
    theta = math.radians(-rotation_deg); c, s = math.cos(theta), math.sin(theta)
    poses = {}
    for ref, fp in fps.items():
        p = fp.GetPosition(); x, y = (p.x-origin.x)/1e6, (p.y-origin.y)/1e6
        poses[ref] = [round(origin.x/1e6+delta_mm[0]+c*x-s*y, 6),
            round(origin.y/1e6+delta_mm[1]+s*x+c*y, 6),
            (fp.GetOrientationDegrees()+rotation_deg) % 360]
    return poses


def ground_translation_events(board, owner_ref, *, selected_refs, retired_uuids,
                              rotation_deg=0, radius_mm=16., max_sites=32, timeout_s=10.,
                              shared_entry_proposals=False, surface_proposals=False,
                              allow_native_ground_refill=False,
                              measurement_portal_proposals=False,
                              source_local_ground=False,board_hint=None):
    """Project REAL all-layer copper into the owner's via-access domain.

    The default requires possible centre barrels at every typed ground land.
    Explicit shared-entry proposal mode instead projects manufacturer ground
    roots and the uniquely assigned bypass root, including the existing .8 mm
    immediate-dogbone reach. References can then use the already-supported
    directed package/bypass link. This only broadens upstream pose proposals:
    every final land, bypass, link, barrel and source obligation still needs
    independent live ground_screen and complete-cell receiving.
    Explicit surface mode intersects the actual owner-land free domain BEFORE
    ranking/truncation. It only accepts physically retired private material;
    a list of worker-provided copper UUIDs cannot waive the surface obstacles.
    Optional typed measurement portal domains reserve possible local layer
    access away from every retained non-GND conductor, including SAME-net
    force material. They cannot confer a new Kelvin pickup/contact aperture.
    Final live qualified-return, courtyard, DRC and field checks remain due.
    """
    from shapely import affinity
    from shapely.geometry import Point, box
    from shapely.ops import nearest_points, unary_union
    import cec_kelvin_copper_cut as cut
    if (type(radius_mm) not in (int,float) or not math.isfinite(radius_mm)
            or not 0 < radius_mm <= 16 or rotation_deg not in (0,90,180,270)
            or type(max_sites) is not int or not 1 <= max_sites <= 64
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(shared_entry_proposals) is not bool
            or type(surface_proposals) is not bool
            or type(allow_native_ground_refill) is not bool
            or type(measurement_portal_proposals) is not bool or type(source_local_ground)is not bool
            or source_local_ground and (not shared_entry_proposals or type(board_hint)is not str or not board_hint)):
        raise ValueError('bounded_native_ground_translation_events_required')
    refs=set(selected_refs);retired=set(retired_uuids)
    fp=board.FindFootprintByReference(owner_ref);model=roles.footprint_contract(fp) if fp else None
    tracks={force._uid(t):t for t in board.GetTracks()}
    if (not model or owner_ref not in refs or not refs
            or len(refs)>8 or not retired <= tracks.keys()):
        raise ValueError('typed_ground_pose_and_exact_retained_scope_required')
    if surface_proposals and retired:
        raise ValueError('private_source_cut_native_surface_required')
    if measurement_portal_proposals and not surface_proposals:
        raise ValueError('measurement_portals_require_joint_private_surface_scope')
    binding=row._source_binding(board);started=time.monotonic();deadline=started+timeout_s
    work=cut._Work(deadline);offsets=[];root_offsets=[];root_witnesses=[];lands=[]
    measurement_offsets=[];measurement_witnesses=[]
    old_angle=fp.GetOrientationDegrees()
    origin=tuple(fp.GetPosition());owner_court=None
    try:
        fp.SetOrientationDegrees(old_angle+rotation_deg)
        native_court=fp.GetCourtyard(pcbnew.B_Cu if fp.IsFlipped() else pcbnew.F_Cu)
        if native_court.OutlineCount():
            b=native_court.BBox();owner_court=(b.GetLeft(),b.GetTop(),b.GetRight(),b.GetBottom())
        for p in fp.Pads():
            if surface_proposals:
                layers=tuple(p.GetLayerSet().CuStack())
                if p.HasHole() or len(layers)!=1:
                    raise ValueError('single_face_surface_lands_required')
                shape=affinity.scale(cut._shape(p,int(layers[0]),True,work),
                    xfact=1e-6,yfact=1e-6,origin=(0,0))
                lands.append((p,int(layers[0]),shape.bounds))
            if measurement_portal_proposals and model['pins'].get(p.GetNumber())=='measurement':
                if p.GetNetCode()<=0 or p.GetNetname()=='GND':
                    raise ValueError('populated_typed_measurement_net_required')
                measurement_offsets.append(((p.GetPosition().x-origin[0])/1e6,
                    (p.GetPosition().y-origin[1])/1e6))
                measurement_witnesses.append(dict(pad_uuid=force._uid(p),net=p.GetNetname()))
            if (p.GetNetname()=='GND' and model['pins'].get(p.GetNumber())
                    in ('ground','reference','power_return')):
                offsets.append(((p.GetPosition().x-origin[0])/1e6,
                    (p.GetPosition().y-origin[1])/1e6))
                if model['pins'].get(p.GetNumber()) in ('ground','power_return'):
                    root_offsets.append(offsets[-1])
                    root_witnesses.append(dict(kind='manufacturer_ground',pad_uuid=force._uid(p)))
    finally:
        fp.SetOrientationDegrees(old_angle)
    profile_name=fab.board_profile_name(board)
    profile=fab.get_profile(profile_name) if profile_name else None
    geometry=fab.preferred_pofv_geometry(profile) if profile else None
    if not offsets or (geometry is None and not source_local_ground) or owner_court is None:
        raise ValueError('declared_factory_ground_portal_geometry_required')
    if not source_local_ground:
        diameter,drill=geometry
        if not fab.pofv_dimensions(profile,diameter,drill)[0]:
            raise ValueError('declared_factory_ground_portal_dimensions_refused')
    if shared_entry_proposals:
        if (not root_offsets or any(role in ('power_output','switch','feedback')
                for role in model['pins'].values())):
            raise ValueError('typed_low_power_shared_ground_roots_required')
        assigned=constraints._device_bypass_assignment(board,project_max_mm=3.5)
        candidates=[q for q in assigned['assigned'].values()
            if q['requirement']['ref']==owner_ref and q['cap_ref'] in refs]
        # A producer cannot turn arbitrary same-net neighbouring copper into
        # a root. This pose tier only understands one source-selected bypass.
        caps={q['cap_ref'] for q in candidates}
        if len(caps)!=1:
            raise ValueError('unique_source_selected_shared_ground_bypass_required')
        selected=next(q for q in candidates if q['cap_ref'] in caps)
        cap=board.FindFootprintByReference(selected['cap_ref'])
        if (cap is None or cap.IsFlipped()!=fp.IsFlipped()
                or len(list(cap.Pads()))!=2
                or {p.GetNetname() for p in cap.Pads()}!={selected['requirement']['rail'],'GND'}
                or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in cap.Pads())):
            raise ValueError('source_selected_surface_ground_bypass_required')
        land=next(p for p in cap.Pads() if p.GetNetname()=='GND')
        x,y=(land.GetPosition().x-origin[0])/1e6,(land.GetPosition().y-origin[1])/1e6
        theta=math.radians(-rotation_deg);c,s=math.cos(theta),math.sin(theta)
        root_offsets.append((c*x-s*y,s*x+c*y))
        root_witnesses.append(dict(kind='source_selected_bypass',pad_uuid=force._uid(land),
            cap_ref=cap.GetReference(),owner_ref=owner_ref,
            supply_pin=selected['requirement']['pin']))
    reach=.8;local_contract=None
    if source_local_ground:
        local_contract=_source_local_event_contract(board,[r['pad_uuid']for r in root_witnesses],
            board_hint=board_hint,deadline=deadline)
        diameter,drill=[local_contract[k]/1e6 for k in ('diameter_nm','drill_nm')]
        reach=local_contract['maximum_ground_reach_mm']
        import cec_fr as fr
        source_local_clearance=fr._foreign_clearance_resolver(board)
    copper=[];holes=[];seen=set();native_shape_cache={}
    query_offsets=[*(root_offsets if shared_entry_proposals else offsets),*measurement_offsets]
    halo=radius_mm+max(reach if shared_entry_proposals else 0.,.8 if measurement_portal_proposals else 0.)
    query_box=(origin[0]/1e6+min(x for x,y in query_offsets)-halo,
        origin[1]/1e6+min(y for x,y in query_offsets)-halo,
        origin[0]/1e6+max(x for x,y in query_offsets)+halo,
        origin[1]/1e6+max(y for x,y in query_offsets)+halo)
    objects=[*(p for f in board.GetFootprints() for p in f.Pads()),
        *board.GetTracks(),*[z for z in board.Zones() if not z.GetIsRuleArea()]]
    for item in objects:
        work.tick()
        uid=force._uid(item)
        if uid in retired or (item.GetClass()=='PAD'
                and item.GetParentFootprint().GetReference() in refs):
            continue
        if item.GetClass()=='PCB_VIA' or (item.GetClass()=='PAD' and item.HasHole()):
            d=(item.GetDrillValue() if item.GetClass()=='PCB_VIA'
               else max(item.GetDrillSize().x,item.GetDrillSize().y))/1e6
            h=(d+drill)/2+board.GetDesignSettings().m_HoleToHoleMin/1e6+1e-3
            x,y=item.GetPosition().x/1e6,item.GetPosition().y/1e6
            if not (x+h<query_box[0] or y+h<query_box[1]
                    or x-h>query_box[2] or y-h>query_box[3]):
                holes.append(Point(x,y).buffer(h))
        if item.GetNetname()=='GND':
            continue
        gap_nm=max(200000,int(board.GetDesignSettings().m_MinClearance),
            int(cell._netclass(board,str(item.GetNetname()))['clearance']))
        if source_local_ground:
            gap_nm=max(gap_nm,int(cell._netclass(board,'GND')['clearance']),
                *(int(source_local_clearance(item,layer))for layer in
                    board.GetEnabledLayers().CuStack()if item.IsOnLayer(layer)))
        gap=gap_nm/1e6
        bb=item.GetBoundingBox();h=diameter/2+gap+1e-3
        if (bb.GetRight()/1e6+h<query_box[0] or bb.GetBottom()/1e6+h<query_box[1]
                or bb.GetLeft()/1e6-h>query_box[2] or bb.GetTop()/1e6-h>query_box[3]):
            continue
        for layer in board.GetEnabledLayers().CuStack():
            if not item.IsOnLayer(layer):
                continue
            key=(uid,int(layer))
            if key in seen:
                continue
            seen.add(key)
            if item.GetClass()=='ZONE':
                if not item.IsFilled():
                    raise ValueError('ground_pose_foreign_zone_fill_unknown')
                shape=cut._poly(item.GetFilledPolysList(layer),work)
            else:
                shape=cut._shape(item,layer,True,work)
            native_shape_cache[(uid,int(layer),'filled')]=shape
            copper.append(affinity.scale(shape,xfact=1e-6,yfact=1e-6,origin=(0,0)).buffer(
                diameter/2+gap+1e-3))
    occupied=unary_union([*copper,*holes])
    # Work in translation coordinates, keeping the source centre explicit.
    domain=Point(0,0).buffer(radius_mm,quad_segs=32)
    if shared_entry_proposals:
        # Union, not intersection: one qualified root can own short directed
        # links. The Minkowski reach is only an event-generating upper bound;
        # it is never a proof that an emitted dogbone clears native copper.
        free=unary_union([domain.difference(affinity.translate(occupied,
            xoff=-origin[0]/1e6-dx,yoff=-origin[1]/1e6-dy)).buffer(reach)
            for dx,dy in root_offsets]).intersection(domain)
    else:
        forbidden=unary_union([affinity.translate(occupied,
            xoff=-origin[0]/1e6-dx,yoff=-origin[1]/1e6-dy) for dx,dy in offsets])
        free=domain.difference(forbidden)
    if measurement_portal_proposals:
        if not measurement_offsets:raise ValueError('typed_measurement_portal_roots_required')
        for dx,dy in measurement_offsets:
            portal=domain.difference(affinity.translate(occupied,
                xoff=-origin[0]/1e6-dx,yoff=-origin[1]/1e6-dy)).buffer(.8).intersection(domain)
            free=free.intersection(portal)
    # Combine assembly access before ranking sites. Otherwise hundreds of
    # almost-identical capsule vertices adjacent to one *occupied* package
    # starve the finite portfolio and never reach the genuinely free regions.
    # Bounding boxes are conservative proposal geometry only; the live
    # courtyard screen still consumes exact polygons at the actual seat.
    court_forbidden=[];a0,b0,a1,b1=owner_court
    for peer in board.GetFootprints():
        work.tick()
        if peer.GetReference() in refs or peer.IsFlipped()!=fp.IsFlipped():continue
        native=peer.GetCourtyard(pcbnew.B_Cu if peer.IsFlipped() else pcbnew.F_Cu)
        if not native.OutlineCount():continue
        b=native.BBox()
        court_forbidden.append(box((b.GetLeft()-a1)/1e6-.002,
            (b.GetTop()-b1)/1e6-.002,(b.GetRight()-a0)/1e6+.002,
            (b.GetBottom()-b0)/1e6+.002))
    free=free.difference(unary_union(court_forbidden))
    edges=board.GetBoardEdgesBoundingBox()
    if edges.GetWidth()>0 and edges.GetHeight()>0:
        free=free.intersection(box((edges.GetLeft()-a0)/1e6,
            (edges.GetTop()-b0)/1e6,(edges.GetRight()-a1)/1e6,
            (edges.GetBottom()-b1)/1e6))
    surface_count=0;refill=[]
    if surface_proposals and not free.is_empty:
        dx0,dy0,dx1,dy1=free.bounds
        import cec_fr as fr
        local=fr._foreign_clearance_resolver(board)
        pad_gap=max(int(board.GetDesignSettings().m_MinClearance),
            *(int(local(p,l)) for p,l,b in lands))/1e6+.000002
        surface_region=(min(b[0] for p,l,b in lands)+dx0-pad_gap,
            min(b[1] for p,l,b in lands)+dy0-pad_gap,
            max(b[2] for p,l,b in lands)+dx1+pad_gap,
            max(b[3] for p,l,b in lands)+dy1+pad_gap)
        obstacles,refill,local=_surface_obstacles(board,refs,{l for p,l,b in lands},
            work=work,allow_native_ground_refill=allow_native_ground_refill,
            native_shape_cache=native_shape_cache,region_mm=surface_region)
        fences,surface_count=_surface_translation_fences(board,lands,obstacles,local,free,work)
        free=free.difference(unary_union(fences))
    polys=[free] if free.geom_type=='Polygon' else list(getattr(free,'geoms',()))
    sites=set()
    for poly in polys:
        work.tick()
        if poly.geom_type!='Polygon' or poly.is_empty:
            continue
        inner=poly.buffer(-.002)
        pieces=[inner] if inner.geom_type=='Polygon' else list(getattr(inner,'geoms',()))
        for piece in pieces:
            if piece.geom_type!='Polygon' or piece.is_empty:continue
            point=piece.representative_point();sites.add((point.x,point.y))
            if surface_proposals:
                point=nearest_points(Point(0,0),piece)[1];sites.add((point.x,point.y))
            sites.update(tuple(p) for p in piece.exterior.coords[:-1])
    ranked=[]
    for point in sorted(sites,key=lambda p:(math.hypot(*p),p)):
        site=tuple(float(v) for v in point)
        if not any(math.dist(site,prior)<.5 for prior in ranked):
            ranked.append(site)
        if len(ranked)>=max_sites:break
    if row._source_binding(board)!=binding:
        raise ValueError('ground_translation_oracle_changed_source')
    if time.monotonic()>=deadline:
        raise ValueError('ground_translation_event_deadline')
    result=dict(deltas_mm=[list(p) for p in ranked],rotation_deg=rotation_deg,
        native_projected_items=len(seen),ground_lands=len(offsets),
        shared_entry_proposals=shared_entry_proposals,
        conservative_same_face_copper_events=surface_proposals,
        native_surface_contacts_projected=surface_count,
        native_vertices_examined=work.vertices,
        native_ground_refill_still_required=refill,
        measurement_portal_proposals=measurement_portal_proposals,
        source_typed_measurement_portal_witnesses=measurement_witnesses,
        every_final_measurement_contact_and_source_boundary_still_required=True,
        source_ground_root_witnesses=root_witnesses if shared_entry_proposals else [],
        immediate_portal_reach_mm=reach if shared_entry_proposals else 0.,
        every_final_ground_obligation_still_required=True,
        declared_portal_geometry_mm=[diameter,drill],elapsed_s=time.monotonic()-started,
        source_unchanged=True,no_path_proof=False,routing_admitted=False,release_authority=False)
    if local_contract is not None:
        fresh=_source_local_event_contract(board,[r['pad_uuid']for r in root_witnesses],
            board_hint=board_hint,deadline=deadline)
        if fresh!=local_contract:raise ValueError('source_local_ground_event_contract_changed')
        result['source_local_ground_contract']=fresh
        result['measurement_portal_reach_mm']=.8 if measurement_portal_proposals else 0.
    return result


def courtyard_screen(board, refs):
    """Exact native courtyard polygons, including selected-selected pairs.

    Missing selected courtyards fail closed; absent unrelated courtyards are
    explicitly unqualified rather than fabricated from label bounding boxes.
    Final saved-board placement/DRC still checks body, edge and keepout rules.
    """
    selected = set(refs); rows = []; missing = []
    fps = list(board.GetFootprints())
    courts = {}
    for fp in fps:
        layer = pcbnew.B_Cu if fp.IsFlipped() else pcbnew.F_Cu
        shape = fp.GetCourtyard(layer)
        if shape.OutlineCount():
            courts[force._uid(fp)] = (layer, shape)
        else:
            missing.append(fp.GetReference())
    for i, fp in enumerate(fps):
        for peer in fps[i+1:]:
            if not ({fp.GetReference(), peer.GetReference()} & selected):
                continue
            first, last = courts.get(force._uid(fp)), courts.get(force._uid(peer))
            if first and last and first[0] == last[0] and first[1].Collide(last[1], 0):
                rows.append([fp.GetReference(), peer.GetReference()])
    return dict(ok=not rows and not (selected & set(missing)), conflicts=rows,
        missing_selected=sorted(selected & set(missing)),
        missing_unrelated=sorted(set(missing)-selected),
        routing_admitted=False, release_authority=False)


def _surface_obstacles(board, refs, layers, *, work, allow_native_ground_refill,
                       native_shape_cache=None,region_mm=None):
    """Actual same-face material; never substitute an all-layer plotting slab.

    No retirement allowlist is accepted. A caller that has source-owned cuts
    applies them to its private board first. Ground refill is an explicit
    proposal scope, not permission to antipad a protected power territory.
    """
    from shapely import affinity
    import cec_fr as fr
    import cec_kelvin_copper_cut as cut
    # Cache only within one immutable native snapshot. It cannot carry a
    # shape across pose/copper epochs; an outline and a fill have distinct
    # keys so reserved pockets can never turn into plotting slabs.
    cache={} if native_shape_cache is None else native_shape_cache
    local=fr._foreign_clearance_resolver(board)
    minimum=int(board.GetDesignSettings().m_MinClearance)
    fixed=[fp for fp in board.GetFootprints() if fp.GetReference() not in refs]
    graphics=[g for fp in fixed for g in fp.GraphicalItems()
              if any(g.IsOnLayer(layer) for layer in layers)]
    graphics += [g for g in board.GetDrawings() if any(g.IsOnLayer(layer) for layer in layers)]
    material=[*(p for fp in fixed for p in fp.Pads()), *board.GetTracks(), *board.Zones(), *graphics]
    obstacles=[];refill=set()
    for item in material:
        work.tick()
        if (item.GetClass()=='PAD' and item.HasHole()
                and item.GetAttribute()==pcbnew.PAD_ATTRIB_NPTH):
            hole=cut._hole(item,True,work)
            for layer in layers:
                obstacles.append((layer,None,int(board.GetDesignSettings().m_HoleClearance),
                    affinity.scale(hole,xfact=1e-6,yfact=1e-6,origin=(0,0)),force._uid(item),'hole'))
        for layer in layers:
            if not item.IsOnLayer(layer):continue
            if item.GetClass()=='PAD' and item.GetAttribute()==pcbnew.PAD_ATTRIB_NPTH:continue
            gap=max(minimum,int(local(item,layer)))
            if region_mm is not None:
                bb=item.GetBoundingBox()
                halo=max(gap,int(board.GetDesignSettings().m_HoleClearance))/1e6+.000002
                if (bb.GetRight()/1e6+halo<region_mm[0] or bb.GetBottom()/1e6+halo<region_mm[1]
                        or bb.GetLeft()/1e6-halo>region_mm[2] or bb.GetTop()/1e6-halo>region_mm[3]):
                    continue
            if item.GetClass()=='ZONE':
                if item.GetIsRuleArea():
                    if not item.GetDoNotAllowFootprints():continue
                    shape=cut._poly(item.Outline(),work);net=None;gap=0;kind='placement_keepout'
                else:
                    if allow_native_ground_refill and item.GetNetname()=='GND':
                        refill.add(force._uid(item));continue
                    if not item.IsFilled():raise ValueError('surface_pose_foreign_zone_fill_unknown')
                    # Laid power pours reserve their native outline as well
                    # as today's fill, exactly like guarded route insertion.
                    outline=fr._zone_is_route_reservation(board,item,layer)
                    key=(force._uid(item),int(layer),'outline' if outline else 'filled')
                    if key not in cache:
                        cache[key]=cut._poly(item.Outline() if outline
                            else item.GetFilledPolysList(layer),work)
                    shape=cache[key]
                    net=int(item.GetNetCode());kind='copper'
            else:
                key=(force._uid(item),int(layer),'filled')
                if key not in cache:cache[key]=cut._shape(item,layer,True,work)
                shape=cache[key]
                net=int(item.GetNetCode()) if hasattr(item,'GetNetCode') else None;kind='copper'
            if not shape.is_empty:
                obstacles.append((layer,net,gap,
                    affinity.scale(shape,xfact=1e-6,yfact=1e-6,origin=(0,0)),force._uid(item),kind))
    return obstacles,sorted(refill),local


def _surface_hits(board,pads,obstacles,local,work):
    """Current land shapes against one immutable, function-local snapshot."""
    from shapely import affinity
    import cec_kelvin_copper_cut as cut
    conflicts=[];minimum=int(board.GetDesignSettings().m_MinClearance);native_by_uuid=None
    import cec_fab_profile as fab
    vias=[t for t in board.GetTracks()if t.GetClass()=='PCB_VIA']
    shapes=[(p,l,affinity.scale(cut._shape(p,l,True,work),xfact=1e-6,yfact=1e-6,origin=(0,0)))
        for p,l in pads]
    for i,(pad,layer,shape) in enumerate(shapes):
        # Rigid package motion cannot change its own source pad spacing.
        # Do not turn an inherited manufacturer/package spacing question
        # into a fabricated placement failure; final DRC still owns it.
        peers=[(l,int(p.GetNetCode()),max(minimum,int(local(p,l))),s,force._uid(p),'copper')
            for p,l,s in shapes[i+1:]
            if force._uid(p.GetParentFootprint())!=force._uid(pad.GetParentFootprint())]
        for other,net,gap,foreign,uid,kind in [*obstacles,*peers]:
            work.tick()
            if other!=layer or (net is not None and net>0 and net==pad.GetNetCode()):continue
            clearance=0 if kind=='placement_keepout' else max(minimum,gap,int(local(pad,layer)))
            distance=shape.distance(foreign)
            if distance<=clearance/1e6+cut.GUARD_NM/1e6:
                # ERROR_OUTSIDE polygons include a numerical guard on BOTH
                # conductors. At exactly the valid fabrication floor that
                # can report a false 4 nm shortfall. Only this guard-sized
                # band may consult the exact native shapes, at the FULL
                # unchanged clearance. Reserved outlines, holes and rule
                # areas do not receive a copper-only fallback.
                if kind=='copper' and distance>=(clearance-3*cut.GUARD_NM)/1e6:
                    if native_by_uuid is None:
                        native_by_uuid={}
                        for item in [*(p for fp in board.GetFootprints() for p in fp.Pads()),
                                *board.GetTracks()]:
                            work.tick();native_by_uuid.setdefault(force._uid(item),[]).append(item)
                    candidates=native_by_uuid.get(uid,[])
                    if len(candidates)==1:
                        item=candidates[0]
                        if item.IsOnLayer(layer) and item.GetClass() in ('PAD','PCB_TRACK','PCB_VIA','PCB_ARC'):
                            work.contact()
                            if not pad.GetEffectiveShape(layer).Collide(item.GetEffectiveShape(layer),clearance):
                                continue
                conflicts.append(dict(pad_uuid=force._uid(pad),ref=pad.GetParentFootprint().GetReference(),
                    pin=pad.GetNumber(),foreign_uuid=uid,kind=kind,layer=board.GetLayerName(layer),
                    clearance_nm=clearance))
        # Same-net copper is not a process exemption. A moved SMD land can
        # partially cover an UNMOVED Ground barrel: foreign-copper tests and
        # the carried-barrel inventory both miss this new assembly defect.
        # Reuse the actual factory's full native land-containment decision;
        # no candidate hole, pad, process floor or unrelated Source debt is
        # changed. Only the explicitly screened lands are inspected here.
        for via in vias:
            work.tick()
            if (not via.IsOnLayer(layer)or via.GetNetCode()<=0
                    or via.GetNetCode()!=pad.GetNetCode()):continue
            diameter=int(via.GetWidth(layer))
            if not pad.GetEffectiveShape(layer).Collide(via.GetPosition(),diameter//2):continue
            ok,reason=fab.via_pad_decision(board,pad,via.GetPosition(),diameter,
                int(via.GetDrillValue()),via.GetNetCode())
            if not ok:
                conflicts.append(dict(pad_uuid=force._uid(pad),ref=pad.GetParentFootprint().GetReference(),
                    pin=pad.GetNumber(),foreign_uuid=force._uid(via),kind='same_net_via_pad_process',
                    layer=board.GetLayerName(layer),reason=reason,
                    same_net_does_not_waive_complete_native_POFV_containment=True))
    work.tick()
    return conflicts


def surface_screen(board, refs, *, timeout_s=10., allow_native_ground_refill=False,
                   selected_refs=None):
    """Read-only native land/copper preflight, before spending route effort.

    Only source-cut private material is absent. It is not a DRC certificate,
    placement/body/edge qualification or permission to move a power bus.
    """
    import cec_kelvin_copper_cut as cut
    refs=tuple(refs)
    if (not refs or len(refs)>8 or len(set(refs))!=len(refs)
            or type(allow_native_ground_refill) is not bool
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10):raise ValueError('bounded_native_surface_preflight_required')
    selected=set(refs if selected_refs is None else selected_refs)
    if not set(refs)<=selected or len(selected)>8:
        raise ValueError('bounded_complete_surface_cell_required')
    before=row._source_binding(board);work=cut._Work(time.monotonic()+timeout_s)
    pads=[]
    for ref in refs:
        fp=board.FindFootprintByReference(ref)
        if fp is None:raise ValueError('native_surface_owner_missing')
        for pad in fp.Pads():
            layers=tuple(pad.GetLayerSet().CuStack())
            if pad.HasHole() or len(layers)!=1:raise ValueError('single_face_surface_lands_required')
            pads.append((pad,int(layers[0])))
    obstacles,refill,local=_surface_obstacles(board,selected,{l for p,l in pads},
        work=work,allow_native_ground_refill=allow_native_ground_refill)
    conflicts=_surface_hits(board,pads,obstacles,local,work)
    if row._source_binding(board)!=before:raise ValueError('surface_preflight_changed_source')
    work.tick()
    return dict(ok=not conflicts,conflicts=conflicts,source_unchanged=True,
        native_ground_refill_still_required=refill,routing_admitted=False,release_authority=False,
        no_path_proof=False,final_native_drc_and_whole_board_receiving_still_required=True)


def _rectangular_sweep(shape, half_x, half_y, work):
    """Minkowski expansion by a land bbox, preserving useful narrow pockets.

    A circular circumscribed pad would wrongly erase legal axis-aligned seats.
    Sweep every polygon boundary, including holes, rather than convex-hulling
    the entire obstacle and destroying its concavities.
    """
    from cec_translation_geometry import rectangular_sweep
    import cec_kelvin_copper_cut as cut
    try:return rectangular_sweep(shape,half_x,half_y,work)
    except ValueError as exc:raise cut.Unknown(str(exc)) from exc


def _surface_translation_fences(board,lands,obstacles,local,domain,work):
    from shapely import affinity
    from shapely.geometry import box
    from shapely.ops import unary_union
    minimum=int(board.GetDesignSettings().m_MinClearance);fences=[];count=0
    if domain.is_empty:return fences,count
    dx0,dy0,dx1,dy1=domain.bounds
    for pad,layer,(x0,y0,x1,y1) in lands:
        work.tick();hx,hy=(x1-x0)/2,(y1-y0)/2;cx,cy=(x0+x1)/2,(y0+y1)/2
        region=box(x0+dx0-.001,y0+dy0-.001,x1+dx1+.001,y1+dy1+.001);grouped={}
        for other,net,gap,shape,uid,kind in obstacles:
            work.tick()
            if other!=layer or (net is not None and net>0 and net==pad.GetNetCode()):continue
            clearance=0 if kind=='placement_keepout' else max(minimum,gap,int(local(pad,layer)))
            # Buffer BEFORE clipping; an obstacle outside the proposed
            # domain can still own a high-clearance incursion into it.
            clipped=shape.buffer(clearance/1e6+.000002,join_style=2).intersection(region)
            if clipped.is_empty:continue
            grouped.setdefault(kind,[]).append(clipped);count+=1
        for shapes in grouped.values():
            expanded=_rectangular_sweep(unary_union(shapes),hx,hy,work)
            fences.append(affinity.translate(expanded,xoff=-cx,yoff=-cy))
    work.tick()
    return fences,count


def assembly_translation_events(board, owners, *, selected_refs, rotation_deg=0,
                                radius_mm=16., max_sites=16, timeout_s=10.,
                                allow_native_ground_refill=False):
    """Continuous native courtyard events for a coordinated owner group.

    Conservative assembly AND same-face copper proposal geometry. Repeated fixed-grid trials
    may miss a narrow legal interval and waste routing on occupied poses.
    Actual final courtyards, capacitor followers and all-layer access remain
    mandatory. Retained power copper and board dimensions are never moved.
    """
    from shapely.geometry import Point, box
    from shapely import affinity
    from shapely.ops import nearest_points, unary_union
    import cec_kelvin_copper_cut as cut
    owners=tuple(owners);refs=set(selected_refs)
    if (not owners or len(owners)>4 or len(set(owners))!=len(owners)
            or not set(owners)<=refs or len(refs)>8 or rotation_deg not in (0,90,180,270)
            or type(radius_mm) not in (int,float) or not math.isfinite(radius_mm)
            or not 0<radius_mm<=16 or type(max_sites) is not int or not 1<=max_sites<=64
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(allow_native_ground_refill) is not bool):
        raise ValueError('bounded_native_group_assembly_events_required')
    before=row._source_binding(board);deadline=time.monotonic()+timeout_s
    work=cut._Work(deadline);original={};projected=[];fixed=[];lands=[]
    anchor=board.FindFootprintByReference(owners[0])
    if anchor is None:raise ValueError('native_assembly_owner_missing')
    try:
        poses=rigid_poses(board,owners,owners[0],(0,0),rotation_deg)
        for ref in owners:
            fp=board.FindFootprintByReference(ref)
            original[ref]=(tuple(fp.GetPosition()),fp.GetOrientationDegrees())
            fp.SetPosition(pcbnew.VECTOR2I(round(poses[ref][0]*1e6),round(poses[ref][1]*1e6)))
            fp.SetOrientationDegrees(poses[ref][2])
            layer=pcbnew.B_Cu if fp.IsFlipped() else pcbnew.F_Cu
            shape=fp.GetCourtyard(layer)
            if not shape.OutlineCount():raise ValueError('native_assembly_courtyard_missing')
            bb=shape.BBox();projected.append((layer,bb.GetLeft()/1e6,bb.GetTop()/1e6,
                bb.GetRight()/1e6,bb.GetBottom()/1e6))
            for pad in fp.Pads():
                work.tick();layers=tuple(pad.GetLayerSet().CuStack())
                if pad.HasHole() or len(layers)!=1:raise ValueError('single_face_surface_lands_required')
                poly=affinity.scale(cut._shape(pad,int(layers[0]),True,work),
                    xfact=1e-6,yfact=1e-6,origin=(0,0))
                lands.append((pad,int(layers[0]),poly.bounds))
        for fp in board.GetFootprints():
            if fp.GetReference() in refs:continue
            layer=pcbnew.B_Cu if fp.IsFlipped() else pcbnew.F_Cu
            shape=fp.GetCourtyard(layer)
            if not shape.OutlineCount():continue
            bb=shape.BBox();fixed.append((layer,bb.GetLeft()/1e6,bb.GetTop()/1e6,
                bb.GetRight()/1e6,bb.GetBottom()/1e6))
    finally:
        for ref,(at,angle) in original.items():
            fp=board.FindFootprintByReference(ref);fp.SetPosition(pcbnew.VECTOR2I(*at))
            fp.SetOrientationDegrees(angle)
    forbidden=[];free=Point(0,0).buffer(radius_mm,quad_segs=32)
    obstacles,refill,local=_surface_obstacles(board,refs,{l for p,l,b in lands},
        work=work,allow_native_ground_refill=allow_native_ground_refill)
    surface_fences,surface_count=_surface_translation_fences(board,lands,obstacles,local,free,work)
    forbidden.extend(surface_fences)
    edges=board.GetBoardEdgesBoundingBox()
    for layer,a0,b0,a1,b1 in projected:
        if time.monotonic()>=deadline:raise ValueError('group_assembly_event_deadline')
        for other,x0,y0,x1,y1 in fixed:
            if layer==other:forbidden.append(box(x0-a1-.002,y0-b1-.002,x1-a0+.002,y1-b0+.002))
        if edges.GetWidth()>0 and edges.GetHeight()>0:
            free=free.intersection(box(edges.GetLeft()/1e6-a0,edges.GetTop()/1e6-b0,
                edges.GetRight()/1e6-a1,edges.GetBottom()/1e6-b1))
    free=free.difference(unary_union(forbidden)).buffer(-.005)
    pieces=[free] if free.geom_type=='Polygon' else list(getattr(free,'geoms',()))
    candidates=[]
    for poly in pieces:
        if poly.is_empty or poly.geom_type!='Polygon':continue
        nearest=nearest_points(Point(0,0),poly)[1]
        middle=poly.representative_point()
        candidates.extend([(nearest.x,nearest.y),(middle.x,middle.y),*list(poly.exterior.coords[:-1])])
    selected=[]
    for point in sorted(set(candidates),key=lambda p:(math.hypot(*p),p)):
        if not any(math.dist(point,prior)<.5 for prior in selected):selected.append(point)
        if len(selected)>=max_sites:break
    if row._source_binding(board)!=before:raise ValueError('assembly_events_changed_source')
    if time.monotonic()>=deadline:raise ValueError('group_assembly_event_deadline')
    return dict(deltas_mm=[[float(v) for v in p] for p in selected],rotation_deg=rotation_deg,
        conservative_native_courtyard_events=True,source_unchanged=True,
        conservative_same_face_copper_events=True,native_surface_contacts_projected=surface_count,
        native_ground_refill_still_required=refill,
        no_path_proof=False,routing_admitted=False,release_authority=False,
        qualified_ground_followers_and_final_native_courtyards_still_required=True)


def cell_translation_events(source, owners, *, board_hint, seed_delta_mm,
                            rotation_deg=0, radius_mm=8., max_sites=32,
                            timeout_s=10., allow_native_ground_refill=False,
                            allow_owned_locked_escapes=False,reference_group_uuids=()):
    """Source-owned cut-aware event proposals, with no worker allowlist.

    The explicit bounded seed is a proposed moving cell, not a scope waiver.
    Only its independently rederived thin departures are absent in a private
    snapshot. Each returned pose needs a FRESH source plan, follower search,
    routing and saved-board receiving; the seed cuts cannot authorize it.
    """
    owners=tuple(owners);source=Path(source).resolve()
    if (not owners or len(owners)>4 or len(set(owners))!=len(owners)
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(allow_owned_locked_escapes) is not bool
            or type(reference_group_uuids)not in(list,tuple)or len(reference_group_uuids)>8
            or any(type(u)is not str or not u for u in reference_group_uuids)
            or len(set(reference_group_uuids))!=len(reference_group_uuids)):
        raise ValueError('bounded_source_cell_events_required')
    started=time.monotonic();family=force._family(source,board_hint);epoch=force._code_identity()
    parent=pcbnew.LoadBoard(str(source));binding=row._source_binding(parent)
    with force._thermal_hint(board_hint):
        assigned=constraints._device_bypass_assignment(parent,project_max_mm=3.5)
    caps=sorted({q['cap_ref'] for q in assigned['assigned'].values()
        if q['requirement']['ref'] in owners})
    refs=[*owners,*caps]
    # Ownership belongs to the actual proposed pose, including its rotation.
    # A rotation-only seed used to look stationary here: its obsolete owned
    # escapes then fenced the surface search and produced an empty domain.
    # Derive the complete rotated source cut first, without granting it to
    # any later pose. The private snapshot already has that rotation; asking
    # the event projector to rotate it again would test a different device.
    seed=rigid_poses(parent,refs,owners[0],seed_delta_mm,rotation_deg)
    proposal=escape.prepare(parent,seed,board_hint=board_hint,max_shift_mm=16.,
        **({'allow_owned_locked_escapes':True} if allow_owned_locked_escapes else {}),
        **({'reference_group_uuids':reference_group_uuids}if reference_group_uuids else {}))
    private=pcbnew.LoadBoard(str(source));escape.apply_private(private,proposal)
    budget=timeout_s-(time.monotonic()-started)
    if budget<=0:raise ValueError('source_cell_event_deadline')
    events=assembly_translation_events(private,owners,selected_refs=refs,
        rotation_deg=0,radius_mm=radius_mm,max_sites=max_sites,
        timeout_s=budget,allow_native_ground_refill=allow_native_ground_refill)
    if (row._source_binding(parent)!=binding or force._family(source,board_hint)!=family
            or force._code_identity()!=epoch):raise ValueError('cell_events_source_or_code_changed')
    return dict(events,seed_poses=seed,seed_delta_mm=list(seed_delta_mm),
        rotation_deg=rotation_deg,private_projector_rotation_deg=0,
        proposed_source_rotation_applied_exactly_once=True,
        deltas_from_source_mm=[[float(dx+seed_delta_mm[0]),float(dy+seed_delta_mm[1])]
            for dx,dy in events['deltas_mm']],
        source_sha256=force._hash(source),source_owned_retired_track_uuids=proposal['retired_track_uuids'],
        source_and_code_unchanged=True,elapsed_s=time.monotonic()-started,
        source_owned_locked_escapes_requested=allow_owned_locked_escapes,
        fresh_source_plan_for_each_final_pose_required=True)


def _completed_package_ground_strap(board,pad,completed,*,deadline):
    """A non-return input may link to an ALREADY proved local Ground root.

    ``completed`` is the live producer's successful-prefix set, not external
    worker testimony.  Capacitor and actual device returns keep their own
    immediate rules; no cycle, new barrel, current rating or relaxed reach
    can be obtained here.  The full-class link producer and its existing
    four-mm package-link bound are exactly those used by cell construction.
    """
    if time.monotonic()>=deadline:return None
    fp=pad.GetParentFootprint();model=roles.footprint_contract(fp)
    if (pad.GetNetname()!='GND' or not model or fp.IsDNP()
            or model['pins'].get(pad.GetNumber())not in ('address','reference')
            or any(v in ('power_output','switch','feedback')for v in model['pins'].values())):
        return None
    for peer,ops in escape.typed_non_return_package_ground_links(board,pad,
            deadline=deadline,peer_uuids=completed):
        if time.monotonic()>=deadline:return None
        added=escape._native_ops(board,ops,'GND');accepted=False
        try:
            path=cell._shortest_track_path_mm(board,pad,peer,snap_mm=.000001)
            if path is not None and path<=4. and time.monotonic()<deadline:
                accepted=True
                return dict(status='completed-typed-package-ground-link',items=added,
                    peer_pad_uuid=force._uid(peer),path_mm=path,package_link_limit_mm=4.,
                    manufacturer_role=model['pins'][pad.GetNumber()],
                    manufacturer_source=model['source'],
                    peer_qualified_native_return_already_completed=True,
                    non_return_input_not_reclassified=True,
                    no_new_process_current_or_immediate_return_reach_authority=True,
                    whole_saved_source_partition_receiving_still_required=True)
        finally:
            if not accepted:discard_items(board,added)
    return None


def ground_screen(board, refs, *, board_path, timeout_s=10., reach_mm=.8,
                  selected_bypasses=None):
    """Construct all local returns jointly, then undo every added native item.

    The live process-qualified return producer checks foreign copper on ALL
    layers, pad containment, holes and immediate stubs. Earlier proposed vias
    remain obstacles to later ones. A failed finite menu is not no-path proof.
    """
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(reach_mm) not in (int, float)
            or not math.isfinite(reach_mm) or not 0 < reach_mm <= .8):
        raise ValueError('bounded_immediate_ground_screen_required')
    refs = tuple(refs)
    if not refs or len(refs) > 8 or len(set(refs)) != len(refs):
        raise ValueError('bounded_complete_ground_cell_required')
    pads = []
    for ref in refs:
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            raise ValueError('ground_cell_member_missing')
        pads.extend(p for p in fp.Pads() if p.GetNetname() == 'GND')
    if not pads or len(pads) > 32 or any(p.HasHole()
            or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD for p in pads):
        raise ValueError('bounded_surface_ground_lands_required')
    before = row._source_binding(board)
    entries = (escape.assigned_ground_entries(board, selected_bypasses, board_hint=board_path)
        if selected_bypasses else {})
    pad_by_uuid = {force._uid(p): p for p in pads}
    if any(entry['portal_pad_uuid'] not in pad_by_uuid for entry in entries.values()):
        raise ValueError('complete_selected_ground_portals_required')
    tracks, groups = cell._cell_trial_snapshot(board)
    started = time.monotonic(); deadline = started+timeout_s
    results = []; error = None
    try:
        # Bypasses first: their immediate returns cannot be replaced by an
        # across-package IC link. Use native identities, never board names.
        def ground_order(pad):
            fp=pad.GetParentFootprint();model=roles.footprint_contract(fp)
            role=model['pins'].get(pad.GetNumber()) if model else None
            return (0 if len(list(fp.Pads()))==2 else 1,
                0 if role in ('ground','power_return') else 1,force._uid(pad))
        pads.sort(key=ground_order)
        completed=set()
        for pad in pads:
            if time.monotonic() >= deadline:
                error = 'ground_pose_screen_deadline'; break
            detail = {}
            import cec_ground_return_policy as return_policy
            actual_reach=return_policy.reach(pad,entries,portal_max_mm=reach_mm)
            result, refusal = cell._add_ground_return(board, pad, board_path=board_path,
                reach_mm=actual_reach, lock=True, diagnostics=detail)
            if result is None and force._uid(pad) in entries and time.monotonic() < deadline:
                entry = entries[force._uid(pad)]
                portal = pad_by_uuid[entry['portal_pad_uuid']]
                if force._uid(portal) in completed:
                    options = escape.ground_link_ops(board, pad, portal, deadline=deadline,
                        max_link_mm=entry['max_link_mm'])
                    if options:
                        added = escape._native_ops(board, options[0], 'GND')
                        path = cell._shortest_track_path_mm(board, pad, portal, snap_mm=.000001)
                        if path is not None and path <= entry['max_link_mm']:
                            result = dict(status='shared-selected-bypass-entry',
                                items=added, selected_bypass_entry=entry, path_mm=path,
                                portal_immediate_return_required=True)
                            refusal = None
                        else:
                            discard_items(board, added)
            if result is None and time.monotonic()<deadline:
                # Match construction's existing typed same-package link
                # proposals, but only towards a successful native prefix.
                # Treating every grounded address input as a separate via
                # need needlessly rejects a routeable fine-pitch package.
                result=_completed_package_ground_strap(board,pad,completed,deadline=deadline)
                if result is not None:refusal=None
            results.append(dict(pad_uuid=force._uid(pad), ref=pad.GetParentFootprint().GetReference(),
                pin=pad.GetNumber(), ok=result is not None,source_return_reach_mm=actual_reach,
                return_proof=cell._report_only(result), refusal=refusal, diagnostic=detail))
            if result is None:
                error = 'immediate_all_layer_return_refused'; break
            completed.add(force._uid(pad))
        if time.monotonic() >= deadline:
            error = 'ground_pose_screen_deadline'
    finally:
        discard_items(board, [t for t in board.GetTracks() if force._uid(t) not in tracks])
        new_groups = [g for g in board.Groups() if force._uid(g) not in groups]
        for g in new_groups:
            for member in list(g.GetItems()):
                g.RemoveItem(member)
        discard_items(board, new_groups)
        # Do not call board.BuildConnectivity: native reconstruction has no
        # authority to relabel source nets. Receiving uses a private graph.
        if cell._cell_trial_snapshot(board) != (tracks, groups) or row._source_binding(board) != before:
            raise ValueError('ground_pose_screen_changed_source_material')
    return dict(ok=error is None and len(results) == len(pads),
        attempted=len(results), required=len(pads), results=results, error=error,
        elapsed_s=time.monotonic()-started, source_unchanged=True,
        no_path_proof=False, routing_admitted=False, release_authority=False,
        whole_board_connectivity_and_field_receiving_still_required=True)


def follower_frontier(board, source, selected_bypasses, *, board_path,
                      max_shift_mm, deadline, joint_owner_ground=False,
                      allow_native_ground_refill=False,ground_attempt_s=1.5):
    """Apply a complete private follower proposal or restore EVERY old pose.

    An early successful capacitor must not leak a partial move when a later
    capacitor times out, has unknown geometry or raises during construction.
    Temporary quarter turns are also rolled back on unexpected exceptions.
    No native item other than a selected footprint pose may change here.
    """
    original={}
    for ref in selected_bypasses:
        cap=board.FindFootprintByReference(ref)
        if cap is None:raise ValueError('selected_native_bypass_missing')
        original[ref]=(cap,tuple(cap.GetPosition()),cap.GetOrientationDegrees())
    before=row._source_binding(board);complete=False
    try:
        result=_follower_frontier(board,source,selected_bypasses,board_path=board_path,
            max_shift_mm=max_shift_mm,deadline=deadline,joint_owner_ground=joint_owner_ground,
            allow_native_ground_refill=allow_native_ground_refill,ground_attempt_s=ground_attempt_s)
        complete=result['ok']
        return result
    finally:
        if not complete:
            for cap,at,angle in original.values():
                cap.SetPosition(pcbnew.VECTOR2I(*at));cap.SetOrientationDegrees(angle)
            if row._source_binding(board)!=before:
                raise ValueError('failed_follower_frontier_changed_source_material')


def _follower_frontier(board, source, selected_bypasses, *, board_path,
                       max_shift_mm, deadline, joint_owner_ground=False,
                       allow_native_ground_refill=False,ground_attempt_s=1.5):
    """Native supply-pin-relative capacitor proposals, not rigid old seats.

    A legal IC pose can be discarded merely because a translated old bypass
    hits a trunk. Enumerate source-selected cap quarter turns around its real
    owner supply land, within the project's existing 3.5 mm assignment bound.
    Actual courtyards and process-qualified immediate returns decide seats.
    A finite greedy follower portfolio is explicitly not exhaustive proof.
    """
    import cec_kelvin_copper_cut as cut
    if (type(ground_attempt_s) not in (int,float) or not math.isfinite(ground_attempt_s)
            or not 0<ground_attempt_s<=10):raise ValueError('bounded_follower_ground_grant_required')
    chosen = {}; trials = [];snapshot_builds=0;portal_event_count=0
    for ref, selected in sorted(selected_bypasses.items()):
        cap = board.FindFootprintByReference(ref)
        prior = source.FindFootprintByReference(ref)
        owner = board.FindFootprintByReference(selected['owner'])
        pin = owner.FindPadByNumber(selected['pin'])
        at = tuple(pin.GetPosition()); original = (tuple(cap.GetPosition()), cap.GetOrientationDegrees())
        current_land=next(p for p in cap.Pads() if p.GetNetname()==selected['rail'])
        current_site=(math.dist(tuple(current_land.GetPosition()),at)/1e6,
            original[0][0],original[0][1],original[1])
        # This snapshot never escapes the one capacitor search. Its own
        # lands are excluded; every other footprint and native item is fixed
        # while probing seats. Rebuild after EACH accepted follower. Ground
        # probes roll back all their additions and check the native binding.
        layers={int(l) for p in cap.Pads() for l in p.GetLayerSet().CuStack()}
        try:
            obstacles,refill,local=_surface_obstacles(board,{ref},layers,
                work=cut._Work(deadline),allow_native_ground_refill=allow_native_ground_refill)
        except (ValueError,cut.Unknown) as exc:
            return dict(ok=False,poses={},trials=trials,no_path_proof=False,
                error=str(exc),surface_snapshot_builds=snapshot_builds)
        snapshot_builds+=1
        sites = []
        for angle in (0,90,180,270):
            cap.SetOrientationDegrees(angle)
            land = next(p for p in cap.Pads() if p.GetNetname() == selected['rail'])
            offset = (land.GetPosition().x-cap.GetPosition().x, land.GetPosition().y-cap.GetPosition().y)
            for distance in (1.,1.5,2.,2.5,3.,3.5):
                for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                    x,y = (at[0]+round(dx*distance*1e6)-offset[0],
                        at[1]+round(dy*distance*1e6)-offset[1])
                    if math.dist((x,y),tuple(prior.GetPosition())) <= max_shift_mm*1e6:
                        sites.append((distance, x, y, angle))
            # Continuous courtyard-boundary events find narrow diagonal
            # pockets that four cardinal rays can never sample. These are
            # native assembly proposals, never clearance/return admission.
            sites.extend(_bypass_courtyard_events(board,cap,pin,prior,
                max_shift_mm=max_shift_mm,deadline=deadline,surface_snapshot=(obstacles,local)))
            # A supply-centred lattice is blind to retained return portals
            # between protected inner buses. Add literal saved Ground-root
            # events, without moving/drilling/qualifying those barrels.
            import cec_bypass_ground_portal_events as ground_portals
            portal_events=ground_portals.events(board,cap,pin,prior,
                max_shift_mm=max_shift_mm,deadline=deadline)
            portal_event_count+=len(portal_events['sites'])
            sites.extend((r['supply_distance_mm'],*r['position_nm'],r['orientation_deg'])
                for r in portal_events['sites'])
        cap.SetPosition(pcbnew.VECTOR2I(*original[0])); cap.SetOrientationDegrees(original[1])
        found = False
        # First try the actual proposed native seat. It can be a good
        # diagonal owner/cap relationship that cardinal rays miss entirely.
        # Preserve qualified existing work before spending the finite lease
        # on a closer but obstructed seat. Optimisation follows closure.
        ordered=sorted(set(sites))
        if (current_site[0]<=3.5 and math.dist(original[0],tuple(prior.GetPosition()))<=max_shift_mm*1e6):
            ordered=[current_site,*[site for site in ordered if site!=current_site]]
        for distance, x,y,angle in ordered:
            if time.monotonic() >= deadline:
                break
            cap.SetPosition(pcbnew.VECTOR2I(x,y));cap.SetOrientationDegrees(angle)
            courts = courtyard_screen(board,[ref]); record=dict(ref=ref,supply_distance_mm=distance,
                pose=[x/1e6,y/1e6,angle],courtyards_ok=courts['ok'])
            trials.append(record)
            if not courts['ok']:
                continue
            try:
                pads=[(p,int(next(iter(p.GetLayerSet().CuStack())))) for p in cap.Pads()]
                hits=_surface_hits(board,pads,obstacles,local,cut._Work(deadline))
                surface=dict(ok=not hits,conflicts=hits,native_ground_refill_still_required=refill,
                    function_local_immutable_snapshot=True,routing_admitted=False,release_authority=False)
            except (ValueError,cut.Unknown) as exc:
                record['surface_geometry_error']=str(exc);continue
            record['surface_access']=surface
            if not surface['ok']:continue
            ground_refs = [ref, selected['owner']] if joint_owner_ground else [ref]
            try:
                proof=ground_screen(board,ground_refs,board_path=board_path,
                    # One obstructed follower must not exhaust every other
                    # seat in the owner portfolio. A timeout is NOT no-path.
                    timeout_s=max(.001,min(ground_attempt_s,deadline-time.monotonic())),
                    selected_bypasses={ref:selected} if joint_owner_ground else None)
            except ValueError as exc:
                record['ground_access_error'] = str(exc)
                continue
            record['ground_access']=proof
            if proof['ok']:
                chosen[ref]=record['pose'];found=True;break
        if not found:
            cap.SetPosition(pcbnew.VECTOR2I(*original[0]));cap.SetOrientationDegrees(original[1])
            return dict(ok=False,poses={},trials=trials,no_path_proof=False,
                surface_snapshot_builds=snapshot_builds,
                retained_ground_portal_event_count=portal_event_count)
    return dict(ok=True,poses=chosen,trials=trials,no_path_proof=False,
        surface_snapshot_builds=snapshot_builds,
        retained_ground_portal_event_count=portal_event_count)


def _bypass_courtyard_events(board, cap, supply, source_cap, *, max_shift_mm, deadline,
                             surface_snapshot=None):
    from shapely import affinity
    from shapely.geometry import Point, box
    from shapely.ops import nearest_points, unary_union
    import cec_kelvin_copper_cut as cut
    layer=pcbnew.B_Cu if cap.IsFlipped() else pcbnew.F_Cu
    court=cap.GetCourtyard(layer)
    if not court.OutlineCount():return []
    at=cap.GetPosition();rail=next(p for p in cap.Pads() if p.GetNetname()==supply.GetNetname())
    center=((supply.GetPosition().x-rail.GetPosition().x)/1e6,
        (supply.GetPosition().y-rail.GetPosition().y)/1e6)
    bb=court.BBox();a0,b0,a1,b1=(bb.GetLeft()/1e6,bb.GetTop()/1e6,
        bb.GetRight()/1e6,bb.GetBottom()/1e6)
    blocked=[]
    for peer in board.GetFootprints():
        if time.monotonic()>=deadline:return []
        if peer==cap or peer.IsFlipped()!=cap.IsFlipped():continue
        shape=peer.GetCourtyard(layer)
        if not shape.OutlineCount():continue
        b=shape.BBox();blocked.append(box(b.GetLeft()/1e6-a1-.002,b.GetTop()/1e6-b1-.002,
            b.GetRight()/1e6-a0+.002,b.GetBottom()/1e6-b0+.002))
    free=Point(*center).buffer(3.5,quad_segs=32).intersection(Point(
        (source_cap.GetPosition().x-at.x)/1e6,(source_cap.GetPosition().y-at.y)/1e6
        ).buffer(max_shift_mm,quad_segs=32))
    if surface_snapshot is not None:
        obstacles,local=surface_snapshot;work=cut._Work(deadline);lands=[]
        for pad in cap.Pads():
            bounds=affinity.scale(cut._shape(pad,layer,True,work),xfact=1e-6,yfact=1e-6,origin=(0,0)).bounds
            lands.append((pad,layer,bounds))
        fences,_=_surface_translation_fences(board,lands,obstacles,local,free,work)
        blocked.extend(fences)
    free=free.difference(unary_union(blocked)).buffer(-.005)
    pieces=[free] if free.geom_type=='Polygon' else list(getattr(free,'geoms',()))
    candidates=[]
    for poly in pieces:
        if poly.geom_type!='Polygon' or poly.is_empty:continue
        near=nearest_points(Point(*center),poly)[1];middle=poly.representative_point()
        candidates.extend([(near.x,near.y),(middle.x,middle.y),*list(poly.exterior.coords[:-1])])
    ranked=[];out=[]
    for dx,dy in sorted(set(candidates),key=lambda p:(math.dist(p,center),p)):
        point=(float(dx),float(dy))
        if any(math.dist(point,other)<.25 for other in ranked):continue
        ranked.append(point);x,y=at.x+round(dx*1e6),at.y+round(dy*1e6)
        rail_x,rail_y=x+rail.GetPosition().x-at.x,y+rail.GetPosition().y-at.y
        distance=math.dist((rail_x,rail_y),tuple(supply.GetPosition()))/1e6
        if distance<=3.5:out.append((distance,x,y,cap.GetOrientationDegrees()))
        if len(out)>=16:break
    return out


def frontier(source, owners, *, board_hint, deltas_mm, rotations=(0, 90, 180, 270),
             max_shift_mm=16., timeout_s=10., max_results=4, flexible_bypasses=False,
             allow_native_ground_refill=False, complete_escapes=False,
             include_power_layer=False,allow_owned_locked_escapes=False):
    """Finite source-bound placement-and-access portfolio, never adoption.

    Select manufacturer-typed owners and their unique source-selected bypasses
    through ``escape.prepare``. Only its rederived thin departure scope can be
    retired in each private board. Every retained bus/barrel remains unchanged.
    The caller funds explicit generic translations; no hidden board-specific
    ref, coordinate, bus move, load reduction or dimension growth is a rule.
    Complete-escape mode requires a full compatible connection proposal,
    not merely ground/courtyard fit. Legacy ground-only results explicitly
    retain every other connection obligation; neither mode admits IC motion.
    """
    import cec_kelvin_copper_cut as cut
    owners = tuple(owners); deltas_mm = tuple(deltas_mm); rotations = tuple(rotations)
    if (not owners or len(owners) > 4 or len(set(owners)) != len(owners)
            or not deltas_mm or len(deltas_mm)*len(rotations) > 256
            or not rotations or any(v not in (0, 90, 180, 270) for v in rotations)
            or type(max_results) is not int or not 1 <= max_results <= 8
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(flexible_bypasses) is not bool
            or type(allow_native_ground_refill) is not bool
            or type(complete_escapes) is not bool or type(include_power_layer) is not bool
            or type(allow_owned_locked_escapes) is not bool
            or (include_power_layer and not complete_escapes)):
        raise ValueError('bounded_escape_pose_portfolio_required')
    started = time.monotonic(); deadline = started+timeout_s
    source = Path(source).resolve(); family = force._family(source, board_hint)
    epoch = force._code_identity(); parent = pcbnew.LoadBoard(str(source))
    with force._thermal_hint(board_hint):
        assigned = constraints._device_bypass_assignment(parent, project_max_mm=3.5)
    caps = sorted({r['cap_ref'] for r in assigned['assigned'].values()
        if r['requirement']['ref'] in owners})
    refs = [*owners, *caps]; history = []; found = []
    for delta_index,delta in enumerate(deltas_mm):
        for rotation_index,rotation in enumerate(rotations):
            if time.monotonic() >= deadline or len(found) >= max_results:
                break
            record = dict(delta_mm=list(delta), rotation_deg=rotation)
            history.append(record)
            remaining=(len(deltas_mm)-delta_index)*len(rotations)-rotation_index
            # Reserve independent grants for other owner poses. Expensive
            # ground/follower searches used to spend the entire portfolio on
            # its first pose, despite dozens of untried geometric events.
            pose_deadline=min(deadline,time.monotonic()+max(2.,
                (deadline-time.monotonic())/min(8,remaining)))
            record['pose_grant_s']=max(0.,pose_deadline-time.monotonic())
            try:
                poses = rigid_poses(parent, refs, owners[0], delta, rotation)
                if flexible_bypasses:
                    # This is only an unfinished initial seat. Each selected
                    # follower is recompiled against its actual moved owner.
                    for ref in caps:
                        f=parent.FindFootprintByReference(ref)
                        poses[ref]=[f.GetPosition().x/1e6+delta[0],
                            f.GetPosition().y/1e6+delta[1],f.GetOrientationDegrees()]
                import cec_native_pose_prescreen as prescreen
                record['before_source_preparation_courtyards']=prescreen.screen(parent,poses,
                    selected_refs=owners if flexible_bypasses else refs)
                if not record['before_source_preparation_courtyards']['ok']:
                    record['reason']='native_courtyard_refused_before_source_preparation';continue
                proposal = escape.prepare(parent, poses, board_hint=board_hint, max_shift_mm=max_shift_mm,
                    allow_owned_locked_escapes=allow_owned_locked_escapes)
                trial = pcbnew.LoadBoard(str(source))
                escape.apply_private(trial, proposal)
                courts = courtyard_screen(trial, owners if flexible_bypasses else refs)
                record['courtyards'] = courts
                if not courts['ok']:
                    record['reason'] = 'native_courtyard_refused'; continue
                active=[r for r in owners if r not in proposal['stationary_device_owners']]
                if active:
                    record['surface_access']=surface_screen(trial,active,
                        selected_refs=[r for r in refs if r not in proposal['stationary_device_owners']],
                        timeout_s=max(.001,min(10.,pose_deadline-time.monotonic())),
                        allow_native_ground_refill=allow_native_ground_refill)
                    if not record['surface_access']['ok']:
                        record['reason']='native_surface_copper_refused';continue
                if flexible_bypasses:
                    # Owner access depends on the selected follower's seat.
                    # Screening the owner first demanded redundant barrels
                    # and rejected otherwise legal short shared-entry cells.
                    followers=follower_frontier(trial,parent,proposal['selected_bypasses'],
                        board_path=board_hint,max_shift_mm=max_shift_mm,deadline=pose_deadline,
                        joint_owner_ground=True,allow_native_ground_refill=allow_native_ground_refill)
                    record['followers']=followers
                    if not followers['ok']:
                        record['reason']='selected_bypass_frontier_refused';continue
                    poses.update(followers['poses'])
                    # Independently derive every cut again for the FINAL
                    # poses. No earlier producer's transient draft is proof.
                    proposal=escape.prepare(parent,poses,board_hint=board_hint,max_shift_mm=max_shift_mm,
                        allow_owned_locked_escapes=allow_owned_locked_escapes)
                    # A follower may return to its source seat, changing
                    # which exclusive stubs are actually owned. Never test
                    # its final ground access against the initial draft's
                    # over-cut or under-cut material snapshot.
                    trial=pcbnew.LoadBoard(str(source))
                    escape.apply_private(trial,proposal)
                    courts=courtyard_screen(trial,refs)
                    if not courts['ok']:
                        record['reason']='final_complete_courtyards_refused';continue
                active=[r for r in refs if r not in proposal['stationary_device_owners']]
                record['final_surface_access']=surface_screen(trial,active,
                    selected_refs=active,timeout_s=max(.001,min(10.,pose_deadline-time.monotonic())),
                    allow_native_ground_refill=allow_native_ground_refill)
                if not record['final_surface_access']['ok']:
                    record['reason']='final_native_surface_copper_refused';continue
                record['ground_access'] = ground_screen(trial, refs, board_path=board_hint,
                    timeout_s=max(.001, min(10., pose_deadline-time.monotonic())),
                    selected_bypasses=proposal['selected_bypasses'] if flexible_bypasses else None)
                if record['ground_access']['ok']:
                    connection=None
                    if complete_escapes:
                        remaining=pose_deadline-time.monotonic()
                        if remaining<=0:
                            record['reason']='complete_escape_work_lease_exhausted';continue
                        connection=escape.complete_connection_screen(source,trial,proposal,
                            board_hint=board_hint,timeout_s=min(10.,remaining),
                            measurement_bridges=True,include_power_layer=include_power_layer)
                        record['complete_connections']=connection
                        if connection.get('complete') is not True:
                            record['reason']='complete_cell_connections_not_constructed';continue
                    found.append(dict(poses=poses, proposal=proposal,
                        native_ground_access=record['ground_access'], native_courtyards=courts,
                        complete_private_connections=connection,
                        every_connection_proposed=complete_escapes,
                        remaining_connection_obligations_required=not complete_escapes,
                        routing_admitted=False, release_authority=False))
            except (ValueError,cut.Unknown) as exc:
                record['reason'] = str(exc)
        if time.monotonic() >= deadline or len(found) >= max_results:
            break
    if family != force._family(source, board_hint) or epoch != force._code_identity():
        raise ValueError('escape_pose_source_or_code_changed')
    return dict(schema=1, scope='bounded_complete_cell_escape_pose_frontier',
        source=str(source), source_sha256=force._hash(source), owners=list(owners), refs=refs,
        poses=found, history=history, elapsed_s=time.monotonic()-started,
        complete_escape_screen_required=complete_escapes,
        deadline_exhausted=time.monotonic() >= deadline, source_and_code_unchanged=True,
        no_path_proof=False, routing_admitted=False, release_authority=False)
