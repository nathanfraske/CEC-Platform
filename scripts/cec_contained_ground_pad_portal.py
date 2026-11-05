"""Move one ground barrel only within its unchanged containing SMD land.

Only a solitary pad-contacting barrel, without ANY surface/inner departure,
may move. Exact dimensions, UUID, factory membership, land and rules remain.
The entire swept barrel must lie in two actual saved GND-plane sheets before
AND after. This is a bounded geometry proposal, not a ground-mesh rip-up,
current/inductive qualification, clearance waiver or release permission.
Pad-centre distance may change; both entries have zero external dogbone.
All other proved short returns and signal-via return support must survive.
"""
import math,tempfile,time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_future_contour_barrel as future
import cec_rectilinear_copper as contour
from cec_native_items import discard_items


def _budget(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=10:
        raise ValueError('bounded_contained_ground_portal_lease_required')
    return time.monotonic()+seconds


def _sweep_witnesses(board,start,end,width,deadline):
    sweep=pcbnew.PCB_TRACK(board);sweep.SetStart(pcbnew.VECTOR2I(*start))
    sweep.SetEnd(pcbnew.VECTOR2I(*end));sweep.SetWidth(width);witnesses=[]
    for name in fr.plane_layers(board):
        face=int(board.GetLayerID(name))
        if face in (pcbnew.F_Cu,pcbnew.B_Cu):continue
        for zone in board.Zones():
            contour._check_deadline(deadline)
            if zone.GetIsRuleArea() or zone.GetNetname()!='GND' or not zone.IsOnLayer(face):continue
            if not zone.IsFilled() or not zone.HasFilledPolysForLayer(face):
                raise ValueError('contained_ground_portal_saved_plane_unknown')
            missing=pcbnew.SHAPE_POLY_SET()
            sweep.TransformShapeToPolygon(missing,face,0,1000,pcbnew.ERROR_OUTSIDE)
            missing.BooleanSubtract(zone.GetFilledPolysList(face))
            if not missing.OutlineCount():witnesses.append([force._uid(zone),face])
    if len({r[1] for r in witnesses})<2:
        raise ValueError('two_complete_native_ground_swept_barrel_covers_required')
    return sorted(witnesses)


def _source(board,uid,allow_locked,deadline):
    if type(uid) is not str or not uid or type(allow_locked) is not bool:
        raise ValueError('literal_contained_ground_barrel_scope_required')
    found=[t for t in board.GetTracks() if force._uid(t)==uid and t.GetClass()=='PCB_VIA']
    if len(found)!=1:raise ValueError('unique_actual_ground_pad_barrel_required')
    via=found[0];layers=list(board.GetEnabledLayers().CuStack())
    groups=[g for g in board.Groups() if g.ContainsItem(via)]
    # A selected source barrel must meet the actual board setup dimensions;
    # the default netclass routing preference is NOT a manufacturing floor.
    settings=board.GetDesignSettings()
    if (via.GetNetname()!='GND' or via.GetNetCode()<=0 or via.IsLocked() and not allow_locked
            or via.GetViaType()!=pcbnew.VIATYPE_THROUGH or via.TopLayer()!=pcbnew.F_Cu
            or via.BottomLayer()!=pcbnew.B_Cu or via.GetDrillValue()<settings.m_MinThroughDrill
            or any(via.GetWidth(l)<settings.m_ViasMinSize
                or via.GetWidth(l)-via.GetDrillValue()<2*settings.m_ViasMinAnnularWidth for l in layers)
            or len(groups)>1 or any(g.GetName()!=fr.LOCAL_POFV_SIGNAL_VIA_GROUP or g.IsLocked()
                or g.GetParentGroup() is not None for g in groups)
            or not fab.local_pofv_via_decision(board,via)[0]):
        raise ValueError('unprotected_existing_full_setup_inpad_ground_barrel_required')
    contacts=[]
    material=[*(p for f in board.GetFootprints() for p in f.Pads()),*board.GetTracks()]
    if len(material)+len(list(board.Zones()))>16384:raise ValueError('contained_ground_portal_inventory_bound')
    for item in material:
        contour._check_deadline(deadline)
        if force._uid(item)==uid:continue
        if any(item.IsOnLayer(l) and item.GetEffectiveShape(l).Collide(via.GetEffectiveShape(l),0) for l in layers):
            contacts.append(item)
    if len(contacts)!=1 or contacts[0].GetClass()!='PAD':
        raise ValueError('one_smd_land_only_no_ground_lead_mesh_or_other_barrel_contact')
    pad=contacts[0]
    if (pad.GetNetname()!='GND' or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or pad.HasHole()
            or tuple(pad.GetLayerSet().CuStack()) not in ((pcbnew.F_Cu,),(pcbnew.B_Cu,))
            or pad.GetParentFootprint().IsDNP()
            or not fab._pad_contains_circle(pad,via.GetPosition(),
                max(via.GetWidth(l) for l in layers)/2+1000,tolerance_nm=0)):
        raise ValueError('whole_unchanged_native_ground_barrel_inside_actual_smd_land_required')
    # Every source zone contact is a GND reference plane, not an arbitrary
    # surface pour/thermal/force owner whose connection this scope could cut.
    planes={int(board.GetLayerID(n)) for n in fr.plane_layers(board)}-{pcbnew.F_Cu,pcbnew.B_Cu}
    for zone in board.Zones():
        if zone.GetIsRuleArea():continue
        for l in layers:
            contour._check_deadline(deadline)
            if not zone.IsOnLayer(l):continue
            if not zone.IsFilled() or not zone.HasFilledPolysForLayer(l):
                if zone.Outline().Collide(via.GetEffectiveShape(l),0):
                    raise ValueError('contained_ground_portal_contact_fill_unknown')
                continue
            if zone.GetFilledPolysList(l).Collide(via.GetEffectiveShape(l),0) and (
                    zone.GetNetname()!='GND' or int(l) not in planes):
                raise ValueError('contained_ground_portal_has_nonplane_zone_contact')
    return via,pad


def plan(source,*,board_hint,via_uuid,allow_owned_locked=False,radius_mm=.3,grid_mm=.025,timeout_s=10.):
    deadline=_budget(timeout_s)
    if (type(radius_mm) not in (int,float) or not math.isfinite(radius_mm) or not .025<=radius_mm<=.5
            or type(grid_mm) not in (int,float) or not math.isfinite(grid_mm) or not .025<=grid_mm<=.1
            or int(radius_mm*1e6)//round(grid_mm*1e6)<1
            or (2*(int(radius_mm*1e6)//round(grid_mm*1e6))+1)**2>1681):
        raise ValueError('finite_literal_contained_ground_portal_work_required')
    source=Path(source).resolve();epoch=force._code_identity();family=force._family(source,board_hint)
    board=pcbnew.LoadBoard(str(source));via,pad=_source(board,via_uuid,allow_owned_locked,deadline)
    root=tuple(via.GetPosition());width=max(via.GetWidth(l) for l in board.GetEnabledLayers().CuStack())
    _sweep_witnesses(board,root,root,width,deadline)
    profiles=future._profiles(board,deadline);gap=future._gap(board,'GND')
    blocked=[r for r,s in profiles if s.Collide(via.GetEffectiveShape(r['layer_id']),max(gap,r['clearance_nm']))]
    if not blocked:raise ValueError('contained_ground_barrel_does_not_block_future_contour')
    private=pcbnew.LoadBoard(str(source))
    discard_items(private,[v for v in private.GetTracks() if force._uid(v)==via_uuid])
    step=round(grid_mm*1e6);radius=round(radius_mm*1e6);extent=radius//step;menu=[];cache={}
    probe=via.Duplicate()
    for _,ix,iy in sorted((math.hypot(x,y),x,y) for x in range(-extent,extent+1)
            for y in range(-extent,extent+1) if 0<math.hypot(x*step,y*step)<=radius):
        contour._check_deadline(deadline);at=pcbnew.VECTOR2I(root[0]+ix*step,root[1]+iy*step)
        if not fab._pad_contains_circle(pad,at,width/2+1000,tolerance_nm=0):continue
        probe.SetPosition(at)
        if any(s.Collide(probe.GetEffectiveShape(r['layer_id']),max(gap,r['clearance_nm'])) for r,s in profiles):continue
        if not fr._via_spot_clear(private,at,width,gap,{via.GetNetCode()},drill_nm=via.GetDrillValue(),
                net_code=via.GetNetCode(),foreign_cache=cache):continue
        try:witnesses=_sweep_witnesses(board,root,tuple(at),width,deadline)
        except ValueError:continue
        menu.append(dict(at_nm=list(at),source_swept_ground_plane_witnesses=witnesses))
    if not menu:raise ValueError('finite_contained_ground_portal_menu_exhausted_not_no_path')
    assert epoch==force._code_identity() and family==force._family(source,board_hint)
    return dict(schema=1,source=str(source),source_sha256=force._hash(source),code_identity=epoch,
        board_hint=board_hint,via_uuid=via_uuid,pad_uuid=force._uid(pad),allow_owned_locked=allow_owned_locked,
        radius_mm=radius_mm,grid_mm=grid_mm,source_position_nm=list(root),
        diameter_by_layer_nm={str(int(l)):int(via.GetWidth(l)) for l in board.GetEnabledLayers().CuStack()},
        drill_nm=int(via.GetDrillValue()),future_profiles=[r for r,s in profiles],blocked_profiles=blocked,
        portal_menu=menu,external_dogbone_length_mm_before_after=[0.,0.],
        pad_center_distance_is_not_external_dogbone_length=True,
        source_family_and_code_unchanged=True,current_authority=False,routing_admitted=False,release_authority=False)


def discover(source,*,board_hint,max_barrels=4,allow_owned_locked=False,timeout_s=10.):
    """Only actual conflicting single-land GND barrels; never coordinate hints."""
    deadline=_budget(timeout_s)
    if type(max_barrels) is not int or not 1<=max_barrels<=8 or type(allow_owned_locked) is not bool:
        raise ValueError('literal_bounded_contained_ground_portal_inventory_required')
    source=Path(source).resolve();epoch=force._code_identity();family=force._family(source,board_hint)
    b=pcbnew.LoadBoard(str(source));profiles=future._profiles(b,deadline);candidates=[];refusals=[];plans=[]
    pads=[p for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()=='GND'
        and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and not p.HasHole()]
    settings=b.GetDesignSettings()
    for via in b.GetTracks():
        contour._check_deadline(deadline)
        if via.GetClass()!='PCB_VIA' or via.GetNetname()!='GND':continue
        if (via.GetWidth(via.TopLayer())<settings.m_ViasMinSize
                or via.GetDrillValue()<settings.m_MinThroughDrill
                or not any(fab._pad_contains_circle(p,via.GetPosition(),
                    via.GetWidth(via.TopLayer())/2+1000,tolerance_nm=0) for p in pads)):continue
        gap=future._gap(b,'GND')
        hits=sum(s.Collide(via.GetEffectiveShape(r['layer_id']),max(gap,r['clearance_nm'])) for r,s in profiles)
        if not hits:continue
        try:_source(b,force._uid(via),allow_owned_locked,deadline)
        except ValueError as exc:
            refusals.append(dict(via_uuid=force._uid(via),reason=str(exc)));continue
        candidates.append((-hits,force._uid(via)))
    for _,uid in sorted(candidates)[:max_barrels]:
        contour._check_deadline(deadline)
        try:plans.append(plan(source,board_hint=board_hint,via_uuid=uid,allow_owned_locked=allow_owned_locked,
            timeout_s=max(.001,deadline-time.monotonic())))
        except ValueError as exc:refusals.append(dict(via_uuid=uid,reason=str(exc)))
    assert epoch==force._code_identity() and family==force._family(source,board_hint)
    return dict(ok=True,complete=True,source=str(source),source_sha256=force._hash(source),code_identity=epoch,
        candidate_barrels=len(candidates),unattempted=max(0,len(candidates)-max_barrels),plans=plans,refusals=refusals,
        source_and_code_unchanged=True,routing_admitted=False,release_authority=False)


def construct(source,outdir,proposal,*,portal_index=0,timeout_s=10.):
    deadline=_budget(timeout_s);source=Path(source).resolve();outdir=Path(outdir).resolve()
    if outdir.exists() or type(portal_index) is not int or not 0<=portal_index<len(proposal['portal_menu']):
        raise ValueError('fresh_private_contained_ground_portal_output_required')
    q=plan(source,board_hint=proposal['board_hint'],via_uuid=proposal['via_uuid'],
        allow_owned_locked=proposal['allow_owned_locked'],radius_mm=proposal['radius_mm'],grid_mm=proposal['grid_mm'],
        timeout_s=max(.001,deadline-time.monotonic()))
    if contour._digest(q)!=contour._digest(proposal):raise ValueError('stale_contained_ground_portal_plan')
    board=pcbnew.LoadBoard(str(source));via=next(t for t in board.GetTracks() if force._uid(t)==q['via_uuid'])
    via.SetPosition(pcbnew.VECTOR2I(*q['portal_menu'][portal_index]['at_nm']))
    child=force._copy_family(source,outdir/'UNADMITTED-contained-ground-pad-portal')
    additive._ground_refill(board);field._save_field_snapshot(board,child)
    _sweep_witnesses(board,q['source_position_nm'],tuple(via.GetPosition()),max(q['diameter_by_layer_nm'].values()),deadline)
    return dict(source=str(source),source_sha256=force._hash(source),candidate=str(child),
        candidate_sha256=force._hash(child),proposal=q,portal_index=portal_index,
        source_selected=False,routing_admitted=False,release_authority=False)


def receive(source,candidate,proposal,*,timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],current_authority=False,routing_admitted=False,release_authority=False,
        full_native_current_fields_pair_cuts_and_stack_receiving_still_required=True)
    try:
        deadline=_budget(timeout_s);paths=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,proposal['board_hint']) for p in paths]
        q=plan(paths[0],board_hint=proposal['board_hint'],via_uuid=proposal['via_uuid'],
            allow_owned_locked=proposal['allow_owned_locked'],radius_mm=proposal['radius_mm'],grid_mm=proposal['grid_mm'],
            timeout_s=max(.001,deadline-time.monotonic()))
        if contour._digest(q)!=contour._digest(proposal):raise ValueError('stale_or_forged_contained_ground_portal_plan')
        before,after=[pcbnew.LoadBoard(str(p)) for p in paths]
        via,pad=_source(after,q['via_uuid'],q['allow_owned_locked'],deadline)
        matches=[i for i,row in enumerate(q['portal_menu']) if list(via.GetPosition())==row['at_nm']]
        if len(matches)!=1:raise ValueError('replacement_not_one_source_derived_contained_ground_portal')
        witness=_sweep_witnesses(after,q['source_position_nm'],tuple(via.GetPosition()),
            max(q['diameter_by_layer_nm'].values()),deadline)
        if witness!=q['portal_menu'][matches[0]]['source_swept_ground_plane_witnesses']:
            raise ValueError('same_source_swept_ground_plane_sheets_must_survive')
        with tempfile.TemporaryDirectory(prefix='cec-contained-ground-portal-') as work:
            expected=construct(paths[0],Path(work)/'expected',q,portal_index=matches[0],
                timeout_s=max(.001,deadline-time.monotonic()))
            _,nodes=additive._nodes(expected['candidate']);_,actual=additive._nodes(paths[1])
            if nodes.keys()!=actual.keys() or any(syntax._freeze(nodes[u])!=syntax._freeze(actual[u]) for u in nodes):
                raise ValueError('saved_board_differs_from_exact_inpad_barrel_and_ground_refill_replay')
        if force._sidecars(paths[0])!=force._sidecars(paths[1]):raise ValueError('inpad_portal_changed_existing_rules_or_project')
        newpads={force._uid(p):p for f in after.GetFootprints() for p in f.Pads()}
        for oldpad in [p for f in before.GetFootprints() for p in f.Pads() if p.GetNetname()=='GND']:
            contour._check_deadline(deadline)
            if force._uid(oldpad)==q['pad_uuid']:continue
            prior=cells._existing_return(before,oldpad,3.5,allow_native_track_body=True)
            if prior is None:continue
            last=cells._existing_return(after,newpads[force._uid(oldpad)],3.5,allow_native_track_body=True)
            if last is None or last[0]>prior[0]+1e-6:raise ValueError('another_actual_short_ground_return_worsened')
        oldg=[tuple(v.GetPosition()) for v in before.GetTracks() if v.GetClass()=='PCB_VIA' and v.GetNetname()=='GND']
        newg=[tuple(v.GetPosition()) for v in after.GetTracks() if v.GetClass()=='PCB_VIA' and v.GetNetname()=='GND']
        for v in before.GetTracks():
            contour._check_deadline(deadline)
            if v.GetClass()=='PCB_VIA' and v.GetNetname()!='GND':
                at=tuple(v.GetPosition())
                if min((math.dist(at,p) for p in oldg),default=math.inf)<=1500000 and min(
                        (math.dist(at,p) for p in newg),default=math.inf)>1500000:
                    raise ValueError('existing_signal_barrel_local_ground_support_lost')
        assert epoch==force._code_identity() and families==[force._family(p,q['board_hint']) for p in paths]
        r.update(ok=True,complete=True,code_identity=epoch,source_candidate_and_code_unchanged=True,
            exact_saved_ground_barrel_and_all_other_objects_replayed=True,swept_ground_plane_witnesses=witness,
            source_and_candidate_external_dogbones_mm=[0.,0.],
            source_pad_center_distance_mm=math.dist(q['source_position_nm'],tuple(pad.GetPosition()))/1e6,
            candidate_pad_center_distance_mm=math.dist(tuple(via.GetPosition()),tuple(pad.GetPosition()))/1e6,
            other_proved_ground_returns_and_signal_barrel_support_preserved=True)
    except (ValueError,KeyError,TypeError,OSError,RuntimeError,AssertionError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
