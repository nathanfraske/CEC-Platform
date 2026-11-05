"""Fresh canonical EN/control-shunt passive placement identity, never bypass authority."""
import math
import time
import copy
import contextvars
from contextlib import contextmanager
import pcbnew
import cec_force_current as force
import cec_source_ground_leaf as leaf
import cec_cell_row_rebuild as row
import cec_device_power_roles as roles
import cec_source_netlist_semantics as semantic

PROOF_REPRESENTATION='source_control_shunt_full_semantic_export_identity-v1'
_export_evidence=contextvars.ContextVar('control_shunt_raw_export_evidence',default=None)


@contextmanager
def capture_exports():
    """Optional diagnostic evidence, deliberately outside replayable contracts."""
    observations=[];token=_export_evidence.set(observations)
    try:yield observations
    finally:_export_evidence.reset(token)


def _canonical_source_proof(raw_proof):
    proof=semantic.replay_identity(raw_proof)
    proof['proof_representation']=PROOF_REPRESENTATION
    return proof


def _require(ok,reason):
    if not ok:raise ValueError(reason)


def _complete_owner_motion(board,owner,poses,*,board_hint,deadline):
    """Positive whole-device/follower context, not stand-alone pose authority.

    The old stationary control-passive scope remains the default. A moving
    owner needs a complete supported manufacturer map, fresh canonical
    names/types/nets, and every Source-selected bypass in the same cohort.
    No signal is reclassified and no old departure may be discarded here.
    """
    target=poses.get(owner.GetReference())
    if target is None:return None
    _require(type(target)in(list,tuple)and len(target)==3
        and all(type(v)in(int,float)and math.isfinite(v)for v in target),'finite_control_owner_pose_required')
    if (tuple(round(v*1e6)for v in target[:2])==tuple(owner.GetPosition())
            and abs((target[2]-owner.GetOrientationDegrees()+180)%360-180)<1e-9):return None
    _require(not owner.IsLocked()and not owner.IsDNP()and not owner.GetParentGroup()
        and math.dist(tuple(owner.GetPosition()),[round(v*1e6)for v in target[:2]])<=32e6
        and (target[2]-owner.GetOrientationDegrees())%90==0,'bounded_unlocked_complete_control_owner_required')
    model=roles.footprint_contract(owner)
    _require(model is not None and not set(model['pins'].values())&{'power_output','switch','feedback'},
        'complete_low_power_control_owner_model_required')
    _require(time.monotonic()<deadline,'complete_control_owner_source_deadline')
    roles.physical_pinmap(owner,model,board_hint=board_hint,
        timeout_s=min(8.,max(.001,deadline-time.monotonic())))
    _require(time.monotonic()<deadline,'complete_control_owner_source_deadline')
    if any(p.GetPinFunction()or p.GetPinType()for p in owner.Pads()):
        import cec_source_device_pinmap as source_pinmap
        source_pinmap.prove(owner,model,board_hint=board_hint,
            timeout_s=min(8.,max(.001,deadline-time.monotonic())))
    import cec_constraints as constraints
    with force._thermal_hint(board_hint):
        assignment=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    selected=[v for v in assignment['assigned'].values()if v['requirement']['ref']==owner.GetReference()]
    _require(selected and not any(v['ref']==owner.GetReference()
        for v in assignment.get('missing',[])), 'complete_source_selected_control_owner_bypasses_required')
    followers=[]
    for selected_cap in selected:
        requirement=selected_cap['requirement'];ref=selected_cap['cap_ref']
        cap=board.FindFootprintByReference(ref)
        _require(ref in poses and cap is not None and model['pins'].get(str(requirement['pin']))=='power_input'
            and (requirement.get('return_rail')or'GND')=='GND'
            and len(list(cap.Pads()))==2 and {p.GetNetname()for p in cap.Pads()}=={requirement['rail'],'GND'},
            'complete_source_selected_control_owner_followers_required')
        followers.append(dict(ref=ref,owner=owner.GetReference(),pin=str(requirement['pin']),rail=requirement['rail']))
    binding=row._source_binding(board)
    _require(time.monotonic()<deadline,'complete_control_owner_source_deadline')
    return dict(scope='complete_source_typed_control_owner_cohort',owner=owner.GetReference(),
        owner_uuid=force._uid(owner),source_native_binding=binding,
        manufacturer=model,target_pose=list(target),selected_followers=sorted(followers,key=lambda v:v['ref']),
        current_authority=False,trace_retirement_authority=False,placement_admitted=False)


