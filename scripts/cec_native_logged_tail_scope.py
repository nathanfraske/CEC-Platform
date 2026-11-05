"""Bounded source-typed tail-frontier proposals from fresh native reports.

A removed dead end can expose the next old segment. Grow its exact original
UUID scope before accepting a complete transaction. This selector never cuts,
admits, grants ownership, or treats an intermediate diagnostic as a source.
Independent ordinary/source-chain/current/field/native receivers still decide.
"""
import math,time


def extend(rows,report,seeds,eligible_nets,probe,*,allow_locked_track_uuids=(),
           maximum_tracks=32,maximum_probes=8,timeout_s=90.):
    if (type(rows) not in (list,tuple) or not 1<=len(rows)<=16384
            or type(seeds) not in (list,tuple,set,frozenset) or not seeds
            or len(seeds)!=len(set(seeds)) or type(eligible_nets) not in (set,frozenset)
            or any(type(n) is not str or not n for n in eligible_nets) or not callable(probe)
            or type(maximum_tracks) is not int or not 1<=maximum_tracks<=32
            or type(maximum_probes) is not int or not 1<=maximum_probes<=8
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=90.):
        raise ValueError('bounded_positive_source_native_tail_frontier_required')
    if any(type(r) is not dict or type(r.get('uuid')) is not str or not r['uuid'] for r in rows):
        raise ValueError('literal_original_native_tail_inventory_required')
    source={r['uuid']:r for r in rows}
    if len(source)!=len(rows):raise ValueError('ambiguous_original_native_tail_identity')
    if (type(allow_locked_track_uuids) not in (list,tuple,set,frozenset)
            or len(allow_locked_track_uuids)!=len(set(allow_locked_track_uuids))
            or len(allow_locked_track_uuids)>32 or not set(allow_locked_track_uuids)<=source.keys()):
        raise ValueError('bounded_exact_original_tail_lock_scope_required')
    locked=set(allow_locked_track_uuids)
    def heads(raw,kind):
        if (type(raw) is not dict or type(raw.get('violations')) is not list
                or len(raw['violations'])>20000 or type(raw.get('unconnected_items')) is not list
                or len(raw['unconnected_items'])>20000):
            raise ValueError('complete_bounded_native_tail_report_required')
        found=set()
        for finding in raw['violations']:
            if type(finding) is not dict or type(finding.get('type')) is not str:
                raise ValueError('literal_native_tail_finding_required')
            if finding['type']!=kind:continue
            if (type(finding.get('items')) is not list or len(finding['items'])!=1
                    or type(finding['items'][0]) is not dict
                    or type(finding['items'][0].get('uuid')) is not str):
                raise ValueError('exact_single_native_tail_identity_required')
            uid=finding['items'][0]['uuid']
            if uid not in source:raise ValueError('reported_tail_not_in_original_source_inventory')
            found.add(uid)
        return found
    initial=heads(report,'track_dangling');initial_vias=heads(report,'via_dangling')
    scope=set(seeds)
    if not scope<=initial:raise ValueError('tail_seed_requires_actual_original_native_finding')
    wanted={source[u].get('net') for u in scope}
    def allowed(uid):
        r=source[uid]
        return (r.get('kind')=='PCB_TRACK' and r.get('net') in eligible_nets
            and r.get('net') in wanted and type(r.get('width_nm')) is int and 0<r['width_nm']<500000
            and r.get('grouped') is False and type(r.get('locked')) is bool
            and (not r['locked'] or uid in locked))
    if any(not allowed(u) for u in scope) or len(scope)>maximum_tracks:
        raise ValueError('tail_seed_is_not_scoped_source_ordinary_copper')
    stages=[];deadline=time.monotonic()+timeout_s
    result=dict(schema=1,retired_track_uuids=[],stages=stages,frontier_exhausted=False,
        stop=None,requires_typed_barrel_phase=False,barrel_obligations=[],
        source_board_mutated=False,mutation_or_owner_authority=False,
        independently_received_whole_source_cut_still_required=True,
        no_path_proof=False,routing_admitted=False,release_authority=False)
    for _ in range(maximum_probes):
        if time.monotonic()>=deadline:result['stop']='native_tail_planning_deadline';break
        trial=probe(tuple(sorted(scope)))
        frontier=heads(trial,'track_dangling')-initial
        vias=heads(trial,'via_dangling')-initial_vias
        if (frontier|heads(trial,'track_dangling')|vias)&scope:
            raise ValueError('stale_native_tail_probe_still_reports_retired_material')
        stages.append(dict(retired_track_uuids=sorted(scope),new_tail_heads=sorted(frontier),
            new_barrel_obligations=sorted(vias),reported_opens=len(trial['unconnected_items'])))
        result.update(retired_track_uuids=sorted(scope),barrel_obligations=sorted(vias),
            requires_typed_barrel_phase=bool(vias))
        if not frontier:
            result.update(frontier_exhausted=True,stop='finite_native_tail_frontier_exhausted');break
        if any(not allowed(u) for u in frontier):result['stop']='next_tail_has_unowned_or_protected_source_material';break
        if len(scope|frontier)>maximum_tracks:result['stop']='original_tail_inventory_work_bound';break
        scope.update(frontier)
    if result['stop'] is None:result['stop']='native_tail_probe_work_bound'
    return result
