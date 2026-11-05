"""Receive a finite capacitor pivot, ordinary GND entry and obsolete leaf cut.

No nearest-IC assumption, changed capacitance, invented current, source bus
cut or enlarged outline. The physical native package may turn around the
same supply-pad centre; reoriented land geometry is disclosed, not called
an unchanged rectangular pad. A separate dead-leaf receiver owns the cut.
Full original-parent current, field, Kelvin, native DRC and stack gates still
own admission; this transaction cannot qualify a board or a converter loop.
"""
from pathlib import Path
import math,time
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_constraints as constraints
import cec_device_bypass as capacitors
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_ground_tee_tail as tails
import cec_ground_return_shortcut as reference
import cec_pose_additive_reconstruction as poses
import cec_fab_profile as fab


def context(board,pad_uuid):
    pads=[p for f in board.GetFootprints() for p in f.Pads()]
    if len(pads)+len(list(board.GetTracks()))>16384:raise ValueError('capacitor_return_repack_inventory_bound')
    matches=[p for p in pads if force._uid(p)==pad_uuid]
    if len(matches)!=1:raise ValueError('one_literal_capacitor_ground_land_required')
    pad=matches[0];fp=pad.GetParentFootprint();lands=list(fp.Pads())
    farads=capacitors.capacitance_f(fp.GetValue())
    anchors=[p for p in lands if p.GetNetname()!='GND' and p.GetNetCode()>0]
    if (not capacitors.capacitor_identity(fp.GetReference(),fp.GetFPIDAsString())
            or farads is None or not 0<farads<=1e-3 or fp.IsDNP() or fp.IsLocked() or fp.GetParentGroup()
            or any(g.ContainsItem(fp) for g in board.Groups()) or len(lands)!=2 or len(anchors)!=1
            or pad.GetNetname()!='GND' or len({p.GetNumber() for p in lands})!=2
            or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole()
                or p.GetShape() not in (pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT)
                or not 0<max(p.GetSize().x,p.GetSize().y)<=2000000 for p in lands)):
        raise ValueError('actual_unlocked_two_surface_land_capacitor_required')
    face=cells._ground_terminal_layer(pad)
    if face not in (pcbnew.F_Cu,pcbnew.B_Cu) or cells._ground_terminal_layer(anchors[0])!=face:
        raise ValueError('one_actual_capacitor_surface_required')
    return fp,pad,anchors[0],int(face)


def _assignments(board,hint):
    with force._thermal_hint(hint):r=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    return {key:dict(cap_ref=q['cap_ref'],requirement={k:q['requirement'].get(k) for k in
        ('ref','pin','rail','kind','return_rail','return_pin','max_mm','source')}) for key,q in r['assigned'].items()}


