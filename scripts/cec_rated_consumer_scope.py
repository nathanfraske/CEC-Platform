"""Bind a bounded repair to an already proved, source-declared consumer leaf.

This never assigns a local current from a net label, part rating, route width,
or proposed topology. Both saved endpoints independently prove the same exact
consumer, one physical shared-rail tap, and unchanged aggregate allocation.
"""
import copy
import math
import cec_supply_consumer_branch as consumer
import cec_native_supply_via_context as web
import cec_force_current as force
import cec_fab_profile as fab


def _native_aggregate(board,net,*,board_hint):
    """Recover an existing force-domain contract, never allocate its branch.

    Distributed-supply catalogs correctly exclude aggregate cable rails.
    A separately proved exclusive consumer may still live on such a rail.
    Only its actual complete native aggregate authority can fill this catalog
    gap; the consumer proof below independently owns every selected cut.
    """
    import cec_current_topology as topology
    import cec_fr as fr
    domains=topology.board_current_domains(board,board_hint)
    domain=domains.get(net)
    raw=topology.route_width_contracts(board,board_hint).get(net)
    if (not domain or domain.get('complete') is not True or domain.get('missing_refs')
            or not raw or not raw.get('authority_refs') or not domain.get('authority_refs')
            or set(raw['authority_refs'])!=set(domain['authority_refs'])
            or raw.get('net')!=net):
        raise ValueError('consumer_repair_complete_native_aggregate_domain_required')
    spec=fr._project_netclass_resolver(str(board.GetFileName()))(net) or {}
    clearance=spec.get('clearance')
    if (type(clearance) not in (int,float) or not math.isfinite(clearance) or clearance<=0):
        raise ValueError('consumer_repair_native_aggregate_clearance_authority_required')
    return dict(raw,clearance_mm=max(clearance,board.GetDesignSettings().m_MinClearance/1e6))


def _contract(raw,proof,profile):
    budget=proof['budget']
    if raw.get('profile')!=profile:
        raise ValueError('consumer_repair_source_profile_changed')
    if raw.get('current_authority')!=budget['aggregate_current_authority']:
        raise ValueError('consumer_repair_aggregate_authority_changed')
    required=budget['required_by_layer_mm']
    if set(required)!=set(raw.get('required_by_layer_mm',{})):
        raise ValueError('consumer_repair_complete_source_layer_floors_required')
    result=copy.deepcopy(raw)
    result.update(current_authority=copy.deepcopy(budget['current_authority']),
        required_by_layer_mm=copy.deepcopy(required),
        source_consumer_root_pad_uuid=proof['root_pad_uuid'],
        whole_aggregate_current_unchanged=True,branch_sharing_assumed=False)
    return result


def bind(board,aggregate,retired,*,board_hint):
    proof=consumer.inventory(board,board_hint=board_hint,timeout_s=10.)
    if not proof['complete']:raise ValueError('complete_existing_consumer_island_proof_required')
    owned=proof['all_owned_track_requirements']
    if not retired or not set(retired)<=owned.keys():
        raise ValueError('every_source_cut_track_requires_existing_consumer_island_ownership')
    live={force._uid(t):t for t in board.GetTracks()};local={};roots={}
    aggregate=dict(aggregate);native_aggregate=set()
    for uid in sorted(retired):
        net=str(live[uid].GetNetname())
        matches=[p for p in proof['proofs'] if uid in p['track_requirements']
            or uid in p['retained_island_track_requirements']]
        if len(matches)!=1:
            raise ValueError('unique_exact_source_consumer_scope_required')
        if net not in aggregate:
            aggregate[net]=_native_aggregate(board,net,board_hint=board_hint)
            native_aggregate.add(net)
        p=matches[0];contract=_contract(aggregate[net],p,fab.active_profile_name(board,hint=board_hint))
        if net in local and contract!=local[net]:raise ValueError('consumer_current_allocation_cannot_mix_roots')
        local[net]=contract;roots[net]=p['root_pad_uuid']
    return local,dict(root_by_net=roots,aggregate_contracts={n:aggregate[n] for n in local},
        source_native_aggregate_domain_nets=sorted(native_aggregate),
        source_cut_track_uuids=sorted(retired),source_native_island_reproved=True,
        aggregate_budget_reduced=False,current_or_release_qualified=False)


def receive(board,aggregate,scope,contracts,track_ids,via_ids,*,board_hint):
    proof=consumer.inventory(board,board_hint=board_hint,timeout_s=10.)
    if not proof['complete']:
        raise ValueError('saved_consumer_island_proof_required:'+str(proof.get('refusals',[])))
    aggregate=dict(aggregate)
    native_aggregate=scope.get('source_native_aggregate_domain_nets',[])
    if (type(native_aggregate) is not list or len(native_aggregate)!=len(set(native_aggregate))
            or not set(native_aggregate)<=set(contracts)):
        raise ValueError('saved_consumer_repair_exact_aggregate_provider_scope_required')
    for net in native_aggregate:
        if net in aggregate:
            raise ValueError('saved_consumer_repair_aggregate_provider_changed')
        aggregate[net]=_native_aggregate(board,net,board_hint=board_hint)
    if {n:aggregate.get(n) for n in contracts}!=scope['aggregate_contracts']:
        raise ValueError('saved_consumer_repair_aggregate_contract_changed')
    live={force._uid(t):t for t in board.GetTracks()};proved=[]
    for net,contract in contracts.items():
        matches=[p for p in proof['proofs'] if p['root_pad_uuid']==scope['root_by_net'][net]]
        if len(matches)!=1 or _contract(aggregate[net],matches[0],fab.active_profile_name(board,hint=board_hint))!=contract:
            raise ValueError('saved_consumer_repair_root_or_local_budget_changed')
        p=matches[0];owned=set(p['track_requirements'])|set(p['retained_island_track_requirements'])
        new_tracks={u for u in track_ids if str(live[u].GetNetname())==net}
        if not new_tracks<=owned:raise ValueError('new_rated_track_outside_proved_exclusive_consumer_leaf')
        for uid in via_ids:
            if str(live[uid].GetNetname())!=net:continue
            if uid not in p['retained_consumer_island_uuids']:
                raise ValueError('new_rated_barrel_outside_proved_exclusive_consumer_leaf')
            checked=web.receive(board,uid,contract,timeout_s=2.)
            if not checked['ok'] or not checked['complete']:
                raise ValueError('new_consumer_barrel_full_actual_contact_web_required')
        proved.append(dict(root_pad_uuid=p['root_pad_uuid'],new_tracks=sorted(new_tracks),
            physical_trunk_tap_count=p['physical_trunk_tap_count'],
            aggregate_rail_budget_unchanged=True))
    return dict(ok=True,complete=True,proofs=proved,current_or_release_qualified=False)
