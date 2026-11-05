"""Reject macro seats that would force an unplanned priority-copper rebuild.

The source's board-design-basis current contracts and existing locked pours
define the priority set. All enabled faces are inspected using native filled
copper and real lands/barrels, never a placement-layer-only bounding box.
This is a proposal filter, not clearance/current/Kelvin or release authority.
"""
import json
import math
import tempfile
import time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_fab_profile as fab
import cec_fr as fr
import cec_current_topology as topology


def _receive_retained_copper_only(source,candidate,owners,*,deadline):
    """Empty transport is not empty work: prove actual whole retained metal."""
    import cec_field_coupling as field
    import cec_additive_route_receiving as ast
    import cec_copper_echo as syntax
    first={force._uid(f):f for f in source.GetFootprints()}
    last={force._uid(f):f for f in candidate.GetFootprints()}
    def pose(f):return tuple(f.GetPosition()),f.GetOrientationDegrees(),f.IsFlipped()
    moved={u for u,f in first.items()if pose(f)!=pose(last[u])}
    if moved!=set(owners)or not moved or any(first[u].IsFlipped()!=last[u].IsFlipped()for u in moved):
        raise ValueError('exact_actual_retained_copper_macro_owner_motion_required')
    layers=set(map(int,source.GetEnabledLayers().CuStack()))
    for board in(source,candidate):
        if any(not z.GetIsRuleArea()and not z.IsFilled()for z in board.Zones()):
            raise ValueError('retained_copper_macro_unknown_source_or_candidate_fill')
    # Complete native serialized definitions retain via process/tenting,
    # arcs, every filled island and group membership, not just XY/width.
    # Unmoved owners and copper-layer board graphics are equally immutable.
    inventories=[]
    with tempfile.TemporaryDirectory(prefix='cec-retained-macro-priority-')as work:
        for index,board in enumerate((source,candidate)):
            if time.monotonic()>=deadline:raise ValueError('native_macro_priority_preflight_deadline')
            drawing_ids={force._uid(i)for i in board.GetDrawings()if any(i.IsOnLayer(l)for l in layers)}
            saved=Path(work)/(str(index)+'.kicad_pcb');field._save_field_snapshot(board,saved)
            _,nodes=ast._nodes(saved)
            inventories.append({uid:syntax._freeze(node)for uid,node in nodes.items()
                if node[0]in('segment','arc','via','zone','group')or uid in drawing_ids
                or node[0]=='footprint'and uid not in moved})
    if inventories[0]!=inventories[1]:
        raise ValueError('empty_macro_changes_require_exact_all_source_copper_retention')
    if time.monotonic()>=deadline:raise ValueError('native_macro_priority_preflight_deadline')
    return dict(complete=True,actual_moved_owner_uuids=sorted(moved),
        unchanged_native_definition_count=len(inventories[0]),all_source_copper_and_groups_retained=True,
        old_pad_contact_restoration_not_proven=True,current_or_route_admission=False)


