"""Source-qualified distributed supply joins for the whole received stage.

Only the unchanged explicit aggregate load is used.  New short terminal
prefixes require fresh canonical Source ownership and independent saved
full-current prefix receiving.  No vias, old-thin-track capacity credit,
consumer allocation, current qualification or publication authority follows.
"""
import math
from pathlib import Path
import time


def _budget(value):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=10.:
        raise ValueError('bounded_distributed_supply_stage_lease_required')
    return float(value)


def _remaining(deadline):
    remaining=deadline-time.monotonic()
    if remaining<=0:raise ValueError('distributed_supply_stage_deadline')
    return min(10.,remaining)


def _replay_identity(proposal):
    import copy
    import json
    import cec_source_netlist_semantics as semantic
    result=copy.deepcopy(proposal)
    authority=result.get('source_authority',{})
    if 'export' in authority:
        # The fresh CLI emits a generated date. Only that known volatile raw
        # hash may differ; the full semantic netlist and exporter stay bound.
        authority['export']=semantic.replay_identity({'exporter':authority['export']})['exporter']
    # Native planners use tuples for immutable arrays. Public JSON transport
    # correctly restores those as lists; that is not a Source/contract edit.
    # Compare exact JSON identities, not Python's container equality (which
    # also incorrectly treats True, 1 and 1.0 as interchangeable). Nothing
    # except the known generated export hash above may be normalized away.
    return json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False)


def plan(board,source,*,board_hint,net,timeout_s=10.):
    import cec_force_current as force
    import cec_cell_row_rebuild as cells
    import cec_distributed_supply as supply
    import cec_distributed_supply_prefix as prefixes
    if type(board_hint)is not str or not board_hint or type(net)is not str or not net:
        raise ValueError('explicit_source_supply_board_and_net_required')
    deadline=time.monotonic()+_budget(timeout_s)
    source=Path(source).resolve(strict=True);sha=force._hash(source)
    binding=cells._source_binding(board)
    report=supply.audit(board,board_hint=board_hint,include_nets=[net])
    result=dict(scope='source_qualified_aggregate_supply_planar_join',complete=False,
        source=str(source),source_sha256=sha,source_binding=binding,board_hint=board_hint,net=net,
        current_qualified=False,release_authority=False,no_path_proof=False,
        current_authority_changed=False)
    if set(report['contracts'])!={net}:
        return dict(result,reason='existing_explicit_aggregate_supply_contract_required',
            refusals=report.get('refusals',{}))
    graph=report['nets'][net]
    if len(graph['native_components'])<2:
        return dict(result,reason='supply_native_pad_components_already_joined')
    if graph['planar_full_width_components'] is None or graph['unsupported_terminal_uuids']:
        return dict(result,reason='supported_planar_supply_terminal_inventory_required')
    context=prefixes.prepare(board,report['contracts'],board_hint=board_hint,
        timeout_s=_remaining(deadline))
    if net not in context['contracts']:
        return dict(result,reason='positive_canonical_supply_terminal_authority_required')
    if force._hash(source)!=sha or cells._source_binding(board)!=binding:
        raise ValueError('supply_source_changed_during_scope_compilation')
    _remaining(deadline)
    return dict(result,complete=True,contract=report['contracts'][net],
        source_native_components=graph['native_components'],
        source_planar_full_width_components=graph['planar_full_width_components'],
        source_authority=context['source_bindings'])


def construct_private(source,candidate,proposal,*,board_hint,timeout_s=10.):
    import pcbnew
    import cec_force_current as force
    import cec_distributed_supply as supply
    import cec_additive_pair_repair as additive
    deadline=time.monotonic()+_budget(timeout_s)
    source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
    if source==candidate or force._hash(source)!=force._hash(candidate):
        raise ValueError('exact_private_supply_source_copy_required')
    board=pcbnew.LoadBoard(str(source))
    fresh=plan(board,source,board_hint=board_hint,net=proposal['net'],timeout_s=_remaining(deadline))
    if _replay_identity(fresh)!=_replay_identity(proposal)or fresh.get('complete')is not True:
        raise ValueError('fresh_exact_supply_scope_required')
    old={force._uid(t)for t in board.GetTracks()}
    construction=supply.construct(board,board_hint=board_hint,include_nets=[fresh['net']],
        timeout_s=_remaining(deadline),max_joins=8,max_attempts=128,max_pair_s=1.,
        allow_maze=True,allow_supply_prefixes=True)
    if not construction.get('created_uuids'):
        return dict(complete=False,reason='finite_supply_geometry_incomplete',construction=construction,
            current_qualified=False,release_authority=False,no_path_proof=False)
    # Preserve original literal Source nodes; do not normalize the board or
    # use the legacy full-current-only finalizer for endpoint-qualified joins.
    additive.save_native_additions(candidate,board,construction,old,board_hint=board_hint)
    return dict(complete=True,construction=construction,current_qualified=False,
        release_authority=False,whole_saved_receiving_required=True)


