"""Source-proved retirement of complete pad-free, zone-free route islands.

This is not dangling-end peeling: a component attached to even one actual
source pad, zone or owned group is never removable. The caller explicitly
selects ordinary nets or a named ground network. Rated supply, pair, Kelvin
and unfilled copper uncertainty fail closed. Saved DRC, field, current and
full-suite receiving remain mandatory; isolation alone is not qualification.
"""
import math
from pathlib import Path
import tempfile
import time


def _context(board, deadline):
    import pcbnew
    import cec_force_current as force
    from cec_cell_row_rebuild import _source_binding
    material=[*board.GetTracks(),*[p for f in board.GetFootprints() for p in f.Pads() if p.GetNetCode()>0],
        *[z for z in board.Zones() if not z.GetIsRuleArea()]]
    if len(material)>16384:
        raise ValueError('floating_island_inventory_bound')
    items={force._uid(i):i for i in material}
    if len(items)!=len(material):
        raise ValueError('floating_island_ambiguous_native_identity')
    graph=pcbnew.CONNECTIVITY_DATA()
    for item in material:
        if time.monotonic()>=deadline:
            raise ValueError('floating_island_deadline')
        if not graph.Add(item):
            raise ValueError('floating_island_native_graph_unknown')
    return items,graph,_source_binding(board)


def plan(board, *, source_path, board_hint, include_nets, ground_net='GND',
         authorize_source_locked=False, timeout_s=10., max_items=128):
    import cec_force_current as force
    import cec_fr as fr
    import cec_ordinary_route_receiving as ordinary
    import cec_current_topology as topology
    if (type(include_nets) not in (list,tuple,set) or not 1<=len(include_nets)<=16
            or any(type(n) is not str or not n for n in include_nets)
            or len(set(include_nets))!=len(include_nets)
            or type(ground_net) is not str or not ground_net
            or type(authorize_source_locked) is not bool or type(max_items) is not int
            or not 1<=max_items<=128 or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=10):
        raise ValueError('bounded_explicit_floating_island_scope_required')
    deadline=time.monotonic()+timeout_s
    ordinary_nets=ordinary.eligible_nets(board,source_path,board_hint)
    wanted=set(include_nets)
    with force._thermal_hint(board_hint):
        protected=set(topology.board_current_domains(board,board_hint))- {ground_net}
    if (wanted-ordinary_nets-{ground_net} or wanted & protected
            or wanted & fr.coupled_pair_nets(board)):
        raise ValueError('floating_island_specialized_or_rated_net_refused')
    items,graph,binding=_context(board,deadline)
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    selected=set();proofs=[];refused=[]
    for net in sorted(wanted):
        zones=[z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()==net]
        if any(not z.IsFilled() for z in zones):
            raise ValueError('floating_island_same_net_fill_unknown')
        remaining={u for u,i in items.items() if i.GetNetname()==net}
        while remaining:
            if time.monotonic()>=deadline:
                raise ValueError('floating_island_deadline')
            seed=items[min(remaining)]
            part=({force._uid(seed)} | {force._uid(i) for i in graph.GetConnectedItems(seed)}) & remaining
            remaining-=part
            conductors=[items[u] for u in sorted(part)]
            if any(i.GetClass() not in ('PCB_TRACK','PCB_VIA','PCB_ARC') for i in conductors):
                continue
            # Explicitly test native geometry against EVERY pad and filled
            # own-net zone, not merely whether the ratsnest named a pad.
            contacts=False
            for item in conductors:
                for other in items.values():
                    if time.monotonic()>=deadline:
                        raise ValueError('floating_island_deadline')
                    if (other.GetNetname()!=net or force._uid(other) in part
                            or other.GetClass() not in ('PAD','ZONE')
                            or not item.GetBoundingBox().Intersects(other.GetBoundingBox())):
                        continue
                    for layer in item.GetLayerSet().CuStack():
                        if not other.IsOnLayer(layer):
                            continue
                        shape=(other.GetFilledPolysList(layer) if other.GetClass()=='ZONE'
                            else other.GetEffectiveShape(layer))
                        if shape.Collide(item.GetEffectiveShape(layer),0):
                            contacts=True; break
                    if contacts:break
                if contacts:break
            reason=('native_land_or_zone_contact' if contacts else
                'owner_group_required' if part & grouped or any(i.GetParentGroup() is not None for i in conductors) else
                'locked_source_scope_not_authorized' if not authorize_source_locked and any(i.IsLocked() for i in conductors) else
                'bounded_retirement_inventory' if len(selected|part)>max_items else None)
            if reason:
                refused.append(dict(net=net,uuids=sorted(part),reason=reason)); continue
            selected|=part
            proofs.append(dict(net=net,uuids=sorted(part),source_pad_contacts=[],
                source_zone_contacts=[],source_boundary_contacts=[],source_group_contacts=[]))
    return dict(schema=1,kind='complete-floating-native-route-islands',
        source_native_sha256=binding,include_nets=sorted(wanted),ground_net=ground_net,
        authorize_source_locked=authorize_source_locked,max_items=max_items,
        retired_uuids=sorted(selected),islands=proofs,refusals=refused,
        electrical_terminals_removed=0,source_boundary_contacts=[],
        routing_admitted=False,current_qualified=False,release_authority=False)


