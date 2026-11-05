"""Bounded surface shortcuts to literal, unchanged source GND barrels.

No new/moved hole, source conductor cut, pad/pose/rule edit, inferred bypass
role or new current capacity. An already-connected source surface terminal
must gain a strictly shorter proved return witness to a real filled reference
entry. Target reuse is NOT new-via placement or fabrication qualification.
All saved parent/current/native/field/clipped-cut gates still own admission.
"""
import argparse,json,math,tempfile,time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_ground_span_reflow as lease
import cec_ordinary_route_receiving as ordinary
import cec_route_quality as quality
import cec_search_budget as budget
import cec_sensitive_scalar_path_reflow as geometry
from cec_native_items import discard_items


def _reference_contacts(board,via):
    profile=fab.get_profile(fab.board_profile_name(board))
    if not profile:raise ValueError('declared_ground_reference_profile_required')
    faces={int(board.GetLayerID(n)) for n,r in zip(fab.COPPER_LAYERS,profile['roles']) if r=='GND'}
    if not faces:raise ValueError('declared_ground_reference_faces_required')
    actual=[]
    for zone in board.Zones():
        if zone.GetIsRuleArea() or zone.GetNetname()!='GND':continue
        for face in sorted(faces):
            if (zone.IsFilled() and zone.IsOnLayer(face) and via.IsOnLayer(face)
                    and zone.HasFilledPolysForLayer(face)
                    and zone.GetFilledPolysList(face).Collide(via.GetEffectiveShape(face),0)):
                actual.append([force._uid(zone),face])
    if {v[1] for v in actual}!=faces:raise ValueError('actual_saved_contact_to_each_declared_ground_reference_required')
    return actual


def _context(board,pad_uuid,target_via_uuid):
    if sum(fp.GetPadCount() for fp in board.GetFootprints())+len(list(board.GetTracks()))>16384:
        raise ValueError('ground_shortcut_native_inventory_bound')
    pads=[p for fp in board.GetFootprints() for p in fp.Pads() if force._uid(p)==pad_uuid]
    vias=[v for v in board.GetTracks() if force._uid(v)==target_via_uuid]
    if len(pads)!=1 or len(vias)!=1:raise ValueError('literal_source_pad_and_barrel_required')
    pad,via=pads[0],vias[0];face=cells.cec_return_escape.smd_surface_layer(pad)
    if (face is None or pad.GetNetname()!='GND' or pad.GetNetCode()<=0 or pad.HasHole()
            or pad.GetParentFootprint().IsDNP() or via.GetClass()!='PCB_VIA' or via.GetNetCode()!=pad.GetNetCode()
            or via.GetViaType()!=pcbnew.VIATYPE_THROUGH or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu):
        raise ValueError('populated_source_surface_ground_and_existing_through_barrel_required')
    contacts=_reference_contacts(board,via)
    graph=fr._read_only_route_connectivity(board)
    if target_via_uuid not in {force._uid(i) for i in graph.GetConnectedItems(pad)}:
        raise ValueError('source_ground_pad_and_reference_barrel_must_already_be_connected')
    return pad,via,int(face),contacts


