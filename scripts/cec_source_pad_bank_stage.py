"""Exact saved Source plus one rederived solid pad-bank collector.

The existing bank owner proves geometry, not ampacity or release. This
adapter independently reconstructs ONLY that new native zone and existing
Ground fills. All Source parts, tracks, vias, power zones, rules, locks and
opaque companions remain exact. Whole-board current, field, contact/Kelvin,
factory, parity and severity-all native receiving remain mandatory.
"""
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as ast
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_pad_bank_collector as bank


def receive(source,candidate,proposal,*,zone_uuid,board_hint,timeout_s=10.):
    result=dict(ok=False,complete=False,errors=[],scope='exact_saved_source_plus_one_pad_bank',
        routing_admitted=False,new_capacity_credited=False,current_qualified=False,
        release_authority=False,all_whole_board_gates_still_required=True)
    try:
        if (type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10
                or type(zone_uuid)is not str or not zone_uuid
                or type(board_hint)is not str or not board_hint or type(proposal)is not dict):
            raise ValueError('bounded_explicit_saved_pad_bank_context_required')
        deadline=time.monotonic()+timeout_s
        def remaining():
            value=deadline-time.monotonic()
            if value<=0:raise ValueError('saved_pad_bank_receiving_deadline')
            return min(10.,value)
        source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
        if source==candidate:raise ValueError('distinct_saved_pad_bank_source_and_child_required')
        code=force._code_identity();families=[force._family(p,board_hint)for p in(source,candidate)]
        if force._sidecars(source)!=force._sidecars(candidate):
            raise ValueError('pad_bank_source_companions_must_remain_exact')
        stable=lambda value:json.dumps(value,sort_keys=True,allow_nan=False)
        requested=stable(proposal)
        before,after=[pcbnew.LoadBoard(str(p))for p in(source,candidate)]
        fresh=bank.plan(before,[q['uuid']for q in proposal['source_pads']],
            layer_id=proposal['layer_id'],support_track_uuids=[q['uuid']for q in proposal['retained_source_tracks']],
            clearance_nm=proposal['clearance_nm'],min_thickness_nm=proposal['min_thickness_nm'],
            timeout_s=remaining(),**proposal['envelope_policy'])
        if stable(fresh)!=requested:raise ValueError('fresh_complete_source_pad_bank_proposal_required')
        spec=cells._netclass(before,fresh['net'])
        if (fresh['layer_id']in{before.GetLayerID(name)for name in fr.plane_layers(before)}
                or fresh['clearance_nm']<max(before.GetDesignSettings().m_MinClearance,int(spec['clearance']))):
            raise ValueError('actual_source_pad_bank_face_and_clearance_floor_required')
        old_root,old=additive._nodes(source);new_root,new=additive._nodes(candidate)
        if set(new)-set(old)!={zone_uuid}or set(old)-set(new)or new[zone_uuid][0]!='zone':
            raise ValueError('exactly_one_new_zone_and_no_retirement_required')
        uid=lambda node:next((q[1].strip('"')for q in node[1:]
            if isinstance(q,list)and len(q)==2 and q[0]=='uuid'),None)
        metadata=lambda root:ast._freeze([q for q in root[1:]if not isinstance(q,list)or uid(q)is None])
        if metadata(old_root)!=metadata(new_root):raise ValueError('pad_bank_source_root_settings_changed')
        ground={force._uid(z)for z in before.Zones()if not z.GetIsRuleArea()and z.GetNetname()=='GND'}
        for key,node in old.items():
            remaining()
            same=(additive._without(node,'filled_polygon')==additive._without(new[key],'filled_polygon')
                if key in ground else ast._freeze(node)==ast._freeze(new[key]))
            if not same:raise ValueError('pad_bank_original_native_item_changed:'+key)
        proof=bank.receive(after,fresh,zone_uuid,timeout_s=remaining())
        result['saved_native_bank_receiving']=proof
        if not proof.get('ok')or not proof.get('complete'):
            raise ValueError('actual_saved_native_pad_bank_refused:'+str(proof.get('reason')))
        # Rebuild from the actual Source, not from a candidate zone clone.
        emitted=bank.materialize(before,fresh)
        created=next(z for z in before.Zones()if force._uid(z)==emitted['zone_uuid'])
        created.m_Uuid.Clone(pcbnew.KIID(zone_uuid))
        selected=pcbnew.ZONES();selected.append(created)
        import cec_zone_fill
        cec_zone_fill.compile_selected(before,selected,timeout_s=remaining(),initialize_selected=True)
        additive._ground_refill(before)
        if field._field_snapshot_inventory(before)!=field._field_snapshot_inventory(after):
            raise ValueError('pad_bank_actual_native_zone_or_ground_refill_differs')
        import cec_native_partition_pair as partitions
        paired=partitions.compare(pcbnew.LoadBoard(str(source)),after,timeout_s=remaining())
        result['native_partition_preservation']={k:v for k,v in paired.items()
            if k not in('source_parts','child_parts','demoted_parts')}
        if paired.get('available')is not True or paired.get('preserved')is not True:
            raise ValueError('pad_bank_lost_surviving_native_partition')
        remaining()
        if (code!=force._code_identity()or requested!=stable(proposal)
                or families!=[force._family(p,board_hint)for p in(source,candidate)]):
            raise ValueError('pad_bank_source_candidate_proposal_or_code_changed')
        result.update(ok=True,complete=True,source=str(source),candidate=str(candidate),
            source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            source_plan=fresh,zone_uuid=zone_uuid,only_one_native_collector_added=True,
            original_objects_and_companions_preserved=True,independent_native_ground_and_bank_refill_equal=True,
            source_family_and_code_unchanged=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
