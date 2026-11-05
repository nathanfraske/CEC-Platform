"""Typed cleanup of newly emitted full-load distributed-supply tails.

Only new native dangling-track hints absent from the immutable macro source
may be considered. The existing supply-loop receiver, not a warning or a
width heuristic, must prove exact subtraction, actual connectivity and every
full-load face join. Original copper is excluded unless an exact opt-in names
a newly dangling, geometrically unchanged small-supply tail. Main force buses,
ground, groups and vias are not retirement candidates. This private prefix is never an admission
baseline: final receiving against the original macro source is mandatory.
"""
import math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_native_macro_tail_cleanup as hints
import cec_distributed_loop_retirement as loops
import cec_redundant_force_branch as force_branches
import cec_current_topology as topology
import cec_current_debt as debt
import cec_fr as fr
import cec_additive_route_receiving as additive
import cec_field_coupling as field


def construct(original_source,prefix,outdir,*,board_hint,original_native,proposed_native,timeout_s=10.,
              allow_obsolete_source_track_uuids=()):
    result=dict(schema=1,scope='new_generated_full_load_supply_tail_cut',ok=False,complete=False,
        changed=False,candidate=None,errors=[],retired_track_uuids=[],retired_via_uuids=[],
        original_macro_source_receiving_still_required=True,private_prefix_not_admission_baseline=True,
        current_qualified=False,release_authority=False)
    started=time.monotonic()
    try:
        if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
                or type(board_hint) is not str or not board_hint):
            raise ValueError('bounded_explicit_macro_supply_tail_context_required')
        original_source,prefix=map(lambda p:Path(p).resolve(),(original_source,prefix))
        outdir=Path(outdir)
        if original_source==prefix or outdir.exists():raise ValueError('distinct_fresh_macro_supply_tail_prefix_required')
        families=[force._family(p,board_hint) for p in (original_source,prefix)]
        epoch=force._code_identity();original=pcbnew.LoadBoard(str(original_source));board=pcbnew.LoadBoard(str(prefix))
        old_ids={force._uid(t) for t in original.GetTracks()};live={force._uid(t):t for t in board.GetTracks()}
        warnings=hints.new_warning_ids(original_native,proposed_native)
        allowed=set(allow_obsolete_source_track_uuids)
        if (type(allow_obsolete_source_track_uuids) not in (list,tuple) or len(allowed)!=len(allow_obsolete_source_track_uuids)
                or len(allowed)>4 or any(type(u) is not str or not u for u in allowed)
                or not allowed<=old_ids & live.keys() or allowed and not allowed & set(warnings)):
            raise ValueError('exact_original_newly_dangling_supply_tail_scope_required')
        old={force._uid(t):t for t in original.GetTracks()}
        for uid in allowed:
            def unchanged(t):
                if t.GetClass()!='PCB_TRACK':return None
                return (t.GetNetname(),t.GetLayer(),t.GetWidth(),tuple(t.GetStart()),tuple(t.GetEnd()),t.IsLocked())
            if unchanged(old[uid]) is None or unchanged(old[uid])!=unchanged(live[uid]):
                raise ValueError('source_supply_tail_geometry_must_be_unchanged')
        with force._thermal_hint(board_hint):
            catalog=topology.distributed_supply_contracts(board,board_hint,
                netclass_resolver=fr._project_netclass_resolver(str(prefix)))
            domains=topology.board_current_domains(board,board_hint)
            contracts=topology.route_width_contracts(board,board_hint)
        reference={str(z.GetNetname()) for z in board.Zones() if
            int(z.GetLayer()) in {board.GetLayerID(n) for n in fr.plane_layers(board)}}
        protected=reference|set(fr.coupled_pair_nets(board))|{'GND'}
        # A declared small current domain is a DIFFERENT positive type from
        # a distributed all-terminal supply. It uses its own exact force-
        # branch receiver; never reinterpret it as an ordinary net or a load
        # allocation. Whole main-bus dimensions remain outside this work tier.
        force_nets={net for net,domain in domains.items() if net not in protected
            and domain.get('complete') is True and domain.get('source_refs') and domain.get('sink_refs')
            and net in contracts and {'F.Cu','B.Cu'}<=set(contracts[net].get('routing_layers',()))
            and all(type(contracts[net].get('required_by_layer_mm',{}).get(face)) in (int,float)
                and math.isfinite(contracts[net]['required_by_layer_mm'][face])
                and 0<contracts[net]['required_by_layer_mm'][face]<=1. for face in ('F.Cu','B.Cu'))}
        selected=[u for u in warnings if (u not in old_ids or u in allowed) and u in live and live[u].GetClass()=='PCB_TRACK'
            and str(live[u].GetNetname()) not in protected
            and str(live[u].GetNetname()) in set(catalog['contracts'])|force_nets]
        if selected:
            from cec_ordinary_tail_discovery import _discover_native_leaf_chains
            discovery=_discover_native_leaf_chains(board,selected,
                positive_nets=set(catalog['contracts'])|force_nets,maximum_width_nm=1000000,timeout_s=timeout_s,
                allow_connected_seed_cohorts=True)
            result['native_whole_supply_leaf_chain_discovery']=discovery
            derived=set(discovery['proposed_exact_track_uuids'])
            if not selected or not derived or not discovery['complete']:
                raise ValueError('complete_positive_native_supply_leaf_chain_required')
            if derived & old_ids - allowed:
                raise ValueError('source_supply_leaf_requires_exact_whole_original_tail_scope')
            selected=sorted(derived)
        if not allowed<=set(selected):raise ValueError('source_supply_tail_requires_positive_actual_current_type')
        if not selected:
            result.update(ok=True,complete=True);return result
        nets={str(live[u].GetNetname()) for u in selected}
        if len(nets)!=1 or len(selected)>4:raise ValueError('one_net_four_new_supply_tail_work_bound')
        net=next(iter(nets));locks=[u for u in selected if live[u].IsLocked()]
        supply_type=net in catalog['contracts']
        if supply_type:
            proposal=loops.plan(board,prefix,net=net,board_hint=board_hint,track_uuids=selected,
                allow_locked_track_uuids=locks,timeout_s=timeout_s)
            loops.subtract(board,proposal)
        else:
            _,contract=force_branches._model(board,net,board_hint)
            for uid in selected:
                item=live[uid];face=board.GetLayerName(item.GetLayer())
                if (face not in ('F.Cu','B.Cu') or not 0<item.GetLength()<=32000000
                        or not math.ceil(contract['required_by_layer_mm'][face]*1e6)<=item.GetWidth()<=1000000):
                    raise ValueError('new_force_tail_must_retain_actual_whole_source_floor')
            proposal=force_branches.plan(board,selected,net=net,board_hint=board_hint,
                allow_locked_track_uuids=locks,max_retired_tracks=4,timeout_s=timeout_s)
            force_branches.subtract(board,proposal)
        child=force._copy_family(prefix,outdir);additive._ground_refill(board);field._save_field_snapshot(board,child)
        result.update(candidate=str(child),candidate_sha256=force._hash(child),
            positive_type='distributed_whole_load' if supply_type else 'source_declared_whole_current_domain',
            proposal={k:v for k,v in proposal.items() if k!='source_binding'},
            original_source=str(original_source),original_source_sha256=force._hash(original_source),
            prefix=str(prefix),prefix_sha256=force._hash(prefix),retired_track_uuids=sorted(selected),
            explicitly_requested_original_obsolete_track_uuids=sorted(allowed))
        proof=(loops.receive(prefix,child,proposal,board_hint=board_hint) if supply_type else
            force_branches.receive(prefix,child,track_uuids=selected,net=net,board_hint=board_hint,
                allow_locked_track_uuids=locks,max_retired_tracks=4,timeout_s=timeout_s))
        result['independent_exact_full_load_supply_loop_receiving']=proof
        if not proof['ok'] or not proof['complete']:
            raise ValueError('new_supply_tail_exact_native_full_load_receiving_refused:'+str(proof['errors']))
        current=debt.receive(prefix,child,board_hint=board_hint)
        result['independent_current_nonregression']=current
        if not current['ok'] or not current['complete']:
            raise ValueError('new_supply_tail_current_nonregression_refused:'+str(current['errors']))
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (original_source,prefix)]:
            raise ValueError('macro_supply_tail_source_prefix_or_code_changed')
        result.update(ok=True,complete=True,changed=True,code_identity=epoch,
            source_and_prefix_and_code_unchanged=True,removed_length_mm=(proposal['removed_length_nm']/1e6
                if supply_type else sum(math.dist(r['start_nm'],r['end_nm']) for r in proposal['source_tracks'])/1e6),
            independent_native_drc_field_and_whole_original_macro_receiving_still_required=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=time.monotonic()-started
    return result
