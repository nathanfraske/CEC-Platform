"""Manufacturer-typed tied-enable leaves, never aggregate power credit.

Only an exclusive short EN-to-IN-island branch is classified as control.
Removing ALL classified material must preserve every declared current-pad
partition. Unknown packages, loads, long routes, ambiguous contacts and partial
proofs keep the old aggregate width obligation. No typical current is treated
as a maximum; rail, barrel, voltage and release qualification stay separate.
"""
import math
import time

import pcbnew
import cec_device_power_roles as roles
import cec_force_current as force
import cec_fr as fr
import cec_route_dimensions as dimensions
import cec_current_topology as topology
import cec_fab_profile as fab
from cec_measurement_current_branch import _partitions
from cec_resistive_monitor_branch import _native_exclusive_plan


def inventory(board,source,domains,*,timeout_s=2.,max_leaves=16):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(max_leaves) is not int or not 1<=max_leaves<=16):
        raise ValueError('bounded_tied_control_current_inventory_required')
    deadline=time.monotonic()+timeout_s
    resolver=fr._project_netclass_resolver(str(source))
    material=[*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks(),
        *[z for z in board.Zones() if not z.GetIsRuleArea()]]
    if len(material)>16384:
        return dict(complete=False,uuids=[],proofs=[],refusals=['control_inventory_bound'])
    live={force._uid(i):i for i in material};cohorts={};refused=[];count=0
    distributed=None;authorities={}
    for fp in board.GetFootprints():
        try:
            model=roles.tied_enable_contract(fp)
            if not model or fp.IsDNP():continue
            enable=[p for p in fp.Pads() if p.GetNumber()==model['enable_pin']]
            supply=[p for p in fp.Pads() if p.GetNumber()==model['input_pin']]
            if len(enable)!=1 or len(supply)!=1:raise ValueError('control_terminal_identity_ambiguous')
            root,supply=enable[0],supply[0];net=str(root.GetNetname());domain=domains.get(net,{})
            if root.GetNetCode()<=0:continue
            if net in domains:
                if domain.get('complete') is not True:continue
                authorities[net]=domain
            else:
                if distributed is None:
                    distributed=topology.distributed_supply_contracts(board,source,netclass_resolver=resolver)['contracts']
                if net not in distributed:continue
                authorities[net]=distributed[net]
            if (root.GetNetCode()!=supply.GetNetCode() or root.HasHole() or supply.HasHole()
                    or math.dist(tuple(root.GetPosition()),tuple(supply.GetPosition()))>3500000):
                raise ValueError('manufacturer_tied_control_topology_required')
            if time.monotonic()>=deadline or count>=max_leaves:raise ValueError('control_inventory_deadline_or_bound')
            count+=1
            q=_native_exclusive_plan(board,force._uid(root),deadline=deadline)
            if q['source_length_mm']>4. or len(q['via_uuids'])>2:
                raise ValueError('control_branch_exceeds_existing_local_bound')
            if any(live[u].GetParentGroup() is not None for u in q['track_uuids']):
                raise ValueError('control_trace_has_other_group_owner')
            for uid in q['via_uuids']:
                item=live[uid];owners=[g for g in board.Groups() if g.ContainsItem(item)]
                if owners and (len(owners)!=1 or owners[0].GetName()!=fr.LOCAL_POFV_SIGNAL_VIA_GROUP
                        or any(i.GetClass()!='PCB_VIA' for i in owners[0].GetItems())
                        or not fab.local_pofv_via_decision(board,item)[0]):
                    raise ValueError('control_transition_has_unqualified_group_owner')
            spec=dimensions.compile_spec(resolver(net) or {},limits=dimensions.board_limits(board),role='branch')
            if any(width<math.ceil(spec['track_width']*1e6)
                    for layer,width in q['track_widths_by_uuid'].values()):
                raise ValueError('control_branch_below_project_or_factory_floor')
            cut=set(q['native_removed_material_uuids'])
            # Reconstruct native reachability without the candidate control
            # branch: every retained boundary must already reach this exact IN.
            graph=pcbnew.CONNECTIVITY_DATA()
            for item in material:
                if time.monotonic()>=deadline:raise ValueError('control_capture_deadline')
                if force._uid(item) not in cut and not graph.Add(item):
                    raise ValueError('control_capture_native_graph_unknown')
            reached={force._uid(supply)}|{force._uid(i) for i in graph.GetConnectedItems(supply)}
            if not set(q['boundary_uuids'])<=reached:
                raise ValueError('control_boundary_is_not_selected_input_island')
            q['manufacturer_source']=model['source'];q['input_pad_uuid']=force._uid(supply)
            cohorts.setdefault(net,[]).append(q)
        except (ValueError,RuntimeError) as exc:
            refused.append(dict(owner=fp.GetReference(),reason=str(exc)))
    admitted=set();proofs=[]
    for net,qs in sorted(cohorts.items()):
        try:
            cut={uid for q in qs for uid in q['native_removed_material_uuids']}
            ids={uid for q in qs for uid in q['track_uuids']}
            roots={q['pad_uuid'] for q in qs}
            declared=force._authority_pads(board,net,domains[net]) if net in domains else []
            # A declared source/sink terminal cannot borrow control semantics.
            if {force._uid(p) for p in declared}&roots:
                raise ValueError('control_land_declared_as_current_terminal')
            # Distributed supplies have no aggregate source/sink domain.
            # Preserve EVERY other physical land, not an inferred source pair.
            # This stronger comparison also retains all aggregate-domain loads.
            pads=[i for i in material if i.GetClass()=='PAD' and i.GetNetname()==net
                  and force._uid(i) not in roots]
            own=[i for i in material if i.GetNetname()==net and force._uid(i) not in {force._uid(p) for p in pads}]
            if not pads or len(own)+len(pads)>4096:raise ValueError('complete_control_current_terminals_required')
            before=_partitions(pads,own,deadline)
            after=_partitions(pads,[i for i in own if force._uid(i) not in cut],deadline)
            if before!=after:raise ValueError('control_cut_changes_current_terminal_partitions')
            admitted|=ids
            proofs.append(dict(net=net,track_uuids=sorted(ids),
                leaf_pad_uuids=sorted(q['pad_uuid'] for q in qs),
                input_pad_uuids=sorted(q['input_pad_uuid'] for q in qs),
                manufacturer_sources=sorted({q['manufacturer_source'] for q in qs}),
                unchanged_source_current_authority=authorities[net],
                native_exclusive_branch_material_uuids=sorted(cut),
                native_current_terminal_partitions=before,
                partitions_unchanged_after_collective_removal=True,
                manufacturer_control_role=True,new_numeric_load_assumed=False,
                control_input_current_max_a=None,current_path_qualified=False,release_authority=False))
        except (ValueError,RuntimeError) as exc:
            refused.append(dict(net=net,reason=str(exc)))
    complete=time.monotonic()<deadline
    return dict(complete=complete,uuids=sorted(admitted) if complete else [],
        proofs=proofs if complete else [],refusals=refused,
        current_path_qualified=False,release_authority=False)
