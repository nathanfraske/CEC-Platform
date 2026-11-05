"""Recompile privately owned bypass returns to the existing board via floors.

No pose, net, group, lock, current budget or rule waiver is changed. The immutable
source's unique bypass assignment and manufacturer ground pins identify the
return. Only an unlocked ordinary barrel or the existing generated local-POFV
owner is supported. Exact saved material and native partitions are received
independently; full DRC/current/field/assembly signoff remains the caller's duty.
"""
import math
import tempfile
import time
from pathlib import Path

import pcbnew
import cec_additive_route_receiving as additive
import cec_constraints as constraints
import cec_copper_echo as sexpr
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_placement_context as motion
import cec_ordinary_route_receiving as ordinary
import cec_route_dimensions as dimensions


def _bounds(hint, cap_refs, limit, timeout_s):
    if (type(hint) is not str or not hint or type(limit) is not int or not 1<=limit<=16
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or cap_refs is not None and
            (type(cap_refs) not in (list,tuple) or not 1<=len(cap_refs)<=limit
             or any(type(ref) is not str or not ref for ref in cap_refs)
             or len(set(cap_refs))!=len(cap_refs))):
        raise ValueError('bounded_source_owned_ground_floor_scope_required')


def _plans(board,hint,cap_refs,limit,deadline):
    def tick():
        if time.monotonic()>=deadline:raise ValueError('source_owned_ground_floor_deadline')
    if (sum(fp.GetPadCount() for fp in board.GetFootprints())+len(list(board.GetTracks()))>16384):
        raise ValueError('source_owned_ground_floor_inventory_bound')
    with force._thermal_hint(hint):assignment=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    selected={}
    for row in assignment['assigned'].values():
        selected.setdefault(row['cap_ref'],[]).append(row['requirement'])
    if cap_refs is not None and not set(cap_refs)<=selected.keys():
        raise ValueError('requested_ground_floor_cap_not_source_assigned')
    scope=sorted(selected if cap_refs is None else cap_refs)
    plans=[];refused=[];deferred=0;seen=set();floor=dimensions.board_limits(board)
    for ref in scope:
        tick()
        try:
            reqs=selected[ref]
            if len(reqs)!=1:raise ValueError('ground_floor_bypass_owner_ambiguous')
            req=reqs[0];cap=board.FindFootprintByReference(ref);owner=board.FindFootprintByReference(req['ref'])
            if not cap or not owner or len(list(cap.Pads()))!=2 or cells._owner_ground_contract(owner) is None:
                raise ValueError('ground_floor_manufacturer_bypass_roles_unresolved')
            rail,pad,grounds=cells._cell_return_pads(req,owner,cap)
            if rail!='GND' or pad is None or not grounds:
                raise ValueError('ground_floor_true_ground_return_required')
            with force._thermal_hint(hint):entry=cells._existing_return(board,pad,1.5,allow_native_track_body=True)
            if entry is None:raise ValueError('ground_floor_source_return_missing')
            via=entry[1];uid=force._uid(via)
            diameter=int(via.GetWidth(via.TopLayer()));drill=int(via.GetDrillValue())
            target=dimensions.ordinary_via_geometry({},floor,requested=(diameter/1e6,drill/1e6))
            target_nm=tuple(round(value*1e6) for value in target)
            if target_nm==(diameter,drill):continue
            if uid in seen:raise ValueError('ground_floor_shared_source_barrel')
            if (via.GetViaType()!=pcbnew.VIATYPE_THROUGH or via.GetNetname()!='GND'
                    or set(via.GetLayerSet().CuStack())!=set(board.GetEnabledLayers().CuStack())
                    or any(int(via.GetWidth(layer))!=diameter for layer in via.GetLayerSet().CuStack())):
                raise ValueError('ground_floor_uniform_assigned_through_barrel_required')
            groups=[group.GetName() for group in board.Groups() if group.ContainsItem(via)]
            generated=groups==[fr.LOCAL_POFV_SIGNAL_VIA_GROUP]
            if groups and not generated or via.IsLocked() and not generated:
                raise ValueError('ground_floor_other_owner_recompile_required')
            portals=motion.local_portals(board,[ref],timeout_s=max(.001,min(10.,deadline-time.monotonic())))
            portal=next((row for row in portals if row['via_uuid']==uid),None)
            if (not portal or not portal['all_source_contacts_in_scope']
                    or {row['pad_uuid'] for row in portal['source_contacts']}!={force._uid(pad)}):
                raise ValueError('ground_floor_private_ground_portal_required')
            profile=fab.get_profile(fab.board_profile_name(board)) if fab.board_profile_name(board) else None
            if generated and not fab.pofv_dimensions(profile,*target)[0]:
                raise ValueError('ground_floor_existing_process_cannot_supply_floor')
            blocked,_=fab.via_at_pad_conflicts(board,via.GetPosition(),*target_nm,via.GetNetCode())
            if blocked is not None:raise ValueError('ground_floor_pad_or_process_conflict:'+str(cells._pad_identity(blocked)))
            holes_ok,_=cells._hole_to_hole_clear(board,via.GetPosition(),target[1],ignore_via_uuids=(uid,))
            witness={}
            spec=dimensions.project_resolver(board.GetFileName(),board=board)(via.GetNetname())
            clearance=max(int(board.GetDesignSettings().m_MinClearance),
                          math.ceil(float(spec.get('clearance') or 0)*1e6))
            if (not holes_ok or not fr._via_spot_clear(board,via.GetPosition(),target_nm[0],
                    clearance,{via.GetNetCode()},
                    drill_nm=target_nm[1],net_code=via.GetNetCode(),existing_via_uuid=uid,report=witness)
                    or not fr._edge_leg_clear(board,via.GetPosition(),via.GetPosition(),target_nm[0]//2)):
                raise ValueError('ground_floor_native_foreign_hole_or_edge_conflict:'+str(witness.get('reason')))
            seen.add(uid)
            if len(plans)>=limit:deferred+=1;continue
            plans.append(dict(cap=ref,owner=req['ref'],pin=str(req['pin']),via_uuid=uid,
                ground_pad_uuid=force._uid(pad),source_geometry_nm=[diameter,drill],target_geometry_nm=list(target_nm),
                source_position_nm=list(via.GetPosition()),source_locked=bool(via.IsLocked()),
                source_groups=groups,manufacturer_source=cells._owner_ground_contract(owner)['source'],
                ground_return_mm=entry[0],board_floor_mm=floor,private_source_portal=portal))
        except ValueError as exc:refused.append(dict(cap=ref,reason=str(exc)))
    tick()
    return plans,refused,deferred


def construct(board,*,board_hint,cap_refs=None,limit=16,timeout_s=10.):
    """Mutate only a caller's disposable native board, all-or-nothing locally."""
    _bounds(board_hint,cap_refs,limit,timeout_s)
    deadline=time.monotonic()+timeout_s
    plans,refused,deferred=_plans(board,board_hint,cap_refs,limit,deadline)
    if not plans:return dict(changed=False,complete=True,plans=[],refused=refused,deferred=deferred,
        routing_admitted=False,release_authority=False)
    vias={force._uid(via):via for via in board.GetTracks() if via.GetClass()=='PCB_VIA'}
    try:
        for row in plans:
            via=vias[row['via_uuid']];via.SetWidth(row['target_geometry_nm'][0]);via.SetDrill(row['target_geometry_nm'][1])
        # Re-test against the final set of enlarged holes, not only its source.
        for row in plans:
            via=vias[row['via_uuid']]
            if time.monotonic()>=deadline:raise ValueError('source_owned_ground_floor_deadline')
            if not cells._hole_to_hole_clear(board,via.GetPosition(),via.GetDrillValue()/1e6,
                    ignore_via_uuids=(row['via_uuid'],))[0]:
                raise ValueError('ground_floor_joint_final_holes_conflict')
    except Exception:
        for row in plans:
            via=vias[row['via_uuid']];via.SetWidth(row['source_geometry_nm'][0]);via.SetDrill(row['source_geometry_nm'][1])
        raise
    return dict(changed=True,complete=True,plans=plans,refused=refused,deferred=deferred,
        existing_locks_and_membership_unchanged=True,current_capacity_credited=False,
        exact_existing_generated_rule_rebinding_required=any(row['source_groups'] for row in plans),
        independent_saved_receiving_required=True,routing_admitted=False,release_authority=False)


def receive(source,candidate,*,board_hint,limit=16,timeout_s=10.):
    """Infer changed returns from the source; replay exact dimensions/material."""
    started=time.monotonic();r=dict(ok=False,complete=False,errors=[],release_authority=False,
        routing_admitted=False,current_qualification=False,inherited_debt_qualified=False)
    try:
        _bounds(board_hint,None,limit,timeout_s);deadline=started+timeout_s
        paths=[Path(path).resolve() for path in (source,candidate)]
        families=[force._family(path,board_hint) for path in paths];epoch=force._code_identity()
        _,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        if old.keys()!=new.keys():raise ValueError('ground_floor_native_population_changed')
        parent,child=[pcbnew.LoadBoard(str(path)) for path in paths]
        old_vias={force._uid(via):via for via in parent.GetTracks() if via.GetClass()=='PCB_VIA'}
        new_vias={force._uid(via):via for via in child.GetTracks() if via.GetClass()=='PCB_VIA'}
        if old_vias.keys()!=new_vias.keys():raise ValueError('ground_floor_barrel_population_changed')
        changed=[uid for uid in old_vias if sexpr._freeze(old[uid])!=sexpr._freeze(new[uid])]
        if not 1<=len(changed)<=limit:raise ValueError('ground_floor_changed_barrel_scope_required')
        plans,_,_=_plans(parent,board_hint,None,16,deadline)
        by_via={row['via_uuid']:row for row in plans}
        if not set(changed)<=by_via.keys():raise ValueError('ground_floor_changed_barrel_not_source_owned')
        refs=[by_via[uid]['cap'] for uid in changed]
        with tempfile.TemporaryDirectory(prefix='cec-bypass-ground-floor-') as work:
            projected=force._copy_family(paths[0],Path(work)/'projected')
            # Only the existing generated owner may rebind its exact-object
            # rule. If the immutable source is not an exact owner replay,
            # refuse rather than lower an authored native constraint.
            prior_rule=additive.bind_local_via_rule(parent,projected)
            if prior_rule.get('written'):raise ValueError('ground_floor_source_rule_not_exact_owner_replay')
            construction=construct(parent,board_hint=board_hint,cap_refs=refs,limit=limit,
                timeout_s=max(.001,min(10.,deadline-time.monotonic())))
            if not construction['changed'] or {row['via_uuid'] for row in construction['plans']}!=set(changed):
                raise ValueError('ground_floor_source_reconstruction_refused')
            additive._ground_refill(parent);field._save_field_snapshot(parent,projected)
            final_rule=additive.bind_local_via_rule(parent,projected)
            material=additive.receive(projected,paths[1],timeout_s=max(.001,min(10.,deadline-time.monotonic())))
            if not material['ok'] or not material['complete']:
                raise ValueError('ground_floor_exact_native_material_refused:'+str(material['errors']))
        original=pcbnew.LoadBoard(str(paths[0]));before=ordinary._partition(original,deadline)
        keys=set().union(*before);after=ordinary._partition(child,deadline,retained_keys=keys)
        if any(not any(component<=other for other in after) for component in before):
            raise ValueError('ground_floor_original_native_partition_lost')
        if time.monotonic()>=deadline or epoch!=force._code_identity() or families!=[force._family(path,board_hint) for path in paths]:
            raise ValueError('ground_floor_source_candidate_code_or_deadline_changed')
        r.update(ok=True,complete=True,source_owned_barrel_reconstruction=construction,
            all_original_native_components_preserved=True,unchanged_native_material_receiving=material,
            source_candidate_and_code_unchanged=True,exact_existing_generated_rule_replay=final_rule)
    except Exception as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    r['elapsed_s']=round(time.monotonic()-started,6)
    return r
