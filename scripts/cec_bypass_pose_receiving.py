"""Receive bounded native bypass motion without rewriting protected copper.

Ownership comes from the immutable source's selected-device bypass inventory,
not a worker's ref/pose allowlist. Reconstruct the exact native footprint
transforms, retain every old conductor/terminal partition, and independently
replay only additive local copper, existing GND fills, and exact-object rules.
Native DRC, placement, field, current and Kelvin admission remain mandatory.
"""
from pathlib import Path
import math
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_constraints as constraints
import cec_copper_echo as sexpr
import cec_decoupler_cell as cell
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary


def receive(source,candidate,*,board_hint,timeout_s=10.,max_shift_mm=6.,max_caps=4,
            return_reach_mm=.8):
    result=dict(schema=1,scope='source_selected_bypass_pose_receiving',ok=False,
        complete=False,errors=[],release_authority=False,power_authority=False,
        inherited_debt_qualified=False,retired_track_uuids=[])
    started=time.monotonic()
    try:
        if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=30
                or type(max_shift_mm) not in (int,float) or not math.isfinite(max_shift_mm)
                or not 0<max_shift_mm<=6 or type(max_caps) is not int or not 1<=max_caps<=4
                or type(return_reach_mm) not in (int,float) or not math.isfinite(return_reach_mm)
                or not 0<return_reach_mm<=1.5 or type(board_hint) is not str or not board_hint):
            raise ValueError('invalid_bypass_pose_bounds_or_identity')
        deadline=started+timeout_s
        paths=[Path(p).resolve() for p in (source,candidate)]
        families=[force._family(p,board_hint) for p in paths];code=force._code_identity()
        _,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        if not old.keys()<=new.keys():raise ValueError('bypass_pose_cannot_retire_native_material')
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        first={force._uid(fp):fp for fp in parent.GetFootprints()}
        last={force._uid(fp):fp for fp in child.GetFootprints()}
        if first.keys()!=last.keys():raise ValueError('bypass_footprint_population_changed')
        moved={u for u in first if sexpr._freeze(old[u])!=sexpr._freeze(new[u])}
        if not 1<=len(moved)<=max_caps:raise ValueError('outside_bounded_selected_bypass_scope')
        grouped={force._uid(i) for g in parent.Groups() for i in g.GetItems()}
        with force._thermal_hint(board_hint):
            assigned=constraints._device_bypass_assignment(parent,project_max_mm=3.5)
            final_assigned=constraints._device_bypass_assignment(child,project_max_mm=3.5)
        by_cap={};final_by_cap={}
        for row in assigned['assigned'].values():by_cap.setdefault(row['cap_ref'],[]).append(row['requirement'])
        for row in final_assigned['assigned'].values():final_by_cap.setdefault(row['cap_ref'],[]).append(row['requirement'])
        proofs=[]
        for uid in sorted(moved):
            if time.monotonic()>=deadline:raise ValueError('bypass_pose_receiving_deadline')
            before,after=first[uid],last[uid];reqs=by_cap.get(before.GetReference(),[])
            final_reqs=final_by_cap.get(before.GetReference(),[])
            pads=list(before.Pads())
            if (len(reqs)!=1 or len(final_reqs)!=1 or before.IsLocked() or uid in grouped
                    or len(pads)!=2 or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole() for p in pads)
                    or before.IsFlipped()!=after.IsFlipped()):
                raise ValueError('not_an_unlocked_unique_two_land_bypass')
            req=reqs[0]
            role=lambda r:(r['ref'],str(r['pin']),r['rail'],r.get('return_rail') or 'GND')
            if role(req)!=role(final_reqs[0]):raise ValueError('selected_bypass_owner_changed')
            if (req.get('return_rail') or 'GND')!='GND':raise ValueError('rail_to_rail_cell_needs_separate_pose_contract')
            source_supply=next(p for p in before.Pads() if p.GetNetname()==req['rail'])
            source_ground=next(p for p in before.Pads() if p.GetNetname()=='GND')
            target_supply=next((p for p in after.Pads() if p.GetNetname()==req['rail']),None)
            target_owner=child.FindFootprintByReference(req['ref'])
            target_pin=target_owner.FindPadByNumber(str(req['pin'])) if target_owner else None
            if target_supply is None or target_pin is None:raise ValueError('bypass_supply_identity_missing')
            prior_supply=math.dist(force._point(req['pad']),force._point(source_supply))/1e6
            final_supply=math.dist(force._point(target_pin),force._point(target_supply))/1e6
            prior_path=cell._shortest_track_path_mm(parent,req['pad'],source_supply)
            final_path=cell._shortest_track_path_mm(child,target_pin,target_supply)
            prior_ground=cell._existing_return(parent,source_ground,1.5,allow_native_track_body=True)
            prior_topology=(cell._existing_return_topology(parent,source_ground,prior_ground[1])
                if prior_ground is not None else {})
            a,b=before.GetPosition(),after.GetPosition()
            shift=math.hypot(a.x-b.x,a.y-b.y)/1e6
            delta=(after.GetOrientationDegrees()-before.GetOrientationDegrees())%360
            if shift>max_shift_mm or not any(abs(delta-v)<1e-5 for v in (0.,90.,180.,270.)):
                raise ValueError('bypass_pose_outside_translation_or_quarter_turn_bound')
            ground=next((p for p in after.Pads() if p.GetNetname()=='GND'),None)
            if ground is None:raise ValueError('bypass_return_identity_missing')
            with force._thermal_hint(board_hint):
                # A small native land translation can keep its exact old
                # trace contact while moving the land centre onto the
                # interior of that trace. Use the same positively measured
                # native body path as whole-board Ground preservation;
                # endpoint-only lookup falsely reports this as an open.
                # Actual gaps, process, partitions and clearances remain
                # independently checked below and by additive receiving.
                entry=cell._existing_return(child,ground,return_reach_mm,allow_native_track_body=True)
                if entry is None:raise ValueError('moved_bypass_has_no_immediate_native_ground_entry')
                via=entry[1]
                blocked,_=fab.via_at_pad_conflicts(child,via.GetPosition(),via.GetWidth(via.TopLayer()),
                    via.GetDrillValue(),via.GetNetCode())
                if blocked is not None:raise ValueError('moved_bypass_ground_entry_not_process_qualified:'+str(blocked))
            final_topology=cell._existing_return_topology(child,ground,via)
            retained_vip=bool(prior_ground is not None and force._uid(prior_ground[1])==force._uid(via)
                and prior_topology.get('topology_qualified') is True
                and final_topology.get('topology_qualified') is True)
            prior_return=prior_ground[0] if prior_ground is not None else None
            # In-pad equivalence is exact native containment on the SAME old
            # qualified barrel, not a distance/annular-ring waiver. A small
            # bypass translation may keep the via fully in-pad off-centre.
            nonworse=bool(final_supply<=prior_supply+1e-6 and final_path is not None
                and (prior_path is None or final_path<=prior_path+1e-6)
                and (prior_return is None or entry[0]<=prior_return+1e-6 or retained_vip))
            improved=bool(final_supply<prior_supply-.01 or prior_path is None
                or (final_path is not None and final_path<(prior_path or 0)-.01)
                or prior_return is None or entry[0]<(prior_return or 0)-.01)
            # Reconstruct from the immutable parent's complete native package,
            # not the candidate's fields/pad definitions or rounded footprint.
            before.SetPosition(after.GetPosition());before.SetOrientationDegrees(after.GetOrientationDegrees())
            proofs.append(dict(uuid=uid,ref=after.GetReference(),owner=req['ref'],pin=str(req['pin']),
                rail=req['rail'],return_rail='GND',shift_mm=shift,rotation_delta_deg=delta,
                ground_via_uuid=force._uid(via),ground_path_mm=entry[0],
                native_PI_metrics=dict(before=dict(supply_mm=prior_supply,supply_path_mm=prior_path,
                    ground_path_mm=prior_return),after=dict(supply_mm=final_supply,
                    supply_path_mm=final_path,ground_path_mm=entry[0]),
                    original_qualified_via_still_fully_in_pad=retained_vip,
                    nonworse=nonworse,improved=improved)))
        with tempfile.TemporaryDirectory(prefix='cec-bypass-pose-receiving-') as work:
            projected=force._copy_family(paths[0],Path(work)/'projected')
            field._save_field_snapshot(parent,projected)
            _,replayed=additive._nodes(projected)
            if (replayed.keys()!=old.keys() or any(sexpr._freeze(replayed[u])!=sexpr._freeze(
                    new[u] if u in moved else old[u]) for u in old)):
                raise ValueError('received_pose_is_not_exact_native_source_transform')
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ValueError('bypass_pose_receiving_deadline')
            proof=additive.receive(projected,paths[1],timeout_s=min(30.,remaining))
            result['exact_native_pose_additive_ground_rule_replay']=proof
            if proof.get('ok') is not True or proof.get('complete') is not True:
                raise ValueError('independent_bypass_pose_delta_refused')
        # Use the original, unmoved source here: a moved pad must keep its
        # entire old component, including copper-only tees and GND barrels.
        original=pcbnew.LoadBoard(str(paths[0]))
        old_parts=ordinary._partition(original,deadline)
        retained=set().union(*old_parts)
        original_fps={force._uid(fp):fp for fp in original.GetFootprints()}
        rebindings={}
        for uid in moved:
            old_pads={force._uid(p):p for p in original_fps[uid].Pads()}
            new_pads={force._uid(p):p for p in last[uid].Pads()}
            if len(old_pads)!=2 or old_pads.keys()!=new_pads.keys():
                raise ValueError('ambiguous_moved_bypass_pad_identity')
            for pad_id,pad in old_pads.items():
                rebindings[force._item_key(new_pads[pad_id])]=force._item_key(pad)
        new_parts=ordinary._partition(child,deadline,retained_keys=retained,
            _identity_rebindings=rebindings)
        if any(not any(p<=q for q in new_parts) for p in old_parts):
            raise ValueError('moved_bypass_lost_original_native_component')
        stable=families==[force._family(p,board_hint) for p in paths] and code==force._code_identity()
        if not stable or time.monotonic()>=deadline:raise ValueError('bypass_pose_identity_or_deadline_changed')
        result.update(ok=True,complete=True,source_candidate_and_code_unchanged=True,
            moved_bypasses=proofs,added_native_uuids=proof['added_native_uuids'],
            original_owner_power_pair_and_sense_copper_exact=True,
            all_prior_native_terminal_and_copper_partitions_preserved=True,
            independently_measured_local_PI_progress=bool(
                all(p['native_PI_metrics']['nonworse'] for p in proofs)
                and any(p['native_PI_metrics']['improved'] for p in proofs)))
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=round(time.monotonic()-started,6)
    return result
