"""Ground debts of fixed low-power owners after their selected bypass cut.

A stationary owner is not blanket routing authority. This adds a mandatory
return ONLY for an exact manufacturer Ground land in an actually severed
native Source fragment of its own moving selected bypass. Converters and
unrelated fixed pins remain untouched. It creates no copper or cut, changes
no reach/current/process rule, and proves no connection by itself.
"""
import math
import time

import cec_force_current as force
import cec_device_power_roles as roles


def merge(existing,debts):
    """Never replace a separately compiled mandatory endpoint contract."""
    if type(existing)is not dict or type(debts)is not dict:
        raise ValueError('typed_stationary_owner_ground_request_maps_required')
    if any(existing[key]!=debts[key]for key in existing.keys()&debts.keys()):
        raise ValueError('stationary_owner_ground_debt_conflicts_with_existing_obligation')
    return {**existing,**debts}


def requests(parent,posed,proposal,ground_cuts,*,timeout_s=10.):
    if (type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10.
            or type(ground_cuts)is not dict or len(ground_cuts)>64):
        raise ValueError('bounded_source_stationary_owner_ground_inventory_required')
    if not ground_cuts:return {}
    import cec_cell_escape_replan as escape
    import cec_cell_row_rebuild as row
    import cec_ground_return_policy as policy
    deadline=time.monotonic()+timeout_s
    if row._source_binding(parent)!=proposal['source_native_binding']:
        raise ValueError('literal_stationary_owner_ground_source_required')
    selected={}
    stationary=set(proposal['stationary_device_owners'])
    for cap,bypass in proposal['selected_bypasses'].items():
        if bypass['owner']not in stationary:continue
        before=parent.FindFootprintByReference(cap);after=posed.FindFootprintByReference(cap)
        owner=parent.FindFootprintByReference(bypass['owner']);live=posed.FindFootprintByReference(bypass['owner'])
        model=roles.footprint_contract(owner)if owner else None
        if (not before or not after or not model or not live
                or model['pins'].get(bypass['pin'])!='power_input'
                or set(model['pins'].values())&{'power_output','switch','feedback'}):continue
        if (tuple(before.GetPosition())==tuple(after.GetPosition())and
                abs((before.GetOrientationDegrees()-after.GetOrientationDegrees()+180)%360-180)<1e-9):continue
        if (force._uid(owner)!=force._uid(live)or tuple(owner.GetPosition())!=tuple(live.GetPosition())
                or abs((owner.GetOrientationDegrees()-live.GetOrientationDegrees()+180)%360-180)>1e-9
                or roles.footprint_contract(live)!=model):
            raise ValueError('actual_exact_stationary_selected_owner_required')
        selected[cap]=bypass
    if not selected:return {}
    # Both observations are independently derived from the real selected
    # Source supply pin, not a worker-named Ground neighbour or net label.
    old_entries=escape.assigned_ground_entries(parent,selected,board_hint=proposal['board_hint'])
    new_entries=escape.assigned_ground_entries(posed,selected,board_hint=proposal['board_hint'])
    old_pads={force._uid(p):p for f in parent.GetFootprints()for p in f.Pads()}
    live_pads={force._uid(p):p for f in posed.GetFootprints()for p in f.Pads()}
    result={}
    for key,cut in ground_cuts.items():
        if time.monotonic()>=deadline:raise ValueError('stationary_owner_ground_inventory_deadline')
        proof=cut.get('retained_source_ground_fragment',{})
        if (cut.get('kind')!='ground_boundary'or cut.get('net')!='GND'
                or proof.get('source_native_binding')!=proposal['source_native_binding']
                or proof.get('actual_fixed_source_contacts_not_same_net_proximity')is not True
                or proof.get('whole_original_current_plane_and_saved_partition_receiving_required')is not True):
            raise ValueError('actual_native_source_ground_cut_fragment_required')
        cap_uid=cut.get('a',{}).get('pad_uuid');cap_pad=old_pads.get(cap_uid)
        if not cap_pad or cap_pad.GetParentFootprint().GetReference()not in selected:continue
        cap_ref=cap_pad.GetParentFootprint().GetReference();bypass=selected[cap_ref]
        for item in proof.get('retained_fragment_keys',[]):
            if (type(item)not in(list,tuple)or len(item)!=6 or item[0]!='pad'):continue
            uid=item[-1];before,pad=old_pads.get(uid),live_pads.get(uid)
            if (before is None or pad is None or uid not in old_entries or uid not in new_entries
                    or before.GetParentFootprint().GetReference()!=bypass['owner']
                    or before.GetNetname()!='GND'or pad.GetNetname()!='GND'
                    or list(force._item_key(before))!=list(item)
                    or tuple(before.GetPosition())!=tuple(pad.GetPosition())
                    or new_entries[uid]['selected_bypass']!=cap_ref):continue
            model=roles.footprint_contract(before.GetParentFootprint())
            if model['pins'].get(before.GetNumber())not in('ground','power_return','reference','address'):continue
            entry=new_entries[uid]
            result['ground:'+uid]=dict(kind='ground',net='GND',a=dict(pad_uuid=uid,
                at_nm=list(pad.GetPosition()),layers=list(map(int,pad.GetLayerSet().CuStack()))),
                reach_mm=policy.reach(pad,new_entries),same_package_ground_link_proposal_allowed=True,
                selected_bypass_entry=entry,stationary_selected_owner_native_ground_cut_debt=dict(
                    source_ground_boundary_request=key,selected_bypass_pad_uuid=cap_uid,
                    actual_retained_source_pad_key=list(item),source_owner=entry['selected_owner'],
                    original_fixed_owner_signal_supply_and_other_pins_not_retyped=True,
                    original_native_fragment_and_local_return_still_mandatory=True,
                    current_authority=False,release_authority=False))
    if time.monotonic()>=deadline:raise ValueError('stationary_owner_ground_inventory_deadline')
    return result