def _new_surface_material(board,points,face,deadline):
    """Require real full-class copper outside the OUTSIDE Source envelope.

    A covered centreline may still add a real full-width corner. Derive the
    width from Source, use inward incoming/outward retained polygons, and
    remove actual bores before deciding novelty. This is a conservative
    duplicate screen, never an impedance/current or new-hole certificate.
    """
    old=pcbnew.SHAPE_POLY_SET()
    items=[*board.GetTracks(),*(p for fp in board.GetFootprints() for p in fp.Pads())]
    for item in items:
        if time.monotonic()>=deadline:raise ValueError('ground_shortcut_source_sheet_deadline')
        if item.GetNetname()!='GND' or not item.IsOnLayer(face):continue
        part=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(part,face,0,1000,pcbnew.ERROR_OUTSIDE)
        old.BooleanAdd(part)
    for zone in board.Zones():
        if time.monotonic()>=deadline:raise ValueError('ground_shortcut_source_sheet_deadline')
        if zone.GetIsRuleArea() or zone.GetNetname()!='GND' or not zone.IsOnLayer(face):continue
        if not zone.IsFilled() or not zone.HasFilledPolysForLayer(face):
            raise ValueError('ground_shortcut_existing_surface_fill_unknown')
        old.BooleanAdd(zone.GetFilledPolysList(face))
    spec=cells._netclass(board,'GND')
    width=max(int(board.GetDesignSettings().m_TrackMinWidth),int(spec['width']),200000)
    incoming=pcbnew.SHAPE_POLY_SET()
    for a,b in zip(points,points[1:]):
        if time.monotonic()>=deadline:raise ValueError('ground_shortcut_source_sheet_deadline')
        edge=pcbnew.PCB_TRACK(board);edge.SetLayer(face)
        edge.SetStart(pcbnew.VECTOR2I(*a));edge.SetEnd(pcbnew.VECTOR2I(*b));edge.SetWidth(width)
        part=pcbnew.SHAPE_POLY_SET();edge.TransformShapeToPolygon(part,face,0,1,pcbnew.ERROR_INSIDE);incoming.BooleanAdd(part)
    # A trace glyph over a drilled void is not new metal. Include all actual
    # through-pad bores (even NPTHs without a copper-layer membership), and
    # only the actual layer span of a via. Never infer a clearance window.
    holes=[p for fp in board.GetFootprints()for p in fp.Pads()if p.HasHole()]
    holes += [v for v in board.GetTracks()if v.GetClass()=='PCB_VIA'and v.IsOnLayer(face)]
    for item in holes:
        if time.monotonic()>=deadline:raise ValueError('ground_shortcut_source_sheet_deadline')
        shape=(pcbnew.SHAPE_CIRCLE(item.GetPosition(),(int(item.GetDrillValue())+1)//2)
            if item.GetClass()=='PCB_VIA'else item.GetEffectiveHoleShape())
        if shape is None:raise ValueError('ground_shortcut_actual_bore_shape_required')
        bore=pcbnew.SHAPE_POLY_SET();shape.TransformToPolygon(bore,1,pcbnew.ERROR_OUTSIDE)
        incoming.BooleanSubtract(bore)
    incoming.BooleanSubtract(old)
    if not incoming.OutlineCount():raise ValueError('ground_shortcut_path_already_covered_by_source_copper')


def _unbranched_departure_tracks(board,pad,face):
    """Do not turn local reflow into an added parallel triangle/loop.

    Walk only literal endpoint-linear Ground until another real terminal,
    barrel, plane or native branch. This is an exclusion from additive
    shortcuts, never authority to cut or move the observed material.
    """
    tracks=[t for t in board.GetTracks() if t.GetNetname()=='GND' and t.IsOnLayer(face)]
    # Ground lands of the SAME native package are part of its local web,
    # not a foreign consumer that legitimizes a new parallel triangle.
    # Keep walking through those literal terminal contacts until a real
    # external owner, barrel, plane or branching conductor is reached.
    owner=force._uid(pad.GetParentFootprint())
    pads=[p for f in board.GetFootprints() for p in f.Pads()
        if force._uid(f)!=owner and p.GetNetname()=='GND' and p.IsOnLayer(face)]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()=='GND' and z.IsOnLayer(face)]
    first=[t for t in tracks if t.GetEffectiveShape(face).Collide(pad.GetEffectiveShape(face),0)]
    if len(first)!=1:return set()
    current=first[0];point=tuple(pad.GetPosition());visited=set()
    for _ in range(8):
        if current.GetClass()!='PCB_TRACK':break
        ends=(tuple(current.GetStart()),tuple(current.GetEnd()))
        if point not in ends or ends[0]==ends[1]:break
        uid=force._uid(current)
        if uid in visited:break
        visited.add(uid);shape=current.GetEffectiveShape(face)
        if any(shape.Collide(p.GetEffectiveShape(face),0) for p in pads):break
        if any((z.IsFilled() and z.HasFilledPolysForLayer(face)
                and z.GetFilledPolysList(face).Collide(shape,0)) for z in zones):break
        far=ends[1] if point==ends[0] else ends[0]
        peers=[t for t in tracks if force._uid(t) not in visited
            and t.GetEffectiveShape(face).Collide(shape,0)]
        if len(peers)!=1 or peers[0].GetClass()!='PCB_TRACK':break
        if far not in (tuple(peers[0].GetStart()),tuple(peers[0].GetEnd())):break
        current,point=peers[0],far
    return visited


def _track_entry(board, pad, face, track_uuid, point):
    """A literal centreline tap, not a nearest-net or bounding-box seed."""
    if type(track_uuid) is not str or not track_uuid:
        raise ValueError('literal_existing_ground_track_identity_required')
    tracks=[t for t in board.GetTracks() if force._uid(t)==track_uuid]
    if len(tracks)!=1:
        raise ValueError('one_existing_ground_track_entry_required')
    track=tracks[0]
    if (track.GetClass()!='PCB_TRACK' or track.GetNetname()!='GND'
            or track.GetNetCode()!=pad.GetNetCode() or track.GetLayer()!=face):
        raise ValueError('same_surface_native_ground_track_entry_required')
    if track_uuid in _unbranched_departure_tracks(board,pad,face):
        raise ValueError('source_unbranched_ground_departure_needs_reflow_not_parallel_chord')
    a,b=tuple(track.GetStart()),tuple(track.GetEnd())
    vector=(b[0]-a[0],b[1]-a[1]);offset=(point[0]-a[0],point[1]-a[1])
    if (a==b or offset[0]*vector[1]!=offset[1]*vector[0]
            or not 0<=sum(x*y for x,y in zip(offset,vector))<=sum(x*x for x in vector)
            or not track.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*point),0)):
        raise ValueError('exact_saved_ground_track_centreline_entry_required')
    graph=fr._read_only_route_connectivity(board)
    if track_uuid not in {force._uid(i) for i in graph.GetConnectedItems(pad)}:
        raise ValueError('source_ground_track_entry_must_already_be_connected')
    return dict(uuid=track_uuid,at_nm=list(point),source_start_nm=list(a),source_end_nm=list(b),
        width_nm=int(track.GetWidth()),layer_id=int(face),source_unchanged=True,
        saved_whole_return_gain_still_required=True)


