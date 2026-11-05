"""Bounded order repair of newly generated, physically shared pair segments.

No source copper is movable. Only a complete, strictly better transaction can
replace an earlier prefix; a failed retry restores exact native identities and
group memberships, including supporting return vias.
"""
from __future__ import annotations

import math
import os
import time


def shared_series_groups(board, pairs):
    """Connected pair segments sharing two proven opposite-land supports."""
    import cec_precision_route as precision
    names=[str(pair.get('name') or '') for pair in pairs]
    if len(set(names))!=len(names) or not all(names):
        return []
    stations={name:precision._pair_endpoint_stations(board,pair)
              for name,pair in zip(names,pairs)}
    footprints={}
    for fp in board.GetFootprints():
        footprints.setdefault(str(fp.GetReference()),[]).append(fp)
    edges=[]
    for i,first in enumerate(pairs):
        for second in pairs[i+1:]:
            if len({first['p'],first['n'],second['p'],second['n']})!=4:
                continue
            for a in stations[first['name']]:
                refs=set(a.get('physical_refs') or ())
                if a.get('kind')!='split-member-footprints' or len(refs)!=2:
                    continue
                for b in stations[second['name']]:
                    if b.get('kind')!='split-member-footprints' or set(b.get('physical_refs') or ())!=refs:
                        continue
                    witnesses=[]
                    for member in ('p','n'):
                        left,right=a.get(member+'_contacts') or (),b.get(member+'_contacts') or ()
                        if len(left)!=1 or len(right)!=1 or left[0]['ref']!=right[0]['ref']:
                            break
                        ref=left[0]['ref']
                        if len(footprints.get(ref,()))!=1:
                            break
                        pads=list(footprints[ref][0].Pads())
                        aa=[pad for pad in pads if pad.GetNetname()==first[member]]
                        bb=[pad for pad in pads if pad.GetNetname()==second[member]]
                        if len(pads)!=2 or len(aa)!=1 or len(bb)!=1:
                            break
                        if any(pad.GetNumber()!=str(contact['pad']) or
                               pad.GetPosition()!=precision._v(*contact['point_mm'])
                               for pad,contact in ((aa[0],left[0]),(bb[0],right[0]))):
                            break
                        witnesses.append(dict(ref=ref,member=member,
                            pads=[aa[0].m_Uuid.AsString(),bb[0].m_Uuid.AsString()]))
                    if len(witnesses)==2 and {row['ref'] for row in witnesses}==refs:
                        edges.append(dict(pairs=[first['name'],second['name']],supports=witnesses))
    adjacency={name:set() for name in names}
    for edge in edges:
        a,b=edge['pairs'];adjacency[a].add(b);adjacency[b].add(a)
    seen=set();groups=[]
    for name in names:
        if name in seen or not adjacency[name]:
            continue
        connected=set();pending=[name]
        while pending:
            current=pending.pop()
            if current in connected:continue
            connected.add(current);pending.extend(adjacency[current]-connected)
        seen.update(connected)
        groups.append(dict(pairs=[name for name in names if name in connected],
            edges=[edge for edge in edges if set(edge['pairs'])<=connected]))
    return groups


def _group_inventory(board):
    return {group.m_Uuid.AsString():frozenset(item.m_Uuid.AsString() for item in group.GetItems())
            for group in board.Groups()}


def _remove_empty_new_groups(board, original_groups):
    from cec_native_items import discard_items
    discard_items(board,[group for group in board.Groups()
        if group.m_Uuid.AsString() not in original_groups and not list(group.GetItems())])