def _receive_complete_owner_motion(source,posed,item,poses,*,board_hint,deadline):
    """Same Source-owned physical package at its literal requested rigid pose."""
    original=source.FindFootprintByReference(item['owner']);owner=posed.FindFootprintByReference(item['owner'])
    _require(original is not None and owner is not None
        and _complete_owner_motion(source,original,poses,board_hint=board_hint,deadline=deadline)==item,
        'fresh_complete_control_owner_motion_required')
    expected=pcbnew.FOOTPRINT(original);target=item['target_pose']
    expected.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in target[:2])));expected.SetOrientationDegrees(target[2])
    import cec_source_current_pad_ports as ports
    _require(force._uid(owner)==force._uid(original)and owner.GetValue()==original.GetValue()
        and owner.GetFPIDAsString()==original.GetFPIDAsString()
        and leaf.footprint_properties(owner)==leaf.footprint_properties(original)
        and owner.GetAttributes()==original.GetAttributes()and owner.IsDNP()==original.IsDNP()
        and owner.IsLocked()==original.IsLocked()and owner.IsFlipped()==original.IsFlipped()
        and not owner.GetParentGroup()
        and tuple(owner.GetPosition())==tuple(expected.GetPosition())
        and abs((owner.GetOrientationDegrees()-expected.GetOrientationDegrees()+180)%360-180)<1e-9
        and sorted(ports._pad_identity(p)for p in owner.Pads())==sorted(ports._pad_identity(p)for p in expected.Pads()),
        'complete_control_owner_rigid_physical_package_changed')
    _require(time.monotonic()<deadline,'complete_control_owner_receive_deadline')


def _reference_group_scope(reference_group_uuids):
    _require(type(reference_group_uuids)in(list,tuple)and len(reference_group_uuids)<=8
        and all(type(u)is str and u for u in reference_group_uuids)
        and len(set(reference_group_uuids))==len(reference_group_uuids),
        'explicit_unique_source_reference_groups_required')


