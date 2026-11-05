"""Complete absent or nonlocal GND access with source-bound physical additions.

An unobserved return is not an electrical open. Reuse the existing guarded
return producer, reject already-covered surface paths and existing in-pad
plated references, and independently replay every saved addition. No part,
barrel, source trace, power copper, current budget or fabrication rule moves.
"""
import math,time,tempfile
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_additive_portal_compaction as portal
import cec_cell_row_rebuild as row
import cec_copper_echo as syntax
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_fab_profile as fab
import cec_force_current as force
import cec_existing_local_pofv_pad_rule as local_rule
import cec_fr as fr
import cec_ground_return_preservation as returns
import cec_ground_return_shortcut as shortcut
import cec_kelvin_copper_cut as native
import cec_native_ground_span_reflow as lease
import cec_ordinary_route_receiving as ordinary
import cec_route_quality as quality
import cec_sensitive_scalar_path_reflow as geometry
from cec_native_items import discard_items


def _pad(board,uid):
    if board is None:raise ValueError('readable_native_ground_source_required')
    selected=[p for f in board.GetFootprints() for p in f.Pads() if force._uid(p)==uid]
    if len(selected)!=1:raise ValueError('unique_source_ground_terminal_required')
    p=selected[0];face=cells.cec_return_escape.smd_surface_layer(p)
    if (face is None or p.HasHole() or p.GetNetCode()<=0 or p.GetNetname()!='GND'
            or p.GetParentFootprint().IsDNP()):
        raise ValueError('populated_native_surface_ground_terminal_required')
    return p,int(face)


