"""Exact source-owned cleanup of whole pad-free, zone-free power islands.

No rated net is reclassified as an ordinary signal. An existing complete
aggregate current domain owns the request. Every selected source component
must be wholly floating, ungrouped and outside actual and authored own-net
zones. Complete saved replay, surviving partitions and trace/rated authority
connections must hold. This removes copper; it never grants rating credit.
"""
import time
from pathlib import Path
import tempfile

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_path_receiving as current_paths
import cec_field_coupling as field
import cec_floating_route_islands as floating
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_redundant_force_branch as branches
from cec_native_items import discard_items


def _ids(values, maximum, *, empty=False):
    if (not isinstance(values,(list,tuple,set,frozenset))
            or not (0 if empty else 1)<=len(values)<=maximum
            or any(type(u) is not str or not u for u in values)
            or len(set(values))!=len(values)):
        raise ValueError('bounded_explicit_power_island_inventory_required')
    return set(values)


def plan(board, seed_uuids, *, board_hint, allow_locked_uuids=(), timeout_s=10.):
    deadline=branches._budget(timeout_s)
    seeds=_ids(seed_uuids,4);unlocks=_ids(allow_locked_uuids,128,empty=True)
    items,graph,binding=floating._context(board,deadline)
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    selected=set();proofs=[];models={}
    for uid in sorted(seeds):
        if time.monotonic()>=deadline:raise ValueError('power_island_inventory_deadline')
        item=items.get(uid)
        if item is None or item.GetClass() not in ('PCB_TRACK','PCB_VIA') or item.GetNetCode()<=0:
            raise ValueError('actual_source_power_island_seed_required')
        net=str(item.GetNetname())
        models[net]=branches._model(board,net,board_hint)
        part={uid}|{force._uid(other) for other in graph.GetConnectedItems(item)
                   if other.GetNetCode()==item.GetNetCode()}
        if not part<=items.keys() or not 1<=len(selected|part)<=128:
            raise ValueError('complete_bounded_power_island_required')
        conductors=[items[u] for u in sorted(part)]
        if any(i.GetClass() not in ('PCB_TRACK','PCB_VIA') for i in conductors):
            raise ValueError('power_island_has_actual_source_pad_or_zone_contact')
        if part & grouped or any(i.GetParentGroup() is not None for i in conductors):
            raise ValueError('power_island_source_group_owned')
        if any(i.IsLocked() and force._uid(i) not in unlocks for i in conductors):
            raise ValueError('power_island_explicit_locked_scope_required')
        if any(i.GetClass()=='PCB_VIA' and (i.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or i.TopLayer()!=pcbnew.F_Cu or i.BottomLayer()!=pcbnew.B_Cu) for i in conductors):
            raise ValueError('power_island_only_source_through_barrels_allowed')
        for conductor in conductors:
            for other in items.values():
                if time.monotonic()>=deadline:raise ValueError('power_island_native_contact_deadline')
                if (other.GetNetCode()!=item.GetNetCode() or force._uid(other) in part
                        or other.GetClass() not in ('PAD','ZONE')):continue
                for layer in conductor.GetLayerSet().CuStack():
                    if not other.IsOnLayer(layer):continue
                    shape=other.Outline() if other.GetClass()=='ZONE' else other.GetEffectiveShape(layer)
                    if shape.Collide(conductor.GetEffectiveShape(layer),0):
                        raise ValueError('power_island_native_land_or_authored_zone_contact')
        if part & selected:
            if not part<=selected:raise ValueError('ambiguous_power_island_partition')
            continue
        selected|=part
        proofs.append(dict(net=net,uuids=sorted(part),source_pad_contacts=[],
            source_zone_contacts=[],source_authored_zone_reservations=[],source_boundary_contacts=[]))
    if not unlocks<=selected:raise ValueError('power_island_unlock_not_exact_selected_scope')
    return dict(schema=1,kind='source_owned_complete_floating_power_islands',
        source_native_sha256=binding,board_hint=board_hint,seed_uuids=sorted(seeds),
        allow_locked_uuids=sorted(unlocks),retired_uuids=sorted(selected),islands=proofs,
        source_current_models=models,source_terminals_removed=0,
        current_qualified=False,plated_barrel_rating_qualified=False,release_authority=False)