def _reference_group_authorizations(board,poses,reference_group_uuids,*,binding,deadline):
    """Shared canonical passive annotation opt-in; no physical move authority.

    Both control-shunt and pull-up compilers use the same saved-Source map
    recognition. Arbitrary/changed/nested groups still refuse. The complete
    macro independently transports and receives the exact drawing geometry.
    """
    _reference_group_scope(reference_group_uuids)
    # Recognition is fresh against the literal saved Source, never a caller
    # assertion or permission to unlock/ungroup a physical component.
    authorized={}
    if reference_group_uuids:
        import cec_source_reference_group_transport as mapping
        saved=pcbnew.LoadBoard(board.GetFileName())
        _require(saved is not None and row._source_binding(saved)==binding,
            'exact_saved_source_reference_group_board_required')
        selections=[]
        for gid in reference_group_uuids:
            matching=[g for g in board.Groups()if force._uid(g)==gid]
            _require(len(matching)==1,'one_actual_requested_reference_group_required')
            fps=[i for i in matching[0].GetItems()if i.GetClass()=='FOOTPRINT']
            _require(len(fps)==1 and fps[0].GetReference()in poses,
                'requested_reference_group_owner_must_be_in_poses')
            selections.append((force._uid(fps[0]),gid))
        proofs=mapping.inspect_many(board.GetFileName(),selections,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        import cec_reference_map_reownership as map_geometry
        def ink_inventory(owner,contract):
            items={force._uid(i):i for i in owner.GetDrawings()}
            return {u:map_geometry._geometry(items[u]) for u in contract['member_uuids']
                if u!=contract['owner_uuid']}
        for contract in proofs:
            live_group=next(g for g in board.Groups()if force._uid(g)==contract['group_uuid'])
            _require(ink_inventory(board,contract)==ink_inventory(saved,contract)
                and bool(live_group.IsLocked())==contract['group_locked'],
                'exact_saved_source_reference_group_ink_required')
            cap=next(f for f in board.GetFootprints()if force._uid(f)==contract['owner_uuid'])
            target=poses[cap.GetReference()]
            _require(type(target)in(list,tuple)and len(target)==3
                and all(type(v)in(int,float)and math.isfinite(v)for v in target),
                'finite_control_shunt_pose_required')
            _require((target[2]-cap.GetOrientationDegrees())%90==0,
                'source_reference_group_exact_cardinal_only')
            authorized[force._uid(cap)]=contract
    return authorized


def plan(board,poses,*,board_hint,timeout_s=10.,reference_group_uuids=()):
    _require(type(poses)is dict and 1<=len(poses)<=8 and type(board_hint)is str and bool(board_hint)
        and type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,
        'bounded_control_shunt_placement_context_required')
    start=time.monotonic();deadline=start+timeout_s;binding=row._source_binding(board)
    _reference_group_scope(reference_group_uuids)
    candidates=leaf._candidates(board)
    selected=[v for v in candidates.values()if v[1]=='source_control_shunt_ground'
        and v[0].GetParentFootprint().GetReference()in poses]
    if not selected:return {}
    authorized=_reference_group_authorizations(board,poses,reference_group_uuids,
        binding=binding,deadline=deadline)
    proof=leaf.plan(board,board_hint=board_hint,timeout_s=max(.001,deadline-time.monotonic()))
    _require(proof.get('complete')and not proof.get('errors'),'complete_canonical_control_shunt_source_proof_required')
    groups={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    import cec_additive_route_receiving as additive
    groups.update(u for n in additive._nodes(board.GetFileName())[1].values()if n[0]=='group'for u in additive._members(n))
    result={}
    for ground,kind,witness,control in selected:
        _require(time.monotonic()<deadline,'control_shunt_source_deadline')
        cap=ground.GetParentFootprint();owner=control.GetParentFootprint();ref=cap.GetReference()
        pads=list(cap.Pads());uid=force._uid(ground);source=proof.get('proofs',{}).get(uid)
        _require(source is not None and source.get('kind')==kind and source.get('owner')==ref
            and source.get('pin')==ground.GetNumber()and source.get('net')=='GND'
            and source.get('manufacturer')==roles.control_shunt_input_contract(owner,control.GetNumber())
            and source.get('manufacturer')==witness,'exact_canonical_control_shunt_witness_required')
        canonical_source=_canonical_source_proof(source)
        observations=_export_evidence.get()
        if observations is not None:
            _require(len(observations)<128,'bounded_control_shunt_raw_export_observations_required')
            observations.append(dict(owner=ref,source_native_binding=binding,raw_source_proof=copy.deepcopy(source)))
        _require(len(pads)==2 and len({p.GetNumber()for p in pads})==2
            and all(p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and not p.HasHole()for p in pads)
            and not cap.IsLocked()and not cap.IsDNP()
            and ((not cap.GetParentGroup()and force._uid(cap)not in groups)
                or force._uid(cap)in authorized)
            and all(not p.IsLocked()and force._uid(p)not in groups for p in pads),
            'unlocked_ungrouped_populated_two_land_control_shunt_required')
        signal=next(p for p in pads if force._uid(p)!=uid)
        _require(signal.GetNetCode()>0 and signal.GetNetname()==control.GetNetname()
            and signal.GetNetname()!='GND','exact_control_shunt_signal_net_required')
        peers=[v for v in candidates.values()if v[1]==kind and v[3]is not None
            and force._uid(v[3])==force._uid(control)]
        _require(len(peers)==1,'unique_source_control_shunt_cap_required')
        owner_motion=_complete_owner_motion(board,owner,poses,board_hint=board_hint,deadline=deadline)
        target=poses[ref]
        _require(type(target)in(list,tuple)and len(target)==3
            and all(type(v)in(int,float)and math.isfinite(v)for v in target),'finite_control_shunt_pose_required')
        result[ref]=dict(cap_uuid=force._uid(cap),ground_pad_uuid=uid,signal_pad_uuid=force._uid(signal),
            control_owner=owner.GetReference(),control_owner_uuid=force._uid(owner),control_pad_uuid=force._uid(control),
            control_pin=control.GetNumber(),net=str(signal.GetNetname()),source_proof=canonical_source,
            source_native_binding=binding,role='source_control_shunt_passive',bypass_owner=False,
            current_authority=False,reset_timing_qualified=False,release_authority=False)
        if force._uid(cap)in authorized:
            result[ref]['source_reference_group_authorization']=authorized[force._uid(cap)]
        if owner_motion is not None:result[ref]['source_complete_owner_motion']=owner_motion
    _require(time.monotonic()<deadline and binding==row._source_binding(board)
        and leaf.bindings_current([v['source_proof']for v in result.values()]),'control_shunt_source_binding_changed')
    return result


def requests(source,board,proposal,*,timeout_s=10.):
    deadline=time.monotonic()+timeout_s
    selected=proposal.get('selected_control_shunts',{})
    if not selected:return {}
    fresh=plan(source,proposal['poses'],board_hint=proposal['board_hint'],timeout_s=timeout_s,
        reference_group_uuids=proposal.get('reference_group_uuids',()))
    _require(fresh==selected,'fresh_source_control_shunt_proposal_required')
    import cec_decoupler_cell as cell
    requests={};pads={force._uid(p):p for f in board.GetFootprints()for p in f.Pads()}
    originals={force._uid(p):p for f in source.GetFootprints()for p in f.Pads()}
    def end(p):return dict(pad_uuid=force._uid(p),at_nm=list(p.GetPosition()),layers=list(map(int,p.GetLayerSet().CuStack())))
    for ref,item in selected.items():
        ground,signal,control=(pads.get(item[k])for k in('ground_pad_uuid','signal_pad_uuid','control_pad_uuid'))
        _require(all(p is not None for p in(ground,signal,control)),'actual_projected_control_shunt_lands_required')
        for p in(ground,signal,control):
            old=originals[force._uid(p)]
            _require(p.GetNumber()==old.GetNumber()and p.GetNetname()==old.GetNetname()
                and force._uid(p.GetParentFootprint())==force._uid(old.GetParentFootprint())
                and list(p.GetLayerSet().CuStack())==list(old.GetLayerSet().CuStack()),'control_shunt_projected_pin_net_face_changed')
        owner=control.GetParentFootprint();original=source.FindFootprintByReference(item['control_owner'])
        if 'source_complete_owner_motion'in item:
            _receive_complete_owner_motion(source,board,item['source_complete_owner_motion'],proposal['poses'],
                board_hint=proposal['board_hint'],deadline=deadline)
        else:
            _require(tuple(owner.GetPosition())==tuple(original.GetPosition())
                and owner.GetOrientationDegrees()==original.GetOrientationDegrees()
                and owner.IsFlipped()==original.IsFlipped(),'control_shunt_stationary_owner_changed')
        width=max(int(board.GetDesignSettings().m_TrackMinWidth),int(cell._netclass(board,item['net'])['width']))
        _require(width>0,'source_control_shunt_signal_width_required')
        requests['control_shunt:'+item['signal_pad_uuid']]=dict(kind='source_boundary',net=item['net'],
            a=end(signal),b=end(control),width_nm=width,source_control_shunt=item,
            no_power_bypass_or_current_authority=True)
        # The existing complete-cell Ground compiler separately requires the
        # actual moved Ground land's native immediate return; never discharge
        # it merely because EN has a request or owner is stationary.
    return requests