def _partitions_survive(before,after):
    return all(any(set(group)<=set(child)for child in after)for group in before)


def receive(source,candidate,*,board_hint,net,timeout_s=10.):
    """Fresh saved scope; all ten enclosing receivers are still mandatory."""
    import pcbnew
    import cec_force_current as force
    import cec_additive_route_receiving as additive
    import cec_distributed_supply as supply
    import cec_distributed_supply_prefix as prefixes
    import cec_source_literal_additions as literal
    result=dict(ok=False,complete=False,errors=[],scope='saved_source_qualified_supply_native_join',
        current_qualified=False,release_authority=False,whole_shared_stage_still_required=True)
    deadline=time.monotonic()+_budget(timeout_s)
    try:
        source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
        if source==candidate:raise ValueError('distinct_supply_source_and_candidate_required')
        epoch=force._code_identity();families=[force._family(p,board_hint)for p in(source,candidate)]
        before,after=[pcbnew.LoadBoard(str(p))for p in(source,candidate)]
        scoped=plan(before,source,board_hint=board_hint,net=net,timeout_s=_remaining(deadline))
        if scoped.get('complete')is not True:raise ValueError('fresh_saved_supply_scope_refused')
        contracts={net:scoped['contract']}
        actual=supply.audit(after,board_hint=board_hint,include_nets=[net])
        if actual['contracts']!=contracts:raise ValueError('saved_aggregate_current_contract_changed')
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        if old.keys()-new.keys():raise ValueError('supply_scope_retired_source_material')
        incoming=set(new)-set(old)
        if any(new[uid][0] not in ('segment','group')for uid in incoming):
            raise ValueError('supply_scope_only_straight_tracks_and_ownership_groups')
        tracks={force._uid(t):t for t in after.GetTracks()if force._uid(t)in incoming}
        if not 1<=len(tracks)<=512:raise ValueError('bounded_saved_new_supply_tracks_required')
        names=literal.incoming_copper_nets(candidate.read_text(),set(tracks))
        if set(names)!=set(tracks) or any(n!=net for n in names.values()):
            raise ValueError('saved_new_supply_copper_scope_or_net_changed')
        if any(t.GetClass()!='PCB_TRACK' or t.GetNetname()!=net for t in tracks.values()):
            raise ValueError('new_supply_barrel_or_foreign_copper_forbidden')
        context=prefixes.prepare(after,contracts,board_hint=board_hint,timeout_s=_remaining(deadline))
        proof=prefixes.receive(after,contracts,tracks,context,timeout_s=_remaining(deadline))
        graph=supply._graph(after,net,scoped['contract'],prefix_uuids=proof['track_uuids'])
        previous=scoped['source_native_components'];current=graph['native_components']
        if len(current)>=len(previous) or not _partitions_survive(previous,current):
            raise ValueError('saved_supply_native_partitions_not_monotonically_joined')
        if (graph['planar_full_width_components'] is None or
                len(graph['planar_full_width_components'])>=len(scoped['source_planar_full_width_components'])):
            raise ValueError('saved_full_width_and_received_prefix_graph_not_improved')
        if epoch!=force._code_identity()or families!=[force._family(p,board_hint)for p in(source,candidate)]:
            raise ValueError('supply_source_candidate_or_code_epoch_changed')
        _remaining(deadline)
        result.update(ok=True,complete=True,added_native_uuids=sorted(tracks),
            source_components=len(previous),candidate_components=len(current),
            saved_prefix_receiving=proof,aggregate_current_contract=scoped['contract'],
            canonical_supply_source_independently_recompiled=True,
            current_authority_changed=False)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError)as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
