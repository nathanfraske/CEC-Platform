"""Restore stranded fixed Ground fragments to their OWN retained Source root.

The original cut remains owned and every fixed fragment remains mandatory.
An actual Source-known return may name an unchanged, live-qualified barrel
on both saved reference planes instead of forcing a long trip through a
newly moving capacitor. This changes request endpoints, never PCB copper,
current budgets, source cuts, width, factory rules or receiving gates.
"""
import copy,json,math,time
from pathlib import Path
import cec_cell_ground_cut_boundaries as original
import cec_cell_row_rebuild as binding
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_ground_return_shortcut as contacts
import cec_native_placement_context as native
import cec_projected_ground_contact as signatures
import cec_stationary_ground_barrel as qualified

_SELF=Path(__file__).resolve();_HASH=force._hash(_SELF)
_BASE=Path(original.__file__).resolve();_BASE_HASH=force._hash(_BASE)
def identity():
    if force._hash(_SELF)!=_HASH or force._hash(_BASE)!=_BASE_HASH:
        raise ValueError('stationary_ground_boundary_root_helpers_changed')
    return {str(_SELF):_HASH,str(_BASE):_BASE_HASH}

def requests(source,posed,proposal,*,timeout_s=10.,transported_source_barrels=(),
             additional_source_ground_cut_rows=()):
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
        raise ValueError('bounded_source_stationary_ground_boundary_required')
    identity();before=[binding._source_binding(b) for b in (source,posed)]
    deadline=time.monotonic()+timeout_s
    result=original.requests(source,posed,proposal,timeout_s=timeout_s,transported_source_barrels=transported_source_barrels,
        additional_source_ground_cut_rows=additional_source_ground_cut_rows)
    old_pads={force._uid(p):p for f in source.GetFootprints() for p in f.Pads()}
    new_pads={force._uid(p):p for f in posed.GetFootprints() for p in f.Pads()}
    old_vias={force._uid(v):v for v in source.GetTracks() if v.GetClass()=='PCB_VIA'}
    new_vias={force._uid(v):v for v in posed.GetTracks() if v.GetClass()=='PCB_VIA'}
    for key,row in result.items():
        if time.monotonic()>=deadline:raise ValueError('stationary_ground_boundary_root_deadline')
        uid=row['b'].get('pad_uuid');pad=old_pads.get(uid);peer=new_pads.get(uid)
        if pad is None or peer is None:continue
        first=native._native_stationary_land(pad,deadline)
        if first is None or first!=native._native_stationary_land(peer,deadline):continue
        witness=cells._existing_return(source,pad,16.,allow_native_track_body=True)
        if witness is None:continue
        root=witness[1];rid=force._uid(root);last=new_vias.get(rid)
        if rid not in old_vias or last is None:continue
        if signatures._via_signature(source,root)!=signatures._via_signature(posed,last):continue
        try:
            if not qualified._qualified(source,root) or not qualified._qualified(posed,last):continue
            planes=contacts._reference_contacts(source,root)
            if planes!=contacts._reference_contacts(posed,last):continue
        except ValueError:continue
        source_key=list(force._item_key(root));fixed_key=list(force._item_key(pad))
        original_keys=row['retained_source_ground_fragment']['original_source_component_keys']
        freeze=lambda q:json.dumps(q,sort_keys=True)
        if not {freeze(source_key),freeze(fixed_key)}<={freeze(v) for v in original_keys}:continue
        old_a=copy.deepcopy(row['a'])
        row['a']=dict(at_nm=list(last.GetPosition()),layers=list(map(int,last.GetLayerSet().CuStack())),native_uuids=[rid])
        proof=row['retained_source_ground_fragment']
        proof['original_moving_entry_source_key']=proof.pop('moving_entry_source_key')
        proof['retained_reference_source_key']=source_key
        row['stationary_source_ground_root_restoration']=dict(source_fixed_pad_uuid=uid,
            source_known_return_mm=witness[0],retained_reference_via_uuid=rid,
            original_moving_entry_endpoint=old_a,actual_saved_reference_contacts=planes,
            unchanged_native_barrel_and_live_process=True,exact_stationary_land=True,
            native_original_component_membership=True,root_is_not_a_new_or_nearby_same_net_guess=True,
            no_new_holes_or_copper_constructed=True,all_source_partitions_and_returns_still_required=True,
            current_qualified=False,release_authority=False)
    if before!=[binding._source_binding(b) for b in (source,posed)]:
        raise ValueError('stationary_ground_boundary_requests_changed_native_boards')
    identity()
    if time.monotonic()>=deadline:raise ValueError('stationary_ground_boundary_root_deadline')
    return result