def retry_groups(board, pairs, routed, refused, created_by_pair, source_ids, *,
                 route_order, max_wall_s=120., max_group_pairs=4):
    """Try refused-first ONCE per shared group, with a single shared deadline.

    ``route_order(names, deadline)`` must use the normal complete precision
    ladder with recursive order repair disabled. This controller never treats
    a favorable raw open count as complete pair qualification. Candidate
    quality, source copper identity and preserved coverage all remain gates.
    """
    from cec_local_copper_cell import copper_inventory
    from cec_native_copper_snapshot import CopperSnapshot
    from cec_native_items import discard_items
    from cec_probe_evidence import compact_pair_search_trace
    import cec_operation_budget as operation_budget

    max_wall_s=float(max_wall_s)
    if not math.isfinite(max_wall_s) or max_wall_s<=0:
        raise ValueError('invalid pair-order repair budget')
    if not isinstance(max_group_pairs,int) or isinstance(max_group_pairs,bool) or max_group_pairs<2:
        raise ValueError('invalid pair-order group bound')
    report=dict(policy='native-shared-series-joint-order-v2',attempts=[],adopted=0)
    routed=list(routed);refused=list(refused)
    failed={row['name'] for row in refused}
    completed={row['name'] for row in routed if row.get('route_mode')!='preexisting-locked'}
    if not failed or not completed:
        return routed,refused,report
    available=operation_budget.available_timeout(max_wall_s,os.environ,reserve_s=30)
    deadline=time.monotonic()+available
    all_source=set(source_ids)
    initial=copper_inventory(board)
    source_nets={value[1] for identifier,value in initial.items() if identifier in all_source}
    pair_map={pair['name']:pair for pair in pairs}
    for group in shared_series_groups(board,pairs):
        names=group['pairs'];scope=set(names)
        if (len(names)>max_group_pairs or not scope & failed or not scope & completed
                or not scope <= failed|completed
                or any(pair_map[name][member] in source_nets for name in names for member in ('p','n'))):
            continue
        order=[name for name in names if name in failed]+[name for name in names if name not in failed]
        if order==names:
            continue
        evidence=dict(group=group,order=order,selected=False)
        report['attempts'].append(evidence)
        if deadline-time.monotonic()<5.:
            evidence['reason']='insufficient shared order budget';break
        before=copper_inventory(board);groups_before=_group_inventory(board)
        owned=set().union(*(set(created_by_pair.get(name,())) for name in names))
        other_owned=set().union(*(set(items) for name,items in created_by_pair.items() if name not in scope))
        if not owned or not owned<=before.keys() or owned & (all_source|other_owned):
            evidence['reason']='new pair-copper ownership is incomplete or ambiguous';continue
        fixed={uid:value for uid,value in before.items() if uid not in owned}
        parent=CopperSnapshot(board,owned)
        fixed_parent=CopperSnapshot(board,fixed)
        old_group_members={uid:members-owned for uid,members in groups_before.items()}
        discard_items(board,[item for item in board.GetTracks() if item.m_Uuid.AsString() in owned])
        started=time.monotonic();candidate=None
        try:
            candidate=route_order(order,deadline)
            after=copper_inventory(board)
            now_groups=_group_inventory(board)
            created=after.keys()-fixed.keys()
            fixed_ok=(all(after.get(uid)==value for uid,value in fixed.items())
                and all(uid in now_groups and (now_groups[uid]-created)==members
                        for uid,members in old_group_members.items()))
            candidate_pairs=candidate.get('pairs') or {}
            candidate_done={row['name'] for row in candidate_pairs.get('routed') or ()}
            quality=candidate.get('route_quality') or {}
            accepted=(fixed_ok and bool(candidate.get('pairs_ok'))
                and bool(quality.get('ok')) and bool(quality.get('geometry_ok'))
                and scope==candidate_done and not candidate_pairs.get('refused')
                and not (after.keys() & owned))
            evidence.update(wall_s=round(time.monotonic()-started,3),fixed_copper_unchanged=fixed_ok,
                candidate_pairs_ok=bool(candidate.get('pairs_ok')),
                qualified_pairs=sorted(candidate_done),
                refused=[dict(name=row.get('name'),refused=row.get('refused'),
                    exhausted=bool(row.get('pair_search_budget_exhausted')),
                    search_trace=compact_pair_search_trace(row,limit=12))
                    for row in (candidate_pairs.get('refused') or ())[:max_group_pairs]])
            if not fixed_ok:
                raise RuntimeError('pair order retry modified fixed native copper or group membership')
            if accepted:
                routed=[row for row in routed if row['name'] not in scope]+list(candidate_pairs['routed'])
                refused=[row for row in refused if row['name'] not in scope]
                evidence.update(selected=True,reason=None,created_items=len(after)-len(fixed),
                    schedule=[row for row in candidate_pairs.get('schedule') or () if row.get('name') in scope])
                report['adopted']+=1
                # Keep mixed/source groups. Empty groups solely owned by the
                # discarded prefix have no remaining native members.
                discard_items(board,[native for native in board.Groups()
                    if native.m_Uuid.AsString() in groups_before
                    and groups_before[native.m_Uuid.AsString()]
                    and groups_before[native.m_Uuid.AsString()]<=owned
                    and not list(native.GetItems())])
                continue
            evidence['reason']='complete shared group did not qualify'
        except Exception as exc:
            evidence.update(reason='order transaction raised',error='%s: %s'%(type(exc).__name__,str(exc)[:500]))
        # Every trial-created item (including GND returns) belongs to this
        # transaction. Never remove an inherited item as collateral cleanup.
        discard_items(board,[item for item in board.GetTracks() if item.m_Uuid.AsString() not in fixed])
        _remove_empty_new_groups(board,groups_before)
        # An unexpected generator mutation is a rejected transaction, never
        # authority to alter the original obstacle. Restore its exact snapshot.
        remaining=copper_inventory(board)
        if remaining!=fixed:
            fixed_parent.restore()
        parent.restore()
        if copper_inventory(board)!=before or _group_inventory(board)!=groups_before:
            raise RuntimeError('pair order retry failed exact native rollback')
        evidence['rollback_exact']=True
    return routed,refused,report
