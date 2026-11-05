"""Constructive debts for retained Ground fragments after a typed cell cut.

An immediate return for a moving part does not restore a stationary fork.
Use native source/posed partitions, not ref names or nearby same-net items.
This helper proposes full-class local return links only; it grants no rip-up,
barrel/plane current rating, rule change or saved-board admission authority.
"""
import hashlib
import json
import time
import pcbnew
import cec_cell_row_rebuild as row
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_fr as fr


def _items(board,deadline=None):
    import cec_native_zone_islands as islands
    deadline=time.monotonic()+10. if deadline is None else deadline
    items=[p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname()=='GND']
    items += [t for t in board.GetTracks() if t.GetNetname()=='GND']
    for zone in board.Zones():
        if not zone.GetIsRuleArea() and zone.GetNetname()=='GND':
            items += islands.decompose(board,zone,deadline=deadline)
    if len(items)>16384:raise ValueError('ground_cut_boundary_native_inventory_bound')
    return items


def _parts(items,deadline,key):
    conn=pcbnew.CONNECTIVITY_DATA();remaining={key(i):i for i in items}
    if len(remaining)!=len(items):raise ValueError('ground_cut_boundary_ambiguous_native_identity')
    for item in items:
        if time.monotonic()>=deadline:raise ValueError('ground_cut_boundary_native_deadline')
        if not conn.Add(item):raise ValueError('ground_cut_boundary_native_item_refused')
    parts=[]
    while remaining:
        if time.monotonic()>=deadline:raise ValueError('ground_cut_boundary_native_deadline')
        seed=min(remaining);reached={seed}|{key(i) for i in conn.GetConnectedItems(remaining[seed])}
        own=set(remaining)&reached;parts.append(own)
        for k in own:del remaining[k]
    return parts


def _pad_id(p):
    return p.GetParentFootprint().GetReference(),str(p.GetNumber()),force._uid(p)