def apply(board, proposal, *, source_path, board_hint, timeout_s=10.):
    import cec_force_current as force
    from cec_native_items import discard_items
    fresh=plan(board,source_path=source_path,board_hint=board_hint,
        include_nets=proposal['include_nets'],ground_net=proposal['ground_net'],
        authorize_source_locked=proposal['authorize_source_locked'],timeout_s=timeout_s,
        max_items=proposal['max_items'])
    if fresh!=proposal or not fresh['retired_uuids']:
        raise ValueError('floating_island_stale_forged_or_empty_plan')
    by_id={force._uid(t):t for t in board.GetTracks()}
    discard_items(board,[by_id[u] for u in fresh['retired_uuids']])
    return dict(retired_uuids=fresh['retired_uuids'],source_terminals_or_zones_removed=False)


def receive(source, candidate, proposal, *, board_hint, timeout_s=10.):
    import pcbnew
    import cec_additive_route_receiving as additive
    import cec_copper_echo as syntax
    import cec_field_coupling as field
    import cec_force_current as force
    import cec_ordinary_route_receiving as ordinary
    result=dict(ok=False,complete=False,errors=[],release_authority=False)
    try:
        paths=[Path(p).resolve() for p in (source,candidate)]
        families=[force._family(p,board_hint) for p in paths]
        before,after=[pcbnew.LoadBoard(str(p)) for p in paths]
        # Re-derive the source-owned scope, then replay only that deletion.
        apply(before,proposal,source_path=paths[0],board_hint=board_hint,timeout_s=timeout_s)
        with tempfile.TemporaryDirectory(prefix='cec-floating-island-receiving-') as work:
            expected=force._copy_family(paths[0],Path(work)/'expected')
            additive._ground_refill(before);field._save_field_snapshot(before,expected)
            _,old=additive._nodes(expected);_,new=additive._nodes(paths[1])
            if old.keys()!=new.keys() or any(syntax._freeze(old[u])!=syntax._freeze(new[u]) for u in old):
                raise ValueError('floating_island_not_exact_native_subtract_and_refill')
            if force._preservation_snapshot(expected)[1]!=force._preservation_snapshot(paths[1])[1]:
                raise ValueError('floating_island_rules_or_outline_changed')
            if force._sidecars(expected)!=force._sidecars(paths[1]):
                raise ValueError('floating_island_sidecars_changed')
        parent=pcbnew.LoadBoard(str(paths[0]))
        oldparts=ordinary._partition(parent,time.monotonic()+timeout_s,
            retired_uuids=proposal['retired_uuids'])
        retained=set().union(*oldparts)
        newparts=ordinary._partition(after,time.monotonic()+timeout_s,retained_keys=retained)
        if any(not any(p<=q for q in newparts) for p in oldparts):
            raise ValueError('floating_island_lost_surviving_native_partition')
        if families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('floating_island_source_or_candidate_changed')
        result.update(ok=True,complete=True,source_retired_scope_independently_derived=True,
            all_surviving_native_partitions_preserved=True,retired_uuids=proposal['retired_uuids'])
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