def inspect(source,candidate,transport,*,board_hint,timeout_s=10.,max_conflicts=1024,
            extend_owned_local_power_escapes=False,source_measurement_leaves=(),retired_source_track_uuids=(),
            allow_contained_source_barrel_motion=False,ground_barrel_clearance_window_uuids=(),
            actual_ground_barrel_window_board=None,source_reconstruction_packet=None):
    if (type(board_hint) is not str or not board_hint
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(max_conflicts) is not int or not 1<=max_conflicts<=1024
            or type(extend_owned_local_power_escapes) is not bool or type(allow_contained_source_barrel_motion) is not bool
            or type(transport) is not dict
            or transport.get('scope')!='provisional_source_owned_smd_cohort_endpoint_transport'):
        raise ValueError('bounded_source_macro_priority_preflight_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('native_macro_priority_preflight_deadline')
    import cec_macro_ground_barrel_window as windows
    window_ids=windows.ids(ground_barrel_clearance_window_uuids)
    if not window_ids and actual_ground_barrel_window_board is not None:
        raise ValueError('explicit_carried_Ground_window_identities_required')
    changes=transport.get('changes');owners=transport.get('moved_owner_footprint_uuids')
    if (type(changes) is not list or not 0<=len(changes)<=512 or type(owners) is not list
            or not 1<=len(owners)<=32 or len(set(owners))!=len(owners)):
        raise ValueError('literal_bounded_source_macro_changes_required')
    changed={r['uuid'] for r in changes}
    if len(changed)!=len(changes):raise ValueError('unique_native_macro_change_identity_required')
    old={force._uid(t):t for t in source.GetTracks()};new={force._uid(t):t for t in candidate.GetTracks()}
    first={force._uid(f):f for f in source.GetFootprints()};last={force._uid(f):f for f in candidate.GetFootprints()}
    layers=tuple(map(int,source.GetEnabledLayers().CuStack()))
    if (layers!=tuple(map(int,candidate.GetEnabledLayers().CuStack())) or old.keys()!=new.keys()
            or first.keys()!=last.keys() or not changed<=old.keys() or not set(owners)<=first.keys()):
        raise ValueError('exact_source_macro_population_and_stack_required')
    zero_motion_receiving=(_receive_retained_copper_only(source,candidate,owners,deadline=deadline)if not changes else None)
    with force._thermal_hint(board_hint):contracts=topology.route_width_contracts(source,board_hint=board_hint)
    basis={net for net,c in contracts.items()
        if (c.get('current_authority') or {}).get('source')=='board_design_basis'}
    pour_owned=set(fr.locked_pour_authority_nets_board(source,include_complete_nets=False))
    priority=basis|pour_owned
    # Native plane identity, not a colour or a layer-number guess.
    planes={source.GetLayerID(n) for n in fr.plane_layers(source)}
    reference={str(z.GetNetname()) for z in source.Zones() if z.GetLayer() in planes}
    priority-=reference
    # A thin manufacturer measurement INPUT can share its net name with a
    # force bus. Only the independently rederived exclusive Source leaf may
    # be reconstructed; its first real boundary and every force conductor
    # stay protected. Net names/widths alone never grant this distinction.
    measurement_ids=set();measurement_proofs=[]
    if type(source_measurement_leaves) not in (list,tuple) or len(source_measurement_leaves)>32:
        raise ValueError('bounded_explicit_source_measurement_leaf_scope_required')
    if source_measurement_leaves:
        import cec_measurement_leaf as leaf
        import cec_macro_rc_input_prefix as rc_prefix
        import cec_ordinary_route_receiving as ordinary
        retired=ordinary._ids(retired_source_track_uuids,'complete_source_macro_retired_tracks',128)
        source_pads={force._uid(p):p for fp in source.GetFootprints() for p in fp.Pads()}
        linear_scope='source_typed_thin_measurement_leaf'
        auxiliary_scope='source_typed_same_net_auxiliary_measurement_strap'
        supplied={};by_pad={};fresh_by_pad={}
        for proof in source_measurement_leaves:
            tick()
            if (type(proof) is not dict or proof.get('pad_uuid') not in source_pads
                    or proof.get('scope') not in (linear_scope,auxiliary_scope,rc_prefix.SCOPE)
                    or force._uid(source_pads[proof['pad_uuid']].GetParentFootprint()) not in owners):
                raise ValueError('literal_moving_manufacturer_measurement_leaf_required')
            key=(proof['pad_uuid'],proof['scope'])
            if key in supplied:raise ValueError('unique_typed_source_measurement_obligation_required')
            supplied[key]=proof;by_pad.setdefault(proof['pad_uuid'],set()).add(proof['scope'])
        for pad_uuid,scopes in by_pad.items():
            tick()
            if rc_prefix.SCOPE in scopes:
                if scopes!={rc_prefix.SCOPE}:
                    raise ValueError('distinct_canonical_RC_prefix_not_an_ordinary_leaf_alias')
                supplied_prefix=supplied[pad_uuid,rc_prefix.SCOPE]
                fresh_by_pad[pad_uuid]={rc_prefix.SCOPE:rc_prefix.plan(source,Path(source.GetFileName()),
                    board_hint=board_hint,request=supplied_prefix['identity_request'],
                    timeout_s=max(.001,deadline-time.monotonic()))}
                continue
            external=supplied.get((pad_uuid,linear_scope))
            if external is None:raise ValueError('complete_external_measurement_and_auxiliary_obligations_required')
            coupled=('separately_owned_source_auxiliary_strap' in external or auxiliary_scope in scopes)
            if coupled:
                if scopes!={linear_scope,auxiliary_scope}:
                    raise ValueError('complete_external_measurement_and_auxiliary_obligations_required')
                # Re-inspect the complete saved map, never trust a worker's
                # group label or let it substitute for either copper scope.
                mapped='source_reference_map' in supplied[pad_uuid,auxiliary_scope]
                departure,strap=leaf.plan_with_auxiliary_strap(source,pad_uuid,
                    timeout_s=max(.001,deadline-time.monotonic()),
                    allow_source_reference_maps=mapped)
                fresh_by_pad[pad_uuid]={linear_scope:departure,auxiliary_scope:strap}
            else:
                fresh_by_pad[pad_uuid]={linear_scope:leaf.plan(source,pad_uuid,
                    timeout_s=max(.001,deadline-time.monotonic()))}
        # Preserve the caller's obligation order, but independently rederive
        # BOTH roles at a declared same-net package strap. One pin can own a
        # distinct external departure and internal strap; neither may stand
        # in for the other or waive a branch/current/fixed-contact check.
        for proof in source_measurement_leaves:
            tick();fresh=fresh_by_pad[proof['pad_uuid']][proof['scope']]
            if json.loads(json.dumps(fresh,allow_nan=False))!=proof:
                raise ValueError('stale_or_forged_source_priority_measurement_leaf')
            ids=set(fresh['track_uuids'])
            if not ids or not ids<=retired or not ids<=old.keys() or ids&measurement_ids:
                raise ValueError('entire_unique_source_measurement_leaf_must_be_reconstructed')
            measurement_ids.update(ids);measurement_proofs.append(fresh)
    def conductor_dims(item):
        common=(item.GetClass(),str(item.GetNetname()),bool(item.IsLocked()))
        if item.GetClass()=='PCB_VIA':return common+(int(item.TopLayer()),int(item.BottomLayer()),
            int(item.GetViaType()),int(item.GetDrillValue()),tuple(int(item.GetWidth(l)) for l in layers))
        return common+(int(item.GetLayer()),int(item.GetWidth()),
            tuple(item.GetMid()) if item.GetClass()=='PCB_ARC' else None)
    # A tiny extension of a local escape is not a licence to shift a bus.
    # Rederive ownership from live native lands, never the transport report.
    # The complete old priority strip must remain inside the new strip.
    extensions=[];local_vias={}
    if extend_owned_local_power_escapes or allow_contained_source_barrel_motion:
        priority_changed=[u for u in changed if str(old[u].GetNetname()) in priority]
        if len(priority_changed)>16:raise ValueError('bounded_local_priority_escape_extension_required')
        for uid in priority_changed:
            tick();v,q=old[uid],new[uid]
            if v.GetClass()!='PCB_VIA':continue
            d=tuple(b-a for a,b in zip(tuple(v.GetPosition()),tuple(q.GetPosition())))
            if (conductor_dims(v)!=conductor_dims(q) or not 0<math.hypot(*d)<=1000000
                    or not fab.local_pofv_via_decision(source,v)[0]
                    or not fab.local_pofv_via_decision(candidate,q)[0]):continue
            groups=[g for g in source.Groups() if g.ContainsItem(v)]
            if any(g.GetName()!=fr.LOCAL_POFV_SIGNAL_VIA_GROUP or g.IsLocked() for g in groups):continue
            owned=[]
            for owner in owners:
                tick();f,after=first[owner],last[owner]
                if (f.GetParentGroup() is not None or f.IsLocked()
                        or tuple(b-a for a,b in zip(tuple(f.GetPosition()),tuple(after.GetPosition())))!=d):continue
                targets={force._uid(p):p for p in after.Pads()}
                for p in f.Pads():
                    if p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.GetNetname()!=v.GetNetname():continue
                    faces=[l for l in layers if p.IsOnLayer(l)]
                    r=targets.get(force._uid(p))
                    if len(faces)!=1 or r is None or tuple(r.GetPosition())!=tuple(x+s for x,s in zip(tuple(p.GetPosition()),d)):continue
                    # Keep native polygon/box owners alive. Chaining a
                    # borrowed BBox().GetSize() through a temporary polygon
                    # can read released SWIG storage instead of dimensions.
                    before_land=p.GetEffectivePolygon(faces[0]);after_land=r.GetEffectivePolygon(faces[0])
                    before_box=before_land.BBox();after_box=after_land.BBox()
                    if ((int(before_box.GetWidth()),int(before_box.GetHeight()))!=
                            (int(after_box.GetWidth()),int(after_box.GetHeight()))
                            or str(r.GetNetname())!=str(p.GetNetname()) or tuple(p.GetSize())!=tuple(r.GetSize())
                            or p.GetShape()!=r.GetShape() or p.GetAttribute()!=r.GetAttribute()
                            or p.GetOrientationDegrees()!=r.GetOrientationDegrees()
                            or tuple(p.GetLayerSet().Seq())!=tuple(r.GetLayerSet().Seq())):continue
                    remainder=pcbnew.SHAPE_POLY_SET();v.TransformShapeToPolygon(remainder,faces[0],0,1,pcbnew.ERROR_OUTSIDE)
                    remainder.BooleanSubtract(p.GetEffectivePolygon(faces[0],pcbnew.ERROR_INSIDE))
                    if remainder.OutlineCount():continue
                    remainder=pcbnew.SHAPE_POLY_SET();q.TransformShapeToPolygon(remainder,faces[0],0,1,pcbnew.ERROR_OUTSIDE)
                    remainder.BooleanSubtract(r.GetEffectivePolygon(faces[0],pcbnew.ERROR_INSIDE))
                    if not remainder.OutlineCount():owned.append(force._uid(p))
            if len(owned)==1:local_vias[uid]=dict(uuid=uid,owner_pad_uuid=owned[0],translation_nm=list(d))
        for uid in priority_changed:
            if not extend_owned_local_power_escapes:continue
            tick();t,q=old[uid],new[uid]
            if t.GetClass()!='PCB_TRACK' or t.GetParentGroup() is not None or conductor_dims(t)!=conductor_dims(q):continue
            a0,a1=tuple(t.GetStart()),tuple(t.GetEnd());b0,b1=tuple(q.GetStart()),tuple(q.GetEnd())
            moved=[i for i,(a,b) in enumerate(zip((a0,a1),(b0,b1))) if a!=b]
            if len(moved)!=1 or t.GetLength()>10000000:continue
            i=moved[0];at=(a0,a1)[i];dest=(b0,b1)[i]
            anchored=[v for v in local_vias if old[v].GetNetname()==t.GetNetname()
                and old[v].IsOnLayer(t.GetLayer()) and tuple(old[v].GetPosition())==at
                and tuple(new[v].GetPosition())==dest]
            if len(anchored)!=1:continue
            # Equal-width native PCB_TRACKs are swept disks. Exact integer
            # collinearity plus interval containment proves that EVERY old
            # disk remains in the extension. Polygon approximations of two
            # identical round caps can disagree by a nanometre; neither
            # approximating their ink nor relaxing a tolerance is needed.
            from cec_route_quality import is_canonical_stroke
            if not is_canonical_stroke(a0,a1,tolerance_nm=0) or not is_canonical_stroke(b0,b1,tolerance_nm=0):continue
            dx,dy=a1[0]-a0[0],a1[1]-a0[1]
            if dx*(dest[1]-at[1])!=dy*(dest[0]-at[0]):continue
            nx,ny=b1[0]-b0[0],b1[1]-b0[1];length2=nx*nx+ny*ny
            if not all(0<=(p[0]-b0[0])*nx+(p[1]-b0[1])*ny<=length2 for p in (a0,a1)):continue
            extensions.append(dict(uuid=uid,owner_barrel_uuid=anchored[0],source_width_nm=int(t.GetWidth()),
                all_original_priority_strip_retained=True,extension_nm=round(math.dist(at,dest))))
    # A local in-pad barrel can move WITHOUT extending any bus: the entire
    # carried barrel can remain enclosed in the exact old full-width copper
    # on every contacted non-owner face. Re-derive that native enclosure;
    # transport flags and mere same-net/body overlap grant no permission.
    unchanged_access=[]
    if extend_owned_local_power_escapes or allow_contained_source_barrel_motion:
        import cec_route_dimensions as dimensions
        resolver=dimensions.project_resolver(source.GetFileName(),board=source)
        source_pads={force._uid(p):p for f in source.GetFootprints() for p in f.Pads()}
        for uid,owned in local_vias.items():
            tick();v,q=old[uid],new[uid];pad=source_pads[owned['owner_pad_uuid']]
            faces=[l for l in layers if pad.IsOnLayer(l)]
            if len(faces)!=1:continue
            accesses=[];valid=True;net=str(v.GetNetname());spec=resolver(net) or {}
            for lid in layers:
                if lid==faces[0] or not v.IsOnLayer(lid):continue
                items=[t for t in old.values() if t.GetClass() in ('PCB_TRACK','PCB_ARC')
                    and t.GetNetname()==net and t.IsOnLayer(lid)
                    and t.GetEffectiveShape(lid).Collide(v.GetEffectiveShape(lid),0)]
                for t in items:
                    tick();other=new[force._uid(t)]
                    floor=math.ceil(max(float(spec.get('track_width') or 0),
                        float((contracts.get(net,{}).get('required_by_layer_mm') or {}).get(source.GetLayerName(lid)) or 0),
                        dimensions.board_limits(source)['track_width'])*1e6)
                    if (force._uid(t) in changed or conductor_dims(t)!=conductor_dims(other)
                            or tuple(t.GetStart())!=tuple(other.GetStart()) or tuple(t.GetEnd())!=tuple(other.GetEnd())
                            or t.GetWidth()<floor):valid=False;break
                    envelope=pcbnew.SHAPE_POLY_SET();q.TransformShapeToPolygon(envelope,lid,0,1,pcbnew.ERROR_OUTSIDE)
                    copper=pcbnew.SHAPE_POLY_SET();t.TransformShapeToPolygon(copper,lid,0,1,pcbnew.ERROR_INSIDE)
                    envelope.BooleanSubtract(copper)
                    if envelope.OutlineCount():valid=False;break
                    accesses.append(dict(track_uuid=force._uid(t),layer=int(lid),
                        source_width_nm=int(t.GetWidth()),required_width_floor_nm=floor))
                if not valid:break
            if valid and accesses:
                unchanged_access.append(dict(uuid=uid,owner_pad_uuid=owned['owner_pad_uuid'],
                    exact_unchanged_full_width_source_accesses=accesses,
                    complete_native_barrel_enclosure=True,new_capacity_or_current_authority=False))
    extension_ids={r['uuid'] for r in extensions}
    extended_vias={r['owner_barrel_uuid'] for r in extensions}
    enclosed_vias={r['uuid'] for r in unchanged_access}
    pending=None;reconstructed=set()
    existing_allowed=extension_ids|extended_vias|enclosed_vias|measurement_ids
    unplanned={u for u in changed if str(old[u].GetNetname())in priority and u not in existing_allowed}
    if source_reconstruction_packet is not None and unplanned:
        import cec_macro_priority_reconstruction as reconstruction
        pending=reconstruction.inspect(source,candidate,transport,source_reconstruction_packet,
            board_hint=board_hint,timeout_s=max(.001,deadline-time.monotonic()))
        reconstructed=set(pending['track_uuids'])|set(pending['barrel_uuids'])
    allowed=extension_ids|extended_vias|enclosed_vias|measurement_ids|reconstructed
    fixed=[];priority_motion=[]
    for uid,t in old.items():
        tick()
        if str(t.GetNetname()) not in priority:continue
        if uid in measurement_ids:continue
        if uid in changed:
            if uid not in allowed:priority_motion.append(uid)
            continue
        q=new[uid]
        if (conductor_dims(t)!=conductor_dims(q) or tuple(t.GetStart())!=tuple(q.GetStart())
                or tuple(t.GetEnd())!=tuple(q.GetEnd()) or int(t.GetLayer())!=int(q.GetLayer())):
            raise ValueError('undeclared_priority_source_conductor_changed')
        fixed.append(t)
    for uid,fp in first.items():
        if uid in owners:continue
        after={force._uid(p):p for p in last[uid].Pads()}
        for p in fp.Pads():
            if str(p.GetNetname()) not in priority:continue
            q=after.get(force._uid(p))
            if (q is None or str(p.GetNetname())!=str(q.GetNetname())
                    or tuple(p.GetPosition())!=tuple(q.GetPosition()) or tuple(p.GetSize())!=tuple(q.GetSize())
                    or tuple(p.GetDrillSize())!=tuple(q.GetDrillSize())
                    or tuple(p.GetLayerSet().Seq())!=tuple(q.GetLayerSet().Seq())
                    or any(p.GetEffectivePolygon(l).Format()!=q.GetEffectivePolygon(l).Format()
                        for l in layers if p.IsOnLayer(l))):
                raise ValueError('undeclared_priority_source_land_changed')
            fixed.append(p)
    zones={force._uid(z):z for z in candidate.Zones()}
    window_proof=None;window_zones={}
    if window_ids:
        expected,window_proof=windows.priority_expected(source,candidate,transport,window_ids,
            actual_ground_barrel_window_board,timeout_s=max(.001,deadline-time.monotonic()))
        window_zones={force._uid(z):z for z in expected.Zones()}
    for z in source.Zones():
        tick()
        if z.GetIsRuleArea() or str(z.GetNetname()) not in priority:continue
        q=zones.get(force._uid(z))
        if (q is None or z.Outline().Format()!=q.Outline().Format() or str(z.GetNetname())!=str(q.GetNetname())
                or tuple(z.GetLayerSet().CuStack())!=tuple(q.GetLayerSet().CuStack())
                or bool(z.IsLocked())!=bool(q.IsLocked())
                or any(z.GetFilledPolysList(l).Format()!=q.GetFilledPolysList(l).Format()
                    for l in z.GetLayerSet().CuStack())):
            raise ValueError('priority_macro_cannot_change_source_pour_outline')
        if not z.IsFilled():raise ValueError('actual_native_priority_source_fill_required')
        # The uncut frame still has exact Source fills. Only fresh native
        # window replay may substitute a whole expected zone, matched to
        # the actual cut pose. All unrelated Source copper remains fixed.
        fixed.append(window_zones.get(force._uid(z),z))
    if len(fixed)>16384:raise ValueError('native_priority_source_inventory_bound')
    shapes={}
    for lid in layers:
        rows=[]
        for t in fixed:
            tick()
            if not t.IsOnLayer(lid):continue
            if t.GetClass()=='ZONE':
                if not t.HasFilledPolysForLayer(lid):continue
                shape=t.GetFilledPolysList(lid)
            else:shape=t.GetEffectiveShape(lid)
            rows.append((t,shape))
        shapes[lid]=rows
    incoming=[new[u] for u in sorted(changed) if new[u].GetClass()=='PCB_VIA']
    incoming.extend(new[u] for u in sorted(extension_ids))
    incoming.extend(p for u in owners for p in last[u].Pads())
    if len(incoming)>4096:raise ValueError('native_macro_moving_land_inventory_bound')
    resolver=fr._project_netclass_resolver(source.GetFileName())
    conflicts=[];queries=0
    for item in incoming:
        tick();net=str(item.GetNetname())
        gap=max(source.GetDesignSettings().m_MinClearance,
            math.ceil(float((resolver(net) or {}).get('clearance') or .2)*1e6))
        for lid in layers:
            if not item.IsOnLayer(lid):continue
            shape=item.GetEffectiveShape(lid)
            for retained,obstacle in shapes[lid]:
                tick()
                if str(retained.GetNetname())==net:continue
                queries+=1
                if not obstacle.Collide(shape,gap):continue
                if len(conflicts)>=max_conflicts:raise ValueError('native_macro_priority_conflict_inventory_bound')
                conflicts.append(dict(moved_uuid=force._uid(item),moved_kind=item.GetClass(),
                    moved_net=net,at_nm=list(item.GetPosition()),layer=candidate.GetLayerName(lid),layer_id=lid,
                    retained_priority_uuid=force._uid(retained),retained_kind=retained.GetClass(),
                    retained_net=str(retained.GetNetname()),clearance_nm=gap))
    return dict(schema=1,scope='all_enabled_face_source_priority_macro_proposal_filter',
        ok=not conflicts and not priority_motion,complete=True,conflicts=conflicts,
        moved_priority_source_conductor_uuids=priority_motion,
        source_owned_local_power_escape_extensions=extensions,
        source_owned_in_pad_vias_with_unchanged_full_width_access=unchanged_access,
        independently_typed_source_measurement_reconstruction=measurement_proofs,
        independently_typed_pending_full_current_reconstruction=pending,
        source_measurement_retirement_is_not_force_bus_retirement=bool(measurement_ids),
        rederived_local_power_owner_barrels=[local_vias[u] for u in sorted(extended_vias|enclosed_vias)],
        saved_current_receiving_required=bool(allowed),
        protected_nets=sorted(priority),positive_board_design_basis_nets=sorted(basis),
        existing_native_pour_owned_nets=sorted(pour_owned),native_shape_queries=queries,
        moving_land_or_barrel_count=len(incoming),
        zero_conductor_motion_receiving=zero_motion_receiving,
        independently_replayed_carried_Ground_via_antipads=window_proof,
        all_enabled_native_layer_ids=list(layers),
        priority_copper_reconstruction_not_authorized=True,
        source_current_reduced=False,source_mutated=False,candidate_mutated=False,
        current_or_clearance_qualified=False,routing_admitted=False,release_authority=False)