def plan(source,*,board_hint,pad_uuid,target_via_uuid,points_nm,timeout_s=10.,target_track_uuid=None):
    deadline=lease._deadline(timeout_s)
    if any(type(v) is not str or not v for v in (board_hint,pad_uuid,target_via_uuid)):
        raise ValueError('explicit_source_ground_shortcut_identity_required')
    points=geometry._points(points_nm);source=Path(source).resolve();digest=force._hash(source)
    board=pcbnew.LoadBoard(str(source));pad,via,face,contacts=_context(board,pad_uuid,target_via_uuid)
    if points[0]!=tuple(pad.GetPosition()):
        raise ValueError('literal_unchanged_ground_pad_and_barrel_ports_required')
    entry=None
    if target_track_uuid is not None:
        entry=_track_entry(board,pad,face,target_track_uuid,points[-1])
    elif points[-1]!=tuple(via.GetPosition()):
        raise ValueError('literal_unchanged_ground_pad_and_barrel_ports_required')
    else:
        local=_unbranched_departure_tracks(board,pad,face)
        if any(force._uid(t) in local and t.GetEffectiveShape(face).Collide(
                via.GetEffectiveShape(face),0) for t in board.GetTracks()):
            raise ValueError('source_unbranched_ground_departure_needs_reflow_not_parallel_chord')
    before=cells._existing_return(board,pad,16.,allow_native_track_body=True)
    length=sum(math.dist(a,b) for a,b in zip(points,points[1:]))/1e6
    if before is None or not .01<length<before[0]-.01:
        raise ValueError('strict_source_proved_ground_return_witness_gain_required')
    spec=cells._netclass(board,'GND');width=max(int(board.GetDesignSettings().m_TrackMinWidth),int(spec['width']),200000)
    gap=max(int(board.GetDesignSettings().m_MinClearance),int(spec['clearance']),200000);cache={}
    for a,b in zip(points,points[1:]):
        if time.monotonic()>=deadline:raise ValueError('ground_shortcut_geometry_deadline')
        a,b=pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b)
        if (not fr._edge_leg_clear(board,a,b,(width+1)//2+gap)
                or not fr._tap_foreign_clear(board,a,b,width,face,gap,{pad.GetNetCode()},foreign_cache=cache)):
            raise ValueError('ground_shortcut_foreign_copper_or_edge_clearance')
    _new_surface_material(board,points,face,deadline)
    if force._hash(source)!=digest:raise ValueError('ground_shortcut_source_changed')
    result=dict(source=str(source),source_sha256=digest,board_hint=board_hint,pad_uuid=pad_uuid,
        target_via_uuid=target_via_uuid,points_nm=[list(p) for p in points],layer_id=face,width_nm=width,
        source_return_witness_mm=before[0],new_explicit_path_mm=length,
        actual_saved_ground_reference_contacts=contacts,source_barrel_never_replaced_or_moved=True,
        new_holes=0,manufacturer_bypass_role_inferred=False,current_or_fabrication_qualified=False,release_authority=False)
    if entry is not None:
        result.update(target_track_uuid=target_track_uuid,source_track_entry=entry,
            no_duplicate_path_from_native_body_entry_to_retained_reference_barrel=True)
    return result


def construct(proposal,*,incoming_uuids=None):
    params={k:proposal[k] for k in ('board_hint','pad_uuid','target_via_uuid','points_nm')}
    if 'target_track_uuid' in proposal:params['target_track_uuid']=proposal['target_track_uuid']
    if plan(proposal['source'],**params)!=proposal:raise ValueError('stale_or_forged_ground_shortcut_plan')
    count=len(proposal['points_nm'])-1
    if incoming_uuids is not None and (type(incoming_uuids) is not list or len(incoming_uuids)!=count
            or len(set(incoming_uuids))!=count or any(type(u) is not str or not u for u in incoming_uuids)):
        raise ValueError('exact_ground_shortcut_reconstruction_uuids_required')
    board=pcbnew.LoadBoard(proposal['source'])
    for i,(a,b) in enumerate(zip(proposal['points_nm'],proposal['points_nm'][1:])):
        item=pcbnew.PCB_TRACK(board);item.m_Uuid.Clone(pcbnew.KIID(incoming_uuids[i]) if incoming_uuids else pcbnew.KIID())
        item.SetNetCode(board.GetNetcodeFromNetname('GND'));item.SetLayer(proposal['layer_id']);item.SetWidth(proposal['width_nm'])
        item.SetStart(pcbnew.VECTOR2I(*a));item.SetEnd(pcbnew.VECTOR2I(*b));item.SetLocked(True);board.Add(item)
    return board


def receive(source,candidate,*,board_hint,pad_uuid,target_via_uuid,points_nm,timeout_s=10.,target_track_uuid=None):
    r=dict(ok=False,complete=False,errors=[],current_qualified=False,fab_ready=False,release_authority=False)
    try:
        deadline=lease._deadline(timeout_s);source,candidate=[Path(p).resolve() for p in (source,candidate)]
        if source==candidate:raise ValueError('distinct_source_and_saved_shortcut_candidate_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        q=plan(source,board_hint=board_hint,pad_uuid=pad_uuid,target_via_uuid=target_via_uuid,points_nm=points_nm,
            timeout_s=max(.001,deadline-time.monotonic()),target_track_uuid=target_track_uuid)
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        _,old=additive._nodes(source);_,new=additive._nodes(candidate);incoming=set(new)-set(old)
        if set(old)-set(new) or not 1<=len(incoming)==len(points_nm)-1<=15:
            raise ValueError('bounded_additive_track_only_ground_shortcut_required')
        tracks=[t for t in child.GetTracks() if force._uid(t) in incoming]
        ordered=[]
        for a,b in zip(q['points_nm'],q['points_nm'][1:]):
            match=[t for t in tracks if t.GetClass()=='PCB_TRACK' and list(t.GetStart())==a and list(t.GetEnd())==b]
            if len(match)!=1:raise ValueError('exact_source_requested_ground_shortcut_legs_required')
            ordered.append(force._uid(match[0]))
        with tempfile.TemporaryDirectory(prefix='cec-ground-shortcut-replay-') as work:
            import cec_additive_pair_repair as saved_additions
            expected=construct(q,incoming_uuids=ordered)
            replay=force._copy_family(source,Path(work)/'expected')
            # Native serialization can reorder pre-existing group members.
            # Reconstruct the actual additions/refill through the existing
            # literal Source-preserving producer, never normalize or waive
            # a comparison of the original Source objects.
            old_track_ids={force._uid(t)for t in parent.GetTracks()}
            saved_additions.save_native_additions(replay,expected,dict(created_uuids=ordered),
                old_track_ids,board_hint=board_hint)
            _,nodes=additive._nodes(replay)
            if ({u:syntax._freeze(v) for u,v in nodes.items()}!={u:syntax._freeze(v) for u,v in new.items()}
                    or force._sidecars(source)!=force._sidecars(candidate)):
                raise ValueError('ground_shortcut_child_differs_from_independent_full_source_replay')
        delta=additive.receive(source,candidate,board_hint=board_hint)
        if not delta['ok'] or not delta['complete']:raise ValueError('ground_shortcut_independent_additive_receiving_refused')
        ground=geometry._preserved_ground_material(parent,child,deadline)
        parts0=ordinary._partition(parent,deadline);keys=set().union(*parts0)
        parts1=ordinary._partition(child,deadline,retained_keys=keys)
        if {frozenset(v) for v in parts0}!={frozenset(v) for v in parts1}:
            raise ValueError('ground_shortcut_changed_existing_native_conductor_partition')
        pad=next(p for fp in child.GetFootprints() for p in fp.Pads() if force._uid(p)==pad_uuid)
        after=cells._existing_return(child,pad,16.,allow_native_track_body=True)
        if after is None or after[0]>=q['source_return_witness_mm']-.01:
            raise ValueError('saved_ground_shortcut_witness_did_not_improve')
        craft=[quality.analyze_board(b) for b in (parent,child)]
        if any(craft[1][k]>craft[0][k] for k in ('issue_count','non_octilinear_count')):
            raise ValueError('ground_shortcut_worsened_whole_native_trace_craft')
        if (time.monotonic()>=deadline or epoch!=force._code_identity()
                or families!=[force._family(p,board_hint) for p in (source,candidate)]):
            raise ValueError('ground_shortcut_family_code_or_receiving_lease_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            proposal=q,retired_track_uuids=[],added_native_uuids=ordered,modified_nets=['GND'],
            source_return_witness_mm=q['source_return_witness_mm'],saved_return_witness_mm=after[0],
            shortened_return_witness_mm=q['source_return_witness_mm']-after[0],
            native_ground_material_preservation=ground,every_source_native_partition_identical=True,
            independent_additive_receiving=delta,new_holes=0,all_source_barrels_pads_poses_rules_and_power_copper_retained=True,
            witness_is_not_a_global_shortest_path_or_immediate_return_certificate=True,
            whole_current_fields_uncapped_native_DRC_absolute_cuts_and_release_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def _native_track_entry_points(track, point):
    """Exact integer centreline events; no bbox or rounded off-line tap."""
    if track.GetClass()!='PCB_TRACK':return []
    a,b=tuple(track.GetStart()),tuple(track.GetEnd())
    dx,dy=b[0]-a[0],b[1]-a[1]
    if a==b or (dx and dy and abs(dx)!=abs(dy)):return []
    steps=math.gcd(abs(dx),abs(dy));ux,uy=dx//steps,dy//steps
    denominator=ux*ux+uy*uy
    numerator=(point[0]-a[0])*ux+(point[1]-a[1])*uy
    step=max(0,min(steps,(numerator+denominator//2)//denominator))
    nearest=(a[0]+step*ux,a[1]+step*uy)
    return sorted({nearest,a,b},key=lambda p:(math.dist(point,p),p))


def _source_track_targets(board,pad,face,via,reached,limit_mm,deadline):
    """Propose other real Ground trunks, never a parallel local chord.

    The source reference barrel is retained as an independently checked
    reference witness, NOT a request to duplicate its existing trunk. Every
    returned event still needs native route, actual saved full-return gain,
    whole-board craft, current, field, DRC and clipped-copper receiving.
    """
    excluded=_unbranched_departure_tracks(board,pad,face)
    start=tuple(pad.GetPosition());rows=[];seen=set()
    for track in board.GetTracks():
        if time.monotonic()>=deadline:break
        uid=force._uid(track)
        if (track.GetClass()!='PCB_TRACK' or track.GetLayer()!=face
                or track.GetNetCode()!=pad.GetNetCode() or uid not in reached or uid in excluded):continue
        for at in _native_track_entry_points(track,start):
            distance=math.dist(start,at)/1e6
            if not .01<distance<limit_mm-.01 or at in seen:continue
            seen.add(at);rows.append(dict(distance_mm=distance,target_via_uuid=force._uid(via),
                target_track_uuid=uid,at_nm=at))
    return sorted(rows,key=lambda r:(r['distance_mm'],r['target_track_uuid'],r['at_nm']))


def _trial_return_witness(board,pad,legs,old_mm):
    """Receive temporary WHOLE return cost before funding a saved offer.

    The proximity of another branch can be misleading: its real continuation
    may lead back along a longer route. This is only a disposable proposal
    filter; independently saved receiving is still required afterwards.
    """
    made=[]
    try:
        for a,b,width in legs:
            item=pcbnew.PCB_TRACK(board);item.SetNetCode(pad.GetNetCode())
            item.SetLayer(cells._ground_terminal_layer(pad));item.SetWidth(int(width))
            item.SetStart(a);item.SetEnd(b);board.Add(item);made.append(item)
        value=cells._existing_return(board,pad,old_mm,allow_native_track_body=True)
        return None if value is None else value[0]
    finally:
        discard_items(board,made)


def discover(source,*,board_hint,maximum_pads=8,maximum_targets=12,minimum_return_mm=3.,timeout_s=10.,
             include_track_entries=True,cohort_offset=0):
    deadline=lease._deadline(timeout_s)
    if (type(maximum_pads) is not int or not 1<=maximum_pads<=8 or type(maximum_targets) is not int
            or not 1<=maximum_targets<=24 or type(minimum_return_mm) not in (int,float)
            or not math.isfinite(minimum_return_mm) or not 0<minimum_return_mm<=16
            or type(include_track_entries) is not bool or type(cohort_offset) is not int
            or not 0<=cohort_offset<=2048):
        raise ValueError('bounded_ground_shortcut_discovery_required')
    source=Path(source).resolve();digest=force._hash(source);board=pcbnew.LoadBoard(str(source));pending=[]
    snapshot=field._field_snapshot_inventory(board)
    if sum(fp.GetPadCount() for fp in board.GetFootprints())+len(list(board.GetTracks()))>16384:
        raise ValueError('ground_shortcut_native_inventory_bound')
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if time.monotonic()>=deadline:break
            if fp.IsDNP() or pad.GetNetname()!='GND' or cells.cec_return_escape.smd_surface_layer(pad) is None:continue
            old=cells._existing_return(board,pad,16.,allow_native_track_body=True)
            if old and old[0]>minimum_return_mm:pending.append((-old[0],force._uid(pad),pad,old[1]))
    plans=[];trials=[];cache={};reference_cache={};graph=None;funded=0;refused_launches=[];cohorts=[];skipped=0
    for negative,pad_uid,pad,source_via in sorted(pending,key=lambda r:r[:2]):
        if time.monotonic()>=deadline:break
        if funded>=maximum_pads:break
        face=cells._ground_terminal_layer(pad);code=pad.GetNetCode();start=pad.GetPosition();spec=cells._netclass(board,'GND')
        width=max(200000,int(spec['width']),int(board.GetDesignSettings().m_TrackMinWidth))
        gap=max(200000,int(spec['clearance']),int(board.GetDesignSettings().m_MinClearance));options=[]
        # Every proposed full-class source-centre leg contains this exact
        # capsule. A blocked capsule cannot become legal by changing its
        # remote barrel. Do not spend all pad slots on known-blocked launches
        # or call that a general no-path proof. Independent plan still tests
        # every actual leg on a fresh source/cache before any construction.
        if (not fr._edge_leg_clear(board,start,start,(width+1)//2+gap)
                or not fr._tap_foreign_clear(board,start,start,width,face,gap,{code},foreign_cache=cache)):
            refused_launches.append(dict(pad_uuid=pad_uid,reason='fixed_full_class_source_launch_refused'))
            continue
        if skipped<cohort_offset:
            skipped+=1;continue
        funded+=1
        if graph is None:graph=fr._read_only_route_connectivity(board)
        reached={force._uid(i) for i in graph.GetConnectedItems(pad)}
        for via in board.GetTracks():
            if time.monotonic()>=deadline:break
            if (via.GetClass()!='PCB_VIA' or via.GetNetCode()!=code or force._uid(via) not in reached
                    or via.GetViaType()!=pcbnew.VIATYPE_THROUGH or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu):continue
            distance=math.dist(tuple(start),tuple(via.GetPosition()))/1e6
            if .001<distance<-negative-.01:
                uid=force._uid(via)
                if uid not in reference_cache:
                    try:reference_cache[uid]=_reference_contacts(board,via)
                    except ValueError:reference_cache[uid]=None
                if reference_cache[uid] is None:continue
                options.append(dict(distance_mm=distance,target_via_uuid=force._uid(via),
                    at_nm=tuple(via.GetPosition())))
        options.sort(key=lambda r:(r['distance_mm'],r['target_via_uuid']))
        entries=[]
        source_via_uid=force._uid(source_via)
        if include_track_entries:
            if source_via_uid not in reference_cache:
                try:reference_cache[source_via_uid]=_reference_contacts(board,source_via)
                except ValueError:reference_cache[source_via_uid]=None
            if reference_cache[source_via_uid] is not None:
                entries=_source_track_targets(board,pad,face,source_via,reached,-negative,deadline)
        # Fairly compose the existing barrel portfolio and literal body
        # events under the SAME pad/target/deadline bounds. No kind can
        # consume every target slot before the other gets its first trial.
        combined=[]
        for index in range(max(len(options),len(entries))):
            if index<len(options):combined.append(options[index])
            if index<len(entries):combined.append(entries[index])
        cohorts.append(dict(pad_uid=pad_uid,pad=pad,face=face,code=code,start=start,width=width,gap=gap,
            source_return_mm=-negative,options=combined[:maximum_targets],found_kinds=[]))
    # Give every funded terminal a first target before retrying a hard one.
    # A longest-first depth-first loop previously spent the whole lease on
    # adjacent blocked terminals, hiding shorter independent return repairs.
    # All cohorts share ONE deadline; no pad/target renews the search budget.
    for round_index in range(maximum_targets):
        for cohort in cohorts:
            if time.monotonic()>=deadline:break
            if round_index>=len(cohort['options']):continue
            target=cohort['options'][round_index];uid=target['target_via_uuid']
            kind='track' if 'target_track_uuid' in target else 'barrel'
            if kind in cohort['found_kinds']:continue
            pad_uid,face,code,start,width,gap=[cohort[k] for k in ('pad_uid','face','code','start','width','gap')]
            end=min(deadline,time.monotonic()+1.);diagnostics={}
            def valid(legs):
                if time.monotonic()>=end:return False
                q=quality.assess_proposed_route(board,[dict(net='GND',layer=face,width_nm=w,
                    start_nm=list(a),end_nm=list(b)) for a,b,w in legs],deadline=end,max_proposed=64)
                return q['ok'] and q['complete']
            with budget.scoped(24000) as work:
                legs=fr._guarded_profiled_lastmile_legs(board,start,pcbnew.VECTOR2I(*target['at_nm']),width,face,gap,code,
                    lambda a,b,half:fr._edge_leg_clear(board,a,b,half+gap),foreign_cache=cache,
                    deadline_monotonic=end,refine_maze=True,refinement_grids_mm=(.2,.1),endpoint_detail_grid_mm=.1,
                    maze_margin_mm=3.,compact_phase_jogs=True,max_length_nm=math.floor((cohort['source_return_mm']-.01)*1e6),
                    path_validator=valid,search_diagnostics=diagnostics)
                row=dict(pad_uuid=pad_uid,target_via_uuid=uid,found=bool(legs),cohort_round=round_index,
                    work=work.report(),search=diagnostics);trials.append(row)
                if 'target_track_uuid' in target:row['target_track_uuid']=target['target_track_uuid']
            if not legs:continue
            try:
                witness=_trial_return_witness(board,cohort['pad'],legs,cohort['source_return_mm'])
                row['temporary_whole_return_witness_mm']=witness
                if witness is None or witness>=cohort['source_return_mm']-.01:
                    row['refusal']='temporary_full_return_not_shorter';continue
                points=[list(legs[0][0])]+[list(b) for a,b,w in legs]
                extra=({"target_track_uuid":target['target_track_uuid']} if 'target_track_uuid' in target else {})
                plans.append(plan(source,board_hint=board_hint,pad_uuid=pad_uid,target_via_uuid=uid,points_nm=points,
                    timeout_s=max(.001,deadline-time.monotonic()),**extra));cohort['found_kinds'].append(kind)
            except ValueError as exc:row['refusal']=str(exc)
        if time.monotonic()>=deadline:break
    plans.sort(key=lambda p:(p['new_explicit_path_mm']-p['source_return_witness_mm'],p['pad_uuid'],p['target_via_uuid']))
    if force._hash(source)!=digest or snapshot!=field._field_snapshot_inventory(board):
        raise ValueError('ground_shortcut_discovery_changed_source')
    return dict(plans=plans,trials=trials,deadline_reached=time.monotonic()>=deadline,
        funded_pad_cohorts=funded,refused_source_launches=refused_launches,
        round_robin_target_cohorts_share_one_deadline=True,
        literal_native_track_entries_requested=include_track_entries,
        qualified_cohort_offset=cohort_offset,qualified_cohorts_skipped=skipped,
        next_qualified_cohort_offset=skipped+funded,
        source_geometry_mutated=False,finite_portfolio_not_a_no_path_proof=True,release_authority=False)


def _stage_context(board_hint,expected_source_sha256,reporting_build,maximum_candidates,minimum_return_mm):
    if (type(board_hint) is not str or not board_hint or type(expected_source_sha256) is not str
            or len(expected_source_sha256)!=64 or any(c not in '0123456789abcdef' for c in expected_source_sha256)
            or reporting_build is None or type(maximum_candidates) is not int or not 1<=maximum_candidates<=4
            or type(minimum_return_mm) not in (int,float) or not math.isfinite(minimum_return_mm)
            or not 0<minimum_return_mm<=16):
        raise ValueError('bounded_explicit_ground_shortcut_stage_required')


def discover_portfolio(source,*,board_hint,minimum_return_mm=3.,maximum_waves=3):
    """Visit distinct qualified cohorts instead of retrying one plateau.

    Every wave has the existing independent ten-second bound. There are at
    most four waves, each on the same exact source family/runtime epoch;
    failed longest terminals cannot hide the next bounded set forever.
    """
    if type(maximum_waves) is not int or not 1<=maximum_waves<=4:
        raise ValueError('one_to_four_ground_discovery_waves_required')
    source=Path(source).resolve();epoch=force._code_identity();family=force._family(source,board_hint)
    offset=0;waves=[];plans=[];reason='wave_limit'
    for _ in range(maximum_waves):
        q=discover(source,board_hint=board_hint,minimum_return_mm=minimum_return_mm,cohort_offset=offset)
        waves.append(q);plans.extend(q['plans'])
        if plans:reason='proposal_offers_require_saved_receiving';break
        next_offset=q['next_qualified_cohort_offset']
        if not q['funded_pad_cohorts'] or next_offset<=offset:
            reason='no_further_qualified_cohort_in_observed_inventory';break
        offset=next_offset
    if epoch!=force._code_identity() or family!=force._family(source,board_hint):
        raise ValueError('ground_discovery_portfolio_source_family_or_code_changed')
    return dict(plans=plans,waves=waves,trials=[t for w in waves for t in w['trials']],
        stop_reason=reason,maximum_waves=maximum_waves,
        independent_wave_max_seconds=10.,source_geometry_mutated=False,
        finite_portfolio_not_a_no_path_proof=True,source_family_and_code_unchanged=True,
        release_authority=False)


def run(source,outdir,*,board_hint,expected_source_sha256,reporting_build,maximum_candidates=1,minimum_return_mm=3.):
    _stage_context(board_hint,expected_source_sha256,reporting_build,maximum_candidates,minimum_return_mm)
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if outdir.exists() or not source.is_file() or force._hash(source)!=expected_source_sha256:
        raise ValueError('fresh_output_and_exact_ground_shortcut_source_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    inventory=discover_portfolio(source,board_hint=board_hint,minimum_return_mm=minimum_return_mm);r=dict(ok=True,complete=True,changed=False,errors=[],
        source=str(source),source_sha256=expected_source_sha256,code_identity=epoch,discovery=inventory,records=[],attempts=[],
        candidate=str(source),candidate_sha256=expected_source_sha256,source_selected=False,routing_admitted=False,
        minimum_return_mm=minimum_return_mm,minimum_return_is_search_ranking_not_receiving_or_current_authority=True,
        current_qualified=False,fab_ready=False,release_authority=False)
    import cec_current_debt as current
    import cec_force_sense_evidence as sense
    import cec_native_drc_runner as native
    import cec_stage_admission as admission
    def observe(path,label):
        shadow=force._copy_family(path,outdir/(label+'-native-input'));dest=outdir/(label+'.drc.json')
        q=native.run(shadow,dest,reporting_build=reporting_build,timeout_s=10.)
        if not q['ok'] or not q['complete'] or q['native_inventory']['potentially_truncated']:
            raise ValueError('complete_uncapped_ground_shortcut_native_report_required')
        return json.loads(dest.read_text()),q
    baseline=None
    for index,q in enumerate(inventory['plans'][:maximum_candidates]):
        row=dict(accepted=False,errors=[]);r['attempts'].append(row)
        try:
            board=construct(q);child=force._copy_family(source,outdir/('UNADMITTED-ground-shortcut-'+str(index)))
            additive._ground_refill(board);field._save_field_snapshot(board,child)
            params={k:q[k] for k in ('pad_uuid','target_via_uuid','points_nm')}
            if 'target_track_uuid' in q:params['target_track_uuid']=q['target_track_uuid']
            proof=receive(source,child,board_hint=board_hint,**params);row['independent_saved_phase']=proof
            if not proof['ok'] or not proof['complete']:raise ValueError('source_ground_shortcut_saved_receiving:'+str(proof['errors']))
            debt=current.receive(source,child,board_hint=board_hint);row['whole_parent_current_receiving']=debt
            if not debt['ok'] or not debt['complete']:raise ValueError('ground_shortcut_current_nonregression_required')
            with force._thermal_hint(board_hint):
                blockers=sorted(field.blocker_keys(field.field_coupling_summary(str(child)))-field.blocker_keys(field.field_coupling_summary(str(source))))
            row['new_field_blockers']=blockers
            if blockers:raise ValueError('ground_shortcut_new_field_blocker')
            if baseline is None:baseline,producer=observe(source,'source');r['source_native_producer']=producer
            after,producer=observe(child,'candidate-'+str(index));row['candidate_native_producer']=producer
            faults=sorted({admission._canonical_identity(v) for v in after['violations']}-
                {admission._canonical_identity(v) for v in baseline['violations']})
            row.update(new_native_fault_ids=faults,opens=len(after['unconnected_items']))
            if faults or row['opens']:raise ValueError('ground_shortcut_new_native_fault_or_open')
            cuts0,cuts1=[sense.replay(p,board_hint=board_hint,timeout_s=40.) for p in (source,child)]
            cuts=sense.compare_contour_preservation(cuts0,cuts1,modified_nets=['GND'],
                native_copper_transforms=sense.native_copper_transform_inventory(pcbnew.LoadBoard(str(source)),board,modified_nets=['GND']))
            row['whole_parent_clipped_preservation']=cuts
            if not cuts['same_evidence'] or not cuts['comparison_complete']:raise ValueError('ground_shortcut_absolute_cuts_changed')
            row['accepted']=True;r.update(changed=True,candidate=str(child),candidate_sha256=force._hash(child),
                records=[dict(plan=params,materialized=dict(added_native_uuids=proof['added_native_uuids']))],
                shortened_return_witness_mm=proof['shortened_return_witness_mm'])
            break
        except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:row['errors'].append(type(exc).__name__+':'+str(exc))
    r['source_family_and_code_unchanged']=epoch==force._code_identity() and family==force._family(source,board_hint)
    if not r['source_family_and_code_unchanged']:
        r.update(ok=False,complete=False,changed=False,candidate=str(source),candidate_sha256=expected_source_sha256,
            errors=['ground_shortcut_source_family_or_code_changed'])
    force._write(outdir/'stage.json',r);return r


def run_campaign(source,outdir,*,board_hint,expected_source_sha256,reporting_build,maximum_candidates=1,
                 minimum_return_mm=3.,max_passes=4):
    """Finite original-source-bound return improvement, with no new hole.

    Each accepted phase remeasures its terminal against its own saved parent.
    The sum is a per-phase RETURN WITNESS improvement, never a claim that old
    copper was removed. All original copper remains, and whole-original-parent
    receiving remains mandatory. A no-offer stop is not a no-path certificate.
    """
    if type(max_passes) is not int or not 1<=max_passes<=4:
        raise ValueError('one_to_four_ground_shortcut_passes_required')
    _stage_context(board_hint,expected_source_sha256,reporting_build,maximum_candidates,minimum_return_mm)
    source,outdir=[Path(p).resolve() for p in (source,outdir)]
    if outdir.exists() or not source.is_file() or force._hash(source)!=expected_source_sha256:
        raise ValueError('literal_source_and_fresh_ground_shortcut_campaign_required')
    epoch=force._code_identity();family=force._family(source,board_hint);outdir.mkdir(parents=True)
    cursor=source;digest=expected_source_sha256;seen={digest};phases=[];passes=[];reason='pass_limit';gains=[]
    for index in range(max_passes):
        dest=outdir/('pass-'+str(index))
        result=run(cursor,dest,board_hint=board_hint,expected_source_sha256=digest,reporting_build=reporting_build,
            maximum_candidates=maximum_candidates,minimum_return_mm=minimum_return_mm)
        path=dest/'stage.json';passes.append(dict(path=str(path),sha256=force._hash(path),ok=result['ok'],
            complete=result['complete'],changed=result['changed']))
        if not result['ok'] or not result['complete']:reason='stage_failure';break
        if not result['changed']:reason='no_accepted_finite_portfolio_offer';break
        if result['candidate_sha256'] in seen:reason='repeated_source_hash_refused';break
        seen.add(result['candidate_sha256']);phases.append(dict(kind='ground_shortcut',path=str(path),sha256=force._hash(path)))
        gains.append(result['shortened_return_witness_mm']);cursor=Path(result['candidate']);digest=result['candidate_sha256']
    stable=epoch==force._code_identity() and family==force._family(source,board_hint)
    success=stable and reason not in ('stage_failure','repeated_source_hash_refused')
    r=dict(ok=success,complete=success,errors=[] if success else [reason if stable else 'source_family_or_code_changed'],
        source=str(source),source_sha256=expected_source_sha256,candidate=str(cursor),candidate_sha256=digest,
        changed=bool(phases),code_identity=epoch,source_family_and_code_unchanged=stable,phase_receipts=phases,
        passes=passes,stop_reason=reason,shortened_return_witness_mm=sum(gains),minimum_return_mm=minimum_return_mm,
        minimum_return_is_search_ranking_not_receiving_or_current_authority=True,
        summed_terminal_return_witness_gains_not_removed_copper_length=True,
        original_parent_receiving_still_required=True,whole_board_cleanliness_or_no_path_proof=False,
        new_holes=0,original_copper_material_retained=True,source_selected=False,routing_admitted=False,
        current_qualified=False,fab_ready=False,release_authority=False)
    force._write(outdir/'campaign.json',r);return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','reporting-build'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('board-hint','expected-source-sha256'):p.add_argument('--'+k,required=True)
    p.add_argument('--maximum-candidates',type=int,default=1)
    p.add_argument('--minimum-return-mm',type=float,default=3.,help='Proposal ranking threshold only; no electrical or receiving waiver')
    p.add_argument('--max-passes',type=int,help='Explicit finite campaign, one to four independently received phases');a=p.parse_args()
    import cec_swig_guard;cec_swig_guard.pin()
    import wx;quiet=wx.LogNull()
    operation=run if a.max_passes is None else run_campaign
    options={} if a.max_passes is None else dict(max_passes=a.max_passes)
    r=operation(a.source,a.out,board_hint=a.board_hint,expected_source_sha256=a.expected_source_sha256,
        reporting_build=a.reporting_build,maximum_candidates=a.maximum_candidates,minimum_return_mm=a.minimum_return_mm,**options)
    print(json.dumps(dict(receipt=str(a.out/('stage.json' if a.max_passes is None else 'campaign.json')),
        **{k:r.get(k) for k in ('ok','complete','changed','candidate','candidate_sha256','shortened_return_witness_mm','errors')})),flush=True)
    return 0 if r['ok'] and r['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