def receive(source,candidate,*,board_hint,pad_uuid,posed_candidate,seed_uuid,
            allow_locked_track_uuids=(),timeout_s=10.,per_phase_leases=False):
    r=dict(ok=False,complete=False,errors=[],current_qualified=False,routing_admitted=False,
        converter_loop_or_EM_qualified=False,fab_ready=False,release_authority=False,
        full_original_parent_current_fields_Kelvin_DRC_stack_and_release_still_required=True)
    try:
        deadline=tails.tails._deadline(timeout_s);started=time.monotonic()
        if type(per_phase_leases) is not bool:raise ValueError('explicit_bounded_capacitor_repack_phase_leases_required')
        if any(type(v) is not str or not v for v in (board_hint,pad_uuid,seed_uuid)):
            raise ValueError('explicit_source_capacitor_return_repack_context_required')
        paths=[Path(p).resolve() for p in (source,posed_candidate,candidate)]
        if len(set(paths))!=3:raise ValueError('distinct_saved_source_pose_and_leaf_cut_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        parent,posed,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        old_fp,old_pad,old_supply,face=context(parent,pad_uuid)
        new_fp,new_pad,new_supply,new_face=context(child,pad_uuid)
        before=cells._existing_return(parent,old_pad,32.,allow_native_track_body=True)
        after=cells._existing_return(child,new_pad,32.,allow_native_track_body=True)
        if (force._uid(old_fp)!=force._uid(new_fp) or force._uid(old_supply)!=force._uid(new_supply)
                or old_supply.GetNetname()!=new_supply.GetNetname() or tuple(old_supply.GetPosition())!=tuple(new_supply.GetPosition())
                or face!=new_face or before is None or after is None or not .01<after[0]<=6.
                or not after[0]<before[0]-.1):
            raise ValueError('fixed_supply_centre_and_strict_ground_return_gain_required')
        delta=(new_fp.GetOrientationDegrees()-old_fp.GetOrientationDegrees())%360
        if delta not in (90.,180.,270.) or math.dist(tuple(old_fp.GetPosition()),tuple(new_fp.GetPosition()))>2000000:
            raise ValueError('bounded_source_cardinal_capacitor_pivot_required')
        if _assignments(parent,board_hint)!=_assignments(child,board_hint):
            raise ValueError('source_selected_bypass_assignments_must_be_unchanged')
        remaining=lambda:max(.001,min(10.,deadline-time.monotonic()))
        if per_phase_leases:deadline=tails.tails._deadline(timeout_s)
        proof=poses.receive(paths[0],paths[1],selected_footprint_uuids=[force._uid(old_fp)],board_hint=board_hint,
            timeout_s=remaining(),max_shift_mm=2.,allow_field_reflow=True)
        r['independent_original_source_pose_receiving']=proof
        if not proof['ok'] or not proof['complete']:raise ValueError('source_capacitor_pose_refused:'+str(proof['errors']))
        if per_phase_leases:deadline=tails.tails._deadline(timeout_s)
        plan=tails.plan(posed,seed_uuid,allow_locked_track_uuids=allow_locked_track_uuids,timeout_s=remaining())
        leaf=tails.receive(paths[1],paths[2],plan,board_hint=board_hint,timeout_s=remaining())
        r['independent_obsolete_leaf_receiving']=leaf
        if not leaf['ok'] or not leaf['complete']:raise ValueError('source_capacitor_obsolete_leaf_refused:'+str(leaf['errors']))
        _,old=additive._nodes(paths[0]);_,mid=additive._nodes(paths[1]);_,new=additive._nodes(paths[2])
        retired=set(plan['retired_track_uuids']);added=new.keys()-old.keys();uid=force._uid(old_fp)
        if (not retired<=old.keys() or old.keys()-new.keys()!=retired or added!=mid.keys()-old.keys()
                or any(old[u][0]!='segment' for u in retired)
                or any(syntax._freeze(old[u])!=syntax._freeze(new[u]) for u in old.keys()&new.keys()
                    if u!=uid and old[u][0]!='zone')):
            raise ValueError('exact_original_capacitor_pose_GND_entry_and_old_leaf_delta_required')
        live={force._uid(t):t for t in child.GetTracks()};via=[live[u] for u in added if live[u].GetClass()=='PCB_VIA']
        tracks=[live[u] for u in added if live[u].GetClass()=='PCB_TRACK']
        if (len(via)!=1 or not 1<=len(tracks)<=8 or len(added)!=len(via)+len(tracks)
                or any(t.GetNetname()!='GND' or t.GetLayer()!=face or t.GetWidth()>350000 for t in tracks)
                or force._uid(after[1])!=force._uid(via[0])):
            raise ValueError('one_actual_new_ground_entry_and_bounded_surface_connector_required')
        geometry=cells._netclass(child,'GND')
        dia,drill,_=fab.board_legal_through_via_geometry(child,max(.6,float(geometry['via_dia'])),max(.3,float(geometry['via_drill'])))
        v=via[0]
        if (v.GetViaType()!=pcbnew.VIATYPE_THROUGH or v.TopLayer()!=pcbnew.F_Cu or v.BottomLayer()!=pcbnew.B_Cu
                or v.GetDrillValue()!=round(drill*1e6)
                or any(v.GetWidth(l)!=round(dia*1e6) for l in child.GetEnabledLayers().CuStack())):
            raise ValueError('full_ordinary_source_process_barrel_required_no_compact_via_inference')
        planes=reference._reference_contacts(child,v)
        if (epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]
                or time.monotonic()>=deadline or time.monotonic()-started>timeout_s*(3 if per_phase_leases else 1)):
            raise ValueError('capacitor_repack_sources_code_or_bounded_receiving_lease_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(paths[0]),candidate_sha256=force._hash(paths[2]),
            posed_candidate=str(paths[1]),posed_candidate_sha256=force._hash(paths[1]),
            source_candidate_families_and_code_unchanged=True,modified_footprint_uuids=[uid],
            retired_track_uuids=sorted(retired),added_native_uuids=sorted(added),new_ground_via_uuid=force._uid(v),
            source_ground_return_mm=before[0],saved_ground_return_mm=after[0],return_gain_mm=before[0]-after[0],
            source_supply_pad_uuid=force._uid(old_supply),entire_source_supply_land_unchanged=delta==180.,
            source_supply_rail=old_supply.GetNetname(),
            source_supply_land_centre_and_all_original_supply_tracks_unchanged=True,
            real_native_supply_land_reoriented_with_package=delta!=180.,source_bypass_assignments_unchanged=True,
            new_ordinary_ground_barrels=1,actual_saved_ground_reference_contacts=planes,
            no_immediate_return_or_current_capacity_qualification=True,
            main_power_buses_reference_contracts_and_interfaces_not_reconstructed=True)
        r.update(independent_bounded_phase_leases=per_phase_leases,each_native_owner_lease_s=timeout_s,
            phase_lease_count=3 if per_phase_leases else 1,elapsed_seconds=time.monotonic()-started)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
