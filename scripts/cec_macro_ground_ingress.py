"""Required projected low-power Ground entries, never speculative cut credit.

An exact Source SMD terminal and its existing process rule own the proposed
column. A foreign lead may be reconstructed for that column only when the
complete macro is also obliged to build it. Saved receiving rederives the
Source and observes the actual new barrel and every declared reference face.
No main-current/Ground mesh, new rule, guessed load or hole-size waiver.
"""
import hashlib,json,time,uuid
from pathlib import Path
import pcbnew
import cec_cell_row_rebuild as row
import cec_decoupler_cell as cell
import cec_device_power_roles as roles
import cec_existing_local_pofv_pad_rule as local_rule
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_ground_return_shortcut as reference
import cec_measurement_leaf as leaf
import cec_native_placement_context as native
import cec_ordinary_route_receiving as ordinary


def plan(parent,private,proposal,pad_uuids,*,timeout_s=10.):
    if type(timeout_s) not in (int,float) or not 0<timeout_s<=10.:
        raise ValueError('bounded_required_projected_ground_entry_lease')
    deadline=time.monotonic()+timeout_s
    ids=ordinary._ids(pad_uuids,'required_projected_ground_entry',4)
    if not ids:return [],[]
    source=Path(parent.GetFileName()).resolve();digest=force._hash(source)
    old={force._uid(p):p for f in parent.GetFootprints() for p in f.Pads()}
    live={force._uid(p):p for f in private.GetFootprints() for p in f.Pads()}
    if not ids<=old.keys() or not ids<=live.keys():raise ValueError('literal_required_ground_entry_pad')
    profile_name=fab.board_profile_name(private);profile=fab.get_profile(profile_name)
    geometry=fab.preferred_pofv_geometry(profile) if profile else None
    if not geometry or not fab.pofv_dimensions(profile,*geometry)[0]:
        raise ValueError('existing_declared_required_ground_entry_process')
    diameter,drill=[round(v*1e6) for v in geometry];proofs=[];columns=[]
    for uid in sorted(ids):
        if time.monotonic()>=deadline:raise ValueError('required_ground_entry_plan_deadline')
        before,pad=old[uid],live[uid];fp=pad.GetParentFootprint();ref=fp.GetReference()
        model=roles.footprint_contract(before.GetParentFootprint())
        if model:
            role=model['pins'].get(before.GetNumber())
            if role not in ('ground','reference','power_return') or set(model['pins'].values())&{'power_output','switch','feedback'}:
                raise ValueError('positive_nonconverter_required_ground_entry_owner')
            authority=dict(kind='manufacturer_ground_terminal',role=role,source=model['source'])
        else:
            authority=dict(kind='selected_low_power_bypass_ground',selected=leaf._bypass_supply_owner(
                parent,before,proposal['board_hint'],ground_return=True))
        face=cell.cec_return_escape.smd_surface_layer(pad)
        if (ref not in proposal['poses'] or pad.GetNetname()!='GND' or before.GetNetname()!='GND'
                or face is None or pad.HasHole() or fp.IsDNP() or fp.IsLocked()
                or (tuple(before.GetPosition())==tuple(pad.GetPosition())
                    and before.GetEffectivePolygon(face).Format()==pad.GetEffectivePolygon(face).Format())):
            raise ValueError('actual_moved_source_surface_ground_terminal_required')
        previous=cell._existing_return(parent,before,16.,allow_native_track_body=True)
        if previous is None:raise ValueError('known_original_required_ground_return')
        context=local_rule.resolve(private,pad)
        ordinary_geometry=fab.board_legal_through_via_geometry(private,*geometry)[:2]==tuple(geometry)
        if not ordinary_geometry and (context is None or diameter<context['minimum_nm']['via_diameter']
                or drill<context['minimum_nm']['hole_size']
                or (diameter-drill)//2<context['minimum_nm']['annular_width']):
            raise ValueError('existing_saved_required_ground_entry_rule')
        duplicates=[force._uid(t) for t in private.GetTracks()
            if t.GetClass()=='PCB_VIA' and tuple(t.GetPosition())==tuple(pad.GetPosition())]
        if duplicates:
            raise ValueError('required_ground_column_must_be_new_not_duplicate:'+uid+':'+','.join(sorted(duplicates)))
        column=pcbnew.PCB_VIA(private);column.SetNet(pad.GetNet());column.SetPosition(pad.GetPosition())
        column.SetWidth(diameter);column.SetDrill(drill);column.SetViaType(pcbnew.VIATYPE_THROUGH)
        column.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        name='required-source-ground:'+digest+':'+uid+':'+repr(tuple(pad.GetPosition()))
        column.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,name))))
        land=pcbnew.SHAPE_POLY_SET();pad.TransformShapeToPolygon(land,face,0,1000,pcbnew.ERROR_INSIDE)
        disk=pcbnew.SHAPE_POLY_SET();column.TransformShapeToPolygon(disk,face,0,1000,pcbnew.ERROR_OUTSIDE)
        disk.BooleanSubtract(land)
        if disk.OutlineCount():raise ValueError('entire_required_ground_column_must_fit_actual_land')
        if (not fr._edge_leg_clear(private,pad.GetPosition(),pad.GetPosition(),diameter//2)
                or not cell._hole_to_hole_clear(private,pad.GetPosition(),drill/1e6)[0]):
            raise ValueError('required_ground_column_existing_edge_or_drill_conflict')
        material=native._native_stationary_land(pad,deadline)
        if material is None:raise ValueError('required_ground_native_land_unknown')
        # Numeric net allocation changes on save; native net NAME, UUID and
        # layer polygons, not an allocator ordinal, bind the actual land.
        stable=material[:3]+material[4:]
        proof=dict(schema=1,scope='source_required_projected_ground_column',source=str(source),
            source_sha256=digest,source_native_binding=row._source_binding(parent),board_hint=proposal['board_hint'],
            pad_uuid=uid,owner=ref,target_pose=list(proposal['poses'][ref]),face=int(face),
            point_nm=list(pad.GetPosition()),diameter_nm=diameter,drill_nm=drill,profile=profile_name,
            source_return_mm=previous[0],source_role=authority,existing_local_rule=context,
            actual_land_sha256=hashlib.sha256(repr(stable).encode()).hexdigest(),
            proposal_column_uuid=force._uid(column),mandatory_new_saved_barrel=True,
            no_new_rule_or_floor_or_current_credit=True,release_authority=False)
        proofs.append(proof);columns.append(column)
    return proofs,columns


def rederive(board,proof,*,timeout_s=10.):
    source=Path(proof['source'])
    if force._hash(source)!=proof['source_sha256']:raise ValueError('required_ground_source_changed')
    parent=pcbnew.LoadBoard(str(source))
    q,_=plan(parent,board,dict(poses={proof['owner']:proof['target_pose']},board_hint=proof['board_hint']),
        [proof['pad_uuid']],timeout_s=timeout_s)
    if json.loads(json.dumps(q[0]))!=proof:raise ValueError('required_ground_entry_stale_or_forged')
    return proof


def required_ops(proof,ops):
    vias=[op for op in ops if op[0]=='via']
    return bool(len(vias)==1 and list(vias[0][1])==proof['point_nm']
        and round(vias[0][2]*1e6)==proof['drill_nm'] and round(vias[0][3]*1e6)==proof['diameter_nm'])


def entry_ops(board,proof,*,timeout_s=10.):
    """Offer the promised column, not an unrelated first-success dogbone.

    Ordinary return search may legitimately prefer a nearby retained barrel.
    That cannot satisfy a Source cut funded by this exact required column.
    Reprove its land/process/Source, actual all-face copper and holes, and
    filled reference contacts before offering it. Nothing is added here.
    """
    started=time.monotonic();rederive(board,proof,timeout_s=timeout_s)
    pad=next(p for f in board.GetFootprints() for p in f.Pads() if force._uid(p)==proof['pad_uuid'])
    point=pad.GetPosition();diameter=proof['diameter_nm'];drill=proof['drill_nm']
    gap=max(200000,int(board.GetDesignSettings().m_MinClearance),int(cell._netclass(board,'GND')['clearance']))
    via=pcbnew.PCB_VIA(board);via.SetNet(pad.GetNet());via.SetPosition(point)
    via.SetWidth(diameter);via.SetDrill(drill);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    detail=dict(scope='exact_required_native_ground_entry_offer',found=False,
        no_new_native_material=True,no_path_proof=False,release_authority=False)
    process,reason=fab.local_pofv_via_decision(board,via)
    detail['process_ok']=bool(process);detail['process_reason']=reason
    spot={}
    clear=bool(process and fr._edge_leg_clear(board,point,point,diameter//2)
        and cell._hole_to_hole_clear(board,point,drill/1e6)[0]
        and fr._via_spot_clear(board,point,diameter,gap,{pad.GetNetCode()},
            drill_nm=drill,net_code=pad.GetNetCode(),contained_layers={proof['face']},
            local_pofv_pad=pad,foreign_cache={},report=spot))
    detail['native_column_admission']=spot
    if clear:
        try:detail['reference_contacts']=reference._reference_contacts(board,via)
        except ValueError as exc:
            clear=False;detail['reference_refusal']=str(exc)
    if time.monotonic()-started>=timeout_s:
        raise ValueError('required_ground_entry_native_offer_deadline')
    detail['found']=clear
    return ([('via',tuple(point),drill/1e6,diameter/1e6)] if clear else []),detail


def receive(board,proofs,incoming,*,timeout_s=10.):
    deadline=time.monotonic()+timeout_s;observed=[]
    for proof in proofs:
        if time.monotonic()>=deadline:raise ValueError('required_ground_saved_observation_deadline')
        pads=[p for f in board.GetFootprints() for p in f.Pads() if force._uid(p)==proof['pad_uuid']]
        if len(pads)!=1:raise ValueError('required_saved_ground_pad_missing')
        pad=pads[0]
        material=native._native_stationary_land(pad,deadline);stable=material[:3]+material[4:] if material else None
        if stable is None or hashlib.sha256(repr(stable).encode()).hexdigest()!=proof['actual_land_sha256']:
            raise ValueError('required_saved_ground_land_changed')
        matches=[t for t in board.GetTracks() if force._uid(t) in incoming and t.GetClass()=='PCB_VIA'
            and t.GetNetname()=='GND' and list(t.GetPosition())==proof['point_nm']
            and int(t.GetDrillValue())==proof['drill_nm'] and t.GetViaType()==pcbnew.VIATYPE_THROUGH
            and t.TopLayer()==pcbnew.F_Cu and t.BottomLayer()==pcbnew.B_Cu
            and all(t.GetWidth(l)==proof['diameter_nm'] for l in board.GetEnabledLayers().CuStack())]
        if len(matches)!=1:raise ValueError('required_new_saved_ground_column_not_constructed')
        via=matches[0]
        if not fab.local_pofv_via_decision(board,via)[0]:raise ValueError('required_saved_ground_process_not_reproved')
        contacts=reference._reference_contacts(board,via)
        observed.append(dict(pad_uuid=proof['pad_uuid'],via_uuid=force._uid(via),
            reference_contacts=contacts,exact_required_column_constructed=True,release_authority=False))
    return observed