def _transported_barrel_keys(source,posed,proofs,deadline,*,allow_octilinear_rotations=False,
                             source_proposal=None):
    """Same physical barrel identity after its exact source-owner transform.

    This is a comparison-key map, not permission to move or cut copper.
    Every barrel must retain all native dimensions, layers and grouping and
    re-prove its old and new local process ownership on the SAME SMD pad.
    """
    import cec_fab_profile as fab
    if (type(proofs) not in (list,tuple) or len(proofs)>16
            or type(allow_octilinear_rotations) is not bool
            or source_proposal is not None and type(source_proposal) is not dict):
        raise ValueError('bounded_transported_ground_barrel_proofs_required')
    old={force._uid(t):t for t in source.GetTracks()}
    new={force._uid(t):t for t in posed.GetTracks()}
    old_pads={force._uid(p):p for fp in source.GetFootprints() for p in fp.Pads()}
    new_pads={force._uid(p):p for fp in posed.GetFootprints() for p in fp.Pads()}
    layers=tuple(map(int,source.GetEnabledLayers().CuStack()))
    if layers!=tuple(map(int,posed.GetEnabledLayers().CuStack())):
        raise ValueError('transported_ground_barrel_stack_changed')
    # Only literal identity requests cross this boundary. Producer role/cut
    # dictionaries are NOT authority: rederive the complete canonical rows
    # once, within this consumer's inherited lease, then compare strict JSON.
    axes={}
    if source_proposal is not None:
        records=[q['source_control_shunt_return_axis'] for q in proofs
            if type(q) is dict and 'source_control_shunt_return_axis' in q]
        if records:
            if (source_proposal.get('scope')!='source_typed_complete_cell_escape_proposal'
                    or source_proposal.get('source_native_binding')!=row._source_binding(source)
                    or any(type(q) is not dict or type(q.get('owner_pad_uuid')) is not str
                        or type(q.get('position_nm')) is not list for q in records)):
                raise ValueError('exact_source_explicit_ground_axis_context_required')
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ValueError('transported_ground_barrel_identity_deadline')
            import cec_control_shunt_ground_return_axes as axis_owner
            derived=axis_owner.derive(source,posed,source_proposal,
                [dict(owner_pad_uuid=q['owner_pad_uuid'],position_nm=list(q['position_nm']))
                    for q in records],timeout_s=min(10.,remaining))
            def strict(value):
                try:return json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':'))
                except (TypeError,ValueError) as exc:
                    raise ValueError('literal_canonical_ground_axis_record_required') from exc
            if len(derived)!=len(records) or any(strict(a)!=strict(b) for a,b in zip(derived,records)):
                raise ValueError('fresh_canonical_ground_axis_record_required')
            if any(q.get('uuid')!=q['source_control_shunt_return_axis'].get('uuid')
                    for q in proofs if type(q) is dict and 'source_control_shunt_return_axis' in q):
                raise ValueError('same_physical_canonical_ground_axis_required')
            axes={q['uuid']:q for q in derived}
            if len(axes)!=len(derived):raise ValueError('unique_canonical_ground_axis_required')
    def signature(board,via):
        return (via.GetClass(),str(via.GetNetname()),int(via.GetViaType()),
            via.GetDrillValue(),int(via.TopLayer()),int(via.BottomLayer()),bool(via.IsLocked()),
            tuple((l,via.GetWidth(l)) for l in layers),
            tuple(sorted((force._uid(g),g.GetName(),bool(g.IsLocked()))
                for g in board.Groups() if g.ContainsItem(via))))
    result={};seen=set()
    for proof in proofs:
        if time.monotonic()>=deadline:raise ValueError('transported_ground_barrel_identity_deadline')
        uid=proof.get('uuid') if type(proof) is dict else None
        if (uid in seen or uid not in old or uid not in new or
                old[uid].GetClass()!='PCB_VIA' or old[uid].GetNetname()!='GND'):
            raise ValueError('unique_actual_source_ground_barrel_required')
        seen.add(uid);a,b=old[uid],new[uid]
        old_process,new_process=fab.local_pofv_via_decision(source,a),fab.local_pofv_via_decision(posed,b)
        if (signature(source,a)!=signature(posed,b) or not old_process[0] or not new_process[0]):
            raise ValueError('transported_ground_barrel_native_process_or_dimensions_changed:'+uid+
                ':source='+str(old_process)+':posed='+str(new_process))
        owners=proof.get('source_owner_pad_uuids',[])
        if not owners or not set(owners)<=old_pads.keys() or not set(owners)<=new_pads.keys():
            raise ValueError('literal_transported_ground_barrel_owner_required')
        axis=axes.get(uid)
        if axis is not None:
            owner=axis['owner_pad_uuid'];pad=old_pads.get(owner)
            if (owners!=[owner] or pad is None
                    or proof.get('owner_footprint_uuids')!=[force._uid(pad.GetParentFootprint())]
                    or proof.get('actual_source_ownership_basis')!='bounded_native_smd_dogbone'
                    or proof.get('original_barrel_geometry_count_and_relative_owner_seat_preserved') is not False
                    or proof.get('original_barrel_geometry_and_count_preserved') is not True
                    or proof.get('source_control_shunt_return_axis') is not None
                        and strict(proof['source_control_shunt_return_axis'])!=strict(axis)
                    or list(b.GetPosition())!=axis['position_nm']):
                raise ValueError('exact_canonical_ground_axis_native_identity_required')
        received=False
        for owner in owners:
            p,q=old_pads[owner],new_pads[owner];fp,after=p.GetParentFootprint(),q.GetParentFootprint()
            if (p.GetNetname()!='GND' or q.GetNetname()!='GND'
                    or force._uid(fp)!=force._uid(after) or p.GetNumber()!=q.GetNumber()
                    or p.HasHole() or q.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                    or q.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or tuple(p.GetSize())!=tuple(q.GetSize())
                    or p.GetShape()!=q.GetShape() or tuple(p.GetOffset())!=tuple(q.GetOffset())
                    or p.GetRoundRectRadiusRatio()!=q.GetRoundRectRadiusRatio()
                    or tuple(p.GetLayerSet().Seq())!=tuple(q.GetLayerSet().Seq())
                    or fp.IsFlipped()!=after.IsFlipped()):continue
            turn=(after.GetOrientationDegrees()-fp.GetOrientationDegrees())%360
            if turn not in range(0,360,45 if allow_octilinear_rotations else 90):continue
            angle=pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T)
            delta=after.GetPosition()-fp.GetPosition()
            expected=a.Duplicate();expected.Rotate(fp.GetPosition(),angle);expected.Move(delta)
            if axis is None:
                if tuple(b.GetPosition())!=tuple(expected.GetPosition()):continue
            else:
                target=source_proposal['poses'].get(fp.GetReference())
                expected_pad=p.Duplicate();expected_pad.Rotate(fp.GetPosition(),angle);expected_pad.Move(delta)
                if (target is None or tuple(after.GetPosition())!=tuple(round(v*1e6) for v in target[:2])
                        or abs((after.GetOrientationDegrees()-target[2]+180)%360-180)>1e-9
                        or tuple(q.GetPosition())!=tuple(expected_pad.GetPosition())):continue
            # A claimed pad UUID is not ownership. The actual full land or
            # source dogbone must name this same pad in both native boards.
            def owns(board,pad,via):
                face=cells.cec_return_escape.smd_surface_layer(pad)
                if face is None:return False
                poly=pcbnew.SHAPE_POLY_SET()
                via.TransformShapeToPolygon(poly,face,0,1,pcbnew.ERROR_OUTSIDE)
                poly.BooleanSubtract(pad.GetEffectivePolygon(face,pcbnew.ERROR_INSIDE))
                if not poly.OutlineCount():return True
                return any(t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND'
                    and any(tuple(v)==tuple(via.GetPosition()) and
                        fab.local_pofv_dogbone_matches(pad,u,v,face,via.GetNetCode())
                        for u,v in ((t.GetStart(),t.GetEnd()),(t.GetEnd(),t.GetStart())))
                    for t in board.GetTracks() if t.IsOnLayer(face))
            if owns(source,p,a) and owns(posed,q,b):received=True;break
        if not received:raise ValueError('exact_same_source_ground_owner_transform_not_received')
        result[force._item_key(b)]=force._item_key(a)
        if axis is not None:
            # One exclusive Source pickup keeps its PHYSICAL UUID, class,
            # face, locks and groups. Only the freshly canonical shorter
            # axis replaces the old rigid endpoint expectation.
            tid=axis['source_tail_uuid'];t=old.get(tid);after_track=new.get(tid)
            def groups(board,item):
                return sorted((force._uid(g),g.GetName(),bool(g.IsLocked()))
                    for g in board.Groups() if g.ContainsItem(item))
            if (t is None or after_track is None or t.GetClass()!='PCB_TRACK'
                    or after_track.GetClass()!='PCB_TRACK' or t.GetNetname()!='GND'
                    or after_track.GetNetname()!='GND' or t.GetWidth()!=axis['source_full_width_nm']
                    or after_track.GetWidth()!=t.GetWidth() or after_track.GetLayer()!=t.GetLayer()
                    or after_track.IsLocked()!=t.IsLocked() or after_track.HasSolderMask()!=t.HasSolderMask()
                    or groups(source,t)!=groups(posed,after_track)):
                raise ValueError('canonical_ground_axis_tail_metadata_changed')
            import cec_route_quality as quality
            if (not quality.is_canonical_stroke(tuple(after_track.GetStart()),tuple(after_track.GetEnd()))
                    or not 0<after_track.GetLength()<=axis['maximum_return_nm']
                    or not after_track.GetLength()+10000<t.GetLength()
                    or not any(tuple(v)==tuple(b.GetPosition()) and fab.local_pofv_dogbone_matches(
                        q,u,v,t.GetLayer(),b.GetNetCode()) for u,v in
                        ((after_track.GetStart(),after_track.GetEnd()),(after_track.GetEnd(),after_track.GetStart())))):
                raise ValueError('canonical_ground_axis_actual_shorter_dogbone_not_received')
            result[force._item_key(after_track)]=force._item_key(t)
            continue
        # An exact rigid source dogbone may accompany its barrel. It is
        # retained native copper, not a new restoration edge or width waiver.
        for key,t in old.items():
            if (t.GetClass()!='PCB_TRACK' or t.GetNetname()!='GND' or key not in new):continue
            after_track=new[key]
            if not any(tuple(v)==tuple(a.GetPosition()) and fab.local_pofv_dogbone_matches(
                    p,u,v,t.GetLayer(),a.GetNetCode()) for u,v in
                    ((t.GetStart(),t.GetEnd()),(t.GetEnd(),t.GetStart()))):continue
            if (after_track.GetClass()!='PCB_TRACK' or after_track.GetNetname()!='GND'
                    or after_track.GetWidth()!=t.GetWidth() or after_track.GetLayer()!=t.GetLayer()
                    or after_track.IsLocked()!=t.IsLocked() or after_track.HasSolderMask()!=t.HasSolderMask()
                    or tuple(sorted(force._uid(g) for g in source.Groups() if g.ContainsItem(t)))
                    !=tuple(sorted(force._uid(g) for g in posed.Groups() if g.ContainsItem(after_track)))):
                raise ValueError('transported_ground_dogbone_dimensions_or_groups_changed')
            expected_track=t.Duplicate();expected_track.Rotate(fp.GetPosition(),angle);expected_track.Move(delta)
            if (tuple(after_track.GetStart())!=tuple(expected_track.GetStart())
                    or tuple(after_track.GetEnd())!=tuple(expected_track.GetEnd())
                    or not any(tuple(v)==tuple(b.GetPosition()) and fab.local_pofv_dogbone_matches(
                        q,u,v,t.GetLayer(),b.GetNetCode()) for u,v in
                        ((after_track.GetStart(),after_track.GetEnd()),(after_track.GetEnd(),after_track.GetStart())))):
                raise ValueError('exact_source_ground_dogbone_transform_not_received')
            result[force._item_key(after_track)]=force._item_key(t)
    return result