def _source_track_root(board,pad,requested,reach_mm,deadline):
    """Finite exact source-centreline sites, never an extra surface branch.

    The geometric menu is only a proposal. Every hole rechecks all copper
    layers, factory/land context, drills, edges and the actual local source
    return before it can replace a proposed dogbone. Source metal is intact.
    Besides the historical small carriers, a literal saved Ground-class
    carrier may provide the same attachment. This grants no cut, smaller
    via, current capacity, or authority to use an arbitrary wide mesh edge.
    """
    face=cells.cec_return_escape.smd_surface_layer(pad);at=tuple(pad.GetPosition())
    if len(list(board.GetTracks()))+sum(f.GetPadCount() for f in board.GetFootprints())>16384:
        raise ValueError('source_track_ground_root_native_inventory_bound')
    dia,drill,_=cells._board_legal_through_via_geometry(board,*requested)
    width,diameter=pcbnew.FromMM(drill),pcbnew.FromMM(dia)
    spec=cells._netclass(board,'GND')
    clearance=max(200000,int(board.GetDesignSettings().m_MinClearance),int(spec['clearance']))
    # The actual sibling project, not a mutable native Default proxy, must
    # name a wider carrier. Keep its exact via preference as well: the
    # producer's optional contained-seat tier can offer smaller BOARD-floor
    # geometry, but that is not permission for this Source-track fallback.
    source_class_width=None
    filename=board.GetFileName()
    if filename and Path(filename).with_suffix('.kicad_pro').is_file():
        expected=cells._board_legal_through_via_geometry(board,
            max(.6,float(spec['via_dia'])),max(.3,float(spec['via_drill'])))
        if ((diameter,width)==tuple(pcbnew.FromMM(v) for v in expected[:2])
                and 0<int(spec['width'])<=1000000):
            source_class_width=int(spec['width'])
    menu=[];grouped={force._uid(t) for g in board.Groups() for t in g.GetItems()}
    for t in board.GetTracks():
        if time.monotonic()>=deadline:raise ValueError('source_track_ground_root_discovery_deadline')
        if (t.GetClass()!='PCB_TRACK' or t.GetNetCode()!=pad.GetNetCode() or t.GetLayer()!=face
                or t.GetParentGroup() or force._uid(t) in grouped or t.HasSolderMask()
                or not (0<t.GetWidth()<=350000
                    or t.GetWidth()==source_class_width)):continue
        a,b=tuple(t.GetStart()),tuple(t.GetEnd());d=(b[0]-a[0],b[1]-a[1]);square=d[0]**2+d[1]**2
        if not square or not quality.is_canonical_stroke(a,b,tolerance_nm=0):continue
        points={a,b}
        for n in (1,2,3):
            if all((n*v)%4==0 for v in d):points.add(tuple(a[i]+n*d[i]//4 for i in (0,1)))
        dot=sum((at[i]-a[i])*d[i] for i in (0,1))
        if 0<=dot<=square and all((dot*v)%square==0 for v in d):
            points.add(tuple(a[i]+dot*d[i]//square for i in (0,1)))
        for point in points:
            distance=math.dist(at,point)/1e6
            if 0<distance<=reach_mm:menu.append((distance,point,force._uid(t)))
    cache={};seen=set()
    for _,point,carrier in sorted(menu):
        if point in seen:continue
        if len(seen)>=24:break
        seen.add(point)
        if time.monotonic()>=deadline:raise ValueError('source_track_ground_root_geometry_deadline')
        pos=pcbnew.VECTOR2I(*point)
        if (not fr._edge_leg_clear(board,pos,pos,diameter//2)
                or not cells._hole_to_hole_clear(board,pos,drill)[0]
                or not fr._via_spot_clear(board,pos,diameter,clearance,{pad.GetNetCode()},
                    drill_nm=width,net_code=pad.GetNetCode(),contained_layers={face},foreign_cache=cache)):continue
        via=pcbnew.PCB_VIA(board);via.SetPosition(pos);via.SetWidth(diameter);via.SetDrill(width)
        via.SetNetCode(pad.GetNetCode());via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetLocked(True)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.m_Uuid.Clone(pcbnew.KIID());board.Add(via)
        try:
            actual=cells._existing_return(board,pad,reach_mm,allow_native_track_body=True)
            if actual is None or force._uid(actual[1])!=force._uid(via):raise ValueError('new_source_track_root_not_a_literal_local_return')
            shortcut._reference_contacts(board,via)
        except ValueError:
            discard_items(board,[via]);continue
        except BaseException:
            # The pre-producer tier uses the invocation's still-pristine
            # Source working board. Unexpected native errors must leave that
            # board pristine too, then propagate; never silently fall back.
            discard_items(board,[via]);raise
        return dict(status='source-track-entry',items=[via],via_uuid=force._uid(via),
            source_track_root=dict(carrier_uuid=carrier,at_nm=list(point),native_return_mm=actual[0],
                sampled_sites=len(seen),maximum_sites=24,only_literal_source_track_centres=True,
                carrier_width_nm=next(t.GetWidth() for t in board.GetTracks() if force._uid(t)==carrier),
                saved_ground_class_width_nm=source_class_width,
                requested_via_geometry_nm=[diameter,width],new_capacity_credited=False))
    return None


def _existing_pad_rule(board,pad):
    """An actual saved local rule, not a profile-name floor exemption.

    Default use is the unchanged Source SMD land centre. An explicitly
    requested canonical dogbone separately proves the same literal Source
    owner and bounded local process. The group must already exist; adding
    its new member is exact-replayed and independently native received,
    never a new rule or fabrication/current qualification.
    """
    context=local_rule.resolve(board,pad)
    groups=[g for g in board.Groups() if g.GetName()==local_rule.GROUP]
    if context is None or len(groups)!=1 or groups[0].IsLocked():
        raise ValueError('unique_unlocked_existing_saved_local_pad_rule_required')
    context=dict(context,ordinary_board_limits_nm=list(context['ordinary_board_limits_nm']))
    limits=context['minimum_nm']
    requested=local_rule.geometry(context,(
        max(limits['via_diameter'],limits['hole_size']+2*limits['annular_width'])/1e6,
        limits['hole_size']/1e6))
    return context,force._uid(groups[0]),requested


def _explicit_local_dogbone(board,pad,face,point,requested,reach_mm,*,use_existing_local_pad_rule):
    """One exact 0/45 SMD escape; ordinary geometry unless a saved rule owns it."""
    at=pcbnew.VECTOR2I(*point);start=pad.GetPosition()
    spec=cells._netclass(board,'GND')
    width=max(int(spec['width']),int(board.GetDesignSettings().m_TrackMinWidth))
    clearance=max(200000,int(spec['clearance']),int(board.GetDesignSettings().m_MinClearance))
    diameter,drill=[round(v*1e6) for v in requested]
    if not 0<math.dist(tuple(start),tuple(at))<=reach_mm*1e6:
        raise ValueError('explicit_local_ground_dogbone_exceeds_declared_reach')
    if (not quality.is_canonical_stroke(tuple(start),tuple(at),tolerance_nm=0)
            or not fr._edge_leg_clear(board,start,at,width/2+clearance)
            or not cells._hole_to_hole_clear(board,at,requested[1])[0]
            or not fr._via_spot_clear(board,at,diameter,clearance,{pad.GetNetCode()},drill_nm=drill,
                net_code=pad.GetNetCode(),local_pofv_dogbone=(
                    dict(pad=pad,start=start,layer=face)if use_existing_local_pad_rule else None))
            or not fr._tap_foreign_clear(board,start,at,width,face,clearance,{pad.GetNetCode()})):
        raise ValueError('explicit_source_local_ground_dogbone_is_not_native_clear')
    edge=pcbnew.PCB_TRACK(board);edge.SetNet(pad.GetNet());edge.SetLayer(face);edge.SetWidth(width)
    edge.SetStart(start);edge.SetEnd(at);board.Add(edge)
    via=pcbnew.PCB_VIA(board);via.SetNet(pad.GetNet());via.SetPosition(at)
    via.SetWidth(diameter);via.SetDrill(drill);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);board.Add(via)
    process=fab.local_pofv_via_decision(board,via)
    if not process[0]:raise ValueError('explicit_ground_dogbone_has_no_live_process_owner:'+process[1])
    shortcut._reference_contacts(board,via)
    return dict(status='dogbone',items=[edge,via],via_uuid=force._uid(via)),None


def _explicit_local_polyline(board,pad,face,points,requested,reach_mm):
    """Two full-class limbs; no new rule, width, reach or capacity allowance."""
    points=[pcbnew.VECTOR2I(*p)for p in points]
    spec=cells._netclass(board,'GND')
    width=max(int(spec['width']),int(board.GetDesignSettings().m_TrackMinWidth))
    clearance=max(200000,int(spec['clearance']),int(board.GetDesignSettings().m_MinClearance))
    diameter,drill=[round(v*1e6)for v in requested]
    if not fab.local_pofv_polyline_matches(pad,points,face,int(pad.GetNetCode()),reach_mm=reach_mm):
        raise ValueError('bounded_literal_source_SMD_two_leg_ground_path_required')
    if (any(not fr._edge_leg_clear(board,a,z,width/2+clearance)
            or not fr._tap_foreign_clear(board,a,z,width,face,clearance,{pad.GetNetCode()})
            for a,z in zip(points,points[1:]))
            or not cells._hole_to_hole_clear(board,points[-1],requested[1])[0]
            or not fr._via_spot_clear(board,points[-1],diameter,clearance,{pad.GetNetCode()},
                drill_nm=drill,net_code=pad.GetNetCode(),local_pofv_polyline=
                    dict(pad=pad,points=points,layer=face))):
        raise ValueError('explicit_source_local_ground_polyline_is_not_native_clear')
    items=[]
    for a,z in zip(points,points[1:]):
        edge=pcbnew.PCB_TRACK(board);edge.SetNet(pad.GetNet());edge.SetLayer(face);edge.SetWidth(width)
        edge.SetStart(a);edge.SetEnd(z);board.Add(edge);items.append(edge)
    via=pcbnew.PCB_VIA(board);via.SetNet(pad.GetNet());via.SetPosition(points[-1])
    via.SetWidth(diameter);via.SetDrill(drill);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);board.Add(via);items.append(via)
    decision=fab.local_pofv_via_decision(board,via)
    if not decision[0]:raise ValueError('explicit_ground_polyline_has_no_live_process_owner:'+decision[1])
    shortcut._reference_contacts(board,via)
    return dict(status='dogbone',items=items,via_uuid=force._uid(via)),None


def plan(source,*,board_hint,pad_uuid,reach_mm=1.5,timeout_s=10.,prefer_source_track_root=False,
         use_existing_local_pad_rule=False,dogbone_position_nm=None,dogbone_points_nm=None):
    deadline=lease._deadline(timeout_s)
    if (type(board_hint) is not str or not board_hint or type(pad_uuid) is not str or not pad_uuid
            or type(reach_mm) not in (int,float) or not math.isfinite(reach_mm) or not 0<reach_mm<=1.5
            or type(prefer_source_track_root) is not bool
            or type(use_existing_local_pad_rule) is not bool
            or use_existing_local_pad_rule and prefer_source_track_root
            or dogbone_position_nm is not None and (prefer_source_track_root
                or type(dogbone_position_nm) not in (list,tuple) or len(dogbone_position_nm)!=2
                or any(type(v) is not int or abs(v)>2000000000 for v in dogbone_position_nm))
            or dogbone_points_nm is not None and (prefer_source_track_root or not use_existing_local_pad_rule
                or dogbone_position_nm is not None
                or type(dogbone_points_nm) not in (list,tuple) or len(dogbone_points_nm)!=3
                or any(type(p)not in(list,tuple)or len(p)!=2
                    or any(type(v)is not int or abs(v)>2000000000 for v in p)for p in dogbone_points_nm))):
        raise ValueError('bounded_source_local_ground_completion_required')
    source=Path(source).resolve();family=force._family(source,board_hint)
    b=pcbnew.LoadBoard(str(source));pad,face=_pad(b,pad_uuid)
    before=cells._existing_return(b,pad,16.,allow_native_track_body=True)
    if before is not None and before[0]<=reach_mm+.000001:
        raise ValueError('source_already_has_a_bounded_local_ground_return')
    # A thermal PTH inside a land is real copper, not an absent PCB_VIA.
    # This tier cannot add another hole merely because the legacy observer
    # does not report footprint-owned plated barrels.
    planes={b.GetLayerID(n) for n in fr.plane_layers(b)}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if (p.GetAttribute()!=pcbnew.PAD_ATTRIB_PTH or not p.HasHole()
                    or p.GetNetCode()!=pad.GetNetCode() or not p.IsOnLayer(face)
                    or not p.GetEffectiveShape(face).Collide(pad.GetEffectiveShape(face),0)):continue
            if planes and all(p.IsOnLayer(layer) and any(not z.GetIsRuleArea()
                    and z.GetNetname()=='GND' and z.IsOnLayer(layer) and z.IsFilled()
                    and z.HasFilledPolysForLayer(layer)
                    and z.GetFilledPolysList(layer).Collide(p.GetEffectiveShape(layer),0)
                    for z in b.Zones()) for layer in planes):
                raise ValueError('source_land_already_contacts_a_plated_reference_pad')
    original={force._uid(t):t for t in b.GetTracks()};binding=row._source_binding(b)
    spec=cells._netclass(b,'GND')
    # Native netclass defaults and board floors, not a new smaller drill.
    # _netclass returns via geometry in mm, unlike track widths in nm.
    requested=(max(.6,float(spec['via_dia'])),max(.3,float(spec['via_drill'])))
    context=group_uid=None
    if use_existing_local_pad_rule:
        context,group_uid,requested=_existing_pad_rule(b,pad)
    elif dogbone_position_nm is not None:
        # A manually selected axis is not permission to borrow a local
        # in-pad floor. Retain the larger saved GND class and board/factory
        # geometry, exactly as the ordinary automatic producer does.
        diameter,drill,_=cells._board_legal_through_via_geometry(b,*requested)
        requested=(diameter,drill)
    if use_existing_local_pad_rule and dogbone_position_nm is None and dogbone_points_nm is None:
        diameter,drill=[round(v*1e6) for v in requested]
        clearance=max(200000,int(b.GetDesignSettings().m_MinClearance),int(spec['clearance']))
        if (not fr._edge_leg_clear(b,pad.GetPosition(),pad.GetPosition(),diameter//2)
                or not cells._hole_to_hole_clear(b,pad.GetPosition(),requested[1])[0]
                or not fr._via_spot_clear(b,pad.GetPosition(),diameter,clearance,{pad.GetNetCode()},
                    drill_nm=drill,net_code=pad.GetNetCode(),contained_layers={face},local_pofv_pad=pad)):
            raise ValueError('existing_source_local_in_pad_ground_entry_is_not_native_clear')
    result=error=None;source_root_attempted=False
    if prefer_source_track_root:
        diameter,_,_=cells._board_legal_through_via_geometry(b,*requested)
        # An exact native land can prove that the REQUESTED ordinary barrel
        # is not contained at its centre. In that case honour the caller's
        # Source-track preference before paying for the optional off-centre
        # seat search. This is proposal ordering, not new in-pad authority.
        if not fab._pad_contains_circle(pad,pad.GetPosition(),
                pcbnew.FromMM(diameter)/2+1000,tolerance_nm=0):
            source_root_attempted=True
            # No producer has touched this freshly loaded Source board yet.
            # The root probe rolls back every failed barrel and only returns
            # its explicit additions on success. Re-loading the SAME parent
            # here contributed no independent observation or authority.
            result=_source_track_root(b,pad,requested,reach_mm,deadline)
    if result is None:
        if dogbone_points_nm is not None:
            result,error=_explicit_local_polyline(b,pad,face,dogbone_points_nm,requested,reach_mm)
        elif dogbone_position_nm is not None:
            result,error=_explicit_local_dogbone(b,pad,face,dogbone_position_nm,requested,reach_mm,
                use_existing_local_pad_rule=use_existing_local_pad_rule)
        else:
            result,error=cells._add_ground_return(b,pad,board_path=board_hint,reach_mm=reach_mm,
                lock=True,pofv_geometry=requested)
    if result is None:raise ValueError('source_guarded_ground_completion_refused:'+str(error))
    if (use_existing_local_pad_rule and dogbone_position_nm is None and dogbone_points_nm is None
            and result['status']!='via-in-pad'):
        raise ValueError('existing_local_pad_rule_only_allows_direct_source_land_entry')
    # A producer can now offer a fully contained OFF-CENTRE seat with the
    # same via-in-pad status as an exact-centre entry. This wrapper still
    # requires the latter for that operation type. Do not discard the
    # caller's requested Source-track fallback merely because of the status
    # string: inspect the actual new barrel's position. A failed fallback
    # retains the strict centre-only refusal below, never adopts a new seat
    # or smaller geometry by trusting producer flags.
    off_centre_entry=(result['status']=='via-in-pad'
        and any(i.GetClass()=='PCB_VIA' and tuple(i.GetPosition())!=tuple(pad.GetPosition())
            for i in result['items']))
    if (prefer_source_track_root and not source_root_attempted
            and (result['status']=='dogbone' or off_centre_entry)):
        alternative=pcbnew.LoadBoard(str(source));alt_pad,_=_pad(alternative,pad_uuid)
        root=_source_track_root(alternative,alt_pad,requested,reach_mm,deadline)
        if root is not None:result=root
    # Keep both native boards alive while consuming their item proxies.
    added=result['items'];ops=[];pruned=0;covered_stubs=[];target=result.get('via_uuid')
    for item in added:
        if item.GetClass()=='PCB_TRACK':
            # A new qualified root may already sit on an existing source
            # track. Do not add the producer's duplicate stub: exact integer
            # collinear capsule containment is proof, proximity is not.
            if result['status']=='dogbone' and target not in original:
                covered=portal._covered_by_source(item,original.values())
                if covered:
                    covered_stubs.append(covered);continue
            # Suppress an emitted finishing limb wholly inside a retained
            # flashed land. The same native drill subtraction applies to
            # both objects, so this introduces no imaginary copper in a hole.
            root=original.get(target)
            if root is not None and root.GetClass()=='PCB_VIA' and root.FlashLayer(item.GetLayer()):
                work=native._Work(deadline)
                if native._shape(root,item.GetLayer(),False,work).covers(native._shape(item,item.GetLayer(),True,work)):
                    pruned+=1;continue
            ops.append(['trk',list(item.GetStart()),list(item.GetEnd()),int(item.GetWidth()),int(item.GetLayer())])
        elif item.GetClass()=='PCB_VIA':
            ops.append(['via',list(item.GetPosition()),item.GetDrillValue(),item.GetWidth(item.TopLayer())])
        else:raise ValueError('ground_completion_only_native_track_or_via')
    if not 1<=len(ops)<=16 or sum(op[0]=='via' for op in ops)>1:
        raise ValueError('bounded_nonempty_ground_completion_additions_required')
    parent=pcbnew.LoadBoard(str(source));p,face=_pad(parent,pad_uuid)
    vias=[op for op in ops if op[0]=='via'];tracks=[op for op in ops if op[0]=='trk']
    if vias:
        if result['status']=='via-in-pad':
            if len(ops)!=1 or vias[0][1]!=list(p.GetPosition()):
                raise ValueError('new_in_pad_ground_hole_must_be_exact_source_land_entry')
        elif result['status']=='dogbone':
            if (not tracks and not covered_stubs) or target in original:
                raise ValueError('source_guarded_dogbone_must_have_a_new_local_root')
        elif result['status']=='source-track-entry':
            if (not prefer_source_track_root or len(ops)!=1 or not result.get('source_track_root')
                    or result['source_track_root']['at_nm']!=vias[0][1]):
                raise ValueError('exact_source_track_owned_ground_root_required')
        else:raise ValueError('only_source_guarded_in_pad_or_dogbone_ground_holes_allowed')
    elif target not in original:raise ValueError('literal_retained_ground_reference_barrel_required')
    if not vias:shortcut._reference_contacts(parent,original[target])
    if tracks:
        pts=[tracks[0][1],*[op[2] for op in tracks]]
        if ((pts[0]!=list(p.GetPosition())if dogbone_points_nm is None else
                pts!=[list(q)for q in dogbone_points_nm]or not p.HitTest(pcbnew.VECTOR2I(*pts[0])))
                or any(tracks[i][2]!=tracks[i+1][1] for i in range(len(tracks)-1))):
            raise ValueError('one_continuous_source_ground_stub_required')
        if vias and pts[-1]!=vias[0][1]:raise ValueError('new_dogbone_must_end_at_its_literal_source_guarded_root')
        geometry._points(pts)
        shortcut._new_surface_material(parent,pts,face,deadline)
    unchanged=family==force._family(source,board_hint)
    source_hash=force._hash(source)
    if not unchanged:raise ValueError('ground_completion_source_family_changed')
    if time.monotonic()>=deadline:raise ValueError('ground_completion_plan_deadline')
    proposal=dict(schema=1,source=str(source),source_sha256=source_hash,board_hint=board_hint,
        pad_uuid=pad_uuid,reach_mm=reach_mm,source_native_binding=binding,ops=ops,
        retained_target_via_uuid=target if target in original else None,
        fully_retained_land_covered_finishing_limbs_suppressed=pruned,
        source_capsule_covered_dogbone_stubs_suppressed=covered_stubs,
        prefer_source_track_root=prefer_source_track_root,
        use_existing_local_pad_rule=use_existing_local_pad_rule,
        existing_local_pad_rule=context,existing_local_pad_rule_group_uuid=group_uid,
        source_track_root=result.get('source_track_root'),
        source_return_witness_mm=before[0] if before is not None else None,
        source_unobserved_is_not_an_electrical_open=True,
        source_parts_power_and_rules_unchanged=True,release_authority=False)
    if dogbone_position_nm is not None:proposal['dogbone_position_nm']=list(dogbone_position_nm)
    if dogbone_points_nm is not None:proposal['dogbone_points_nm']=[list(p)for p in dogbone_points_nm]
    return proposal


def construct(proposal,*,incoming_uuids=None,timeout_s=10.):
    args={k:proposal[k] for k in ('board_hint','pad_uuid','reach_mm','prefer_source_track_root')}
    args['use_existing_local_pad_rule']=proposal.get('use_existing_local_pad_rule',False)
    if 'dogbone_position_nm' in proposal:args['dogbone_position_nm']=proposal['dogbone_position_nm']
    if 'dogbone_points_nm' in proposal:args['dogbone_points_nm']=proposal['dogbone_points_nm']
    fresh=plan(proposal['source'],timeout_s=timeout_s,**args)
    if fresh!=proposal:raise ValueError('stale_or_forged_ground_completion_plan')
    return _construct_rederived(fresh,incoming_uuids=incoming_uuids)


def _construct_rederived(proposal,*,incoming_uuids=None):
    """Materialize one plan just rederived by this public API/receiver.

    This is not admission or a reusable success token. Public construction
    re-plans above; saved receiving independently re-plans its ORIGINAL
    parent before using this helper, then compares the entire exact saved
    delta and Source/code families. Re-running that same expensive search
    inside its replay consumed the lease needed for physical return checks.
    """
    ops=proposal['ops']
    if incoming_uuids is not None and (type(incoming_uuids) is not list or len(incoming_uuids)!=len(ops)
            or len(set(incoming_uuids))!=len(ops) or any(type(u) is not str or not u for u in incoming_uuids)):
        raise ValueError('exact_ground_completion_incoming_identities_required')
    b=pcbnew.LoadBoard(proposal['source'])
    for i,op in enumerate(ops):
        if op[0]=='trk':
            item=pcbnew.PCB_TRACK(b);item.SetStart(pcbnew.VECTOR2I(*op[1]));item.SetEnd(pcbnew.VECTOR2I(*op[2]))
            item.SetWidth(op[3]);item.SetLayer(op[4])
        else:
            item=pcbnew.PCB_VIA(b);item.SetPosition(pcbnew.VECTOR2I(*op[1]));item.SetDrill(op[2]);item.SetWidth(op[3])
            item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);item.SetViaType(pcbnew.VIATYPE_THROUGH)
        item.m_Uuid.Clone(pcbnew.KIID(incoming_uuids[i]) if incoming_uuids else pcbnew.KIID())
        item.SetNetCode(b.GetNetcodeFromNetname('GND'));item.SetLocked(True);b.Add(item)
        if proposal['use_existing_local_pad_rule'] and op[0]=='via':
            group=next(g for g in b.Groups() if force._uid(g)==proposal['existing_local_pad_rule_group_uuid'])
            group.AddItem(item)
        elif (proposal['use_existing_local_pad_rule'] and 'dogbone_position_nm' not in proposal
                and 'dogbone_points_nm' not in proposal):
            raise ValueError('local_pad_rule_cannot_qualify_a_surface_stub')
    return b


def _save_additive_snapshot(board,source,path):
    """Publish native additions without rewriting opaque retained Source ink.

    This is a producer, not a receiving exception. Only exact native new
    copper, existing Ground fill children and already-owned monotone group
    membership enter the literal Source. The independent receiver still
    rederives the proposal, every saved node and all physical obligations.
    """
    import cec_source_literal_additions as literal
    import cec_source_retaining_ses_import as text_io
    source,path=[Path(p).resolve(strict=True)for p in(source,path)]
    if source==path:raise ValueError('distinct_private_ground_snapshot_required')
    force._check_output(path,force._protected_paths(source))
    original=text_io.raw_text(source)
    if text_io.raw_text(path)!=original:
        raise ValueError('exact_private_source_copy_required_for_ground_snapshot')
    sidecars=force._sidecars(source)
    if force._sidecars(path)!=sidecars:
        raise ValueError('ground_snapshot_cannot_change_source_authority_sidecars')
    ground=additive._ground_refill(board)
    with tempfile.TemporaryDirectory(prefix='cec-ground-literal-snapshot-')as work:
        native_path=Path(work)/'native.kicad_pcb'
        field._save_field_snapshot(board,native_path)
        saved=literal.assemble(original,text_io.raw_text(native_path),ground_ids=ground)
    if (text_io.raw_text(source)!=original or text_io.raw_text(path)!=original
            or force._sidecars(source)!=sidecars or force._sidecars(path)!=sidecars):
        raise ValueError('ground_snapshot_source_or_private_copy_changed_before_publish')
    text_io.write_raw(path,saved)
    return dict(source_literal_nodes_retained=True,existing_ground_only_refill_uuids=ground,
        only_native_additions_and_existing_typed_group_extensions=True,
        source_authority_sidecars_unchanged=True,receiving_still_required=True,
        current_qualified=False,fab_ready=False,release_authority=False)


def write_private(proposal,directory,*,incoming_uuids=None,timeout_s=10.):
    """Construct/save one fresh proposal with the same literal replay writer."""
    deadline=lease._deadline(timeout_s)
    source=Path(proposal['source']).resolve(strict=True);hint=proposal['board_hint']
    epoch=force._code_identity();family=force._family(source,hint)
    if force._hash(source)!=proposal['source_sha256']:
        raise ValueError('ground_completion_source_identity_changed_before_save')
    board=construct(proposal,incoming_uuids=incoming_uuids,
        timeout_s=max(.001,deadline-time.monotonic()))
    target=force._copy_family(source,Path(directory))
    saved=_save_additive_snapshot(board,source,target)
    unchanged=(epoch==force._code_identity() and family==force._family(source,hint))
    candidate_hash=force._hash(target)
    if not unchanged or time.monotonic()>=deadline:
        raise ValueError('ground_completion_saved_source_code_or_lease_changed')
    return dict(candidate=str(target),candidate_sha256=candidate_hash,save=saved,
        complete=True,routing_admitted=False,whole_saved_receiving_still_required=True,
        current_qualified=False,fab_ready=False,release_authority=False)


def _selected_ground_join_partitions(old_parts,new_parts,selected_key,ground_keys):
    """Preserve every old partition; only this pad's GND island may gain peers.

    A legitimate open closure merges old connected components. It cannot
    split an old component, merge two other islands, touch another net or
    obtain credit from a new object without a real Source reference contact.
    The caller independently proves exact additions and all plane contacts.
    """
    old=[frozenset(p)for p in old_parts];new=[frozenset(p)for p in new_parts]
    if (not old or not new or any(not p for p in [*old,*new])
            or set().union(*old)!=set().union(*new)
            or sum(len(p)for p in old)!=len(set().union(*old))
            or sum(len(p)for p in new)!=len(set().union(*new))):
        raise ValueError('ground_completion_exact_retained_partition_inventory_required')
    selected=[p for p in old if selected_key in p]
    if len(selected)!=1 or not selected[0]<=ground_keys:
        raise ValueError('ground_completion_selected_Source_ground_partition_required')
    for p in old:
        if sum(p<=q for q in new)!=1:
            raise ValueError('ground_completion_split_a_Source_partition')
    merged=[q for q in new if q not in old]
    if (len(merged)>1 or any(not selected[0]<=q or not q<=ground_keys for q in merged)):
        raise ValueError('ground_completion_merged_unselected_or_foreign_Source_partitions')
    return dict(every_Source_partition_preserved=True,
        every_Source_partition_identical=set(old)==set(new),
        only_selected_ground_Source_islands_joined=True,
        original_partition_count=len(old),candidate_partition_count=len(new),
        joined_Source_ground_partitions=len(old)-len(new))


GROUND_RECEIVING_PHASES=(
    'Source_identity_and_proposal',
    'independent_saved_delta',
    'actual_saved_partitions_and_local_return',
    'all_Source_returns_craft_and_identity')


class _GroundReceivingLease:
    """Four explicit checks, each <=10s; never borrow an unused later lease.

    This optional composition does not change any Source, saved-delta,
    partition, return, craft or final-identity predicate. The default receiver
    still uses its historical single deadline and unchanged result schema.
    """
    def __init__(self,seconds,phase_timeouts):
        if (type(seconds)not in(int,float)or not math.isfinite(seconds)or not 0<seconds<=10
                or type(phase_timeouts)not in(list,tuple)or len(phase_timeouts)!=len(GROUND_RECEIVING_PHASES)
                or any(type(v)not in(int,float)or not math.isfinite(v)or not 0<v<=seconds
                    for v in phase_timeouts)):
            raise ValueError('bounded_explicit_Ground_receiving_phase_timeouts_required')
        self.budgets=tuple(float(v)for v in phase_timeouts)
        self.index=0;self.timings={}
        self.started=self.phase_started=time.monotonic()
        self.deadline=self.started+self.budgets[0]

    def _close(self):
        now=time.monotonic()
        if now>=self.deadline:
            raise ValueError('saved_Ground_'+GROUND_RECEIVING_PHASES[self.index]+'_deadline')
        self.timings[GROUND_RECEIVING_PHASES[self.index]]=now-self.phase_started
        return now

    def advance(self,name):
        if self.index+1>=len(GROUND_RECEIVING_PHASES)or GROUND_RECEIVING_PHASES[self.index+1]!=name:
            raise ValueError('explicit_saved_Ground_receiving_stage_order_required')
        closed=self._close();self.index+=1
        self.phase_started=closed;self.deadline=self.phase_started+self.budgets[self.index]
        return self.deadline

    def finish(self):
        if self.index!=len(GROUND_RECEIVING_PHASES)-1:
            raise ValueError('all_saved_Ground_receiving_stages_required')
        finished=self._close()
        if finished-self.started>=sum(self.budgets):
            raise ValueError('saved_Ground_total_work_deadline')


def receive(source,candidate,*,board_hint,pad_uuid,reach_mm=1.5,timeout_s=10.,prefer_source_track_root=False,
            use_existing_local_pad_rule=False,dogbone_position_nm=None,dogbone_points_nm=None,
            receiving_phase_timeouts_s=None):
    r=dict(ok=False,complete=False,errors=[],fab_ready=False,current_qualified=False,release_authority=False)
    try:
        phases=(_GroundReceivingLease(timeout_s,receiving_phase_timeouts_s)
            if receiving_phase_timeouts_s is not None else None)
        deadline=lease._deadline(timeout_s)if phases is None else phases.deadline
        if phases is not None:
            r.update(stage_timings_s=phases.timings,bounded_composition=dict(
                constituents=list(GROUND_RECEIVING_PHASES),stage_limits_s=list(phases.budgets),
                per_constituent_limit_s=timeout_s,aggregate_limit_s=sum(phases.budgets)))
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        if source==candidate:raise ValueError('distinct_saved_ground_completion_candidate_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        q=plan(source,board_hint=board_hint,pad_uuid=pad_uuid,reach_mm=reach_mm,
            prefer_source_track_root=prefer_source_track_root,
            use_existing_local_pad_rule=use_existing_local_pad_rule,
            dogbone_position_nm=dogbone_position_nm,
            dogbone_points_nm=dogbone_points_nm,
            timeout_s=max(.001,deadline-time.monotonic()))
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        if phases is not None:deadline=phases.advance('independent_saved_delta')
        _,old=additive._nodes(source);_,new=additive._nodes(candidate);incoming=set(new)-set(old)
        if old.keys()-new.keys() or len(incoming)!=len(q['ops']):raise ValueError('exact_additive_ground_completion_scope_required')
        live={force._uid(t):t for t in child.GetTracks()};ordered=[]
        for op in q['ops']:
            matching=[]
            for uid in incoming-set(ordered):
                t=live.get(uid)
                if t is None:continue
                geometry_match=(t.GetClass()=='PCB_TRACK' and op[0]=='trk'
                    and list(t.GetStart())==op[1] and list(t.GetEnd())==op[2]
                    or t.GetClass()=='PCB_VIA' and op[0]=='via' and list(t.GetPosition())==op[1])
                if geometry_match:matching.append(uid)
            if len(matching)!=1:raise ValueError('exact_ground_completion_operation_identity_required')
            ordered.append(matching[0])
        with tempfile.TemporaryDirectory(prefix='cec-ground-completion-replay-') as work:
            projected=_construct_rederived(q,incoming_uuids=ordered)
            expected=force._copy_family(source,Path(work)/'expected')
            _save_additive_snapshot(projected,source,expected)
            _,nodes=additive._nodes(expected)
            if ({u:syntax._freeze(v) for u,v in nodes.items()}!={u:syntax._freeze(v) for u,v in new.items()}
                    or force._sidecars(source)!=force._sidecars(candidate)):
                raise ValueError('ground_completion_saved_child_differs_from_exact_source_replay')
        delta=(additive.receive(source,candidate,board_hint=board_hint)
            if phases is None else additive.receive(source,candidate,board_hint=board_hint,
                timeout_s=min(10.,max(.001,deadline-time.monotonic()))))
        if not delta['ok'] or not delta['complete']:raise ValueError('independent_ground_completion_additive_receiving_refused')
        if phases is not None:deadline=phases.advance('actual_saved_partitions_and_local_return')
        old_parts=ordinary._partition(parent,deadline);keys=set().union(*old_parts)
        new_parts=ordinary._partition(child,deadline,retained_keys=keys)
        partitions_identical={frozenset(p)for p in old_parts}=={frozenset(p)for p in new_parts}
        join=None
        if (dogbone_position_nm is not None and not use_existing_local_pad_rule
                or dogbone_points_nm is not None):
            import cec_native_partition_pair as paired
            source_inventory=paired._inventory(parent,min(deadline,time.monotonic()+10.),
                dict(items=16384,polygons=4096,vertices=200000))
            ground_keys={force._item_key(i)for i in source_inventory['objects']if i.GetNetname()=='GND'}
            source_pad,_=_pad(parent,pad_uuid)
            join=_selected_ground_join_partitions(old_parts,new_parts,force._item_key(source_pad),ground_keys)
        elif not partitions_identical:
            raise ValueError('ground_completion_changed_existing_native_partitions')
        p,_=_pad(child,pad_uuid);after=cells._existing_return(child,p,16.,allow_native_track_body=True)
        if after is None or after[0]>reach_mm+.000001:
            raise ValueError('saved_ground_completion_has_no_bounded_local_return')
        before=q['source_return_witness_mm']
        if before is not None and after[0]>=before-.000001:
            raise ValueError('saved_ground_completion_did_not_shorten_the_known_return')
        contacts=shortcut._reference_contacts(child,after[1])
        if phases is not None:deadline=phases.advance('all_Source_returns_craft_and_identity')
        preserved=returns.receive(parent,child,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        r['all_source_known_returns']=preserved
        if not preserved['ok'] or not preserved['complete']:
            raise ValueError('ground_completion_worsened_source_known_returns'
                if preserved.get('regressed_terminals') else 'ground_completion_source_known_returns_inconclusive')
        craft=[quality.analyze_board(b) for b in (parent,child)]
        if any(craft[1][k]>craft[0][k] for k in ('issue_count','non_octilinear_count')):
            raise ValueError('ground_completion_worsened_whole_native_route_craft')
        source_hash,candidate_hash=[force._hash(p) for p in (source,candidate)]
        unchanged=(epoch==force._code_identity()
            and families==[force._family(p,board_hint) for p in (source,candidate)])
        # Family/code hashing is part of the SAME lease. Checking the clock
        # before these observations could return a late success afterwards.
        if not unchanged or time.monotonic()>=deadline:
            raise ValueError('ground_completion_source_code_or_lease_changed')
        if phases is not None:phases.finish()
        r.update(ok=True,complete=True,code_identity=epoch,source_sha256=source_hash,candidate_sha256=candidate_hash,
            proposal=q,added_native_uuids=ordered,retired_track_uuids=[],modified_nets=['GND'],
            new_holes=sum(op[0]=='via' for op in q['ops']),saved_return_witness_mm=after[0],
            source_return_witness_mm=before,
            shortened_return_witness_mm=before-after[0] if before is not None else None,
            source_unobserved_return_not_an_open_or_infinite_length=True,
            actual_saved_reference_contacts=contacts,all_source_known_returns=preserved,
            every_source_native_partition_identical=partitions_identical,
            every_source_native_partition_preserved=True,
            selected_Source_ground_join=join,independent_additive_receiving=delta,
            original_parts_poses_barrels_rules_and_power_copper_unchanged=True,
            whole_native_current_fields_clipped_and_fabrication_receiving_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
