"""Exact ordinary barrel ownership for a bounded atomic macro reconstruction.

The source via and ALL of its actual source contacts are one cut scope.
Blocked old via centres are not retained terminals of a replacement tree.
This read-only proposal does not authorize subtraction by itself: exact
original-source replay, all surviving partitions, native clearance/current,
field/pair/Kelvin and process receiving remain independently mandatory.
"""
import math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary
import cec_field_coupling as field


def plan(source,candidate,requested,*,source_path,board_hint,obstructing_items,
         clearance_nm,allow_locked_via_uuids=(),timeout_s=10.):
    if (type(requested) not in (list,tuple) or not 1<=len(requested)<=16
            or len(set(requested))!=len(requested)
            or any(type(u) is not str or not u for u in requested)
            or type(obstructing_items) not in (list,tuple) or not 1<=len(obstructing_items)<=512
            or type(clearance_nm) is not int or not 0<=clearance_nm<=2000000
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or Path(source.GetFileName()).resolve()!=Path(source_path).resolve()):
        raise ValueError('bounded_original_source_macro_barrel_scope_required')
    deadline=time.monotonic()+timeout_s
    unlock=set(allow_locked_via_uuids)
    if len(unlock)!=len(allow_locked_via_uuids) or not unlock<=set(requested):
        raise ValueError('exact_source_barrel_lock_scope_required')
    old={force._uid(t):t for t in source.GetTracks()}
    new={force._uid(t):t for t in candidate.GetTracks()}
    layers=list(source.GetEnabledLayers().CuStack())
    if layers!=list(candidate.GetEnabledLayers().CuStack()):
        raise ValueError('unchanged_native_barrel_layer_stack_required')
    positive=ordinary.eligible_nets(source,source_path,board_hint)
    contacts=set();rows=[]
    grouped={force._uid(i) for g in source.Groups() for i in g.GetItems()}
    source_items=[*(p for f in source.GetFootprints() for p in f.Pads()),*source.GetTracks()]
    if len(source_items)>16384:raise ValueError('macro_barrel_source_inventory_bound')
    for uid in requested:
        before,after=old.get(uid),new.get(uid)
        if (before is None or after is None or before.GetClass()!='PCB_VIA' or after.GetClass()!='PCB_VIA'
                or before.GetNetname() not in positive
                or tuple(before.GetPosition())!=tuple(after.GetPosition())
                or before.GetNetCode()!=after.GetNetCode() or before.IsLocked()!=after.IsLocked()
                or before.GetViaType()!=after.GetViaType()
                or (before.TopLayer(),before.BottomLayer())!=(after.TopLayer(),after.BottomLayer())
                or before.GetDrillValue()!=after.GetDrillValue()
                or any(before.IsOnLayer(l)!=after.IsOnLayer(l) or before.GetWidth(l)!=after.GetWidth(l) for l in layers)):
            raise ValueError('unchanged_positive_source_ordinary_barrel_required:'+uid)
        witnesses=[]
        for item in obstructing_items:
            if time.monotonic()>=deadline:raise ValueError('macro_barrel_scope_deadline')
            if force._uid(item)==uid:continue
            faces=[int(l) for l in layers if item.GetNetCode()!=after.GetNetCode()
                and item.IsOnLayer(l) and after.IsOnLayer(l)
                and item.GetEffectiveShape(l).Collide(after.GetEffectiveShape(l),clearance_nm)]
            hole=False
            if item.GetClass()=='PCB_VIA':
                gap=candidate.GetDesignSettings().m_HoleToHoleMin
                diameter=after.GetDrillValue()+item.GetDrillValue()+2*gap
                hole=4*sum((x-y)**2 for x,y in zip(after.GetPosition(),item.GetPosition()))<diameter**2
            if faces or hole:witnesses.append(dict(uuid=force._uid(item),layers=faces,hole_conflict=hole))
        if not witnesses:raise ValueError('actual_native_cohort_obstruction_witness_required:'+uid)
        incident=set()
        for item in source_items:
            if time.monotonic()>=deadline:raise ValueError('macro_barrel_scope_deadline')
            other=force._uid(item)
            if other==uid:continue
            if any(item.IsOnLayer(l) and item.GetEffectiveShape(l).Collide(before.GetEffectiveShape(l),0) for l in layers):
                if item.GetClass()!='PCB_TRACK' or item.GetNetCode()!=before.GetNetCode() or other in grouped:
                    raise ValueError('macro_barrel_has_retained_pad_barrel_or_foreign_source_contact:'+uid)
                incident.add(other)
        contacts.update(incident)
        if len(contacts)>64:raise ValueError('macro_barrel_exact_contact_track_work_bound')
        rows.append(dict(via_uuid=uid,net=before.GetNetname(),source_nm=list(before.GetPosition()),
            obstruction_witnesses=witnesses,source_contact_track_uuids=sorted(incident)))
    ownership=ordinary._exclusive_retired_vias(source,set(requested),retired_tracks=contacts,
        nets=positive,unlock=unlock,deadline=deadline)
    return dict(schema=1,scope='bounded_original_source_ordinary_barrel_macro_kernel',
        source_binding=field._field_snapshot_inventory(source),
        provisional_binding=field._field_snapshot_inventory(candidate),
        exact_retired_via_uuids=sorted(requested),mandatory_reconstruction_track_uuids=sorted(contacts),
        independently_reproved_source_exclusive_barrels=ownership,rows=rows,
        original_source_saved_replay_and_partitions_required=True,
        proposed_geometry_or_cut_is_not_admission=True,
        current_or_barrel_capacity_credited=False,source_or_candidate_mutated=False,release_authority=False)