def requests(source,posed,proposal,*,timeout_s=10.,transported_source_barrels=(),
             additional_source_ground_cut_rows=()):
    if (type(timeout_s) not in (int,float) or not 0<timeout_s<=10.
            or row._source_binding(source)!=proposal['source_native_binding']):
        raise ValueError('exact_bounded_source_ground_cut_context_required')
    deadline=time.monotonic()+timeout_s;retired=set(proposal['retired_track_uuids'])
    cut=[t for t in source.GetTracks() if force._uid(t) in retired and t.GetNetname()=='GND']
    if not cut:return {}
    if len(cut)>64 or any(t.GetClass()!='PCB_TRACK' or not 0<t.GetWidth() for t in cut):
        raise ValueError('bounded_source_owned_small_ground_cut_required')
    # Establish actual old/new process, dimensions, group, SAME pad ownership
    # and rigid transform BEFORE using a transported barrel as a cut root.
    # An inner-layer source edge touches that barrel, not its surface pad;
    # discarding this context falsely labels it an unowned Ground trunk.
    barrel_mapping=_transported_barrel_keys(source,posed,transported_source_barrels,deadline,
        allow_octilinear_rotations=proposal.get('allow_octilinear_rotations',False),source_proposal=proposal)
    continuations={}
    if additional_source_ground_cut_rows:
        import cec_source_ground_continuation as continuation
        import cec_cell_escape_replan as escape
        selected=[q for q in additional_source_ground_cut_rows
            if q.get('authority',{}).get('kind')==continuation.KIND]
        roots=[q for q in additional_source_ground_cut_rows
            if q.get('authority',{}).get('kind')=='positive_existing_low_power_ground_boundary']
        if selected:
            ids=[q['change']['uuid']for q in selected]
            if len(set(ids))!=len(ids)or not set(ids)<=retired:
                raise ValueError('exact_retired_source_ground_continuations_required')
            # The enclosing macro's cut includes independently owned extras;
            # freshly recover the ORIGINAL Source proposal before rederiving
            # their separate authority. Never call a continuation a pad leg.
            original=escape.recompile_source_proposal(source,proposal)
            work={json.dumps(q['authority']['source_ground_continuation']['source_work_bounds'],sort_keys=True)
                for q in selected}
            if len(work)!=1:raise ValueError('one_exact_ground_continuation_source_work_context_required')
            fresh=continuation.ownership(source,posed,source.GetFileName(),original,ids,
                existing_ground_cut_rows=roots,deadline=deadline,
                **json.loads(next(iter(work))))
            stable=lambda value:json.loads(json.dumps(value,allow_nan=False))
            if sorted(map(stable,fresh),key=lambda q:q['change']['uuid'])!=sorted(
                    map(stable,selected),key=lambda q:q['change']['uuid']):
                raise ValueError('fresh_complete_source_ground_continuation_receiving_required')
            continuations={q['change']['uuid']:q['authority']for q in fresh}
    # Rederive one complete additional-cap Source context for its exact
    # retired leaves. Do not classify these passives as low-power device
    # terminals or add the new role to legacy trunk/continuation whitelists.
    additional_leaf_ids={u for p in proposal.get('additional_aggregate_capacitors',{}).values()
        if p.get('source_Ground_leaf') is not None for u in p['source_Ground_leaf']['track_uuids']}
    additional_cut=sorted(additional_leaf_ids & {force._uid(t) for t in cut})
    additional_authorities={}
    if additional_cut:
        import cec_aggregate_cap_ground_leaf as additional
        derived=additional.single_edge_ownerships(source,proposal,additional_cut,deadline=deadline)
        additional_authorities={q['change']['uuid']:q['authority'] for q in derived}
        if set(additional_authorities)!=set(additional_cut) or any(
                not additional.authority_label(q) for q in additional_authorities.values()):
            raise ValueError('fresh_exact_additional_cap_Ground_leaf_authority_required')
    complete_ground_typer=None
    ground_transport={'source_process_barrel_motion':list(transported_source_barrels)}
    for edge in cut:
        if edge.GetWidth()<=350000:continue
        # Wider existing class-width Ground legs need their own positive
        # source terminal ownership, not a blanket Ground/trunk cut waiver.
        import cec_cell_macro_requests as compiler
        proof=additional_authorities.get(force._uid(edge),continuations.get(force._uid(edge)))
        if proof is None:
            if complete_ground_typer is None:
                complete_ground_typer=compiler._complete_ground_boundary_typer(source,ground_transport,proposal,deadline)
            proof=complete_ground_typer(edge)
        if edge.GetWidth()>proof['source_full_class_width_nm']:
            raise ValueError('ground_cut_exceeds_literal_source_class_width')
    old=_items(source,deadline);live=_items(posed,deadline)
    old_by_key={force._item_key(i):i for i in old};old_pads={_pad_id(i):i for i in old if i.GetClass()=='PAD'}
    new_pads={_pad_id(i):i for i in live if i.GetClass()=='PAD'}
    if old_pads.keys()!=new_pads.keys():raise ValueError('ground_cut_boundary_terminal_population_changed')
    mapping={force._item_key(new_pads[k]):force._item_key(v) for k,v in old_pads.items()}
    mapping.update(barrel_mapping)
    key=lambda i:mapping.get(force._item_key(i),force._item_key(i))
    old_parts=_parts(old,deadline,force._item_key);new_parts=_parts(live,deadline,key)
    original={k:n for n,part in enumerate(old_parts) for k in part}
    affected={original[force._item_key(t)] for t in cut}
    moving_refs={ref for ref,target in proposal['poses'].items()
        if (tuple(source.FindFootprintByReference(ref).GetPosition())!=tuple(round(v*1e6) for v in target[:2])
            or abs((source.FindFootprintByReference(ref).GetOrientationDegrees()-target[2]+180)%360-180)>1e-9)}
    moved={force._item_key(p) for k,p in old_pads.items()
        if p.GetParentFootprint().GetReference() in moving_refs}
    # Every emitted link ends at a real currently moving Ground terminal.
    # The existing cell ground obligations still own its actual qualified
    # return/root and dependency-cycle checks.
    portals={k:new_pads[_pad_id(old_by_key[k])] for k in moved}
    planes={source.GetLayerID(n) for n in fr.plane_layers(source)}
    live_by_key={key(i):i for i in live};expected=set(old_by_key)-{force._item_key(t) for t in cut}
    if set(live_by_key)!=expected:raise ValueError('ground_cut_boundary_exact_source_minus_cut_required')
    result={}
    for part in new_parts:
        owners={original[k] for k in part}
        if len(owners)!=1:raise ValueError('posed_ground_contact_merged_distinct_source_components')
        owner=next(iter(owners))
        if owner not in affected or part&moved:continue
        actual_planes={l for k in part for l in live_by_key[k].GetLayerSet().CuStack()
            if live_by_key[k].GetClass()=='ZONE' and l in planes}
        if len(actual_planes)>=2:continue
        possible=[(k,p) for k,p in portals.items() if original[k]==owner]
        if not possible:
            raise ValueError('retained_ground_fragment_has_no_source_related_moving_entry')
        choices=[]
        for k in part:
            item=live_by_key[k];faces=list(map(int,item.GetLayerSet().CuStack()))
            if item.GetClass()=='PAD':
                sites=[dict(pad_uuid=force._uid(item),at_nm=list(item.GetPosition()),layers=faces)]
            elif item.GetClass() in ('PCB_TRACK','PCB_VIA'):
                points={tuple(item.GetPosition())} if item.GetClass()=='PCB_VIA' else {
                    tuple(item.GetStart()),tuple(item.GetEnd())}
                sites=[dict(at_nm=list(at),layers=faces,native_uuids=[force._uid(item)]) for at in sorted(points)]
            else:
                # Never guess a filled polygon attachment or acquire a
                # whole same-net island by its ZONE owner alone.
                continue
            for portal_key,pad in possible:
                for site in sites:
                    a=list(pad.GetPosition());b=site['at_nm']
                    choices.append((sum((x-y)**2 for x,y in zip(a,b)),repr(k),portal_key,pad,site))
        if not choices:raise ValueError('retained_ground_fragment_has_no_literal_native_attachment')
        _,_,portal_key,pad,end=min(choices,key=lambda q:(q[0],q[1],q[2]))
        fingerprint=hashlib.sha256(repr(sorted(part)).encode()).hexdigest()[:24]
        width=max(source.GetDesignSettings().m_TrackMinWidth,int(cells._netclass(source,'GND')['width']),
            max(t.GetWidth() for t in cut))
        result['ground_retained_boundary:'+fingerprint]=dict(kind='ground_boundary',net='GND',
            a=dict(pad_uuid=force._uid(pad),at_nm=list(pad.GetPosition()),
                layers=list(map(int,pad.GetLayerSet().CuStack()))),b=end,width_nm=int(width),
            retained_source_ground_fragment=dict(source_native_binding=proposal['source_native_binding'],
                original_source_component_keys=[list(k) for k in sorted(old_parts[owner])],
                retained_fragment_keys=[list(k) for k in sorted(part)],
                retired_ground_track_uuids=sorted(force._uid(t) for t in cut),
                moving_entry_source_key=list(portal_key),
                actual_fixed_source_contacts_not_same_net_proximity=True,
                low_power_source_cut_restoration_not_aggregate_ground_rating=True,
                whole_original_current_plane_and_saved_partition_receiving_required=True))
    if time.monotonic()>=deadline:raise ValueError('ground_cut_boundary_native_deadline')
    return result