def apply(board, proposal, *, timeout_s=10.):
    fresh=plan(board,proposal['seed_uuids'],board_hint=proposal['board_hint'],
        allow_locked_uuids=proposal['allow_locked_uuids'],timeout_s=timeout_s)
    # JSON serialization converts model tuples to lists. Compare canonical
    # serialized data; this is not permission to omit any source model field.
    import json
    if json.dumps(fresh,sort_keys=True)!=json.dumps(proposal,sort_keys=True):
        raise ValueError('power_island_stale_or_forged_plan')
    live={force._uid(t):t for t in board.GetTracks()}
    discard_items(board,[live[u] for u in proposal['retired_uuids']])


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    result=dict(schema=1,ok=False,complete=False,errors=[],current_qualified=False,
        plated_barrel_rating_qualified=False,release_authority=False,
        full_native_current_field_kelvin_and_release_receiving_still_required=True)
    try:
        deadline=branches._budget(timeout_s)
        paths=[Path(p).resolve() for p in (source,candidate)]
        if paths[0]==paths[1] or proposal['board_hint']!=board_hint:
            raise ValueError('distinct_source_bound_power_island_candidate_required')
        families=[force._family(p,board_hint) for p in paths];epoch=force._code_identity()
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        retired=set(proposal['retired_uuids'])
        _,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        if old.keys()-new.keys()!=retired or new.keys()-old.keys():
            raise ValueError('power_island_exact_subtraction_only')
        original=ordinary._partition(parent,deadline,retired_uuids=retired)
        retained=set().union(*original)
        restored=ordinary._partition(child,deadline,retained_keys=retained)
        if not branches.preserved_partitions(original,restored):
            raise ValueError('power_island_lost_surviving_native_partition')
        resolver=fr._project_netclass_resolver(str(paths[0]));proofs={}
        for net in proposal['source_current_models']:
            domain,contract=branches._model(parent,net,board_hint)
            if (domain,contract)!=branches._model(child,net,board_hint):
                raise ValueError('power_island_current_authority_changed')
            before=force._graph(parent,net,domain,contract,resolver(net) or {})[0]
            after=force._graph(child,net,domain,contract,resolver(net) or {})[0]
            proof=current_paths.compare(before,after);proofs[net]=proof
            if not proof['ok'] or not proof['complete'] or proof['new_joins']:
                raise ValueError('power_island_existing_current_path_changed')
        with tempfile.TemporaryDirectory(prefix='cec-power-island-receiving-') as work:
            expected=force._copy_family(paths[0],Path(work)/'expected')
            basis=pcbnew.LoadBoard(str(expected));apply(basis,proposal,timeout_s=min(10.,deadline-time.monotonic()))
            field._save_field_snapshot(basis,expected)
            _,nodes=additive._nodes(expected)
            if nodes.keys()!=old.keys()-retired or any(syntax._freeze(nodes[u])!=syntax._freeze(old[u]) for u in nodes):
                raise ValueError('power_island_changed_unowned_source_copper')
            exact=additive.receive(expected,paths[1],timeout_s=min(10.,deadline-time.monotonic()))
            if not exact['ok'] or not exact['complete']:raise ValueError('power_island_saved_replay_refused')
        if (epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]
                or time.monotonic()>=deadline):raise ValueError('power_island_source_code_or_deadline_changed')
        result.update(ok=True,complete=True,retired_uuids=sorted(retired),
            all_surviving_native_partitions_preserved=True,
            all_existing_trace_and_rated_authority_connections_preserved=True,
            independent_current_path_receiving=proofs,independent_exact_saved_replay=exact,
            source_candidate_and_code_unchanged=True)
    except (ValueError,TypeError,KeyError,RuntimeError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
