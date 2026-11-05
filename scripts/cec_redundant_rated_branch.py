"""Exact unused distributed-supply track cuts, never a load/rating waiver.

The immutable complete supply catalog types the cut. Every surviving native
conductor, every actual drilled terminal, and every planar full-load terminal
partition must survive. No source barrel, group, pad, fill or new material is
permitted. This scope grants no thermal, Kelvin or release qualification.
"""
import math,time,tempfile
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_rated_branch_repair as rated
import cec_ordinary_route_receiving as ordinary
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_distributed_supply as supply
import cec_current_debt as debt
import cec_generated_pickup_retirement as pickups
from cec_generated_pickup_retirement import _scoped_terminal_graph
from cec_native_items import discard_items


def receive(source,candidate,*,board_hint,retired_track_uuids,allow_locked_track_uuids=(),
            timeout_s=10.,max_source_track_mm=8.,max_source_width_mm=.35,
            max_retired_tracks=8,allow_rated_source_inner_layers=False,
            future_single_face_pickup_uuids=()):
    started=time.monotonic();result=dict(schema=1,scope='exact_unused_distributed_supply_track_cut',
        ok=False,complete=False,errors=[],release_authority=False,current_qualified=False,
        barrel_ampacity_qualified=False,inherited_debt_qualified=False)
    try:
        if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
                or not 0<timeout_s<=30 or type(board_hint) is not str or not board_hint):
            raise ValueError('bounded_unused_rated_branch_context_required')
        deadline=started+timeout_s;paths=[Path(p).resolve() for p in (source,candidate)]
        if paths[0]==paths[1]:raise ValueError('distinct_saved_rated_cut_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        proposal=rated.plan(parent,paths[0],board_hint=board_hint,
            retired_track_uuids=retired_track_uuids,timeout_s=min(10.,deadline-time.monotonic()),
            max_source_track_mm=max_source_track_mm,max_source_width_mm=max_source_width_mm,
            max_retired_tracks=max_retired_tracks,
            allow_rated_source_inner_layers=allow_rated_source_inner_layers)
        cut=set(proposal['retired_track_uuids']);locks=ordinary._ids(
            allow_locked_track_uuids,'unused_rated_locked_scope',32)
        future_vias=ordinary._ids(future_single_face_pickup_uuids,'planned_single_face_pickups',2)
        live={force._uid(t):t for t in parent.GetTracks()}
        if (not locks<=cut or any(not live[u].IsLocked() for u in locks)
                or any(live[u].IsLocked() and u not in locks for u in cut)):
            raise ValueError('exact_source_rated_cut_lock_authority_required')
        if len(proposal['contracts'])!=1:raise ValueError('one_complete_source_supply_cut_required')
        net,contract=next(iter(proposal['contracts'].items()))
        authority=contract.get('current_authority') or {}
        amps=authority.get('amps')
        if (type(amps) not in (int,float) or not math.isfinite(amps) or amps<=0
                or contract.get('role')!='all_terminal_conservative_aggregate'):
            raise ValueError('complete_existing_aggregate_supply_authority_required')
        _,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        if old.keys()-new.keys()!=cut or new.keys()-old.keys():
            raise ValueError('unused_rated_branch_exact_source_cut_only')
        if future_vias:
            # This is a private prefix for a separately received atomic
            # pickup cut. The exact unchanged original holes must ALREADY
            # have only one real outer contact face after this track cut.
            # Their obsolete layer exits are not final retained boundaries.
            owned=pickups.plan(child,sorted(future_vias))
            result['independently_planned_single_face_pickup_scope']=owned
            result['remaining_planned_pickup_retirement_required']=True
        before=ordinary._partition(parent,deadline,retired_uuids=cut)
        after=ordinary._partition(child,deadline,retained_keys=set().union(*before))
        if any(not any(part<=q for q in after) for part in before):
            raise ValueError('unused_rated_cut_lost_surviving_native_partition')
        # Full-load graph ignores source barrels/zones for capacity, while a
        # separate drilled native model proves all actual terminal material.
        graphs=[supply._graph(b,net,contract) for b in (parent,child)]
        if (any(g['unsupported_terminal_uuids'] or g['planar_full_width_components'] is None
                or not g['native_connected'] for g in graphs)
                or graphs[0]['native_components']!=graphs[1]['native_components']
                or graphs[0]['planar_full_width_components']!=graphs[1]['planar_full_width_components']):
            raise ValueError('unused_rated_cut_changed_actual_full_load_terminal_partitions')
        result['unchanged_native_and_planar_full_load_graphs']=graphs
        drilled=[_scoped_terminal_graph(b,net,timeout_s=min(2.,deadline-time.monotonic()))
            for b in (parent,child)]
        if drilled[0]['pad_uuids']!=drilled[1]['pad_uuids']:
            raise ValueError('unused_rated_cut_changed_actual_drilled_terminal_inventory')
        result['actual_drilled_terminal_graphs']=drilled
        result['restored_retained_source_boundaries']=ordinary._boundaries(parent,child,
            [live[u] for u in sorted(cut)],deadline,exclusive_retired_via_uuids=future_vias)
        with force._thermal_hint(board_hint):
            fresh=rated.topology.distributed_supply_contracts(child,board_hint,
                netclass_resolver=rated.fr._project_netclass_resolver(str(paths[0])))
        if fresh['contracts'].get(net)!=contract:
            raise ValueError('unused_rated_cut_changed_existing_load_authority')
        with tempfile.TemporaryDirectory(prefix='cec-unused-rated-cut-') as tmp:
            expected=force._copy_family(paths[0],Path(tmp)/'expected')
            b=pcbnew.LoadBoard(str(expected));discard_items(b,[t for t in b.GetTracks() if force._uid(t) in cut])
            field._save_field_snapshot(b,expected)
            _,nodes=additive._nodes(expected)
            if nodes.keys()!=old.keys()-cut or any(syntax._freeze(nodes[u])!=syntax._freeze(old[u]) for u in nodes):
                raise ValueError('unused_rated_projection_changed_unowned_source')
            replay=additive.receive(expected,paths[1],timeout_s=min(10.,deadline-time.monotonic()))
            result['exact_saved_subtract_and_refill_receiving']=replay
            if not replay['ok'] or not replay['complete']:
                raise ValueError('unused_rated_exact_subtract_and_refill_replay_refused')
        current=debt.receive(*paths,board_hint=board_hint)
        if not current['ok'] or not current['complete']:
            raise ValueError('unused_rated_cut_increased_source_current_debt')
        result['unchanged_whole_source_current_debt']=current
        if (epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]
                or time.monotonic()>=deadline):
            raise ValueError('unused_rated_cut_source_candidate_code_or_deadline_changed')
        result.update(ok=True,complete=True,source_proposal=proposal,
            receiving_wall_budget_s=float(timeout_s),
            retired_track_uuids=sorted(cut),added_native_uuids=[],
            source_candidate_and_code_unchanged=True,
            full_native_drc_field_kelvin_and_release_receiving_still_required=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=round(time.monotonic()-started,6)
    return result


def receive_with_single_face_pickups(source,candidate,*,board_hint,retired_track_uuids,
        retired_pickup_via_uuids,allow_locked_track_uuids=(),timeout_s=20.,
        max_source_track_mm=8.,max_source_width_mm=.35,max_retired_tracks=8,
        allow_rated_source_inner_layers=False):
    """Atomically receive a dead supply tree and its now-unused owned holes.

    The hypothetical track-only prefix must pass the independent full-load
    cut receiver first. Only then may the existing source-generator receiver
    prove exactly one surviving outer contact face for each requested pickup.
    This prefix is never a candidate/admission waiver for a dangling barrel.
    """
    started=time.monotonic();r=dict(schema=1,scope='exact_unused_rated_tree_and_single_face_pickups',
        ok=False,complete=False,errors=[],current_qualified=False,release_authority=False,
        private_track_only_prefix_not_candidate=True)
    try:
        if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=30:
            raise ValueError('bounded_compound_unused_supply_context_required')
        tracks=ordinary._ids(retired_track_uuids,'compound_unused_rated_tracks',32)
        vias=ordinary._ids(retired_pickup_via_uuids,'compound_single_face_pickups',2)
        if not tracks or not vias or tracks&vias:raise ValueError('exact_distinct_track_and_pickup_scopes_required')
        paths=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        with tempfile.TemporaryDirectory(prefix='cec-unused-rated-tree-') as tmp:
            prefix=force._copy_family(paths[0],Path(tmp)/'PRIVATE-NOT-CANDIDATE')
            b=pcbnew.LoadBoard(str(prefix));live={force._uid(t):t for t in b.GetTracks()}
            if not tracks<=live.keys():raise ValueError('compound_unused_tracks_are_stale')
            discard_items(b,[live[u] for u in sorted(tracks)]);field._save_field_snapshot(b,prefix)
            first=receive(paths[0],prefix,board_hint=board_hint,retired_track_uuids=sorted(tracks),
                allow_locked_track_uuids=allow_locked_track_uuids,timeout_s=timeout_s,
                future_single_face_pickup_uuids=sorted(vias),
                max_source_track_mm=max_source_track_mm,max_source_width_mm=max_source_width_mm,
                max_retired_tracks=max_retired_tracks,
                allow_rated_source_inner_layers=allow_rated_source_inner_layers)
            r['independent_full_load_track_cut']=first
            if not first['ok'] or not first['complete']:
                raise ValueError('compound_unused_supply_track_cut_refused:'+str(first['errors']))
            proposal=pickups.plan(b,sorted(vias))
            second=pickups.receive(prefix,paths[1],proposal,board_hint=board_hint)
            r['independent_single_face_source_pickup_retirement']=second
            if not second['ok'] or not second['complete']:
                raise ValueError('compound_unused_supply_source_pickup_cut_refused:'+str(second['errors']))
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        old=ordinary._partition(parent,time.monotonic()+10.,retired_uuids=tracks|vias)
        new=ordinary._partition(child,time.monotonic()+10.,retained_keys=set().union(*old))
        if any(not any(part<=q for q in new) for part in old):
            raise ValueError('compound_unused_supply_lost_original_surviving_partition')
        current=debt.receive(*paths,board_hint=board_hint);r['whole_original_current_debt']=current
        if not current['ok'] or not current['complete']:
            raise ValueError('compound_unused_supply_current_debt_changed')
        if (epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]
                or time.monotonic()-started>=timeout_s):
            raise ValueError('compound_unused_supply_inputs_code_or_deadline_changed')
        r.update(ok=True,complete=True,retired_track_uuids=sorted(tracks),
            retired_via_uuids=sorted(vias),added_native_uuids=[],
            source_candidate_and_code_unchanged=True,
            full_native_drc_fields_kelvin_current_and_release_receiving_still_required=True)
    except Exception as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    r['elapsed_s']=round(time.monotonic()-started,6)
    return r
