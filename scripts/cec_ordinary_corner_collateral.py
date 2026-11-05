"""Read-only scope for new native dangling legs exposed by ordinary cleanup.

Only literal unchanged source tracks implicated by a fresh native warning,
with exact endpoint adjacency to the existing cut, can be proposed. This is
not permission to delete copper: independent source-minus-cut receiving,
full native DRC, current, field and absolute Kelvin checks remain mandatory.
"""
import math
import time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_force_current as force


# Finite geometry-work scope, not a signal/current/clearance relaxation. A
# dangling obsolete branch can be long even when its exposing jog is tiny.
# The stage still caps the entire causal tail to FOUR native source tracks.
MAXIMUM_SOURCE_LEG_NM = 32000000


def plan(source,candidate,violations,retired,nets,*,allow_locked_source=False,timeout_s=2.):
    if (type(violations) is not list or not 1<=len(violations)<=4
            or type(retired) not in (list,set,tuple) or not 1<=len(retired)<=32
            or len(set(retired))!=len(retired)
            or any(type(u) is not str or not u for u in retired)
            or not isinstance(nets,(set,frozenset))
            or any(type(n) is not str or not n for n in nets)
            or type(allow_locked_source) is not bool
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10.):
        raise ValueError('bounded_actual_ordinary_corner_collateral_scope_required')
    deadline=time.monotonic()+timeout_s
    source,candidate=map(Path,(source,candidate))
    _,old=additive._nodes(source);_,new=additive._nodes(candidate)
    board=pcbnew.LoadBoard(str(source));items=list(board.GetTracks())
    live={force._uid(t):t for t in items}
    if len(live)!=len(items) or len(items)>16384 or not set(retired)<=live.keys():
        raise ValueError('unique_actual_collateral_source_inventory_required')
    grouped={force._uid(t) for g in board.Groups() for t in g.GetItems()}
    result=dict(ok=False,complete=True,retired_track_uuids=[],proofs=[],reason=None,
        mutation_authorized=False,saved_source_and_native_receiving_required=True,release_authority=False)
    selected=set()
    for violation in violations:
        if time.monotonic()>=deadline:raise ValueError('ordinary_corner_collateral_deadline')
        rows=violation.get('items') if type(violation) is dict else None
        if (type(violation) is not dict or violation.get('type')!='track_dangling'
                or type(rows) is not list or len(rows)!=1
                or type(rows[0]) is not dict or type(rows[0].get('uuid')) is not str):
            result['reason']='not_one_literal_new_native_dangling_track';return result
        uid=rows[0]['uuid'];t=live.get(uid)
        if (t is None or uid in selected or uid in retired or uid not in old or uid not in new
                or syntax._freeze(old[uid])!=syntax._freeze(new[uid])
                or t.GetClass()!='PCB_TRACK' or uid in grouped or t.GetParentGroup()
                or t.HasSolderMask() or t.IsLocked() and not allow_locked_source
                or str(t.GetNetname()) not in nets or not 0<t.GetWidth()<500000
                or not 0<t.GetLength()<=MAXIMUM_SOURCE_LEG_NM):
            result['reason']='not_bounded_unchanged_ungrouped_owned_ordinary_source';return result
        fields={v[0] if isinstance(v,list) else v for v in old[uid][1:]}
        if not fields<=set(('start','end','width','layer','net','uuid','locked')):
            result['reason']='collateral_has_other_fabrication_semantics';return result
        ends={tuple(t.GetStart()),tuple(t.GetEnd())};causal=[]
        for gone in retired:
            other=live[gone]
            if (other.GetClass()=='PCB_TRACK' and other.GetNetCode()==t.GetNetCode()
                    and other.GetLayer()==t.GetLayer()
                    and ends & {tuple(other.GetStart()),tuple(other.GetEnd())}):causal.append(gone)
        if not causal:
            result['reason']='no_exact_source_endpoint_adjacency_to_existing_cut';return result
        selected.add(uid)
        result['proofs'].append(dict(source_track_uuid=uid,net=str(t.GetNetname()),
            layer=int(t.GetLayer()),source_length_nm=int(t.GetLength()),
            causal_cut_track_uuids=sorted(causal),literal_native_warning=violation,
            exact_source_and_candidate_node_equal=True))
    if len(set(retired)|selected)>32:
        result['reason']='ordinary_receiver_retired_scope_bound';return result
    if time.monotonic()>=deadline:raise ValueError('ordinary_corner_collateral_deadline')
    result.update(ok=True,retired_track_uuids=sorted(selected),reason='bounded_actual_native_collateral_scope')
    return result
